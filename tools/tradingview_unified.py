"""
TradingView Unified API Tool
Comprehensive integration of all TradingView API endpoints for the Stock Agent
"""

import os
import sys
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

# Add parent directory for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from tools.tradingview_price import get_price, get_batch_prices
    from tools.tradingview_quote import get_quote, get_batch_quotes
    from tools.tradingview_search import search_market
    from tools.tradingview_technical_analysis import get_technical_analysis, get_technical_indicators
    from tools.tradingview_market_data import (
        get_company_info, get_financials_annual, get_financials_quarterly,
        get_dividend_info, get_analyst_recommendations, get_current_metrics
    )
    from tools.tradingview_leaderboards import (
        get_trending_stocks, get_trending_crypto, get_trending_indices, get_trending_etfs
    )
    from tools.tradingview_calendar import (
        get_economic_calendar, get_earnings_calendar, get_dividends_calendar, get_ipo_calendar
    )
    from tools.tradingview_community import get_hot_ideas, get_editors_picks, get_symbol_ideas
except ImportError:
    # If running from tools directory
    from tradingview_price import get_price, get_batch_prices
    from tradingview_quote import get_quote, get_batch_quotes
    from tradingview_search import search_market
    from tradingview_technical_analysis import get_technical_analysis, get_technical_indicators
    from tradingview_market_data import (
        get_company_info, get_financials_annual, get_financials_quarterly,
        get_dividend_info, get_analyst_recommendations, get_current_metrics
    )
    from tradingview_leaderboards import (
        get_trending_stocks, get_trending_crypto, get_trending_indices, get_trending_etfs
    )
    from tradingview_calendar import (
        get_economic_calendar, get_earnings_calendar, get_dividends_calendar, get_ipo_calendar
    )
    from tradingview_community import get_hot_ideas, get_editors_picks, get_symbol_ideas


def get_unified_analysis(symbol: str) -> Dict[str, Any]:
    """
    Alias for get_comprehensive_stock_analysis for backward compatibility.
    
    Args:
        symbol (str): Stock symbol
    
    Returns:
        dict: Comprehensive stock analysis
    """
    return get_comprehensive_stock_analysis(symbol)


def get_comprehensive_stock_analysis(symbol: str) -> Dict[str, Any]:
    """
    Get comprehensive analysis for a stock including price, quote, technical analysis, and market data.
    
    Args:
        symbol (str): Stock symbol (e.g., "AAPL")
    
    Returns:
        dict: Comprehensive stock analysis
    """
    try:
        results = {
            "status": "SUCCESS",
            "symbol": symbol,
            "price_data": get_price(symbol),
            "quote_data": get_quote(symbol),
            "technical_analysis": get_technical_analysis(symbol),
            "company_info": get_company_info(symbol),
            "analyst_recommendations": get_analyst_recommendations(symbol),
            "current_metrics": get_current_metrics(symbol)
        }
        
        # Check if any requests failed
        failed_requests = [k for k, v in results.items() if k != "status" and k != "symbol" and v.get("status") == "ERROR"]
        
        if failed_requests:
            results["warnings"] = f"Some requests failed: {', '.join(failed_requests)}"
        
        return results
        
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Error in comprehensive analysis: {str(e)}"
        }


def get_market_overview() -> Dict[str, Any]:
    """
    Get overall market overview including trending stocks, economic calendar, and hot ideas.
    
    Returns:
        dict: Market overview data
    """
    try:
        results = {
            "status": "SUCCESS",
            "trending_stocks": get_trending_stocks(),
            "economic_calendar": get_economic_calendar(),
            "hot_ideas": get_hot_ideas(),
            "editors_picks": get_editors_picks()
        }
        
        # Check if any requests failed
        failed_requests = [k for k, v in results.items() if k != "status" and v.get("status") == "ERROR"]
        
        if failed_requests:
            results["warnings"] = f"Some requests failed: {', '.join(failed_requests)}"
        
        return results
        
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Error in market overview: {str(e)}"
        }


def get_portfolio_analysis(symbols: List[str]) -> Dict[str, Any]:
    """
    Get analysis for multiple portfolio symbols.
    
    Args:
        symbols (list): List of stock symbols
    
    Returns:
        dict: Portfolio analysis with batch data
    """
    try:
        results = {
            "status": "SUCCESS",
            "symbols": symbols,
            "batch_prices": get_batch_prices(symbols),
            "batch_quotes": get_batch_quotes(symbols)
        }
        
        # Get individual analysis for each symbol (limited to first 5 for performance)
        individual_analysis = {}
        for i, symbol in enumerate(symbols[:5]):
            individual_analysis[symbol] = {
                "technical_analysis": get_technical_analysis(symbol),
                "company_info": get_company_info(symbol)
            }
        
        results["individual_analysis"] = individual_analysis
        
        # Check if any requests failed
        failed_requests = [k for k, v in results.items() if k != "status" and k != "symbols" and v.get("status") == "ERROR"]
        
        if failed_requests:
            results["warnings"] = f"Some requests failed: {', '.join(failed_requests)}"
        
        return results
        
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Error in portfolio analysis: {str(e)}"
        }


if __name__ == "__main__":
    # Test the unified functions
    print("Testing TradingView Unified API Tool...")
    
    # Test comprehensive stock analysis
    print("\n=== Comprehensive Stock Analysis (AAPL) ===")
    stock_result = get_comprehensive_stock_analysis("AAPL")
    print(f"Status: {stock_result['status']}")
    if stock_result['status'] == 'SUCCESS':
        print(f"Available data: {list(stock_result.keys())}")
        if 'warnings' in stock_result:
            print(f"Warnings: {stock_result['warnings']}")
    
    # Test market overview
    print("\n=== Market Overview ===")
    overview_result = get_market_overview()
    print(f"Status: {overview_result['status']}")
    if overview_result['status'] == 'SUCCESS':
        print(f"Available data: {list(overview_result.keys())}")
        if 'warnings' in overview_result:
            print(f"Warnings: {overview_result['warnings']}")
    
    # Test portfolio analysis
    print("\n=== Portfolio Analysis ===")
    portfolio_result = get_portfolio_analysis(["AAPL", "MSFT", "GOOGL"])
    print(f"Status: {portfolio_result['status']}")
    if portfolio_result['status'] == 'SUCCESS':
        print(f"Available data: {list(portfolio_result.keys())}")
        if 'warnings' in portfolio_result:
            print(f"Warnings: {portfolio_result['warnings']}")