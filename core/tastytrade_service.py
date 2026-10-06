"""
Tastytrade Service -- Production health check using OAuth refresh flow.

Security rules (DO NOT violate):
- Never hardcode tokens, passwords, or secrets.
- Never log Authorization headers or token values.
- Never expose tokens in exception messages.
- Use https://api.tastyworks.com (production) only.
- Do NOT use https://api.cert.tastyworks.com.
- Never place real trades or call order/position endpoints.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()


def _base() -> str:
    return os.getenv("TASTYTRADE_API_BASE_URL", "https://api.tastyworks.com")


def _ua() -> str:
    return os.getenv("TASTYTRADE_USER_AGENT", "flex-ai-finance/1.0")


def _refresh_token_value() -> str:
    return os.getenv("TASTYTRADE_REFRESH_TOKEN", "")


def _client_secret() -> str:
    return os.getenv("TASTYTRADE_CLIENT_SECRET", "")


def _exchange_refresh_token() -> Tuple[str, str]:
    """POST /oauth/token with grant_type=refresh_token. Returns (access_token, error)."""
    refresh = _refresh_token_value()
    if not refresh:
        return "", "TASTYTRADE_REFRESH_TOKEN not set in .env"

    payload: Dict[str, str] = {
        "grant_type":    "refresh_token",
        "refresh_token": refresh,
    }
    secret = _client_secret()
    if secret:
        payload["client_secret"] = secret

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent":   _ua(),
    }
    try:
        r = requests.post(
            f"{_base()}/oauth/token",
            data=payload,
            headers=headers,
            timeout=15,
        )
        if r.status_code == 200:
            token = r.json().get("access_token", "")
            if token:
                return token, ""
            return "", "Token refresh succeeded but access_token missing from response"
        # Never include token values in error messages
        return "", f"Token refresh failed: HTTP {r.status_code}"
    except Exception as exc:
        return "", f"Token refresh error: {type(exc).__name__}"


def _bearer(token: str) -> str:
    return token if token.startswith("Bearer ") else f"Bearer {token}"


def run_tastytrade_health_check() -> Dict[str, Any]:
    """
    Refresh the access token, then call GET /customers/me to confirm the
    Tastytrade production API connection is live and credentials are valid.

    Returns a dict with:
      called                -- True if the /customers/me request was made
      endpoint              -- Full URL called (/customers/me)
      http_status           -- HTTP response code (0 on exception)
      latency_ms            -- round-trip time in ms
      token_refreshed       -- True if refresh succeeded
      customer_verified     -- True if /customers/me returned HTTP 200
      refresh_present       -- bool: was TASTYTRADE_REFRESH_TOKEN in env
      role                  -- "authentication_and_account_health_check"
      used_in_stock_mode    -- False (stock mode uses price validation only)
      used_in_options_mode  -- True (backtester uses Tastytrade credentials)
      error                 -- None or error string
    """
    refresh_present = bool(_refresh_token_value())
    base            = _base()
    endpoint        = f"{base}/customers/me"

    result: Dict[str, Any] = {
        "called":               False,
        "endpoint":             endpoint,
        "http_status":          0,
        "latency_ms":           None,
        "token_refreshed":      False,
        "customer_verified":    False,
        "refresh_present":      refresh_present,
        "role":                 "authentication_and_account_health_check",
        "used_in_stock_mode":   False,
        "used_in_options_mode": True,
        "error":                None,
    }

    if not refresh_present:
        result["error"] = "TASTYTRADE_REFRESH_TOKEN not set in .env"
        return result

    # Step 1 — exchange refresh token for access token
    token, ref_err = _exchange_refresh_token()
    if not token:
        result["error"] = ref_err
        return result

    result["token_refreshed"] = True

    # Step 2 — verify token against /customers/me
    auth_headers = {
        "Authorization": _bearer(token),
        "Content-Type":  "application/json",
        "User-Agent":    _ua(),
    }
    try:
        t0  = time.monotonic()
        r   = requests.get(endpoint, headers=auth_headers, timeout=10)
        ms  = int((time.monotonic() - t0) * 1000)
        result["called"]      = True
        result["http_status"] = r.status_code
        result["latency_ms"]  = ms
        if r.status_code == 200:
            result["customer_verified"] = True
        else:
            # Never expose token in error message
            result["error"] = f"HTTP {r.status_code}"
    except Exception as exc:
        result["called"] = True
        result["error"]  = f"{type(exc).__name__}: {exc}"

    return result


def run_tastytrade_instrument_check(symbol: str) -> Dict[str, Any]:
    """
    Verify that a symbol exists as a tradeable equity via /instruments/equities/{symbol}.
    Uses a freshly-refreshed token. For health check / verification only -- no trades placed.
    """
    hc = run_tastytrade_health_check()
    hc["symbol_checked"] = symbol

    if not hc.get("customer_verified"):
        hc["instrument_found"] = False
        return hc

    token, _ = _exchange_refresh_token()
    if not token:
        hc["instrument_found"] = False
        hc["instrument_error"] = "Could not get access token for instrument check"
        return hc

    inst_endpoint = f"{_base()}/instruments/equities/{symbol}"
    auth_headers  = {
        "Authorization": _bearer(token),
        "Content-Type":  "application/json",
        "User-Agent":    _ua(),
    }
    hc["instrument_endpoint"] = inst_endpoint
    try:
        r = requests.get(inst_endpoint, headers=auth_headers, timeout=10)
        hc["instrument_http_status"] = r.status_code
        hc["instrument_found"]       = r.status_code == 200
    except Exception as exc:
        hc["instrument_found"]  = False
        hc["instrument_error"]  = f"{type(exc).__name__}: {exc}"
    return hc
