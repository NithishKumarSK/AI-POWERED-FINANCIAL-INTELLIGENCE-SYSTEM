"""
Market Top Detector - Composite Scoring Engine. Ported verbatim from
scorer.py.

Combines 6 component scores into a weighted composite (0-100).
1. Distribution Day Count:    25%   4. Market Breadth Divergence: 15%
2. Leading Stock Health:      20%   5. Index Technical Condition: 15%
3. Defensive Sector Rotation: 15%   6. Sentiment & Speculation:   10%

Risk Zone Mapping:
  0-20:  Green (Normal)         - Risk Budget: 100%
  21-40: Yellow (Early Warning) - Risk Budget: 80-90%
  41-60: Orange (Elevated Risk) - Risk Budget: 60-75%
  61-80: Red (High Risk)        - Risk Budget: 40-55%
  81-100: Critical (Very High)  - Risk Budget: 20-35%
"""
from __future__ import annotations

from typing import Optional

COMPONENT_WEIGHTS = {
    "distribution_days": 0.25,
    "leading_stocks": 0.20,
    "defensive_rotation": 0.15,
    "breadth_divergence": 0.15,
    "index_technical": 0.15,
    "sentiment": 0.10,
}

COMPONENT_LABELS = {
    "distribution_days": "Distribution Day Count",
    "leading_stocks": "Leading Stock Health",
    "defensive_rotation": "Defensive Sector Rotation",
    "breadth_divergence": "Market Breadth Divergence",
    "index_technical": "Index Technical Condition",
    "sentiment": "Sentiment & Speculation",
}

CORRELATION_PAIRS = [("distribution_days", "defensive_rotation")]
CORRELATION_THRESHOLD = 80
CORRELATION_DISCOUNT = 0.8


def _apply_correlation_adjustment(component_scores: dict) -> dict:
    adjusted = dict(component_scores)
    adjustments = []
    for comp_a, comp_b in CORRELATION_PAIRS:
        score_a = component_scores.get(comp_a, 0)
        score_b = component_scores.get(comp_b, 0)
        if score_a >= CORRELATION_THRESHOLD and score_b >= CORRELATION_THRESHOLD:
            weight_a = COMPONENT_WEIGHTS.get(comp_a, 0)
            weight_b = COMPONENT_WEIGHTS.get(comp_b, 0)
            if weight_a >= weight_b:
                discounted, original = comp_b, score_b
            else:
                discounted, original = comp_a, score_a
            adjusted[discounted] = original * CORRELATION_DISCOUNT
            adjustments.append({
                "pair": [comp_a, comp_b], "discounted_component": discounted,
                "original_score": original, "adjusted_score": adjusted[discounted],
                "discount_factor": CORRELATION_DISCOUNT,
            })
    return {"adjusted_scores": adjusted, "adjustments": adjustments}


def calculate_composite_score(component_scores: dict, data_availability: Optional[dict] = None) -> dict:
    if data_availability is None:
        data_availability = {}

    corr_result = _apply_correlation_adjustment(component_scores)
    adjusted_scores = corr_result["adjusted_scores"]
    correlation_adjustment = corr_result["adjustments"]

    available_weight = sum(w for k, w in COMPONENT_WEIGHTS.items() if data_availability.get(k, True))
    effective_weights = {
        k: (w / available_weight if available_weight > 0 else w)
        for k, w in COMPONENT_WEIGHTS.items() if data_availability.get(k, True)
    }

    composite = round(sum(adjusted_scores.get(k, 0) * ew for k, ew in effective_weights.items()), 1)

    available_scores = {k: v for k, v in component_scores.items() if k in effective_weights}
    if available_scores:
        strongest_warning = max(available_scores, key=available_scores.get)
        weakest_warning = min(available_scores, key=available_scores.get)
    else:
        strongest_warning = weakest_warning = None

    zone_info = _interpret_zone(composite)

    available_count = sum(1 for k in COMPONENT_WEIGHTS if data_availability.get(k, True))
    total_components = len(COMPONENT_WEIGHTS)
    missing_components = [COMPONENT_LABELS[k] for k in COMPONENT_WEIGHTS if not data_availability.get(k, True)]

    if available_count == total_components:
        quality_label = f"Complete ({available_count}/{total_components} components)"
    elif available_count >= total_components - 2:
        quality_label = f"Partial ({available_count}/{total_components} components) - interpret with caution"
    else:
        quality_label = f"Limited ({available_count}/{total_components} components) - low confidence"

    data_quality = {
        "available_count": available_count, "total_components": total_components,
        "label": quality_label, "missing_components": missing_components,
    }

    if strongest_warning is not None:
        strongest_dict = {"component": strongest_warning, "label": COMPONENT_LABELS.get(strongest_warning, strongest_warning), "score": available_scores.get(strongest_warning, 0)}
    else:
        strongest_dict = {"component": None, "label": "N/A", "score": 0}

    if weakest_warning is not None:
        weakest_dict = {"component": weakest_warning, "label": COMPONENT_LABELS.get(weakest_warning, weakest_warning), "score": available_scores.get(weakest_warning, 0)}
    else:
        weakest_dict = {"component": None, "label": "N/A", "score": 0}

    return {
        "score_kind": "heuristic_risk_score", "score_version": "market-top-risk-v1",
        "calibrated_probability": False,
        "interpretation": "Risk score, not an estimated event probability. Risk budgets are policy heuristics.",
        "composite_score": composite, "zone": zone_info["zone"], "zone_color": zone_info["color"],
        "risk_budget": zone_info["risk_budget"], "guidance": zone_info["guidance"], "actions": zone_info["actions"],
        "strongest_warning": strongest_dict, "weakest_warning": weakest_dict, "data_quality": data_quality,
        "correlation_adjustment": correlation_adjustment,
        "component_scores": {
            k: {
                "score": component_scores.get(k, 0),
                "adjusted_score": adjusted_scores.get(k, component_scores.get(k, 0)),
                "weight": w,
                "weighted_contribution": round(adjusted_scores.get(k, 0) * effective_weights[k], 1) if k in effective_weights else 0.0,
                "label": COMPONENT_LABELS[k],
            }
            for k, w in COMPONENT_WEIGHTS.items()
        },
    }


def _interpret_zone(composite: float) -> dict:
    if composite <= 20:
        return {"zone": "Green (Normal)", "color": "green", "risk_budget": "100%",
                "guidance": "Normal market conditions. Maintain standard position management.",
                "actions": ["Normal position sizing", "Standard stop-loss levels", "New position entries allowed"]}
    elif composite <= 40:
        return {"zone": "Yellow (Early Warning)", "color": "yellow", "risk_budget": "80-90%",
                "guidance": "Early warning signs detected. Tighten stops and reduce new entries.",
                "actions": ["Tighten stop-losses by 10-20%", "Reduce new position sizes by 25-50%",
                             "Review weakest positions for exits", "Monitor distribution days closely"]}
    elif composite <= 60:
        return {"zone": "Orange (Elevated Risk)", "color": "orange", "risk_budget": "60-75%",
                "guidance": "Elevated risk of correction. Begin profit-taking on weaker positions.",
                "actions": ["Take profits on weakest 25-30% of positions", "No new momentum entries",
                             "Only quality stocks near support", "Raise cash allocation",
                             "Watch for Follow-Through Day if market pulls back"]}
    elif composite <= 80:
        return {"zone": "Red (High Risk)", "color": "red", "risk_budget": "40-55%",
                "guidance": "High heuristic market top risk. Aggressive profit-taking recommended.",
                "actions": ["Aggressive profit-taking (sell 40-50% of positions)", "Maximum cash allocation",
                             "Only hold strongest leaders", "Consider hedges (put options, inverse ETFs)",
                             "Prepare short watchlist"]}
    return {"zone": "Critical (Very High Risk)", "color": "critical", "risk_budget": "20-35%",
            "guidance": "Very high heuristic market top risk. Maximum defensive posture.",
            "actions": ["Sell most positions (keep only 20-35% invested)", "Full hedge implementation",
                         "Short positions on weakest leaders", "Preserve capital as primary objective"]}
