"""Centralised config loading from .env — never hardcode secrets here."""
from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load project-root .env with absolute path so it works regardless of CWD
# settings.py lives at src/config/settings.py → parents[2] is the project root
_BASE_DIR = Path(__file__).resolve().parents[2]
_ENV_PATH  = _BASE_DIR / ".env"
load_dotenv(_ENV_PATH, override=True)


@dataclass(frozen=True)
class Settings:
    # Tastytrade
    tastytrade_api_base_url: str = field(
        default_factory=lambda: os.getenv("TASTYTRADE_API_BASE_URL", "https://api.tastyworks.com"))
    tastytrade_backtester_base_url: str = field(
        default_factory=lambda: os.getenv("TASTYTRADE_BACKTESTER_BASE_URL", "https://backtester.vast.tastyworks.com"))
    tastytrade_client_secret: str = field(
        default_factory=lambda: os.getenv("TASTYTRADE_CLIENT_SECRET", "").strip())
    tastytrade_refresh_token: str = field(
        default_factory=lambda: os.getenv("TASTYTRADE_REFRESH_TOKEN", "").strip())
    tastytrade_access_token: str = field(
        default_factory=lambda: os.getenv("TASTYTRADE_ACCESS_TOKEN", "").strip())
    tastytrade_user_agent: str = field(
        default_factory=lambda: os.getenv("TASTYTRADE_USER_AGENT", "ajay-ai-finance/1.0"))

    # Google Gemini
    gemini_api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", ""))
    agent_model: str = field(
        default_factory=lambda: os.getenv("AGENT_MODEL", "gemini-2.5-flash"))
    agent_temperature: float = field(
        default_factory=lambda: float(os.getenv("AGENT_TEMPERATURE", "1.0")))

    # RapidAPI TradingView
    rapidapi_key: str = field(
        default_factory=lambda: os.getenv("RAPIDAPI_KEY", ""))
    rapidapi_host: str = "tradingview-data1.p.rapidapi.com"
    rapidapi_base_url: str = "https://tradingview-data1.p.rapidapi.com"

    # App
    current_user: str = field(
        default_factory=lambda: os.getenv("CURRENT_USER", ""))
    google_cloud_project: str = field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT", ""))

    @property
    def has_tastytrade_auth(self) -> bool:
        """True only when BOTH client_secret AND refresh_token are present.
        Access token is NOT required — it expires quickly and is obtained via refresh.
        """
        return bool(self.tastytrade_client_secret and self.tastytrade_refresh_token)

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def has_rapidapi(self) -> bool:
        return bool(self.rapidapi_key)

    @property
    def tastytrade_auth_headers(self) -> dict:
        if not self.tastytrade_access_token:
            return {}
        return {
            "Authorization": _format_bearer(self.tastytrade_access_token),
            "Content-Type": "application/json",
            "User-Agent": self.tastytrade_user_agent,
        }


def _format_bearer(token: str) -> str:
    """Ensure Authorization value is always 'Bearer <token>'. Never logged."""
    if not token:
        return ""
    token = token.strip()
    return token if token.startswith("Bearer ") else f"Bearer {token}"


# Module-level singleton — import this everywhere
settings = Settings()
