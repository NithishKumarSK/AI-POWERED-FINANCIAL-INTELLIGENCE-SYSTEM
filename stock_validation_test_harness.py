"""
Stock Validation Test Harness
Known-answer tests for the stock prediction validation system.

All tests use the pure formula functions -- NO API calls, NO RAPIDAPI_KEY needed.

Run:
    python stock_validation_test_harness.py

Expected output (last line):
    ALL STOCK VALIDATION TESTS PASSED

Tests:
  1. TSLA formula (known-answer example: origin=402, target=371, capital=50000)
  2. 10% gain (BUY decision)
  3. -1.5% loss (HOLD decision -- within -2%/+2% band)
  4. -10% loss (SELL decision)
  5. Leakage detection: bars after origin date must be stripped/rejected
  6. Hash mismatch: compare_ai_vs_actual must block with mismatched hashes
  7. Stale state prevention: failed AI must not trigger comparison
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Import ONLY the pure-math functions -- no API calls
from stock_comparison_engine import (
    compute_actual_metrics,
    compare_ai_vs_actual,
    validate_no_leakage,
    decision_from_return,
)
from historical_price_service import filter_history_up_to

PASS = 0
FAIL = 0
_TOL = 0.01   # tolerance for float comparisons


def _assert(condition: bool, test_name: str, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {test_name}")
    else:
        FAIL += 1
        print(f"  FAIL  {test_name}" + (f" -- {detail}" if detail else ""))


def _close(a, b, tol=_TOL) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1 -- TSLA known-answer example
# origin=402, target=371, capital=50,000
# ══════════════════════════════════════════════════════════════════════════════

def test1_tsla_known_answer():
    print("\nTest 1: TSLA known-answer (origin=402, target=371, capital=50000)")
    origin_price   = 402.0
    target_price   = 371.0
    initial_capital = 50_000.0

    result = compute_actual_metrics(origin_price, target_price, initial_capital)

    expected_return     = -7.7114427861  # ((371-402)/402)*100
    expected_capital    = 46144.278606965  # 50000*(371/402)
    expected_pl         = -3855.721393035  # 46144.28... - 50000
    expected_decision   = "SELL"

    _assert(result["status"] == "SUCCESS", "status=SUCCESS")
    _assert(_close(result["actual_return_pct"],   expected_return, 0.0001),
            f"actual_return_pct={result['actual_return_pct']:.6f} expected={expected_return:.6f}",
            f"got {result['actual_return_pct']}, expected {expected_return}")
    _assert(_close(result["actual_final_capital"], expected_capital, 0.01),
            f"actual_final_capital={result['actual_final_capital']:.4f} expected={expected_capital:.4f}",
            f"got {result['actual_final_capital']}, expected {expected_capital}")
    _assert(_close(result["actual_total_pl"],      expected_pl, 0.01),
            f"actual_total_pl={result['actual_total_pl']:.4f} expected={expected_pl:.4f}",
            f"got {result['actual_total_pl']}, expected {expected_pl}")
    _assert(result["actual_decision"] == expected_decision,
            f"decision={result['actual_decision']} expected={expected_decision}")

    # Verify exact formula output
    _assert(
        abs(result["actual_final_capital"] - 46144.278606965) < 0.01,
        "Expected capital $46,144.28 -- formula matches",
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2 -- 10% gain -> BUY
# ══════════════════════════════════════════════════════════════════════════════

def test2_ten_pct_gain_buy():
    print("\nTest 2: 10% gain -> BUY (origin=100, target=110, capital=10000)")
    result = compute_actual_metrics(100.0, 110.0, 10_000.0)

    _assert(result["status"] == "SUCCESS",                         "status=SUCCESS")
    _assert(_close(result["actual_return_pct"], 10.0, 0.0001),     "return_pct=10.0%")
    _assert(_close(result["actual_final_capital"], 11_000.0, 0.01),"final_capital=11000")
    _assert(_close(result["actual_total_pl"], 1_000.0, 0.01),      "total_pl=1000")
    _assert(result["actual_decision"] == "BUY",                    "decision=BUY")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3 -- -1.5% -> HOLD (within the -2%/+2% neutral band)
# ══════════════════════════════════════════════════════════════════════════════

def test3_hold_band():
    print("\nTest 3: -1.5% -> HOLD (within -2%/+2% band)")
    result = compute_actual_metrics(100.0, 98.5, 10_000.0)

    _assert(result["status"] == "SUCCESS",                          "status=SUCCESS")
    _assert(_close(result["actual_return_pct"], -1.5, 0.0001),     "return_pct=-1.5%")
    _assert(_close(result["actual_final_capital"], 9_850.0, 0.01), "final_capital=9850")
    _assert(result["actual_decision"] == "HOLD",                   "decision=HOLD (not SELL)")

    # Also test the boundary: exactly -2.0 should be HOLD
    r2 = compute_actual_metrics(100.0, 98.0, 10_000.0)
    _assert(r2["actual_decision"] == "HOLD",
            "decision=HOLD at exactly -2.0% boundary")

    # +2.0 should be HOLD (threshold is > 2 for BUY)
    r3 = compute_actual_metrics(100.0, 102.0, 10_000.0)
    _assert(r3["actual_decision"] == "HOLD",
            "decision=HOLD at exactly +2.0% boundary")

    # +2.001 should be BUY
    r4 = compute_actual_metrics(100.0, 102.001, 10_000.0)
    _assert(r4["actual_decision"] == "BUY",
            "decision=BUY above +2% threshold")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 4 -- -10% -> SELL
# ══════════════════════════════════════════════════════════════════════════════

def test4_sell():
    print("\nTest 4: -10% -> SELL (origin=100, target=90, capital=10000)")
    result = compute_actual_metrics(100.0, 90.0, 10_000.0)

    _assert(result["status"] == "SUCCESS",                         "status=SUCCESS")
    _assert(_close(result["actual_return_pct"], -10.0, 0.0001),   "return_pct=-10.0%")
    _assert(_close(result["actual_final_capital"], 9_000.0, 0.01),"final_capital=9000")
    _assert(_close(result["actual_total_pl"], -1_000.0, 0.01),    "total_pl=-1000")
    _assert(result["actual_decision"] == "SELL",                   "decision=SELL")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 5 -- Leakage detection: bars after origin date must be rejected
# ══════════════════════════════════════════════════════════════════════════════

def test5_leakage_detection():
    print("\nTest 5: Leakage detection -- bars after origin date must be flagged")
    origin_date = "2026-03-01"

    # Bars that include a bar AFTER origin_date (future data = leakage)
    bars_with_leakage = [
        {"date": "2026-02-26", "close": 400.0},
        {"date": "2026-02-27", "close": 401.0},
        {"date": "2026-03-01", "close": 402.0},
        {"date": "2026-03-15", "close": 371.0},  # This is AFTER origin -- leakage!
        {"date": "2026-03-31", "close": 350.0},  # Also after -- leakage!
    ]

    check = validate_no_leakage(bars_with_leakage, origin_date)
    _assert(
        check["status"] == "LEAKAGE_DETECTED",
        "validate_no_leakage detects bars after origin_date",
        f"got status={check['status']}",
    )
    _assert(
        len(check["leaked_bars"]) == 2,
        "leaked_bars count=2",
        f"got {len(check.get('leaked_bars', []))}",
    )

    # Clean bars (all <= origin_date) must pass
    clean_bars = [
        {"date": "2026-02-26", "close": 400.0},
        {"date": "2026-02-27", "close": 401.0},
        {"date": "2026-03-01", "close": 402.0},
    ]
    clean_check = validate_no_leakage(clean_bars, origin_date)
    _assert(
        clean_check["status"] == "CLEAN",
        "validate_no_leakage passes clean bars",
        f"got status={clean_check['status']}",
    )

    # filter_history_up_to must strip all bars after cutoff
    from historical_price_service import filter_history_up_to
    filtered = filter_history_up_to(bars_with_leakage, origin_date)
    _assert(
        len(filtered) == 3,
        "filter_history_up_to removes 2 future bars, keeps 3",
        f"got {len(filtered)}",
    )
    _assert(
        all(b["date"] <= origin_date for b in filtered),
        "all filtered bars have date <= origin_date",
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 6 -- Hash mismatch: compare_ai_vs_actual must block
# ══════════════════════════════════════════════════════════════════════════════

def test6_hash_mismatch():
    print("\nTest 6: Hash mismatch -- compare_ai_vs_actual must block comparison")

    ai_pred = {
        "status": "SUCCESS",
        "stock_prediction_input_hash": "aaaa1111bbbb2222",
        "predicted_target_price": 380.0,
        "predicted_return_pct": -5.47,
        "predicted_final_capital": 47265.0,
        "predicted_total_pl": -2735.0,
        "decision": "SELL",
    }
    actual_val = {
        "status": "SUCCESS",
        "stock_prediction_input_hash": "zzzz9999xxxx8888",  # DIFFERENT hash
        "target_price": 371.0,
        "actual_return_pct": -7.71,
        "actual_final_capital": 46144.28,
        "actual_total_pl": -3855.72,
        "actual_decision": "SELL",
    }

    result = compare_ai_vs_actual(ai_pred, actual_val)
    _assert(
        result["status"] == "FAILED",
        "compare_ai_vs_actual returns FAILED on hash mismatch",
        f"got status={result['status']}",
    )
    _assert(
        "mismatch" in result.get("error", "").lower() or "hash" in result.get("error", "").lower(),
        "error message mentions hash mismatch",
        f"got error={result.get('error', '')}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 7 -- Stale state prevention: failed AI prediction blocks comparison
# ══════════════════════════════════════════════════════════════════════════════

def test7_failed_ai_blocks_comparison():
    print("\nTest 7: Failed AI prediction -- compare_ai_vs_actual must block")

    failed_ai = {
        "status": "ERROR",
        "stock_prediction_input_hash": "aaaa1111",
        "predicted_target_price": None,
        "predicted_return_pct": None,
        "predicted_final_capital": None,
        "decision": "REVIEW",
        "error": "Insufficient historical bars",
    }
    actual_val = {
        "status": "SUCCESS",
        "stock_prediction_input_hash": "aaaa1111",
        "target_price": 371.0,
        "actual_return_pct": -7.71,
        "actual_final_capital": 46144.28,
        "actual_total_pl": -3855.72,
        "actual_decision": "SELL",
    }

    result = compare_ai_vs_actual(failed_ai, actual_val)
    _assert(
        result["status"] == "FAILED",
        "compare_ai_vs_actual blocked when AI status=ERROR",
        f"got status={result['status']}",
    )
    _assert(
        result.get("agreement") == "UNVERIFIED",
        "agreement=UNVERIFIED when blocked",
        f"got agreement={result.get('agreement')}",
    )

    # Also test: successful AI + failed validation = blocked
    good_ai = {
        "status": "SUCCESS",
        "stock_prediction_input_hash": "aaaa1111",
        "predicted_target_price": 380.0,
        "predicted_return_pct": -5.47,
        "predicted_final_capital": 47265.0,
        "predicted_total_pl": -2735.0,
        "decision": "SELL",
    }
    failed_val = {
        "status": "FAILED",
        "stock_prediction_input_hash": "aaaa1111",
        "error": "Cannot get target price",
    }
    result2 = compare_ai_vs_actual(good_ai, failed_val)
    _assert(
        result2["status"] == "FAILED",
        "compare_ai_vs_actual blocked when actual status=FAILED",
        f"got status={result2['status']}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# BONUS: Verify MATCH vs CONFLICT correctly reported
# ══════════════════════════════════════════════════════════════════════════════

def test_bonus_match_conflict():
    print("\nBonus: MATCH and CONFLICT correctly labeled in comparison")

    # Both SELL -- should be MATCH
    ai_sell = {
        "status": "SUCCESS",
        "stock_prediction_input_hash": "abc123",
        "predicted_target_price": 380.0,
        "predicted_return_pct": -5.47,
        "predicted_final_capital": 47265.0,
        "predicted_total_pl": -2735.0,
        "decision": "SELL",
    }
    actual_sell = {
        "status": "SUCCESS",
        "stock_prediction_input_hash": "abc123",
        "target_price": 371.0,
        "actual_return_pct": -7.71,
        "actual_final_capital": 46144.28,
        "actual_total_pl": -3855.72,
        "actual_decision": "SELL",
    }
    match_result = compare_ai_vs_actual(ai_sell, actual_sell)
    _assert(match_result["status"] == "SUCCESS",       "match comparison succeeded")
    _assert(match_result["agreement"] == "MATCH",      "agreement=MATCH when both SELL")
    _assert(match_result["decision_match"] is True,    "decision_match=True")

    # AI says BUY, actual is SELL -- should be CONFLICT
    ai_buy = {**ai_sell, "predicted_return_pct": 5.0, "decision": "BUY",
              "predicted_target_price": 422.0, "predicted_final_capital": 52500.0}
    conflict_result = compare_ai_vs_actual(ai_buy, actual_sell)
    _assert(conflict_result["status"] == "SUCCESS",        "conflict comparison succeeded")
    _assert(conflict_result["agreement"] == "CONFLICT",    "agreement=CONFLICT when BUY vs SELL")
    _assert(conflict_result["decision_match"] is False,    "decision_match=False")
    _assert(conflict_result["final_decision"] == "REVIEW", "final_decision=REVIEW on conflict")


# ══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def run_all():
    print("=" * 60)
    print("STOCK VALIDATION TEST HARNESS")
    print("No API calls -- pure formula and logic tests")
    print("=" * 60)

    test1_tsla_known_answer()
    test2_ten_pct_gain_buy()
    test3_hold_band()
    test4_sell()
    test5_leakage_detection()
    test6_hash_mismatch()
    test7_failed_ai_blocks_comparison()
    test_bonus_match_conflict()

    print("\n" + "=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL == 0:
        print("\nALL STOCK VALIDATION TESTS PASSED")
        sys.exit(0)
    else:
        print(f"\nFAILED: {FAIL} test(s) did not pass. See details above.")
        sys.exit(1)


if __name__ == "__main__":
    run_all()
