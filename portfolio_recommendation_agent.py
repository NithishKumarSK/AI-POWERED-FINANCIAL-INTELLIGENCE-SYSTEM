"""
Portfolio Recommendation Agent
Takes all stock reports and portfolio data to provide portfolio-level recommendations
"""

import os
import sys
import warnings
from typing import Dict, Any, List
from dotenv import load_dotenv

# Suppress FutureWarning for google.generativeai
warnings.filterwarnings("ignore", category=FutureWarning)

import google.generativeai as genai

load_dotenv()


class PortfolioRecommendationAgent:
    """
    Recommendation agent that analyzes portfolio-level data and provides
    optimization suggestions, risk reduction strategies, and actionable insights.
    """
    
    def __init__(self, user_id: str = None):
        """Initialize recommendation agent with Gemini AI."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash')
                print("Portfolio Recommendation Agent initialized with Gemini AI")
            except Exception as e:
                print(f"Error initializing Gemini AI: {e}")
                self.model = None
        else:
            print("Warning: GOOGLE_API_KEY not found")
            self.model = None
        
        self.user_id = user_id or "default_user"
    
    def generate_recommendations(self, orchestrated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate portfolio-level recommendations from orchestrated analysis.
        
        Args:
            orchestrated_data: Output from PortfolioOrchestrator
                {
                    "portfolio_data": {...},
                    "portfolio_value": float,
                    "stock_reports": [
                        {
                            "symbol": str,
                            "shares": int,
                            "avg_cost": float,
                            "current_price": float,
                            "position_value": float,
                            "analysis_result": {...}
                        },
                        ...
                    ]
                }
        
        Returns:
            dict: Portfolio recommendations with actionable insights
        """
        if not self.model:
            return {
                "status": "ERROR",
                "message": "AI model not available"
            }
        
        try:
            # Prepare portfolio summary
            portfolio_data = orchestrated_data.get("portfolio_data", {})
            stock_reports = orchestrated_data.get("stock_reports", [])
            portfolio_value = orchestrated_data.get("portfolio_value", 0.0)
            
            # Build comprehensive portfolio summary
            portfolio_summary = self._build_portfolio_summary(portfolio_data, stock_reports, portfolio_value)
            
            # Build stock analysis summary
            stock_analysis_summary = self._build_stock_analysis_summary(stock_reports)
            
            # Generate AI recommendations
            prompt = f"""
            You are a professional portfolio manager and financial advisor. 
            Analyze the following portfolio data and provide actionable recommendations.
            
            PORTFOLIO SUMMARY:
            {portfolio_summary}
            
            INDIVIDUAL STOCK ANALYSES:
            {stock_analysis_summary}
            
            Based on this comprehensive analysis, provide:
            
            1. PORTFOLIO HEALTH ASSESSMENT:
               - Overall portfolio quality (Excellent/Good/Fair/Poor)
               - Diversification score (0-100%)
               - Risk level (Low/Medium/High)
               - Concentration risk analysis
            
            2. RISK ANALYSIS:
               - Current portfolio risk factors
               - Sector concentration risks
               - Individual stock risks
               - Market exposure risks
            
            3. DIVERSIFICATION ANALYSIS:
               - Current diversification status
               - Missing sectors/asset classes
               - Correlation concerns
               - Geographic diversification
            
            4. PERFORMANCE ANALYSIS:
               - Portfolio performance vs benchmarks
               - Best performing positions
               - Underperforming positions
               - Performance attribution
            
            5. ACTIONABLE RECOMMENDATIONS:
               - TOP 3 IMMEDIATE ACTIONS (Priority: High)
               - Rebalancing suggestions
               - Positions to consider reducing
               - Positions to consider increasing
               - New positions to consider adding
               - Positions to consider selling
            
            6. RISK REDUCTION STRATEGIES:
               - How to lower portfolio risk
               - Stop-loss recommendations
               - Position sizing adjustments
               - Hedging strategies (if applicable)
            
            7. PORTFOLIO OPTIMIZATION:
               - Target allocation adjustments
               - Tax-efficient strategies
               - Cost reduction opportunities
               - Long-term strategic adjustments
            
            8. NEXT STEPS:
               - Specific action items for next 30 days
               - Monitoring checklist
               - Review schedule
            
            Format as a professional, actionable portfolio management report.
            Focus on practical, implementable recommendations based on the actual data provided.
            Be conservative and risk-aware in your recommendations.
            """
            
            response = self.model.generate_content(prompt)
            
            return {
                "status": "SUCCESS",
                "recommendations": response.text,
                "portfolio_value": portfolio_value,
                "stocks_analyzed": len(stock_reports),
                "focus": "portfolio-level optimization and risk reduction"
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Error generating recommendations: {str(e)}"
            }
    
    def _build_portfolio_summary(self, portfolio_data: Dict, stock_reports: List, 
                                 portfolio_value: float) -> str:
        """Build portfolio summary string for AI."""
        holdings = portfolio_data.get("holdings", [])
        cash = portfolio_data.get("cash", 0.0)
        
        summary = f"""
Total Portfolio Value: ${portfolio_value:,.2f}
Cash: ${cash:,.2f}
Number of Holdings: {len(holdings)}
Invested Value: ${portfolio_value - cash:,.2f}

POSITION BREAKDOWN:
"""
        
        for report in stock_reports:
            symbol = report.get("symbol")  # Original input (could be company name)
            ticker = report.get("ticker", symbol)  # Converted ticker symbol
            conversion_info = report.get("conversion_info", {})
            shares = report.get("shares", 0)
            avg_cost = report.get("avg_cost", 0.0)
            current_price = report.get("current_price", 0.0)
            position_value = report.get("position_value", 0.0)

            # Ensure all values are numeric, convert if needed
            shares = float(shares) if isinstance(shares, (int, float)) else 0.0
            avg_cost = float(avg_cost) if isinstance(avg_cost, (int, float)) else 0.0
            current_price = float(current_price) if isinstance(current_price, (int, float)) else 0.0
            position_value = float(position_value) if isinstance(position_value, (int, float)) else 0.0

            weight_pct = (position_value / portfolio_value * 100) if portfolio_value > 0 else 0
            gain_loss_pct = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0
            
            # Show conversion info if applicable
            conversion_note = ""
            if conversion_info.get("converted"):
                conversion_note = f" (Converted from '{symbol}')"
            
            summary += f"""
- {ticker}: {shares} shares @ ${avg_cost:.2f} avg cost{conversion_note}
  Current Price: ${current_price:.2f}
  Position Value: ${position_value:,.2f} ({weight_pct:.1f}% of portfolio)
  Gain/Loss: {gain_loss_pct:+.2f}%
"""
        
        return summary
    
    def _build_stock_analysis_summary(self, stock_reports: List) -> str:
        """Build stock analysis summary from individual reports."""
        summary = "\nINDIVIDUAL STOCK ANALYSIS SUMMARY:\n\n"
        
        for stock_report in stock_reports:
            symbol = stock_report.get("symbol")  # Original input
            ticker = stock_report.get("ticker", symbol)  # Converted ticker
            analysis_result = stock_report.get("analysis_result", {})

            summary += f"=== {ticker} ===\n"
            if symbol != ticker:
                summary += f"Original Input: {symbol}\n"
            summary += f"Analysis Status: {analysis_result.get('status')}\n"

            if analysis_result.get("status") == "SUCCESS":
                # Extract key insights from the report
                report_text = analysis_result.get("report", "")

                # If it's a comprehensive analysis, extract probability data
                if "probability_analysis" in analysis_result:
                    summary += "Comprehensive Analysis: Available with probability assessment\n"
                elif "prediction" in analysis_result:
                    summary += "1-Month Prediction: Available\n"
                elif "scenario_analysis" in analysis_result:
                    summary += "Investment Scenario: Available\n"

                # Add a snippet of the report (first 500 chars)
                # Ensure report_text is a string
                if isinstance(report_text, dict):
                    report_text = str(report_text)
                summary += f"Report Summary: {report_text[:500]}...\n"
            else:
                summary += f"Analysis Error: {analysis_result.get('message', 'Unknown')}\n"

            summary += "\n"
        
        return summary
    
    def compile_final_report(self, orchestrated_data: Dict, 
                            recommendations: Dict) -> str:
        """
        Compile final portfolio report with all data and recommendations.
        
        Args:
            orchestrated_data: Output from PortfolioOrchestrator
            recommendations: Output from generate_recommendations
        
        Returns:
            str: Comprehensive portfolio report
        """
        portfolio_data = orchestrated_data.get("portfolio_data", {})
        stock_reports = orchestrated_data.get("stock_reports", [])
        portfolio_value = orchestrated_data.get("portfolio_value", 0.0)
        total_time = orchestrated_data.get("total_time", "0s")
        analysis_type = orchestrated_data.get("analysis_type", "unknown")
        
        report = f"""
{'='*80}
PORTFOLIO ANALYSIS & RECOMMENDATION REPORT
{'='*80}

PORTFOLIO OVERVIEW:
- Total Value: ${portfolio_value:,.2f}
- Number of Holdings: {len(stock_reports)}
- Analysis Type: {analysis_type}
- Analysis Time: {total_time}

POSITION BREAKDOWN:
"""
        
        for stock_report in stock_reports:
            symbol = stock_report.get("symbol")  # Original input
            ticker = stock_report.get("ticker", symbol)  # Converted ticker
            conversion_info = stock_report.get("conversion_info", {})
            shares = stock_report.get("shares", 0)
            avg_cost = stock_report.get("avg_cost", 0.0)
            current_price = stock_report.get("current_price", 0.0)
            position_value = stock_report.get("position_value", 0.0)
            
            # Ensure numeric types
            shares = float(shares) if isinstance(shares, (int, float)) else 0.0
            avg_cost = float(avg_cost) if isinstance(avg_cost, (int, float)) else 0.0
            current_price = float(current_price) if isinstance(current_price, (int, float)) else 0.0
            position_value = float(position_value) if isinstance(position_value, (int, float)) else 0.0
            
            weight_pct = (position_value / portfolio_value * 100) if portfolio_value > 0 else 0
            gain_loss_pct = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0
            
            # Show conversion info if applicable
            conversion_note = ""
            if conversion_info.get("converted"):
                conversion_note = f" (Converted from '{symbol}')"

            report += f"""
{ticker}{conversion_note}:
  Shares: {shares:.2f}
  Avg Cost: ${avg_cost:.2f}
  Current Price: ${current_price:.2f}
  Position Value: ${position_value:,.2f} ({weight_pct:.1f}%)
  Gain/Loss: {gain_loss_pct:+.2f}%
  Analysis Status: {stock_report['analysis_result'].get('status')}
"""
        
        report += f"\n{'='*80}\n"
        report += "PORTFOLIO RECOMMENDATIONS:\n"
        report += f"{'='*80}\n\n"
        
        if recommendations.get("status") == "SUCCESS":
            report += recommendations.get("recommendations", "")
        else:
            report += f"Recommendations Error: {recommendations.get('message', 'Not available')}\n"
        
        report += f"\n{'='*80}\n"
        report += "INDIVIDUAL STOCK REPORTS:\n"
        report += f"{'='*80}\n\n"
        
        for stock_report in stock_reports:
            symbol = stock_report.get("symbol")  # Original input
            ticker = stock_report.get("ticker", symbol)  # Converted ticker
            analysis_result = stock_report.get("analysis_result", {})

            report += f"\n{'='*80}\n"
            report += f"STOCK REPORT: {ticker}"
            if symbol != ticker:
                report += f" (Original Input: {symbol})"
            report += "\n"
            report += f"{'='*80}\n"

            if analysis_result.get("status") == "SUCCESS":
                report_text = analysis_result.get("report", "No report available")
                # Ensure report_text is a string
                if isinstance(report_text, dict):
                    report_text = str(report_text)
                report += report_text
            else:
                report += f"Analysis failed: {analysis_result.get('message', 'Unknown error')}\n"
        
        report += f"\n{'='*80}\n"
        report += "DISCLAIMER: This analysis is for educational purposes only.\n"
        report += "Past performance does not guarantee future results.\n"
        report += "Consult a licensed financial advisor before making investment decisions.\n"
        report += f"{'='*80}\n"
        
        return report


if __name__ == "__main__":
    # Test recommendation agent
    print("Testing Portfolio Recommendation Agent...")
    
    # Sample orchestrated data (simulating output from PortfolioOrchestrator)
    sample_orchestrated = {
        "portfolio_data": {
            "holdings": [
                {"symbol": "AAPL", "shares": 100, "avg_cost": 150.00},
                {"symbol": "TSLA", "shares": 50, "avg_cost": 200.00}
            ],
            "cash": 10000.00
        },
        "portfolio_value": 45000.00,
        "stock_reports": [
            {
                "symbol": "AAPL",
                "shares": 100,
                "avg_cost": 150.00,
                "current_price": 175.00,
                "position_value": 17500.00,
                "analysis_result": {
                    "status": "SUCCESS",
                    "report": "Sample AAPL analysis report..."
                }
            },
            {
                "symbol": "TSLA",
                "shares": 50,
                "avg_cost": 200.00,
                "current_price": 250.00,
                "position_value": 12500.00,
                "analysis_result": {
                    "status": "SUCCESS",
                    "report": "Sample TSLA analysis report..."
                }
            }
        ],
        "total_time": "90.5s",
        "analysis_type": "comprehensive"
    }
    
    agent = PortfolioRecommendationAgent()
    
    print("\nGenerating Portfolio Recommendations...")
    result = agent.generate_recommendations(sample_orchestrated)
    
    print(f"\nStatus: {result['status']}")
    if result['status'] == 'SUCCESS':
        print("\nRecommendations:")
        print(result['recommendations'])
    else:
        print(f"Error: {result.get('message')}")
