"""
Test just the conversion step for user portfolio
"""

from portfolio_orchestrator import PortfolioOrchestrator

# User's portfolio holdings (dollar amounts) - test with just a few
test_holdings = [
    {"name": "Apple", "amount": 22000},
    {"name": "Microsoft", "amount": 477700},
    {"name": "Meta", "amount": 4000},
    {"name": "Netflix", "amount": 5080}
]

print("="*80)
print("TESTING DOLLAR AMOUNT CONVERSION")
print("="*80)

orchestrator = PortfolioOrchestrator()

print("\nConverting dollar amounts to shares...")
result = orchestrator.convert_dollar_amounts_to_shares(test_holdings)

print("\nConversion Results:")
for log in result['conversion_log']:
    print(f"\n{log['name']} -> {log['ticker']}")
    print(f"  Amount Invested: ${log['amount']:,.2f}")
    print(f"  Current Price: ${log['current_price']:.2f}")
    print(f"  Calculated Shares: {log['calculated_shares']:.2f}")
    print(f"  Avg Cost (set to current price): ${log['avg_cost']:.2f}")

print("\n" + "="*80)
print("Portfolio Data Structure:")
print("="*80)
for h in result['holdings']:
    print(f"\n{h['symbol']}:")
    print(f"  Shares: {h['shares']:.2f}")
    print(f"  Avg Cost: ${h['avg_cost']:.2f}")
    print(f"  Original Name: {h['original_name']}")
    print(f"  Original Amount: ${h['original_amount']:,.2f}")
