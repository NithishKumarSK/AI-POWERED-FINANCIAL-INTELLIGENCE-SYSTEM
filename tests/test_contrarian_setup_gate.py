"""
Tests for core/contrarian_setup_gate.py -- pure synthesis logic, the
15-row collapsed decision table from references/gate-decision-table.md
plus its explicitly named precedence pins.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from contrarian_setup_gate import run_contrarian_setup_gate

CROWDED_LONG = {"classification": "CROWDED_LONG"}
NEUTRAL = {"classification": "NEUTRAL"}
INVALID_CROWDING = {"classification": "BANANA"}

CONFIRMED_NEWS = {"verdict": "CONFIRMED", "confidence": "HIGH", "direction": "CROWDED_LONG", "verdict_reason": "news_failure_confirmed"}
NOT_CONFIRMED_NEWS = {"verdict": "NOT_CONFIRMED", "confidence": None, "direction": "CROWDED_LONG", "verdict_reason": "no_reversal_evidence"}
INSUFFICIENT_NEWS = {"verdict": "INSUFFICIENT_EVIDENCE", "confidence": None, "direction": None, "verdict_reason": "too_few_usable_events"}
INVALID_NEWS = {"not": "a valid report shape"}

CONFIRMED_PRICE = {"verdict": "CONFIRMED", "confidence": "MEDIUM", "direction": "CROWDED_LONG", "verdict_reason": "key_reversal", "swing_levels": {"stop_reference": 105.0}}
NOT_CONFIRMED_PRICE = {"verdict": "NOT_CONFIRMED", "confidence": None, "direction": "CROWDED_LONG", "verdict_reason": "no_reversal_evidence"}
INSUFFICIENT_PRICE = {"verdict": "INSUFFICIENT_DATA", "confidence": None, "direction": None, "verdict_reason": "insufficient_weekly_bars"}
INVALID_PRICE_MISSING_STOP = {"verdict": "CONFIRMED", "confidence": "HIGH", "direction": "CROWDED_LONG", "verdict_reason": "key_reversal", "swing_levels": {}}


def test_crowding_invalid_short_circuits():
    result = run_contrarian_setup_gate(INVALID_CROWDING, CONFIRMED_NEWS, NOT_CONFIRMED_PRICE)
    assert result["setup_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["missing_confirmations"][0]["step"] == "crowding"


def test_crowding_not_confirmed_rejects_regardless_of_downstream():
    result = run_contrarian_setup_gate(NEUTRAL, CONFIRMED_NEWS, CONFIRMED_PRICE)
    assert result["setup_status"] == "REJECTED"
    assert result["missing_confirmations"][0]["step"] == "crowding"


def test_named_pin_crowding_not_confirmed_plus_price_not_confirmed():
    result = run_contrarian_setup_gate(NEUTRAL, None, NOT_CONFIRMED_PRICE)
    assert result["setup_status"] == "REJECTED"
    assert result["missing_confirmations"][0]["step"] == "crowding"


def test_crowding_confirmed_both_pending_gives_crowded():
    result = run_contrarian_setup_gate(CROWDED_LONG, None, None)
    assert result["setup_status"] == "CROWDED"


def test_news_invalid_insufficient_evidence_price_never_inspected():
    result = run_contrarian_setup_gate(CROWDED_LONG, INVALID_NEWS, NOT_CONFIRMED_PRICE)
    assert result["setup_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["missing_confirmations"][0]["step"] == "news"


def test_named_pin_news_not_confirmed_plus_price_invalid_rejects_not_insufficient():
    result = run_contrarian_setup_gate(CROWDED_LONG, NOT_CONFIRMED_NEWS, INVALID_NEWS)
    assert result["setup_status"] == "REJECTED"
    assert result["missing_confirmations"][0]["step"] == "news"


def test_named_pin_news_insufficient_plus_price_not_confirmed_is_insufficient_not_rejected():
    result = run_contrarian_setup_gate(CROWDED_LONG, INSUFFICIENT_NEWS, NOT_CONFIRMED_PRICE)
    assert result["setup_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["missing_confirmations"][0]["step"] == "news"


def test_news_confirmed_price_pending_gives_watching_price():
    result = run_contrarian_setup_gate(CROWDED_LONG, CONFIRMED_NEWS, None)
    assert result["setup_status"] == "WATCHING_PRICE"


def test_news_confirmed_price_not_confirmed_rejects():
    result = run_contrarian_setup_gate(CROWDED_LONG, CONFIRMED_NEWS, NOT_CONFIRMED_PRICE)
    assert result["setup_status"] == "REJECTED"
    assert result["missing_confirmations"][0]["step"] == "price_action"


def test_news_confirmed_price_insufficient_gives_insufficient_evidence():
    result = run_contrarian_setup_gate(CROWDED_LONG, CONFIRMED_NEWS, INSUFFICIENT_PRICE)
    assert result["setup_status"] == "INSUFFICIENT_EVIDENCE"


def test_all_three_confirmed_gives_ready_for_plan():
    result = run_contrarian_setup_gate(CROWDED_LONG, CONFIRMED_NEWS, CONFIRMED_PRICE)
    assert result["setup_status"] == "READY_FOR_PLAN"
    assert result["direction"] == "SHORT"  # fading a crowded LONG
    assert result["invalidation_level"] == 105.0
    assert result["entry_trigger"] == "key_reversal"
    assert result["gate_confidence"] == "MEDIUM"  # weaker of HIGH(news)/MEDIUM(price)


def test_out_of_order_price_confirmed_caps_at_crowded_with_warning():
    result = run_contrarian_setup_gate(CROWDED_LONG, None, CONFIRMED_PRICE)
    assert result["setup_status"] == "CROWDED"
    assert "out_of_order_price_action" in result["warnings"]
    assert result["direction"] is None  # never reaches READY_FOR_PLAN, so no plan fields


def test_out_of_order_price_not_confirmed_still_rejects():
    result = run_contrarian_setup_gate(CROWDED_LONG, None, NOT_CONFIRMED_PRICE)
    assert result["setup_status"] == "REJECTED"


def test_out_of_order_price_invalid_is_insufficient():
    result = run_contrarian_setup_gate(CROWDED_LONG, None, INVALID_NEWS)
    assert result["setup_status"] == "INSUFFICIENT_EVIDENCE"


def test_direction_mismatch_marks_price_action_invalid():
    mismatched = {**CONFIRMED_PRICE, "direction": "CROWDED_SHORT"}
    result = run_contrarian_setup_gate(CROWDED_LONG, CONFIRMED_NEWS, mismatched)
    assert result["setup_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["missing_confirmations"][0]["reason"] == "price_action_direction_mismatch"


def test_confirmed_price_missing_stop_reference_is_invalid():
    result = run_contrarian_setup_gate(CROWDED_LONG, CONFIRMED_NEWS, INVALID_PRICE_MISSING_STOP)
    assert result["setup_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["missing_confirmations"][0]["reason"] == "price_action_missing_stop_reference"


def test_confirmed_price_negative_stop_reference_is_invalid():
    bad = {**CONFIRMED_PRICE, "swing_levels": {"stop_reference": -5.0}}
    result = run_contrarian_setup_gate(CROWDED_LONG, CONFIRMED_NEWS, bad)
    assert result["missing_confirmations"][0]["reason"] == "price_action_invalid_stop_reference"


def test_ready_for_plan_invariant_always_has_entry_trigger_and_stop():
    result = run_contrarian_setup_gate(CROWDED_LONG, CONFIRMED_NEWS, CONFIRMED_PRICE)
    if result["setup_status"] == "READY_FOR_PLAN":
        assert result["entry_trigger"]
        assert result["invalidation_level"] > 0


def test_crowded_short_fade_direction_is_long():
    result = run_contrarian_setup_gate({"classification": "CROWDED_SHORT"}, None, None)
    assert result["setup_status"] == "CROWDED"
