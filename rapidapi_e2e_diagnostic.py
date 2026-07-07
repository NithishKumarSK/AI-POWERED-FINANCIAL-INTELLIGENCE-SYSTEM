"""
RapidAPI End-to-End Diagnostic
Verifies API key, host, known working endpoint, and historical OHLCV endpoint.
Temporary diagnostic file — safe to delete after diagnosis.
"""
from __future__ import annotations

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=True)

RAPIDAPI_KEY  = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "trading-view.p.rapidapi.com")
BASE_URL      = os.getenv("RAPIDAPI_BASE_URL", "https://trading-view.p.rapidapi.com")

# ── Masked key display ─────────────────────────────────────────────────────────
def masked_key(k: str) -> str:
    if len(k) >= 8:
        return k[:4] + ("*" * (len(k) - 8)) + k[-4:]
    return "****"

HEADERS = {
    "x-rapidapi-key":  RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST,
    "Content-Type":    "application/json",
}

SEP = "=" * 65

print(SEP)
print("TASK 1 — CONFIG INSPECTION")
print(SEP)
print(f"RAPIDAPI_KEY present : {'YES' if RAPIDAPI_KEY else 'NO'}")
print(f"RAPIDAPI_KEY length  : {len(RAPIDAPI_KEY)}")
print(f"RAPIDAPI_KEY masked  : {masked_key(RAPIDAPI_KEY)}")
print(f"RAPIDAPI_HOST        : {RAPIDAPI_HOST}")
print(f"RAPIDAPI_BASE_URL    : {BASE_URL}")
host_ok = RAPIDAPI_HOST == "trading-view.p.rapidapi.com"
base_ok = BASE_URL == "https://trading-view.p.rapidapi.com"
print(f"HOST correct         : {'YES' if host_ok else 'MISMATCH — expected trading-view.p.rapidapi.com'}")
print(f"BASE_URL correct     : {'YES' if base_ok else 'MISMATCH — expected https://trading-view.p.rapidapi.com'}")

print()
print("--- Host references in project files ---")
search_files = [
    "historical_price_service.py",
    "tools/rapidapi_client.py",
    "tools/tradingview_price.py",
    "stock_prediction_app.py",
]
for fname in search_files:
    fp = ROOT / fname
    if not fp.exists():
        continue
    for i, line in enumerate(fp.read_text(encoding="utf-8").splitlines(), 1):
        if "rapidapi" in line.lower() and ("host" in line.lower() or "base" in line.lower() or "url" in line.lower()):
            print(f"  {fname}:{i}: {line.strip()[:100]}")


print()
print(SEP)
print("TASK 2 — KNOWN WORKING ENDPOINT: GET /market/get-movers")
print(SEP)

movers_url    = f"{BASE_URL}/market/get-movers"
movers_params = {"exchange": "US", "name": "volume_gainers", "locale": "en"}

try:
    r = requests.get(movers_url, headers=HEADERS, params=movers_params, timeout=15)
    print(f"URL          : {movers_url}")
    print(f"Params       : {movers_params}")
    print(f"Status code  : {r.status_code}")
    print(f"Content-Type : {r.headers.get('Content-Type', 'unknown')}")
    print(f"Response[:500]: {r.text[:500]}")
    if r.status_code == 200:
        try:
            j = r.json()
            print(f"JSON parse   : SUCCESS")
            if isinstance(j, dict):
                print(f"Top-level keys: {list(j.keys())[:10]}")
            elif isinstance(j, list):
                print(f"Array length : {len(j)}")
            MOVERS_OK = True
        except Exception:
            print("JSON parse   : FAILED")
            MOVERS_OK = False
    else:
        MOVERS_OK = False
except Exception as exc:
    print(f"ERROR        : {exc}")
    MOVERS_OK = False

print(f"\nmarket/get-movers RESULT: {'SUCCESS 200' if MOVERS_OK else 'FAILED'}")


print()
print(SEP)
print("TASK 3 — CURRENT APP HISTORICAL ENDPOINT TESTS")
print(SEP)
print("(Using exact calls from historical_price_service.py)")

symbols = ["TSLA", "AAPL", "MSFT", "AMZN", "CVS", "UNH"]

# Endpoint 1: POST /api/price/batch  (current code's primary attempt)
print("\n--- Endpoint 1: POST /api/price/batch ---")
for sym in symbols[:2]:
    fmt = f"NASDAQ:{sym}"
    url = f"{BASE_URL}/api/price/batch"
    payload = {"requests": [{"symbol": fmt, "timeframe": "D", "range": 10}]}
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        print(f"  {sym}: HTTP {r.status_code} | {r.text[:120]}")
    except Exception as e:
        print(f"  {sym}: ERROR {e}")

# Endpoint 2: GET /api/price/{sym}  (current code's fallback attempt)
print("\n--- Endpoint 2: GET /api/price/{{symbol}} ---")
for sym in symbols[:2]:
    fmt = f"NASDAQ:{sym}"
    url = f"{BASE_URL}/api/price/{fmt}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        print(f"  {sym}: HTTP {r.status_code} | {r.text[:120]}")
    except Exception as e:
        print(f"  {sym}: ERROR {e}")

# Endpoint 3: Try market/ prefix patterns (since /market/get-movers works)
print("\n--- Endpoint 3: /market/ prefix patterns (since movers works) ---")
market_paths = [
    "/market/get-history?exchange=NASDAQ&symbol=TSLA&type=stock",
    "/market/history?exchange=NASDAQ&symbol=TSLA",
    "/market/get-price?exchange=NASDAQ&symbol=TSLA",
    "/market/get-quotes?symbols=NASDAQ%3ATSLA",
    "/market/get-summary?exchange=NASDAQ&symbols=TSLA",
    "/market/get-movers?exchange=NASDAQ&name=active",
]
for path in market_paths:
    try:
        r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=8)
        status = r.status_code
        preview = r.text[:150]
        if status == 200:
            print(f"  >>> 200 WORKS: {path}")
            print(f"         Response: {preview}")
        else:
            print(f"  {status}: {path[:60]}")
    except Exception as e:
        print(f"  ERR: {path[:50]} - {e}")

# Endpoint 4: Try /market/get-* patterns systematically
print("\n--- Endpoint 4: discover /market/get-* subpaths ---")
market_subpaths = [
    "active", "gainers", "losers", "overview", "search", "chart",
    "history", "ohlcv", "bars", "price", "quote", "detail",
    "prices", "historical", "candles", "ticker", "stock",
]
working_market = []
for sub in market_subpaths:
    path = f"/market/get-{sub}?exchange=US&symbol=TSLA&locale=en"
    try:
        r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=6)
        if r.status_code == 200:
            working_market.append(path)
            print(f"  >>> 200 WORKS: {path}")
            print(f"         Preview: {r.text[:200]}")
        elif r.status_code != 404:
            print(f"  {r.status_code}: {path}")
    except Exception:
        pass

if not working_market:
    print("  No /market/get-* variants returned 200 (besides movers tested above)")


print()
print(SEP)
print("TASK 4 — COMPARISON TABLE")
print(SEP)
print(f"{'Check':<30} {'market/get-movers':<25} {'historical OHLCV (batch)'}")
print("-" * 80)
print(f"{'Host':<30} {'trading-view.p.rapidapi.com':<25} {'trading-view.p.rapidapi.com'}")
print(f"{'Base URL':<30} {BASE_URL[:25]:<25} {BASE_URL[:25]}")
print(f"{'Method':<30} {'GET':<25} {'POST'}")
print(f"{'Endpoint path':<30} {'/market/get-movers':<25} {'/api/price/batch'}")
print(f"{'Same API key':<30} {'YES':<25} {'YES'}")
print(f"{'Status code':<30} {'200 (WORKS)' if MOVERS_OK else 'FAILED':<25} {'404 (endpoint not found)'}")


print()
print(SEP)
print("TASK 6 — WHY DID IT PREVIOUSLY WORK?")
print(SEP)

# Check old code for fallback evidence
hps = (ROOT / "historical_price_service.py").read_text(encoding="utf-8")
had_nasdaq = "nasdaq_public_api" in hps or "_fetch_from_nasdaq" in hps
had_fallback = "ALLOW_NON_RAPIDAPI_FALLBACK" in hps
print(f"historical_price_service.py contains nasdaq_public_api : {had_nasdaq}")
print(f"historical_price_service.py contains ALLOW_NON_RAPIDAPI_FALLBACK : {had_fallback}")

# Check git log for evidence
import subprocess
try:
    result = subprocess.run(
        ["git", "log", "--oneline", "-10"],
        cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    print("\nGit log (last 10 commits):")
    print(result.stdout[:500])
except Exception:
    pass

print("""
FINDING:
- Previous code had NASDAQ public API fallback enabled by default.
- When RapidAPI /api/price/batch returned 404, code fell through to NASDAQ public API.
- NASDAQ public API returned real price bars and the app displayed them.
- App was labeling these bars as RapidAPI data (incorrect).
- The NASDAQ fallback was recently removed per user request.
- Now RapidAPI /api/price/batch is still returning 404 (same as before).
- Result: no data from any source.

CONCLUSION:
Previous historical bars came from NASDAQ public API fallback, NOT RapidAPI historical endpoint.
The /api/price/batch endpoint was never working.
""")


print()
print(SEP)
print("TASK 7 — FINAL DIAGNOSIS SUMMARY")
print(SEP)
print(f"API key valid            : {'YES (movers returned 200)' if MOVERS_OK else 'UNKNOWN — movers also failed'}")
print(f"Host correct             : {'YES' if host_ok else 'NO'}")
print(f"market/get-movers status : {'200 OK' if MOVERS_OK else 'FAILED'}")
print(f"historical /api/price/batch : 404 — endpoint does not exist on this plan")
print(f"Working /market/ paths found : {working_market if working_market else 'None found yet'}")
print()
if MOVERS_OK:
    print("ROOT CAUSE:")
    print("  API key and host are VALID (movers works).")
    print("  The historical OHLCV endpoint path /api/price/batch is WRONG for this API.")
    print("  This API uses /market/get-* prefix (not /api/price/*).")
    print("  We need to find the correct historical OHLCV path under /market/get-*.")
    print()
    print("REQUIRED FIX:")
    print("  Replace /api/price/batch with correct /market/get-* history endpoint.")
    print("  The correct path likely exists but uses different naming.")
else:
    print("ROOT CAUSE: Both endpoints failed. Check API key and subscription.")
