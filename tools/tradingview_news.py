"""
TradingView News Tool
Fetches financial news using TradingView API
"""

import os
import requests
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()


def get_news(symbol: str = None, market: str = "stock", lang: str = "en") -> Dict[str, Any]:
    """
    Alias for get_tradingview_news for backward compatibility.
    
    Args:
        symbol (str): Trading pair symbol (optional)
        market (str): Market type (stock/crypto/forex/futures/bond/etf)
        lang (str): Language code (en/zh-Hans/ja)
    
    Returns:
        dict: News data with status and articles
    """
    return get_tradingview_news(symbol, market, lang)


def get_tradingview_news(symbol: str = None, market: str = "stock", lang: str = "en") -> Dict[str, Any]:
    """
    Get financial news from TradingView API.
    
    Args:
        symbol (str): Trading pair symbol (optional)
        market (str): Market type (stock/crypto/forex/futures/bond/etf)
        lang (str): Language code (en/zh-Hans/ja)
    
    Returns:
        dict: News data with status and articles
    """
    try:
        api_key = os.getenv("RAPIDAPI_KEY")
        
        if not api_key:
            return {
                "status": "ERROR",
                "message": "RAPIDAPI_KEY not found in environment variables"
            }
        
        url = "https://tradingview-data1.p.rapidapi.com/api/news"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": api_key
        }
        
        params = {}
        # Format symbol with exchange prefix if provided
        if symbol:
            # Import format_symbol function
            from tools.tradingview_price import format_symbol
            formatted_symbol = format_symbol(symbol)
            params["symbol"] = formatted_symbol
        # Only add market parameter if no symbol is provided
        elif market:
            params["market"] = market
        if lang:
            params["lang"] = lang
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "data": data,
                "symbol": symbol,
                "formatted_symbol": formatted_symbol if symbol else None,
                "market": market
            }
        else:
            return {
                "status": "ERROR",
                "message": f"API request failed with status {response.status_code}",
                "response": response.text
            }
            
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Error fetching TradingView news: {str(e)}"
        }


def get_stock_news(symbol: str) -> Dict[str, Any]:
    """
    Get news for a specific stock symbol.
    
    Args:
        symbol (str): Stock symbol (e.g., AAPL, TSLA)
    
    Returns:
        dict: News data for the stock
    """
    # Use the format_symbol function to get the correct TradingView format
    from tools.tradingview_price import format_symbol
    formatted_symbol = format_symbol(symbol)
    # Call with only symbol and lang, matching the curl format exactly
    return get_tradingview_news(symbol=formatted_symbol, lang="en")


def get_stock_market_news() -> Dict[str, Any]:
    """
    Get stock market news using the dedicated endpoint.
    
    Returns:
        dict: Stock market news data
    """
    try:
        api_key = os.getenv("RAPIDAPI_KEY")
        if not api_key:
            return {"status": "ERROR", "message": "RAPIDAPI_KEY not found"}
        
        url = "https://tradingview-data1.p.rapidapi.com/api/news/stock"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": api_key
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "data": data,
                "market": "stock"
            }
        else:
            return {
                "status": "ERROR",
                "message": f"API request failed with status {response.status_code}",
                "response": response.text
            }
    except Exception as e:
        return {"status": "ERROR", "message": f"Error fetching stock news: {str(e)}"}


def get_crypto_news() -> Dict[str, Any]:
    """
    Get cryptocurrency news using the dedicated endpoint.
    
    Returns:
        dict: Crypto news data
    """
    try:
        api_key = os.getenv("RAPIDAPI_KEY")
        if not api_key:
            return {"status": "ERROR", "message": "RAPIDAPI_KEY not found"}
        
        url = "https://tradingview-data1.p.rapidapi.com/api/news/crypto"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": api_key
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "data": data,
                "market": "crypto"
            }
        else:
            return {
                "status": "ERROR",
                "message": f"API request failed with status {response.status_code}",
                "response": response.text
            }
    except Exception as e:
        return {"status": "ERROR", "message": f"Error fetching crypto news: {str(e)}"}


def get_forex_news() -> Dict[str, Any]:
    """
    Get forex market news using the dedicated endpoint.
    
    Returns:
        dict: Forex news data
    """
    try:
        api_key = os.getenv("RAPIDAPI_KEY")
        if not api_key:
            return {"status": "ERROR", "message": "RAPIDAPI_KEY not found"}
        
        url = "https://tradingview-data1.p.rapidapi.com/api/news/forex"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": api_key
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "data": data,
                "market": "forex"
            }
        else:
            return {
                "status": "ERROR",
                "message": f"API request failed with status {response.status_code}",
                "response": response.text
            }
    except Exception as e:
        return {"status": "ERROR", "message": f"Error fetching forex news: {str(e)}"}


def get_futures_news() -> Dict[str, Any]:
    """
    Get futures market news using the dedicated endpoint.
    
    Returns:
        dict: Futures news data
    """
    try:
        api_key = os.getenv("RAPIDAPI_KEY")
        if not api_key:
            return {"status": "ERROR", "message": "RAPIDAPI_KEY not found"}
        
        url = "https://tradingview-data1.p.rapidapi.com/api/news/futures"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": api_key
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "data": data,
                "market": "futures"
            }
        else:
            return {
                "status": "ERROR",
                "message": f"API request failed with status {response.status_code}",
                "response": response.text
            }
    except Exception as e:
        return {"status": "ERROR", "message": f"Error fetching futures news: {str(e)}"}


def get_bond_news() -> Dict[str, Any]:
    """
    Get bond market news using the dedicated endpoint.
    
    Returns:
        dict: Bond news data
    """
    try:
        api_key = os.getenv("RAPIDAPI_KEY")
        if not api_key:
            return {"status": "ERROR", "message": "RAPIDAPI_KEY not found"}
        
        url = "https://tradingview-data1.p.rapidapi.com/api/news/bond"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": api_key
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "data": data,
                "market": "bond"
            }
        else:
            return {
                "status": "ERROR",
                "message": f"API request failed with status {response.status_code}",
                "response": response.text
            }
    except Exception as e:
        return {"status": "ERROR", "message": f"Error fetching bond news: {str(e)}"}


def get_etf_news() -> Dict[str, Any]:
    """
    Get ETF news using the dedicated endpoint.
    
    Returns:
        dict: ETF news data
    """
    try:
        api_key = os.getenv("RAPIDAPI_KEY")
        if not api_key:
            return {"status": "ERROR", "message": "RAPIDAPI_KEY not found"}
        
        url = "https://tradingview-data1.p.rapidapi.com/api/news/etf"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": api_key
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "data": data,
                "market": "etf"
            }
        else:
            return {
                "status": "ERROR",
                "message": f"API request failed with status {response.status_code}",
                "response": response.text
            }
    except Exception as e:
        return {"status": "ERROR", "message": f"Error fetching ETF news: {str(e)}"}


def get_economic_news() -> Dict[str, Any]:
    """
    Get economic news using the dedicated endpoint.
    
    Returns:
        dict: Economic news data
    """
    try:
        api_key = os.getenv("RAPIDAPI_KEY")
        if not api_key:
            return {"status": "ERROR", "message": "RAPIDAPI_KEY not found"}
        
        url = "https://tradingview-data1.p.rapidapi.com/api/news/economic"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": api_key
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "data": data,
                "market": "economic"
            }
        else:
            return {
                "status": "ERROR",
                "message": f"API request failed with status {response.status_code}",
                "response": response.text
            }
    except Exception as e:
        return {"status": "ERROR", "message": f"Error fetching economic news: {str(e)}"}


def get_index_news() -> Dict[str, Any]:
    """
    Get index news using the dedicated endpoint.
    
    Returns:
        dict: Index news data
    """
    try:
        api_key = os.getenv("RAPIDAPI_KEY")
        if not api_key:
            return {"status": "ERROR", "message": "RAPIDAPI_KEY not found"}
        
        url = "https://tradingview-data1.p.rapidapi.com/api/news/index"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": api_key
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "data": data,
                "market": "index"
            }
        else:
            return {
                "status": "ERROR",
                "message": f"API request failed with status {response.status_code}",
                "response": response.text
            }
    except Exception as e:
        return {"status": "ERROR", "message": f"Error fetching index news: {str(e)}"}


def get_news_details(news_id: str) -> Dict[str, Any]:
    """
    Get detailed news for a specific news ID.
    
    Args:
        news_id (str): The ID of the news article
    
    Returns:
        dict: Detailed news data
    """
    try:
        api_key = os.getenv("RAPIDAPI_KEY")
        if not api_key:
            return {"status": "ERROR", "message": "RAPIDAPI_KEY not found"}
        
        url = f"https://tradingview-data1.p.rapidapi.com/api/news/{news_id}"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": api_key
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "data": data,
                "news_id": news_id
            }
        else:
            return {
                "status": "ERROR",
                "message": f"API request failed with status {response.status_code}",
                "response": response.text
            }
    except Exception as e:
        return {"status": "ERROR", "message": f"Error fetching news details: {str(e)}"}


if __name__ == "__main__":
    # Test the news function
    print("Testing TradingView News Tool...")
    
    # Test general news
    result = get_tradingview_news()
    print(f"General news: {result['status']}, {result.get('count', 0)} articles")
    
    # Test stock news
    stock_result = get_stock_news("AAPL")
    print(f"AAPL news: {stock_result['status']}, {stock_result.get('count', 0)} articles")