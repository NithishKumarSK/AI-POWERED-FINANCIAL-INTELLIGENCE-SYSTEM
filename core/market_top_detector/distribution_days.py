"""
Component 1: Distribution Day Count (Weight: 25%). Ported from
calculators/distribution_day_calculator.py.

O'Neil's Distribution Day Rules:
- Distribution Day: Index drops >= 0.2% on higher volume than previous day
- Stalling Day: Volume increases but price gain < 0.1% (half weight)
- Days expire after 25 trading days
- Count the higher of S&P 500 or NASDAQ

Note: a separate, more elaborate port of the full IBD methodology (with
5%-gain invalidation and per-day enrichment) lives in
core/ibd_distribution_day_monitor.py -- this is the source skill's own
simpler count-in-trailing-25-days version, kept faithful to its own
scoring curve rather than conflated with that one.
"""
from __future__ import annotations


def calculate_distribution_days(sp500_history: list, nasdaq_history: list) -> dict:
    """*_history: most-recent-first OHLCV, at least 30 days."""
    sp500_result = _count_distribution_days(sp500_history)
    nasdaq_result = _count_distribution_days(nasdaq_history)

    sp500_effective = sp500_result["distribution_days"] + 0.5 * sp500_result["stalling_days"]
    nasdaq_effective = nasdaq_result["distribution_days"] + 0.5 * nasdaq_result["stalling_days"]

    if sp500_effective >= nasdaq_effective:
        primary = sp500_result
        primary_name = "S&P 500"
    else:
        primary = nasdaq_result
        primary_name = "NASDAQ"

    effective_count = max(sp500_effective, nasdaq_effective)
    raw_score = _score_distribution_days(effective_count)

    clustering = _calculate_clustering_factor(primary["details"])
    clustering_applied = effective_count >= 2 and clustering["factor"] > 0.5
    score = min(100, round(raw_score * 1.15)) if clustering_applied else raw_score

    if effective_count >= 5:
        signal = "CRITICAL: Heavy distribution detected"
    elif effective_count >= 4:
        signal = "WARNING: O'Neil's threshold reached"
    elif effective_count >= 3:
        signal = "CAUTION: Moderate distribution"
    elif effective_count >= 1:
        signal = "MINOR: Some distribution present"
    else:
        signal = "CLEAR: No distribution"

    return {
        "score": score,
        "raw_score": raw_score,
        "effective_count": effective_count,
        "signal": signal,
        "clustering": clustering,
        "clustering_applied": clustering_applied,
        "primary_index": primary_name,
        "sp500": {
            "distribution_days": sp500_result["distribution_days"],
            "stalling_days": sp500_result["stalling_days"],
            "effective_count": sp500_effective,
        },
        "nasdaq": {
            "distribution_days": nasdaq_result["distribution_days"],
            "stalling_days": nasdaq_result["stalling_days"],
            "effective_count": nasdaq_effective,
        },
    }


def _count_distribution_days(history: list) -> dict:
    if not history or len(history) < 2:
        return {"distribution_days": 0, "stalling_days": 0, "details": []}

    window = min(25, len(history) - 1)
    distribution_days = 0
    stalling_days = 0
    details = []

    for i in range(window):
        today = history[i]
        yesterday = history[i + 1]
        today_close = today.get("close", today.get("adjClose", 0))
        yesterday_close = yesterday.get("close", yesterday.get("adjClose", 0))
        today_volume = today.get("volume", 0)
        yesterday_volume = yesterday.get("volume", 0)

        if yesterday_close == 0 or yesterday_volume == 0:
            continue

        pct_change = (today_close - yesterday_close) / yesterday_close * 100
        volume_increase = today_volume > yesterday_volume
        date = today.get("date", f"day-{i}")

        if pct_change <= -0.2 and volume_increase:
            distribution_days += 1
            details.append({
                "date": date, "type": "distribution", "pct_change": round(pct_change, 2),
                "volume_change": round((today_volume / yesterday_volume - 1) * 100, 1),
                "window_index": i,
            })
        elif volume_increase and 0 <= pct_change < 0.1:
            stalling_days += 1
            details.append({
                "date": date, "type": "stalling", "pct_change": round(pct_change, 2),
                "volume_change": round((today_volume / yesterday_volume - 1) * 100, 1),
                "window_index": i,
            })

    return {"distribution_days": distribution_days, "stalling_days": stalling_days, "details": details}


def _calculate_clustering_factor(details: list) -> dict:
    """window_index 0-4 = most recent 5 days. factor = recent/total."""
    if not details:
        return {"factor": 0.0, "recent_count": 0, "total_count": 0}
    total_count = len(details)
    recent_count = sum(1 for d in details if d.get("window_index", 99) < 5)
    factor = recent_count / total_count if total_count > 0 else 0.0
    return {"factor": round(factor, 2), "recent_count": recent_count, "total_count": total_count}


def _score_distribution_days(effective_count: float) -> int:
    if effective_count >= 6:
        return 100
    elif effective_count >= 5:
        return 90
    elif effective_count >= 4:
        return 75
    elif effective_count >= 3:
        return 55
    elif effective_count >= 2:
        return 30
    elif effective_count >= 1:
        return 15
    return 0
