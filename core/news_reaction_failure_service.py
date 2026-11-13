"""
Live orchestrator for core/news_reaction_failure.py -- fetches daily
price history via core/historical_price_service.py (leakage-safe,
truncated to as_of_date) and runs the drift-significance test against a
caller-supplied, already-curated events list (see that module's
docstring for why curation itself isn't done here).
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Tuple

from news_reaction_failure import DEFAULT_MIN_EVENTS, DEFAULT_STDEV_LOOKBACK, DRIFT_Z_DEFAULT, analyze_news_reaction


def fetch_news_reaction_analysis(
    symbol: str,
    events: List[Dict[str, Any]],
    as_of_date: str,
    drift_z: float = DRIFT_Z_DEFAULT,
    min_events: int = DEFAULT_MIN_EVENTS,
    stdev_lookback: int = DEFAULT_STDEV_LOOKBACK,
    lookback_days: int = 400,
) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        from historical_price_service import fetch_price_history_for_range
        lookback_start = (_dt.date.fromisoformat(as_of_date) - _dt.timedelta(days=lookback_days)).isoformat()
        bars, price_err, _ = fetch_price_history_for_range(symbol, lookback_start, as_of_date)
    except Exception as exc:
        return None, f"price_history_failed: {type(exc).__name__}: {exc}"
    if price_err or not bars:
        return None, price_err or "no_price_history"

    chronological = sorted(bars, key=lambda b: b["date"]) if bars and bars[0]["date"] > bars[-1]["date"] else bars
    truncated = [b for b in chronological if b["date"][:10] <= as_of_date[:10]]
    trading_dates = [b["date"][:10] for b in truncated]
    closes = [b["close"] for b in truncated]

    result = analyze_news_reaction(events, trading_dates, closes, drift_z=drift_z, min_events=min_events, stdev_lookback=stdev_lookback)
    result["symbol"] = symbol.upper()
    return result, ""
