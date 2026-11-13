"""
Tests for core/contrarian_confirmation.py -- pure calculation, synthetic
weekly OHLC series hand-built to exercise each signal check per
references/contrarian-confirmation-checklist.md's own worked examples.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import pytest

from contrarian_confirmation import run_contrarian_confirmation


def _week(n, high=100.0, low=90.0, close=95.0):
    return {"week_of": f"W{n:03d}", "open": close, "high": high, "low": low, "close": close}


def _flat_weeks(n):
    return [_week(i) for i in range(n)]


def test_invalid_direction_raises():
    with pytest.raises(ValueError, match="direction must be"):
        run_contrarian_confirmation(_flat_weeks(30), direction="LONG")


def test_insufficient_weekly_bars():
    result = run_contrarian_confirmation(_flat_weeks(10), direction="CROWDED_LONG")
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["verdict_reason"] == "insufficient_weekly_bars"
    assert result["checks"] is None
    assert result["swing_levels"] is None


def test_no_reversal_evidence_on_flat_history():
    result = run_contrarian_confirmation(_flat_weeks(30), direction="CROWDED_LONG")
    assert result["verdict"] == "NOT_CONFIRMED"
    assert result["verdict_reason"] == "no_reversal_evidence"


def test_weekly_key_reversal_confirmed_medium():
    # Asymmetric history isolates key_reversal from failed_extreme: an older,
    # higher high (weeks 0-15, outside the 13-week swing lookback) means
    # week29's new 13-week high (105) is NOT also a new 29-week high (120),
    # so failed_extreme's broader-window condition never fires.
    bars = (
        [_week(i, high=120.0) for i in range(16)]
        + [_week(i) for i in range(16, 29)]
        + [_week(29, high=105.0, low=84.0, close=85.0)]
    )
    result = run_contrarian_confirmation(bars, direction="CROWDED_LONG")
    assert result["verdict"] == "CONFIRMED"
    assert result["verdict_reason"] == "key_reversal"
    assert result["confidence"] == "MEDIUM"
    assert result["checks"]["weekly_key_reversal"]["triggered"] is True
    assert result["checks"]["failed_extreme"]["triggered"] is False


def test_weekly_key_reversal_and_failed_extreme_cotrigger_gives_high_confidence():
    # Flat baseline: the same anomalous week pierces both the (smaller)
    # swing-lookback window and the (larger, but here equal) extreme-
    # lookback window, so both checks legitimately fire together ->
    # 2 distinct signal types -> HIGH confidence per the Confidence rule.
    bars = _flat_weeks(29) + [_week(29, high=110.0, low=84.0, close=85.0)]
    result = run_contrarian_confirmation(bars, direction="CROWDED_LONG")
    assert result["verdict"] == "CONFIRMED"
    assert result["confidence"] == "HIGH"
    assert result["checks"]["weekly_key_reversal"]["triggered"] is True
    assert result["checks"]["failed_extreme"]["triggered"] is True


def test_continuation_veto_overrides_key_reversal():
    bars = _flat_weeks(29) + [_week(29, high=110.0, low=84.0, close=85.0), _week(30, high=125.0, low=119.0, close=120.0)]
    result = run_contrarian_confirmation(bars, direction="CROWDED_LONG")
    assert result["verdict"] == "NOT_CONFIRMED"
    assert result["verdict_reason"] == "continuation_intact"


def test_failed_extreme_confirmed():
    bars = _flat_weeks(28) + [_week(28, high=105.0, low=90.0, close=95.0), _week(29)]
    result = run_contrarian_confirmation(bars, direction="CROWDED_LONG")
    assert result["verdict"] == "CONFIRMED"
    assert result["verdict_reason"] == "failed_extreme"
    assert result["checks"]["failed_extreme"]["attempted_level"] == 100.0


def test_failed_breakout_confirmed_no_later_bars():
    bars = (
        _flat_weeks(25)
        + [_week(25, high=112.0, low=108.0, close=110.0)]   # breakout week
        + [_week(26, high=125.0, low=115.0, close=120.0)]    # still above, not yet a failure
        + [_week(27, high=97.0, low=93.0, close=95.0)]        # failure week (closes back below 100)
        + [_week(28), _week(29)]
    )
    result = run_contrarian_confirmation(bars, direction="CROWDED_LONG")
    assert result["verdict"] == "CONFIRMED"
    assert result["verdict_reason"] == "failed_breakout"
    assert result["checks"]["failed_breakout"]["week_of"] == "W027"


def test_failed_breakout_vetoed_by_new_closing_high_at_w_plus_3():
    bars = (
        _flat_weeks(25)
        + [_week(25, high=112.0, low=108.0, close=110.0)]
        + [_week(26, high=125.0, low=115.0, close=120.0)]
        + [_week(27, high=97.0, low=93.0, close=95.0)]
        + [_week(28, high=123.0, low=119.0, close=122.0)]   # new CLOSING high (>120) but not a new
                                                               # HIGH-based breakout (<125) -> pure veto trigger
        + [_week(29)]
    )
    result = run_contrarian_confirmation(bars, direction="CROWDED_LONG")
    assert result["verdict"] == "NOT_CONFIRMED"
    assert result["verdict_reason"] == "continuation_intact"


def test_crowded_short_mirrors_key_reversal():
    # Mirror of the LONG key-reversal case, isolated the same way: an older,
    # deeper low (weeks 0-15) keeps week29's new 13-week low (85) from also
    # being a new 29-week low (80), so failed_extreme's mirrored condition
    # never fires. week29: new 13-week LOW, close (105) above prior week's HIGH (100).
    bars = (
        [_week(i, low=80.0) for i in range(16)]
        + [_week(i) for i in range(16, 29)]
        + [_week(29, high=106.0, low=85.0, close=105.0)]
    )
    result = run_contrarian_confirmation(bars, direction="CROWDED_SHORT")
    assert result["verdict"] == "CONFIRMED"
    assert result["verdict_reason"] == "key_reversal"
    assert result["confidence"] == "MEDIUM"


def test_stop_reference_direction_for_crowded_long_uses_swing_high():
    bars = _flat_weeks(29) + [_week(29, high=110.0, low=84.0, close=85.0)]
    result = run_contrarian_confirmation(bars, direction="CROWDED_LONG")
    swing = result["swing_levels"]
    assert swing["stop_reference"] == swing["nearest_swing_high"]["price"]


def test_stop_reference_direction_for_crowded_short_uses_swing_low():
    bars = _flat_weeks(29) + [{"week_of": "W029", "open": 96.0, "high": 96.0, "low": 80.0, "close": 96.0}]
    result = run_contrarian_confirmation(bars, direction="CROWDED_SHORT")
    swing = result["swing_levels"]
    assert swing["stop_reference"] == swing["nearest_swing_low"]["price"]
