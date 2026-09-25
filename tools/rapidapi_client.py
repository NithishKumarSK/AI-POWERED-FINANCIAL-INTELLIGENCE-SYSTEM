"""Central RapidAPI client — correct host, dynamic key loading, structured error handling.

Security rules:
- Key is NEVER logged or exposed in exceptions.
- Always read os.getenv("RAPIDAPI_KEY") at call time, never at import time.
- Host/base-URL read from env so .env override works without code changes.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

# Correct host: trading-view.p.rapidapi.com  (NOT tradingview-data1.p.rapidapi.com)
_DEFAULT_HOST = "trading-view.p.rapidapi.com"
_DEFAULT_BASE_URL = "https://trading-view.p.rapidapi.com"


def get_rapidapi_key() -> str:
    return os.getenv("RAPIDAPI_KEY", "")


def get_rapidapi_host() -> str:
    return os.getenv("RAPIDAPI_HOST", _DEFAULT_HOST)


def get_rapidapi_base_url() -> str:
    return os.getenv("RAPIDAPI_BASE_URL", _DEFAULT_BASE_URL)


def get_rapidapi_headers(host: Optional[str] = None) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-rapidapi-host": host or get_rapidapi_host(),
        "x-rapidapi-key": get_rapidapi_key(),
    }


def rapidapi_get(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    host: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """GET request to RapidAPI. path should start with '/'.

    Returns:
        {"status": "SUCCESS", "data": <parsed JSON>}
        {"status": "ERROR", "error_type": "RAPIDAPI_403", ...}   on 403
        {"status": "ERROR", "error_type": "HTTP_<N>", ...}        on other errors
    Never raises. Never logs the API key.
    """
    resolved_host = host or get_rapidapi_host()
    resolved_base = base_url or get_rapidapi_base_url()
    url = f"{resolved_base}{path}"
    headers = get_rapidapi_headers(resolved_host)
    try:
        resp = requests.get(url, headers=headers, params=params or {}, timeout=timeout)
        if resp.status_code == 403:
            return {
                "status": "ERROR",
                "error_type": "RAPIDAPI_403",
                "message": "RapidAPI subscription error (403). Check host and key.",
                "host": resolved_host,
                "endpoint": url,
                "preview": resp.text[:300],
            }
        if resp.status_code != 200:
            return {
                "status": "ERROR",
                "error_type": f"HTTP_{resp.status_code}",
                "message": f"API returned HTTP {resp.status_code}",
                "host": resolved_host,
                "endpoint": url,
                "preview": resp.text[:200],
            }
        return {"status": "SUCCESS", "data": resp.json()}
    except requests.Timeout:
        return {"status": "ERROR", "error_type": "TIMEOUT", "message": "Request timed out", "endpoint": url}
    except Exception as exc:
        return {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc), "endpoint": url}


def rapidapi_post(
    path: str,
    json_body: Optional[Dict[str, Any]] = None,
    host: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """POST request to RapidAPI."""
    resolved_host = host or get_rapidapi_host()
    resolved_base = base_url or get_rapidapi_base_url()
    url = f"{resolved_base}{path}"
    headers = get_rapidapi_headers(resolved_host)
    try:
        resp = requests.post(url, headers=headers, json=json_body or {}, timeout=timeout)
        if resp.status_code == 403:
            return {
                "status": "ERROR",
                "error_type": "RAPIDAPI_403",
                "message": "RapidAPI subscription error (403). Check host and key.",
                "host": resolved_host,
                "endpoint": url,
                "preview": resp.text[:300],
            }
        if resp.status_code not in (200, 201):
            return {
                "status": "ERROR",
                "error_type": f"HTTP_{resp.status_code}",
                "message": f"API returned HTTP {resp.status_code}",
                "preview": resp.text[:200],
            }
        return {"status": "SUCCESS", "data": resp.json()}
    except Exception as exc:
        return {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc), "endpoint": url}
