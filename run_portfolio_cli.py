"""
Simple command-line portfolio analysis - no web interface needed
"""

import sys
from portfolio_manager import PortfolioManager

# Force output flushing
sys.stdout.reconfigure(line_buffering=True)

# Your portfolio
portfolio_text = """
Fairfax India - 10000
Google class - 264960
Nitendo - 5200
Brkb - 21336
Qxo - 8871
Markel group - 20000
Epd - 11500
Verizon - 17800
Siri - 2500
Barrick - 11500
Gld - 15500
Netflix - 5080
Rgld - 14000
Ttwo - 2200
Wy - 4500
Sgov - 30000
Fwona - 5000
Wpm - 5000
Meta - 4000
Microsoft - 477700
Apple - 22000
Micron - 3800
Nvida - 30397
"""

def parse_portfolio_text(text_input: str) -> list:
    """Parse free-text portfolio input into structured holdings."""
    holdings = []
    lines = text_input.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        separators = ['-', '—', '–', ':', ',', '|', ' ']

        for sep in separators:
            if sep in line:
                parts = line.split(sep)
                if len(parts) >= 2:
                    name_part = parts[0].strip()
                    amount_part = parts[-1].strip()

                    if not name_part or name_part.replace('.', '').isdigit():
                        continue

                    amount_str = amount_part

                    if 'k' in amount_str.lower():
                        amount_before_k = amount_str.lower().replace('k', '')
                        try:
                            base_amount = float(amount_before_k)
                            if base_amount > 10000:
                                amount = base_amount
                            else:
                                amount = base_amount * 1000
                        except ValueError:
                            continue
                    else:
                        amount_str = ''.join(c for c in amount_str if c.isdigit() or c == '.')
                        try:
                            amount = float(amount_str)
                        except ValueError:
                            continue

                    if amount > 0:
                        holdings.append({"name": name_part, "amount": amount})
                    break

    return holdings


print("="*80, flush=True)
print("PORTFOLIO ANALYSIS - COMMAND LINE VERSION", flush=True)
print("="*80, flush=True)

# Parse portfolio
print("\nParsing portfolio...", flush=True)
holdings = parse_portfolio_text(portfolio_text)

print(f"Parsed {len(holdings)} holdings:", flush=True)
for h in holdings:
    print(f"  {h['name']}: ${h['amount']:,.2f}", flush=True)

total = sum(h['amount'] for h in holdings)
print(f"\nTotal: ${total:,.2f}", flush=True)

# Run analysis
print("\n" + "="*80, flush=True)
print("Starting portfolio analysis...", flush=True)
print("This will take approximately 6-8 minutes for 24 stocks", flush=True)
print("="*80, flush=True)

manager = PortfolioManager()

try:
    result = manager.analyze_portfolio_from_dollar_amounts(
        holdings,
        analysis_type="one_month"
    )

    print(f"\nStatus: {result['status']}", flush=True)
    if result['status'] == 'SUCCESS':
        print(f"Total Time: {result['total_time']}", flush=True)
        print("\n" + "="*80, flush=True)
        print("PORTFOLIO REPORT", flush=True)
        print("="*80, flush=True)
        print(result['final_report'], flush=True)

        # Save to file
        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"portfolio_report_{timestamp}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(result['final_report'])
        print(f"\nReport saved to: {filename}", flush=True)
    else:
        print(f"\nError: {result.get('message')}", flush=True)

except Exception as e:
    print(f"\nError: {str(e)}", flush=True)
    import traceback
    traceback.print_exc()

print("\n" + "="*80, flush=True)
print("ANALYSIS COMPLETE", flush=True)
print("="*80, flush=True)
