"""
Tests for core/stockbee_exhaustion_hammer_screener.py -- ported Stockbee
selling-exhaustion hammer detection. Synthetic data only, no network.
All Bar lists are MOST-RECENT-FIRST.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from stockbee_exhaustion_hammer_screener import (
    Bar,
    ScreenerConfig,
    analyze_symbol,
    close_location_pct,
    detect_hammer_profile,
    detect_pullback_profile,
    market_gate_score,
    pct_change,
    risk_distance_score,
    score_to_rating,
    score_to_state,
)


def _bar(date_str, open_, high, low, close, volume=5_000_000):
    return Bar(date=date_str, open=open_, high=high, low=low, close=close, volume=volume)


def _build_hammer_scenario():
    """A textbook setup: 40 flat days, a strong run-up to a recent high,
    a multi-day pullback that undercuts a prior low, then a hammer candle
    that reclaims it on elevated volume -- MRF (bars[0] = latest/hammer day)."""
    import datetime as dt
    d0 = dt.date(2026, 1, 1)
    chrono = []

    # Base + run-up to a high around day 60 (recent high).
    price = 50.0
    for i in range(70):
        if i < 20:
            price = 50.0
        else:
            price *= 1.012  # steady climb to a high
        chrono.append(_bar((d0 + dt.timedelta(days=i)).isoformat(), price, price * 1.01, price * 0.99, price, 1_000_000))

    recent_high = chrono[-1].close

    # Pullback: 10 days of decline, undercutting a short-term low.
    pullback_low = recent_high * 0.80
    for i in range(70, 80):
        d = d0 + dt.timedelta(days=i)
        frac = (i - 69) / 10.0
        p = recent_high - (recent_high - pullback_low) * frac
        chrono.append(_bar(d.isoformat(), p * 1.01, p * 1.02, p * 0.98, p * 0.995, 800_000))

    prior_low = min(b.low for b in chrono[-5:])

    # Hammer day: opens near the low, dips below prior_low intraday, then
    # reclaims and closes strong near the high, on elevated volume.
    hammer_low = prior_low * 0.97
    hammer_open = prior_low * 1.01
    hammer_close = prior_low * 1.09
    hammer_high = hammer_close * 1.005
    chrono.append(_bar((d0 + dt.timedelta(days=80)).isoformat(), hammer_open, hammer_high, hammer_low, hammer_close, 3_000_000))

    return list(reversed(chrono))  # most-recent-first


# ── pure helpers ──────────────────────────────────────────────────────────

def test_pct_change_basic():
    assert abs(pct_change(110, 100) - 10.0) < 1e-9
    assert pct_change(100, 0) == 0.0  # guarded against division by zero


def test_close_location_pct_at_high_is_100():
    bar = _bar("d", 10, 20, 10, 20)
    assert close_location_pct(bar) == 100.0


def test_risk_distance_score_bands():
    assert risk_distance_score(2.0) == 15
    assert risk_distance_score(15.0) == 0


def test_market_gate_score_mapping():
    assert market_gate_score("allowed") == 5
    assert market_gate_score("neutral") == 3
    assert market_gate_score("restrictive") == 0


def test_score_to_rating_bands():
    assert score_to_rating(95) == "A"
    assert score_to_rating(85) == "A-"
    assert score_to_rating(75) == "B"
    assert score_to_rating(60) == "Watch"
    assert score_to_rating(10) == "Reject"


def test_score_to_state_hard_rejected_overrides_score():
    assert score_to_state(95, "allowed", hard_rejected=True) == "REJECTED"


def test_score_to_state_restrictive_gate_caps_at_manual_review_only():
    assert score_to_state(90, "restrictive", hard_rejected=False) == "MANUAL_REVIEW_ONLY"


# ── detect_hammer_profile / detect_pullback_profile ───────────────────────

def test_detect_hammer_profile_identifies_long_lower_wick_and_strong_close():
    bars = _build_hammer_scenario()
    cfg = ScreenerConfig()
    hammer = detect_hammer_profile(bars, cfg)
    assert hammer.lower_wick_pct_of_range > 25  # real intraday dip-and-reclaim wick
    assert hammer.close_location_pct > 60
    assert hammer.green_close is True


def test_detect_pullback_profile_finds_undercut_reclaim():
    bars = _build_hammer_scenario()
    cfg = ScreenerConfig()
    pullback = detect_pullback_profile(bars, cfg)
    assert pullback.undercut_reclaim is True
    assert pullback.pullback_pct_from_high < 0


# ── analyze_symbol (end-to-end) ─────────────────────────────────────────────

def test_analyze_symbol_full_pipeline_on_textbook_setup():
    bars = _build_hammer_scenario()
    cfg = ScreenerConfig(min_price=1.0, min_volume=1, min_avg_dollar_volume=1, min_market_cap=0)
    result = analyze_symbol("TEST", bars, cfg)
    assert result["symbol"] == "TEST"
    assert "setup_score" in result
    assert result["state"] in ("ACTIONABLE_CLOSE_BUY", "MANUAL_REVIEW", "WATCH_TOMORROW", "REJECTED", "MANUAL_REVIEW_ONLY")
    assert "components" in result
    assert sum(result["components"].values()) == result["raw_setup_score"]


def test_analyze_symbol_insufficient_history_rejects_cleanly():
    bars = [_bar(f"d{i}", 100, 101, 99, 100) for i in range(10)]
    cfg = ScreenerConfig()
    result = analyze_symbol("TEST", bars, cfg)
    assert result["state"] == "REJECTED"
    assert result["reject_reasons"] == ["insufficient_history"]


def test_analyze_symbol_below_min_price_is_rejected():
    import datetime as dt
    d0 = dt.date(2026, 1, 1)
    bars = list(reversed([_bar((d0 + dt.timedelta(days=i)).isoformat(), 5, 5.1, 4.9, 5) for i in range(50)]))
    cfg = ScreenerConfig(min_price=20.0)
    result = analyze_symbol("TEST", bars, cfg)
    assert "below_min_price" in result["reject_reasons"]
    assert result["state"] == "REJECTED"
