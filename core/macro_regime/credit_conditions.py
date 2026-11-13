"""
Component 3: Credit Conditions (weight 15%) -- HYG/LQD ratio, ported from
claude-trading-skills' macro-regime-detector (see core/macro_regime/__init__.py).

Rising ratio = credit risk appetite expanding (easing). Falling = flight
to quality (tightening).
"""
from __future__ import annotations

from .utils import calculate_ratio, compute_percentile, compute_roc, compute_sma, detect_crossover, determine_direction, downsample_to_monthly, score_transition_signal


def calculate_credit_conditions(hyg_history: list, lqd_history: list) -> dict:
    if not hyg_history or not lqd_history:
        return _insufficient_data("No HYG or LQD data available")

    hyg_monthly, lqd_monthly = downsample_to_monthly(hyg_history), downsample_to_monthly(lqd_history)
    if len(hyg_monthly) < 12 or len(lqd_monthly) < 12:
        return _insufficient_data("Insufficient monthly data (need >= 12 months)")

    ratio_series = calculate_ratio(hyg_monthly, lqd_monthly)
    if len(ratio_series) < 12:
        return _insufficient_data("Insufficient ratio data")

    ratio_values = [r["value"] for r in ratio_series]
    current_ratio, current_date = ratio_values[0], ratio_series[0]["date"]
    sma_6m, sma_12m = compute_sma(ratio_values, 6), compute_sma(ratio_values, 12)
    crossover = detect_crossover(ratio_values, short_period=6, long_period=12)
    roc_3m, roc_12m = compute_roc(ratio_values, 3), compute_roc(ratio_values, 12)
    percentile = compute_percentile(ratio_values, current_ratio)
    score = score_transition_signal(crossover, roc_3m, roc_12m, sma_6m, sma_12m)
    direction, momentum_qualifier = determine_direction(crossover, roc_3m, "easing", "tightening", "stable")
    signal = _describe_signal(score, direction, current_ratio)

    return {
        "score": score, "signal": signal, "data_available": True, "direction": direction,
        "momentum_qualifier": momentum_qualifier,
        "current_ratio": round(current_ratio, 4), "current_date": current_date,
        "sma_6m": round(sma_6m, 4) if sma_6m is not None else None,
        "sma_12m": round(sma_12m, 4) if sma_12m is not None else None,
        "roc_3m": round(roc_3m, 2) if roc_3m is not None else None,
        "roc_12m": round(roc_12m, 2) if roc_12m is not None else None,
        "percentile": round(percentile, 1) if percentile is not None else None,
        "crossover": crossover, "monthly_points": len(ratio_series),
    }


def _describe_signal(score: int, direction: str, ratio: float) -> str:
    if score >= 60:
        return f"TRANSITION: Credit conditions {direction} (HYG/LQD={ratio:.4f})"
    elif score >= 40:
        return f"SHIFTING: Credit conditions {direction} (HYG/LQD={ratio:.4f})"
    return f"STABLE: Credit conditions stable (HYG/LQD={ratio:.4f})"


def _insufficient_data(reason: str) -> dict:
    return {
        "score": 0, "signal": f"INSUFFICIENT DATA: {reason}", "data_available": False,
        "direction": "unknown", "current_ratio": None, "current_date": None,
        "sma_6m": None, "sma_12m": None, "roc_3m": None, "roc_12m": None,
        "percentile": None, "crossover": {"type": "none", "bars_ago": None}, "monthly_points": 0,
    }
