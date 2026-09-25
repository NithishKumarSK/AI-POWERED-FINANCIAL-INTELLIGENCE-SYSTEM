"""
Debug test for portfolio analysis
"""

from portfolio_manager import PortfolioManager

# Simple test with 2 stocks
test_holdings = [
    {"name": "Microsoft", "amount": 477700},
    {"name": "Apple", "amount": 22000}
]

print("Testing portfolio analysis with debugging...")
print(f"Holdings: {test_holdings}")

manager = PortfolioManager()

try:
    result = manager.analyze_portfolio_from_dollar_amounts(
        test_holdings,
        analysis_type="one_month"
    )
    
    print(f"\nStatus: {result['status']}")
    if result['status'] == 'SUCCESS':
        print("SUCCESS!")
        print(result['final_report'][:500])
    else:
        print(f"Error: {result.get('message')}")
        
except Exception as e:
    print(f"\nException: {e}")
    import traceback
    traceback.print_exc()
