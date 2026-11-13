"""Central Financial Modeling Prep (FMP) client -- free tier (250 req/day,
no credit card, 5 years of US-exchange data), confirmed live this session.

Mirrors tools/alpha_vantage_client.py's pattern: key read from env at call
time, structured {"status": ...} returns, never raises. Uses the current
/stable/ API (FMP's v3 endpoints are deprecated) with header-based auth
(apikey in the request header, not the URL) so the key never appears in a
logged URL or exception text.

Live-verified this session: GET /stable/quote?symbol=AAPL returned a real,
current quote (price $344.63, real market cap) with the free-tier key.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import requests

_BASE_URL = "https://financialmodelingprep.com/stable"
_MIN_REQUEST_INTERVAL_S = 0.25  # free tier is 250 req/day; no need to hammer it

_last_request_ts = 0.0


def get_fmp_key() -> str:
    return os.getenv("FMP_API_KEY", "")


def _throttle() -> None:
    global _last_request_ts
    elapsed = time.time() - _last_request_ts
    if elapsed < _MIN_REQUEST_INTERVAL_S:
        time.sleep(_MIN_REQUEST_INTERVAL_S - elapsed)
    _last_request_ts = time.time()


def fmp_get(endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: int = 20) -> Dict[str, Any]:
    """GET request to a /stable/ FMP endpoint (e.g. "quote", "earnings-calendar").

    Returns:
        {"status": "SUCCESS", "data": <parsed JSON>}
        {"status": "ERROR", "error_type": "NO_KEY", ...}             if key not set
        {"status": "ERROR", "error_type": "PREMIUM_REQUIRED", ...}   free tier can't reach this endpoint
        {"status": "ERROR", "error_type": "RATE_LIMIT", ...}         daily 250-request cap hit
        {"status": "ERROR", "error_type": "HTTP_<N>", ...}           other HTTP errors
    Never raises. Never logs the API key (header auth, not query param).
    """
    key = get_fmp_key()
    if not key:
        return {"status": "ERROR", "error_type": "NO_KEY", "message": "FMP_API_KEY not set in .env"}

    _throttle()
    try:
        resp = requests.get(
            f"{_BASE_URL}/{endpoint.lstrip('/')}",
            params=params or {},
            headers={"apikey": key},
            timeout=timeout,
        )
        if resp.status_code in (402, 403):
            return {"status": "ERROR", "error_type": "PREMIUM_REQUIRED",
                     "message": f"FMP returned {resp.status_code} -- this endpoint needs a paid plan the free tier doesn't cover"}
        if resp.status_code == 429:
            return {"status": "ERROR", "error_type": "RATE_LIMIT",
                     "message": "FMP free-tier daily request limit (250/day) reached"}
        if resp.status_code != 200:
            return {"status": "ERROR", "error_type": f"HTTP_{resp.status_code}",
                     "message": f"FMP returned HTTP {resp.status_code}", "preview": resp.text[:200]}
        data = resp.json()
        if isinstance(data, dict) and "Error Message" in data:
            return {"status": "ERROR", "error_type": "API_ERROR", "message": data["Error Message"]}
        return {"status": "SUCCESS", "data": data}
    except requests.Timeout:
        return {"status": "ERROR", "error_type": "TIMEOUT", "message": "Request timed out"}
    except Exception as exc:
        return {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc)}
