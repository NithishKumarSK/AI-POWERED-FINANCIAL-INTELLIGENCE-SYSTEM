"""RapidAPI smoke test — correct host, confirmed working endpoint.

Run: python test_rapidapi_smoke.py

Correct host  : trading-view.p.rapidapi.com
Test endpoint : GET /market/get-movers

SECURITY: Never prints or logs the key value.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
except ImportError:
    pass

sys.path.insert(0, str(ROOT / "tools"))
from rapidapi_client import get_rapidapi_key, get_rapidapi_host, get_rapidapi_base_url, rapidapi_get


def run_smoke_test() -> bool:
    print("\n=== RapidAPI Smoke Test ===")

    key = get_rapidapi_key()
    host = get_rapidapi_host()
    base_url = get_rapidapi_base_url()

    print(f"Key present : {bool(key)}")
    print(f"Key length  : {len(key) if key else 0}")
    print(f"Host        : {host}")
    print(f"Base URL    : {base_url}")

    if not key:
        print("\nFAIL: RAPIDAPI_KEY not found in environment.")
        return False

    # Test the confirmed working endpoint
    print(f"\nProbing: {base_url}/market/get-movers")
    result = rapidapi_get(
        "/market/get-movers",
        params={"exchange": "US", "name": "volume_gainers", "locale": "en"},
        timeout=20,
    )

    status = result.get("status")
    error_type = result.get("error_type", "")
    preview = str(result.get("preview", ""))

    print(f"Status     : {status}")
    if error_type:
        print(f"Error type : {error_type}")

    if status == "SUCCESS":
        data = result.get("data", {})
        if isinstance(data, dict):
            print(f"Top-level keys : {list(data.keys())[:8]}")
        elif isinstance(data, list):
            print(f"Items returned : {len(data)}")
        print("\nPASS: RapidAPI is reachable and subscription is active.")
        return True
    elif error_type == "RAPIDAPI_403":
        print(f"Preview    : {preview[:200]}")
        print("\nFAIL: 403 — check host or subscription status.")
        return False
    else:
        msg = result.get("message", "unknown")
        print(f"\nFAIL: {error_type} — {msg}")
        return False


if __name__ == "__main__":
    ok = run_smoke_test()
    sys.exit(0 if ok else 1)
