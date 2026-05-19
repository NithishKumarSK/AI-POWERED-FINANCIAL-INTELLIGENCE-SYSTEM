"""
Test text parsing for portfolio input
"""

def parse_portfolio_text(text_input: str) -> list:
    """Parse free-text portfolio input into structured holdings."""
    holdings = []
    lines = text_input.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try different separators
        separators = ['-', '—', '–', ':', ',', '|']

        for sep in separators:
            if sep in line:
                parts = line.split(sep)
                if len(parts) >= 2:
                    name = parts[0].strip()
                    # Extract amount from second part
                    amount_str = parts[1].strip()

                    # Handle 'k' suffix (multiply by 1000)
                    if 'k' in amount_str.lower():
                        # Remove 'k' and multiply by 1000
                        amount_str = amount_str.lower().replace('k', '')
                        try:
                            amount = float(amount_str) * 1000
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
                        holdings.append({"name": name, "amount": amount})
                    break  # Successfully parsed, move to next line

    return holdings


# Test with user's portfolio format
test_text = """Fairfax India - 10k
Google class - 26496k
Nitendo- 5200
Brkb- 21336
Qxo- 8871
Markel group - 20000
Epd- 11500
Verizon - 17800
Siri 2500
Barrick 11500
Gld 15500
Netflix - 5080
Rgld- 14000
Ttwo- 2200
Wy - 4500
Sgov- 30000
Fwona 5000
Wpm- 5000
Meta - 4000
Microsoft- 477700
Apple - 22k
Micron - 3800
Nvida- 30397"""

print("Testing Portfolio Text Parsing")
print("="*80)

parsed = parse_portfolio_text(test_text)

print(f"\nParsed {len(parsed)} holdings:")
for h in parsed:
    print(f"  {h['name']}: ${h['amount']:,.2f}")

print(f"\nTotal: ${sum(h['amount'] for h in parsed):,.2f}")
