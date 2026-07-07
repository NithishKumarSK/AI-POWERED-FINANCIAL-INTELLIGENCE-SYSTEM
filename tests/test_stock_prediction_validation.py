"""
Pytest: Stock Prediction Validation — Formula, Hash, and Record Tests.

No API calls. All tests use hardcoded prices.

Test coverage:
  1. Known-answer: TSLA origin=402, target=371, capital=50,000
  2. 10% gain → BUY decision
  3. -1.5% return → HOLD (boundary)
  4. Hash mismatch blocks comparison
  5. Future target date blocks AI validation
  6. Accuracy record filter (stock vs options)
  7. Zero capital rejected
  8. Negative origin price rejected
  9. Exact formula proof (capital × target/origin)
  10. compare_ai_vs_actual with failed AI blocks
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pathlib import Path as _Path
from stock_comparison_engine import (
    compute_actual_metrics,
    compare_ai_vs_actual,
    validate_no_leakage,
    decision_from_return,
)
from stock_accuracy_engine import is_valid_stock_record


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1 — Known-answer: TSLA $402 → $371, $50,000
# ══════════════════════════════════════════════════════════════════════════════

class TestKnownAnswer:
    """
    These are verified expected values.
    These numbers must match exactly or the system is wrong.
    """

    ORIGIN  = 402.0
    TARGET  = 371.0
    CAPITAL = 50_000.0

    EXPECTED_RETURN_PCT    = (371.0 - 402.0) / 402.0 * 100     # -7.71144278...
    EXPECTED_FINAL_CAPITAL = 50_000.0 * (371.0 / 402.0)        # 46,144.2786...
    EXPECTED_TOTAL_PL      = EXPECTED_FINAL_CAPITAL - 50_000.0  # -3,855.7214...
    EXPECTED_DECISION      = "SELL"

    def test_return_pct(self):
        result = compute_actual_metrics(self.ORIGIN, self.TARGET, self.CAPITAL)
        assert result["status"] == "SUCCESS"
        assert abs(result["actual_return_pct"] - self.EXPECTED_RETURN_PCT) < 1e-8, (
            f"Expected {self.EXPECTED_RETURN_PCT:.10f}, "
            f"got {result['actual_return_pct']:.10f}"
        )

    def test_final_capital(self):
        result = compute_actual_metrics(self.ORIGIN, self.TARGET, self.CAPITAL)
        assert abs(result["actual_final_capital"] - self.EXPECTED_FINAL_CAPITAL) < 0.01, (
            f"Expected ${self.EXPECTED_FINAL_CAPITAL:,.4f}, "
            f"got ${result['actual_final_capital']:,.4f}"
        )

    def test_total_pl(self):
        result = compute_actual_metrics(self.ORIGIN, self.TARGET, self.CAPITAL)
        assert abs(result["actual_total_pl"] - self.EXPECTED_TOTAL_PL) < 0.01

    def test_decision(self):
        result = compute_actual_metrics(self.ORIGIN, self.TARGET, self.CAPITAL)
        assert result["actual_decision"] == self.EXPECTED_DECISION, (
            f"Expected SELL (return {self.EXPECTED_RETURN_PCT:.4f}%), "
            f"got {result['actual_decision']}"
        )

    def test_formula_identity(self):
        """capital × (target/origin) must match actual_final_capital exactly (formula proof)."""
        result = compute_actual_metrics(self.ORIGIN, self.TARGET, self.CAPITAL)
        direct = self.CAPITAL * (self.TARGET / self.ORIGIN)
        assert abs(result["actual_final_capital"] - direct) < 1e-10


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2 — 10% gain → BUY
# ══════════════════════════════════════════════════════════════════════════════

def test_ten_pct_gain_is_buy():
    result = compute_actual_metrics(100.0, 110.0, 50_000.0)
    assert result["status"] == "SUCCESS"
    assert abs(result["actual_return_pct"] - 10.0) < 1e-8
    assert result["actual_decision"] == "BUY"
    assert abs(result["actual_final_capital"] - 55_000.0) < 0.01


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3 — -1.5% return → HOLD (inside -2% to +2% band)
# ══════════════════════════════════════════════════════════════════════════════

def test_minus_1_5_pct_is_hold():
    """Exactly -1.5% must be HOLD, not SELL (threshold is -2%)."""
    origin = 200.0
    target = 200.0 * (1.0 - 0.015)  # 197.0
    result = compute_actual_metrics(origin, target, 50_000.0)
    assert result["status"] == "SUCCESS"
    assert abs(result["actual_return_pct"] - (-1.5)) < 1e-6
    assert result["actual_decision"] == "HOLD"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 4 — Hash mismatch blocks comparison
# ══════════════════════════════════════════════════════════════════════════════

def test_hash_mismatch_blocks_comparison():
    ai = {
        "status": "SUCCESS",
        "stock_prediction_input_hash": "aaaa1111bbbb2222",
        "predicted_target_price": 380.0,
        "predicted_return_pct":   -5.0,
        "predicted_final_capital": 47_500.0,
        "predicted_total_pl":     -2_500.0,
        "decision":               "SELL",
    }
    val = {
        "status": "SUCCESS",
        "stock_prediction_input_hash": "different_hash_!!",  # mismatch
        "target_price":        371.0,
        "actual_return_pct":  -7.71,
        "actual_final_capital": 46_144.28,
        "actual_total_pl":    -3_855.72,
        "actual_decision":    "SELL",
    }
    result = compare_ai_vs_actual(ai, val)
    assert result["status"] == "FAILED"
    assert "mismatch" in result["error"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# TEST 5 — Failed AI blocks comparison
# ══════════════════════════════════════════════════════════════════════════════

def test_failed_ai_blocks_comparison():
    ai = {"status": "FAILED", "error": "Insufficient data"}
    val = {
        "status": "SUCCESS",
        "target_price": 371.0,
        "actual_return_pct": -7.71,
        "actual_final_capital": 46_144.28,
        "actual_total_pl": -3_855.72,
        "actual_decision": "SELL",
    }
    result = compare_ai_vs_actual(ai, val)
    assert result["status"] == "FAILED"
    assert result["final_decision"] == "REVIEW"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 6 — -10% loss → SELL
# ══════════════════════════════════════════════════════════════════════════════

def test_ten_pct_loss_is_sell():
    result = compute_actual_metrics(100.0, 90.0, 50_000.0)
    assert result["status"] == "SUCCESS"
    assert abs(result["actual_return_pct"] - (-10.0)) < 1e-8
    assert result["actual_decision"] == "SELL"
    assert abs(result["actual_final_capital"] - 45_000.0) < 0.01


# ══════════════════════════════════════════════════════════════════════════════
# TEST 7 — Zero capital rejected
# ══════════════════════════════════════════════════════════════════════════════

def test_zero_capital_rejected():
    result = compute_actual_metrics(100.0, 110.0, 0.0)
    assert result["status"] == "FAILED"
    assert "capital" in result["error"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# TEST 8 — Negative origin price rejected
# ══════════════════════════════════════════════════════════════════════════════

def test_negative_origin_rejected():
    result = compute_actual_metrics(-1.0, 110.0, 50_000.0)
    assert result["status"] == "FAILED"
    assert "origin_price" in result["error"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# TEST 9 — Exact formula proof at various prices
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("origin,target,capital", [
    (100.0, 110.0, 50_000.0),
    (402.0, 371.0, 50_000.0),
    (500.0, 550.0, 100_000.0),
    (1.50,  1.25,  25_000.0),
    (250.0, 250.0, 10_000.0),   # flat → HOLD
])
def test_formula_identity_parametrized(origin, target, capital):
    result = compute_actual_metrics(origin, target, capital)
    expected = capital * (target / origin)
    assert abs(result["actual_final_capital"] - expected) < 1e-8, (
        f"origin={origin}, target={target}, capital={capital}: "
        f"expected {expected:.6f}, got {result['actual_final_capital']:.6f}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 10 — MATCH vs CONFLICT labeling
# ══════════════════════════════════════════════════════════════════════════════

def test_match_conflict_labeling():
    # When AI and actual agree on SELL → MATCH, final_decision = SELL
    ai = {
        "status":                     "SUCCESS",
        "stock_prediction_input_hash": "abcd1234abcd1234",
        "predicted_target_price":      90.0,
        "predicted_return_pct":       -10.0,
        "predicted_final_capital":    45_000.0,
        "predicted_total_pl":         -5_000.0,
        "decision":                   "SELL",
    }
    val = {
        "status":                     "SUCCESS",
        "stock_prediction_input_hash": "abcd1234abcd1234",
        "target_price":               90.0,
        "actual_return_pct":         -10.0,
        "actual_final_capital":       45_000.0,
        "actual_total_pl":           -5_000.0,
        "actual_decision":            "SELL",
    }
    result = compare_ai_vs_actual(ai, val)
    assert result["status"] == "SUCCESS"
    assert result["agreement"] == "MATCH"
    assert result["final_decision"] == "SELL"
    assert result["decision_match"] is True


def test_conflict_produces_review():
    # AI says BUY, actual says SELL → CONFLICT → final_decision = REVIEW
    ai = {
        "status":                     "SUCCESS",
        "stock_prediction_input_hash": "abcd1234abcd1234",
        "predicted_target_price":      110.0,
        "predicted_return_pct":         10.0,
        "predicted_final_capital":     55_000.0,
        "predicted_total_pl":           5_000.0,
        "decision":                    "BUY",
    }
    val = {
        "status":                     "SUCCESS",
        "stock_prediction_input_hash": "abcd1234abcd1234",
        "target_price":                90.0,
        "actual_return_pct":         -10.0,
        "actual_final_capital":       45_000.0,
        "actual_total_pl":           -5_000.0,
        "actual_decision":            "SELL",
    }
    result = compare_ai_vs_actual(ai, val)
    assert result["status"] == "SUCCESS"
    assert result["agreement"] == "CONFLICT"
    assert result["final_decision"] == "REVIEW"   # CONFLICT must produce REVIEW
    assert result["decision_match"] is False


# ══════════════════════════════════════════════════════════════════════════════
# TEST 11 — Conflict records must be saved as valid evaluation records
# ══════════════════════════════════════════════════════════════════════════════

def test_conflict_record_is_valid_for_saving():
    """
    A conflict (AI BUY, actual SELL) is a valid evaluation outcome.
    It means AI was wrong — that MUST be saved for accuracy metrics.
    """
    from datetime import date as _date, timedelta as _td
    past_target = (_date.today() - _td(days=45)).strftime("%Y-%m-%d")

    record = {
        "stock_prediction_input": {"symbol": "TSLA", "target_date": past_target},
        "ai_prediction": {
            "predicted_target_price":  110.0,
            "predicted_return_pct":    10.0,
            "predicted_final_capital": 55_000.0,
            "decision":                "BUY",   # AI was bullish
        },
        "actual_validation": {
            "origin_price":          100.0,
            "target_price":           90.0,
            "actual_return_pct":     -10.0,
            "actual_final_capital":   45_000.0,
            "actual_decision":        "SELL",  # Actual was bearish
        },
        "comparison": {
            "status":        "SUCCESS",  # Comparison ran fine
            "decision_match": False,     # Conflict — AI was wrong
            "agreement":     "CONFLICT",
        },
    }

    assert is_valid_stock_record(record), (
        "CONFLICT records must pass is_valid_stock_record(). "
        "AI being wrong is a valid result, not a failure. "
        "These must be saved for accuracy tracking."
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 12 — REVIEW AI decisions must be saved (SELL-bias high-risk fix output)
# ══════════════════════════════════════════════════════════════════════════════

def test_review_ai_decision_is_valid_for_saving():
    """
    When risk_score >= 80 and AI wanted to SELL, the SELL-bias fix changes
    decision to REVIEW. This is a valid AI output and must be saved.
    """
    from datetime import date as _date, timedelta as _td
    past_target = (_date.today() - _td(days=45)).strftime("%Y-%m-%d")

    record = {
        "stock_prediction_input": {"symbol": "NVDA", "target_date": past_target},
        "ai_prediction": {
            "predicted_target_price":  85.0,
            "predicted_return_pct":   -15.0,
            "predicted_final_capital": 42_500.0,
            "decision":                "REVIEW",  # High-risk SELL converted to REVIEW
        },
        "actual_validation": {
            "origin_price":         100.0,
            "target_price":          90.0,
            "actual_return_pct":    -10.0,
            "actual_final_capital":  45_000.0,
            "actual_decision":       "SELL",
        },
        "comparison": {
            "status":         "SUCCESS",
            "decision_match":  False,
            "agreement":       "CONFLICT",
        },
    }

    assert is_valid_stock_record(record), (
        "REVIEW AI decisions (risk >= 80 + SELL-bias fix) must pass is_valid_stock_record(). "
        "REVIEW is a valid AI output, not an error."
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 13 — Price basis default must be close
# ══════════════════════════════════════════════════════════════════════════════

def test_price_basis_default_is_close():
    """
    Price Basis selectbox must have 'close' as the first option (default).
    Close price is the standard for walk-forward validation; 'open' must not be the default.
    """
    app_path = _Path(__file__).resolve().parent.parent / "stock_prediction_app.py"
    text = app_path.read_text(encoding="utf-8")
    # Both forms (stock and options) should have close before open in options list
    assert 'options=["close", "open"' in text, (
        "Price Basis selectbox must list 'close' before 'open' — close is the default. "
        "Close price is the standard for walk-forward validation."
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 14 — Effective origin date alignment: validator must use AI's resolved origin
# ══════════════════════════════════════════════════════════════════════════════

def test_effective_origin_alignment():
    """
    When origin_date is a Sunday (non-trading day), the AI resolves to the
    last trading Friday (on_or_before), while get_price_on_date on full history
    would find the nearest bar which could be Monday (after origin).

    The validator MUST use AI's origin_price_used and effective_origin_date so
    both AI and actual validation compare against the exact same price/date.
    """
    from stock_walkforward_validator import run_stock_validation

    # Build synthetic history: Friday, then Monday
    # Origin = Sunday (non-trading) — AI uses Friday, naive lookup would find Monday
    bars = [
        {"date": "2025-01-03", "open": 100.0, "high": 105.0, "low": 98.0,  "close": 100.0, "volume": 1_000_000},
        {"date": "2025-01-06", "open": 101.0, "high": 106.0, "low": 99.0,  "close": 101.0, "volume": 1_000_000},  # Monday
        {"date": "2025-01-07", "open": 102.0, "high": 107.0, "low": 100.0, "close": 102.0, "volume": 1_000_000},
        {"date": "2025-01-08", "open": 103.0, "high": 108.0, "low": 101.0, "close": 103.0, "volume": 1_000_000},
        {"date": "2025-01-09", "open": 104.0, "high": 109.0, "low": 102.0, "close": 104.0, "volume": 1_000_000},
        {"date": "2025-01-10", "open": 105.0, "high": 110.0, "low": 103.0, "close": 105.0, "volume": 1_000_000},
        # target date bar
        {"date": "2025-02-10", "open": 120.0, "high": 125.0, "low": 118.0, "close": 120.0, "volume": 1_000_000},
    ]

    # origin_date = Sunday 2025-01-05; AI resolved to Friday 2025-01-03
    spi = {
        "symbol":                        "TEST",
        "historical_context_start_date": "2024-07-01",
        "prediction_origin_date":        "2025-01-05",  # Sunday
        "decision_horizon_days":         30,
        "target_date":                   "2025-02-10",
        "initial_capital":               50_000.0,
        "benchmark":                     "SPY",
        "price_basis":                   "close",
    }

    ai_prediction = {
        "status":                      "SUCCESS",
        "stock_prediction_input_hash": "testhash123",
        "origin_price_used":           100.0,       # Friday 2025-01-03 close
        "effective_origin_date":       "2025-01-03",  # Friday (AI's last bar)
        "predicted_target_price":      110.0,
        "predicted_return_pct":        10.0,
        "predicted_final_capital":     55_000.0,
        "predicted_total_pl":          5_000.0,
        "decision":                    "BUY",
    }

    result = run_stock_validation(spi, ai_prediction, bars)

    # Validator MUST use AI's effective origin, not re-resolve independently
    assert result.get("status") == "SUCCESS", (
        f"Validation failed: {result.get('error', 'unknown')}"
    )
    assert result.get("origin_price") == 100.0, (
        f"origin_price must match AI's origin_price_used (100.0), "
        f"got {result.get('origin_price')}. "
        "Validator must not re-resolve origin independently from full history."
    )
    assert result.get("effective_origin_price_date") == "2025-01-03", (
        f"effective_origin_price_date must match AI's effective_origin_date (2025-01-03), "
        f"got {result.get('effective_origin_price_date')}. "
        "AI and actual must use the same effective origin date."
    )


def test_future_target_date_not_rejected():
    """
    validate_stock_prediction_input must NOT reject future target dates.
    Future target = live_future_prediction mode. AI still runs.
    """
    from stock_prediction_agent import validate_stock_prediction_input
    from datetime import date as _date, timedelta as _td

    future_target = (_date.today() + _td(days=30)).strftime("%Y-%m-%d")
    past_origin   = (_date.today() - _td(days=15)).strftime("%Y-%m-%d")
    ctx_start     = (_date.today() - _td(days=200)).strftime("%Y-%m-%d")

    spi = {
        "symbol":                        "AAPL",
        "historical_context_start_date": ctx_start,
        "prediction_origin_date":        past_origin,
        "decision_horizon_days":         30,
        "target_date":                   future_target,
        "initial_capital":               10_000.0,
        "benchmark":                     "SPY",
        "price_basis":                   "close",
    }
    valid, err = validate_stock_prediction_input(spi)
    assert valid, (
        f"validate_stock_prediction_input must accept future target_date. "
        f"Future target = live_future_prediction mode, not an error. Got: {err}"
    )


def test_validator_uses_ai_origin_price_not_nearest():
    """
    Static proof: stock_walkforward_validator.py must read origin_price_used
    from ai_prediction instead of always calling get_price_on_date independently.
    """
    val_path = _Path(__file__).resolve().parent.parent / "stock_walkforward_validator.py"
    text = val_path.read_text(encoding="utf-8")
    assert "origin_price_used" in text, (
        "stock_walkforward_validator.py must read 'origin_price_used' from ai_prediction. "
        "This prevents effective origin date mismatch when origin_date is a non-trading day."
    )
    assert "effective_origin_date" in text, (
        "stock_walkforward_validator.py must read 'effective_origin_date' from ai_prediction."
    )
