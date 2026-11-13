"""
Tests for core/pead_screener.py -- ported PEAD weekly-candle pattern
analysis. Synthetic data only, no network. All daily/weekly price lists
are MOST-RECENT-FIRST (same convention as core/ibd_distribution_day_monitor.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from pead_screener import (
    analyze_stock,
    analyze_weekly_pattern,
    calculate_breakout,
    calculate_composite_score,
    calculate_liquidity,
    calculate_price_gap,
    calculate_risk_reward,
    calculate_setup_quality,
    daily_to_weekly,
    find_red_candle,
)


def _daily_bar(date_str, open_, high, low, close, volume=5_000_000):
    return {"date": date_str, "open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _build_chrono_days(start, end, price_fn, volume=5_000_000):
    """Weekday-only chronological daily bars from start to end (inclusive)."""
    import datetime as dt
    out = []
    d = dt.date.fromisoformat(start)
    end_d = dt.date.fromisoformat(end)
    while d <= end_d:
        if d.weekday() < 5:  # Mon-Fri only
            p = price_fn(d)
            out.append(_daily_bar(d.isoformat(), p, p * 1.01, p * 0.99, p, volume))
        d += dt.timedelta(days=1)
    return out


# ── daily_to_weekly ───────────────────────────────────────────────────────

def test_daily_to_weekly_groups_by_iso_week_and_reverses_to_mrf():
    chrono = _build_chrono_days("2026-06-01", "2026-06-12", lambda d: 100.0)
    daily_mrf = list(reversed(chrono))
    weekly = daily_to_weekly(daily_mrf)
    assert len(weekly) >= 2
    assert weekly[0]["week_start"] > weekly[-1]["week_start"]  # most-recent-first


def test_daily_to_weekly_splits_earnings_week():
    # Week of 2026-06-01 (Mon) -- earnings mid-week on 2026-06-03 (Wed)
    chrono = _build_chrono_days("2026-06-01", "2026-06-05", lambda d: 100.0)
    daily_mrf = list(reversed(chrono))
    weekly = daily_to_weekly(daily_mrf, earnings_date="2026-06-03")
    earnings_week = [w for w in weekly if w["week_start"] == "2026-06-01"][0]
    assert earnings_week["trading_days"] == 3  # Wed, Thu, Fri only
    assert earnings_week["partial_week"] is True


# ── find_red_candle / analyze_weekly_pattern ─────────────────────────────

def _weekly_candle(week_start, open_, close, high=None, low=None, volume=1_000_000, year=2026, week=1):
    return {
        "week_start": week_start, "year": year, "week": week,
        "open": open_, "close": close,
        "high": high if high is not None else max(open_, close) * 1.02,
        "low": low if low is not None else min(open_, close) * 0.98,
        "volume": volume, "is_green": close >= open_, "partial_week": False, "trading_days": 5,
    }


def test_find_red_candle_finds_first_red_after_earnings_week():
    weekly = [
        _weekly_candle("2026-07-06", 110, 115, week=28),  # current, green
        _weekly_candle("2026-06-29", 100, 95, week=27),   # red -- should be found
        _weekly_candle("2026-06-22", 90, 92, week=26),    # earnings week (idx 2)
    ]
    red = find_red_candle(weekly, earnings_week_idx=2)
    assert red is not None
    assert red["week_index"] == 1


def test_analyze_weekly_pattern_detects_breakout():
    weekly = [
        _weekly_candle("2026-07-06", 96, 102, high=103, week=28),  # current, green, close > red high (100)
        _weekly_candle("2026-06-29", 100, 94, high=100, low=93, week=27),  # red candle, high=100
        _weekly_candle("2026-06-22", 90, 95, week=26, year=2026),
    ]
    pattern = analyze_weekly_pattern(weekly, earnings_date="2026-06-24", watch_weeks=5)
    assert pattern["red_candle"] is not None
    assert pattern["stage"] == "BREAKOUT"
    assert pattern["is_breakout"] is True


def test_analyze_weekly_pattern_expired_after_watch_window():
    weekly = [_weekly_candle("2026-09-01", 100, 101, week=36)]
    pattern = analyze_weekly_pattern(weekly, earnings_date="2026-06-01", watch_weeks=5)
    assert pattern["stage"] == "EXPIRED"


# ── calculate_price_gap ───────────────────────────────────────────────────

def test_calculate_price_gap_unknown_timing_uses_next_day_open():
    daily_mrf = [
        _daily_bar("2026-06-04", 110, 111, 109, 110),  # next day (most recent)
        _daily_bar("2026-06-03", 100, 101, 99, 100),    # earnings date
        _daily_bar("2026-06-02", 98, 99, 97, 99),
    ]
    gap = calculate_price_gap(daily_mrf, earnings_date="2026-06-03", timing="unknown")
    assert gap == round((110 / 100 - 1) * 100, 2)


def test_calculate_price_gap_bmo_uses_prev_close():
    daily_mrf = [
        _daily_bar("2026-06-03", 108, 109, 107, 108),  # earnings date (BMO gap up at open)
        _daily_bar("2026-06-02", 98, 99, 97, 100),      # prev close = 100
    ]
    gap = calculate_price_gap(daily_mrf, earnings_date="2026-06-03", timing="bmo")
    assert gap == round((108 / 100 - 1) * 100, 2)


def test_calculate_price_gap_unknown_date_returns_zero():
    daily_mrf = [_daily_bar("2026-06-03", 100, 101, 99, 100)]
    assert calculate_price_gap(daily_mrf, earnings_date="2099-01-01", timing="unknown") == 0.0


# ── calculate_setup_quality ────────────────────────────────────────────────

def test_setup_quality_breakout_and_big_gap_scores_high():
    score = calculate_setup_quality(gap_pct=10.0, pattern_result={"stage": "BREAKOUT", "weeks_since_earnings": 2, "red_candle": None})
    assert score == 100.0


def test_setup_quality_expired_scores_only_gap_component():
    score = calculate_setup_quality(gap_pct=3.0, pattern_result={"stage": "EXPIRED", "weeks_since_earnings": 6, "red_candle": None})
    assert score == 20.0


# ── calculate_breakout ────────────────────────────────────────────────────

def test_calculate_breakout_strong_with_volume_confirmation():
    red_candle = {"high": 100.0, "low": 95.0}
    weekly = [
        _weekly_candle("2026-07-06", 100, 104, volume=2_000_000),  # current: +4% above red high
        _weekly_candle("2026-06-29", 95, 97, volume=500_000),
        _weekly_candle("2026-06-22", 96, 95, volume=500_000),
    ]
    result = calculate_breakout(weekly, red_candle, current_price=104.0)
    assert result["is_breakout"] is True
    assert result["volume_confirmation"] is True
    assert result["score"] == 100.0


def test_calculate_breakout_no_breakout_below_red_high():
    red_candle = {"high": 100.0, "low": 95.0}
    result = calculate_breakout([_weekly_candle("2026-07-06", 90, 95)], red_candle, current_price=95.0)
    assert result["is_breakout"] is False
    assert result["score"] == 0.0


# ── calculate_liquidity ────────────────────────────────────────────────────

def test_liquidity_all_thresholds_pass_scores_high():
    daily = [_daily_bar(f"2026-06-{i:02d}", 50, 51, 49, 50, volume=5_000_000) for i in range(1, 21)]
    result = calculate_liquidity(daily, current_price=50.0)
    assert result["passes_all"] is True
    assert result["score"] == 100.0  # adv20 = 5M*50 = 250M > 100M


def test_liquidity_low_price_fails_one_threshold():
    daily = [_daily_bar(f"2026-06-{i:02d}", 5, 5.1, 4.9, 5, volume=5_000_000) for i in range(1, 21)]
    result = calculate_liquidity(daily, current_price=5.0)
    assert result["passes_all"] is False
    assert result["score"] == 40.0  # fails price>=10, passes adv20 and volume


# ── calculate_risk_reward ──────────────────────────────────────────────────

def test_risk_reward_high_ratio_scores_100():
    red_candle = {"low": 95.0}
    result = calculate_risk_reward(current_price=100.0, red_candle=red_candle, target_multiplier=2.0)
    # risk=5, reward=10, rr=2.0 -- wait target_multiplier affects reward not ratio
    assert result["risk_reward_ratio"] == 2.0
    assert result["score"] == 70.0


def test_risk_reward_stop_above_entry_returns_neutral():
    red_candle = {"low": 110.0}  # stop ABOVE current price -- invalid setup
    result = calculate_risk_reward(current_price=100.0, red_candle=red_candle)
    assert result["risk_reward_ratio"] == 0.0
    assert result["score"] == 25.0


# ── calculate_composite_score ─────────────────────────────────────────────

def test_composite_score_weighted_correctly():
    result = calculate_composite_score(setup_score=100, breakout_score=100, liquidity_score=100, rr_score=100)
    assert result["composite_score"] == 100.0
    assert result["rating"] == "Strong Setup"


def test_composite_score_identifies_weakest_and_strongest():
    result = calculate_composite_score(setup_score=90, breakout_score=10, liquidity_score=50, rr_score=50)
    assert result["weakest_component"] == "Breakout Strength"
    assert result["strongest_component"] == "Setup Quality"


# ── analyze_stock (end-to-end) ──────────────────────────────────────────────

def test_analyze_stock_full_pipeline_produces_a_rating():
    chrono = _build_chrono_days("2026-06-01", "2026-07-10", lambda d: 100.0 + (d.toordinal() % 5))
    daily_mrf = list(reversed(chrono))
    earnings_date = chrono[5]["date"]  # some date within the window

    result = analyze_stock(
        "TEST", daily_mrf, earnings_date=earnings_date, earnings_timing="unknown",
        gap_pct=5.0, current_price=daily_mrf[0]["close"], watch_weeks=5,
    )
    assert result is not None
    assert result["symbol"] == "TEST"
    assert "composite_score" in result
    assert result["rating"] in ("Strong Setup", "Good Setup", "Developing", "Weak")


def test_analyze_stock_insufficient_data_returns_none():
    result = analyze_stock("TEST", [_daily_bar("2026-06-01", 100, 101, 99, 100)], "2026-06-01", "unknown", 5.0, 100.0)
    assert result is None
