"""
Component 2: Yield Curve (weight 20%) -- 10Y-2Y Treasury spread (primary)
or SHY/TLT ratio (keyless fallback), ported from claude-trading-skills'
macro-regime-detector (see core/macro_regime/__init__.py).
"""
from __future__ import annotations

from typing import Optional

from .utils import calculate_ratio, compute_percentile, compute_roc, compute_sma, detect_crossover, downsample_to_monthly, score_transition_signal


def calculate_yield_curve(
    treasury_rates: Optional[list] = None,
    shy_history: Optional[list] = None,
    tlt_history: Optional[list] = None,
) -> dict:
    if treasury_rates:
        result = _analyze_treasury_spread(treasury_rates)
        if result is not None:
            return result
    if shy_history and tlt_history:
        return _analyze_shy_tlt_proxy(shy_history, tlt_history)
    return _insufficient_data("No treasury rates or SHY/TLT data available")


def _analyze_treasury_spread(treasury_rates: list) -> Optional[dict]:
    spread_monthly = {}
    for entry in treasury_rates:
        date_str = entry.get("date", "")
        year10, year2 = entry.get("year10"), entry.get("year2")
        if not date_str or year10 is None or year2 is None:
            continue
        try:
            y10, y2 = float(year10), float(year2)
        except (ValueError, TypeError):
            continue
        ym = date_str[:7]
        if ym not in spread_monthly:
            spread_monthly[ym] = {"date": date_str, "spread": y10 - y2, "year10": y10, "year2": y2}

    if len(spread_monthly) < 12:
        return None

    spread_series = sorted(spread_monthly.values(), key=lambda x: x["date"], reverse=True)
    spread_values = [s["spread"] for s in spread_series]
    current_spread = spread_values[0]
    current_date = spread_series[0]["date"]
    current_10y, current_2y = spread_series[0]["year10"], spread_series[0]["year2"]

    sma_6m, sma_12m = compute_sma(spread_values, 6), compute_sma(spread_values, 12)
    crossover = detect_crossover(spread_values, short_period=6, long_period=12)
    y10_values = [s["year10"] for s in spread_series]
    y2_values = [s["year2"] for s in spread_series]
    roc_3m_10y, roc_3m_2y = compute_roc(y10_values, 3), compute_roc(y2_values, 3)
    roc_3m, roc_12m = compute_roc(spread_values, 3), compute_roc(spread_values, 12)
    percentile = compute_percentile(spread_values, current_spread)
    score = score_transition_signal(crossover, roc_3m, roc_12m, sma_6m, sma_12m)
    curve_state = _classify_curve_state(current_spread, sma_6m, roc_3m)

    if roc_3m is not None and roc_3m > 0:
        direction = "steepening"
    elif roc_3m is not None and roc_3m < 0:
        direction = "flattening"
    else:
        direction = "stable"

    steepening_type = None
    if direction == "steepening":
        if roc_3m_2y is not None and roc_3m_2y < 0:
            steepening_type = "bull_steepener"
        elif roc_3m_10y is not None and roc_3m_10y > 0:
            steepening_type = "bear_steepener"
        else:
            steepening_type = "mixed_steepener"

    signal = _describe_signal(score, curve_state, current_spread, direction)

    return {
        "score": score, "signal": signal, "data_available": True, "data_source": "treasury_api",
        "direction": direction, "curve_state": curve_state, "steepening_type": steepening_type,
        "current_spread": round(current_spread, 3), "current_10y": current_10y, "current_2y": current_2y,
        "current_date": current_date,
        "sma_6m": round(sma_6m, 3) if sma_6m is not None else None,
        "sma_12m": round(sma_12m, 3) if sma_12m is not None else None,
        "roc_3m": round(roc_3m, 2) if roc_3m is not None else None,
        "roc_12m": round(roc_12m, 2) if roc_12m is not None else None,
        "roc_3m_10y": round(roc_3m_10y, 2) if roc_3m_10y is not None else None,
        "roc_3m_2y": round(roc_3m_2y, 2) if roc_3m_2y is not None else None,
        "percentile": round(percentile, 1) if percentile is not None else None,
        "crossover": crossover, "monthly_points": len(spread_series),
    }


def _analyze_shy_tlt_proxy(shy_history: list, tlt_history: list) -> dict:
    shy_monthly, tlt_monthly = downsample_to_monthly(shy_history), downsample_to_monthly(tlt_history)
    if len(shy_monthly) < 12 or len(tlt_monthly) < 12:
        return _insufficient_data("Insufficient SHY/TLT monthly data")

    ratio_series = calculate_ratio(shy_monthly, tlt_monthly)
    if len(ratio_series) < 12:
        return _insufficient_data("Insufficient SHY/TLT ratio data")

    ratio_values = [r["value"] for r in ratio_series]
    current_ratio, current_date = ratio_values[0], ratio_series[0]["date"]
    sma_6m, sma_12m = compute_sma(ratio_values, 6), compute_sma(ratio_values, 12)
    crossover = detect_crossover(ratio_values, short_period=6, long_period=12)
    roc_3m, roc_12m = compute_roc(ratio_values, 3), compute_roc(ratio_values, 12)
    percentile = compute_percentile(ratio_values, current_ratio)
    score = score_transition_signal(crossover, roc_3m, roc_12m, sma_6m, sma_12m)

    if roc_3m is not None and roc_3m < 0:
        direction = "steepening"
    elif roc_3m is not None and roc_3m > 0:
        direction = "flattening"
    else:
        direction = "stable"

    return {
        "score": score, "signal": f"PROXY (SHY/TLT): {direction} signal, score={score}",
        "data_available": True, "data_source": "shy_tlt_proxy", "direction": direction,
        "curve_state": "proxy_only", "steepening_type": None,
        "current_spread": None, "current_10y": None, "current_2y": None, "current_date": current_date,
        "proxy_ratio": round(current_ratio, 4),
        "sma_6m": round(sma_6m, 4) if sma_6m is not None else None,
        "sma_12m": round(sma_12m, 4) if sma_12m is not None else None,
        "roc_3m": round(roc_3m, 2) if roc_3m is not None else None,
        "roc_12m": round(roc_12m, 2) if roc_12m is not None else None,
        "percentile": round(percentile, 1) if percentile is not None else None,
        "crossover": crossover, "monthly_points": len(ratio_series),
    }


def _classify_curve_state(spread: float, sma_6m: Optional[float], roc_3m: Optional[float]) -> str:
    if spread < -0.5:
        return "deeply_inverted"
    elif spread < 0:
        return "inverted"
    elif spread < 0.5:
        return "normalizing" if (roc_3m is not None and roc_3m > 0) else "flat"
    elif spread < 1.5:
        return "normal"
    return "steep"


def _describe_signal(score: int, state: str, spread: float, direction: str) -> str:
    labels = {"deeply_inverted": "Deeply Inverted", "inverted": "Inverted", "normalizing": "Normalizing",
              "flat": "Flat", "normal": "Normal", "steep": "Steep"}
    state_label = labels.get(state, state)
    if score >= 60:
        return f"TRANSITION: Yield curve {direction} ({state_label}, spread={spread:+.3f}%)"
    elif score >= 40:
        return f"SHIFTING: Yield curve {direction} ({state_label}, spread={spread:+.3f}%)"
    return f"STABLE: Yield curve {state_label} (spread={spread:+.3f}%)"


def _insufficient_data(reason: str) -> dict:
    return {
        "score": 0, "signal": f"INSUFFICIENT DATA: {reason}", "data_available": False,
        "data_source": "none", "direction": "unknown", "curve_state": "unknown",
        "current_spread": None, "current_10y": None, "current_2y": None, "current_date": None,
        "sma_6m": None, "sma_12m": None, "roc_3m": None, "roc_12m": None,
        "percentile": None, "crossover": {"type": "none", "bars_ago": None}, "monthly_points": 0,
    }
