"""
TradingView Community Ideas Tools
Access TradingView community trading ideas, market sentiment, and expert analysis
"""

import os
import requests
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://tradingview-data1.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")


def get_community_data(symbol: str = None) -> Dict[str, Any]:
    """
    Get community data for a symbol or general community data.
    
    Args:
        symbol (str): Stock symbol (optional)
    
    Returns:
        dict: Community data
    """
    if symbol:
        return get_symbol_ideas(symbol)
    else:
        return get_hot_ideas()


def get_hot_ideas() -> Dict[str, Any]:
    """
    Get hot trading ideas from the TradingView community.
    
    Returns:
        dict: Hot trading ideas data
    """
    try:
        url = f"{BASE_URL}/api/ideas/hot"
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
            "message": f"Error fetching hot ideas: {str(e)}"
        }


def get_editors_picks() -> Dict[str, Any]:
    """
    Get editors' picks from TradingView.
    
    Returns:
        dict: Editors' picks data
    """
    try:
        url = f"{BASE_URL}/api/ideas/editors-picks"
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
            "message": f"Error fetching editors picks: {str(e)}"
        }


def get_symbol_ideas(symbol: str) -> Dict[str, Any]:
    """
    Get trading ideas for a specific symbol.
    
    Args:
        symbol (str): Stock symbol (e.g., "AAPL")
    
    Returns:
        dict: Trading ideas for the symbol
    """
    try:
        # Format symbol with exchange prefix
        from tools.tradingview_price import format_symbol
        formatted_symbol = format_symbol(symbol)
        
        # According to API documentation: GET /api/ideas/{symbol}
        url = f"{BASE_URL}/api/ideas/{formatted_symbol}"
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
            "message": f"Error fetching symbol ideas: {str(e)}"
        }


if __name__ == "__main__":
    # Test the functions
    print("Testing TradingView Community Tools...")
    
    # Test hot ideas
    result = get_hot_ideas()
    print(f"Hot Ideas Status: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Data keys: {list(result['data'].keys())}")
    
    # Test symbol ideas
    symbol_result = get_symbol_ideas("AAPL")
    print(f"\nSymbol Ideas Status: {symbol_result['status']}")
    if symbol_result['status'] == 'SUCCESS':
        print(f"Data keys: {list(symbol_result['data'].keys())}")