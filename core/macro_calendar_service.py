"""
Live orchestrator for tools/fxmacrodata_client.py -- ported from
claude-trading-skills' `fxmacrodata-calendar` skill. Produces an
event-risk summary for the window between an as-of date and the end of
a prediction horizon: is there a top-tier US macro release (CPI, NFP,
GDP, FOMC decision, etc.) due before the prediction resolves?

LIVE-ONLY, by design -- see tools/fxmacrodata_client.py's docstring.
Callers (core/gemini_stock_prediction_agent.py) MUST gate this behind
the same `_is_recent_origin` check already used for every other
live-only enrichment source. This module does not gate itself because
it has no notion of "the current prediction's origin date" -- that's
the caller's responsibility, exactly like rapidapi_market_service.py.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Optional, Tuple

from tools.fxmacrodata_client import fetch_calendar, filter_top_tier_events


def fetch_macro_event_risk(
    as_of_date: str,
    lookahead_days: int = 7,
    min_tier: int = 2,
    currency: str = "usd",
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Find the nearest top-tier macro release on/after as_of_date within lookahead_days.

    Returns (data, error_string). data is None (not an error) when the
    calendar fetch succeeded but no qualifying event falls in the window --
    an honestly empty result, per the source skill's own rule that only a
    successful response with no matching rows means "no event risk."
    """
    try:
        as_of = _dt.date.fromisoformat(as_of_date)
    except (ValueError, TypeError):
        return None, f"invalid_as_of_date:{as_of_date}"

    window_end = as_of + _dt.timedelta(days=max(lookahead_days, 0))
    payload, err = fetch_calendar(
        currency=currency,
        start_date=as_of.isoformat(),
        end_date=window_end.isoformat(),
    )
    if err:
        return None, err

    events = filter_top_tier_events(payload, min_tier=min_tier)
    if not events:
        return None, ""

    def _event_date(ev: Dict[str, Any]) -> Optional[_dt.date]:
        ts = ev.get("announcement_datetime_utc", "")
        try:
            return _dt.date.fromisoformat(ts[:10])
        except (ValueError, TypeError):
            return None

    dated_events = [(ev, _event_date(ev)) for ev in events]
    dated_events = [(ev, d) for ev, d in dated_events if d is not None and as_of <= d <= window_end]
    if not dated_events:
        return None, ""

    dated_events.sort(key=lambda pair: pair[1])
    nearest_event, nearest_date = dated_events[0]

    return {
        "has_event_risk": True,
        "nearest_event_name": nearest_event.get("name", nearest_event.get("release", "")),
        "nearest_event_date": nearest_date.isoformat(),
        "days_to_nearest_event": (nearest_date - as_of).days,
        "nearest_event_tier": nearest_event.get("market_tier"),
        "nearest_event_importance": nearest_event.get("event_importance", "unknown"),
        "events_in_window": len(dated_events),
    }, ""
