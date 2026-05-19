"""
TradingView Market Data Tools
Get comprehensive market data including company info, financials, dividends, analyst recommendations
"""

import os
import requests
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://tradingview-data1.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")


def get_market_data(symbol: str, endpoint: str = "") -> Dict[str, Any]:
    """
    Get market data for a symbol with various endpoints.
    
    Args:
        symbol (str): Stock symbol (e.g., "AAPL")
        endpoint (str): Specific endpoint (company, ipo, indicators, ttm, current, 
                       financials-quarterly, financials-annual, history-quarterly, 
                       history-annual, dividend, analyst-recommendations, enterprise-value, 
                       credit-ratings, cash-flow)
    
    Returns:
        dict: Market data for the specified endpoint
    """
    try:
        url = f"{BASE_URL}/api/market-data/{symbol}"
        if endpoint:
            url += f"/{endpoint}"
        
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": API_KEY
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "symbol": symbol,
                "endpoint": endpoint,
                "data": data
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
            "message": f"Error fetching market data: {str(e)}"
        }


def get_market_data_exact(symbol: str, exchange: str = "NASDAQ") -> Dict[str, Any]:
    """
    Get market data for a symbol using exact API format with exchange prefix.
    Matches curl format: /api/market-data/NASDAQ:AAPL
    
    Args:
        symbol (str): Stock symbol (e.g., "AAPL")
        exchange (str): Exchange prefix (default: "NASDAQ", also "NYSE", etc.)
    
    Returns:
        dict: Market data for the specified symbol with exchange prefix
    """
    try:
        # Exact format from curl: /api/market-data/NASDAQ:AAPL
        url = f"{BASE_URL}/api/market-data/{exchange}:{symbol}"
        
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": API_KEY
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "symbol": symbol,
                "exchange": exchange,
                "full_symbol": f"{exchange}:{symbol}",
                "data": data
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
            "message": f"Error fetching market data: {str(e)}"
        }


def get_company_info(symbol: str) -> Dict[str, Any]:
    """Get company profile and information."""
    return get_market_data(symbol, "company")


def get_financials_annual(symbol: str) -> Dict[str, Any]:
    """Get annual financial statements."""
    return get_market_data(symbol, "financials-annual")


def get_financials_quarterly(symbol: str) -> Dict[str, Any]:
    """Get quarterly financial statements."""
    return get_market_data(symbol, "financials-quarterly")


def get_dividend_info(symbol: str) -> Dict[str, Any]:
    """Get dividend information and history."""
    return get_market_data(symbol, "dividend")


def get_analyst_recommendations(symbol: str) -> Dict[str, Any]:
    """Get analyst recommendations and price targets."""
    return get_market_data(symbol, "analyst-recommendations")


def get_current_metrics(symbol: str) -> Dict[str, Any]:
    """Get current market metrics and ratios."""
    return get_market_data(symbol, "current")


def get_market_data_multi_exchange(symbol: str, exchanges: list = ["NASDAQ", "NYSE"]) -> Dict[str, Any]:
    """
    Try multiple exchanges for a symbol and return the first successful result.
    
    Args:
        symbol (str): Stock symbol (e.g., "AAPL")
        exchanges (list): List of exchanges to try (default: ["NASDAQ", "NYSE"])
    
    Returns:
        dict: Market data from the first successful exchange
    """
    for exchange in exchanges:
        result = get_market_data_exact(symbol, exchange)
        if result['status'] == 'SUCCESS':
            return result
    
    return {
        "status": "ERROR",
        "message": f"No successful response from any exchange. Tried: {exchanges}"
    }


if __name__ == "__main__":
    # Test the functions
    print("Testing TradingView Market Data Tools...")
    
    # Test exact format (new function matching curl)
    print("\n=== Testing Exact Format (NASDAQ:AAPL) ===")
    exact_result = get_market_data_exact("AAPL", "NASDAQ")
    print(f"Status: {exact_result['status']}")
    if exact_result['status'] == 'SUCCESS':
        print(f"Full Symbol: {exact_result['full_symbol']}")
        print(f"Data keys: {list(exact_result['data'].keys())}")
        print(f"Sample data: {str(exact_result['data'])[:500]}")
    else:
        print(f"Error: {exact_result['message']}")
    
    # Test multi-exchange
    print("\n=== Testing Multi-Exchange ===")
    multi_result = get_market_data_multi_exchange("AAPL")
    print(f"Status: {multi_result['status']}")
    if multi_result['status'] == 'SUCCESS':
        print(f"Full Symbol: {multi_result['full_symbol']}")
        print(f"Data keys: {list(multi_result['data'].keys())}")
    else:
        print(f"Error: {multi_result['message']}")
    
    # Test company info (original format)
    print("\n=== Testing Company Info (Original Format) ===")
    result = get_company_info("AAPL")
    print(f"Status: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Data keys: {list(result['data'].keys())}")
    else:
        print(f"Error: {result['message']}")
    
    # Test analyst recommendations
    print("\n=== Testing Analyst Recommendations ===")
    analyst_result = get_analyst_recommendations("AAPL")
    print(f"Status: {analyst_result['status']}")
    if analyst_result['status'] == 'SUCCESS':
        print(f"Data keys: {list(analyst_result['data'].keys())}")
    else:
        print(f"Error: {analyst_result['message']}")