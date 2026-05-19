"""
Portfolio Orchestrator Agent
Coordinates stock research agent for portfolio analysis
"""

import os
import sys
import time
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

# Import stock research agent
from stock_analysis_agent import StockAnalysisAgent
# Import price tool for conversion
from tradingview_price import get_price
# Import search tool for ticker conversion
from tradingview_search import find_ticker_by_company_name


class PortfolioOrchestrator:
    """
    Orchestrator agent that coordinates stock research agent for portfolio analysis.
    Takes portfolio data and runs stock analysis for each holding.
    """
    
    def __init__(self, user_id: str = None):
        """Initialize orchestrator with stock research agent."""
        self.stock_agent = StockAnalysisAgent(user_id=user_id)
        self.user_id = user_id or "default_user"
    
    def analyze_portfolio(self, portfolio_data: Dict[str, Any], 
                         analysis_type: str = "comprehensive") -> Dict[str, Any]:
        """
        Analyze entire portfolio by running stock research for each holding.
        
        Args:
            portfolio_data: Portfolio dictionary with holdings
                {
                    "holdings": [
                        {"symbol": "AAPL", "shares": 100, "avg_cost": 150.00},
                        ...
                    ],
                    "cash": 10000.00
                }
            analysis_type: Type of analysis for each stock
                - "comprehensive" (13 tools, ~45s per stock)
                - "one_month" (8 tools, ~16s per stock)
                - "scenario" (6 tools, ~40s per stock)
        
        Returns:
            dict: Orchestrated portfolio analysis with all stock reports
        """
        execution_steps = []
        start_time = time.time()
        
        try:
            holdings = portfolio_data.get("holdings", [])
            cash = portfolio_data.get("cash", 0.0)
            
            if not holdings:
                return {
                    "status": "ERROR",
                    "message": "No holdings found in portfolio data"
                }
            
            execution_steps.append({
                "step": 0,
                "action": f"Portfolio analysis started with {len(holdings)} holdings",
                "status": "SUCCESS",
                "duration": f"{time.time() - start_time:.2f}s"
            })
            
            # Calculate portfolio value
            portfolio_value = 0.0
            stock_reports = []

            # Analyze each stock in portfolio
            for idx, holding in enumerate(holdings):
                symbol = holding.get("symbol")
                shares = holding.get("shares", 0)
                avg_cost = holding.get("avg_cost", 0.0)
                
                step_start = time.time()
                
                # Convert company name to ticker symbol if needed
                ticker_symbol, conversion_info = self.stock_agent._convert_to_ticker(symbol)
                
                execution_steps.append({
                    "step": idx + 1,
                    "action": f"Convert {symbol} -> {ticker_symbol}",
                    "status": "SUCCESS",
                    "duration": f"{time.time() - step_start:.2f}s"
                })
                
                step_start = time.time()
                
                # Choose analysis function based on type
                if analysis_type == "one_month":
                    result = self.stock_agent.analyze_stock_one_month(ticker_symbol)
                elif analysis_type == "scenario":
                    result = self.stock_agent.analyze_investment_scenario(ticker_symbol, shares * avg_cost, 100)
                else:  # comprehensive (default)
                    result = self.stock_agent.analyze_stock(ticker_symbol)
                
                execution_steps.append({
                    "step": idx + 1,
                    "action": f"Analyze {symbol} ({analysis_type})",
                    "status": result.get("status"),
                    "duration": f"{time.time() - step_start:.2f}s"
                })
                
                # Get current price for portfolio value calculation
                # Use avg_cost from holding (already set during conversion)
                current_price = float(avg_cost) if isinstance(avg_cost, (int, float)) else 0.0
                position_value = shares * current_price
                portfolio_value += position_value
                
                stock_reports.append({
                    "symbol": symbol,  # Original input (could be company name)
                    "ticker": ticker_symbol,  # Converted ticker symbol
                    "shares": shares,
                    "avg_cost": avg_cost,
                    "current_price": current_price,
                    "position_value": position_value,
                    "analysis_result": result,
                    "analysis_type": analysis_type,
                    "conversion_info": conversion_info
                })
            
            total_portfolio_value = portfolio_value + cash
            
            execution_steps.append({
                "step": len(holdings) + 1,
                "action": f"Portfolio analysis completed. Total value: ${total_portfolio_value:,.2f}",
                "status": "SUCCESS",
                "duration": f"{time.time() - start_time:.2f}s"
            })
            
            return {
                "status": "SUCCESS",
                "portfolio_data": portfolio_data,
                "portfolio_value": total_portfolio_value,
                "stock_reports": stock_reports,
                "execution_steps": execution_steps,
                "total_time": f"{time.time() - start_time:.2f}s",
                "analysis_type": analysis_type,
                "stocks_analyzed": len(holdings)
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Error orchestrating portfolio analysis: {str(e)}",
                "execution_steps": execution_steps,
                "total_time": f"{time.time() - start_time:.2f}s"
            }
    
    def convert_dollar_amounts_to_shares(self, dollar_holdings: List[Dict]) -> Dict[str, Any]:
        """
        Convert dollar amount holdings to shares based on current prices.

        Args:
            dollar_holdings: List of holdings with "name" and "amount" (dollar value)
                [{"name": "Apple", "amount": 22000}, ...]

        Returns:
            dict: Portfolio data with shares calculated from current prices
        """
        execution_steps = []
        portfolio_holdings = []

        for holding in dollar_holdings:
            try:
                name = holding.get("name")
                amount = holding.get("amount")
                currency = holding.get("currency", "USD")

                if not name:
                    print(f"ERROR: Holding missing 'name' key: {holding}")
                    continue

                if amount is None:
                    print(f"ERROR: Holding missing 'amount' key: {holding}")
                    continue
            except Exception as e:
                print(f"ERROR: Invalid holding format: {holding}, error: {e}")
                continue

            # Convert company name to ticker using imported function
            ticker_result = find_ticker_by_company_name(name)

            if ticker_result['status'] == 'SUCCESS':
                ticker_symbol = ticker_result['ticker']
                conversion_info = {
                    "original_input": name,
                    "converted": True,
                    "type": "company_name",
                    "company_name": ticker_result.get('company_name', name),
                    "exchange": ticker_result.get('exchange', 'N/A')
                }
            else:
                # If search failed, try using the input as-is (might already be a ticker)
                ticker_symbol = name.upper()
                conversion_info = {
                    "original_input": name,
                    "converted": False,
                    "type": "ticker_symbol",
                    "error": ticker_result.get('message', 'Search failed')
                }

            # Get current price
            price_result = get_price(ticker_symbol)
            
            current_price = 0.0
            if price_result and price_result.get('status') == 'SUCCESS':
                try:
                    current_price = price_result.get('data', {}).get('data', {}).get('current', {}).get('close', 0)
                except:
                    current_price = 0.0
            
            # Calculate shares (using current price as both price and avg_cost as requested)
            if current_price > 0:
                shares = amount / current_price
                avg_cost = current_price  # Use current price as cost basis
            else:
                # If price fetch failed, estimate shares (this is a fallback)
                shares = amount / 100  # Rough estimate
                avg_cost = 100.0
                execution_steps.append({
                    "warning": f"Could not get current price for {name}, using estimate"
                })
            
            portfolio_holdings.append({
                "symbol": ticker_symbol,  # Use converted ticker
                "shares": shares,
                "avg_cost": avg_cost,
                "original_name": name,
                "original_amount": amount,
                "conversion_info": conversion_info
            })
            
            # Only add to conversion log if we successfully processed this holding
            try:
                execution_steps.append({
                    "name": name,
                    "ticker": ticker_symbol,
                    "amount": amount,
                    "current_price": current_price,
                    "calculated_shares": shares,
                    "avg_cost": avg_cost
                })
            except Exception as e:
                print(f"ERROR: Could not add to conversion log: {e}")
                # Continue anyway, the holding was already added to portfolio_holdings
        
        return {
            "holdings": portfolio_holdings,
            "cash": 0.0,
            "conversion_log": execution_steps
        }
    
    def analyze_portfolio_from_dollar_amounts(self, dollar_holdings: List[Dict], 
                                              analysis_type: str = "one_month") -> Dict[str, Any]:
        """
        Analyze portfolio from dollar amount holdings (easier user input).
        
        Args:
            dollar_holdings: List of holdings with "name" and "amount"
                [{"name": "Apple", "amount": 22000}, ...]
            analysis_type: Type of analysis for each stock
        
        Returns:
            dict: Complete portfolio analysis
        """
        # Convert dollar amounts to shares
        conversion_result = self.convert_dollar_amounts_to_shares(dollar_holdings)
        
        # Create portfolio data
        portfolio_data = {
            "holdings": conversion_result["holdings"],
            "cash": conversion_result["cash"]
        }
        
        # Run standard portfolio analysis
        result = self.analyze_portfolio(portfolio_data, analysis_type=analysis_type)
        
        # Add conversion log to result
        result["conversion_log"] = conversion_result["conversion_log"]
        
        return result
    
    def get_portfolio_summary(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get basic portfolio summary without running full analysis.
        
        Args:
            portfolio_data: Portfolio dictionary with holdings
        
        Returns:
            dict: Portfolio summary with basic metrics
        """
        try:
            holdings = portfolio_data.get("holdings", [])
            cash = portfolio_data.get("cash", 0.0)
            
            total_invested = 0.0
            position_summary = []
            
            for holding in holdings:
                symbol = holding.get("symbol")
                shares = holding.get("shares", 0)
                avg_cost = holding.get("avg_cost", 0.0)
                
                invested = shares * avg_cost
                total_invested += invested
                
                position_summary.append({
                    "symbol": symbol,
                    "shares": shares,
                    "avg_cost": avg_cost,
                    "invested": invested
                })
            
            total_value = total_invested + cash  # Simplified (uses cost basis)
            
            return {
                "status": "SUCCESS",
                "total_holdings": len(holdings),
                "total_invested": total_invested,
                "cash": cash,
                "total_value": total_value,
                "positions": position_summary
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Error getting portfolio summary: {str(e)}"
            }


if __name__ == "__main__":
    # Test orchestrator
    print("Testing Portfolio Orchestrator...")
    
    # Sample portfolio
    sample_portfolio = {
        "holdings": [
            {"symbol": "AAPL", "shares": 100, "avg_cost": 150.00},
            {"symbol": "TSLA", "shares": 50, "avg_cost": 200.00}
        ],
        "cash": 10000.00
    }
    
    orchestrator = PortfolioOrchestrator()
    
    # Get summary first
    print("\n1. Portfolio Summary:")
    summary = orchestrator.get_portfolio_summary(sample_portfolio)
    print(f"Status: {summary['status']}")
    if summary['status'] == 'SUCCESS':
        print(f"Total Holdings: {summary['total_holdings']}")
        print(f"Total Invested: ${summary['total_invested']:,.2f}")
        print(f"Cash: ${summary['cash']:,.2f}")
        print(f"Total Value: ${summary['total_value']:,.2f}")
    
    # Run portfolio analysis (comprehensive)
    print("\n2. Running Portfolio Analysis (Comprehensive)...")
    print("This will take approximately 90 seconds (2 stocks x 45s each)")
    
    choice = input("\nContinue? (y/n): ").strip().lower()
    if choice == 'y':
        result = orchestrator.analyze_portfolio(sample_portfolio, analysis_type="comprehensive")
        
        print(f"\nStatus: {result['status']}")
        if result['status'] == 'SUCCESS':
            print(f"Stocks Analyzed: {result['stocks_analyzed']}")
            print(f"Portfolio Value: ${result['portfolio_value']:,.2f}")
            print(f"Total Time: {result['total_time']}")
            
            print("\nExecution Steps:")
            for step in result['execution_steps']:
                print(f"  {step['step']}. {step['action']} ({step['status']}) - {step['duration']}")
            
            print("\nStock Reports:")
            for report in result['stock_reports']:
                print(f"\n{report['symbol']}:")
                print(f"  Shares: {report['shares']}")
                print(f"  Position Value: ${report['position_value']:,.2f}")
                print(f"  Analysis Status: {report['analysis_result']['status']}")
        else:
            print(f"Error: {result.get('message')}")
