"""
Tests for core/stockbee_momentum_burst_screener.py -- ported Stockbee
Momentum Burst detection. Synthetic data only, no network. All Bar lists
are MOST-RECENT-FIRST.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from stockbee_momentum_burst_screener import (
    Bar,
    ScreenerConfig,
    analyze_symbol,
    close_location_pct,
    detect_triggers,
    has_recent_breakdown,
    market_gate_score,
    risk_distance_score,
    score_to_rating,
    score_to_state,
    up_streak_before_trigger,
)


def _bar(date_str, open_, high, low, close, volume=1_000_000):
    return Bar(date=date_str, open=open_, high=high, low=low, close=close, volume=volume)


def _build_breakout_scenario():
    """A tight 10-day base around $50, then a 6% breakout day on 3x volume
    -- a textbook 4%-breakout momentum-burst setup. MRF (bars[0]=latest)."""
    import datetime as dt
    d0 = dt.date(2026, 1, 1)
    chrono = []

    # Older filler (for the 20-day volume baseline + base-width calc).
    for i in range(20):
        chrono.append(_bar((d0 + dt.timedelta(days=i)).isoformat(), 50.0, 50.5, 49.5, 50.0, 500_000))

    # Tight 10-day base, ~3% width.
    for i in range(20, 30):
        chrono.append(_bar((d0 + dt.timedelta(days=i)).isoformat(), 50.0, 50.8, 49.6, 50.2, 400_000))

    # Breakout day: +6% close, high volume, closes near the high.
    base_close = chrono[-1].close
    breakout_close = base_close * 1.06
    chrono.append(_bar((d0 + dt.timedelta(days=30)).isoformat(), base_close * 1.001, breakout_close * 1.005, base_close * 0.995, breakout_close, 1_800_000))

    return list(reversed(chrono))


# ── pure helpers ──────────────────────────────────────────────────────────

def test_close_location_pct_at_low_is_zero():
    bar = _bar("d", 15, 20, 10, 10)
    assert close_location_pct(bar) == 0.0


def test_up_streak_before_trigger_counts_consecutive_up_closes():
    bars = [_bar("d0", 0, 0, 0, 110), _bar("d1", 0, 0, 0, 109), _bar("d2", 0, 0, 0, 108), _bar("d3", 0, 0, 0, 107), _bar("d4", 0, 0, 0, 110)]
    assert up_streak_before_trigger(bars, max_days=5) == 2


def test_has_recent_breakdown_detects_sharp_decline():
    bars = [_bar("d0", 0, 0, 0, 100), _bar("d1", 0, 0, 0, 90), _bar("d2", 0, 0, 0, 95)]
    assert has_recent_breakdown(bars, lookback_days=5, threshold_pct=-4.0) is True


def test_risk_distance_score_bands():
    assert risk_distance_score(1.0) == 15
    assert risk_distance_score(20.0) == 0


def test_market_gate_score_mapping():
    assert market_gate_score("allowed") == 5
    assert market_gate_score("restrictive") == 0


def test_score_to_rating_and_state():
    assert score_to_rating(95) == "A"
    assert score_to_state(85, "allowed", hard_rejected=False) == "ACTIONABLE_DAY1"
    assert score_to_state(85, "anything", hard_rejected=True) == "REJECTED"


# ── detect_triggers ────────────────────────────────────────────────────────

def test_detect_triggers_identifies_4pct_breakout():
    bars = _build_breakout_scenario()
    cfg = ScreenerConfig()
    profile = detect_triggers(bars, cfg)
    assert "4pct_breakout" in profile.trigger_tags
    assert profile.day_gain_pct > 4.0


# ── analyze_symbol (end-to-end) ─────────────────────────────────────────────

def test_analyze_symbol_full_pipeline_on_textbook_breakout():
    bars = _build_breakout_scenario()
    cfg = ScreenerConfig(min_price=1.0, min_volume=1)
    result = analyze_symbol("TEST", bars, cfg)
    assert result["symbol"] == "TEST"
    assert "4pct_breakout" in result["trigger_tags"]
    assert sum(result["components"].values()) == result["raw_setup_score"]
    assert result["state"] in ("ACTIONABLE_DAY1", "MANUAL_REVIEW", "WATCH_ONLY", "REJECTED", "MANUAL_REVIEW_ONLY")


def test_analyze_symbol_insufficient_history_rejects_cleanly():
    bars = [_bar(f"d{i}", 100, 101, 99, 100) for i in range(10)]
    cfg = ScreenerConfig()
    result = analyze_symbol("TEST", bars, cfg)
    assert result["state"] == "REJECTED"
    assert result["reject_reasons"] == ["insufficient_history"]


def test_analyze_symbol_no_trigger_is_rejected():
    import datetime as dt
    d0 = dt.date(2026, 1, 1)
    flat = list(reversed([_bar((d0 + dt.timedelta(days=i)).isoformat(), 50, 50.2, 49.8, 50, 500_000) for i in range(30)]))
    cfg = ScreenerConfig()
    result = analyze_symbol("TEST", flat, cfg)
    assert "no_momentum_burst_trigger" in result["reject_reasons"]
    assert result["state"] == "REJECTED"
