"""
Test portfolio analysis to reproduce the 'name' error
"""
from portfolio_manager import PortfolioManager

# Create a simple test portfolio with 3 stocks
test_holdings = [
    {"name": "Apple", "amount": 22000},
    {"name": "Microsoft", "amount": 477700},
    {"name": "Google", "amount": 264960}
]

manager = PortfolioManager()

print("Testing portfolio analysis with 3 stocks...")
print(f"Holdings: {test_holdings}")

try:
    result = manager.analyze_portfolio_from_dollar_amounts(test_holdings, analysis_type="one_month")
    print(f"\nStatus: {result.get('status')}")
    if result.get('status') == 'SUCCESS':
        print("Analysis completed successfully!")
    else:
        print(f"Error: {result.get('message')}")
        if 'conversion_log' in result:
            print(f"Conversion log: {result['conversion_log']}")
except Exception as e:
    print(f"Exception occurred: {str(e)}")
    import traceback
    traceback.print_exc()
