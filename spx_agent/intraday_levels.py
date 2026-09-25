"""
SPX Intraday (15-Minute) Level Detection
Builds day-trading levels from recent 15-minute bars: per-session VWAP,
opening-range (first 30 min) high/low, confluence support/resistance zones
clustered across the lookback window, and a by-time-of-day volatility
profile -- everything needed to plan tomorrow's session off of last
week's/last day's actual intraday structure.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean, median
from typing import Dict, List

BUCKET_PTS = 10.0       # confluence-zone rounding granularity
MIN_TOUCHES = 2         # a level needs >=2 touches to count as confluence
OPENING_RANGE_BARS = 2  # 2 x 15m bars = first 30 minutes of the session


def _group_by_session(bars: List[Dict]) -> Dict[str, List[Dict]]:
    sessions: Dict[str, List[Dict]] = defaultdict(list)
    for b in bars:
        sessions[b["date"]].append(b)
    return dict(sorted(sessions.items()))


def _session_vwap(bars: List[Dict]) -> float:
    num, den = 0.0, 0.0
    for b in bars:
        typical = (b["high"] + b["low"] + b["close"]) / 3
        num += typical * b["volume"]
        den += b["volume"]
    return round(num / den, 2) if den else round(bars[-1]["close"], 2)


def _build_session_summaries(bars: List[Dict]) -> List[Dict]:
    sessions = _group_by_session(bars)
    summaries = []
    for sdate, sbars in sessions.items():
        sbars = sorted(sbars, key=lambda b: b["time"])
        or_bars = sbars[:OPENING_RANGE_BARS]
        session_high = max(b["high"] for b in sbars)
        session_low = min(b["low"] for b in sbars)
        summaries.append({
            "date": sdate,
            "open": sbars[0]["open"],
            "high": session_high,
            "low": session_low,
            "close": sbars[-1]["close"],
            "vwap": _session_vwap(sbars),
            "or_high": max(b["high"] for b in or_bars),
            "or_low": min(b["low"] for b in or_bars),
            "range_pts": round(session_high - session_low, 1),
            "up_day": sbars[-1]["close"] >= sbars[0]["open"],
        })
    return summaries


def _cluster_levels(bars: List[Dict], bucket: float = BUCKET_PTS, min_touches: int = MIN_TOUCHES) -> List[Dict]:
    """Round each 15m bar's high/low to the nearest `bucket` points and count
    touches -- buckets hit repeatedly across the window are confluence
    support/resistance zones for day trading."""
    counts: Dict[float, int] = defaultdict(int)
    for b in bars:
        counts[round(b["high"] / bucket) * bucket] += 1
        counts[round(b["low"] / bucket) * bucket] += 1
    zones = [{"level": lvl, "touches": c} for lvl, c in counts.items() if c >= min_touches]
    zones.sort(key=lambda z: (-z["touches"], z["level"]))
    return zones


def build_intraday_levels(bars: List[Dict]) -> Dict:
    if not bars:
        return {}

    bars = sorted(bars, key=lambda b: b["datetime"])
    sessions = _build_session_summaries(bars)
    last_close = bars[-1]["close"]

    zones = _cluster_levels(bars)
    resistance = sorted([z for z in zones if z["level"] > last_close], key=lambda z: z["level"])[:6]
    support = sorted([z for z in zones if z["level"] <= last_close], key=lambda z: -z["level"])[:6]

    last_session = sessions[-1]
    recent_sessions = sessions[-10:]
    session_ranges = [s["range_pts"] for s in recent_sessions]

    by_time: Dict[str, List[float]] = defaultdict(list)
    for b in bars:
        by_time[b["time"]].append(b["high"] - b["low"])
    time_profile = [
        {"time": t, "avg_range_pts": round(mean(v), 1)}
        for t, v in sorted(by_time.items())
    ]

    return {
        "sessions_used": len(sessions),
        "bars_used": len(bars),
        "date_range": (sessions[0]["date"], sessions[-1]["date"]),
        "last_session": last_session,
        "resistance_zones": resistance,
        "support_zones": support,
        "nearest_resistance": resistance[0]["level"] if resistance else None,
        "nearest_support": support[0]["level"] if support else None,
        "median_session_range_pts": round(median(session_ranges), 1) if session_ranges else None,
        "avg_session_range_pts": round(mean(session_ranges), 1) if session_ranges else None,
        "time_of_day_profile": time_profile,
        "sessions": recent_sessions,
    }
