"""
Tests for core/signal_postmortem.py -- pure classification/aggregation
logic, synthetic data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from signal_postmortem import build_signal_postmortem, classify_outcome_category, decision_to_direction


def test_decision_to_direction_mapping():
    assert decision_to_direction("BUY") == "LONG"
    assert decision_to_direction("SELL") == "SHORT"
    assert decision_to_direction("HOLD") is None
    assert decision_to_direction(None) is None


def test_classify_true_positive():
    assert classify_outcome_category("LONG", 5.0) == "TRUE_POSITIVE"
    assert classify_outcome_category("SHORT", -5.0) == "TRUE_POSITIVE"


def test_classify_false_positive_no_regime_change():
    assert classify_outcome_category("LONG", -5.0, regime_changed=False) == "FALSE_POSITIVE"


def test_classify_regime_mismatch_when_regime_changed():
    assert classify_outcome_category("LONG", -5.0, regime_changed=True) == "REGIME_MISMATCH"


def test_classify_unknown_when_no_realized_return():
    assert classify_outcome_category("LONG", None) == "UNKNOWN"


def test_classify_flat_return_is_false_positive():
    assert classify_outcome_category("LONG", 0.0) == "FALSE_POSITIVE"


def test_build_signal_postmortem_skips_hold_decisions():
    entries = [
        {"symbol": "AAPL", "decision": "HOLD", "realized_return_pct": 1.0},
        {"symbol": "MSFT", "decision": "BUY", "realized_return_pct": 5.0},
    ]
    result = build_signal_postmortem(entries)
    assert result["overall"]["total"] == 1


def test_build_signal_postmortem_overall_rates():
    entries = [
        {"symbol": "AAPL", "decision": "BUY", "realized_return_pct": 5.0},
        {"symbol": "MSFT", "decision": "BUY", "realized_return_pct": -5.0, "regime_changed": False},
        {"symbol": "TSLA", "decision": "SELL", "realized_return_pct": 5.0, "regime_changed": True},
    ]
    result = build_signal_postmortem(entries)
    overall = result["overall"]
    assert overall["TRUE_POSITIVE"] == 1
    assert overall["FALSE_POSITIVE"] == 1
    assert overall["REGIME_MISMATCH"] == 1
    assert abs(overall["true_positive_rate"] - (1 / 3)) < 1e-9
    assert overall["sample_size_sufficient"] is False


def test_build_signal_postmortem_sample_size_sufficient_at_threshold():
    entries = [{"symbol": "AAPL", "decision": "BUY", "realized_return_pct": 1.0} for _ in range(20)]
    result = build_signal_postmortem(entries)
    assert result["overall"]["sample_size_sufficient"] is True


def test_build_signal_postmortem_by_symbol_breakdown():
    entries = [
        {"symbol": "AAPL", "decision": "BUY", "realized_return_pct": 5.0},
        {"symbol": "AAPL", "decision": "BUY", "realized_return_pct": -5.0},
    ]
    result = build_signal_postmortem(entries)
    assert result["by_symbol"]["AAPL"]["total"] == 2
    assert result["by_symbol"]["AAPL"]["TRUE_POSITIVE"] == 1
    assert result["by_symbol"]["AAPL"]["FALSE_POSITIVE"] == 1
