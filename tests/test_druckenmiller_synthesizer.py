"""
Tests for core/druckenmiller_synthesizer.py -- pure synthesis logic,
synthetic component dicts only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from druckenmiller_synthesizer import (
    WEIGHTS,
    build_druckenmiller_synthesis,
    classify_pattern,
    conviction_zone_for_score,
    score_bottom_confirmation,
    score_distribution_risk,
    score_macro_alignment,
    score_market_structure,
    score_signal_convergence,
)


def test_weights_rescaled_to_sum_100():
    assert abs(sum(WEIGHTS.values()) - 100.0) < 1e-9


def test_score_market_structure_averages_breadth_and_uptrend():
    assert score_market_structure(70, 0.8) == 75.0


def test_score_market_structure_handles_missing_pieces():
    assert score_market_structure(70, None) == 70.0
    assert score_market_structure(None, None) is None


def test_score_distribution_risk_inverted():
    assert score_distribution_risk(30) == 70.0
    assert score_distribution_risk(None) is None


def test_score_bottom_confirmation_states():
    assert score_bottom_confirmation("FTD_CONFIRMED") == 100.0
    assert score_bottom_confirmation("CORRECTION") == 0.0
    assert score_bottom_confirmation("NO_SIGNAL") == 50.0
    assert score_bottom_confirmation(None) is None


def test_score_macro_alignment_inverted():
    assert score_macro_alignment(20) == 80.0


def test_score_signal_convergence_full_agreement():
    assert score_signal_convergence([80, 90, 70, 85]) == 100.0


def test_score_signal_convergence_mixed():
    assert score_signal_convergence([80, 20, 70, 85]) == 75.0


def test_score_signal_convergence_empty():
    assert score_signal_convergence([]) is None


def test_classify_pattern_wait_and_observe_default():
    assert classify_pattern(None, None, None, None) == "Wait & Observe"


def test_classify_pattern_extreme_sentiment_contrarian():
    pattern = classify_pattern("Stable (No Transition)", 70, "FTD_CONFIRMED", 30)
    assert pattern == "Extreme Sentiment Contrarian"


def test_classify_pattern_unsustainable_distortion():
    pattern = classify_pattern("Active Transition (Repositioning)", 70, None, None)
    assert pattern == "Unsustainable Distortion"


def test_conviction_zone_boundaries():
    assert conviction_zone_for_score(100)["zone"] == "Maximum Conviction"
    assert conviction_zone_for_score(85)["zone"] == "Maximum Conviction"
    assert conviction_zone_for_score(60)["zone"] == "High Conviction"
    assert conviction_zone_for_score(20)["zone"] == "Low Conviction"
    assert conviction_zone_for_score(0)["zone"] == "Capital Preservation"


def test_build_synthesis_all_missing_defaults_safely():
    result = build_druckenmiller_synthesis()
    assert result["conviction_score"] == 0.0
    assert result["zone"] == "Capital Preservation"
    assert "theme_quality" in result["inputs_missing"]
    assert "setup_availability" in result["inputs_missing"]


def test_build_synthesis_full_bullish_inputs():
    result = build_druckenmiller_synthesis(
        breadth_data={"breadth_200dma_pct": 75, "uptrend_ratio": 0.8},
        regime_data={"composite_score": 10, "confidence": "high", "zone": "Stable (No Transition)"},
        top_risk_data={"composite_score": 5},
        ftd_data={"combined_state": "FTD_CONFIRMED"},
    )
    assert result["conviction_score"] > 80
    assert result["zone"] == "Maximum Conviction"
    assert result["pattern"] == "Wait & Observe"


def test_build_synthesis_very_low_regime_confidence_excluded():
    result = build_druckenmiller_synthesis(
        regime_data={"composite_score": 10, "confidence": "very_low"},
    )
    assert "macro_alignment" in result["inputs_missing"]
    assert result["component_scores"]["macro_alignment"] is None
