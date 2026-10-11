"""Central ApeWisdom client — Research Expansion Program, Component 2
(Reddit mention/attention data, free, keyless).

Mirrors tools/alpha_vantage_client.py's pattern: structured {"status": ...}
returns, never raises. Uses apewisdom.io's own public API directly (NOT the
third-party "oanor" wrapper found during research, which requires its own
key and adds an unnecessary middleman) -- verified live this session,
confirmed keyless and working.

LIVE-ONLY: this is a current-snapshot ranking with no historical/point-in-time
capability (same category as RapidAPI's market movers) -- callers must gate
this to live/recent predictions only, never historical replay.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import requests

_BASE_URL = "https://apewisdom.io/api/v1.0"
_MAX_PAGES_TO_SEARCH = 3  # covers top ~300 mentioned tickers -- enough for any symbol with real chatter


def get_mentions_page(page: int, filter_name: str = "all-stocks", timeout: int = 15) -> Dict[str, Any]:
    """GET one page of the Reddit-mentions ranking.

    Returns {"status": "SUCCESS", "data": <parsed JSON>} or
    {"status": "ERROR", "error_type": ..., "message": ...}. Never raises.
    """
    url = f"{_BASE_URL}/filter/{filter_name}/page/{page}"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200:
            return {
                "status": "ERROR", "error_type": f"HTTP_{resp.status_code}",
                "message": f"ApeWisdom returned HTTP {resp.status_code}",
                "preview": resp.text[:200],
            }
        return {"status": "SUCCESS", "data": resp.json()}
    except requests.Timeout:
        return {"status": "ERROR", "error_type": "TIMEOUT", "message": "Request timed out"}
    except Exception as exc:
        return {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc)}


def find_symbol_mentions(symbol: str) -> Dict[str, Any]:
    """Search the first _MAX_PAGES_TO_SEARCH pages for this symbol's current
    Reddit-mentions entry. Returns:
        {"status": "SUCCESS", "found": True, "rank": int, "mentions": int,
         "mentions_24h_ago": int, "upvotes": int}
        {"status": "SUCCESS", "found": False}   -- symbol has no significant
            current Reddit chatter; this is a real, meaningful result, not an error.
        {"status": "ERROR", ...}                -- the API itself failed.
    """
    sym_upper = symbol.strip().upper()
    for page in range(1, _MAX_PAGES_TO_SEARCH + 1):
        result = get_mentions_page(page)
        if result.get("status") != "SUCCESS":
            return result
        results = (result.get("data") or {}).get("results") or []
        for item in results:
            if str(item.get("ticker", "")).upper() == sym_upper:
                return {
                    "status": "SUCCESS", "found": True,
                    "rank": item.get("rank"),
                    "mentions": item.get("mentions"),
                    "mentions_24h_ago": item.get("mentions_24h_ago"),
                    "upvotes": item.get("upvotes"),
                }
    return {"status": "SUCCESS", "found": False}
