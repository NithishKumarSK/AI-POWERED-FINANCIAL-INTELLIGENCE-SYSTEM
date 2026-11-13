"""
Client for CoinGecko's free, keyless public API, adapted from claude-
trading-skills' `crypto-regime-analyzer` skill's `scripts/data_client.py`
(vendor/claude-trading-skills/skills/crypto-regime-analyzer/). MIT
License, Copyright (c) 2026 TraderMonty.

Confirmed live this session (2026-11-02): /coins/markets, /global, and
/coins/{id}/market_chart all return HTTP 200 with no API key.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import requests

BASE_URL = "https://api.coingecko.com/api/v3"
TIMEOUT_SECONDS = 20
_STABLECOIN_SYMBOLS = {"usdt", "usdc", "dai", "busd", "tusd", "usde", "fdusd", "usds"}
_WRAPPED_STAKED_PREFIXES = ("wrapped-", "staked-", "wbtc", "weth", "steth", "wsteth")


def fetch_top_markets(top_n: int = 20, vs_currency: str = "usd") -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """Top-N coins by market cap, excluding stablecoins and wrapped/staked assets.

    Returns (coins, error_string). Never raises.
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/coins/markets",
            params={"vs_currency": vs_currency, "order": "market_cap_desc", "per_page": min(top_n * 2, 250), "page": 1},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return None, f"network_error: {type(exc).__name__}: {exc}"
    if resp.status_code != 200:
        return None, f"http_{resp.status_code}"
    try:
        coins = resp.json()
    except ValueError:
        return None, "invalid_json_response"
    if not isinstance(coins, list):
        return None, "unexpected_response_shape"

    filtered = [
        c for c in coins
        if c.get("symbol", "").lower() not in _STABLECOIN_SYMBOLS
        and not str(c.get("id", "")).lower().startswith(_WRAPPED_STAKED_PREFIXES)
    ]
    return filtered[:top_n], ""


def fetch_market_chart_daily(coin_id: str, days: int = 365, vs_currency: str = "usd") -> Tuple[Optional[List[float]], str]:
    """Daily close prices for one coin, oldest -> newest. Returns (closes, error).

    Confirmed live this session: CoinGecko's free/public tier caps
    historical range at 365 days (`error_code: 10012` on a wider request,
    paid-plan-gated beyond that) -- the default here stays at the actual
    free-tier ceiling rather than a larger number that silently 401s.
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/coins/{coin_id}/market_chart",
            params={"vs_currency": vs_currency, "days": days, "interval": "daily"},
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
    prices = payload.get("prices")
    if not prices:
        return None, "no_price_data"
    return [p[1] for p in prices], ""


def fetch_btc_dominance() -> Tuple[Optional[float], str]:
    """Current BTC dominance percentage. Returns (pct, error)."""
    try:
        resp = requests.get(f"{BASE_URL}/global", timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return None, f"network_error: {type(exc).__name__}: {exc}"
    if resp.status_code != 200:
        return None, f"http_{resp.status_code}"
    try:
        payload = resp.json()
    except ValueError:
        return None, "invalid_json_response"
    pct = (payload.get("data", {}) or {}).get("market_cap_percentage", {}).get("btc")
    if pct is None:
        return None, "no_dominance_data"
    return float(pct), ""
