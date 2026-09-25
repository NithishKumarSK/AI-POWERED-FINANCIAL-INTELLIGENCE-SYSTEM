"""
Test the improved parser with user's format
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
        separators = ['-', '—', '–', ':', ',', '|', ' ']

        for sep in separators:
            if sep in line:
                parts = line.split(sep)
                if len(parts) >= 2:
                    # Try to identify which part is the name and which is the amount
                    # The name is usually first, amount is usually last
                    name_part = parts[0].strip()
                    amount_part = parts[-1].strip()

                    # Skip if name is empty or looks like a number
                    if not name_part or name_part.replace('.', '').isdigit():
                        continue

                    # Extract amount from second part
                    amount_str = amount_part

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
                        holdings.append({"name": name_part, "amount": amount})
                    break  # Successfully parsed, move to next line

    return holdings


# Test with user's exact format
test_text = """Fairfax India - 10k
Google class - 26496k
Nitendo- 5200
Brkb- 21336"""

print("Testing parser with user's format:")
print(test_text)
print("\n" + "="*80)

parsed = parse_portfolio_text(test_text)

print(f"\nParsed {len(parsed)} holdings:")
for h in parsed:
    print(f"  {h['name']}: ${h['amount']:,.2f}")
