"""
Run portfolio analysis for user's portfolio
"""

from portfolio_manager import PortfolioManager

# User's portfolio holdings (dollar amounts)
user_holdings = [
    {"name": "Fairfax India", "amount": 10000},
    {"name": "Google class", "amount": 264960},
    {"name": "Nitendo", "amount": 5200},
    {"name": "Brkb", "amount": 21336},
    {"name": "Qxo", "amount": 8871},
    {"name": "Markel group", "amount": 20000},
    {"name": "Epd", "amount": 11500},
    {"name": "Exo", "amount": 3960, "currency": "GBP"},  # Will skip GBP for now
    {"name": "Verizon", "amount": 17800},
    {"name": "Siri", "amount": 2500},
    {"name": "Barrick", "amount": 11500},
    {"name": "Gld", "amount": 15500},
    {"name": "Netflix", "amount": 5080},
    {"name": "Rgld", "amount": 14000},
    {"name": "Ttwo", "amount": 2200},
    {"name": "Wy", "amount": 4500},
    {"name": "Sgov", "amount": 30000},
    {"name": "Fwona", "amount": 5000},
    {"name": "Wpm", "amount": 5000},
    {"name": "Meta", "amount": 4000},
    {"name": "Microsoft", "amount": 477700},
    {"name": "Apple", "amount": 22000},
    {"name": "Micron", "amount": 3800},
    {"name": "Nvida", "amount": 30397}
]

# Filter out GBP holdings for now (Exo)
usd_holdings = [h for h in user_holdings if h.get("currency", "USD") == "USD"]

print("="*80)
print("USER PORTFOLIO ANALYSIS")
print("="*80)
print(f"\nTotal Holdings: {len(usd_holdings)}")
total_invested = sum(h["amount"] for h in usd_holdings)
print(f"Total Invested: ${total_invested:,.2f}")

print("\nHoldings:")
for h in usd_holdings:
    print(f"  {h['name']}: ${h['amount']:,.2f}")

print("\n" + "="*80)
print("ANALYSIS OPTIONS")
print("="*80)
print("\nAnalysis Types:")
print("1. 1-Month Prediction (8 tools, ~16s per stock)")
print("   - Total estimated time: ~6.4 minutes for 24 stocks")
print("2. Investment Scenario (6 tools, ~40s per stock)")
print("   - Total estimated time: ~16 minutes for 24 stocks")
print("3. Comprehensive (13 tools, ~45s per stock)")
print("   - Total estimated time: ~18 minutes for 24 stocks")

print("\nRecommendation: Start with 1-Month Prediction for faster results")
print("="*80)

# Initialize portfolio manager
manager = PortfolioManager()

print("\nStarting portfolio analysis (1-Month Prediction)...")
print("This will take approximately 6-7 minutes for 24 stocks")
print("Press Ctrl+C to cancel if needed\n")

try:
    # Run analysis with 1-month prediction (faster)
    result = manager.analyze_portfolio_from_dollar_amounts(
        usd_holdings,
        analysis_type="one_month"
    )
    
    print("\n" + "="*80)
    print("ANALYSIS RESULTS")
    print("="*80)
    
    print(f"\nStatus: {result['status']}")
    print(f"Total Time: {result['total_time']}")
    
    if result['status'] == 'SUCCESS':
        print("\nExecution Log:")
        for log in result['execution_log']:
            status_icon = "[OK]" if log['status'] == "SUCCESS" else "[FAIL]"
            print(f"{status_icon} Step {log['step']}: {log['agent']} - {log['action']} ({log['duration']})")
        
        print("\n" + "="*80)
        print("CONVERSION LOG (Dollar Amounts to Shares)")
        print("="*80)
        for log in result.get('conversion_log', [])[:10]:  # Show first 10
            print(f"{log['name']} -> {log['ticker']}: ${log['amount']:,.2f} invested")
            print(f"  Current Price: ${log['current_price']:.2f}")
            print(f"  Calculated Shares: {log['calculated_shares']:.2f}")
        
        print("\n" + "="*80)
        print("FINAL PORTFOLIO REPORT")
        print("="*80)
        print(result['final_report'])
        
        # Save report to file
        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"user_portfolio_report_{timestamp}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(result['final_report'])
        print(f"\nReport saved to: {filename}")
    else:
        print(f"\nError: {result.get('message')}")
        
except KeyboardInterrupt:
    print("\n\nAnalysis cancelled by user")
except Exception as e:
    print(f"\nError during analysis: {str(e)}")
    import traceback
    traceback.print_exc()
