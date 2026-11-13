"""
Composite scoring & regime classification -- combines the 6 component
transition signals into a weighted composite score and one of 5 regime
classifications. Ported from claude-trading-skills' macro-regime-detector
(vendor/claude-trading-skills/skills/macro-regime-detector/scripts/scorer.py,
MIT License, Copyright (c) 2026 TraderMonty). See core/macro_regime/__init__.py.
"""
from __future__ import annotations

from typing import Optional

COMPONENT_WEIGHTS = {
    "concentration": 0.25, "yield_curve": 0.20, "credit_conditions": 0.15,
    "size_factor": 0.15, "equity_bond": 0.15, "sector_rotation": 0.10,
}

COMPONENT_LABELS = {
    "concentration": "Market Concentration (RSP/SPY)", "yield_curve": "Yield Curve (10Y-2Y)",
    "credit_conditions": "Credit Conditions (HYG/LQD)", "size_factor": "Size Factor (IWM/SPY)",
    "equity_bond": "Equity-Bond (SPY/TLT)", "sector_rotation": "Sector Rotation (XLY/XLP)",
}


def calculate_composite_score(component_scores: dict, data_availability: Optional[dict] = None) -> dict:
    data_availability = data_availability or {}
    composite = round(sum(component_scores.get(k, 0) * w for k, w in COMPONENT_WEIGHTS.items()), 1)
    valid_scores = {k: v for k, v in component_scores.items() if k in COMPONENT_WEIGHTS}
    strongest_signal = max(valid_scores, key=valid_scores.get) if valid_scores else "N/A"
    weakest_signal = min(valid_scores, key=valid_scores.get) if valid_scores else "N/A"
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

    signaling_count = sum(1 for v in valid_scores.values() if v >= 40)

    return {
        "composite_score": composite, "zone": zone_info["zone"], "zone_color": zone_info["color"],
        "guidance": zone_info["guidance"], "actions": zone_info["actions"],
        "signaling_components": signaling_count,
        "strongest_signal": {"component": strongest_signal, "label": COMPONENT_LABELS.get(strongest_signal, strongest_signal), "score": valid_scores.get(strongest_signal, 0)},
        "weakest_signal": {"component": weakest_signal, "label": COMPONENT_LABELS.get(weakest_signal, weakest_signal), "score": valid_scores.get(weakest_signal, 0)},
        "data_quality": {"available_count": available_count, "total_components": total_components, "label": quality_label, "missing_components": missing_components},
        "component_scores": {
            k: {"score": component_scores.get(k, 0), "weight": w, "weighted_contribution": round(component_scores.get(k, 0) * w, 1), "label": COMPONENT_LABELS[k]}
            for k, w in COMPONENT_WEIGHTS.items()
        },
    }


REGIME_DESCRIPTIONS = {
    "concentration": {"label": "Concentration",
        "description": "Market leadership concentrated in mega-cap stocks. RSP/SPY declining, small-caps underperforming. Credit conditions stable.",
        "portfolio_posture": "Focus on mega-cap tech/growth leaders. Underweight small-caps and value."},
    "broadening": {"label": "Broadening",
        "description": "Market participation expanding. RSP/SPY rising, small-caps catching up. Credit easing or stable.",
        "portfolio_posture": "Add small-cap/mid-cap exposure. Equal-weight strategies. Value and cyclical rotation."},
    "contraction": {"label": "Contraction",
        "description": "Credit tightening, defensive rotation, equity-bond shift to risk-off. Classic late-cycle deterioration.",
        "portfolio_posture": "Raise cash. Duration management: short-duration Treasuries as base; add TIPS if inflation signals present; extend duration only when stock-bond correlation turns negative. Defensive sectors: prioritize Staples and Healthcare."},
    "inflationary": {"label": "Inflationary",
        "description": "Positive stock-bond correlation regime. Both equities and bonds under pressure. Traditional hedging breaks down.",
        "portfolio_posture": "Real assets, commodities, energy. Short-duration bonds. TIPS. Reduce long-duration exposure."},
    "transitional": {"label": "Transitional",
        "description": "Multiple components signaling change but no clear regime pattern. Market in flux between regimes.",
        "portfolio_posture": "Increase diversification. Gradual repositioning. Avoid concentrated bets. Monitor weekly for regime clarity."},
}


def _score_concentration_regime(conc_dir: str, size_dir: str, credit_dir: str) -> int:
    score = 0
    if conc_dir == "concentrating":
        score += 2
    if size_dir == "large_cap_leading":
        score += 2
    if credit_dir in ("stable", "easing"):
        score += 1
    return score


def _score_broadening_regime(conc_dir: str, size_dir: str, credit_dir: str, sector_dir: str, yc_dir: str = "unknown") -> int:
    score = 0
    if conc_dir == "broadening":
        score += 2
    if size_dir == "small_cap_leading":
        score += 2
    if credit_dir in ("stable", "easing"):
        score += 1
    if sector_dir == "risk_on":
        score += 1
    if yc_dir == "steepening":
        score += 1
    return score


def _score_contraction_regime(credit_dir: str, sector_dir: str, eb_dir: str, size_dir: str = "unknown", yc_dir: str = "unknown") -> int:
    score = 0
    if credit_dir == "tightening":
        score += 2
    if sector_dir == "risk_off":
        score += 2
    if eb_dir == "risk_off":
        score += 1
    if yc_dir == "flattening":
        score += 1
    if size_dir == "small_cap_leading":
        score -= 1
    return max(0, score)


def _score_inflationary_regime(corr_regime: str, eb_dir: str) -> int:
    score = 0
    if corr_regime == "positive":
        score += 3
    elif corr_regime == "near_zero":
        score += 1
    if eb_dir == "risk_off":
        score += 1
    return score


def _calculate_transition_probability(signaling: int, all_scores: list, regime_scores: dict, current_regime: str, sorted_regimes: Optional[list] = None) -> dict:
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
    if signaling >= 4 and avg_score >= 50:
        prob_level, prob_pct = "high", "70-90%"
    elif signaling >= 3 and avg_score >= 40:
        prob_level, prob_pct = "moderate", "40-60%"
    elif signaling >= 2 and avg_score >= 30:
        prob_level, prob_pct = "low", "20-40%"
    else:
        prob_level, prob_pct = "minimal", "<20%"

    if sorted_regimes is None:
        scored = {k: v for k, v in regime_scores.items() if k != "transitional"}
        sorted_regimes = sorted(scored.items(), key=lambda x: x[1], reverse=True)

    ambiguity = False
    if len(sorted_regimes) >= 2:
        best_val, second_val = sorted_regimes[0][1], sorted_regimes[1][1]
        if best_val > 0 and second_val >= best_val - 1:
            ambiguity = True

    from_regime, to_regime = None, None
    if prob_level in ("high", "moderate") and sorted_regimes:
        top = sorted_regimes[0][0]
        if current_regime == "transitional" and len(sorted_regimes) >= 2:
            to_regime = top
            from_regime = sorted_regimes[1][0] if sorted_regimes[1][1] > 0 else None
        elif top != current_regime:
            from_regime, to_regime = current_regime, top

    return {
        "level": prob_level, "probability_range": prob_pct, "signaling_count": signaling,
        "avg_component_score": round(avg_score, 1), "ambiguous": ambiguity,
        "from_regime": from_regime, "to_regime": to_regime,
    }


def _build_evidence(component_results: dict) -> list:
    evidence = []
    for key in COMPONENT_WEIGHTS:
        comp = component_results.get(key, {})
        if not comp:
            continue
        score = comp.get("score", 0)
        if score >= 40:
            evidence.append({"component": COMPONENT_LABELS.get(key, key), "score": score, "signal": comp.get("signal", ""), "direction": comp.get("direction", "unknown")})
    evidence.sort(key=lambda x: x["score"], reverse=True)
    return evidence


def _interpret_zone(composite: float) -> dict:
    if composite <= 20:
        return {"zone": "Stable (No Transition)", "color": "green", "guidance": "All indicators stable. Current regime well-established.",
                "actions": ["Maintain current portfolio posture", "Standard rebalancing schedule", "Monitor monthly for early signals"]}
    elif composite <= 40:
        return {"zone": "Early Signal (Monitoring)", "color": "yellow", "guidance": "Minor shifts detected. Worth monitoring but not actionable yet.",
                "actions": ["Increase monitoring frequency to bi-weekly", "Review portfolio for regime sensitivity", "Identify potential adjustment triggers", "No position changes needed yet"]}
    elif composite <= 60:
        return {"zone": "Transition Zone (Preparing)", "color": "orange", "guidance": "Multiple indicators in transition. Begin planning portfolio adjustment.",
                "actions": ["Develop regime-change response plan", "Begin gradual diversification shifts", "Reduce concentrated bets", "Identify new regime beneficiaries", "Weekly monitoring"]}
    elif composite <= 80:
        return {"zone": "Active Transition (Repositioning)", "color": "red", "guidance": "Clear regime transition underway. Execute repositioning plan.",
                "actions": ["Execute planned portfolio adjustments", "Rotate toward new regime beneficiaries", "Reduce exposure to old regime leaders", "Increase hedging if contracting/inflationary", "Daily monitoring of confirmation signals"]}
    return {"zone": "Confirmed Transition (Completing)", "color": "critical", "guidance": "Strong confirmed transition. Complete repositioning.",
            "actions": ["Finalize portfolio repositioning", "Full allocation to new regime posture", "Monitor for transition exhaustion signals", "Prepare for new regime stability"]}


def classify_regime(component_results: dict) -> dict:
    conc = component_results.get("concentration", {})
    yc = component_results.get("yield_curve", {})
    credit = component_results.get("credit_conditions", {})
    size = component_results.get("size_factor", {})
    eb = component_results.get("equity_bond", {})
    sector = component_results.get("sector_rotation", {})

    available_count = sum(1 for comp in [conc, yc, credit, size, eb, sector] if comp.get("data_available", False))

    def _dir(comp: dict) -> str:
        return comp.get("direction", "unknown") if comp.get("data_available", False) else "unknown"

    conc_dir, yc_dir, credit_dir = _dir(conc), _dir(yc), _dir(credit)
    size_dir, eb_dir, sector_dir = _dir(size), _dir(eb), _dir(sector)
    corr_regime = eb.get("correlation_regime", "unknown") if eb.get("data_available", False) else "unknown"

    regime_scores = {
        "concentration": _score_concentration_regime(conc_dir, size_dir, credit_dir),
        "broadening": _score_broadening_regime(conc_dir, size_dir, credit_dir, sector_dir, yc_dir),
        "contraction": _score_contraction_regime(credit_dir, sector_dir, eb_dir, size_dir, yc_dir),
        "inflationary": _score_inflationary_regime(corr_regime, eb_dir),
        "transitional": 0,
    }

    all_scores = [conc.get("score", 0), yc.get("score", 0), credit.get("score", 0), size.get("score", 0), eb.get("score", 0), sector.get("score", 0)]
    signaling = sum(1 for s in all_scores if s >= 40)

    scored = {k: v for k, v in regime_scores.items() if k != "transitional"}
    sorted_regimes = sorted(scored.items(), key=lambda x: x[1], reverse=True)
    best_regime, best_score = sorted_regimes[0][0], sorted_regimes[0][1]

    is_tied = len(sorted_regimes) >= 2 and best_score > 0 and (best_score - sorted_regimes[1][1]) <= 1
    tied_regimes = [sorted_regimes[0][0], sorted_regimes[1][0]] if is_tied else None

    quick_composite = sum(comp.get("score", 0) * COMPONENT_WEIGHTS[k] for k, comp in component_results.items() if k in COMPONENT_WEIGHTS)

    if is_tied and quick_composite < 50:
        best_regime = "transitional"
        regime_scores["transitional"] = best_score
    elif signaling >= 3 and best_score < 3:
        best_regime = "transitional"
        best_score = signaling

    if best_score >= 4:
        confidence = "high"
    elif best_score >= 3:
        confidence = "moderate"
    elif best_score >= 2:
        confidence = "low"
    else:
        confidence = "very_low"

    if is_tied and confidence == "high":
        confidence = "moderate"
    if available_count <= 3:
        confidence = "very_low"
    elif available_count <= 4 and confidence in ("high", "moderate"):
        confidence = "low"

    transition_prob = _calculate_transition_probability(signaling, all_scores, regime_scores, best_regime, sorted_regimes)
    evidence = _build_evidence(component_results)
    regime_info = REGIME_DESCRIPTIONS.get(best_regime, {})

    return {
        "current_regime": best_regime, "regime_label": regime_info.get("label", best_regime),
        "regime_description": regime_info.get("description", ""), "confidence": confidence,
        "regime_scores": regime_scores, "signaling_components": signaling,
        "transition_probability": transition_prob, "portfolio_posture": regime_info.get("portfolio_posture", ""),
        "evidence": evidence, "tied_regimes": tied_regimes,
    }


REGIME_CONSISTENCY = {
    "broadening": {"concentration": "broadening", "size_factor": "small_cap_leading", "credit_conditions": ["stable", "easing"], "sector_rotation": "risk_on", "equity_bond": "risk_on", "yield_curve": "steepening"},
    "concentration": {"concentration": "concentrating", "size_factor": "large_cap_leading", "credit_conditions": ["stable", "easing"]},
    "contraction": {"credit_conditions": "tightening", "sector_rotation": "risk_off", "equity_bond": "risk_off", "yield_curve": ["flattening"]},
    "inflationary": {"equity_bond": "risk_off"},
    "transitional": {},
}


def check_regime_consistency(current_regime: str, component_results: dict) -> dict:
    expected = REGIME_CONSISTENCY.get(current_regime, {})
    result = {}
    for key in COMPONENT_WEIGHTS:
        comp = component_results.get(key, {})
        direction = comp.get("direction", "unknown")
        if key not in expected:
            result[key] = "neutral"
            continue
        exp_dir = expected[key]
        if isinstance(exp_dir, list):
            result[key] = "consistent" if direction in exp_dir else ("neutral" if direction == "unknown" else "contradicting")
        else:
            result[key] = "consistent" if direction == exp_dir else ("neutral" if direction == "unknown" else "contradicting")
    return result
