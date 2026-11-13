"""
Tests for core/earnings_trade_analyzer.py -- ported 5-factor post-earnings
reaction scoring. Synthetic data only, no network. All daily price lists
are MOST-RECENT-FIRST.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from earnings_trade_analyzer import (
    analyze_stock,
    calculate_composite_score,
    calculate_gap,
    calculate_ma50_position,
    calculate_ma200_position,
    calculate_pre_earnings_trend,
    calculate_volume_trend,
)


def _bar(date_str, open_=100.0, close=100.0, volume=1_000_000):
    return {"date": date_str, "open": open_, "close": close, "volume": volume}


def _dates_desc(n, end="2026-08-20"):
    import datetime as dt
    d = dt.date.fromisoformat(end)
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= dt.timedelta(days=1)
    return out


# ── calculate_gap ──────────────────────────────────────────────────────────

def test_calculate_gap_amc_unknown_uses_next_day_open():
    daily_mrf = [
        _bar("2026-08-20", open_=110.0, close=110.0),  # next day (most recent)
        _bar("2026-08-19", open_=100.0, close=100.0),  # earnings date
        _bar("2026-08-18", open_=98.0, close=99.0),
    ]
    result = calculate_gap(daily_mrf, earnings_date="2026-08-19", timing="unknown")
    assert result["gap_pct"] == round((110 / 100 - 1) * 100, 2)
    assert result["gap_type"] == "up"
    assert "timing_note" in result


def test_calculate_gap_bmo_uses_prev_close():
    daily_mrf = [
        _bar("2026-08-19", open_=108.0, close=108.0),  # earnings date
        _bar("2026-08-18", open_=98.0, close=100.0),    # prev close = 100
    ]
    result = calculate_gap(daily_mrf, earnings_date="2026-08-19", timing="bmo")
    assert result["gap_pct"] == round((108 / 100 - 1) * 100, 2)
    assert "timing_note" not in result


def test_calculate_gap_scoring_bands():
    # BMO: earnings bar at index 1, prior-day close (index 2) is the base.
    big_gap = [_bar("d2", 111, 111), _bar("d1", 111, 111), _bar("d0", 100, 100)]
    assert calculate_gap(big_gap, "d1", "bmo")["score"] == 100.0
    small_gap = [_bar("d2", 100.5, 100.5), _bar("d1", 100.5, 100.5), _bar("d0", 100, 100)]
    assert calculate_gap(small_gap, "d1", "bmo")["score"] == 15.0


def test_calculate_gap_date_not_found():
    result = calculate_gap([_bar("2026-08-19")], "2099-01-01", "unknown")
    assert result["score"] == 0.0
    assert "warning" in result


# ── calculate_pre_earnings_trend ───────────────────────────────────────────

def test_pre_earnings_trend_strong_uptrend_scores_100():
    dates = _dates_desc(25)
    # daily_prices[0]=most recent, earnings at index 4; 20 days before = index 24
    daily_mrf = [_bar(d, close=100.0 + (24 - i) * 1.0) for i, d in enumerate(dates)]
    earnings_date = dates[4]
    result = calculate_pre_earnings_trend(daily_mrf, earnings_date)
    assert result["trend_direction"] == "up"
    assert result["score"] == 100.0


def test_pre_earnings_trend_insufficient_data():
    daily_mrf = [_bar(d) for d in _dates_desc(10)]
    result = calculate_pre_earnings_trend(daily_mrf, daily_mrf[0]["date"])
    assert result["score"] == 0.0
    assert "warning" in result


# ── calculate_volume_trend ─────────────────────────────────────────────────

def test_volume_trend_elevated_recent_volume_scores_high():
    dates = _dates_desc(65)
    daily_mrf = []
    for i, d in enumerate(dates):
        vol = 3_000_000 if i < 20 else 1_000_000  # recent 20 bars elevated vs older 60
        daily_mrf.append(_bar(d, volume=vol))
    result = calculate_volume_trend(daily_mrf, dates[0])
    assert result["vol_ratio_20_60"] > 1.0
    assert result["score"] >= 60.0


def test_volume_trend_insufficient_data():
    daily_mrf = [_bar(d) for d in _dates_desc(10)]
    result = calculate_volume_trend(daily_mrf, daily_mrf[0]["date"])
    assert result["score"] == 0.0


# ── calculate_ma200_position / calculate_ma50_position ────────────────────

def test_ma200_position_above_ma_scores_well():
    daily_mrf = [_bar(d, close=150.0 if i == 0 else 100.0) for i, d in enumerate(_dates_desc(200))]
    result = calculate_ma200_position(daily_mrf)
    assert result["above_ma200"] is True
    assert result["score"] == 100.0


def test_ma200_position_insufficient_data():
    daily_mrf = [_bar(d) for d in _dates_desc(50)]
    result = calculate_ma200_position(daily_mrf)
    assert result["score"] == 0.0
    assert "warning" in result


def test_ma50_position_below_ma_scores_poorly():
    daily_mrf = [_bar(d, close=80.0 if i == 0 else 100.0) for i, d in enumerate(_dates_desc(50))]
    result = calculate_ma50_position(daily_mrf)
    assert result["above_ma50"] is False
    assert result["score"] == 15.0


# ── calculate_composite_score ─────────────────────────────────────────────

def test_composite_score_all_max_is_grade_a():
    result = calculate_composite_score(100, 100, 100, 100, 100)
    assert result["composite_score"] == 100.0
    assert result["grade"] == "A"


def test_composite_score_weighting_matches_spec():
    # gap=25%, trend=30%, volume=20%, ma200=15%, ma50=10%
    result = calculate_composite_score(gap_score=100, trend_score=0, volume_score=0, ma200_score=0, ma50_score=0)
    assert result["composite_score"] == 25.0
    assert result["grade"] == "D"


# ── analyze_stock (end-to-end) ──────────────────────────────────────────────

def test_analyze_stock_full_pipeline():
    dates = _dates_desc(210)
    daily_mrf = [_bar(d, open_=100.0, close=100.0, volume=1_000_000) for d in dates]
    earnings_date = dates[0]
    result = analyze_stock(daily_mrf, earnings_date, timing="unknown")
    assert "composite" in result
    assert result["composite"]["grade"] in ("A", "B", "C", "D")
    assert "gap" in result and "pre_earnings_trend" in result and "volume_trend" in result
