"""
Stock Analysis Agent
Analyzes individual stocks by fetching historical data, news, and technical indicators
to generate probability-based investment recommendations
"""

import os
import sys
import time
import warnings
from typing import Dict, Any, List
from dotenv import load_dotenv

# Suppress FutureWarning for google.generativeai
warnings.filterwarnings("ignore", category=FutureWarning)

import google.generativeai as genai

load_dotenv()

# Add tools directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

# Import tools
from stock_historical_data import get_year_historical_data, analyze_historical_performance
from tradingview_news import get_stock_news, get_stock_market_news
from tradingview_technical_analysis import get_technical_analysis, get_technical_indicators
from tradingview_price import get_price, format_symbol
from tradingview_market_data import get_market_data_exact, get_market_data_multi_exchange, get_company_info, get_analyst_recommendations
from tradingview_calendar import get_economic_calendar, get_earnings_calendar, get_dividends_calendar
from tradingview_leaderboards import get_stock_gainers, get_stock_losers, get_most_active_stocks
from world_economy import get_g20_gdp_growth, get_world_cpi, get_interest_rates
from tradingview_community import get_community_data
from tradingview_search import find_ticker_by_company_name


class StockAnalysisAgent:
    """
    Agent for analyzing individual stocks and generating probability-based recommendations.
    """
    
    def __init__(self, user_id: str = None):
        """Initialize the stock analysis agent with Gemini AI."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash')
                print("Stock Analysis Agent initialized with Gemini AI")
            except Exception as e:
                print(f"Error initializing Gemini AI: {e}")
                self.model = None
        else:
            print("Warning: GOOGLE_API_KEY not found")
            self.model = None
        
        self.user_id = user_id or "default_user"
    
    def _convert_to_ticker(self, input_symbol: str) -> tuple:
        """
        Convert company name to ticker symbol if needed.
        
        Args:
            input_symbol (str): Company name or ticker symbol (e.g., "Apple" or "AAPL")
        
        Returns:
            tuple: (ticker_symbol, conversion_info)
        """
        # Check if it looks like a ticker symbol (1-5 uppercase letters, maybe with numbers)
        import re
        ticker_pattern = r'^[A-Z]{1,5}[0-9]{0,2}$'
        
        if re.match(ticker_pattern, input_symbol):
            # It looks like a ticker symbol, use as-is
            return input_symbol, {
                "original_input": input_symbol,
                "converted": False,
                "type": "ticker_symbol"
            }
        
        # It looks like a company name, search for ticker
        ticker_result = find_ticker_by_company_name(input_symbol)
        
        if ticker_result['status'] == 'SUCCESS':
            return ticker_result['ticker'], {
                "original_input": input_symbol,
                "converted": True,
                "type": "company_name",
                "company_name": ticker_result['company_name'],
                "exchange": ticker_result['exchange']
            }
        else:
            # Search failed, try using the input as-is
            return input_symbol, {
                "original_input": input_symbol,
                "converted": False,
                "type": "unknown",
                "error": ticker_result.get('message', 'Search failed')
            }
    
    def analyze_investment_scenario(self, symbol: str, investment_amount: float = 10000, days: int = 100) -> Dict[str, Any]:
        """
        Perform comprehensive investment scenario analysis with best/worst/base cases.
        
        Args:
            symbol (str): Stock symbol or company name to analyze (e.g., "AAPL" or "Apple")
            investment_amount (float): Investment amount in USD (default: $10,000)
            days (int): Investment timeframe in days (default: 100 days)
        
        Returns:
            dict: Comprehensive scenario analysis with realistic ranges
        """
        execution_steps = []
        start_time = time.time()
        conversion_info = {}
        
        try:
            # Convert company name to ticker symbol if needed
            ticker_symbol, conversion_info = self._convert_to_ticker(symbol)
            
            execution_steps.append({
                "step": 0,
                "action": f"Input conversion: {symbol} -> {ticker_symbol}",
                "status": "SUCCESS",
                "conversion_info": conversion_info,
                "duration": f"{time.time() - start_time:.2f}s"
            })
            
            # Reset start time for actual analysis
            start_time = time.time()
            # Step 1: Get current price
            step_start = time.time()
            price_result = get_price(ticker_symbol)
            execution_steps.append({
                "step": 1,
                "action": "Fetch Current Price",
                "status": price_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 2: Get comprehensive market data for volatility metrics
            step_start = time.time()
            market_data_result = get_market_data_multi_exchange(ticker_symbol, ["NASDAQ", "NYSE"])
            execution_steps.append({
                "step": 2,
                "action": "Fetch Market Data (Volatility Metrics)",
                "status": market_data_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 3: Get 1-year historical data for volatility analysis
            step_start = time.time()
            historical_result = get_year_historical_data(ticker_symbol)
            execution_steps.append({
                "step": 3,
                "action": "Fetch Historical Data (Volatility Analysis)",
                "status": historical_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 4: Get technical analysis for trend direction
            step_start = time.time()
            technical_result = get_technical_analysis(ticker_symbol)
            execution_steps.append({
                "step": 4,
                "action": "Fetch Technical Analysis (Trend)",
                "status": technical_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 5: Get technical indicators for volatility
            step_start = time.time()
            indicators_result = get_technical_indicators(ticker_symbol)
            execution_steps.append({
                "step": 5,
                "action": "Fetch Technical Indicators (Volatility)",
                "status": indicators_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 6: Get news for sentiment analysis
            step_start = time.time()
            news_result = get_stock_news(ticker_symbol)
            if news_result.get('status') != 'SUCCESS':
                news_result = get_stock_market_news()
            execution_steps.append({
                "step": 6,
                "action": "Fetch News (Sentiment)",
                "status": news_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 7: Generate scenario analysis using AI
            step_start = time.time()
            scenario_analysis = self._generate_scenario_analysis(
                ticker_symbol, investment_amount, days, price_result, market_data_result,
                historical_result, technical_result, indicators_result, news_result
            )
            execution_steps.append({
                "step": 7,
                "action": "Generate Investment Scenario Analysis",
                "status": "SUCCESS",
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Compile scenario report
            report = self._compile_scenario_report(
                ticker_symbol, investment_amount, days, price_result, market_data_result,
                historical_result, scenario_analysis, conversion_info
            )
            
            return {
                "status": "SUCCESS",
                "input": symbol,
                "ticker": ticker_symbol,
                "investment_amount": investment_amount,
                "timeframe_days": days,
                "report": report,
                "scenario_analysis": scenario_analysis,
                "execution_steps": execution_steps,
                "total_time": f"{time.time() - start_time:.2f}s",
                "analysis_type": "investment scenario analysis",
                "tools_used": 6,
                "conversion_info": conversion_info
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Error analyzing investment scenario: {str(e)}",
                "execution_steps": execution_steps,
                "total_time": f"{time.time() - start_time:.2f}s"
            }

    def analyze_stock_one_month(self, symbol: str) -> Dict[str, Any]:
        """
        Perform focused 1-month stock analysis with clear prediction.
        
        Args:
            symbol (str): Stock symbol or company name to analyze (e.g., "AAPL" or "Apple")
        
        Returns:
            dict: Focused 1-month analysis with clear increase/decrease prediction
        """
        execution_steps = []
        start_time = time.time()
        
        try:
            # Convert company name to ticker symbol if needed
            ticker_symbol, conversion_info = self._convert_to_ticker(symbol)
            
            execution_steps.append({
                "step": 0,
                "action": f"Input conversion: {symbol} -> {ticker_symbol}",
                "status": "SUCCESS",
                "conversion_info": conversion_info,
                "duration": f"{time.time() - start_time:.2f}s"
            })
            
            # Reset start time for actual analysis
            start_time = time.time()
            # Step 1: Get current price
            step_start = time.time()
            price_result = get_price(ticker_symbol)
            execution_steps.append({
                "step": 1,
                "action": "Fetch Current Price",
                "status": price_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 2: Get comprehensive market data (15 sections) for fundamentals
            step_start = time.time()
            market_data_result = get_market_data_multi_exchange(ticker_symbol, ["NASDAQ", "NYSE"])
            execution_steps.append({
                "step": 2,
                "action": "Fetch Comprehensive Market Data",
                "status": market_data_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 3: Get 1-year historical data for pattern analysis
            step_start = time.time()
            historical_result = get_year_historical_data(ticker_symbol)
            execution_steps.append({
                "step": 3,
                "action": "Fetch 1-Year Historical Data (Pattern Analysis)",
                "status": historical_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 4: Get technical analysis for signals
            step_start = time.time()
            technical_result = get_technical_analysis(ticker_symbol)
            execution_steps.append({
                "step": 4,
                "action": "Fetch Technical Analysis",
                "status": technical_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 5: Get technical indicators for detailed signals
            step_start = time.time()
            indicators_result = get_technical_indicators(ticker_symbol)
            execution_steps.append({
                "step": 5,
                "action": "Fetch Technical Indicators",
                "status": indicators_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 6: Get stock news for recent sentiment
            step_start = time.time()
            news_result = get_stock_news(ticker_symbol)
            if news_result.get('status') != 'SUCCESS':
                news_result = get_stock_market_news()
            execution_steps.append({
                "step": 6,
                "action": "Fetch Recent News",
                "status": news_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 7: Get analyst recommendations
            step_start = time.time()
            analyst_recommendations_result = get_analyst_recommendations(ticker_symbol)
            execution_steps.append({
                "step": 7,
                "action": "Fetch Analyst Recommendations",
                "status": analyst_recommendations_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 8: Get economic calendar for market context
            step_start = time.time()
            from datetime import datetime, timedelta
            today = datetime.now()
            month_later = today + timedelta(days=30)
            from_timestamp = int(today.timestamp())
            to_timestamp = int(month_later.timestamp())
            economic_calendar_result = get_economic_calendar(
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp
            )
            execution_steps.append({
                "step": 8,
                "action": "Fetch Economic Calendar (30-day context)",
                "status": economic_calendar_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 9: Generate focused 1-month prediction using AI
            step_start = time.time()
            prediction_analysis = self._generate_one_month_prediction(
                ticker_symbol, price_result, market_data_result, historical_result,
                technical_result, indicators_result, news_result,
                analyst_recommendations_result, economic_calendar_result
            )
            execution_steps.append({
                "step": 9,
                "action": "Generate 1-Month Prediction",
                "status": "SUCCESS",
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Compile focused report
            report = self._compile_one_month_report(
                ticker_symbol, price_result, market_data_result, historical_result,
                technical_result, indicators_result, news_result,
                analyst_recommendations_result, economic_calendar_result,
                prediction_analysis, conversion_info
            )
            
            return {
                "status": "SUCCESS",
                "input": symbol,
                "ticker": ticker_symbol,
                "report": report,
                "prediction": prediction_analysis,
                "execution_steps": execution_steps,
                "total_time": f"{time.time() - start_time:.2f}s",
                "analysis_type": "1-month prediction",
                "tools_used": 8,
                "conversion_info": conversion_info
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Error analyzing stock: {str(e)}",
                "execution_steps": execution_steps,
                "total_time": f"{time.time() - start_time:.2f}s"
            }

    def analyze_stock(self, symbol: str) -> Dict[str, Any]:
        """
        Perform comprehensive analysis of a single stock using ALL available tools.
        
        Args:
            symbol (str): Stock symbol to analyze (e.g., "AAPL", "TSLA")
        
        Returns:
            dict: Comprehensive analysis report with probability assessment
        """
        execution_steps = []
        start_time = time.time()
        
        try:
            # Step 1: Get current price
            step_start = time.time()
            price_result = get_price(symbol)
            execution_steps.append({
                "step": 1,
                "action": "Fetch Current Price",
                "status": price_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 2: Get comprehensive market data (NEW - 15 data sections)
            step_start = time.time()
            market_data_result = get_market_data_multi_exchange(symbol, ["NASDAQ", "NYSE"])
            execution_steps.append({
                "step": 2,
                "action": "Fetch Comprehensive Market Data (15 sections)",
                "status": market_data_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 3: Get company information (NEW)
            step_start = time.time()
            company_info_result = get_company_info(symbol)
            execution_steps.append({
                "step": 3,
                "action": "Fetch Company Information",
                "status": company_info_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 4: Get analyst recommendations (NEW)
            step_start = time.time()
            analyst_recommendations_result = get_analyst_recommendations(symbol)
            execution_steps.append({
                "step": 4,
                "action": "Fetch Analyst Recommendations",
                "status": analyst_recommendations_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 5: Get 1-year historical data
            step_start = time.time()
            historical_result = get_year_historical_data(symbol)
            execution_steps.append({
                "step": 5,
                "action": "Fetch 1-Year Historical Data",
                "status": historical_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 6: Get stock news (try symbol-specific first, then general stock market news)
            step_start = time.time()
            news_result = get_stock_news(symbol)
            # If symbol-specific news fails, fall back to general stock market news
            if news_result.get('status') != 'SUCCESS':
                news_result = get_stock_market_news()
            execution_steps.append({
                "step": 6,
                "action": "Fetch Current News",
                "status": news_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 7: Get technical analysis
            step_start = time.time()
            technical_result = get_technical_analysis(symbol)
            execution_steps.append({
                "step": 7,
                "action": "Fetch Technical Analysis",
                "status": technical_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 8: Get detailed technical indicators
            step_start = time.time()
            indicators_result = get_technical_indicators(symbol)
            execution_steps.append({
                "step": 8,
                "action": "Fetch Technical Indicators",
                "status": indicators_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 9: Get community data (NEW)
            step_start = time.time()
            community_result = get_community_data(symbol)
            execution_steps.append({
                "step": 9,
                "action": "Fetch Community Sentiment Data",
                "status": community_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 10: Get economic calendar (NEW - market context)
            step_start = time.time()
            from datetime import datetime, timedelta
            today = datetime.now()
            week_later = today + timedelta(days=7)
            from_timestamp = int(today.timestamp())
            to_timestamp = int(week_later.timestamp())
            economic_calendar_result = get_economic_calendar(
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp
            )
            execution_steps.append({
                "step": 10,
                "action": "Fetch Economic Calendar (market context)",
                "status": economic_calendar_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 11: Get earnings calendar (NEW - company-specific)
            step_start = time.time()
            earnings_calendar_result = get_earnings_calendar(
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp
            )
            execution_steps.append({
                "step": 11,
                "action": "Fetch Earnings Calendar (company events)",
                "status": earnings_calendar_result.get("status"),
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 12: Get market leaderboards (NEW - market comparison)
            step_start = time.time()
            gainers_result = get_stock_gainers()
            losers_result = get_stock_losers()
            active_result = get_most_active_stocks()
            execution_steps.append({
                "step": 12,
                "action": "Fetch Market Leaderboards (comparison context)",
                "status": "SUCCESS" if all([
                    gainers_result.get("status") == "SUCCESS",
                    losers_result.get("status") == "SUCCESS", 
                    active_result.get("status") == "SUCCESS"
                ]) else "PARTIAL",
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 13: Get world economy indicators (NEW - macro context)
            step_start = time.time()
            gdp_result = get_g20_gdp_growth()
            interest_rates_result = get_interest_rates()
            execution_steps.append({
                "step": 13,
                "action": "Fetch World Economy Indicators (macro context)",
                "status": "SUCCESS" if all([
                    gdp_result.get("status") == "SUCCESS",
                    interest_rates_result.get("status") == "SUCCESS"
                ]) else "PARTIAL",
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Step 14: Generate comprehensive probability analysis using AI
            step_start = time.time()
            probability_analysis = self._generate_comprehensive_analysis(
                symbol, price_result, market_data_result, company_info_result,
                analyst_recommendations_result, historical_result, news_result,
                technical_result, indicators_result, community_result,
                economic_calendar_result, earnings_calendar_result,
                gainers_result, losers_result, active_result,
                gdp_result, interest_rates_result
            )
            execution_steps.append({
                "step": 14,
                "action": "Generate Comprehensive Probability Analysis",
                "status": "SUCCESS",
                "duration": f"{time.time() - step_start:.2f}s"
            })
            
            # Compile final comprehensive report
            report = self._compile_comprehensive_report(
                symbol, price_result, market_data_result, company_info_result,
                analyst_recommendations_result, historical_result, news_result,
                technical_result, indicators_result, community_result,
                economic_calendar_result, earnings_calendar_result,
                gainers_result, losers_result, active_result,
                gdp_result, interest_rates_result, probability_analysis
            )
            
            return {
                "status": "SUCCESS",
                "symbol": symbol,
                "report": report,
                "execution_steps": execution_steps,
                "total_time": f"{time.time() - start_time:.2f}s",
                "tools_used": 13
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Error analyzing stock: {str(e)}",
                "execution_steps": execution_steps,
                "total_time": f"{time.time() - start_time:.2f}s"
            }
    
    def _generate_scenario_analysis(self, symbol: str, investment_amount: float, days: int,
                                  price_result: Dict, market_data_result: Dict,
                                  historical_result: Dict, technical_result: Dict,
                                  indicators_result: Dict, news_result: Dict) -> Dict[str, Any]:
        """
        Generate comprehensive investment scenario analysis with realistic ranges.
        
        Args:
            symbol: Stock symbol
            investment_amount: Investment amount in USD
            days: Investment timeframe in days
            price_result: Current price data
            market_data_result: Market data for volatility
            historical_result: Historical data for volatility analysis
            technical_result: Technical analysis for trend
            indicators_result: Technical indicators for volatility
            news_result: News for sentiment
        
        Returns:
            dict: Comprehensive scenario analysis with best/worst/base cases
        """
        if not self.model:
            return {
                "status": "ERROR",
                "message": "AI model not available"
            }
        
        try:
            # Prepare data summary for scenario analysis
            data_summary = f"""
INVESTMENT SCENARIO ANALYSIS FOR: {symbol}
Investment Amount: ${investment_amount:,.2f}
Timeframe: {days} days

CURRENT SITUATION:
"""
            
            # Add current price
            if price_result.get('status') == 'SUCCESS':
                price_data = price_result.get('data', {})
                if price_data.get('success'):
                    actual_data = price_data.get('data', {})
                    current = actual_data.get('current', {})
                    info = actual_data.get('info', {})
                    current_price = current.get('close', 0)
                    shares = investment_amount / current_price if current_price > 0 else 0
                    
                    data_summary += f"""
- Current Price: ${current_price:.2f}
- Investment Amount: ${investment_amount:,.2f}
- Shares Purchased: {shares:.2f}
- Company: {info.get('description', 'N/A')}
"""
            
            # Add volatility metrics from market data
            if market_data_result.get('status') == 'SUCCESS':
                market_data = market_data_result.get('data', {})
                if market_data.get('success'):
                    inner_data = market_data.get('data', {})
                    data_summary += f"""
VOLATILITY METRICS:
"""
                    if 'indicators' in inner_data:
                        indicators = inner_data['indicators']
                        beta = indicators.get('beta_1_year', 1.0)
                        week_high = indicators.get('price_52_week_high', 0)
                        week_low = indicators.get('price_52_week_low', 0)
                        volatility_range = ((week_high - week_low) / week_low * 100) if week_low > 0 else 0
                        
                        data_summary += f"""
- Beta (1Y): {beta:.2f} (Market sensitivity)
- 52-Week Range: ${week_low:.2f} - ${week_high:.2f}
- Historical Volatility Range: {volatility_range:.1f}%
- P/E Ratio: {indicators.get('price_earnings', 'N/A')}
"""
            
            # Add historical volatility context
            if historical_result.get('status') == 'SUCCESS':
                data_summary += """
HISTORICAL VOLATILITY ANALYSIS:
- 1-Year historical data available for volatility calculation
- Historical price patterns and volatility trends accessible
- Support and resistance levels identifiable
"""
            
            # Add technical trend
            if technical_result.get('status') == 'SUCCESS':
                data_summary += """
TECHNICAL TREND ANALYSIS:
- Current trend direction available
- Chart patterns and momentum signals accessible
"""
            
            # Add indicators for volatility
            if indicators_result.get('status') == 'SUCCESS':
                data_summary += """
TECHNICAL INDICATORS (Volatility):
- RSI (Relative Strength Index) available
- MACD and momentum indicators accessible
- Volatility indicators (ATR, Bollinger Bands) available
"""
            
            # Add sentiment context
            if news_result.get('status') == 'SUCCESS':
                data_summary += """
MARKET SENTIMENT:
- Recent news sentiment analysis available
- Current market conditions and company-specific news
"""
            
            prompt = f"""
            Based on the data above, provide a COMPREHENSIVE INVESTMENT SCENARIO ANALYSIS for {symbol}.
            
            Investment: ${investment_amount:,.2f}
            Timeframe: {days} days
            Current shares: {investment_amount / price_result.get('data', {}).get('data', {}).get('current', {}).get('close', 1):.2f}
            
            Provide THREE SCENARIOS with REALISTIC ranges based on historical volatility:
            
            1. BEST CASE SCENARIO (Optimistic but realistic):
               - Expected price increase: X% to Y%
               - Investment value: $[amount]
               - Profit: $[amount]
               - Probability: X%
               - What conditions would make this happen?
            
            2. BASE CASE SCENARIO (Most likely outcome):
               - Expected price change: X% to Y%
               - Investment value: $[amount]
               - Profit/Loss: $[amount]
               - Probability: X%
               - Why is this most likely?
            
            3. WORST CASE SCENARIO (Risk management):
               - Maximum expected decline: X% to Y%
               - Investment value: $[amount]
               - Maximum loss: $[amount]
               - Probability: X%
               - What could cause this?
            
            RISK ANALYSIS:
            - Maximum drawdown risk: X%
            - Stop-loss recommendation: $[price]
            - Position size recommendation: X% of portfolio
            - Risk/reward ratio: X:Y
            
            CONFIDENCE FACTORS:
            - Historical volatility support: [High/Medium/Low]
            - Technical trend confirmation: [Strong/Weak/Neutral]
            - Market sentiment alignment: [Positive/Negative/Neutral]
            - Overall confidence in scenarios: [X]%
            
            IMPORTANT: Be realistic and conservative. Use historical volatility data to calculate realistic ranges.
            Don't promise unrealistic returns. Focus on risk management and realistic expectations.
            
            Format as a clean, professional investment analysis that helps investors make informed decisions.
            """
            
            response = self.model.generate_content(prompt)
            
            return {
                "status": "SUCCESS",
                "analysis": response.text,
                "investment_amount": investment_amount,
                "timeframe_days": days,
                "focus": "comprehensive scenario analysis with risk management"
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Error generating scenario analysis: {str(e)}"
            }

    def _compile_scenario_report(self, symbol: str, investment_amount: float, days: int,
                               price_result: Dict, market_data_result: Dict,
                               historical_result: Dict, scenario_analysis: Dict,
                               conversion_info: Dict) -> str:
        """
        Compile comprehensive scenario analysis report.
        """
        # Calculate shares based on current price
        shares = 0
        current_price = 0
        if price_result.get('status') == 'SUCCESS':
            price_data = price_result.get('data', {})
            if price_data.get('success'):
                actual_data = price_data.get('data', {})
                current = actual_data.get('current', {})
                current_price = current.get('close', 0)
                shares = investment_amount / current_price if current_price > 0 else 0
        
        report = f"""
{'='*80}
COMPREHENSIVE INVESTMENT SCENARIO ANALYSIS: {symbol}
{'='*80}

INPUT CONVERSION:
- Original Input: {conversion_info.get('original_input', 'N/A')}
- Converted: {conversion_info.get('converted', False)}
- Input Type: {conversion_info.get('type', 'N/A')}
"""
        
        if conversion_info.get('converted'):
            report += f"- Company Name: {conversion_info.get('company_name', 'N/A')}\n"
            report += f"- Exchange: {conversion_info.get('exchange', 'N/A')}\n"
        
        report += f"""
INVESTMENT DETAILS:
- Investment Amount: ${investment_amount:,.2f}
- Timeframe: {days} days
- Current Price: ${current_price:.2f}
- Shares Purchased: {shares:.2f}
- Analysis Type: Comprehensive Scenario Planning
- Tools Used: 6 (Price, Volatility Metrics, Historical Analysis, 
             Technical Trend, Volatility Indicators, Market Sentiment)

"""
        
        # Add volatility metrics
        if market_data_result.get('status') == 'SUCCESS':
            market_data = market_data_result.get('data', {})
            if market_data.get('success'):
                inner_data = market_data.get('data', {})
                if 'indicators' in inner_data:
                    indicators = inner_data['indicators']
                    beta = indicators.get('beta_1_year', 1.0)
                    week_high = indicators.get('price_52_week_high', 0)
                    week_low = indicators.get('price_52_week_low', 0)
                    volatility_range = ((week_high - week_low) / week_low * 100) if week_low > 0 else 0
                    
                    report += f"VOLATILITY PROFILE:\n"
                    report += f"Beta (Market Sensitivity): {beta:.2f}\n"
                    report += f"52-Week Range: ${week_low:.2f} - ${week_high:.2f}\n"
                    report += f"Historical Volatility: {volatility_range:.1f}%\n"
                    report += f"P/E Ratio: {indicators.get('price_earnings', 'N/A')}\n\n"
        
        # Add the AI scenario analysis
        if scenario_analysis.get('status') == 'SUCCESS':
            report += f"INVESTMENT SCENARIOS:\n"
            report += f"{scenario_analysis.get('analysis')}\n\n"
        else:
            report += f"Scenario Analysis: {scenario_analysis.get('message', 'Not available')}\n\n"
        
        report += f"{'='*80}\n"
        report += f"DISCLAIMER: This analysis is for educational purposes only.\n"
        report += f"Past performance does not guarantee future results.\n"
        report += f"Invest based on your own research and risk tolerance.\n"
        report += f"{'='*80}\n"
        
        return report

    def _generate_one_month_prediction(self, symbol: str, price_result: Dict,
                                     market_data_result: Dict, historical_result: Dict,
                                     technical_result: Dict, indicators_result: Dict,
                                     news_result: Dict, analyst_recommendations_result: Dict,
                                     economic_calendar_result: Dict) -> Dict[str, Any]:
        """
        Generate focused 1-month price prediction based on historical patterns and key factors.
        
        Args:
            symbol: Stock symbol
            price_result: Current price data
            market_data_result: Comprehensive market data
            historical_result: Historical data for pattern analysis
            technical_result: Technical analysis
            indicators_result: Technical indicators
            news_result: News sentiment
            analyst_recommendations_result: Analyst recommendations
            economic_calendar_result: Economic calendar for context
        
        Returns:
            dict: Focused 1-month prediction with clear increase/decrease and percentage
        """
        if not self.model:
            return {
                "status": "ERROR",
                "message": "AI model not available"
            }
        
        try:
            # Prepare focused data summary for 1-month prediction
            data_summary = f"""
1-MONTH STOCK PRICE PREDICTION FOR: {symbol}

CURRENT SITUATION:
"""
            
            # Add current price - check both status and nested success flag
            price_available = False
            if price_result.get('status') == 'SUCCESS':
                price_data = price_result.get('data', {})
                if price_data.get('success'):
                    actual_data = price_data.get('data', {})
                    current = actual_data.get('current', {})
                    info = actual_data.get('info', {})
                    if current.get('close') or info.get('description'):
                        price_available = True
                        data_summary += f"""
- Current Price: ${current.get('close', 'N/A')}
- Company: {info.get('description', 'N/A')}
- Exchange: {info.get('exchange', 'N/A')}
- Volume: {current.get('volume', 'N/A')}
"""
            
            if not price_available:
                data_summary += f"""
- Current Price: Data not available from API
- Company: {symbol}
- Note: This stock may not be available on the TradingView data feed
"""
            
            # Add comprehensive market data fundamentals - check nested success flag
            market_data_available = False
            if market_data_result.get('status') == 'SUCCESS':
                market_data = market_data_result.get('data', {})
                if market_data.get('success'):
                    inner_data = market_data.get('data', {})
                    
                    if 'indicators' in inner_data:
                        indicators = inner_data['indicators']
                        if indicators.get('market_cap_calc') or indicators.get('price_earnings'):
                            market_data_available = True
                            data_summary += f"\nFUNDAMENTAL DATA:\n"
                            data_summary += f"""
- Market Cap: ${indicators.get('market_cap_calc', 0):,.0f}
- P/E Ratio: {indicators.get('price_earnings', 'N/A')}
- 52-Week High: ${indicators.get('price_52_week_high', 'N/A')}
- 52-Week Low: ${indicators.get('price_52_week_low', 'N/A')}
- Beta (1Y): {indicators.get('beta_1_year', 'N/A')}
"""
                    
                    if 'ttm' in inner_data:
                        ttm = inner_data['ttm']
                        if ttm.get('earnings_per_share_ttm') or ttm.get('total_revenue_ttm'):
                            market_data_available = True
                            if not data_summary.endswith("FUNDAMENTAL DATA:\n"):
                                data_summary += f"\nFUNDAMENTAL DATA:\n"
                            data_summary += f"""
- EPS (TTM): ${ttm.get('earnings_per_share_ttm', 'N/A')}
- Revenue (TTM): ${ttm.get('total_revenue_ttm', 0):,.0f}
- Net Margin (TTM): {ttm.get('net_margin_ttm', 'N/A')}%
- Gross Margin (TTM): {ttm.get('gross_margin_ttm', 'N/A')}%
"""
            
            # Add historical data availability
            if historical_result.get('status') == 'SUCCESS':
                hist_data = historical_result.get('data', {})
                if hist_data.get('success') or hist_data.get('prices'):
                    data_summary += """
HISTORICAL PATTERNS:
- 1-Year Historical Data: Available for pattern analysis
- Price trends and patterns can be analyzed
- Support and resistance levels identifiable
"""
            
            # Add technical signals
            if technical_result.get('status') == 'SUCCESS':
                tech_data = technical_result.get('data', {})
                if tech_data.get('success') or tech_data.get('summary'):
                    data_summary += """
TECHNICAL ANALYSIS:
- Technical signals and indicators available
- Chart patterns and trend analysis possible
"""
            
            # Add indicators
            if indicators_result.get('status') == 'SUCCESS':
                ind_data = indicators_result.get('data', {})
                if ind_data.get('success') or ind_data.get('indicators'):
                    data_summary += """
TECHNICAL INDICATORS:
- RSI, MACD, moving averages available
- Momentum and volatility indicators accessible
"""
            
            # Add news sentiment
            if news_result.get('status') == 'SUCCESS':
                news_data = news_result.get('data', {})
                if news_data.get('success') or news_data.get('news'):
                    data_summary += """
RECENT NEWS SENTIMENT:
- Current news articles and sentiment available
- Recent company developments and market news
"""
            
            # Add analyst views
            if analyst_recommendations_result.get('status') == 'SUCCESS':
                analyst_data = analyst_recommendations_result.get('data', {})
                if analyst_data.get('success') or analyst_data.get('recommendations'):
                    data_summary += """
ANALYST RECOMMENDATIONS:
- Professional analyst ratings available
- Price targets and consensus estimates
"""
            
            # Add economic context
            if economic_calendar_result.get('status') == 'SUCCESS':
                econ_data = economic_calendar_result.get('data', {})
                if econ_data.get('success') or econ_data.get('events'):
                    data_summary += """
ECONOMIC CONTEXT (Next 30 Days):
- Upcoming economic events scheduled
- Market-moving announcements in timeline
"""
            
            prompt = f"""
            Based on the data above, provide a CLEAN, FOCUSED 1-month price prediction for {symbol}.
            
            IMPORTANT NOTES:
            - The data above includes ONLY the information that was successfully retrieved from the API
            - Some data sections may be missing if the API doesn't have that information for this stock
            - If you have at least the current price and company name, you should provide a prediction based on available data
            - If you have very limited data (e.g., only current price), provide a prediction with LOW confidence and explain the limitations
            - Only state "cannot provide prediction" if you have absolutely no data (not even current price)
            
            If you have sufficient data to make a prediction, focus on these specific requirements:
            
            1. CLEAR PREDICTION: Will the stock INCREASE or DECREASE in the next 30 days?
            2. SPECIFIC PERCENTAGE: How much will it increase or decrease? (Give a specific percentage range)
            3. HISTORICAL PATTERNS: What historical patterns support this prediction?
            4. KEY FACTORS: What are the 3-5 most important factors driving this prediction?
            5. CONFIDENCE LEVEL: How confident are you in this prediction? (0-100%)
            6. TARGET PRICE: What is your target price in 30 days?
            
            Format your response as a CLEAN, ACTIONABLE analysis:
            
            PREDICTION: [INCREASE/DECREASE] by [X% to Y%]
            TARGET PRICE: $[price] in 30 days
            CONFIDENCE: [X]%
            
            HISTORICAL PATTERNS SUPPORTING THIS:
            - [Pattern 1]
            - [Pattern 2]
            - [Pattern 3]
            
            KEY FACTORS:
            1. [Factor 1] - [Why it matters]
            2. [Factor 2] - [Why it matters]
            3. [Factor 3] - [Why it matters]
            
            RISK CONSIDERATIONS:
            - [Risk 1]
            - [Risk 2]
            
            Keep it concise, clear, and focused on the 1-month timeframe.
            """
            
            # Combine data_summary with prompt
            full_prompt = data_summary + "\n" + prompt
            
            response = self.model.generate_content(full_prompt)
            
            return {
                "status": "SUCCESS",
                "analysis": response.text,
                "timeframe": "1-month",
                "focus": "price prediction with historical patterns"
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Error generating prediction: {str(e)}"
            }

    def _compile_one_month_report(self, symbol: str, price_result: Dict,
                                  market_data_result: Dict, historical_result: Dict,
                                  technical_result: Dict, indicators_result: Dict,
                                  news_result: Dict, analyst_recommendations_result: Dict,
                                  economic_calendar_result: Dict, prediction_analysis: Dict,
                                  conversion_info: Dict) -> str:
        """
        Compile clean, focused 1-month prediction report.
        """
        report = f"""
{'='*80}
1-MONTH STOCK PRICE PREDICTION: {symbol}
{'='*80}

INPUT CONVERSION:
- Original Input: {conversion_info.get('original_input', 'N/A')}
- Converted: {conversion_info.get('converted', False)}
- Input Type: {conversion_info.get('type', 'N/A')}
"""
        
        if conversion_info.get('converted'):
            report += f"- Company Name: {conversion_info.get('company_name', 'N/A')}\n"
            report += f"- Exchange: {conversion_info.get('exchange', 'N/A')}\n"
        
        report += f"""
ANALYSIS TYPE: Focused 1-Month Prediction
TOOLS USED: 8 (Price, Market Data, Historical Patterns, Technical Analysis, 
             Indicators, News, Analyst Views, Economic Context)

"""
        
        # Add current price information
        if price_result.get('status') == 'SUCCESS':
            price_data = price_result.get('data', {})
            if price_data.get('success'):
                actual_data = price_data.get('data', {})
                current = actual_data.get('current', {})
                info = actual_data.get('info', {})
                
                report += f"CURRENT SITUATION:\n"
                report += f"Symbol: {symbol}\n"
                report += f"Company: {info.get('description', 'N/A')}\n"
                report += f"Current Price: ${current.get('close', 'N/A')}\n"
                report += f"52-Week Range: ${market_data_result.get('data', {}).get('data', {}).get('indicators', {}).get('price_52_week_low', 'N/A')} - ${market_data_result.get('data', {}).get('data', {}).get('indicators', {}).get('price_52_week_high', 'N/A')}\n\n"
        
        # Add the AI prediction
        if prediction_analysis.get('status') == 'SUCCESS':
            report += f"1-MONTH PREDICTION:\n"
            report += f"{prediction_analysis.get('analysis')}\n\n"
        else:
            report += f"Prediction: {prediction_analysis.get('message', 'Not available')}\n\n"
        
        report += f"{'='*80}\n"
        report += f"Analysis Method: Historical Patterns + Key Factors\n"
        report += f"Timeframe: Next 30 Days\n"
        report += f"{'='*80}\n"
        
        return report

    def _generate_comprehensive_analysis(self, symbol: str, price_result: Dict,
                                        market_data_result: Dict, company_info_result: Dict,
                                        analyst_recommendations_result: Dict, historical_result: Dict,
                                        news_result: Dict, technical_result: Dict,
                                        indicators_result: Dict, community_result: Dict,
                                        economic_calendar_result: Dict, earnings_calendar_result: Dict,
                                        gainers_result: Dict, losers_result: Dict, active_result: Dict,
                                        gdp_result: Dict, interest_rates_result: Dict) -> Dict[str, Any]:
        """
        Use AI to generate comprehensive probability-based analysis from ALL data sources.
        
        Args:
            symbol: Stock symbol
            price_result: Current price data
            market_data_result: Comprehensive market data (15 sections)
            company_info_result: Company information
            analyst_recommendations_result: Analyst recommendations
            historical_result: Historical data
            news_result: News data
            technical_result: Technical analysis
            indicators_result: Technical indicators
            community_result: Community sentiment data
            economic_calendar_result: Economic calendar
            earnings_calendar_result: Earnings calendar
            gainers_result: Stock gainers leaderboard
            losers_result: Stock losers leaderboard
            active_result: Most active stocks
            gdp_result: GDP growth data
            interest_rates_result: Interest rates data
        
        Returns:
            dict: Comprehensive probability analysis with buy/sell/hold probabilities
        """
        if not self.model:
            return {
                "status": "ERROR",
                "message": "AI model not available"
            }
        
        try:
            # Prepare comprehensive data summary for AI with actual data from ALL sources
            data_summary = f"""
COMPREHENSIVE STOCK ANALYSIS FOR: {symbol}

"""
            
            # Add price data if available
            if price_result.get('status') == 'SUCCESS':
                price_data = price_result.get('data', {})
                if price_data.get('success'):
                    actual_data = price_data.get('data', {})
                    current = actual_data.get('current', {})
                    info = actual_data.get('info', {})
                    data_summary += f"""
CURRENT PRICE DATA:
- Company: {info.get('description', 'N/A')}
- Current Price: ${current.get('close', 'N/A')}
- Open: ${current.get('open', 'N/A')}
- High: ${current.get('max', 'N/A')}
- Low: ${current.get('min', 'N/A')}
- Volume: {current.get('volume', 'N/A')}
- Exchange: {info.get('exchange', 'N/A')}
"""
                else:
                    data_summary += f"Current Price Data: Available but API returned error - {price_data.get('msg', 'Unknown error')}\n"
            else:
                data_summary += f"Current Price Data: {price_result.get('message', 'Not available')}\n"
            
            # Add comprehensive market data (NEW)
            if market_data_result.get('status') == 'SUCCESS':
                market_data = market_data_result.get('data', {})
                if market_data.get('success'):
                    inner_data = market_data.get('data', {})
                    data_summary += f"""
COMPREHENSIVE MARKET DATA (15 sections):
- Available sections: {list(inner_data.keys())}
"""
                    if 'company' in inner_data:
                        company = inner_data['company']
                        data_summary += f"""
  Company Details:
  - CEO: {company.get('ceo', 'N/A')}
  - Sector: {company.get('sector', 'N/A')}
  - Industry: {company.get('industry', 'N/A')}
  - Employees: {company.get('number_of_employees', 'N/A')}
  - Founded: {company.get('founded', 'N/A')}
  - Country: {company.get('country', 'N/A')}
"""
                    if 'indicators' in inner_data:
                        indicators = inner_data['indicators']
                        data_summary += f"""
  Key Indicators:
  - Market Cap: ${indicators.get('market_cap_calc', 0):,.0f}
  - P/E Ratio: {indicators.get('price_earnings', 'N/A')}
  - 52-Week High: ${indicators.get('price_52_week_high', 'N/A')}
  - 52-Week Low: ${indicators.get('price_52_week_low', 'N/A')}
  - Beta (1Y): {indicators.get('beta_1_year', 'N/A')}
"""
                    if 'ttm' in inner_data:
                        ttm = inner_data['ttm']
                        data_summary += f"""
  TTM Metrics:
  - EPS (TTM): ${ttm.get('earnings_per_share_ttm', 'N/A')}
  - Revenue (TTM): ${ttm.get('total_revenue_ttm', 0):,.0f}
  - Net Margin (TTM): {ttm.get('net_margin_ttm', 'N/A')}%
  - Gross Margin (TTM): {ttm.get('gross_margin_ttm', 'N/A')}%
"""
                else:
                    data_summary += f"Comprehensive Market Data: Available but API returned error - {market_data.get('msg', 'Unknown error')}\n"
            else:
                data_summary += f"Comprehensive Market Data: {market_data_result.get('message', 'Not available')}\n"
            
            # Add company information (NEW)
            if company_info_result.get('status') == 'SUCCESS':
                data_summary += "Company Information: Available\n"
            else:
                data_summary += f"Company Information: {company_info_result.get('message', 'Not available')}\n"
            
            # Add analyst recommendations (NEW)
            if analyst_recommendations_result.get('status') == 'SUCCESS':
                analyst_data = analyst_recommendations_result.get('data', {})
                if analyst_data.get('success'):
                    data_summary += "Analyst Recommendations: Available with ratings and price targets\n"
                else:
                    data_summary += f"Analyst Recommendations: Available but API returned error\n"
            else:
                data_summary += f"Analyst Recommendations: {analyst_recommendations_result.get('message', 'Not available')}\n"
            
            # Add historical data summary
            if historical_result.get('status') == 'SUCCESS':
                hist_data = historical_result.get('data', {})
                if hist_data.get('success'):
                    data_summary += "Historical Data (1Y): Available with price history\n"
                else:
                    data_summary += f"Historical Data (1Y): Available but API returned error - {hist_data.get('msg', 'Unknown error')}\n"
            else:
                data_summary += f"Historical Data (1Y): {historical_result.get('message', 'Not available')}\n"
            
            # Add news summary
            if news_result.get('status') == 'SUCCESS':
                news_data = news_result.get('data', {})
                if news_data.get('success'):
                    data_summary += "News Data: Available with recent news articles\n"
                else:
                    data_summary += f"News Data: Available but API returned error - {news_data.get('msg', 'Unknown error')}\n"
            else:
                data_summary += f"News Data: {news_result.get('message', 'Not available')}\n"
            
            # Add technical analysis summary
            if technical_result.get('status') == 'SUCCESS':
                tech_data = technical_result.get('data', {})
                if tech_data.get('success'):
                    data_summary += "Technical Analysis: Available with signals and indicators\n"
                else:
                    data_summary += f"Technical Analysis: Available but API returned error - {tech_data.get('msg', 'Unknown error')}\n"
            else:
                data_summary += f"Technical Analysis: {technical_result.get('message', 'Not available')}\n"
            
            # Add indicators summary
            if indicators_result.get('status') == 'SUCCESS':
                ind_data = indicators_result.get('data', {})
                if ind_data.get('success'):
                    data_summary += "Technical Indicators: Available with detailed indicator values\n"
                else:
                    data_summary += f"Technical Indicators: Available but API returned error - {ind_data.get('msg', 'Unknown error')}\n"
            else:
                data_summary += f"Technical Indicators: {indicators_result.get('message', 'Not available')}\n"
            
            # Add community sentiment (NEW)
            if community_result.get('status') == 'SUCCESS':
                data_summary += "Community Sentiment Data: Available with social sentiment indicators\n"
            else:
                data_summary += f"Community Sentiment Data: {community_result.get('message', 'Not available')}\n"
            
            # Add economic calendar (NEW)
            if economic_calendar_result.get('status') == 'SUCCESS':
                econ_data = economic_calendar_result.get('data', {})
                if econ_data.get('success'):
                    events = econ_data.get('data', [])
                    data_summary += f"Economic Calendar: Available with {len(events) if isinstance(events, list) else 0} upcoming economic events\n"
                else:
                    data_summary += f"Economic Calendar: Available but API returned error\n"
            else:
                data_summary += f"Economic Calendar: {economic_calendar_result.get('message', 'Not available')}\n"
            
            # Add earnings calendar (NEW)
            if earnings_calendar_result.get('status') == 'SUCCESS':
                earnings_data = earnings_calendar_result.get('data', {})
                if earnings_data.get('success'):
                    events = earnings_data.get('data', [])
                    data_summary += f"Earnings Calendar: Available with {len(events) if isinstance(events, list) else 0} upcoming earnings events\n"
                else:
                    data_summary += f"Earnings Calendar: Available but API returned error\n"
            else:
                data_summary += f"Earnings Calendar: {earnings_calendar_result.get('message', 'Not available')}\n"
            
            # Add market leaderboards (NEW)
            if all([gainers_result.get('status') == 'SUCCESS', losers_result.get('status') == 'SUCCESS', active_result.get('status') == 'SUCCESS']):
                data_summary += "Market Leaderboards: Available with gainers, losers, and most active stocks for market comparison\n"
            else:
                data_summary += "Market Leaderboards: Partially available or not available\n"
            
            # Add world economy indicators (NEW)
            if all([gdp_result.get('status') == 'SUCCESS', interest_rates_result.get('status') == 'SUCCESS']):
                data_summary += "World Economy Indicators: Available with GDP growth and interest rates for macro context\n"
            else:
                data_summary += "World Economy Indicators: Partially available or not available\n"
            
            prompt = f"""
            Analyze the following COMPREHENSIVE stock data from multiple sources and provide a probability assessment:
            
            {data_summary}
            
            Based on ALL the available data sources (price data, comprehensive market data, company info, analyst recommendations, 
            historical data, news, technical analysis, community sentiment, economic calendar, earnings calendar, market leaderboards, 
            and world economy indicators), provide:
            
            1. Probability of price increase (0-100%)
            2. Probability of price decrease (0-100%)
            3. Probability of price staying stable (0-100%)
            4. Overall recommendation (BUY/SELL/HOLD)
            5. Confidence level (0-100%)
            6. Key factors influencing your decision (consider all data sources)
            7. Risk assessment (LOW/MEDIUM/HIGH)
            8. Time horizon for the recommendation
            9. How market context and economic indicators affect this stock
            10. How this stock compares to market leaders (gainers/losers)
            
            Format your response as a structured analysis with clear percentages and reasoning that integrates insights from 
            all available data sources for a comprehensive investment decision.
            """
            
            response = self.model.generate_content(prompt)
            
            return {
                "status": "SUCCESS",
                "analysis": response.text,
                "raw_data": {
                    "price": {
                        "status": price_result.get("status"),
                        "success": price_result.get("data", {}).get("success", False),
                        "has_data": price_result.get("data", {}).get("data") is not None
                    },
                    "market_data": {
                        "status": market_data_result.get("status"),
                        "success": market_data_result.get("data", {}).get("success", False),
                        "has_data": market_data_result.get("data", {}).get("data") is not None
                    },
                    "company_info": {
                        "status": company_info_result.get("status"),
                        "success": company_info_result.get("data", {}).get("success", False),
                        "has_data": company_info_result.get("data", {}).get("data") is not None
                    },
                    "analyst_recommendations": {
                        "status": analyst_recommendations_result.get("status"),
                        "success": analyst_recommendations_result.get("data", {}).get("success", False),
                        "has_data": analyst_recommendations_result.get("data", {}).get("data") is not None
                    },
                    "historical": {
                        "status": historical_result.get("status"),
                        "success": historical_result.get("data", {}).get("success", False),
                        "has_data": historical_result.get("data", {}).get("data") is not None
                    },
                    "news": {
                        "status": news_result.get("status"),
                        "success": news_result.get("data", {}).get("success", False),
                        "has_data": news_result.get("data", {}).get("data") is not None
                    },
                    "technical": {
                        "status": technical_result.get("status"),
                        "success": technical_result.get("data", {}).get("success", False),
                        "has_data": technical_result.get("data", {}).get("data") is not None
                    },
                    "indicators": {
                        "status": indicators_result.get("status"),
                        "success": indicators_result.get("data", {}).get("success", False),
                        "has_data": indicators_result.get("data", {}).get("data") is not None
                    },
                    "community": {
                        "status": community_result.get("status"),
                        "success": community_result.get("data", {}).get("success", False),
                        "has_data": community_result.get("data", {}).get("data") is not None
                    },
                    "economic_calendar": {
                        "status": economic_calendar_result.get("status"),
                        "success": economic_calendar_result.get("data", {}).get("success", False),
                        "has_data": economic_calendar_result.get("data", {}).get("data") is not None
                    },
                    "earnings_calendar": {
                        "status": earnings_calendar_result.get("status"),
                        "success": earnings_calendar_result.get("data", {}).get("success", False),
                        "has_data": earnings_calendar_result.get("data", {}).get("data") is not None
                    },
                    "market_leaderboards": {
                        "status": "SUCCESS" if all([
                            gainers_result.get("status") == "SUCCESS",
                            losers_result.get("status") == "SUCCESS",
                            active_result.get("status") == "SUCCESS"
                        ]) else "PARTIAL",
                        "gainers": gainers_result.get("status"),
                        "losers": losers_result.get("status"),
                        "active": active_result.get("status")
                    },
                    "world_economy": {
                        "status": "SUCCESS" if all([
                            gdp_result.get("status") == "SUCCESS",
                            interest_rates_result.get("status") == "SUCCESS"
                        ]) else "PARTIAL",
                        "gdp": gdp_result.get("status"),
                        "interest_rates": interest_rates_result.get("status")
                    }
                }
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Error generating probability analysis: {str(e)}"
            }
    
    def _compile_comprehensive_report(self, symbol: str, price_result: Dict,
                                     market_data_result: Dict, company_info_result: Dict,
                                     analyst_recommendations_result: Dict, historical_result: Dict,
                                     news_result: Dict, technical_result: Dict,
                                     indicators_result: Dict, community_result: Dict,
                                     economic_calendar_result: Dict, earnings_calendar_result: Dict,
                                     gainers_result: Dict, losers_result: Dict, active_result: Dict,
                                     gdp_result: Dict, interest_rates_result: Dict,
                                     probability_analysis: Dict) -> str:
        """
        Compile ALL data into a comprehensive report.
        
        Args:
            symbol: Stock symbol
            price_result: Current price data
            market_data_result: Comprehensive market data (15 sections)
            company_info_result: Company information
            analyst_recommendations_result: Analyst recommendations
            historical_result: Historical data
            news_result: News data
            technical_result: Technical analysis
            indicators_result: Technical indicators
            community_result: Community sentiment data
            economic_calendar_result: Economic calendar
            earnings_calendar_result: Earnings calendar
            gainers_result: Stock gainers leaderboard
            losers_result: Stock losers leaderboard
            active_result: Most active stocks
            gdp_result: GDP growth data
            interest_rates_result: Interest rates data
            probability_analysis: AI-generated probability analysis
        
        Returns:
            str: Comprehensive report
        """
        report = f"""
{'='*80}
COMPREHENSIVE STOCK ANALYSIS REPORT: {symbol}
{'='*80}

DATA SOURCES STATUS (13 Tools Used):
- Current Price: {price_result.get('status')}
- 1-Year Historical Data: {historical_result.get('status')}
- Current News: {news_result.get('status')}
- Technical Analysis: {technical_result.get('status')}
- Technical Indicators: {indicators_result.get('status')}

"""
        
        # Add current price information if available
        if price_result.get('status') == 'SUCCESS':
            price_data = price_result.get('data', {})
            if price_data.get('success'):
                actual_data = price_data.get('data', {})
                current = actual_data.get('current', {})
                info = actual_data.get('info', {})
                
                report += f"CURRENT PRICE INFORMATION:\n"
                report += f"Symbol: {symbol}\n"
                report += f"Formatted Symbol: {price_result.get('formatted_symbol')}\n"
                report += f"Company: {info.get('description', 'N/A')}\n"
                report += f"Current Price: ${current.get('close', 'N/A')}\n"
                report += f"Open: ${current.get('open', 'N/A')}\n"
                report += f"High: ${current.get('max', 'N/A')}\n"
                report += f"Low: ${current.get('min', 'N/A')}\n"
                report += f"Volume: {current.get('volume', 'N/A')}\n"
                report += f"Exchange: {info.get('exchange', 'N/A')}\n\n"
            else:
                report += f"CURRENT PRICE INFORMATION:\n"
                report += f"Symbol: {symbol}\n"
                report += f"Error: {price_data.get('msg', 'Data not available')}\n\n"
        
        # Add probability analysis
        if probability_analysis.get('status') == 'SUCCESS':
            report += f"PROBABILITY ANALYSIS:\n"
            report += f"{probability_analysis.get('analysis')}\n\n"
        else:
            report += f"Probability Analysis: {probability_analysis.get('message', 'Not available')}\n\n"
        
        # Add technical analysis summary
        if technical_result.get('status') == 'SUCCESS':
            tech_data = technical_result.get('data', {})
            if tech_data.get('success'):
                actual_tech_data = tech_data.get('data', {})
                report += f"TECHNICAL ANALYSIS SUMMARY:\n"
                report += f"Status: Data available\n"
                if isinstance(actual_tech_data, dict):
                    # Add some key technical analysis fields if available
                    if 'recommendation' in actual_tech_data:
                        report += f"Recommendation: {actual_tech_data.get('recommendation', 'N/A')}\n"
                    if 'signal' in actual_tech_data:
                        report += f"Signal: {actual_tech_data.get('signal', 'N/A')}\n"
                    report += f"Data keys: {list(actual_tech_data.keys())}\n"
                report += "\n"
            else:
                report += f"TECHNICAL ANALYSIS SUMMARY:\n"
                report += f"Error: {tech_data.get('msg', 'Data not available')}\n\n"
        
        # Add news summary
        if news_result.get('status') == 'SUCCESS':
            news_data = news_result.get('data', {})
            if news_data.get('success'):
                actual_news_data = news_data.get('data', {})
                report += f"NEWS SUMMARY:\n"
                report += f"Status: Data available\n"
                if isinstance(actual_news_data, list):
                    report += f"Number of articles: {len(actual_news_data)}\n"
                elif isinstance(actual_news_data, dict):
                    report += f"Data keys: {list(actual_news_data.keys())}\n"
                report += "\n"
            else:
                report += f"NEWS SUMMARY:\n"
                report += f"Error: {news_data.get('msg', 'Data not available')}\n\n"
        
        report += f"{'='*80}\n"
        report += f"Report generated by Stock Analysis Agent\n"
        report += f"{'='*80}\n"
        
        return report
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """
        Process user query and extract stock symbol for analysis.
        
        Args:
            query: User's query (e.g., "Analyze AAPL" or "What about TSLA?")
        
        Returns:
            dict: Analysis result
        """
        # Extract stock symbol from query
        symbol = self._extract_symbol(query)
        
        if not symbol:
            return {
                "status": "ERROR",
                "message": "Please provide a stock symbol (e.g., 'Analyze AAPL' or 'What about TSLA?')"
            }
        
        return self.analyze_stock(symbol)
    
    def _extract_symbol(self, query: str) -> str:
        """
        Extract stock symbol from user query.
        
        Args:
            query: User's query text
        
        Returns:
            str: Extracted stock symbol or None
        """
        # Simple extraction - look for uppercase stock symbols (1-5 letters)
        import re
        matches = re.findall(r'\b[A-Z]{1,5}\b', query)
        
        # Filter out common words
        common_words = {'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'HAD', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'HAS', 'HAVE', 'BEEN', 'WILL', 'WITH', 'THIS', 'THAT', 'FROM', 'WHAT', 'WHEN', 'ABOUT'}
        symbols = [match for match in matches if match not in common_words]
        
        if symbols:
            return symbols[0]  # Return first potential symbol
        
        return None


if __name__ == "__main__":
    # Test the agent
    print("Testing Stock Analysis Agent...")
    print("Choose analysis type:")
    print("1. Comprehensive Analysis (13 tools)")
    print("2. 1-Month Prediction (8 tools - focused)")
    print("3. Investment Scenario Analysis (100-day with $10K example)")
    
    choice = input("\nEnter choice (1, 2, or 3): ").strip()
    
    agent = StockAnalysisAgent()
    
    if choice == "3":
        print("\nRunning Investment Scenario Analysis...")
        investment = input("Enter investment amount (default $10,000): ").strip()
        days = input("Enter timeframe in days (default 100): ").strip()
        
        try:
            investment_amount = float(investment) if investment else 10000
            timeframe = int(days) if days else 100
        except:
            investment_amount = 10000
            timeframe = 100
        
        result = agent.analyze_investment_scenario("AAPL", investment_amount, timeframe)
    elif choice == "2":
        print("\nRunning 1-Month Prediction Analysis...")
        result = agent.analyze_stock_one_month("AAPL")
    else:
        print("\nRunning Comprehensive Analysis...")
        result = agent.analyze_stock("AAPL")
    
    print(f"\nStatus: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(result['report'])
    else:
        print(f"Error: {result.get('message')}")