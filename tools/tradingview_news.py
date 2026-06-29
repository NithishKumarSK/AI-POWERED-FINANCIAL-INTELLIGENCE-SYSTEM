"""TradingView News — mapped to trading-view.p.rapidapi.com /news/list."""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))
from rapidapi_client import rapidapi_get


def _fetch_news_list(symbol: Optional[str] = None, lang: str = "en") -> Dict[str, Any]:
    """Fetch news from /news/list. Symbol filter is optional."""
    params: Dict[str, Any] = {"lang": lang}
    if symbol:
        params["symbol"] = symbol.upper()
    result = rapidapi_get("/news/list", params=params, timeout=20)
    if result["status"] != "SUCCESS":
        return result
    articles: List[Dict] = result["data"] if isinstance(result["data"], list) else []
    return {
        "status": "SUCCESS",
        "data": articles,
        "count": len(articles),
        "symbol": symbol,
    }


def _filter_by_symbol(articles: List[Dict], symbol: str) -> List[Dict]:
    """Filter news items that mention symbol in relatedSymbols."""
    sym_upper = symbol.upper()
    matched = []
    for item in articles:
        related = item.get("relatedSymbols", [])
        if isinstance(related, list):
            if any(sym_upper in str(r.get("symbol", "")).upper() for r in related):
                matched.append(item)
    return matched


def get_stock_news(symbol: str) -> Dict[str, Any]:
    """Get news for a specific stock symbol, filtered from the general feed."""
    result = _fetch_news_list(symbol=None, lang="en")
    if result["status"] != "SUCCESS":
        return result
    articles = result.get("data", [])
    filtered = _filter_by_symbol(articles, symbol)
    # If no symbol-specific articles found, return general news (still useful for sentiment)
    chosen = filtered if filtered else articles[:20]
    return {
        "status": "SUCCESS",
        "data": chosen,
        "count": len(chosen),
        "symbol": symbol,
        "filtered": len(filtered) > 0,
    }


def get_stock_market_news() -> Dict[str, Any]:
    """Get general stock market news."""
    result = _fetch_news_list(lang="en")
    if result["status"] != "SUCCESS":
        return result
    articles = result.get("data", [])
    return {
        "status": "SUCCESS",
        "data": articles[:50],
        "count": min(len(articles), 50),
        "market": "stock",
    }


# --- Legacy aliases ---

def get_news(symbol: Optional[str] = None, market: str = "stock", lang: str = "en") -> Dict[str, Any]:
    if symbol:
        return get_stock_news(symbol)
    return get_stock_market_news()


def get_tradingview_news(symbol: Optional[str] = None, market: str = "stock",
                         lang: str = "en") -> Dict[str, Any]:
    return get_news(symbol, market, lang)


def _not_mapped(label: str) -> Dict[str, Any]:
    return {"status": "ERROR", "error_type": "ENDPOINT_NOT_MAPPED",
            "message": f"{label} not available on trading-view.p.rapidapi.com"}


def get_crypto_news() -> Dict[str, Any]:
    return _not_mapped("Crypto-specific news")


def get_forex_news() -> Dict[str, Any]:
    return _not_mapped("Forex news")


def get_futures_news() -> Dict[str, Any]:
    return _not_mapped("Futures news")


def get_bond_news() -> Dict[str, Any]:
    return _not_mapped("Bond news")


def get_etf_news() -> Dict[str, Any]:
    return _not_mapped("ETF news")


def get_economic_news() -> Dict[str, Any]:
    return _not_mapped("Economic news")


def get_index_news() -> Dict[str, Any]:
    return _not_mapped("Index news")


def get_news_details(news_id: str = "", **kwargs) -> Dict[str, Any]:
    return _not_mapped("News details endpoint")
