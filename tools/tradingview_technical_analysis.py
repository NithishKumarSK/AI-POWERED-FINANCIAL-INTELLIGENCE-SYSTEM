"""
TradingView Technical Analysis Tools
Get professional technical analysis indicators and signals
"""

import os
import requests
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://tradingview-data1.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")


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
        # For crypto, forex, etc., this might need adjustment
        return f"NASDAQ:{symbol}"


def get_technical_analysis(symbol: str) -> Dict[str, Any]:
    """
    Get comprehensive technical analysis for a symbol including signals, indicators, and recommendations.
    
    Args:
        symbol (str): Stock/crypto/forex symbol (e.g., "AAPL", "BTCUSD")
    
    Returns:
        dict: Technical analysis data with buy/sell signals and indicators
    """
    try:
        # Format symbol with exchange prefix
        formatted_symbol = format_symbol(symbol)
        
        url = f"{BASE_URL}/api/ta/{formatted_symbol}"
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
                "formatted_symbol": formatted_symbol,
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
            "message": f"Error fetching technical analysis: {str(e)}"
        }


def get_technical_indicators(symbol: str) -> Dict[str, Any]:
    """
    Get detailed technical indicators for a symbol (RSI, MACD, Moving Averages, etc.).
    
    Args:
        symbol (str): Stock/crypto/forex symbol (e.g., "AAPL", "BTCUSD")
    
    Returns:
        dict: Detailed technical indicators data
    """
    try:
        # Format symbol with exchange prefix
        formatted_symbol = format_symbol(symbol)
        
        url = f"{BASE_URL}/api/ta/{formatted_symbol}/indicators"
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
                "formatted_symbol": formatted_symbol,
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
            "message": f"Error fetching technical indicators: {str(e)}"
        }


if __name__ == "__main__":
    # Test the functions
    print("Testing TradingView Technical Analysis Tools...")
    
    # Test technical analysis
    result = get_technical_analysis("AAPL")
    print(f"Technical Analysis Status: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Data keys: {list(result['data'].keys())}")
    
    # Test technical indicators
    indicators_result = get_technical_indicators("AAPL")
    print(f"\nTechnical Indicators Status: {indicators_result['status']}")
    if indicators_result['status'] == 'SUCCESS':
        print(f"Data keys: {list(indicators_result['data'].keys())}")