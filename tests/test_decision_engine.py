"""
Pytest: Decision Engine Tests — Amaan's SELL-Bias Fix.

Critical guarantee: Risk score alone must NEVER force a SELL.
No API calls. All tests use make_decision() directly.

Test coverage:
  1. Clean BUY path (return +5%, no risk issues)
  2. Clean SELL path (return -5%, no risk issues)
  3. Clean HOLD path (return +1%)
  4. Low data quality → REVIEW (data_quality < 60)
  5. SELL bias prevention: predicted=-0.5%, risk=90 → NOT SELL (must be HOLD)
  6. High risk + BUY → downgraded to HOLD
  7. High risk + SELL → converted to REVIEW (risk alone NEVER = SELL)
  8. Low confidence → REVIEW
  9. Boundary: return exactly +3.0% → BUY
  10. Boundary: return exactly -3.0% → SELL (before risk adjustment)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stock_prediction_agent import make_decision


def _decide(**kwargs) -> str:
    """Extract just the decision string from make_decision() — handles tuple or str return."""
    result = make_decision(**kwargs)
    return result[0] if isinstance(result, tuple) else result


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1 — Clean BUY: return +5%, confidence 75, risk 30, quality 90
# ══════════════════════════════════════════════════════════════════════════════

def test_clean_buy():
    decision = _decide(
        predicted_return_pct=5.0,
        confidence_score=75,
        risk_score=30,
        data_quality_score=90,
    )
    assert decision == "BUY", f"Expected BUY, got {decision}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2 — Clean SELL: return -5%, confidence 70, risk 30, quality 85
# ══════════════════════════════════════════════════════════════════════════════

def test_clean_sell():
    decision = _decide(
        predicted_return_pct=-5.0,
        confidence_score=70,
        risk_score=30,
        data_quality_score=85,
    )
    assert decision == "SELL", f"Expected SELL, got {decision}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3 — HOLD: return +1%, well inside band
# ══════════════════════════════════════════════════════════════════════════════

def test_clean_hold():
    decision = _decide(
        predicted_return_pct=1.0,
        confidence_score=65,
        risk_score=40,
        data_quality_score=80,
    )
    assert decision == "HOLD", f"Expected HOLD, got {decision}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 4 — Low data quality → REVIEW regardless of return or risk
# ══════════════════════════════════════════════════════════════════════════════

def test_low_data_quality_forces_review():
    decision = _decide(
        predicted_return_pct=10.0,   # strong BUY signal
        confidence_score=90,
        risk_score=10,
        data_quality_score=55,       # < 60 → REVIEW
    )
    assert decision == "REVIEW", (
        f"data_quality_score=55 must produce REVIEW, got {decision}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 5 — SELL BIAS PREVENTION (Amaan's critical test)
#
# Amaan reported: system was forcing SELL even when return was barely negative.
# Rule: risk alone must NEVER create SELL.
# predicted=-0.5%, risk=90 → HOLD (not SELL, not risk-driven SELL)
# ══════════════════════════════════════════════════════════════════════════════

def test_sell_bias_prevention_high_risk_marginal_negative():
    """
    CRITICAL: predicted=-0.5% is HOLD territory (-3% to +3% band).
    Even with risk=90, the decision must NOT become SELL.
    Risk >= 80 can only downgrade BUY→HOLD or convert SELL→REVIEW.
    It CANNOT manufacture SELL from HOLD.
    """
    decision = _decide(
        predicted_return_pct=-0.5,   # inside HOLD band (-3% to +3%)
        confidence_score=60,
        risk_score=90,               # very high risk
        data_quality_score=75,
    )
    assert decision != "SELL", (
        f"SELL BIAS BUG: risk=90 + return=-0.5% (HOLD band) must NOT produce SELL. "
        f"Got: {decision}"
    )
    # -0.5% is HOLD territory — high risk should keep it HOLD or at most REVIEW
    assert decision in ("HOLD", "REVIEW"), (
        f"Expected HOLD or REVIEW for marginal negative + high risk. Got: {decision}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 6 — High risk + BUY → downgraded to HOLD
# ══════════════════════════════════════════════════════════════════════════════

def test_high_risk_buy_downgraded_to_hold():
    """return=+4% (BUY), risk=85 → risk >= 80 + BUY = downgrade to HOLD."""
    decision = _decide(
        predicted_return_pct=4.0,
        confidence_score=65,
        risk_score=85,
        data_quality_score=80,
    )
    assert decision == "HOLD", (
        f"risk=85 + BUY must be downgraded to HOLD. Got: {decision}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 7 — High risk + SELL → converted to REVIEW (never kept as SELL)
#
# This is the core Amaan fix: risk >= 80 converts SELL → REVIEW.
# Risk alone must NEVER force SELL.
# ══════════════════════════════════════════════════════════════════════════════

def test_high_risk_sell_converted_to_review():
    """
    return=-5% (SELL territory), risk=85 → risk >= 80 + SELL = REVIEW.
    The system was incorrectly keeping SELL in high-risk situations.
    """
    decision = _decide(
        predicted_return_pct=-5.0,
        confidence_score=65,
        risk_score=85,
        data_quality_score=80,
    )
    assert decision == "REVIEW", (
        f"risk=85 + SELL must be converted to REVIEW. Got: {decision}. "
        "This was Amaan's bug report: risk was forcing aggressive SELL."
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 8 — Low confidence → REVIEW
# ══════════════════════════════════════════════════════════════════════════════

def test_low_confidence_forces_review():
    decision = _decide(
        predicted_return_pct=6.0,   # strong BUY signal
        confidence_score=40,        # < 50 → REVIEW
        risk_score=20,
        data_quality_score=80,
    )
    assert decision == "REVIEW", (
        f"confidence_score=40 must produce REVIEW, got {decision}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 9 — Boundary: return exactly +3.0% → BUY (threshold is >=3%)
# ══════════════════════════════════════════════════════════════════════════════

def test_boundary_exactly_plus_3_is_buy():
    decision = _decide(
        predicted_return_pct=3.0,
        confidence_score=70,
        risk_score=30,
        data_quality_score=80,
    )
    assert decision == "BUY", (
        f"predicted_return=+3.0% at BUY threshold should be BUY, got {decision}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 10 — Boundary: return exactly -3.0% → SELL (before risk adjustment)
# ══════════════════════════════════════════════════════════════════════════════

def test_boundary_exactly_minus_3_is_sell_when_low_risk():
    decision = _decide(
        predicted_return_pct=-3.0,
        confidence_score=70,
        risk_score=30,    # low risk → no conversion
        data_quality_score=80,
    )
    assert decision == "SELL", (
        f"predicted_return=-3.0% at SELL threshold with low risk should be SELL, got {decision}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 11 — Zero data quality
# ══════════════════════════════════════════════════════════════════════════════

def test_zero_data_quality_is_review():
    decision = _decide(
        predicted_return_pct=10.0,
        confidence_score=95,
        risk_score=0,
        data_quality_score=0,    # definitely < 60
    )
    assert decision == "REVIEW"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 12 — Risk exactly at 80 boundary (80 triggers downgrade)
# ══════════════════════════════════════════════════════════════════════════════

def test_risk_exactly_80_triggers_buy_downgrade():
    """risk >= 80 must trigger BUY → HOLD downgrade. Test exact boundary."""
    decision = _decide(
        predicted_return_pct=5.0,
        confidence_score=70,
        risk_score=80,    # exactly at cutoff
        data_quality_score=80,
    )
    assert decision == "HOLD", (
        f"risk=80 (exactly at cutoff) + BUY must produce HOLD, got {decision}"
    )
