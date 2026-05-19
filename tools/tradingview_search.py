"""
TradingView Search Tools
Search for stocks, crypto, forex, futures, bonds, and ETFs across all markets
"""

import os
import requests
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://tradingview-data1.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")


def search_market(query: str) -> Dict[str, Any]:
    """
    Search for instruments across all asset types by keyword or symbol.
    
    Args:
        query (str): Search query (company name, symbol, keyword)
    
    Returns:
        dict: Search results with matching instruments
    """
    try:
        url = f"{BASE_URL}/api/search/market/{query}"
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
                "query": query,
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
            "message": f"Error searching market: {str(e)}"
        }


def find_ticker_by_company_name(company_name: str) -> Dict[str, Any]:
    """
    Find ticker symbol by company name.
    
    Args:
        company_name (str): Company name (e.g., "Apple", "Tesla", "Microsoft")
    
    Returns:
        dict: Ticker symbol and company info
    """
    search_result = search_market(company_name)
    
    if search_result['status'] != 'SUCCESS':
        return {
            "status": "ERROR",
            "message": f"Search failed: {search_result.get('message', 'Unknown error')}"
        }
    
    data = search_result.get('data', {})
    if not data.get('success'):
        return {
            "status": "ERROR",
            "message": f"Search returned no success: {data.get('msg', 'Unknown error')}"
        }
    
    # The data structure is nested: data -> data -> markets
    inner_data = data.get('data', {})
    
    # Check for markets key
    if 'markets' not in inner_data:
        return {
            "status": "ERROR",
            "message": f"No 'markets' key in search results for '{company_name}'"
        }
    
    markets = inner_data.get('markets', [])
    if not markets:
        return {
            "status": "ERROR",
            "message": f"No results found for '{company_name}'"
        }
    
    # Find the best stock match (prioritize stocks over other types)
    stock_matches = [m for m in markets if m.get('type') == 'stock']
    
    if stock_matches:
        best_match = stock_matches[0]  # Take first stock match
    else:
        best_match = markets[0]  # Take first match if no stocks found
    
    return {
        "status": "SUCCESS",
        "ticker": best_match.get('symbol'),
        "company_name": best_match.get('description'),
        "exchange": best_match.get('exchange'),
        "type": best_match.get('type'),
        "currency": best_match.get('currency_code'),
        "original_query": company_name
    }


if __name__ == "__main__":
    # Test the search function
    print("Testing TradingView Search Tool...")
    
    result = search_market("Apple")
    print(f"Search Status: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Data keys: {list(result['data'].keys())}")
        if 'markets' in result['data']:
            print(f"Number of results: {len(result['data']['markets'])}")
            if result['data']['markets']:
                print(f"First result: {result['data']['markets'][0]}")
    
    # Test the company name to ticker function
    print("\nTesting Company Name to Ticker Conversion...")
    ticker_result = find_ticker_by_company_name("Apple")
    print(f"Status: {ticker_result['status']}")
    if ticker_result['status'] == 'SUCCESS':
        print(f"Company: {ticker_result['company_name']}")
        print(f"Ticker: {ticker_result['ticker']}")
        print(f"Exchange: {ticker_result['exchange']}")
        print(f"Type: {ticker_result['type']}")
    else:
        print(f"Error: {ticker_result.get('message', 'Unknown error')}")