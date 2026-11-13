"""Tests for core/range_timing_predictor.py — the price-range + which-day
prediction and its backtest comparator."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import bootstrap_paths  # noqa: E402
bootstrap_paths.add_module_paths()

from range_timing_predictor import (  # noqa: E402
    predict_price_range_and_timing, evaluate_range_and_timing,
    predict_day_offset_knn, load_range_timing_training_set,
)


def _fp(origin_price=100.0, horizon_days=7, expected_range_pct=5.0,
        oversold=False, overbought=False, near_support=False, near_resistance=False,
        trend_regime="sideways", adx_regime="weak_trend"):
    return {
        "status": "OK",
        "origin_price": origin_price,
        "horizon_days": horizon_days,
        "return_magnitude_formula": {"expected_range_pct": expected_range_pct},
        "reversal_signals": {
            "oversold_signal": oversold, "overbought_signal": overbought,
            "near_support": near_support, "near_resistance": near_resistance,
        },
        "trend": {"trend_regime": trend_regime, "adx_regime": adx_regime},
    }


def test_insufficient_status_passthrough():
    assert predict_price_range_and_timing({"status": "INSUFFICIENT"})["status"] == "INSUFFICIENT"
    assert predict_price_range_and_timing({})["status"] == "INSUFFICIENT"


def test_range_symmetric_around_origin_price():
    r = predict_price_range_and_timing(_fp(origin_price=100.0, expected_range_pct=5.0))
    assert r["status"] == "OK"
    assert r["predicted_low_price"] == 95.0
    assert r["predicted_high_price"] == 105.0


def test_oversold_near_support_predicts_imminent_low():
    r = predict_price_range_and_timing(_fp(oversold=True, near_support=True, horizon_days=7))
    assert r["predicted_low_day_offset"] == 1


def test_overbought_near_resistance_predicts_imminent_high():
    r = predict_price_range_and_timing(_fp(overbought=True, near_resistance=True, horizon_days=7))
    assert r["predicted_high_day_offset"] == 1


def test_strong_bullish_trend_predicts_low_early_high_late():
    r = predict_price_range_and_timing(_fp(trend_regime="bullish", adx_regime="strong_trend", horizon_days=10))
    assert r["predicted_low_day_offset"] == 1
    assert r["predicted_high_day_offset"] == 10


def test_strong_bearish_trend_predicts_high_early_low_late():
    r = predict_price_range_and_timing(_fp(trend_regime="bearish", adx_regime="strong_trend", horizon_days=10))
    assert r["predicted_high_day_offset"] == 1
    assert r["predicted_low_day_offset"] == 10


def test_no_signal_defaults_to_midpoint():
    r = predict_price_range_and_timing(_fp(horizon_days=7))
    assert r["predicted_low_day_offset"] == 3
    assert r["predicted_high_day_offset"] == 3


def _bar(day_close, high=None, low=None):
    return {"close": day_close, "high": high if high is not None else day_close,
            "low": low if low is not None else day_close}


def test_evaluate_insufficient_without_predicted_or_bars():
    assert evaluate_range_and_timing(None, [_bar(100)])["status"] == "INSUFFICIENT"
    assert evaluate_range_and_timing({"status": "OK", "predicted_low_price": 1, "predicted_high_price": 2,
                                       "predicted_low_day_offset": 1, "predicted_high_day_offset": 1}, [])["status"] == "INSUFFICIENT"


def test_evaluate_finds_real_extreme_and_day():
    predicted = {
        "status": "OK", "predicted_low_price": 95.0, "predicted_high_price": 105.0,
        "predicted_low_day_offset": 1, "predicted_high_day_offset": 7,
    }
    # 7-day window: real low on day 2 (97), real high on day 6 (103)
    window = [_bar(100), _bar(97, high=98, low=97), _bar(99), _bar(101),
              _bar(102), _bar(103, high=103, low=102), _bar(101)]
    result = evaluate_range_and_timing(predicted, window)
    assert result["status"] == "OK"
    assert result["actual_low_day_offset"] == 2
    assert result["actual_low_price"] == 97
    assert result["actual_high_day_offset"] == 6
    assert result["actual_high_price"] == 103
    assert result["range_contains_actual"] is True  # 95<=97 and 103<=105
    assert result["low_day_error_days"] == 1   # predicted 1, actual 2
    assert result["low_day_within_1"] is True
    assert result["low_day_exact_match"] is False
    assert result["high_day_error_days"] == 1  # predicted 7, actual 6
    assert result["high_day_within_1"] is True


def test_range_does_not_contain_actual_when_price_breaks_out():
    predicted = {
        "status": "OK", "predicted_low_price": 95.0, "predicted_high_price": 105.0,
        "predicted_low_day_offset": 1, "predicted_high_day_offset": 3,
    }
    window = [_bar(100), _bar(100), _bar(110, high=112, low=100)]  # breaks above predicted high
    result = evaluate_range_and_timing(predicted, window)
    assert result["range_contains_actual"] is False
    assert result["high_price_error_pct"] < 0  # predicted below actual -> negative error


def test_exact_day_match():
    predicted = {
        "status": "OK", "predicted_low_price": 90.0, "predicted_high_price": 110.0,
        "predicted_low_day_offset": 2, "predicted_high_day_offset": 2,
    }
    window = [_bar(97), _bar(97, high=99, low=95)]
    result = evaluate_range_and_timing(predicted, window)
    assert result["low_day_exact_match"] is True
    assert result["high_day_exact_match"] is True


# ── predict_day_offset_knn ──────────────────────────────────────────────────

def _case(vec, low_day, high_day):
    return {"vec": vec, "actual_low_day": low_day, "actual_high_day": high_day}


def test_knn_insufficient_without_training_cases():
    assert predict_day_offset_knn([1.0, 2.0], [])["status"] == "INSUFFICIENT"


def test_knn_insufficient_without_query_vector():
    assert predict_day_offset_knn([], [_case([1.0], 1, 2)])["status"] == "INSUFFICIENT"


def test_knn_returns_median_of_nearest_neighbors():
    # Query vector [0, 0] -- two cases far away (should be excluded by k=2),
    # two cases close by with known day offsets.
    training = [
        _case([0.1, 0.1], low_day=2, high_day=5),
        _case([0.2, -0.1], low_day=3, high_day=6),
        _case([50.0, 50.0], low_day=7, high_day=1),   # far outlier -- must not be picked
        _case([-50.0, -50.0], low_day=1, high_day=7),  # far outlier -- must not be picked
    ]
    result = predict_day_offset_knn([0.0, 0.0], training, k=2)
    assert result["status"] == "OK"
    # median of the two nearest (2,5) and (3,6) -> low=2 or 3 depending on tie rule, high=5 or 6
    assert result["predicted_low_day_offset"] in (2, 3)
    assert result["predicted_high_day_offset"] in (5, 6)
    assert result["k_neighbors_used"] == 2


def test_knn_k_clamped_to_available_cases():
    training = [_case([0.0], 1, 1), _case([0.1], 2, 2)]
    result = predict_day_offset_knn([0.0], training, k=50)
    assert result["status"] == "OK"
    assert result["k_neighbors_used"] == 2


def test_knn_confidence_values_present_and_real():
    training = [_case([0.0], 1, 1), _case([0.1], 2, 2)]
    result = predict_day_offset_knn([0.0], training, k=2)
    assert 0 < result["low_day_within_1_confidence_pct"] < 100
    assert 0 < result["high_day_within_1_confidence_pct"] < 100


def test_load_training_set_returns_list_even_if_missing(monkeypatch, tmp_path):
    import range_timing_predictor as rtp
    monkeypatch.setattr(rtp, "_TRAINING_SET_CACHE", None)
    monkeypatch.setattr(rtp, "TRAINING_SET_PATH", tmp_path / "does_not_exist.json")
    assert load_range_timing_training_set() == []
