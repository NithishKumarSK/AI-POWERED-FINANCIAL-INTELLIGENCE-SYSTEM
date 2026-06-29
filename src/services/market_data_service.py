"""Market data service — thin wrapper isolating RapidAPI TradingView calls."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.config.settings import settings
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def _rapidapi_headers() -> Dict[str, str]:
    return {
        "x-rapidapi-host": settings.rapidapi_host,
        "x-rapidapi-key": settings.rapidapi_key,
    }


def get_price(symbol: str) -> Optional[float]:
    """Return latest price for symbol, or None on failure."""
    if not settings.has_rapidapi:
        logger.warning("[MarketData] RAPIDAPI_KEY not configured.")
        return None
    try:
        from tools.tradingview_price import get_price as _get_price
        result = _get_price(symbol)
        if result and result.get("status") == "SUCCESS":
            return float(result.get("price") or result.get("data", {}).get("price") or 0)
    except Exception as exc:
        logger.warning(f"[MarketData] get_price({symbol}) failed: {exc}")
    return None


def get_market_data(symbol: str, endpoint: str = "") -> Dict[str, Any]:
    """Fetch market data from TradingView RapidAPI."""
    if not settings.has_rapidapi:
        return {"status": "ERROR", "message": "RAPIDAPI_KEY not configured."}
    try:
        from tools.tradingview_market_data import get_market_data as _get_md
        return _get_md(symbol, endpoint)
    except Exception as exc:
        logger.warning(f"[MarketData] get_market_data({symbol}, {endpoint}) failed: {exc}")
        return {"status": "ERROR", "message": str(exc)}


def get_technical_analysis(symbol: str) -> Dict[str, Any]:
    try:
        from tools.tradingview_technical_analysis import get_technical_analysis as _get_ta
        return _get_ta(symbol)
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


def get_news(symbol: str) -> Dict[str, Any]:
    try:
        from tools.tradingview_news import get_news as _get_news
        return _get_news(symbol)
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


def get_historical_data(symbol: str, period: str = "1Y") -> Dict[str, Any]:
    try:
        from tools.stock_historical_data import get_year_historical_data
        return get_year_historical_data(symbol)
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


def get_analyst_recommendations(symbol: str) -> Dict[str, Any]:
    try:
        from tools.tradingview_market_data import get_analyst_recommendations as _get_ar
        return _get_ar(symbol)
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}
