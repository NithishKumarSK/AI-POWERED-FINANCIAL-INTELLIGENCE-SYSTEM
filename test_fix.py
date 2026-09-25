"""
Test script to verify the portfolio analysis fix with sample data
"""

from portfolio_manager import PortfolioManager

# Sample data from the user's screenshot
sample_holdings = [
    {"name": "DELL", "amount": 12193},
    {"name": "MSFT", "amount": 14442},
    {"name": "NKE", "amount": 2117},
    {"name": "NVDA", "amount": 27},
    {"name": "UNH", "amount": 10029}
]

print("="*80)
print("Testing Portfolio Analysis Fix")
print("="*80)
print(f"\nSample Holdings: {len(sample_holdings)} stocks")
for h in sample_holdings:
    print(f"  {h['name']}: ${h['amount']:,.2f}")

print("\n" + "="*80)
print("Running Portfolio Analysis...")
print("="*80)

manager = PortfolioManager()

try:
    result = manager.analyze_portfolio_from_dollar_amounts(
        sample_holdings,
        analysis_type="one_month"
    )
    
    print(f"\nStatus: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Total Time: {result['total_time']}")
        
        print("\n" + "="*80)
        print("EXECUTION LOG")
        print("="*80)
        for log in result['execution_log']:
            status_icon = "[OK]" if log['status'] == "SUCCESS" else "[FAIL]"
            print(f"{status_icon} Step {log['step']}: {log['agent']} - {log['action']} ({log['duration']})")
        
        print("\n" + "="*80)
        print("CONVERSION LOG")
        print("="*80)
        for log in result['conversion_log']:
            if 'name' in log and 'ticker' in log:
                print(f"{log['name']} -> {log['ticker']}: ${log['amount']:,.2f} invested")
                print(f"  Current Price: ${log['current_price']:.2f}, Shares: {log['calculated_shares']:.2f}")
            elif 'warning' in log:
                print(f"[WARNING] {log['warning']}")
            else:
                print(f"[INFO] {log}")
        
        print("\n" + "="*80)
        print("FINAL REPORT (First 500 chars)")
        print("="*80)
        print(result['final_report'][:500] + "...")
        
        print("\n[SUCCESS] Fix verified successfully!")
    else:
        print(f"[ERROR] Error: {result.get('message')}")
        if 'orchestrated_data' in result:
            print(f"Orchestrator Error: {result['orchestrated_data'].get('message')}")
        
except Exception as e:
    print(f"[ERROR] Exception occurred: {str(e)}")
    import traceback
    traceback.print_exc()
