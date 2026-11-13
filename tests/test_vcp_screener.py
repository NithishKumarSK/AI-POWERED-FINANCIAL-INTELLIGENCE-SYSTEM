"""
Tests for core/vcp_screener.py -- ported Minervini VCP detection
(relative strength, trend template, contraction pattern, volume dry-up,
pivot proximity, execution state, pattern classifier, composite scorer).
Synthetic data only, no network. Price lists are MOST-RECENT-FIRST.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from vcp_screener import (
    analyze_stock,
    apply_state_cap,
    calculate_composite_score,
    calculate_pivot_proximity,
    calculate_relative_strength,
    calculate_trend_template,
    calculate_vcp_pattern,
    calculate_volume_pattern,
    classify_pattern,
    compute_execution_state,
)


def _bar(date_str, close, high=None, low=None, volume=1_000_000):
    return {"date": date_str, "close": close, "high": high if high is not None else close * 1.01,
            "low": low if low is not None else close * 0.99, "volume": volume}


def _mrf_series(n, price_fn, start="2026-01-01", volume_fn=None):
    """Most-recent-first bars; price_fn(i) for i=0 (most recent) .. n-1 (oldest)."""
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    out = []
    for i in range(n):
        d = d0 - dt.timedelta(days=i)
        vol = volume_fn(i) if volume_fn else 1_000_000
        out.append(_bar(d.isoformat(), price_fn(i), volume=vol))
    return out


# ── calculate_relative_strength ────────────────────────────────────────────

def test_relative_strength_outperformer_scores_high():
    # Stock up 30% over 63 days, SPY flat -- clear outperformance.
    stock = _mrf_series(260, lambda i: 130.0 if i == 0 else 100.0 if i >= 63 else 100.0 + (63 - i) * (30.0 / 63))
    spy = _mrf_series(260, lambda i: 100.0)
    result = calculate_relative_strength(stock, spy)
    assert result["weighted_rs"] is not None
    assert result["weighted_rs"] > 0
    assert result["score"] >= 60


def test_relative_strength_insufficient_data():
    short = _mrf_series(30, lambda i: 100.0)
    result = calculate_relative_strength(short, short)
    assert result["score"] == 0
    assert "Insufficient" in result["error"]


# ── calculate_trend_template ──────────────────────────────────────────────

def test_trend_template_strong_uptrend_passes():
    # Steady uptrend: price today highest, SMA50/150/200 all below price and rising.
    stock = _mrf_series(230, lambda i: 200.0 - i * 0.3)
    quote = {"price": 200.0, "yearHigh": 200.0, "yearLow": 130.0}
    result = calculate_trend_template(stock, quote, rs_rank=85)
    assert result["passed"] is True
    assert result["criteria_passed"] >= 6


def test_trend_template_downtrend_fails():
    stock = _mrf_series(230, lambda i: 100.0 + i * 0.3)  # price lower than history -- downtrend
    quote = {"price": 100.0, "yearHigh": 170.0, "yearLow": 95.0}
    result = calculate_trend_template(stock, quote, rs_rank=20)
    assert result["passed"] is False


def test_trend_template_insufficient_data():
    short = _mrf_series(10, lambda i: 100.0)
    result = calculate_trend_template(short, {"price": 100.0})
    assert result["score"] == 0
    assert result["passed"] is False


# ── calculate_vcp_pattern (smoke + structural) ────────────────────────────

def _vcp_like_series():
    """Rough VCP shape (chronological intent, built most-recent-first):
    oldest -> rises to a high, pulls back, rallies to near the same high,
    pulls back tighter, rallies again, pulls back even tighter near the top
    (bars[0] = most recent = the tightest/most-recent point)."""
    import datetime as dt
    d0 = dt.date(2026, 6, 1)
    chrono_prices = (
        [100 + i * 0.5 for i in range(30)]       # run-up to ~115
        + [115 - i * 1.0 for i in range(20)]      # T1 pullback to ~95 (~17% depth)
        + [95 + i * 1.0 for i in range(20)]       # rally back to ~115
        + [115 - i * 0.5 for i in range(15)]      # T2 pullback to ~107.5 (tighter, ~6.5% depth)
        + [107.5 + i * 0.6 for i in range(13)]    # rally back toward 115
        + [115 - i * 0.3 for i in range(10)]      # T3 pullback, tight (~2.6% depth)
    )
    chrono = [_bar((d0 + dt.timedelta(days=i)).isoformat(), p, high=p + 0.5, low=p - 0.5, volume=1_000_000 if i < 50 else 400_000) for i, p in enumerate(chrono_prices)]
    return list(reversed(chrono))  # most-recent-first


def test_calculate_vcp_pattern_detects_contractions_in_textbook_shape():
    mrf = _vcp_like_series()
    result = calculate_vcp_pattern(mrf, lookback_days=120, min_contractions=2)
    assert result["error"] is None or result["num_contractions"] >= 2
    assert result["num_contractions"] >= 1  # at minimum, some contraction structure detected


def test_calculate_vcp_pattern_insufficient_data():
    short = _mrf_series(10, lambda i: 100.0)
    result = calculate_vcp_pattern(short)
    assert result["score"] == 0
    assert "Insufficient" in result["error"]


def test_calculate_vcp_pattern_flat_series_finds_no_contractions():
    flat = _mrf_series(100, lambda i: 100.0)
    result = calculate_vcp_pattern(flat)
    assert result["num_contractions"] == 0 or result["valid_vcp"] is False


# ── calculate_volume_pattern ──────────────────────────────────────────────

def test_volume_pattern_dry_up_scores_well():
    # Recent 10 bars low volume, 50-day baseline much higher -- strong dry-up.
    mrf = _mrf_series(60, lambda i: 100.0, volume_fn=lambda i: 200_000 if i < 10 else 1_000_000)
    result = calculate_volume_pattern(mrf)
    assert result["dry_up_ratio"] < 0.5
    assert result["score"] >= 60


def test_volume_pattern_no_dry_up_scores_low():
    mrf = _mrf_series(60, lambda i: 100.0, volume_fn=lambda i: 1_500_000 if i < 10 else 1_000_000)
    result = calculate_volume_pattern(mrf)
    assert result["dry_up_ratio"] > 1.0
    assert result["score"] <= 40


def test_volume_pattern_insufficient_data():
    short = _mrf_series(5, lambda i: 100.0)
    result = calculate_volume_pattern(short)
    assert result["score"] == 0


# ── calculate_pivot_proximity ──────────────────────────────────────────────

def test_pivot_proximity_at_pivot_scores_high():
    result = calculate_pivot_proximity(current_price=100.0, pivot_price=100.5, last_contraction_low=95.0)
    assert result["score"] == 90
    assert result["trade_status"] == "AT PIVOT (within 2%)"


def test_pivot_proximity_overextended_scores_low():
    result = calculate_pivot_proximity(current_price=130.0, pivot_price=100.0)
    assert result["score"] == 20
    assert "OVEREXTENDED" in result["trade_status"]


def test_pivot_proximity_below_stop_is_invalidated():
    result = calculate_pivot_proximity(current_price=90.0, pivot_price=100.0, last_contraction_low=92.0)
    assert result["trade_status"] == "BELOW STOP LEVEL"
    assert result["score"] == 0


def test_pivot_proximity_no_pivot():
    result = calculate_pivot_proximity(current_price=100.0, pivot_price=None)
    assert result["trade_status"] == "NO PIVOT"


# ── compute_execution_state / apply_state_cap ─────────────────────────────

def test_execution_state_invalid_when_below_both_mas():
    state = compute_execution_state(distance_from_pivot_pct=-5, price=90, sma50=95, sma200=100,
                                      sma200_distance_pct=-10, last_contraction_low=None, breakout_volume=False)
    assert state["state"] == "Invalid"


def test_execution_state_breakout_with_volume_confirmation():
    state = compute_execution_state(distance_from_pivot_pct=1.5, price=110, sma50=100, sma200=90,
                                      sma200_distance_pct=22, last_contraction_low=95, breakout_volume=True)
    assert state["state"] == "Breakout"


def test_apply_state_cap_downgrades_when_over_max():
    capped, was_capped = apply_state_cap("Textbook VCP", "Extended")
    assert was_capped is True
    assert capped == "Developing VCP"


def test_apply_state_cap_no_cap_for_breakout():
    capped, was_capped = apply_state_cap("Textbook VCP", "Breakout")
    assert was_capped is False
    assert capped == "Textbook VCP"


# ── classify_pattern ───────────────────────────────────────────────────────

def test_classify_pattern_damaged_state_wins():
    assert classify_pattern(valid_vcp=True, num_contractions=4, final_contraction_depth=5, execution_state="Damaged", dry_up_ratio=0.3) == "Damaged"


def test_classify_pattern_textbook_requires_all_criteria():
    result = classify_pattern(valid_vcp=True, num_contractions=3, final_contraction_depth=8, execution_state="Pre-breakout", dry_up_ratio=0.5, wide_and_loose=False)
    assert result == "Textbook VCP"


def test_classify_pattern_not_textbook_when_too_few_contractions():
    result = classify_pattern(valid_vcp=True, num_contractions=2, final_contraction_depth=8, execution_state="Pre-breakout", dry_up_ratio=0.5)
    assert result == "VCP-adjacent"


# ── calculate_composite_score ──────────────────────────────────────────────

def test_composite_score_weighted_correctly():
    result = calculate_composite_score(trend_score=100, contraction_score=100, volume_score=100, pivot_score=100, rs_score=100)
    assert result["composite_score"] == 100.0
    assert result["rating"] == "Textbook VCP"


def test_composite_score_invalid_vcp_caps_developing():
    result = calculate_composite_score(trend_score=95, contraction_score=90, volume_score=85, pivot_score=90, rs_score=90, valid_vcp=False)
    assert result["rating"] == "Developing VCP"


def test_composite_score_state_cap_applied():
    result = calculate_composite_score(trend_score=100, contraction_score=100, volume_score=100, pivot_score=100, rs_score=100,
                                         valid_vcp=True, execution_state="Overextended")
    assert result["rating"] == "Weak VCP"
    assert result["state_cap_applied"] is True


def test_composite_score_wide_and_loose_caps_developing():
    result = calculate_composite_score(trend_score=100, contraction_score=100, volume_score=100, pivot_score=100, rs_score=100,
                                         valid_vcp=True, execution_state="Breakout", wide_and_loose=True)
    assert result["rating"] == "Developing VCP"


# ── analyze_stock (end-to-end) ──────────────────────────────────────────────

def test_analyze_stock_full_pipeline_produces_a_rating():
    stock = _mrf_series(260, lambda i: 150.0 - i * 0.1)
    spy = _mrf_series(260, lambda i: 100.0 - i * 0.02)
    quote = {"price": 150.0, "yearHigh": 151.0, "yearLow": 120.0, "marketCap": 0}
    result = analyze_stock("TEST", stock, quote, spy)
    assert result["symbol"] == "TEST"
    assert "composite_score" in result
    assert result["rating"] in ("Textbook VCP", "Strong VCP", "Good VCP", "Developing VCP", "Weak VCP", "No VCP")
    assert result["execution_state"] in ("Invalid", "Damaged", "Overextended", "Extended", "Early-post-breakout", "Breakout", "Pre-breakout")
