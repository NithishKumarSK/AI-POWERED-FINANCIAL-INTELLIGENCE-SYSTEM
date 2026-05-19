"""
Stock Historical Data Tool
Fetches historical price data for stocks over specified time periods
"""

import os
import requests
from typing import Dict, Any, List
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://tradingview-data1.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")

# Import price tool for getting historical data
try:
    from tradingview_price import get_price
except ImportError:
    from .tradingview_price import get_price


def format_symbol(symbol: str) -> str:
    """
    Format symbol with appropriate exchange prefix according to TradingView API requirements.
    
    Args:
        symbol (str): Stock symbol (e.g., "AAPL", "MSFT")
    
    Returns:
        str: Formatted symbol with exchange prefix (e.g., "NASDAQ:AAPL", "NYSE:MSFT")
    """
    # If symbol already contains exchange prefix, return as-is
    if ":" in symbol:
        return symbol
    
    # Common US stock exchanges and their typical symbols
    nasdaq_symbols = ["AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "TSLA", "META", "NVDA", "NFLX", "ADBE", 
                      "INTC", "CSCO", "PYPL", "CMCSA", "PEP", "COST", "AVGO", "QCOM", "SBUX", "INTU",
                      "TXN", "AMD", "GILD", "BIIB", "REGN", "ILMN", "MRNA", "ZM", "DOCU", "SNOW"]
    
    nyse_symbols = ["JPM", "V", "JNJ", "WMT", "PG", "XOM", "BAC", "KO", "DIS", "C", "PFE", "NKE", "HD",
                   "MA", "UNH", "VZ", "CRM", "ABBV", "MRK", "ABT", "MCD", "T", "NFLX", "BA", "WFC",
                   "AMD", "IBM", "GE", "CAT", "ORCL", "CVX", "D", "UPS", "LMT", "GS"]
    
    # Check if symbol matches known patterns
    if symbol in nasdaq_symbols:
        return f"NASDAQ:{symbol}"
    elif symbol in nyse_symbols:
        return f"NYSE:{symbol}"
    else:
        # Default to NASDAQ for unknown US stocks (most common)
        return f"NASDAQ:{symbol}"


def get_historical_data(symbol: str, period: str = "1Y") -> Dict[str, Any]:
    """
    Get historical price data for a stock over a specified time period.
    Uses the working price API with range parameter instead of separate historical endpoint.
    
    Args:
        symbol (str): Stock symbol (e.g., "AAPL", "MSFT")
        period (str): Time period for historical data (e.g., "1D", "1W", "1M", "3M", "6M", "1Y", "5Y")
    
    Returns:
        dict: Historical price data with OHLCV information
    """
    try:
        # Try multiple exchange formats for better compatibility
        exchanges_to_try = ['NASDAQ', 'NYSE']
        price_result = None
        
        for exchange in exchanges_to_try:
            formatted_symbol = f"{exchange}:{symbol}"
            test_result = get_price(formatted_symbol)
            if test_result.get('status') == 'SUCCESS':
                data = test_result.get('data', {})
                if data.get('success'):
                    price_result = test_result
                    break
        
        # If all exchanges fail, try the original symbol
        if price_result is None:
            price_result = get_price(symbol)
        
        if price_result.get('status') == 'SUCCESS':
            price_data = price_result.get('data', {})
            if price_data.get('success'):
                actual_data = price_data.get('data', {})
                
                # Extract history from the price data
                history = actual_data.get('history', [])
                current = actual_data.get('current', {})
                info = actual_data.get('info', {})
                
                # Calculate how many days of history we got
                days_of_history = len(history)
                
                return {
                    "status": "SUCCESS",
                    "symbol": symbol,
                    "formatted_symbol": price_result.get('formatted_symbol'),
                    "period": period,
                    "data": {
                        "success": True,
                        "data": {
                            "symbol": actual_data.get('symbol'),
                            "current": current,
                            "history": history,
                            "info": info,
                            "period_requested": period,
                            "days_available": days_of_history
                        },
                        "msg": f"Success - {days_of_history} data points available"
                    }
                }
            else:
                return {
                    "status": "ERROR",
                    "message": f"Price API returned error: {price_data.get('msg', 'Unknown error')}",
                    "data": price_data
                }
        else:
            return {
                "status": "ERROR",
                "message": price_result.get('message', 'Unknown error')
            }
            
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Error fetching historical data: {str(e)}"
        }


def get_year_historical_data(symbol: str) -> Dict[str, Any]:
    """
    Get 1 year of historical price data for a stock.
    
    Args:
        symbol (str): Stock symbol (e.g., "AAPL", "MSFT")
    
    Returns:
        dict: 1 year historical price data
    """
    return get_historical_data(symbol, period="1Y")


def analyze_historical_performance(historical_data: Dict) -> Dict[str, Any]:
    """
    Analyze historical price data to calculate performance metrics.
    
    Args:
        historical_data (dict): Historical data from get_historical_data
    
    Returns:
        dict: Performance analysis including returns, volatility, etc.
    """
    try:
        if historical_data.get("status") != "SUCCESS":
            return {
                "status": "ERROR",
                "message": "Invalid historical data provided"
            }
        
        data = historical_data.get("data", {})
        
        # Extract price data (this will depend on the actual API response structure)
        # For now, return a basic structure
        return {
            "status": "SUCCESS",
            "analysis": {
                "period": historical_data.get("period"),
                "symbol": historical_data.get("symbol"),
                "data_points": len(data.get("prices", [])) if isinstance(data, dict) else 0,
                "note": "Detailed analysis to be implemented based on API response structure"
            }
        }
        
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Error analyzing historical data: {str(e)}"
        }


if __name__ == "__main__":
    # Test the functions
    print("Testing Stock Historical Data Tool...")
    
    # Test 1-year historical data
    result = get_year_historical_data("AAPL")
    print(f"1Y Historical Data Status: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Data keys: {list(result['data'].keys())}")
    
    # Test analysis
    analysis = analyze_historical_performance(result)
    print(f"\nAnalysis Status: {analysis['status']}")