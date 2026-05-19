"""
TradingView Leaderboards Tools
Discover trending stocks and market opportunities through comprehensive leaderboards
"""

import os
import requests
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://tradingview-data1.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")


def get_leaderboards(category: str = "stocks", tab: str = "all_stocks", market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    """
    Alias for get_leaderboard for backward compatibility.
    
    Args:
        category (str): Asset category (stocks, indices, crypto, futures, forex, bonds, corporate-bonds, etfs)
        tab (str): Tab ID (all_stocks, gainers, losers, etc.)
        market_code (str): Market code (e.g., america, china, japan, europe)
        count (int): Return count (max 150)
    
    Returns:
        dict: Leaderboard data with trending instruments
    """
    return get_leaderboard(category, tab, market_code, count)


def get_leaderboard(category: str, tab: str = "all_stocks", market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    """
    Get leaderboard for a specific asset category with required parameters.
    Updated to match exact API format.
    
    Args:
        category (str): Asset category (stocks, indices, crypto, futures, forex, bonds, corporate-bonds, etfs)
        tab (str): Tab ID (all_stocks, gainers, losers, large_cap, small_cap, largest_employers, high_dividend, highest_net_income, highest_cash, highest_profit_per_employee, highest_revenue_per_employee, active, unusual_volume, most_volatile, high_beta, best_performing, most_expensive, penny_stocks, overbought, oversold, ath, atl, 52wk_high, 52wk_low)
        market_code (str): Market code (e.g., america, china, japan, europe)
        count (int): Return count (max 150)
    
    Returns:
        dict: Leaderboard data with trending instruments
    """
    try:
        url = f"{BASE_URL}/api/leaderboard/{category}"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": API_KEY
        }
        params = {
            "tab": tab,
            "market_code": market_code,
            "count": count
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "category": category,
                "tab": tab,
                "market_code": market_code,
                "count": count,
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
            "message": f"Error fetching leaderboard: {str(e)}"
        }


def get_trending_stocks(tab: str = "all_stocks", market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    """Get trending stocks leaderboard."""
    return get_leaderboard("stocks", tab, market_code, count)


def get_trending_crypto(tab: str = "all_stocks", market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    """Get trending cryptocurrencies leaderboard."""
    return get_leaderboard("crypto", tab, market_code, count)


def get_trending_indices(tab: str = "all_stocks", market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    """Get trending indices leaderboard."""
    return get_leaderboard("indices", tab, market_code, count)


def get_trending_etfs(tab: str = "all_stocks", market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    """Get trending ETFs leaderboard."""
    return get_leaderboard("etfs", tab, market_code, count)


def get_stock_gainers(market_code: str = "america", count: int = 10) -> Dict[str, Any]:
    """Get top stock gainers."""
    return get_leaderboard("stocks", "gainers", market_code, count)


def get_stock_losers(market_code: str = "america", count: int = 10) -> Dict[str, Any]:
    """Get top stock losers."""
    return get_leaderboard("stocks", "losers", market_code, count)


def get_most_active_stocks(market_code: str = "america", count: int = 10) -> Dict[str, Any]:
    """Get most active stocks."""
    return get_leaderboard("stocks", "active", market_code, count)


def get_crypto_leaderboard(tab: str = "all_stocks", market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    """
    Get cryptocurrency leaderboard using dedicated endpoint.
    
    Args:
        tab (str): Tab ID (all_stocks, gainers, losers, active, etc.)
        market_code (str): Market code (e.g., america, global)
        count (int): Return count (max 150)
    
    Returns:
        dict: Crypto leaderboard data
    """
    return get_leaderboard("crypto", tab, market_code, count)


def get_forex_leaderboard(tab: str = "all_stocks", market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    """
    Get forex leaderboard using dedicated endpoint.
    
    Args:
        tab (str): Tab ID (all_stocks, gainers, losers, active, etc.)
        market_code (str): Market code (e.g., america, global)
        count (int): Return count (max 150)
    
    Returns:
        dict: Forex leaderboard data
    """
    return get_leaderboard("forex", tab, market_code, count)


def get_futures_leaderboard(tab: str = "all_stocks", market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    """
    Get futures leaderboard using dedicated endpoint.
    
    Args:
        tab (str): Tab ID (all_stocks, gainers, losers, active, etc.)
        market_code (str): Market code (e.g., america, global)
        count (int): Return count (max 150)
    
    Returns:
        dict: Futures leaderboard data
    """
    return get_leaderboard("futures", tab, market_code, count)


def get_indices_leaderboard(tab: str = "all_stocks", market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    """
    Get indices leaderboard using dedicated endpoint.
    
    Args:
        tab (str): Tab ID (all_stocks, gainers, losers, active, etc.)
        market_code (str): Market code (e.g., america, global)
        count (int): Return count (max 150)
    
    Returns:
        dict: Indices leaderboard data
    """
    return get_leaderboard("indices", tab, market_code, count)


def get_bonds_leaderboard(tab: str = "all_stocks", market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    """
    Get bonds leaderboard using dedicated endpoint.
    
    Args:
        tab (str): Tab ID (all_stocks, gainers, losers, active, etc.)
        market_code (str): Market code (e.g., america, global)
        count (int): Return count (max 150)
    
    Returns:
        dict: Bonds leaderboard data
    """
    return get_leaderboard("bonds", tab, market_code, count)


def get_corporate_bonds_leaderboard(tab: str = "all_stocks", market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    """
    Get corporate bonds leaderboard using dedicated endpoint.
    
    Args:
        tab (str): Tab ID (all_stocks, gainers, losers, active, etc.)
        market_code (str): Market code (e.g., america, global)
        count (int): Return count (max 150)
    
    Returns:
        dict: Corporate bonds leaderboard data
    """
    return get_leaderboard("corporate-bonds", tab, market_code, count)


def get_etf_leaderboard(tab: str = "all_stocks", market_code: str = "america", count: int = 20) -> Dict[str, Any]:
    """
    Get ETF leaderboard using dedicated endpoint.
    
    Args:
        tab (str): Tab ID (all_stocks, gainers, losers, active, etc.)
        market_code (str): Market code (e.g., america, global)
        count (int): Return count (max 150)
    
    Returns:
        dict: ETF leaderboard data
    """
    return get_leaderboard("etfs", tab, market_code, count)


def get_leaderboard_data(config_id: str) -> Dict[str, Any]:
    """
    Get leaderboard data by config ID (Legacy endpoint).
    
    Args:
        config_id (str): Configuration ID for the leaderboard
    
    Returns:
        dict: Leaderboard data for the specified config
    """
    try:
        url = f"{BASE_URL}/api/leaderboard/data"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": API_KEY
        }
        params = {
            "config": config_id
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "config_id": config_id,
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
            "message": f"Error fetching leaderboard data: {str(e)}"
        }


if __name__ == "__main__":
    # Test the functions
    print("Testing TradingView Leaderboards Tools...")
    
    # Test trending stocks
    result = get_trending_stocks()
    print(f"Trending Stocks Status: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Data keys: {list(result['data'].keys())}")
    
    # Test trending crypto
    crypto_result = get_trending_crypto()
    print(f"\nTrending Crypto Status: {crypto_result['status']}")
    if crypto_result['status'] == 'SUCCESS':
        print(f"Data keys: {list(crypto_result['data'].keys())}")