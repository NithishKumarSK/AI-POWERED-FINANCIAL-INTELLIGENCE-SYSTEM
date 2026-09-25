"""
User Portfolio from Query
Parsed from user input - Dollar amounts invested
"""

# Parse the holdings from user query
# These are DOLLAR AMOUNTS invested, not shares
# Will calculate shares based on current price during analysis

raw_holdings = [
    {"name": "Fairfax India", "amount": 10000},  # $10,000
    {"name": "Google class", "amount": 264960},  # $264,960
    {"name": "Nitendo", "amount": 5200},
    {"name": "Brkb", "amount": 21336},
    {"name": "Qxo", "amount": 8871},
    {"name": "Markel group", "amount": 20000},
    {"name": "Epd", "amount": 11500},
    {"name": "Exo", "amount": 3960, "currency": "GBP"},  # £3,960
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
    {"name": "Apple", "amount": 22000},  # $22,000
    {"name": "Micron", "amount": 3800},
    {"name": "Nvida", "amount": 30397}
]

# Calculate total portfolio value
total_invested = sum(h["amount"] for h in raw_holdings if h.get("currency", "USD") == "USD")

print("Portfolio Summary:")
print(f"  Total Holdings: {len(raw_holdings)}")
print(f"  Total Invested (USD): ${total_invested:,.2f}")
print(f"  Cash: $0.00")
print(f"  Total Portfolio Value: ${total_invested:,.2f}")

print("\nHoldings (Dollar Amounts):")
for h in raw_holdings:
    currency = h.get("currency", "USD")
    symbol = "£" if currency == "GBP" else "$"
    print(f"  {h['name']}: {symbol}{h['amount']:,.2f}")

# Note: During analysis, the system will:
# 1. Convert company names to ticker symbols
# 2. Get current price for each stock
# 3. Calculate shares = amount / current_price
# 4. Set avg_cost = current_price (as requested)

