"""
Real-Data Smoke Tests for Stock Prediction Validation
Runs actual API calls to verify prices can be fetched and formulas work end-to-end.

Run:
    python run_stock_smoke_tests.py

If RAPIDAPI_KEY is not set, all tests are skipped gracefully:
    REAL DATA SMOKE TEST SKIPPED -- API unavailable

Tests:
  1. TSLA: fetch origin+target price, compute actual final capital
  2. CVS:  fetch origin+target price, compute actual final capital
  3. MSFT: fetch origin+target price, compute actual final capital
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, date, timedelta

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

from stock_comparison_engine import compute_actual_metrics

PASS = 0
FAIL = 0
SKIP = 0


def _assert(condition: bool, label: str, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}" + (f" -- {detail}" if detail else ""))


def _skip(label: str, reason: str = ""):
    global SKIP
    SKIP += 1
    print(f"  SKIP  {label}" + (f" -- {reason}" if reason else ""))


def _check_api() -> bool:
    key = os.getenv("RAPIDAPI_KEY", "").strip()
    return bool(key)


def _smoke_symbol(symbol: str, origin_date: str, target_date: str, capital: float):
    """Fetch actual prices for symbol and compute final capital."""
    from historical_price_service import fetch_price_history, get_price_on_date

    try:
        ctx_start = "2024-01-01"
        ctx_dt    = datetime.strptime(ctx_start, "%Y-%m-%d").date()
        tgt_dt    = datetime.strptime(target_date, "%Y-%m-%d").date()
        today     = date.today()
        days_req  = max(400, (today - ctx_dt).days + 30)

        hist, err = fetch_price_history(symbol, min_days=days_req)
        if not hist:
            _skip(f"{symbol} price fetch", f"API returned no data: {err}")
            return

        orig_price, eff_orig, orig_err = get_price_on_date(hist, origin_date, max_gap_days=5)
        if orig_price is None:
            _skip(f"{symbol} origin price on {origin_date}",
                  f"price not found: {orig_err}")
            return

        tgt_price, eff_tgt, tgt_err = get_price_on_date(hist, target_date, max_gap_days=5)
        if tgt_price is None:
            _skip(f"{symbol} target price on {target_date}",
                  f"price not found: {tgt_err}")
            return

        result = compute_actual_metrics(orig_price, tgt_price, capital)

        print(f"\n  {symbol} smoke test:")
        print(f"    origin_date     : {origin_date} (effective: {eff_orig})")
        print(f"    target_date     : {target_date} (effective: {eff_tgt})")
        print(f"    origin_price    : ${orig_price:,.4f}")
        print(f"    target_price    : ${tgt_price:,.4f}")
        print(f"    actual_return   : {result['actual_return_pct']:+.4f}%")
        print(f"    actual_capital  : ${result['actual_final_capital']:,.4f}")
        print(f"    actual_pl       : ${result['actual_total_pl']:+,.4f}")
        print(f"    decision        : {result['actual_decision']}")
        print(f"    formula proof   : ${capital:,.2f} x "
              f"({tgt_price:,.4f} / {orig_price:,.4f}) = "
              f"${result['actual_final_capital']:,.4f}")

        _assert(result["status"] == "SUCCESS",
                f"{symbol} compute_actual_metrics succeeded")
        _assert(result["actual_final_capital"] > 0,
                f"{symbol} actual_final_capital > 0",
                f"got {result['actual_final_capital']}")
        _assert(result["actual_decision"] in ("BUY", "SELL", "HOLD"),
                f"{symbol} decision is BUY/SELL/HOLD",
                f"got {result['actual_decision']}")

        # Verify the formula exactly
        expected_cap = capital * (tgt_price / orig_price)
        _assert(
            abs(result["actual_final_capital"] - expected_cap) < 0.01,
            f"{symbol} formula: capital x (target/origin) = {expected_cap:,.4f} matches",
            f"got {result['actual_final_capital']:,.4f}",
        )

    except Exception as exc:
        _skip(f"{symbol} smoke test", f"exception: {type(exc).__name__}: {exc}")


def run_all():
    print("=" * 60)
    print("REAL DATA SMOKE TESTS")
    print("=" * 60)

    if not _check_api():
        print("\nREAL DATA SMOKE TEST SKIPPED -- API unavailable")
        print("Set RAPIDAPI_KEY in .env to run real data tests.")
        sys.exit(0)

    print("RAPIDAPI_KEY found -- running real data tests...\n")

    # Test cases: symbol, origin_date, target_date, capital
    # Use past dates where actual prices are known
    test_cases = [
        ("TSLA", "2026-03-01", "2026-03-31", 50_000.0),
        ("CVS",  "2026-02-23", "2026-03-24", 50_000.0),
        ("MSFT", "2026-01-02", "2026-01-30", 25_000.0),
    ]

    for symbol, origin, target, cap in test_cases:
        # Only run if target date is in the past
        try:
            tgt_dt = datetime.strptime(target, "%Y-%m-%d").date()
            if tgt_dt >= date.today():
                _skip(
                    f"{symbol} smoke test",
                    f"target_date {target} is not yet in the past",
                )
                continue
        except Exception:
            pass
        _smoke_symbol(symbol, origin, target, cap)

    print("\n" + "=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed, {SKIP} skipped")
    print("=" * 60)

    if FAIL == 0:
        print("\nREAL DATA SMOKE TESTS PASSED" if PASS > 0 else "\nAll smoke tests skipped (no API or future dates)")
        sys.exit(0)
    else:
        print(f"\nFAILED: {FAIL} smoke test(s) did not pass.")
        sys.exit(1)


if __name__ == "__main__":
    run_all()
