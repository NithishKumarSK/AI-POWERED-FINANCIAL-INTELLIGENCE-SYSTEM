"""
Tests for core/exposure_coach.py -- pure synthesis logic, synthetic
component dicts only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from exposure_coach import _parse_risk_budget_midpoint, build_exposure_posture


def test_parse_risk_budget_midpoint_single_value():
    assert _parse_risk_budget_midpoint("100%") == 100.0


def test_parse_risk_budget_midpoint_range():
    assert _parse_risk_budget_midpoint("60-75%") == 67.5


def test_parse_risk_budget_midpoint_malformed_or_none():
    assert _parse_risk_budget_midpoint(None) is None
    assert _parse_risk_budget_midpoint("") is None
    assert _parse_risk_budget_midpoint("unknown") is None


def test_all_inputs_missing_defaults_to_conservative_ceiling_and_low_confidence():
    result = build_exposure_posture()
    assert result["exposure_ceiling_pct"] == 50.0
    assert result["confidence"] == "LOW"
    assert set(result["inputs_missing"]) >= {"top_risk", "breadth", "uptrend", "ftd", "regime", "theme", "sector", "institutional"}
    assert result["inputs_provided"] == []


def test_theme_sector_institutional_always_missing():
    result = build_exposure_posture(
        breadth_data={"breadth_200dma_pct": 70, "uptrend_ratio": 0.8},
        regime_data={"composite_score": 10, "confidence": "high"},
        top_risk_data={"risk_budget": "100%", "composite_score": 10},
        ftd_data={"combined_state": "FTD_CONFIRMED"},
    )
    assert set(result["inputs_missing"]) == {"theme", "sector", "institutional"}
    assert "bias" not in result


def test_full_bullish_inputs_give_high_confidence_and_new_entry_allowed():
    result = build_exposure_posture(
        breadth_data={"breadth_200dma_pct": 75, "uptrend_ratio": 0.8},
        regime_data={"composite_score": 10, "confidence": "high"},
        top_risk_data={"risk_budget": "100%", "composite_score": 5},
        ftd_data={"combined_state": "FTD_CONFIRMED"},
    )
    assert result["recommendation"] == "NEW_ENTRY_ALLOWED"
    assert result["confidence"] == "HIGH"
    assert result["participation"] == "BROAD"
    assert result["exposure_ceiling_pct"] == 100.0


def test_narrow_participation_applies_haircut():
    result = build_exposure_posture(
        breadth_data={"breadth_200dma_pct": 30, "uptrend_ratio": 0.3},
        top_risk_data={"risk_budget": "100%", "composite_score": 5},
    )
    assert result["participation"] == "NARROW"
    assert result["exposure_ceiling_pct"] == 90.0


def test_corrective_ftd_state_forces_defensive_floor():
    result = build_exposure_posture(
        top_risk_data={"risk_budget": "100%", "composite_score": 5},
        ftd_data={"combined_state": "CORRECTION"},
    )
    assert result["exposure_ceiling_pct"] <= 50.0
    assert result["recommendation"] in ("REDUCE_ONLY", "CASH_PRIORITY")


def test_very_low_regime_confidence_treated_as_missing():
    result = build_exposure_posture(
        regime_data={"composite_score": 10, "confidence": "very_low"},
    )
    assert "regime" in result["inputs_missing"]
    assert result["component_scores"]["regime_score"] is None


def test_high_top_risk_cash_priority():
    result = build_exposure_posture(
        top_risk_data={"risk_budget": "20-35%", "composite_score": 90},
    )
    assert result["recommendation"] == "CASH_PRIORITY"
