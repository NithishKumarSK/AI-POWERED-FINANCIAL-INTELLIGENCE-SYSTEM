"""
Portfolio Manager - Unified 3-Agent System
Orchestrator + Stock Research Agent + Recommendation Agent
"""

import os
import sys
import time
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

from portfolio_orchestrator import PortfolioOrchestrator
from portfolio_recommendation_agent import PortfolioRecommendationAgent


class PortfolioManager:
    """
    Unified 3-agent system for portfolio analysis:
    1. Orchestrator Agent - Coordinates stock research for portfolio
    2. Stock Research Agent - Analyzes individual stocks
    3. Recommendation Agent - Provides portfolio-level recommendations
    """
    
    def __init__(self, user_id: str = None):
        """Initialize all three agents."""
        self.orchestrator = PortfolioOrchestrator(user_id=user_id)
        self.recommendation_agent = PortfolioRecommendationAgent(user_id=user_id)
        self.user_id = user_id or "default_user"
        print("Portfolio Manager initialized with 3-agent system")
    
    def analyze_portfolio_from_dollar_amounts(self, dollar_holdings: List[Dict], 
                                             analysis_type: str = "one_month") -> Dict[str, Any]:
        """
        Analyze portfolio from dollar amount holdings (easier user input).
        
        Args:
            dollar_holdings: List of holdings with "name" and "amount"
                [{"name": "Apple", "amount": 22000}, ...]
            analysis_type: Type of analysis for each stock
        
        Returns:
            dict: Complete portfolio analysis with recommendations
        """
        start_time = time.time()
        execution_log = []
        
        try:
            # Validate input holdings structure
            valid_holdings = []
            for i, holding in enumerate(dollar_holdings):
                if isinstance(holding, dict) and 'name' in holding and 'amount' in holding:
                    valid_holdings.append(holding)
                else:
                    print(f"WARNING: Skipping invalid holding at index {i}: {holding}")
            
            if not valid_holdings:
                return {
                    "status": "ERROR",
                    "message": "No valid holdings found. Each holding must have 'name' and 'amount' keys.",
                    "execution_log": execution_log,
                    "total_time": f"{time.time() - start_time:.2f}s"
                }
            
            # Step 1: Convert dollar amounts to shares
            step_start = time.time()
            conversion_result = self.orchestrator.convert_dollar_amounts_to_shares(valid_holdings)
            execution_log.append({
                "step": 1,
                "agent": "Orchestrator",
                "action": "Convert dollar amounts to shares",
                "status": "SUCCESS",
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 2: Run complete portfolio analysis
            step_start = time.time()
            portfolio_data = {
                "holdings": conversion_result["holdings"],
                "cash": conversion_result["cash"]
            }
            orchestrated_data = self.orchestrator.analyze_portfolio(portfolio_data, analysis_type=analysis_type)
            execution_log.append({
                "step": 2,
                "agent": "Orchestrator",
                "action": f"Stock Research Analysis ({analysis_type})",
                "status": orchestrated_data.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            if orchestrated_data.get("status") != "SUCCESS":
                return {
                    "status": "ERROR",
                    "message": "Failed to orchestrate stock analysis",
                    "orchestrated_data": orchestrated_data,
                    "execution_log": execution_log
                }
            
            # Step 3: Recommendation Agent generates portfolio-level insights
            step_start = time.time()
            recommendations = self.recommendation_agent.generate_recommendations(orchestrated_data)
            execution_log.append({
                "step": 3,
                "agent": "Recommendation Agent",
                "action": "Portfolio Recommendations",
                "status": recommendations.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 4: Compile final report
            step_start = time.time()
            final_report = self.recommendation_agent.compile_final_report(
                orchestrated_data, recommendations
            )
            execution_log.append({
                "step": 4,
                "agent": "Portfolio Manager",
                "action": "Final Report Compilation",
                "status": "SUCCESS",
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            return {
                "status": "SUCCESS",
                "conversion_log": conversion_result["conversion_log"],
                "portfolio_summary": orchestrated_data,
                "recommendations": recommendations,
                "final_report": final_report,
                "execution_log": execution_log,
                "total_time": f"{time.time() - start_time:.2f}s",
                "analysis_type": analysis_type
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Error in portfolio analysis from dollar amounts: {str(e)}",
                "execution_log": execution_log,
                "total_time": f"{time.time() - start_time:.2f}s"
            }
    
    def analyze_portfolio_complete(self, portfolio_data: Dict[str, Any], 
                                   analysis_type: str = "comprehensive") -> Dict[str, Any]:
        """
        Run complete portfolio analysis through all 3 agents.
        
        Args:
            portfolio_data: Portfolio dictionary with holdings
            analysis_type: Type of analysis for each stock
                - "comprehensive" (13 tools, ~45s per stock)
                - "one_month" (8 tools, ~16s per stock)
                - "scenario" (6 tools, ~40s per stock)
        
        Returns:
            dict: Complete portfolio analysis with recommendations
        """
        start_time = time.time()
        execution_log = []
        
        try:
            # Step 1: Get portfolio summary
            step_start = time.time()
            summary = self.orchestrator.get_portfolio_summary(portfolio_data)
            execution_log.append({
                "step": 1,
                "agent": "Orchestrator",
                "action": "Portfolio Summary",
                "status": summary.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            if summary.get("status") != "SUCCESS":
                return {
                    "status": "ERROR",
                    "message": "Failed to get portfolio summary",
                    "execution_log": execution_log
                }
            
            # Step 2: Orchestrator runs stock research for each holding
            step_start = time.time()
            orchestrated_data = self.orchestrator.analyze_portfolio(
                portfolio_data, analysis_type=analysis_type
            )
            execution_log.append({
                "step": 2,
                "agent": "Orchestrator",
                "action": f"Stock Research Analysis ({analysis_type})",
                "status": orchestrated_data.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            if orchestrated_data.get("status") != "SUCCESS":
                return {
                    "status": "ERROR",
                    "message": "Failed to orchestrate stock analysis",
                    "orchestrated_data": orchestrated_data,
                    "execution_log": execution_log
                }
            
            # Step 3: Recommendation Agent generates portfolio-level insights
            step_start = time.time()
            recommendations = self.recommendation_agent.generate_recommendations(orchestrated_data)
            execution_log.append({
                "step": 3,
                "agent": "Recommendation Agent",
                "action": "Portfolio Recommendations",
                "status": recommendations.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 4: Compile final report
            step_start = time.time()
            final_report = self.recommendation_agent.compile_final_report(
                orchestrated_data, recommendations
            )
            execution_log.append({
                "step": 4,
                "agent": "Portfolio Manager",
                "action": "Final Report Compilation",
                "status": "SUCCESS",
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            return {
                "status": "SUCCESS",
                "portfolio_summary": summary,
                "orchestrated_data": orchestrated_data,
                "recommendations": recommendations,
                "final_report": final_report,
                "execution_log": execution_log,
                "total_time": f"{time.time() - start_time:.2f}s",
                "analysis_type": analysis_type
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Error in complete portfolio analysis: {str(e)}",
                "execution_log": execution_log,
                "total_time": f"{time.time() - start_time:.2f}s"
            }
    
    def analyze_single_stock(self, symbol: str, analysis_type: str = "comprehensive") -> Dict[str, Any]:
        """
        Analyze a single stock using the stock research agent.
        
        Args:
            symbol: Stock symbol
            analysis_type: Type of analysis
        
        Returns:
            dict: Stock analysis result
        """
        stock_agent = self.orchestrator.stock_agent
        
        if analysis_type == "one_month":
            return stock_agent.analyze_stock_one_month(symbol)
        elif analysis_type == "scenario":
            return stock_agent.analyze_investment_scenario(symbol, 10000, 100)
        else:
            return stock_agent.analyze_stock(symbol)
    
    def get_portfolio_quick_summary(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get quick portfolio summary without full analysis.
        
        Args:
            portfolio_data: Portfolio dictionary with holdings
        
        Returns:
            dict: Portfolio summary
        """
        return self.orchestrator.get_portfolio_summary(portfolio_data)


def create_sample_portfolio() -> Dict[str, Any]:
    """Create a sample portfolio for testing.
    
    Note: You can use either company names (e.g., "Apple") or ticker symbols (e.g., "AAPL").
    The system will automatically convert company names to ticker symbols.
    """
    return {
        "holdings": [
            {"symbol": "Apple", "shares": 100, "avg_cost": 150.00},  # Company name
            {"symbol": "Tesla", "shares": 50, "avg_cost": 200.00},  # Company name
            {"symbol": "MSFT", "shares": 75, "avg_cost": 280.00}    # Ticker symbol
        ],
        "cash": 10000.00
    }


if __name__ == "__main__":
    print("="*80)
    print("PORTFOLIO MANAGER - 3-Agent System")
    print("="*80)
    print("\nAgents:")
    print("1. Orchestrator Agent - Coordinates stock research")
    print("2. Stock Research Agent - Analyzes individual stocks")
    print("3. Recommendation Agent - Portfolio-level recommendations")
    print("="*80)
    
    print("\nChoose operation:")
    print("1. Complete Portfolio Analysis (All 3 agents)")
    print("2. Single Stock Analysis (Stock Research Agent only)")
    print("3. Quick Portfolio Summary (Orchestrator only)")
    
    choice = input("\nEnter choice (1, 2, or 3): ").strip()
    
    manager = PortfolioManager()
    
    if choice == "1":
        print("\n" + "="*80)
        print("COMPLETE PORTFOLIO ANALYSIS")
        print("="*80)
        
        # Ask for portfolio input method
        print("\nPortfolio input method:")
        print("1. Use sample portfolio")
        print("2. Enter portfolio manually")
        
        input_method = input("\nEnter choice (1 or 2): ").strip()
        
        if input_method == "1":
            portfolio_data = create_sample_portfolio()
            print("\nUsing sample portfolio:")
            for holding in portfolio_data["holdings"]:
                print(f"  - {holding['symbol']}: {holding['shares']} shares @ ${holding['avg_cost']:.2f}")
            print(f"  - Cash: ${portfolio_data['cash']:,.2f}")
        else:
            print("\nEnter portfolio details:")
            holdings = []
            while True:
                symbol = input("Enter stock symbol (or 'done' to finish): ").strip().upper()
                if symbol == 'DONE' or not symbol:
                    break
                shares = int(input(f"Enter shares for {symbol}: ").strip())
                avg_cost = float(input(f"Enter average cost for {symbol}: ").strip())
                holdings.append({"symbol": symbol, "shares": shares, "avg_cost": avg_cost})
            
            cash = float(input("Enter cash amount: ").strip())
            portfolio_data = {"holdings": holdings, "cash": cash}
        
        # Choose analysis type
        print("\nAnalysis type:")
        print("1. Comprehensive (13 tools, ~45s per stock)")
        print("2. 1-Month Prediction (8 tools, ~16s per stock)")
        print("3. Investment Scenario (6 tools, ~40s per stock)")
        
        analysis_choice = input("\nEnter choice (1, 2, or 3): ").strip()
        analysis_type = "one_month" if analysis_choice == "2" else "scenario" if analysis_choice == "3" else "comprehensive"
        
        # Estimate time
        num_stocks = len(portfolio_data["holdings"])
        if analysis_type == "comprehensive":
            est_time = num_stocks * 45
        elif analysis_type == "one_month":
            est_time = num_stocks * 16
        else:
            est_time = num_stocks * 40
        
        print(f"\nEstimated time: ~{est_time} seconds ({est_time/60:.1f} minutes)")
        proceed = input("\nProceed? (y/n): ").strip().lower()
        
        if proceed == 'y':
            print("\n" + "="*80)
            print("RUNNING 3-AGENT ANALYSIS...")
            print("="*80)
            
            result = manager.analyze_portfolio_complete(portfolio_data, analysis_type=analysis_type)
            
            print(f"\nStatus: {result['status']}")
            if result['status'] == 'SUCCESS':
                print(f"Total Time: {result['total_time']}")
                
                print("\n" + "="*80)
                print("EXECUTION LOG")
                print("="*80)
                for log in result['execution_log']:
                    status_icon = "✅" if log['status'] == "SUCCESS" else "❌"
                    print(f"{status_icon} Step {log['step']}: {log['agent']} - {log['action']} ({log['duration']})")
                
                print("\n" + "="*80)
                print("FINAL REPORT")
                print("="*80)
                print(result['final_report'])
                
                # Save report to file
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"portfolio_report_{timestamp}.txt"
                with open(filename, 'w') as f:
                    f.write(result['final_report'])
                print(f"\nReport saved to: {filename}")
            else:
                print(f"Error: {result.get('message')}")
                if 'orchestrated_data' in result:
                    print(f"Orchestrator Error: {result['orchestrated_data'].get('message')}")
        
    elif choice == "2":
        print("\n" + "="*80)
        print("SINGLE STOCK ANALYSIS")
        print("="*80)
        
        symbol = input("Enter stock symbol: ").strip().upper()
        
        print("\nAnalysis type:")
        print("1. Comprehensive (13 tools, ~45s)")
        print("2. 1-Month Prediction (8 tools, ~16s)")
        print("3. Investment Scenario (6 tools, ~40s)")
        
        analysis_choice = input("\nEnter choice (1, 2, or 3): ").strip()
        analysis_type = "one_month" if analysis_choice == "2" else "scenario" if analysis_choice == "3" else "comprehensive"
        
        print(f"\nAnalyzing {symbol}...")
        result = manager.analyze_single_stock(symbol, analysis_type)
        
        print(f"\nStatus: {result['status']}")
        if result['status'] == 'SUCCESS':
            print(result.get('report', 'No report available'))
        else:
            print(f"Error: {result.get('message')}")
    
    elif choice == "3":
        print("\n" + "="*80)
        print("QUICK PORTFOLIO SUMMARY")
        print("="*80)
        
        portfolio_data = create_sample_portfolio()
        result = manager.get_portfolio_quick_summary(portfolio_data)
        
        print(f"\nStatus: {result['status']}")
        if result['status'] == 'SUCCESS':
            print(f"Total Holdings: {result['total_holdings']}")
            print(f"Total Invested: ${result['total_invested']:,.2f}")
            print(f"Cash: ${result['cash']:,.2f}")
            print(f"Total Value: ${result['total_value']:,.2f}")
            
            print("\nPositions:")
            for pos in result['positions']:
                print(f"  - {pos['symbol']}: {pos['shares']} shares @ ${pos['avg_cost']:.2f} (${pos['invested']:,.2f})")
        else:
            print(f"Error: {result.get('message')}")
    
    else:
        print("Invalid choice")
