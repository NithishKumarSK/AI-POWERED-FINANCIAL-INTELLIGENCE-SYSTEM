"""
Tests for core/parabolic_short_screener.py -- pure calculation, synthetic
OHLCV series only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from parabolic_short_screener import (
    calculate_acceleration,
    calculate_liquidity,
    calculate_ma_extension,
    calculate_range_expansion,
    calculate_volume_climax,
    check_hard_invalidations,
    check_state_cap,
    grade_from_score,
    screen_symbol,
)


def _parabolic_closes(n=60, base=10.0):
    """Flat for a while, then a sharp 5-day parabolic ramp at the end."""
    closes = [base] * (n - 5)
    last = base
    for _ in range(5):
        last *= 1.15
        closes.append(last)
    return closes


def test_calculate_ma_extension_insufficient_history():
    result = calculate_ma_extension([10.0] * 10)
    assert result["qualifies"] is False


def test_calculate_ma_extension_qualifies_on_strong_extension():
    closes = _parabolic_closes()
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.97 for c in closes]
    result = calculate_ma_extension(closes, highs, lows)
    assert result["pct_above_sma20"] > 25


def test_calculate_acceleration_requires_three_green_days():
    closes = [10.0] * 10 + [9.5, 9.0, 10.0, 10.5, 11.0]
    result = calculate_acceleration(closes)
    assert result["consecutive_green_days"] == 3


def test_calculate_volume_climax_qualifies_on_spike():
    volumes = [1_000_000] * 19 + [2_000_000]
    result = calculate_volume_climax(volumes)
    assert result["qualifies"] is True
    assert result["volume_ratio"] >= 1.5


def test_calculate_volume_climax_insufficient_history():
    assert calculate_volume_climax([1_000_000] * 5)["qualifies"] is False


def test_calculate_range_expansion_qualifies_on_wide_bar():
    highs = [10.5] * 21
    lows = [9.5] * 21
    closes = [10.0] * 21
    highs[-1] = 13.0
    lows[-1] = 9.0
    result = calculate_range_expansion(highs, lows, closes)
    assert result["qualifies"] is True


def test_calculate_liquidity_safe_largecap_floor():
    closes = [100.0] * 20
    volumes = [250_000] * 20  # $25M/day, above $20M floor
    result = calculate_liquidity(closes, volumes, mode="safe_largecap")
    assert result["qualifies"] is True


def test_calculate_liquidity_fails_below_floor():
    closes = [10.0] * 20
    volumes = [100_000] * 20  # $1M/day, below both floors
    result = calculate_liquidity(closes, volumes, mode="classic_qm")
    assert result["qualifies"] is False


def test_check_hard_invalidations_rejects_sub_5_dollar():
    rejected, reasons = check_hard_invalidations(
        five_day_return_pct=40, latest_close=3.0, market_cap=5_000_000_000,
        days_since_ipo_trading=500, earnings_within_days_forward=None,
        exclude_earnings_within_days=2, mode="safe_largecap",
    )
    assert rejected is True
    assert any("below $5.00" in r for r in reasons)


def test_check_hard_invalidations_rejects_earnings_blackout():
    rejected, reasons = check_hard_invalidations(
        five_day_return_pct=40, latest_close=50.0, market_cap=5_000_000_000,
        days_since_ipo_trading=500, earnings_within_days_forward=1,
        exclude_earnings_within_days=2, mode="safe_largecap",
    )
    assert rejected is True
    assert any("Earnings in" in r for r in reasons)


def test_check_hard_invalidations_passes_clean_candidate():
    rejected, reasons = check_hard_invalidations(
        five_day_return_pct=40, latest_close=50.0, market_cap=5_000_000_000,
        days_since_ipo_trading=500, earnings_within_days_forward=20,
        exclude_earnings_within_days=2, mode="safe_largecap",
    )
    assert rejected is False
    assert reasons == []


def test_grade_from_score_bands():
    assert grade_from_score(95) == "A"
    assert grade_from_score(80) == "B"
    assert grade_from_score(65) == "C"
    assert grade_from_score(40) == "D"


def test_check_state_cap_still_in_markup():
    cap = check_state_cap(latest_close=99.0, latest_high=100.0, latest_low=90.0, is_fresh_52w_high=True)
    assert cap == "still_in_markup"


def test_check_state_cap_none_when_not_fresh_high():
    assert check_state_cap(latest_close=99.0, latest_high=100.0, latest_low=90.0, is_fresh_52w_high=False) is None


def test_screen_symbol_returns_none_below_return_threshold():
    closes = [10.0] * 60
    result = screen_symbol("AAPL", closes, closes, closes, [1_000_000] * 60, 5_000_000_000, 500, 20)
    assert result is None


def test_screen_symbol_full_candidate_pipeline():
    closes = _parabolic_closes(n=280)
    highs = [c * 1.02 for c in closes]
    lows = [c * 0.97 for c in closes]
    volumes = [1_000_000] * (len(closes) - 1) + [2_500_000]
    result = screen_symbol("XYZ", closes, highs, lows, volumes, market_cap=5_000_000_000,
                             days_since_ipo_trading=500, earnings_within_days_forward=20)
    assert result is not None
    assert result["status"] == "CANDIDATE"
    assert result["grade"] in ("A", "B", "C", "D")


def test_screen_symbol_rejected_by_earnings_blackout():
    closes = _parabolic_closes(n=280)
    highs = [c * 1.02 for c in closes]
    lows = [c * 0.97 for c in closes]
    volumes = [1_000_000] * (len(closes) - 1) + [2_500_000]
    result = screen_symbol("XYZ", closes, highs, lows, volumes, market_cap=5_000_000_000,
                             days_since_ipo_trading=500, earnings_within_days_forward=1)
    assert result is not None
    assert result["status"] == "REJECTED"
