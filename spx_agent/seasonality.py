"""
SPX Seasonality Stats
Calendar-month return / win-rate / range stats computed from up to 5 years
of daily history -- answers "historically, what does SPX tend to do in
this month".
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _month_key(d: str) -> str:
    return d[:7]  # YYYY-MM


def build_monthly_seasonality(bars: List[Dict]) -> Dict:
    """Groups bars into calendar month-instances (e.g. 2024-03), computes
    each instance's return/range, then aggregates by month-of-year (Jan..Dec)
    across however many years of history are available."""
    by_month_instance: Dict[str, List[Dict]] = defaultdict(list)
    for b in bars:
        by_month_instance[_month_key(b["date"])].append(b)

    month_instance_stats = []
    for key, mbars in sorted(by_month_instance.items()):
        mbars = sorted(mbars, key=lambda b: b["date"])
        open_, close = mbars[0]["open"], mbars[-1]["close"]
        high = max(b["high"] for b in mbars)
        low = min(b["low"] for b in mbars)
        month_instance_stats.append({
            "key": key,
            "month_num": int(key.split("-")[1]),
            "return_pct": (close - open_) / open_ * 100,
            "range_pct": (high - low) / open_ * 100,
        })

    by_month_of_year: Dict[int, List[Dict]] = defaultdict(list)
    for s in month_instance_stats:
        by_month_of_year[s["month_num"]].append(s)

    monthly_summary = {}
    for m in range(1, 13):
        instances = by_month_of_year.get(m, [])
        if not instances:
            continue
        returns = [i["return_pct"] for i in instances]
        ranges = [i["range_pct"] for i in instances]
        wins = sum(1 for r in returns if r > 0)
        monthly_summary[m] = {
            "month": MONTH_NAMES[m - 1],
            "years_observed": len(instances),
            "avg_return_pct": round(sum(returns) / len(returns), 2),
            "win_rate_pct": round(wins / len(returns) * 100, 0),
            "avg_range_pct": round(sum(ranges) / len(ranges), 2),
            "best_pct": round(max(returns), 2),
            "worst_pct": round(min(returns), 2),
        }

    current_month = datetime.now().month
    return {
        "by_month": monthly_summary,
        "current_month_stats": monthly_summary.get(current_month),
        "current_month_num": current_month,
    }
