"""TradingView Leaderboards — mapped to trading-view.p.rapidapi.com /market/get-movers."""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(__file__))
from rapidapi_client import rapidapi_get, get_rapidapi_base_url


def _parse_movers(raw: Dict[str, Any], label: str) -> Dict[str, Any]:
    """Convert /market/get-movers response to a normalised dict."""
    fields: List[str] = raw.get("fields", [])
    symbols: List[Dict] = raw.get("symbols", [])
    items = []
    for sym in symbols:
        ticker = sym.get("s", "")
        values = sym.get("f", [])
        entry: Dict[str, Any] = {"symbol": ticker}
        for i, field in enumerate(fields):
            entry[field] = values[i] if i < len(values) else None
        items.append(entry)
    return {
        "status": "SUCCESS",
        "label": label,
        "total": raw.get("totalCount", len(items)),
        "items": items,
        "data": {"items": items},
    }


def _get_movers(name: str, exchange: str = "US", locale: str = "en") -> Dict[str, Any]:
    result = rapidapi_get(
        "/market/get-movers",
        params={"exchange": exchange, "name": name, "locale": locale},
        timeout=20,
    )
    if result["status"] != "SUCCESS":
        return result
    return _parse_movers(result["data"], name)


def get_stock_gainers(market_code: str = "america", count: int = 10) -> Dict[str, Any]:
    return _get_movers("percent_change_gainers")


def get_stock_losers(market_code: str = "america", count: int = 10) -> Dict[str, Any]:
    return _get_movers("percent_change_losers")


def get_most_active_stocks(market_code: str = "america", count: int = 10) -> Dict[str, Any]:
    return _get_movers("volume_gainers")


# --- Legacy wrappers kept so existing imports don't break ---

def get_leaderboard(category: str = "stocks", tab: str = "all_stocks",
                    market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    tab_map = {
        "gainers": "percent_change_gainers",
        "losers": "percent_change_losers",
        "active": "volume_gainers",
        "volume_gainers": "volume_gainers",
        "percent_change_gainers": "percent_change_gainers",
        "percent_change_losers": "percent_change_losers",
    }
    name = tab_map.get(tab, "volume_gainers")
    return _get_movers(name)


def get_leaderboards(category: str = "stocks", tab: str = "all_stocks",
                     market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    return get_leaderboard(category, tab, market_code, count)


def get_trending_stocks(tab: str = "all_stocks", market_code: str = "america",
                        count: int = 20) -> Dict[str, Any]:
    return get_most_active_stocks(market_code, count)


def get_trending_crypto(tab: str = "all_stocks", market_code: str = "america",
                        count: int = 20) -> Dict[str, Any]:
    return {"status": "ERROR", "error_type": "ENDPOINT_NOT_MAPPED",
            "message": "Crypto movers not available on trading-view.p.rapidapi.com"}


def get_trending_indices(tab: str = "all_stocks", market_code: str = "america",
                         count: int = 20) -> Dict[str, Any]:
    return {"status": "ERROR", "error_type": "ENDPOINT_NOT_MAPPED",
            "message": "Indices movers not available on trading-view.p.rapidapi.com"}


def get_trending_etfs(tab: str = "all_stocks", market_code: str = "america",
                      count: int = 20) -> Dict[str, Any]:
    return {"status": "ERROR", "error_type": "ENDPOINT_NOT_MAPPED",
            "message": "ETF movers not available on trading-view.p.rapidapi.com"}


def get_crypto_leaderboard(**kwargs) -> Dict[str, Any]:
    return {"status": "ERROR", "error_type": "ENDPOINT_NOT_MAPPED",
            "message": "Not available on trading-view.p.rapidapi.com"}


def get_forex_leaderboard(**kwargs) -> Dict[str, Any]:
    return {"status": "ERROR", "error_type": "ENDPOINT_NOT_MAPPED",
            "message": "Not available on trading-view.p.rapidapi.com"}


def get_futures_leaderboard(**kwargs) -> Dict[str, Any]:
    return {"status": "ERROR", "error_type": "ENDPOINT_NOT_MAPPED",
            "message": "Not available on trading-view.p.rapidapi.com"}


def get_indices_leaderboard(**kwargs) -> Dict[str, Any]:
    return {"status": "ERROR", "error_type": "ENDPOINT_NOT_MAPPED",
            "message": "Not available on trading-view.p.rapidapi.com"}


def get_bonds_leaderboard(**kwargs) -> Dict[str, Any]:
    return {"status": "ERROR", "error_type": "ENDPOINT_NOT_MAPPED",
            "message": "Not available on trading-view.p.rapidapi.com"}


def get_corporate_bonds_leaderboard(**kwargs) -> Dict[str, Any]:
    return {"status": "ERROR", "error_type": "ENDPOINT_NOT_MAPPED",
            "message": "Not available on trading-view.p.rapidapi.com"}


def get_etf_leaderboard(**kwargs) -> Dict[str, Any]:
    return {"status": "ERROR", "error_type": "ENDPOINT_NOT_MAPPED",
            "message": "Not available on trading-view.p.rapidapi.com"}


def get_leaderboard_data(config_id: str) -> Dict[str, Any]:
    return {"status": "ERROR", "error_type": "ENDPOINT_NOT_MAPPED",
            "message": "Not available on trading-view.p.rapidapi.com"}
