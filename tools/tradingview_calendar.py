"""
TradingView Calendar Tools
Get economic, earnings, dividends, and IPO calendars across global markets
"""

import os
import requests
import time
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://tradingview-data1.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")


def get_calendar(calendar_type: str, from_timestamp: int = None, to_timestamp: int = None) -> Dict[str, Any]:
    """
    Get calendar events for a specific type.
    Updated to match exact API format.
    
    Args:
        calendar_type (str): Calendar type (economic, earnings, revenue, ipo)
                             Note: revenue = dividends calendar
        from_timestamp (int): Start time (Unix timestamp in seconds). Time span cannot exceed 40 days
        to_timestamp (int): End time (Unix timestamp in seconds). Time span cannot exceed 40 days
    
    Returns:
        dict: Calendar events data
    """
    try:
        url = f"{BASE_URL}/api/calendar/{calendar_type}"
        headers = {
            "x-rapidapi-host": "tradingview-data1.p.rapidapi.com",
            "x-rapidapi-key": API_KEY
        }
        
        params = {}
        
        # For all calendar types, from and to are required
        if from_timestamp is None:
            from_timestamp = int(time.time()) - (30 * 24 * 60 * 60)  # 30 days ago
        if to_timestamp is None:
            to_timestamp = int(time.time())  # Now
        
        params["from"] = from_timestamp
        params["to"] = to_timestamp
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "SUCCESS",
                "calendar_type": calendar_type,
                "from": from_timestamp,
                "to": to_timestamp,
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
            "message": f"Error fetching calendar: {str(e)}"
        }


def get_economic_calendar(from_timestamp: int = None, to_timestamp: int = None) -> Dict[str, Any]:
    """
    Get economic events calendar.
    
    Args:
        from_timestamp (int): Start time (Unix timestamp in seconds). Default: 30 days ago
        to_timestamp (int): End time (Unix timestamp in seconds). Default: now
    """
    return get_calendar("economic", from_timestamp, to_timestamp)


def get_earnings_calendar(from_timestamp: int = None, to_timestamp: int = None) -> Dict[str, Any]:
    """
    Get earnings calendar.
    
    Args:
        from_timestamp (int): Start time (Unix timestamp in seconds). Default: 30 days ago
        to_timestamp (int): End time (Unix timestamp in seconds). Default: now
    """
    return get_calendar("earnings", from_timestamp, to_timestamp)


def get_dividends_calendar(from_timestamp: int = None, to_timestamp: int = None) -> Dict[str, Any]:
    """
    Get dividends calendar (revenue endpoint).
    
    Args:
        from_timestamp (int): Start time (Unix timestamp in seconds). Default: 30 days ago
        to_timestamp (int): End time (Unix timestamp in seconds). Default: now
    """
    return get_calendar("revenue", from_timestamp, to_timestamp)


def get_ipo_calendar(from_timestamp: int = None, to_timestamp: int = None) -> Dict[str, Any]:
    """
    Get IPO calendar.
    
    Args:
        from_timestamp (int): Start time (Unix timestamp in seconds). Default: 30 days ago
        to_timestamp (int): End time (Unix timestamp in seconds). Default: now
    """
    return get_calendar("ipo", from_timestamp, to_timestamp)


if __name__ == "__main__":
    # Test the functions
    print("Testing TradingView Calendar Tools...")
    
    # Test economic calendar
    result = get_economic_calendar()
    print(f"Economic Calendar Status: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Data keys: {list(result['data'].keys())}")
    
    # Test earnings calendar
    earnings_result = get_earnings_calendar()
    print(f"\nEarnings Calendar Status: {earnings_result['status']}")
    if earnings_result['status'] == 'SUCCESS':
        print(f"Data keys: {list(earnings_result['data'].keys())}")