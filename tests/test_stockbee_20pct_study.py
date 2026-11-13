"""
Tests for core/stockbee_20pct_study.py -- ported 20%-move detection/
classification/scoring. Synthetic data only, no network. Bars are
CHRONOLOGICAL (oldest first), matching historical_price_service's own
native order.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from stockbee_20pct_study import (
    Bar,
    classify_chart_pattern,
    classify_close_quality,
    classify_extension_risk,
    close_location_pct,
    detect_twenty_pct_event,
    pct_change,
)


def _bar(date_str, open_, high, low, close, volume=10_000_000):
    return Bar(date=date_str, open=open_, high=high, low=low, close=close, volume=volume)


def _flat_history(n, price=50.0, start="2026-01-01"):
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    return [_bar((d0 + dt.timedelta(days=i)).isoformat(), price, price * 1.01, price * 0.99, price) for i in range(n)]


# ── pure helpers ──────────────────────────────────────────────────────────

def test_pct_change_basic():
    assert abs(pct_change(120, 100) - 20.0) < 1e-9


def test_close_location_pct_near_high():
    bar = _bar("d", 10, 20, 10, 19)
    assert close_location_pct(bar) == 90.0


def test_classify_close_quality_up_strong():
    assert classify_close_quality(85, "UP") == "STRONG_CLOSE"
    assert classify_close_quality(30, "UP") == "WEAK_CLOSE"


def test_classify_extension_risk_bands():
    assert classify_extension_risk(70, 60, 40) == "HIGH"
    assert classify_extension_risk(10, 10, 80) == "LOW"


def test_classify_chart_pattern_gap_and_go():
    pattern = classify_chart_pattern(direction="UP", close_location=80, gap_pct=10, range_pct=15, return_pct=25,
                                       distance_to_52w_high_pct=-2, volume_ratio_20=3.0, prior_20d_return_pct=5)
    assert pattern == "GAP_AND_GO"


def test_classify_chart_pattern_breakdown_down():
    pattern = classify_chart_pattern(direction="DOWN", close_location=20, gap_pct=-5, range_pct=15, return_pct=-40,
                                       distance_to_52w_high_pct=-30, volume_ratio_20=2.0, prior_20d_return_pct=0)
    assert pattern == "STRUCTURAL_BREAKDOWN"


# ── detect_twenty_pct_event (end-to-end) ──────────────────────────────────

def test_detect_twenty_pct_event_finds_a_real_up_move():
    import datetime as dt
    base = _flat_history(280, price=50.0)
    # Final bar is a +25% move over the trailing 5 days on strong volume, near 52wk high.
    last_date = dt.date.fromisoformat(base[-1].date) + dt.timedelta(days=1)
    event_bar = _bar(last_date.isoformat(), 55.0, 63.0, 54.5, 62.5, volume=50_000_000)
    bars = base + [event_bar]

    result = detect_twenty_pct_event(bars, as_of=bars[-1].date)
    assert result is not None
    assert result["direction"] == "UP"
    assert result["price_snapshot"]["return_pct"] >= 20.0
    assert result["scores"]["continuation_quality_score"] >= 0


def test_detect_twenty_pct_event_no_event_returns_none():
    bars = _flat_history(50, price=50.0)
    result = detect_twenty_pct_event(bars, as_of=bars[-1].date)
    assert result is None


def test_detect_twenty_pct_event_filtered_by_min_price():
    import datetime as dt
    chrono = _flat_history(20, price=2.0)
    last_date = dt.date.fromisoformat(chrono[-1].date) + dt.timedelta(days=1)
    event_bar = _bar(last_date.isoformat(), 2.2, 2.6, 2.1, 2.5, volume=50_000_000)  # +25% but price < $5 min
    bars = chrono + [event_bar]
    result = detect_twenty_pct_event(bars, as_of=bars[-1].date, min_price=5.0)
    assert result is None


def test_detect_twenty_pct_event_insufficient_lookback_returns_none():
    bars = _flat_history(3, price=50.0)
    result = detect_twenty_pct_event(bars, as_of=bars[-1].date, lookback_days=5)
    assert result is None


def test_detect_twenty_pct_event_down_move_detected_when_included():
    import datetime as dt
    chrono = _flat_history(280, price=100.0)
    last_date = dt.date.fromisoformat(chrono[-1].date) + dt.timedelta(days=1)
    event_bar = _bar(last_date.isoformat(), 95.0, 96.0, 74.0, 75.0, volume=50_000_000)  # -25% breakdown
    bars = chrono + [event_bar]
    result = detect_twenty_pct_event(bars, as_of=bars[-1].date, include_down_movers=True)
    assert result is not None
    assert result["direction"] == "DOWN"


def test_detect_twenty_pct_event_down_move_excluded_when_disabled():
    import datetime as dt
    chrono = _flat_history(280, price=100.0)
    last_date = dt.date.fromisoformat(chrono[-1].date) + dt.timedelta(days=1)
    event_bar = _bar(last_date.isoformat(), 95.0, 96.0, 74.0, 75.0, volume=50_000_000)
    bars = chrono + [event_bar]
    result = detect_twenty_pct_event(bars, as_of=bars[-1].date, include_down_movers=False)
    assert result is None
