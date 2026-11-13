"""
Client for Binance's free, keyless public futures funding-rate endpoint,
adapted from claude-trading-skills' `crypto-regime-analyzer` skill. MIT
License, Copyright (c) 2026 TraderMonty.

Confirmed live this session (2026-11-02): /fapi/v1/premiumIndex returns
HTTP 200 with a real lastFundingRate, no API key.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import requests

BASE_URL = "https://fapi.binance.com"
TIMEOUT_SECONDS = 15


def fetch_latest_funding(symbol: str) -> Tuple[Optional[float], str]:
    """Latest 8h funding rate (decimal, e.g. 0.0001 = +0.010%) for one USDT perp."""
    try:
        resp = requests.get(
            f"{BASE_URL}/fapi/v1/premiumIndex",
            params={"symbol": symbol.upper()},
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
    rate = payload.get("lastFundingRate")
    if rate is None:
        return None, "no_funding_rate"
    return float(rate), ""


def fetch_funding_for_symbols(symbols: list) -> Tuple[Dict[str, float], Dict[str, str]]:
    """Best-effort batch fetch -- a symbol that fails is simply absent from
    the result dict (and recorded in the errors dict), never a fabricated 0.0.
    """
    funding: Dict[str, float] = {}
    errors: Dict[str, str] = {}
    for symbol in symbols:
        rate, err = fetch_latest_funding(symbol)
        if err:
            errors[symbol] = err
        else:
            funding[symbol] = rate
    return funding, errors
