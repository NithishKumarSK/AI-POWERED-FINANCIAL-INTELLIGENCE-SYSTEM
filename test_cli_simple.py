"""
Test basic CLI functionality
"""
import sys
import os

print("Testing basic imports...")

try:
    from portfolio_manager import PortfolioManager
    print("SUCCESS: PortfolioManager imported successfully")
except Exception as e:
    print(f"FAILED: Could not import PortfolioManager: {e}")
    sys.exit(1)

print("\nInitializing PortfolioManager...")
try:
    manager = PortfolioManager()
    print("SUCCESS: PortfolioManager initialized successfully")
except Exception as e:
    print(f"FAILED: Could not initialize PortfolioManager: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nTesting simple portfolio...")
test_holdings = [{"name": "Apple", "amount": 22000}]

try:
    result = manager.analyze_portfolio_from_dollar_amounts(test_holdings, analysis_type="one_month")
    print(f"SUCCESS: Analysis completed with status: {result.get('status')}")
    if result.get('status') == 'SUCCESS':
        print("SUCCESS: Test passed!")
    else:
        print(f"FAILED: Analysis returned: {result.get('message')}")
except Exception as e:
    print(f"FAILED: Analysis error: {e}")
    import traceback
    traceback.print_exc()

print("\nAll tests completed!")
