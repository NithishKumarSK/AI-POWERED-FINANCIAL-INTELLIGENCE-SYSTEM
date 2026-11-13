"""
Component 3: Defensive Sector Rotation (Weight: 15%). Ported from
calculators/defensive_rotation_calculator.py.

Compares defensive ETF performance vs offensive/growth ETF performance
using multi-period weighted analysis: 10d(0.2) + 20d(0.5) + 40d(0.3).
Defensive: XLU, XLP, XLV, VNQ. Offensive: XLK, XLC, XLY, QQQ.
"""
from __future__ import annotations

from typing import Optional

DEFENSIVE_ETFS = ["XLU", "XLP", "XLV", "VNQ"]
OFFENSIVE_ETFS = ["XLK", "XLC", "XLY", "QQQ"]
MULTI_PERIOD_WEIGHTS = {10: 0.2, 20: 0.5, 40: 0.3}


def _calc_return(symbol_hist: list, days: int) -> Optional[float]:
    if not symbol_hist or len(symbol_hist) < days + 1:
        return None
    recent = symbol_hist[0].get("close", symbol_hist[0].get("adjClose", 0))
    past = symbol_hist[days].get("close", symbol_hist[days].get("adjClose", 0))
    if past == 0:
        return None
    return (recent - past) / past * 100


def _compute_period_rotation(historical: dict, lookback: int) -> Optional[dict]:
    def_returns = [r for r in (_calc_return(historical.get(s, []), lookback) for s in DEFENSIVE_ETFS) if r is not None]
    off_returns = [r for r in (_calc_return(historical.get(s, []), lookback) for s in OFFENSIVE_ETFS) if r is not None]
    if not def_returns or not off_returns:
        return None
    def_avg = sum(def_returns) / len(def_returns)
    off_avg = sum(off_returns) / len(off_returns)
    relative = def_avg - off_avg
    score = _score_rotation(relative)
    return {
        "lookback": lookback, "defensive_avg": round(def_avg, 2), "offensive_avg": round(off_avg, 2),
        "relative": round(relative, 2), "score": score, "defensive_leading": relative > 0,
    }


def calculate_defensive_rotation(historical: dict, lookback: int = 20) -> dict:
    """historical: {symbol: most-recent-first OHLCV list}, 50+ days."""
    all_etfs = DEFENSIVE_ETFS + OFFENSIVE_ETFS
    total_attempted = len(all_etfs)
    fetch_successes = 0

    def_details = {}
    off_details = {}
    for symbol in DEFENSIVE_ETFS:
        ret = _calc_return(historical.get(symbol, []), lookback)
        if ret is not None:
            def_details[symbol] = round(ret, 2)
            fetch_successes += 1
    for symbol in OFFENSIVE_ETFS:
        ret = _calc_return(historical.get(symbol, []), lookback)
        if ret is not None:
            off_details[symbol] = round(ret, 2)
            fetch_successes += 1

    fetch_success_rate = fetch_successes / total_attempted if total_attempted > 0 else 0.0

    if not def_details or not off_details:
        return {
            "score": 50, "signal": "INSUFFICIENT DATA (neutral default)", "data_available": False,
            "relative_performance": 0, "defensive_avg_return": 0, "offensive_avg_return": 0,
            "defensive_details": def_details, "offensive_details": off_details,
            "lookback_days": lookback, "fetch_success_rate": round(fetch_success_rate, 2),
        }

    period_results = {}
    weighted_score = 0.0
    total_weight = 0.0
    all_defensive = True
    periods_computed = 0

    for period, weight in MULTI_PERIOD_WEIGHTS.items():
        result = _compute_period_rotation(historical, period)
        if result is not None:
            period_results[period] = result
            weighted_score += result["score"] * weight
            total_weight += weight
            periods_computed += 1
            if not result["defensive_leading"]:
                all_defensive = False
        else:
            all_defensive = False

    if total_weight > 0:
        raw_score = weighted_score / total_weight
    else:
        def_avg = sum(def_details.values()) / len(def_details)
        off_avg = sum(off_details.values()) / len(off_details)
        raw_score = _score_rotation(def_avg - off_avg)

    if periods_computed >= 2 and all_defensive:
        confirmation = "confirmed"
        score = round(min(100, raw_score))
    elif periods_computed >= 2:
        confirmation = "unconfirmed"
        score = round(min(80, raw_score))
    else:
        confirmation = "single_period"
        score = round(min(100, raw_score))
    score = max(0, score)

    primary = period_results.get(lookback)
    if primary:
        relative, def_avg, off_avg = primary["relative"], primary["defensive_avg"], primary["offensive_avg"]
    else:
        def_avg = sum(def_details.values()) / len(def_details)
        off_avg = sum(off_details.values()) / len(off_details)
        relative = def_avg - off_avg

    if score >= 80:
        signal = "CRITICAL: Strong defensive rotation"
    elif score >= 60:
        signal = "WARNING: Defensive outperformance"
    elif score >= 40:
        signal = "CAUTION: Mild defensive rotation"
    elif score >= 20:
        signal = "MIXED: Slight defensive tilt"
    else:
        signal = "HEALTHY: Growth leading"

    return {
        "score": score, "signal": signal, "data_available": fetch_success_rate >= 0.75,
        "relative_performance": round(relative, 2), "defensive_avg_return": round(def_avg, 2),
        "offensive_avg_return": round(off_avg, 2), "defensive_details": def_details,
        "offensive_details": off_details, "lookback_days": lookback,
        "fetch_success_rate": round(fetch_success_rate, 2), "confirmation": confirmation,
        "multi_period": period_results,
    }


def _score_rotation(relative: float) -> int:
    if relative >= 5.0:
        return 100
    elif relative >= 3.0:
        return round(80 + (relative - 3.0) / 2.0 * 20)
    elif relative >= 1.5:
        return round(60 + (relative - 1.5) / 1.5 * 20)
    elif relative >= 0.5:
        return round(40 + (relative - 0.5) / 1.0 * 20)
    elif relative >= 0.0:
        return round(20 + relative / 0.5 * 20)
    elif relative >= -2.0:
        return round(max(0, 20 + relative / 2.0 * 20))
    return 0
