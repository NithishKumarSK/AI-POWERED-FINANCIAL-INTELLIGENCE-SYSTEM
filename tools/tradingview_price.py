"""
TradingView Price Data Tools
Get real-time and historical price data for stocks, crypto, forex, futures, bonds, and ETFs
"""

import os
import requests
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

# TradingView API base URL (using RapidAPI endpoint as provided)
BASE_URL = "https://tradingview-data1.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")


def validate_symbol(symbol: str) -> bool:
    """
    Validate if a symbol exists and returns data from TradingView API.
    
    Args:
        symbol (str): Stock symbol (e.g., "AAPL", "MSFT")
    
    Returns:
        bool: True if symbol is valid and returns data, False otherwise
    """
    try:
        formatted_symbol = format_symbol(symbol)
        url = f"{BASE_URL}/api/price/{formatted_symbol}"
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": API_KEY
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # Check if API returned actual data
            if data.get("success") and data.get("data"):
                nested_data = data.get("data", {})
                # Check if nested data has meaningful content with price data
                if nested_data and isinstance(nested_data, dict):
                    # Look for specific price fields that indicate real data
                    if nested_data.get("price") or nested_data.get("close") or nested_data.get("c"):
                        return True
                    # Also check if there's substantial data (more than empty structure)
                    if len(str(nested_data)) > 50:  # More substantial content
                        return True
        return False
    except Exception:
        return False


def normalize_ticker(symbol: str) -> str:
    """
    Normalize ticker symbol to handle common variations.
    
    Args:
        symbol (str): Stock symbol (e.g., "BRKB", "BRK.B")
    
    Returns:
        str: Normalized ticker symbol
    """
    # Common ticker normalizations
    normalizations = {
        "BRKB": "BRK.B",  # Berkshire Hathaway B
        "BRKA": "BRK.A",  # Berkshire Hathaway A
        # Add more as needed
    }
    
    # Remove any exchange prefix for normalization
    base_symbol = symbol.split(":")[-1].upper()
    
    # Apply normalization if exists
    return normalizations.get(base_symbol, base_symbol)


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
    
    # Normalize ticker first
    normalized = normalize_ticker(symbol)
    
    # Common US stock exchanges and their typical symbols
    nasdaq_symbols = ["AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "TSLA", "META", "NVDA", "NFLX", "ADBE", 
                      "INTC", "CSCO", "PYPL", "CMCSA", "PEP", "COST", "AVGO", "QCOM", "SBUX", "INTU",
                      "TXN", "AMD", "GILD", "BIIB", "REGN", "ILMN", "MRNA", "ZM", "DOCU", "SNOW"]
    
    nyse_symbols = ["JPM", "V", "JNJ", "WMT", "PG", "XOM", "BAC", "KO", "DIS", "C", "PFE", "NKE", "HD",
                   "MA", "UNH", "VZ", "CRM", "ABBV", "MRK", "ABT", "MCD", "T", "BA", "WFC",
                   "IBM", "GE", "CAT", "ORCL", "CVX", "D", "UPS", "LMT", "GS", "BRK.A", "BRK.B"]
    
    # ETFs typically trade on NYSE or ARCA
    etf_patterns = ["GLD", "SLV", "SGOV", "VTI", "VOO", "SPY", "IVV", "QQQ", "IWM", "EFA", "VWO", 
                   "BND", "VNQ", "XLF", "XLV", "XLU", "XLP", "XLE", "XLK", "XLB", "XLI"]
    
    # OTC/penny stocks (typically 4+ letters or ending in F/Y/Z)
    otc_patterns = ["FFXDF", "KIDZ", "QXO", "SIRI"]
    
    # Check if symbol matches known patterns (use normalized symbol)
    if normalized in nasdaq_symbols:
        return f"NASDAQ:{normalized}"
    elif normalized in nyse_symbols:
        return f"NYSE:{normalized}"
    elif normalized in etf_patterns:
        return f"AMEX:{normalized}"  # Most ETFs trade on AMEX
    elif normalized in otc_patterns:
        return f"OTC:{normalized}"  # OTC stocks
    elif len(normalized) > 4 or normalized.endswith(('F', 'Y', 'Z')):
        # Likely OTC stock
        return f"OTC:{normalized}"
    else:
        # Default to NASDAQ for unknown US stocks (most common)
        # For crypto, forex, etc., this might need adjustment
        return f"NASDAQ:{normalized}"


def get_price(symbol: str) -> Dict[str, Any]:
    """
    Get current price data for a single symbol.
    
    Args:
        symbol (str): Stock/crypto/forex symbol (e.g., "AAPL", "BTCUSD", "EURUSD")
    
    Returns:
        dict: Price data including current price, change, volume, etc.
    """
    try:
        # Format symbol with exchange prefix
        formatted_symbol = format_symbol(symbol)
        
        url = f"{BASE_URL}/api/price/{formatted_symbol}"
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
            "message": f"Error fetching price data: {str(e)}"
        }


def get_batch_prices(symbols: List[str]) -> Dict[str, Any]:
    """
    Get price data for multiple symbols in a single request.
    
    Args:
        symbols (list): List of symbols (e.g., ["AAPL", "MSFT", "GOOGL"])
    
    Returns:
        dict: Batch price data for all symbols
    """
    try:
        # Format symbols with exchange prefixes
        formatted_symbols = [format_symbol(symbol) for symbol in symbols]
        
        url = f"{BASE_URL}/api/price/batch"
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": API_KEY
        }
        
        # According to API documentation, batch format should be:
        # {"requests":[{"symbol":"BINANCE:BTCUSDT","timeframe":"60","range":20},{"symbol":"NASDAQ:AAPL","timeframe":"D","range":10}]}
        payload = {
            "requests": [
                {"symbol": formatted_symbol, "timeframe": "D", "range": 10}
                for formatted_symbol in formatted_symbols
            ]
        }
        
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
            "message": f"Error fetching batch prices: {str(e)}"
        }


if __name__ == "__main__":
    # Test the functions
    print("Testing TradingView Price Data Tools...")
    
    # Test single price
    result = get_price("AAPL")
    print(f"Single Price Status: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Data keys: {list(result['data'].keys())}")
    
    # Test batch prices
    batch_result = get_batch_prices(["AAPL", "MSFT", "GOOGL"])
    print(f"\nBatch Price Status: {batch_result['status']}")
    if batch_result['status'] == 'SUCCESS':
        print(f"Data keys: {list(batch_result['data'].keys())}")