"""
World Economy Indicators Tool
Fetches global economic indicators and data from TradingView API
"""

import os
import requests
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://tradingview-data1.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")


def get_world_economy_indicator(indicator: str, region: str = "g20") -> Dict[str, Any]:
    """
    Get world economy indicator data using the exact API format.
    
    Args:
        indicator (str): Indicator type (e.g., 'full-year-gdp-growth', 'cpi', 'unemployment', etc.)
        region (str): Region code (e.g., 'g20', 'world', 'usa', 'europe', etc.)
    
    Returns:
        dict: World economy indicator data
    """
    try:
        url = f"{BASE_URL}/api/world-economy/indicators/{indicator}"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": API_KEY
        }
        params = {
            "region": region
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "indicator": indicator,
                "region": region,
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
            "message": f"Error fetching world economy indicator: {str(e)}"
        }


def get_g20_gdp_growth() -> Dict[str, Any]:
    """
    Get G20 full year GDP growth data.
    
    Returns:
        dict: G20 GDP growth data
    """
    return get_world_economy_indicator("full-year-gdp-growth", region="g20")


def get_world_cpi(region: str = "world") -> Dict[str, Any]:
    """
    Get Consumer Price Index (inflation) data.
    
    Args:
        region (str): Region code (default: 'world')
    
    Returns:
        dict: CPI data
    """
    return get_world_economy_indicator("cpi", region=region)


def get_unemployment_rate(region: str = "g20") -> Dict[str, Any]:
    """
    Get unemployment rate data.
    
    Args:
        region (str): Region code (default: 'g20')
    
    Returns:
        dict: Unemployment rate data
    """
    return get_world_economy_indicator("unemployment", region=region)


def get_interest_rates(region: str = "g20") -> Dict[str, Any]:
    """
    Get interest rates data.
    
    Args:
        region (str): Region code (default: 'g20')
    
    Returns:
        dict: Interest rates data
    """
    return get_world_economy_indicator("interest-rates", region=region)


def get_gdp(region: str = "g20") -> Dict[str, Any]:
    """
    Get GDP data.
    
    Args:
        region (str): Region code (default: 'g20')
    
    Returns:
        dict: GDP data
    """
    return get_world_economy_indicator("gdp", region=region)


def get_trade_balance(region: str = "g20") -> Dict[str, Any]:
    """
    Get trade balance data.
    
    Args:
        region (str): Region code (default: 'g20')
    
    Returns:
        dict: Trade balance data
    """
    return get_world_economy_indicator("trade-balance", region=region)


def get_government_debt(region: str = "g20") -> Dict[str, Any]:
    """
    Get government debt data.
    
    Args:
        region (str): Region code (default: 'g20')
    
    Returns:
        dict: Government debt data
    """
    return get_world_economy_indicator("government-debt", region=region)


def get_current_account(region: str = "g20") -> Dict[str, Any]:
    """
    Get current account data.
    
    Args:
        region (str): Region code (default: 'g20')
    
    Returns:
        dict: Current account data
    """
    return get_world_economy_indicator("current-account", region=region)


def get_custom_indicator(indicator: str, region: str = "g20") -> Dict[str, Any]:
    """
    Get custom world economy indicator by name.
    
    Args:
        indicator (str): Custom indicator name
        region (str): Region code (default: 'g20')
    
    Returns:
        dict: Custom indicator data
    """
    return get_world_economy_indicator(indicator, region=region)


if __name__ == "__main__":
    # Test the functions
    print("Testing World Economy Indicators Tool...")
    
    # Test G20 GDP growth
    result = get_g20_gdp_growth()
    print(f"G20 GDP Growth Status: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Data keys: {list(result['data'].keys())}")
    
    # Test CPI
    cpi_result = get_world_cpi()
    print(f"\nWorld CPI Status: {cpi_result['status']}")
    if cpi_result['status'] == 'SUCCESS':
        print(f"Data keys: {list(cpi_result['data'].keys())}")