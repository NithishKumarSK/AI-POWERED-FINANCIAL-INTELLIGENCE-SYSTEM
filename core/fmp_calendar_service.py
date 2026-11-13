"""
fmp_calendar_service.py -- earnings calendar + economic data-release
calendar via FMP (tools/fmp_client.py), adapted from claude-trading-skills'
earnings-calendar and economic-calendar-fetcher skills
(vendor/claude-trading-skills/skills/{earnings-calendar,economic-calendar-fetcher}/,
MIT License, Copyright (c) 2026 TraderMonty).

Both are forward-looking calendars (upcoming earnings/economic releases) --
live-only by nature, same category as RapidAPI market movers and ApeWisdom
Reddit elsewhere in this project: not usable for historical backtest
replay (a past as_of_date can't "see" a calendar for dates after it the
way it can see a resolved historical fact), so callers should gate these
to _is_recent_origin.

Follows the (data, error_string) tuple convention from historical_price_service.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))

MIN_MARKET_CAP = 2_000_000_000  # $2B, same floor the source skill uses


def fetch_earnings_calendar(start_date: str, end_date: str, symbol: Optional[str] = None) -> Tuple[Optional[list], str]:
    """Upcoming earnings announcements in [start_date, end_date], optionally
    filtered to one symbol. Returns (data, error_string). data: list of
    {"symbol","date","eps_estimated","revenue_estimated"}."""
    from fmp_client import fmp_get

    result = fmp_get("earnings-calendar", {"from": start_date, "to": end_date})
    if result.get("status") != "SUCCESS":
        return None, result.get("message", "FMP earnings-calendar request failed")

    rows = result.get("data") or []
    if not isinstance(rows, list):
        return None, "Unexpected earnings-calendar response shape (not a list)"

    cleaned = []
    for r in rows:
        if symbol and r.get("symbol", "").upper() != symbol.upper():
            continue
        cleaned.append({
            "symbol": r.get("symbol"), "date": r.get("date"),
            "eps_estimated": r.get("epsEstimated"), "revenue_estimated": r.get("revenueEstimated"),
        })
    return cleaned, ""


def fetch_economic_calendar(start_date: str, end_date: str, countries: Optional[list] = None) -> Tuple[Optional[list], str]:
    """Upcoming economic data releases in [start_date, end_date] (CPI, NFP,
    GDP, central-bank decisions, ...). Returns (data, error_string). data:
    list of {"date","country","event","currency","impact","previous","estimate"}."""
    from fmp_client import fmp_get

    result = fmp_get("economic-calendar", {"from": start_date, "to": end_date})
    if result.get("status") != "SUCCESS":
        return None, result.get("message", "FMP economic-calendar request failed")

    rows = result.get("data") or []
    if not isinstance(rows, list):
        return None, "Unexpected economic-calendar response shape (not a list)"

    countries_upper = {c.upper() for c in countries} if countries else None
    cleaned = []
    for r in rows:
        if countries_upper and (r.get("country") or "").upper() not in countries_upper:
            continue
        cleaned.append({
            "date": r.get("date"), "country": r.get("country"), "event": r.get("event"),
            "currency": r.get("currency"), "impact": r.get("impact"),
            "previous": r.get("previous"), "estimate": r.get("estimate"), "actual": r.get("actual"),
        })
    return cleaned, ""
