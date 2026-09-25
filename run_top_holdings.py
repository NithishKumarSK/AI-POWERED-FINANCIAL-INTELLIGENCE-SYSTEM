"""
Run portfolio analysis for top 5 holdings by value (test)
"""

from portfolio_manager import PortfolioManager

# Top 5 holdings by value
top_holdings = [
    {"name": "Microsoft", "amount": 477700},
    {"name": "Google class", "amount": 264960},
    {"name": "Apple", "amount": 22000},
    {"name": "Sgov", "amount": 30000},
    {"name": "Nvida", "amount": 30397}
]

print("="*80)
print("TOP 5 HOLDINGS ANALYSIS (TEST)")
print("="*80)
print(f"\nTotal Holdings: {len(top_holdings)}")
total_invested = sum(h["amount"] for h in top_holdings)
print(f"Total Invested: ${total_invested:,.2f}")

print("\nHoldings:")
for h in top_holdings:
    print(f"  {h['name']}: ${h['amount']:,.2f}")

print("\nEstimated time: ~80 seconds (5 stocks x 16s each)")

# Initialize portfolio manager
print("\nInitializing Portfolio Manager...")
manager = PortfolioManager()
print("Portfolio Manager initialized")

print("\nStarting conversion...")
try:
    # Run analysis with 1-month prediction
    result = manager.analyze_portfolio_from_dollar_amounts(
        top_holdings,
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
        print("CONVERSION LOG")
        print("="*80)
        for log in result.get('conversion_log', []):
            print(f"{log['name']} -> {log['ticker']}: ${log['amount']:,.2f}")
            print(f"  Current Price: ${log['current_price']:.2f}, Shares: {log['calculated_shares']:.2f}")
        
        print("\n" + "="*80)
        print("FINAL REPORT")
        print("="*80)
        print(result['final_report'])
        
        # Save report
        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"top5_portfolio_report_{timestamp}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(result['final_report'])
        print(f"\nReport saved to: {filename}")
    else:
        print(f"\nError: {result.get('message')}")
        
except Exception as e:
    print(f"\nError: {str(e)}")
    import traceback
    traceback.print_exc()
