"""Tastytrade OAuth service — production API only.

Security rules (DO NOT violate):
- Never hardcode tokens, passwords, or secrets.
- Never log Authorization headers or token values.
- Never expose tokens in exception messages.
- Access tokens expire ~15 minutes; use refresh flow to renew.
- Use https://api.tastyworks.com (production) only.
- Do NOT use https://api.cert.tastyworks.com.
"""
from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

import requests

from src.config.settings import settings
from src.utils.logging_utils import get_logger, log_api_call, log_error

logger = get_logger(__name__)

_cached_token: Optional[str] = None
_cached_token_time: float = 0.0
_TOKEN_TTL: float = 14 * 60  # 14 min — refresh before 15-min expiry


def get_access_token() -> Tuple[Optional[str], str]:
    """Return a valid access token, using cache or refresh as needed.

    Prefers refresh-token flow over the static TASTYTRADE_ACCESS_TOKEN env value,
    because the static token may be expired (TTL ~15 min after issuance).
    Static token is only used as last resort when no refresh token is configured.
    """
    global _cached_token, _cached_token_time

    if _cached_token and (time.time() - _cached_token_time) < _TOKEN_TTL:
        return _cached_token, ""

    # Prefer refresh flow — static env token expires quickly and causes 401
    if settings.tastytrade_refresh_token:
        return refresh_access_token()

    # Fall back to static env token only when no refresh token is available
    if settings.tastytrade_access_token:
        _cached_token = settings.tastytrade_access_token
        _cached_token_time = time.time()
        logger.info("[TastytradeAuth] Using static access token from environment (no refresh token).")
        return _cached_token, ""

    return None, "TASTYTRADE_REFRESH_TOKEN is not configured. Add it to .env."


def refresh_access_token() -> Tuple[Optional[str], str]:
    """Exchange refresh token for a new access token."""
    global _cached_token, _cached_token_time

    if not settings.tastytrade_refresh_token:
        return None, "TASTYTRADE_REFRESH_TOKEN not set."

    url = f"{settings.tastytrade_api_base_url}/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": settings.tastytrade_refresh_token,
    }
    if settings.tastytrade_client_secret:
        payload["client_secret"] = settings.tastytrade_client_secret

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": settings.tastytrade_user_agent,
    }

    try:
        resp = requests.post(url, data=payload, headers=headers, timeout=15)
        log_api_call(logger, "TastytradeAuth", "/oauth/token", resp.status_code)

        if resp.status_code == 200:
            data = resp.json()
            token = data.get("access_token") or data.get("data", {}).get("access-token")
            if token:
                _cached_token = token
                _cached_token_time = time.time()
                logger.info("[TastytradeAuth] Token refreshed successfully.")
                return token, ""
            return None, "Token refresh succeeded but access_token missing from response."

        # Never expose token values in error messages
        return None, f"Token refresh failed: HTTP {resp.status_code}"

    except Exception as exc:
        log_error(logger, "TastytradeAuth", exc)
        return None, f"Token refresh error: {type(exc).__name__}"


def format_bearer_token(token: str) -> str:
    """Return 'Bearer <token>'. Safe to call with empty string. Never logged.
    Time O(1), Space O(1).
    """
    if not token:
        return ""
    token = token.strip()
    return token if token.startswith("Bearer ") else f"Bearer {token}"


def get_auth_headers(token: Optional[str] = None) -> Dict[str, str]:
    """Build Authorization headers without exposing the token value in logs."""
    t = token or _cached_token
    if not t:
        return {}
    return {
        "Authorization": format_bearer_token(t),
        "Content-Type": "application/json",
        "User-Agent": settings.tastytrade_user_agent,
    }


def validate_production_token(token: str) -> Tuple[bool, str]:
    """Lightweight validation that the token works against the production API."""
    headers = {
        "Authorization": format_bearer_token(token),
        "Content-Type": "application/json",
        "User-Agent": settings.tastytrade_user_agent,
    }
    url = f"{settings.tastytrade_api_base_url}/customers/me"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        log_api_call(logger, "TastytradeAuth", "/customers/me", resp.status_code)
        if resp.status_code == 200:
            return True, ""
        return False, f"Token validation failed: HTTP {resp.status_code}"
    except Exception as exc:
        return False, f"Token validation error: {type(exc).__name__}"


def clear_token_cache() -> None:
    global _cached_token, _cached_token_time
    _cached_token = None
    _cached_token_time = 0.0
