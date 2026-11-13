"""Tests for core/day_by_day_path_predictor.py -- the real, disclosed
sqrt-of-time interpolation between a known origin price and the real
AI-predicted terminal return/range."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from day_by_day_path_predictor import predict_daily_path, best_entry_exit_days


def test_predict_daily_path_invalid_inputs():
    assert predict_daily_path(0, 5.0, 7)["path"] == []
    assert predict_daily_path(100, 5.0, 0)["path"] == []
    assert predict_daily_path(None, 5.0, 7)["path"] == []


def test_predict_daily_path_length_matches_horizon():
    out = predict_daily_path(100.0, 10.0, 7)
    assert len(out["path"]) == 7
    assert [p["day_offset"] for p in out["path"]] == [1, 2, 3, 4, 5, 6, 7]


def test_predict_daily_path_terminal_day_matches_predicted_return_exactly():
    """day_offset == horizon_days must reproduce predicted_return_pct exactly
    -- this is the real, AI-predicted number; the interpolation must not
    drift from it at the terminal point."""
    out = predict_daily_path(100.0, -8.49, 7)
    terminal = out["path"][-1]
    assert terminal["day_offset"] == 7
    assert abs(terminal["predicted_return_pct"] - (-8.49)) < 1e-6
    assert abs(terminal["predicted_price"] - 100.0 * (1 - 0.0849)) < 1e-4


def test_predict_daily_path_monotonic_for_steady_trend():
    """A positive terminal return should produce a monotonically increasing
    central price path (sqrt-time scaling of a single-signed move)."""
    out = predict_daily_path(100.0, 10.0, 10)
    prices = [p["predicted_price"] for p in out["path"]]
    assert prices == sorted(prices)


def test_predict_daily_path_band_widens_with_day():
    """The low/high band must widen as day_offset increases (ATR x sqrt(day))."""
    out = predict_daily_path(100.0, 5.0, 10, atr_daily_pct=2.0)
    widths = [p["predicted_high_price"] - p["predicted_low_price"] for p in out["path"]]
    assert widths == sorted(widths)


def test_predict_daily_path_no_atr_gives_no_band():
    out = predict_daily_path(100.0, 5.0, 5, atr_daily_pct=None)
    assert all(p["predicted_low_price"] is None and p["predicted_high_price"] is None for p in out["path"])


def test_predict_daily_path_includes_methodology_note():
    out = predict_daily_path(100.0, 5.0, 5)
    assert "interpolat" in out["methodology_note"].lower()


def test_best_entry_exit_days_bullish():
    path = [
        {"day_offset": 1, "predicted_price": 100.0},
        {"day_offset": 2, "predicted_price": 95.0},
        {"day_offset": 3, "predicted_price": 110.0},
        {"day_offset": 4, "predicted_price": 105.0},
    ]
    out = best_entry_exit_days(path, bullish=True)
    assert out["entry_day"] == 2  # lowest price
    assert out["exit_day"] == 3   # highest price AFTER entry


def test_best_entry_exit_days_bearish():
    path = [
        {"day_offset": 1, "predicted_price": 100.0},
        {"day_offset": 2, "predicted_price": 110.0},
        {"day_offset": 3, "predicted_price": 90.0},
    ]
    out = best_entry_exit_days(path, bullish=False)
    assert out["entry_day"] == 2  # highest price (short entry)
    assert out["exit_day"] == 3   # lowest price after


def test_best_entry_exit_days_empty_path():
    out = best_entry_exit_days([])
    assert out["entry_day"] is None


def test_best_entry_exit_days_no_day_after_entry():
    """If the highest/lowest price IS the last day, there's no later day to exit on."""
    path = [
        {"day_offset": 1, "predicted_price": 100.0},
        {"day_offset": 2, "predicted_price": 50.0},  # lowest, and also last
    ]
    out = best_entry_exit_days(path, bullish=True)
    assert out["entry_day"] == 2
    assert out["exit_day"] is None
    assert out["note"]
