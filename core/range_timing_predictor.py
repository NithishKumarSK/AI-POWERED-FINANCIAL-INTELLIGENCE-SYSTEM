"""
range_timing_predictor.py — predicts a price RANGE (low/high) for the
prediction window, and separately, WHICH DAY within that window each extreme
is expected to occur.

These are deliberately two different predictions, scored and reported
separately, never blended into one confidence number:

  RANGE  — the expected low/high price band. Grounded in realized volatility
           (ATR, already computed in build_stock_feature_packet's
           return_magnitude_formula.expected_range_pct) — the same math
           options markets use for "expected move." A tractable problem.

  TIMING — which day within the window each extreme occurs. Derived from
           reversal signals (oversold/overbought, near support/resistance)
           and trend regime, already computed in the same feature packet.
           Genuinely harder than the range call (it compounds magnitude
           uncertainty with timing uncertainty) and UNPROVEN until
           backtested — see evaluate_range_and_timing below, and
           scripts/adhoc or scratchpad validation runs for the real,
           measured hit rate. Never assume this works; measure it.

Both functions are pure/deterministic (no Gemini call) so they can be
backtested at scale for free, same discipline as
_compute_technical_override_score's deterministic cross-check.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TRAINING_SET_PATH = ROOT / "data" / "range_timing_training_set.json"

# Real, measured confidence for the KNN day estimate below -- from a
# 1090-case walk-forward backtest (scripts/adhoc/build_range_timing_training_set.py
# + full leave-one-out KNN evaluation over every case, not a subsample), NOT a
# guess. Previous values (52.0% / 47.7%) were from a 383-case set; expanding
# training data ~2.8x genuinely improved the high-day estimate (47.7% ->
# 51.9%, confirmed on the full leave-one-out, not just a quick subsample) and
# left the low-day estimate about flat (52.0% -> 53.0%). Keep these in sync
# if the training set / K / horizon changes and the backtest is re-run -- a
# stale confidence number here would be exactly the kind of silent staleness
# bug this project has already found and fixed multiple times in the UI.
KNN_LOW_DAY_WITHIN_1_CONFIDENCE_PCT  = 53.0
KNN_HIGH_DAY_WITHIN_1_CONFIDENCE_PCT = 51.9
KNN_K = 9


def predict_price_range_and_timing(feature_packet: dict) -> dict:
    """Deterministic low/high price band + which-day-within-the-window each
    extreme is expected, from a feature packet already built by
    build_stock_feature_packet (same leakage-safe inputs as every other
    prediction path -- no new data source, no new leakage risk).

    Returns {"status": "INSUFFICIENT"} if the feature packet doesn't have
    what's needed (never raises -- this is enrichment, callers degrade
    gracefully same as every other optional signal in this project).
    """
    if not feature_packet or feature_packet.get("status") != "OK":
        return {"status": "INSUFFICIENT", "error": "feature_packet not OK"}

    origin_price = feature_packet.get("origin_price")
    horizon_days = int(feature_packet.get("horizon_days") or 7)
    rmf   = feature_packet.get("return_magnitude_formula", {}) or {}
    rev   = feature_packet.get("reversal_signals", {}) or {}
    trend = feature_packet.get("trend", {}) or {}

    half_range_pct = rmf.get("expected_range_pct")
    if not origin_price or half_range_pct is None:
        return {"status": "INSUFFICIENT", "error": "missing origin_price or expected_range_pct"}

    predicted_low_price  = round(origin_price * (1 - half_range_pct / 100.0), 4)
    predicted_high_price = round(origin_price * (1 + half_range_pct / 100.0), 4)

    oversold   = bool(rev.get("oversold_signal"))
    overbought = bool(rev.get("overbought_signal"))
    near_sup   = bool(rev.get("near_support"))
    near_res   = bool(rev.get("near_resistance"))
    trend_regime = trend.get("trend_regime")
    strong_trend = trend.get("adx_regime") == "strong_trend"

    midpoint = max(1, horizon_days // 2)

    if oversold or near_sup:
        low_day_offset = 1
        low_basis = "oversold/near_support -> imminent bounce expected"
    elif trend_regime == "bullish" and strong_trend:
        low_day_offset = 1
        low_basis = "strong uptrend -> low likely at window start"
    elif trend_regime == "bearish" and strong_trend:
        low_day_offset = horizon_days
        low_basis = "strong downtrend -> low likely late in window"
    else:
        low_day_offset = midpoint
        low_basis = "no strong directional/reversal signal -> midpoint default"

    if overbought or near_res:
        high_day_offset = 1
        high_basis = "overbought/near_resistance -> imminent pullback expected"
    elif trend_regime == "bullish" and strong_trend:
        high_day_offset = horizon_days
        high_basis = "strong uptrend -> high likely late in window"
    elif trend_regime == "bearish" and strong_trend:
        high_day_offset = 1
        high_basis = "strong downtrend -> high likely at window start"
    else:
        high_day_offset = midpoint
        high_basis = "no strong directional/reversal signal -> midpoint default"

    return {
        "status":                   "OK",
        "origin_price":             origin_price,
        "horizon_days":             horizon_days,
        "predicted_low_price":      predicted_low_price,
        "predicted_high_price":     predicted_high_price,
        "predicted_low_day_offset":  low_day_offset,
        "predicted_high_day_offset": high_day_offset,
        "range_basis": f"ATR-based expected move: +/-{half_range_pct}% over {horizon_days}d",
        "low_day_basis":  low_basis,
        "high_day_basis": high_basis,
    }


def evaluate_range_and_timing(predicted: dict, window_bars: List[dict]) -> dict:
    """Score a range+timing prediction against what REALLY happened.

    window_bars: the real bars strictly AFTER the prediction origin, covering
    exactly the horizon window (caller's responsibility -- same leakage
    contract as every other validator in this project: these bars must not
    have been visible to the predictor). bars[0] is day offset 1.

    Returns {"status": "INSUFFICIENT"} if there's nothing to score against.
    """
    if not predicted or predicted.get("status") != "OK" or not window_bars:
        return {"status": "INSUFFICIENT"}

    def _px(bar: dict, key: str) -> float:
        return float(bar.get(key) or bar.get("close") or 0)

    highs = [(i + 1, _px(b, "high")) for i, b in enumerate(window_bars) if _px(b, "high") > 0]
    lows  = [(i + 1, _px(b, "low"))  for i, b in enumerate(window_bars) if _px(b, "low")  > 0]
    if not highs or not lows:
        return {"status": "INSUFFICIENT"}

    actual_high_day, actual_high_price = max(highs, key=lambda t: t[1])
    actual_low_day,  actual_low_price  = min(lows,  key=lambda t: t[1])

    pred_low  = predicted["predicted_low_price"]
    pred_high = predicted["predicted_high_price"]

    range_contains_actual = (pred_low <= actual_low_price) and (actual_high_price <= pred_high)
    low_price_error_pct  = round((pred_low  - actual_low_price)  / actual_low_price  * 100.0, 2) if actual_low_price  else None
    high_price_error_pct = round((pred_high - actual_high_price) / actual_high_price * 100.0, 2) if actual_high_price else None

    low_day_error  = abs(predicted["predicted_low_day_offset"]  - actual_low_day)
    high_day_error = abs(predicted["predicted_high_day_offset"] - actual_high_day)

    return {
        "status": "OK",
        "actual_low_price":  actual_low_price,  "actual_low_day_offset":  actual_low_day,
        "actual_high_price": actual_high_price, "actual_high_day_offset": actual_high_day,
        "range_contains_actual": range_contains_actual,
        "low_price_error_pct":  low_price_error_pct,
        "high_price_error_pct": high_price_error_pct,
        "low_day_error_days":   low_day_error,
        "high_day_error_days":  high_day_error,
        "low_day_exact_match":  low_day_error == 0,
        "low_day_within_1":     low_day_error <= 1,
        "high_day_exact_match": high_day_error == 0,
        "high_day_within_1":    high_day_error <= 1,
    }


_TRAINING_SET_CACHE: Optional[list] = None


def load_range_timing_training_set() -> list:
    """Load the precomputed (feature vector -> real day-of-low/high) precedent
    pool built by scripts/adhoc/build_range_timing_training_set.py. Cached in
    memory after first load -- this file doesn't change at request time, same
    pattern as confidence_calibration_map.json elsewhere in this project.
    Returns [] (never raises) if the file is missing -- callers degrade to
    the rule-based predict_price_range_and_timing() instead."""
    global _TRAINING_SET_CACHE
    if _TRAINING_SET_CACHE is not None:
        return _TRAINING_SET_CACHE
    try:
        data = json.loads(TRAINING_SET_PATH.read_text(encoding="utf-8"))
        _TRAINING_SET_CACHE = data.get("cases", [])
    except Exception:
        _TRAINING_SET_CACHE = []
    return _TRAINING_SET_CACHE


def _standardize_with_query(query_vec: List[float], pool_vecs: List[List[float]]) -> List[List[float]]:
    """Z-score query_vec + pool_vecs together (NaN-safe) so distance isn't
    dominated by large-scale features. Returns [standardized_query, *standardized_pool]."""
    all_vecs = [query_vec] + pool_vecs
    n_feat = len(all_vecs[0])
    means = [0.0] * n_feat
    stds = [1.0] * n_feat
    for j in range(n_feat):
        col = [v[j] for v in all_vecs if not math.isnan(v[j])]
        if len(col) >= 2:
            m = sum(col) / len(col)
            var = sum((x - m) ** 2 for x in col) / len(col)
            s = math.sqrt(var) if var > 1e-9 else 1.0
            means[j], stds[j] = m, s
    return [
        [(v[j] - means[j]) / stds[j] if not math.isnan(v[j]) else 0.0 for j in range(n_feat)]
        for v in all_vecs
    ]


def predict_day_offset_knn(feature_vector: List[float], training_cases: list, k: int = KNN_K) -> dict:
    """K-nearest-neighbor day-timing estimate: find the k most similar past
    cases (by standardized Euclidean distance over the same feature vector
    ml_feature_extractor.py already defines) and return the MEDIAN of their
    real low-day/high-day offsets -- a precedent-based guess ("similar setups
    historically bottomed around day X"), not a fixed rule.

    Measurably better than the fixed-rule heuristic in predict_price_range_
    and_timing on the within-+/-1-day metric (see module-level constants for
    the real backtested numbers) -- use THIS for the day estimate shown to
    users; keep the rule-based one as a fallback when the training set is
    unavailable.

    Returns {"status": "INSUFFICIENT"} if there's no training data or vector
    to compare against -- never raises.
    """
    if not training_cases or not feature_vector:
        return {"status": "INSUFFICIENT"}

    pool_vecs = [c["vec"] for c in training_cases]
    try:
        std = _standardize_with_query(feature_vector, pool_vecs)
    except Exception:
        return {"status": "INSUFFICIENT"}
    std_query, std_pool = std[0], std[1:]

    dists = sorted(
        range(len(training_cases)),
        key=lambda i: math.sqrt(sum((a - b) ** 2 for a, b in zip(std_query, std_pool[i]))),
    )
    k = max(1, min(k, len(training_cases)))
    neighbors = [training_cases[i] for i in dists[:k]]

    low_days  = sorted(nb["actual_low_day"]  for nb in neighbors)
    high_days = sorted(nb["actual_high_day"] for nb in neighbors)

    return {
        "status": "OK",
        "predicted_low_day_offset":  low_days[len(low_days) // 2],
        "predicted_high_day_offset": high_days[len(high_days) // 2],
        "k_neighbors_used": k,
        "low_day_within_1_confidence_pct":  KNN_LOW_DAY_WITHIN_1_CONFIDENCE_PCT,
        "high_day_within_1_confidence_pct": KNN_HIGH_DAY_WITHIN_1_CONFIDENCE_PCT,
        "basis": f"median day-offset among the {k} most similar historical setups (precedent-based, not a fixed rule)",
    }
