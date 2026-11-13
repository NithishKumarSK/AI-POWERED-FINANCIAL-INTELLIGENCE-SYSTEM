"""
Client for FXMacroData's public macro release-calendar API
(https://api.fxmacrodata.com), adapted from claude-trading-skills'
`fxmacrodata-calendar` skill (vendor/claude-trading-skills/skills/
fxmacrodata-calendar/SKILL.md). MIT License, Copyright (c) 2026
TraderMonty.

Confirmed live this session (2026-11-02):
  curl https://api.fxmacrodata.com/v1/calendar/usd  -> HTTP 200, real
  official-source rows (Fed/BLS/BEA release calendars), no API key
  required for the basic /calendar/{currency} endpoint.

SCOPE REDUCTION, disclosed: the source skill's `--min-tier` CLI flag and
its "data_quality" acceptance checks are reproduced here, but the paid
`/calendar/{currency}/snapshot` point-in-time endpoint (the only one that
is genuinely leakage-safe for an arbitrary historical `as_of`) returned
HTTP 401 "api_key_required" when tested live without a key. The free
`/calendar/{currency}` endpoint itself was confirmed live to hold real
history only from 2026-07-27 forward (`history_truncated: true`,
`row_count: 0` for a 2025-01 range) -- i.e. it is a forward-looking "what's
coming up" calendar, not a historical archive. This client is therefore
honestly LIVE-ONLY: callers must gate it to recent/real-time predictions
(the same `_is_recent_origin` discipline already used for yfinance's
options chain and live market movers), never trust it for a historical
replay.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE_URL = "https://api.fxmacrodata.com/v1"
TIMEOUT_SECONDS = 10

VALID_CURRENCIES = {
    "AUD", "BRL", "CAD", "CHF", "CNH", "CNY", "COMM", "DKK", "EUR", "GBP",
    "HUF", "ILS", "JPY", "KRW", "MYR", "NGN", "NOK", "NZD", "PEN", "SEK",
    "THB", "TWD", "USD",
}


def fetch_calendar(
    currency: str = "usd",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Fetch the raw FXMacroData release calendar for one currency.

    Returns (payload, error_string). Never raises. A non-empty error
    string means the caller must NOT trust any `data` on the payload
    (e.g. the SKILL.md's own rule: "a nonzero exit is an unverified
    event-risk state, never an empty calendar").
    """
    currency_upper = currency.upper().strip()
    if currency_upper not in VALID_CURRENCIES:
        return None, f"unsupported_currency:{currency}"

    params: Dict[str, str] = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    api_key = os.getenv("FXMACRODATA_API_KEY", "").strip()
    if api_key:
        params["api_key"] = api_key

    try:
        resp = requests.get(
            f"{BASE_URL}/calendar/{currency_upper.lower()}",
            params=params,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return None, f"network_error: {type(exc).__name__}: {exc}"

    if resp.status_code != 200:
        return None, f"http_{resp.status_code}"

    try:
        payload = resp.json()
    except ValueError:
        return None, "invalid_json_response"

    if payload.get("currency", "").upper() != currency_upper:
        return None, "currency_mismatch"

    dq = payload.get("data_quality", {}) or {}
    if not dq.get("is_official", False):
        return None, "data_quality_not_official"
    if dq.get("is_proxy", False) or dq.get("is_fallback", False):
        return None, "data_quality_proxy_or_fallback"

    return payload, ""


def filter_top_tier_events(
    payload: Dict[str, Any],
    min_tier: int = 2,
) -> List[Dict[str, Any]]:
    """Filter a fetch_calendar() payload's events down to market_tier <= min_tier.

    Every returned event has a non-empty `announcement_datetime_utc` and a
    non-empty `release` identifier (SKILL.md's acceptance rule); events
    missing either are dropped rather than passed through half-formed.
    """
    if min_tier not in (1, 2, 3):
        min_tier = 3
    events = payload.get("data", []) or []
    out = []
    for ev in events:
        tier = ev.get("market_tier")
        if tier is None or tier > min_tier:
            continue
        if not ev.get("announcement_datetime_utc") or not ev.get("release"):
            continue
        out.append(ev)
    return out
