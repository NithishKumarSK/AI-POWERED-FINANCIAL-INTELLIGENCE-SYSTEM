"""Central Alpha Vantage client — Phase 3 accuracy-improvement program
(news/earnings/sentiment, scoped to single-name symbols).

Mirrors tools/rapidapi_client.py's pattern exactly: key read from env at call
time (never at import time), structured {"status": ...} returns, never raises.

Note: the Alpha Vantage MCP connector available to the assistant in chat
sessions is NOT callable by this deployed app -- this is a real, independent
HTTP integration requiring its own free-tier key
(https://www.alphavantage.co/support/#api-key) in ALPHA_VANTAGE_API_KEY.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

_DEFAULT_BASE_URL = "https://www.alphavantage.co/query"


def get_alpha_vantage_key() -> str:
    return os.getenv("ALPHA_VANTAGE_API_KEY", "")


def get_alpha_vantage_base_url() -> str:
    return os.getenv("ALPHA_VANTAGE_BASE_URL", _DEFAULT_BASE_URL)


def alpha_vantage_get(
    function: str,
    params: Optional[Dict[str, Any]] = None,
    base_url: Optional[str] = None,
    timeout: int = 20,
) -> Dict[str, Any]:
    """GET request to the Alpha Vantage query API (function=<endpoint name>).

    Returns:
        {"status": "SUCCESS", "data": <parsed JSON>}
        {"status": "ERROR", "error_type": "NO_KEY", ...}        if key not set
        {"status": "ERROR", "error_type": "RATE_LIMIT", ...}    on free-tier throttle
        {"status": "ERROR", "error_type": "HTTP_<N>", ...}      on other HTTP errors
    Never raises. Never logs the API key.
    """
    key = get_alpha_vantage_key()
    if not key:
        return {"status": "ERROR", "error_type": "NO_KEY", "message": "ALPHA_VANTAGE_API_KEY not set in .env"}

    resolved_base = base_url or get_alpha_vantage_base_url()
    query = dict(params or {})
    query["function"] = function
    query["apikey"] = key

    try:
        resp = requests.get(resolved_base, params=query, timeout=timeout)
        if resp.status_code != 200:
            return {
                "status": "ERROR",
                "error_type": f"HTTP_{resp.status_code}",
                "message": f"API returned HTTP {resp.status_code}",
                "preview": resp.text[:200],
            }
        data = resp.json()
        # Alpha Vantage returns 200 OK with a "Note"/"Information" field instead
        # of a real HTTP error when the free-tier rate limit is hit -- this is
        # the single easiest way to silently get an empty result and think the
        # symbol just has no data, so it's classified explicitly.
        if isinstance(data, dict) and ("Note" in data or "Information" in data):
            return {
                "status": "ERROR", "error_type": "RATE_LIMIT",
                "message": data.get("Note") or data.get("Information"),
            }
        if isinstance(data, dict) and "Error Message" in data:
            return {"status": "ERROR", "error_type": "API_ERROR", "message": data["Error Message"]}
        return {"status": "SUCCESS", "data": data}
    except requests.Timeout:
        return {"status": "ERROR", "error_type": "TIMEOUT", "message": "Request timed out"}
    except Exception as exc:
        return {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc)}
