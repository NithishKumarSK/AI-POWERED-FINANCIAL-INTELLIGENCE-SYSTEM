"""
Live orchestrator for core/contrarian_confirmation.py -- fetches daily
OHLC via core/historical_price_service.py, truncates to as_of_date
BEFORE resampling (no lookahead, per the source skill's own documented
rule: "truncates daily bars to --as-of BEFORE resampling"), resamples
to completed ISO calendar weeks, and runs the confirmation checklist.

Only completed weeks are used -- a week still in progress as of
as_of_date is dropped, since the checklist is explicitly defined "entirely
in terms of completed ISO calendar weeks" (Guardrail, technical-analyst
SKILL.md).
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Tuple

from contrarian_confirmation import DEFAULT_MIN_WEEKS, run_contrarian_confirmation


def _resample_to_completed_weeks(daily_bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """daily_bars: chronological (oldest -> newest) dicts with date/open/high/low/close.
    Groups by ISO (year, week), drops the LAST group if it doesn't look
    like a complete trading week (fewer than 4 sessions) -- a cheap,
    conservative proxy for "still in progress," since holidays can
    legitimately shorten a real completed week to as few as 4 sessions."""
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    order: List[Any] = []
    for bar in daily_bars:
        d = _dt.date.fromisoformat(bar["date"][:10])
        key = d.isocalendar()[:2]
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(bar)

    weekly = []
    for key in order:
        days = groups[key]
        weekly.append({
            "week_of": days[-1]["date"][:10],
            "open": days[0]["open"], "high": max(d["high"] for d in days),
            "low": min(d["low"] for d in days), "close": days[-1]["close"],
            "_session_count": len(days),
        })

    if weekly and weekly[-1]["_session_count"] < 4:
        weekly = weekly[:-1]
    for w in weekly:
        w.pop("_session_count", None)
    return weekly


def fetch_contrarian_confirmation(
    symbol: str,
    direction: str,
    as_of_date: str,
    min_weeks: int = DEFAULT_MIN_WEEKS,
) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        from historical_price_service import fetch_price_history_for_range
        lookback_start = (_dt.date.fromisoformat(as_of_date) - _dt.timedelta(days=min_weeks * 7 + 400)).isoformat()
        bars, price_err, _ = fetch_price_history_for_range(symbol, lookback_start, as_of_date)
    except Exception as exc:
        return None, f"price_history_failed: {type(exc).__name__}: {exc}"
    if price_err or not bars:
        return None, price_err or "no_price_history"

    chronological = sorted(bars, key=lambda b: b["date"]) if bars and bars[0]["date"] > bars[-1]["date"] else bars
    truncated = [b for b in chronological if b["date"][:10] <= as_of_date[:10]]
    weekly_bars = _resample_to_completed_weeks(truncated)

    result = run_contrarian_confirmation(weekly_bars, direction=direction, min_weeks=min_weeks)
    result["symbol"] = symbol.upper()
    return result, ""
