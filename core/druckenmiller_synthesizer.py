"""
Druckenmiller Strategy Synthesizer, adapted from claude-trading-skills'
`stanley-druckenmiller-investment` skill (vendor/claude-trading-skills/
skills/stanley-druckenmiller-investment/SKILL.md). MIT License,
Copyright (c) 2026 TraderMonty.

A meta-skill: combines this project's already-live market_breadth_service,
macro_regime_service, market_top_detector_service, and ftd_status_service
(the source skill's 5 "required" inputs, minus uptrend which this
project's market_breadth_service already merges in -- see
vendor/README.md) into a single 0-100 conviction score, one of 4
Druckenmiller pattern classifications, and a conviction-zone exposure
recommendation.

SCOPE REDUCTION, disclosed: the source skill's 7-component weighting
also includes Theme Quality (12%, from theme-detector -- FINVIZ-blocked,
see vendor/README.md) and Setup Availability (10%, from a market-WIDE
VCP/CANSLIM scan -- this project's vcp_screener.py/canslim_screener.py
are per-symbol tools with no cross-universe discovery step, since that
needs FMP's premium company-screener endpoint). Both components are
dropped entirely, never faked, and the remaining 5 components' weights
(which sum to 78/100 in the source skill) are rescaled to sum to 100,
exactly like value_dividend_screener.py's "raw budget rescaled to 100"
precedent. `theme` and `setup_availability` always appear in
`inputs_missing`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Source skill's own weights (out of 100) for the 5 components this
# project can actually compute, before rescaling.
_RAW_WEIGHTS = {
    "market_structure": 18,
    "distribution_risk": 18,
    "bottom_confirmation": 12,
    "macro_alignment": 18,
    "signal_convergence": 12,
}
_RAW_WEIGHT_SUM = sum(_RAW_WEIGHTS.values())  # 78
WEIGHTS = {k: v / _RAW_WEIGHT_SUM * 100 for k, v in _RAW_WEIGHTS.items()}

_CORRECTIVE_FTD_STATES = {"CORRECTION", "RALLY_FAILED", "FTD_INVALIDATED", "RALLY_ATTEMPT"}

CONVICTION_ZONES = [
    (80, 100, "Maximum Conviction", (90, 100), "Fat pitch - swing hard"),
    (60, 80, "High Conviction", (70, 90), "Standard risk management"),
    (40, 60, "Moderate Conviction", (50, 70), "Reduce position sizes"),
    (20, 40, "Low Conviction", (20, 50), "Preserve capital, minimal risk"),
    (0, 20, "Capital Preservation", (0, 20), "Maximum defense"),
]


def score_market_structure(breadth_pct: Optional[float], uptrend_ratio: Optional[float]) -> Optional[float]:
    parts = [p for p in (breadth_pct, uptrend_ratio * 100 if uptrend_ratio is not None else None) if p is not None]
    if not parts:
        return None
    return max(0.0, min(100.0, sum(parts) / len(parts)))


def score_distribution_risk(top_risk_composite: Optional[float]) -> Optional[float]:
    """Inverted, per the source skill's own component table."""
    if top_risk_composite is None:
        return None
    return max(0.0, min(100.0, 100.0 - top_risk_composite))


def score_bottom_confirmation(ftd_combined_state: Optional[str]) -> Optional[float]:
    if not ftd_combined_state:
        return None
    if ftd_combined_state == "FTD_CONFIRMED":
        return 100.0
    if ftd_combined_state in _CORRECTIVE_FTD_STATES:
        return 0.0
    return 50.0


def score_macro_alignment(regime_composite: Optional[float]) -> Optional[float]:
    """Inverted: the regime composite measures transition INSTABILITY (higher
    = more unsettled), so a low, stable composite is macro-favorable."""
    if regime_composite is None:
        return None
    return max(0.0, min(100.0, 100.0 - regime_composite))


def score_signal_convergence(component_scores: List[float]) -> Optional[float]:
    """Fraction of the available required components agreeing on direction
    (all >=50 i.e. bullish, or all <50 i.e. bearish) -- a simple, honestly-
    documented convergence measure, not a port of unseen internal logic."""
    if not component_scores:
        return None
    bullish = sum(1 for s in component_scores if s >= 50)
    bearish = len(component_scores) - bullish
    agreeing = max(bullish, bearish)
    return (agreeing / len(component_scores)) * 100.0


def classify_pattern(
    regime_zone: Optional[str],
    top_risk_composite: Optional[float],
    ftd_combined_state: Optional[str],
    breadth_pct: Optional[float],
) -> str:
    """One of the source skill's 4 Druckenmiller patterns. Falls back to
    'Wait & Observe' (the documented default) whenever a required signal
    for a more specific pattern is missing."""
    is_transitioning = bool(regime_zone and "Transition" in regime_zone)
    high_top_risk = top_risk_composite is not None and top_risk_composite >= 60
    bearish_breadth = breadth_pct is not None and breadth_pct < 50

    if ftd_combined_state == "FTD_CONFIRMED" and high_top_risk and bearish_breadth:
        return "Extreme Sentiment Contrarian"
    if high_top_risk and is_transitioning:
        return "Unsustainable Distortion"
    if is_transitioning and top_risk_composite is not None and top_risk_composite >= 60:
        return "Policy Pivot Anticipation"
    return "Wait & Observe"


def conviction_zone_for_score(score: float) -> Dict[str, Any]:
    for low, high, label, exposure_range, guidance in CONVICTION_ZONES:
        if low <= score < high or (high == 100 and score == 100):
            return {"zone": label, "exposure_range_pct": list(exposure_range), "guidance": guidance}
    return {"zone": "Capital Preservation", "exposure_range_pct": [0, 20], "guidance": "Maximum defense"}


def build_druckenmiller_synthesis(
    breadth_data: Optional[Dict[str, Any]] = None,
    regime_data: Optional[Dict[str, Any]] = None,
    top_risk_data: Optional[Dict[str, Any]] = None,
    ftd_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    inputs_provided: List[str] = []
    inputs_missing: List[str] = []

    breadth_pct = (breadth_data or {}).get("breadth_200dma_pct")
    uptrend_ratio = (breadth_data or {}).get("uptrend_ratio")
    if breadth_pct is not None or uptrend_ratio is not None:
        inputs_provided.append("market_structure")
    else:
        inputs_missing.append("market_structure")

    top_risk_composite = (top_risk_data or {}).get("composite_score")
    if top_risk_composite is not None:
        inputs_provided.append("distribution_risk")
    else:
        inputs_missing.append("distribution_risk")

    ftd_state = (ftd_data or {}).get("combined_state")
    if ftd_state:
        inputs_provided.append("bottom_confirmation")
    else:
        inputs_missing.append("bottom_confirmation")

    regime_composite = (regime_data or {}).get("composite_score")
    regime_confidence = (regime_data or {}).get("confidence")
    regime_usable = regime_composite is not None and regime_confidence != "very_low"
    if regime_usable:
        inputs_provided.append("macro_alignment")
    else:
        inputs_missing.append("macro_alignment")

    inputs_missing += ["theme_quality", "setup_availability"]

    component_scores = {
        "market_structure": score_market_structure(breadth_pct, uptrend_ratio),
        "distribution_risk": score_distribution_risk(top_risk_composite),
        "bottom_confirmation": score_bottom_confirmation(ftd_state),
        "macro_alignment": score_macro_alignment(regime_composite) if regime_usable else None,
        "theme_quality": None,
        "setup_availability": None,
    }

    available = {k: v for k, v in component_scores.items() if v is not None and k in WEIGHTS}
    convergence = score_signal_convergence(list(available.values()))
    component_scores["signal_convergence"] = convergence
    if convergence is not None:
        available["signal_convergence"] = convergence
        inputs_provided.append("signal_convergence")
    else:
        inputs_missing.append("signal_convergence")

    weight_sum = sum(WEIGHTS[k] for k in available)
    if weight_sum > 0:
        composite = sum(available[k] * WEIGHTS[k] for k in available) / weight_sum
    else:
        composite = 0.0  # Safety First: no usable input at all -> capital-preservation default.

    zone_info = conviction_zone_for_score(composite)
    pattern = classify_pattern(
        (regime_data or {}).get("zone"), top_risk_composite, ftd_state, breadth_pct,
    )

    return {
        "schema_version": "1.0",
        "conviction_score": round(composite, 1),
        "zone": zone_info["zone"],
        "exposure_range_pct": zone_info["exposure_range_pct"],
        "guidance": zone_info["guidance"],
        "pattern": pattern,
        "component_scores": component_scores,
        "component_weights_used_pct": {k: round(WEIGHTS[k], 1) for k in WEIGHTS},
        "inputs_provided": inputs_provided,
        "inputs_missing": sorted(set(inputs_missing)),
    }
