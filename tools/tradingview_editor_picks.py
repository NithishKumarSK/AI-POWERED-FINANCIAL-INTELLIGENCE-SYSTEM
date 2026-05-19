"""
TradingView Editor Picks Tool
Fetches editor picks and recommended content from TradingView analysts
"""

import os
import requests
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://tradingview-data1.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")


def get_editor_picks(page: int = 1, lang: str = "en") -> Dict[str, Any]:
    """
    Get TradingView editor picks using the exact API format.
    
    Args:
        page (int): Page number (default: 1)
        lang (str): Language code (default: 'en')
    
    Returns:
        dict: Editor picks data
    """
    try:
        url = f"{BASE_URL}/api/ideas/editors-picks"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": API_KEY
        }
        params = {
            "page": page,
            "lang": lang
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "page": page,
                "lang": lang,
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
            "message": f"Error fetching editor picks: {str(e)}"
        }


def get_editor_picks_by_symbol(symbol: str, page: int = 1, lang: str = "en") -> Dict[str, Any]:
    """
    Get editor picks filtered by symbol.
    
    Args:
        symbol (str): Stock symbol to filter picks
        page (int): Page number (default: 1)
        lang (str): Language code (default: 'en')
    
    Returns:
        dict: Editor picks data for specific symbol
    """
    try:
        url = f"{BASE_URL}/api/ideas/editors-picks"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": API_KEY
        }
        params = {
            "page": page,
            "lang": lang,
            "symbol": symbol
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "symbol": symbol,
                "page": page,
                "lang": lang,
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
            "message": f"Error fetching editor picks for symbol: {str(e)}"
        }


def get_trending_editor_picks(page: int = 1, lang: str = "en") -> Dict[str, Any]:
    """
    Get trending editor picks.
    
    Args:
        page (int): Page number (default: 1)
        lang (str): Language code (default: 'en')
    
    Returns:
        dict: Trending editor picks data
    """
    return get_editor_picks(page, lang)


def get_top_editor_picks(count: int = 10, lang: str = "en") -> Dict[str, Any]:
    """
    Get top editor picks by fetching multiple pages.
    
    Args:
        count (int): Number of picks to return
        lang (str): Language code (default: 'en')
    
    return:
        dict: Top editor picks
    """
    return get_editor_picks(page=1, lang=lang)


if __name__ == "__main__":
    # Test the functions
    print("Testing TradingView Editor Picks Tool...")
    
    # Test editor picks
    result = get_editor_picks()
    print(f"Editor Picks Status: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Data keys: {list(result['data'].keys())}")
    
    # Test by symbol
    symbol_result = get_editor_picks_by_symbol("AAPL")
    print(f"\nAAPL Editor Picks Status: {symbol_result['status']}")
    if symbol_result['status'] == 'SUCCESS':
        print(f"Data keys: {list(symbol_result['data'].keys())}")