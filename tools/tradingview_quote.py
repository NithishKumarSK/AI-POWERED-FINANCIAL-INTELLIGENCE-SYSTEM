"""
TradingView Quote Tools
Get detailed quote information including bid/ask, volume, market cap, etc.
"""

import os
import requests
from typing import Dict, Any, List
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


def get_quote(symbol: str) -> Dict[str, Any]:
    """
    Get detailed quote data for a single symbol.
    
    Args:
        symbol (str): Stock/crypto/forex symbol (e.g., "AAPL", "BTCUSD")
    
    Returns:
        dict: Detailed quote data including bid, ask, volume, market cap, etc.
    """
    try:
        # Format symbol with exchange prefix
        formatted_symbol = format_symbol(symbol)
        
        url = f"{BASE_URL}/api/quote/{formatted_symbol}"
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
            "message": f"Error fetching quote data: {str(e)}"
        }


def get_batch_quotes(symbols: List[str]) -> Dict[str, Any]:
    """
    Get detailed quote data for multiple symbols in a single request.
    
    Args:
        symbols (list): List of symbols (e.g., ["AAPL", "MSFT", "GOOGL"])
    
    Returns:
        dict: Batch quote data for all symbols
    """
    try:
        # Format symbols with exchange prefixes
        formatted_symbols = [format_symbol(symbol) for symbol in symbols]
        
        url = f"{BASE_URL}/api/quote/batch"
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": API_KEY
        }
        
        # According to API documentation, batch format should be:
        # {"symbols":["NASDAQ:AAPL","NYSE:TSLA","BINANCE:BTCUSDT"]}
        payload = {"symbols": formatted_symbols}
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "symbols": symbols,
                "formatted_symbols": formatted_symbols,
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
            "message": f"Error fetching batch quotes: {str(e)}"
        }


if __name__ == "__main__":
    # Test the functions
    print("Testing TradingView Quote Tools...")
    
    # Test single quote
    result = get_quote("AAPL")
    print(f"Single Quote Status: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Data keys: {list(result['data'].keys())}")
    
    # Test batch quotes
    batch_result = get_batch_quotes(["AAPL", "MSFT", "GOOGL"])
    print(f"\nBatch Quote Status: {batch_result['status']}")
    if batch_result['status'] == 'SUCCESS':
        print(f"Data keys: {list(batch_result['data'].keys())}")