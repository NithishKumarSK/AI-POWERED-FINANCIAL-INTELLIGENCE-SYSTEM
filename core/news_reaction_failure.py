"""
News Reaction Failure Analyzer (Shapiro Step 2), adapted from claude-
trading-skills' `news-reaction-failure-analyzer` skill
(vendor/claude-trading-skills/skills/news-reaction-failure-analyzer/,
references/news-failure-patterns.md). MIT License, Copyright (c) 2026
TraderMonty.

Judges whether a market FAILED to react to news favorable to a crowded
position, using a statistically validated drift-significance test (not
a naive failure-ratio, which the source skill's own design notes show
false-confirms on pure noise 48-83% of the time). Faithfully ported:
effective-date resolution (16:00 ET cutoff, weekend/holiday roll-
forward), true k-trading-session returns with sqrt(k) horizon scaling,
event clustering by overlapping 3-day windows (earliest member's z3
drives the cluster, never averaged), the `drift_stat <= -drift_z AND
responded_ratio <= 0.25` two-condition verdict, and the Monte-Carlo-
chosen `DRIFT_Z_DEFAULT = 1.45`.

SCOPE REDUCTION, disclosed: the events list itself (`events_json`,
normally WebSearch-curated by Claude per the source skill's own
"Events JSON Curation Guide" -- dateable news, classified BULLISH/
BEARISH, cited to a real source_url) is NOT fetched by this module --
same "caller supplies the curated input" pattern already used for
`breakout_trade_planner.py` (consumes `vcp_screener` output) and
`futures_position_sizer.py` Mode A. This module takes `events` as a
parameter; sourcing/curating it is the caller's responsibility.
"""
from __future__ import annotations

import datetime as _dt
import math
import statistics
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

DRIFT_Z_DEFAULT = 1.45
RESPONDED_RATIO_THRESHOLD = 0.25
DEFAULT_MIN_EVENTS = 3
DEFAULT_STDEV_LOOKBACK = 60
_EASTERN = ZoneInfo("America/New_York")


def resolve_effective_date(event_time_iso: str, trading_dates: List[str]) -> Tuple[Optional[str], str]:
    """First trading date at/after the event; events at/after 16:00 ET
    count from the next trading day. Returns (date_str, error_string)."""
    try:
        dt_obj = _dt.datetime.fromisoformat(event_time_iso)
    except ValueError:
        return None, "unparsable_event_time"
    if dt_obj.tzinfo is None:
        return None, "unparsable_event_time"

    et = dt_obj.astimezone(_EASTERN)
    calendar_date = et.date()
    if et.hour >= 16:
        calendar_date = calendar_date + _dt.timedelta(days=1)

    for d in trading_dates:
        if _dt.date.fromisoformat(d) >= calendar_date:
            return d, ""
    return None, "no_trading_day_after_event"


def compute_return_and_zscore(
    trading_dates: List[str], closes: List[float], effective_date: str, stdev_lookback: int = DEFAULT_STDEV_LOOKBACK,
) -> Optional[Dict[str, float]]:
    """True k-trading-session returns (k in {1,3}) against the close the
    day before, with sqrt(k) horizon-scaled z-scores. None when there
    isn't enough history before/after the effective date."""
    try:
        idx = trading_dates.index(effective_date)
    except ValueError:
        return None
    if idx - 1 - stdev_lookback < 0 or idx + 2 >= len(closes):
        return None

    daily_returns = [closes[i] / closes[i - 1] - 1 for i in range(idx - stdev_lookback, idx)]
    daily_stdev = statistics.stdev(daily_returns)
    if daily_stdev <= 0:
        return None

    return_1d = closes[idx] / closes[idx - 1] - 1
    return_3d = closes[idx + 2] / closes[idx - 1] - 1
    return {
        "return_1d": return_1d, "return_3d": return_3d,
        "zscore_1d": return_1d / daily_stdev, "zscore_3d": return_3d / (daily_stdev * math.sqrt(3)),
        "daily_stdev": daily_stdev, "idx": idx,
    }


def _direction_adjust(value: float, expected_impact: str) -> float:
    """Positive = moved favorably WITH the news; negative = moved against it."""
    return value if expected_impact == "BULLISH" else -value


def cluster_relevant_events(resolved_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapses events whose 3-trading-day windows [idx, idx+2] overlap
    into one cluster, counted once toward n, using the EARLIEST member's
    z3 (never averaged). resolved_events must be sorted by idx ascending."""
    clusters: List[Dict[str, Any]] = []
    for ev in resolved_events:
        if clusters and ev["idx"] <= clusters[-1]["_window_end_idx"]:
            clusters[-1]["cluster_members"].append(ev)
            clusters[-1]["_window_end_idx"] = max(clusters[-1]["_window_end_idx"], ev["idx"] + 2)
        else:
            clusters.append({
                "cluster_members": [ev], "_window_end_idx": ev["idx"] + 2,
                "effective_date": ev["effective_date"],
                "zscore_3d": ev["zscore_3d"],
                "direction_adjusted_z3": ev["direction_adjusted_z3"],
            })
    return clusters


def analyze_news_reaction(
    events: List[Dict[str, Any]],
    trading_dates: List[str],
    closes: List[float],
    drift_z: float = DRIFT_Z_DEFAULT,
    min_events: int = DEFAULT_MIN_EVENTS,
    stdev_lookback: int = DEFAULT_STDEV_LOOKBACK,
) -> Dict[str, Any]:
    """events: [{"event_id", "event", "event_time" (ISO8601 w/ UTC offset),
    "source_url", "source_tier", "expected_impact": "BULLISH"|"BEARISH"}].
    trading_dates/closes: parallel, chronological (oldest -> newest).
    """
    resolved: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []

    for ev in events:
        eff_date, err = resolve_effective_date(ev["event_time"], trading_dates)
        if err:
            dropped.append({**ev, "drop_reason": err})
            continue
        stats = compute_return_and_zscore(trading_dates, closes, eff_date, stdev_lookback)
        if stats is None:
            dropped.append({**ev, "drop_reason": "insufficient_price_history"})
            continue
        direction_adjusted_z3 = _direction_adjust(stats["zscore_3d"], ev["expected_impact"])
        direction_adjusted_return_3d = _direction_adjust(stats["return_3d"], ev["expected_impact"])
        resolved.append({
            **ev, "effective_date": eff_date, **stats,
            "direction_adjusted_z3": direction_adjusted_z3,
            "responded": direction_adjusted_return_3d > 0,
        })

    resolved.sort(key=lambda e: e["idx"])

    if len(resolved) < min_events:
        return {
            "schema_version": "1.0", "verdict": "INSUFFICIENT_EVIDENCE", "verdict_reason": "too_few_usable_events",
            "n_events_usable": len(resolved), "n_events_dropped": len(dropped), "dropped": dropped,
            "drift_stat": None, "responded_ratio": None, "clusters": None,
        }

    clusters = cluster_relevant_events(resolved)
    n = len(clusters)
    drift_stat = math.sqrt(n) * statistics.mean(c["direction_adjusted_z3"] for c in clusters)
    responded_ratio = sum(1 for e in resolved if e["responded"]) / len(resolved)

    confirmed = drift_stat <= -drift_z and responded_ratio <= RESPONDED_RATIO_THRESHOLD
    verdict = "CONFIRMED" if confirmed else "NOT_CONFIRMED"
    verdict_reason = "news_failure_confirmed" if confirmed else "insufficient_drift_or_responded_too_often"

    return {
        "schema_version": "1.0", "verdict": verdict, "verdict_reason": verdict_reason,
        "n_events_usable": len(resolved), "n_events_dropped": len(dropped), "dropped": dropped,
        "drift_stat": round(drift_stat, 4), "responded_ratio": round(responded_ratio, 4),
        "drift_z_used": drift_z, "n_clusters": n,
        "clusters": [{"effective_date": c["effective_date"], "zscore_3d": round(c["zscore_3d"], 4),
                       "cluster_size": len(c["cluster_members"])} for c in clusters],
        "events": resolved,
    }
