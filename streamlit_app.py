"""
Stock Analysis Streamlit Application
A focused web interface for analyzing individual stocks
"""

import os
import sys
import streamlit as st
from datetime import datetime

# Add paths - main directory first, then subdirectories
sys.path.insert(0, os.path.dirname(__file__))  # Main directory first
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'tools'))
sys.path.insert(2, os.path.join(os.path.dirname(__file__), 'config'))
sys.path.insert(3, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
from stock_analysis_agent import StockAnalysisAgent
from portfolio_manager import PortfolioManager

load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Stock & Portfolio Analysis",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: white;
        text-align: center;
        padding: 2rem 0;
    }
    .analysis-container {
        background: white;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    .metric-card {
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)


def initialize_agent():
    """Initialize the stock analysis agent and portfolio manager"""
    if 'agent' not in st.session_state:
        # Get or create user ID
        if 'user_id' not in st.session_state:
            st.session_state.user_id = "default_user"

        with st.spinner("Initializing Stock Analysis Agent..."):
            st.session_state.agent = StockAnalysisAgent(user_id=st.session_state.user_id)
            st.session_state.analysis_history = []

    if 'portfolio_manager' not in st.session_state:
        with st.spinner("Initializing Portfolio Manager..."):
            st.session_state.portfolio_manager = PortfolioManager(user_id=st.session_state.user_id)
            st.session_state.portfolio_history = []


def stock_analysis_interface():
    """Main stock analysis interface"""
    st.subheader("📊 Stock Analysis")
    
    st.info("🎯 **Enter a stock symbol** (e.g., AAPL, TSLA, MSFT) to get a comprehensive analysis including:")
    st.info("- 1-year historical price data")
    st.info("- Current news and sentiment")
    st.info("- Technical indicators and analysis")
    st.info("- AI-powered probability assessment")
    
    st.divider()
    
    # Stock symbol input
    col1, col2 = st.columns([3, 1])
    with col1:
        stock_symbol = st.text_input(
            "Enter Stock Symbol",
            placeholder="e.g., AAPL, TSLA, MSFT",
            key="stock_symbol_input"
        ).upper()
    
    with col2:
        analyze_button = st.button("Analyze Stock", type="primary", use_container_width=True)
    
    if analyze_button and stock_symbol:
        # Perform analysis
        with st.spinner(f"Analyzing {stock_symbol}... This may take a moment..."):
            result = st.session_state.agent.analyze_stock(stock_symbol)
        
        # Display results
        if result.get('status') == 'SUCCESS':
            st.success(f"✅ Analysis completed for {stock_symbol}")
            
            # Display execution steps
            with st.expander("📋 Analysis Steps"):
                for step in result.get('execution_steps', []):
                    status_icon = "✅" if step['status'] == 'SUCCESS' else "❌"
                    st.write(f"{status_icon} **Step {step['step']}**: {step['action']} ({step['duration']})")
            
            # Display main report
            st.divider()
            st.subheader("📈 Analysis Report")
            
            # Display report in a nice format
            report_text = result.get('report', '')
            st.markdown(f"""
            <div class="analysis-container">
                <pre>{report_text}</pre>
            </div>
            """, unsafe_allow_html=True)
            
            # Add to history
            st.session_state.analysis_history.append({
                "symbol": stock_symbol,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "result": result
            })
            
        else:
            st.error(f"❌ Analysis failed: {result.get('message', 'Unknown error')}")
    
    # Display analysis history
    if st.session_state.analysis_history:
        st.divider()
        st.subheader("📜 Analysis History")
        
        for i, analysis in enumerate(reversed(st.session_state.analysis_history[-5:]), 1):
            with st.expander(f"{i}. {analysis['symbol']} - {analysis['timestamp']}"):
                st.write(f"Status: {analysis['result'].get('status')}")
                if analysis['result'].get('status') == 'SUCCESS':
                    st.text(analysis['result'].get('report', '')[:500] + "...")


def parse_portfolio_text(text_input: str) -> list:
    """Parse free-text portfolio input into structured holdings.

    Args:
        text_input: Free text portfolio (e.g., "Apple - 22000, Microsoft - 477700")

    Returns:
        list: List of holdings with name and amount
    """
    holdings = []
    lines = text_input.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try different separators
        separators = ['-', '—', '–', ':', ',', '|', ' ']

        for sep in separators:
            if sep in line:
                parts = line.split(sep)
                if len(parts) >= 2:
                    # Try to identify which part is the name and which is the amount
                    # The name is usually first, amount is usually last
                    name_part = parts[0].strip()
                    amount_part = parts[-1].strip()

                    # Skip if name is empty or looks like a number
                    if not name_part or name_part.replace('.', '').isdigit():
                        continue

                    # Extract amount from second part
                    amount_str = amount_part

                    # Handle 'k' suffix (multiply by 1000)
                    # But be smart about it - if number before 'k' is > 1000, it might already be the full amount
                    if 'k' in amount_str.lower():
                        # Remove 'k'
                        amount_before_k = amount_str.lower().replace('k', '')
                        try:
                            base_amount = float(amount_before_k)
                            # If base amount is very large (>10000), don't multiply by 1000
                            # This handles cases like "26496k" where user probably meant 26496, not 26M
                            if base_amount > 10000:
                                amount = base_amount
                            else:
                                amount = base_amount * 1000
                        except ValueError:
                            continue
                    else:
                        # Remove non-numeric characters (except decimal point)
                        amount_str = ''.join(c for c in amount_str if c.isdigit() or c == '.')
                        try:
                            amount = float(amount_str)
                        except ValueError:
                            continue

                    if amount > 0:
                        holdings.append({"name": name_part, "amount": amount})
                    break  # Successfully parsed, move to next line

    return holdings


def portfolio_analysis_interface():
    """Portfolio analysis interface"""
    st.subheader("💼 Portfolio Analysis")

    st.info("🎯 **Enter your portfolio holdings** to get comprehensive portfolio analysis including:")
    st.info("- Individual stock analysis for each holding")
    st.info("- Portfolio-level risk assessment")
    st.info("- Diversification analysis")
    st.info("- AI-powered portfolio recommendations")

    st.divider()

    # Input format selection
    input_format = st.radio(
        "Input Format",
        ["Paste as Text (easiest)", "Dollar Amounts (table)", "Shares & Avg Cost"],
        help="Choose how you want to enter your holdings"
    )

    # Portfolio input
    st.subheader("Enter Your Holdings")

    if input_format == "Paste as Text (easiest)":
        st.info("📝 **Paste your portfolio as text** - one per line")
        st.info("Format: Stock Name - Amount")
        st.info("Example:")
        st.code("""
Apple - 22000
Microsoft - 477700
Google - 264960
Tesla - 50000
        """)

        text_input = st.text_area(
            "Paste your portfolio here",
            height=200,
            placeholder="Apple - 22000\nMicrosoft - 477700\nGoogle - 264960\n...",
            help="One stock per line: Name - Amount"
        )

        holdings = []
        if text_input:
            try:
                holdings = parse_portfolio_text(text_input)
                if holdings:
                    st.success(f"✅ Parsed {len(holdings)} holdings successfully")
                    st.write("**Parsed Holdings (you can edit below if needed):**")

                    # Allow user to edit parsed holdings
                    edited_holdings = []
                    for i, h in enumerate(holdings):
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            edited_name = st.text_input(f"Stock {i+1} Name", value=h.get('name', ''), key=f"edit_name_{i}")
                        with col2:
                            edited_amount = st.number_input(f"Amount ${i+1}", value=h.get('amount', 0.0), key=f"edit_amount_{i}")
                        if edited_name and edited_amount > 0:
                            edited_holdings.append({"name": edited_name, "amount": float(edited_amount)})
                        else:
                            # Keep original if editing failed, but ensure structure is correct
                            if isinstance(h, dict) and 'name' in h and 'amount' in h:
                                edited_holdings.append({"name": h['name'], "amount": float(h['amount'])})
                            else:
                                # Skip this holding if structure is invalid
                                st.warning(f"⚠️ Skipping invalid holding at position {i+1}")

                    holdings = edited_holdings
                    print(f"DEBUG: Final holdings after editing: {holdings}")
                else:
                    st.warning("⚠️ Could not parse holdings. Check the format.")
                    st.info("Expected format: Stock Name - Amount")
                    st.info("Example: Apple - 22000")
            except Exception as e:
                st.error(f"❌ Error parsing portfolio: {str(e)}")
                st.info("Please check the format and try again")

    elif input_format == "Dollar Amounts (table)":
        st.info("Enter company name or ticker and the dollar amount invested")

        # Dynamic input for holdings
        holdings = []
        num_holdings = st.number_input("Number of holdings", min_value=1, max_value=50, value=3)

        for i in range(num_holdings):
            col1, col2 = st.columns([2, 1])
            with col1:
                name = st.text_input(f"Stock {i+1} Name/Ticker", placeholder="e.g., Apple or AAPL", key=f"name_{i}")
            with col2:
                amount = st.number_input(f"Amount ${i+1}", min_value=0.0, value=10000.0, key=f"amount_{i}")

            if name and amount > 0:
                holdings.append({"name": name, "amount": amount})

    else:  # Shares & Avg Cost
        st.info("Enter company name, number of shares, and average cost per share")

        holdings_shares = []
        num_holdings = st.number_input("Number of holdings", min_value=1, max_value=50, value=3)

        for i in range(num_holdings):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                symbol = st.text_input(f"Stock {i+1} Symbol", placeholder="e.g., AAPL", key=f"symbol_{i}")
            with col2:
                shares = st.number_input(f"Shares {i+1}", min_value=0.0, value=100.0, key=f"shares_{i}")
            with col3:
                avg_cost = st.number_input(f"Avg Cost ${i+1}", min_value=0.0, value=150.0, key=f"cost_{i}")

            if symbol and shares > 0 and avg_cost > 0:
                holdings_shares.append({
                    "symbol": symbol,
                    "shares": shares,
                    "avg_cost": avg_cost
                })

    # Cash input
    cash = st.number_input("Cash in Portfolio ($)", min_value=0.0, value=0.0)

    # Analysis type selection
    st.divider()
    st.subheader("Analysis Type")
    analysis_type = st.selectbox(
        "Choose analysis depth",
        ["1-Month Prediction (faster, ~16s per stock)", "Investment Scenario (~40s per stock)", "Comprehensive (~45s per stock)"],
        help="Faster options for quick analysis, comprehensive for deep analysis"
    )

    # Map selection to actual type
    if analysis_type == "1-Month Prediction (faster, ~16s per stock)":
        actual_type = "one_month"
    elif analysis_type == "Investment Scenario (~40s per stock)":
        actual_type = "scenario"
    else:
        actual_type = "comprehensive"

    # Analyze button
    analyze_button = st.button("Analyze Portfolio", type="primary", use_container_width=True)

    if analyze_button:
        if input_format == "Paste as Text (easiest)" and holdings:
            # Estimate time
            est_time = len(holdings) * (16 if actual_type == "one_month" else 40 if actual_type == "scenario" else 45)
            st.info(f"⏱️ Estimated time: ~{est_time} seconds ({est_time/60:.1f} minutes) for {len(holdings)} stocks")

            with st.spinner(f"Analyzing {len(holdings)} holdings... This may take several minutes..."):
                try:
                    # Debug: print holdings before analysis
                    print(f"DEBUG: Holdings to analyze: {holdings}")

                    result = st.session_state.portfolio_manager.analyze_portfolio_from_dollar_amounts(
                        holdings,
                        analysis_type=actual_type
                    )

                    if result.get('status') == 'SUCCESS':
                        st.success(f"✅ Portfolio analysis completed")

                        # Display execution steps
                        with st.expander("📋 Execution Steps"):
                            for step in result.get('execution_log', []):
                                status_icon = "✅" if step['status'] == "SUCCESS" else "❌"
                                st.write(f"{status_icon} **Step {step['step']}**: {step['agent']} - {step['action']} ({step['duration']})")

                        # Display conversion log
                        if result.get('conversion_log'):
                            with st.expander("🔄 Conversion Log"):
                                for log in result['conversion_log']:
                                    if 'name' in log and 'ticker' in log:
                                        st.write(f"{log['name']} → {log['ticker']}: ${log['amount']:,.2f} invested")
                                        st.write(f"  Current Price: ${log['current_price']:.2f}, Shares: {log['calculated_shares']:.2f}")
                                    elif 'warning' in log:
                                        st.warning(f"⚠️ {log['warning']}")
                                    else:
                                        st.info(f"ℹ️ {log}")

                        # Display main report
                        st.divider()
                        st.subheader("📊 Portfolio Analysis Report")

                        # Display report in a nice format
                        report_text = result.get('final_report', '')
                        st.markdown(f"""
                        <div class="analysis-container">
                            <pre>{report_text}</pre>
                        </div>
                        """, unsafe_allow_html=True)

                        # Add to history
                        st.session_state.portfolio_history.append({
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "result": result,
                            "holdings_count": len(holdings)
                        })

                    else:
                        st.error(f"❌ Analysis failed: {result.get('message', 'Unknown error')}")

                except Exception as e:
                    st.error(f"❌ Error during analysis: {str(e)}")

        elif input_format == "Dollar Amounts (table)" and holdings:
            # Estimate time
            est_time = len(holdings) * (16 if actual_type == "one_month" else 40 if actual_type == "scenario" else 45)
            st.info(f"⏱️ Estimated time: ~{est_time} seconds ({est_time/60:.1f} minutes) for {len(holdings)} stocks")

            with st.spinner(f"Analyzing {len(holdings)} holdings... This may take several minutes..."):
                try:
                    # Debug: print holdings before analysis
                    print(f"DEBUG: Holdings to analyze: {holdings}")

                    result = st.session_state.portfolio_manager.analyze_portfolio_from_dollar_amounts(
                        holdings,
                        analysis_type=actual_type
                    )

                    if result.get('status') == 'SUCCESS':
                        st.success(f"✅ Portfolio analysis completed")

                        # Display execution steps
                        with st.expander("📋 Execution Steps"):
                            for step in result.get('execution_log', []):
                                status_icon = "✅" if step['status'] == "SUCCESS" else "❌"
                                st.write(f"{status_icon} **Step {step['step']}**: {step['agent']} - {step['action']} ({step['duration']})")

                        # Display conversion log
                        if result.get('conversion_log'):
                            with st.expander("🔄 Conversion Log"):
                                for log in result['conversion_log']:
                                    if 'name' in log and 'ticker' in log:
                                        st.write(f"{log['name']} → {log['ticker']}: ${log['amount']:,.2f} invested")
                                        st.write(f"  Current Price: ${log['current_price']:.2f}, Shares: {log['calculated_shares']:.2f}")
                                    elif 'warning' in log:
                                        st.warning(f"⚠️ {log['warning']}")
                                    else:
                                        st.info(f"ℹ️ {log}")

                        # Display main report
                        st.divider()
                        st.subheader("📊 Portfolio Analysis Report")

                        # Display report in a nice format
                        report_text = result.get('final_report', '')
                        st.markdown(f"""
                        <div class="analysis-container">
                            <pre>{report_text}</pre>
                        </div>
                        """, unsafe_allow_html=True)

                        # Add to history
                        st.session_state.portfolio_history.append({
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "result": result,
                            "holdings_count": len(holdings)
                        })

                    else:
                        st.error(f"❌ Analysis failed: {result.get('message', 'Unknown error')}")

                except Exception as e:
                    st.error(f"❌ Error during analysis: {str(e)}")

        elif input_format == "Shares & Avg Cost" and holdings_shares:
            portfolio_data = {
                "holdings": holdings_shares,
                "cash": cash
            }

            # Estimate time
            est_time = len(holdings_shares) * (16 if actual_type == "one_month" else 40 if actual_type == "scenario" else 45)
            st.info(f"⏱️ Estimated time: ~{est_time} seconds ({est_time/60:.1f} minutes) for {len(holdings_shares)} stocks")

            with st.spinner(f"Analyzing {len(holdings_shares)} holdings... This may take several minutes..."):
                try:
                    result = st.session_state.portfolio_manager.analyze_portfolio_complete(
                        portfolio_data,
                        analysis_type=actual_type
                    )

                    if result.get('status') == 'SUCCESS':
                        st.success(f"✅ Portfolio analysis completed")

                        # Display execution steps
                        with st.expander("📋 Execution Steps"):
                            for step in result.get('execution_log', []):
                                status_icon = "✅" if step['status'] == "SUCCESS" else "❌"
                                st.write(f"{status_icon} **Step {step['step']}**: {step['agent']} - {step['action']} ({step['duration']})")

                        # Display main report
                        st.divider()
                        st.subheader("📊 Portfolio Analysis Report")

                        report_text = result.get('final_report', '')
                        st.markdown(f"""
                        <div class="analysis-container">
                            <pre>{report_text}</pre>
                        </div>
                        """, unsafe_allow_html=True)

                        # Add to history
                        st.session_state.portfolio_history.append({
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "result": result,
                            "holdings_count": len(holdings_shares)
                        })

                    else:
                        st.error(f"❌ Analysis failed: {result.get('message', 'Unknown error')}")

                except Exception as e:
                    st.error(f"❌ Error during analysis: {str(e)}")
        else:
            st.warning("⚠️ Please enter at least one holding")

    # Display portfolio history
    if st.session_state.portfolio_history:
        st.divider()
        st.subheader("📜 Portfolio Analysis History")

        for i, analysis in enumerate(reversed(st.session_state.portfolio_history[-3:]), 1):
            with st.expander(f"{i}. {analysis['holdings_count']} holdings - {analysis['timestamp']}"):
                st.write(f"Status: {analysis['result'].get('status')}")
                if analysis['result'].get('status') == 'SUCCESS':
                    st.text(analysis['result'].get('final_report', '')[:500] + "...")





def main():
    """Main application"""
    # Header
    st.markdown('<div class="main-header">📈 Stock & Portfolio Analysis</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: white; margin-bottom: 2rem;">AI-powered stock and portfolio analysis</p>', unsafe_allow_html=True)

    # Initialize agent
    initialize_agent()

    # Tab system
    tab1, tab2 = st.tabs(["📊 Stock Analysis", "💼 Portfolio Analysis"])

    with tab1:
        stock_analysis_interface()

    with tab2:
        portfolio_analysis_interface()

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")

        st.subheader("User Session")

        # User ID input for session logging
        user_id = st.text_input("User ID", value=st.session_state.get('user_id', 'default_user'), help="Enter your user ID for session logging")
        if user_id != st.session_state.get('user_id', 'default_user'):
            st.session_state.user_id = user_id
            # Reinitialize agents with new user ID
            if 'agent' in st.session_state:
                st.session_state.agent = StockAnalysisAgent(user_id=user_id)
            if 'portfolio_manager' in st.session_state:
                st.session_state.portfolio_manager = PortfolioManager(user_id=user_id)
            st.success("✅ Session updated with new user ID")

        st.divider()

        st.subheader("Quick Actions")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🧹 Clear Stock History"):
                st.session_state.analysis_history = []
                st.success("✅ Stock history cleared")
        with col2:
            if st.button("🧹 Clear Portfolio History"):
                st.session_state.portfolio_history = []
                st.success("✅ Portfolio history cleared")

        st.divider()

        st.subheader("About")
        st.info("""
        **Stock & Portfolio Analysis** helps you:
        - 📊 Analyze individual stocks
        - 💼 Analyze entire portfolios
        - 📰 Get current news and sentiment
        - 📈 Extract technical indicators
        - 🤖 AI-powered probability assessment
        - 🎯 Portfolio recommendations
        - 📉 Risk analysis
        - 📋 Generate comprehensive reports

        Built with Streamlit & Python
        """)

        st.divider()

        st.subheader("System Status")

        # Check API keys
        google_api_key = os.getenv('GOOGLE_API_KEY')
        if google_api_key:
            st.success("✅ Google AI configured")
        else:
            st.warning("⚠️ Google AI not configured")

        rapidapi_key = os.getenv('RAPIDAPI_KEY')
        if rapidapi_key and rapidapi_key != 'mock-key-for-testing':
            st.success("✅ RapidAPI configured")
        else:
            st.warning("⚠️ RapidAPI not configured")


if __name__ == "__main__":
    main()