"""
Exposure Coach, adapted from claude-trading-skills' `exposure-coach` skill
(vendor/claude-trading-skills/skills/exposure-coach/SKILL.md). MIT
License, Copyright (c) 2026 TraderMonty.

Synthesizes this project's own already-ported market-top-detector,
ftd-detector, macro-regime-detector, and market-breadth-analyzer /
uptrend-analyzer outputs into one "how much capital should I commit to
equities right now?" posture, exactly the question the source skill
answers.

SCOPE REDUCTION, disclosed: the source skill also ingests theme-detector,
sector-analyst, and institutional-flow-tracker outputs. None of those
three exist in this project (theme-detector is confirmed FINVIZ-blocked;
sector-analyst and institutional-flow-tracker were not built this
session). Per the source skill's OWN design -- "accepts partial inputs;
missing files reduce confidence but do not block execution" -- those
three dimensions are always reported in `inputs_missing`, never
fabricated, and never folded into the score. `bias` (growth vs. value)
is therefore DROPPED rather than guessed, since the only two signals the
source skill uses for it (sector-analyst, institutional-flow-tracker) are
exactly the three missing dimensions.

The exposure math below (parsing market-top-detector's own `risk_budget`
string as the baseline ceiling, then applying breadth/FTD
floors/haircuts) is this project's own reasonable combination logic, not
a byte-for-byte port of `calculate_exposure.py` (not available to read --
only the skill's documented I/O contract is), and is documented as such.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

_CORRECTIVE_FTD_STATES = {"CORRECTION", "RALLY_FAILED", "FTD_INVALIDATED", "RALLY_ATTEMPT"}


def _parse_risk_budget_midpoint(risk_budget: Optional[str]) -> Optional[float]:
    """"100%" -> 100.0, "60-75%" -> 67.5, None/malformed -> None."""
    if not risk_budget:
        return None
    nums = re.findall(r"\d+(?:\.\d+)?", risk_budget)
    if not nums:
        return None
    vals = [float(n) for n in nums]
    return sum(vals) / len(vals)


def build_exposure_posture(
    breadth_data: Optional[Dict[str, Any]] = None,
    regime_data: Optional[Dict[str, Any]] = None,
    top_risk_data: Optional[Dict[str, Any]] = None,
    ftd_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Combine the 4 available dimensions into a Market Posture summary.

    Each *_data argument is the trimmed dict the corresponding
    *_service.py's compute_*() function returns on success, or None when
    that source is unavailable -- the caller passes None rather than this
    function reaching out to any live source itself (kept pure/testable,
    consistent with every other *_screener.py / *_analyzer.py here).
    """
    inputs_provided = []
    inputs_missing = []
    component_scores: Dict[str, Optional[float]] = {}

    # --- Top risk (market-top-detector) sets the baseline ceiling. ---
    ceiling: Optional[float] = None
    if top_risk_data and top_risk_data.get("risk_budget"):
        ceiling = _parse_risk_budget_midpoint(top_risk_data["risk_budget"])
        component_scores["top_risk_score"] = top_risk_data.get("composite_score")
        inputs_provided.append("top_risk")
    else:
        component_scores["top_risk_score"] = None
        inputs_missing.append("top_risk")

    # --- Breadth / uptrend sets participation + a narrow-market haircut. ---
    participation = "UNKNOWN"
    if breadth_data and breadth_data.get("breadth_200dma_pct") is not None:
        breadth_pct = breadth_data["breadth_200dma_pct"]
        component_scores["breadth_score"] = breadth_pct
        participation = "BROAD" if breadth_pct >= 50 else "NARROW"
        inputs_provided.append("breadth")
        if ceiling is not None and participation == "NARROW":
            ceiling -= 10
    else:
        component_scores["breadth_score"] = None
        inputs_missing.append("breadth")

    if breadth_data and breadth_data.get("uptrend_ratio") is not None:
        component_scores["uptrend_score"] = breadth_data["uptrend_ratio"] * 100
        inputs_provided.append("uptrend")
    else:
        component_scores["uptrend_score"] = None
        inputs_missing.append("uptrend")

    # --- FTD state applies a hard defensive floor during unconfirmed moves. ---
    if ftd_data and ftd_data.get("combined_state"):
        state = ftd_data["combined_state"]
        component_scores["ftd_score"] = 100.0 if state == "FTD_CONFIRMED" else (0.0 if state in _CORRECTIVE_FTD_STATES else 50.0)
        inputs_provided.append("ftd")
        if state in _CORRECTIVE_FTD_STATES and ceiling is not None:
            ceiling = min(ceiling, 50.0)
    else:
        component_scores["ftd_score"] = None
        inputs_missing.append("ftd")

    # --- Regime sets confidence, per "Regime Alignment": baseline from top
    # risk/FTD, regime only tightens confidence, never silently raises the
    # ceiling (Safety First). `very_low` confidence or missing availability
    # metadata is treated as missing critical input, per the source
    # skill's own rule -- the regime score is NOT used in that case.
    regime_confidence_label = (regime_data or {}).get("confidence")
    regime_usable = bool(regime_data and regime_data.get("composite_score") is not None and regime_confidence_label != "very_low")
    if regime_usable:
        component_scores["regime_score"] = regime_data.get("composite_score")
        inputs_provided.append("regime")
    else:
        component_scores["regime_score"] = None
        inputs_missing.append("regime")

    # Dimensions this project has no source for -- always missing, never guessed.
    for dim in ("theme", "sector", "institutional"):
        component_scores[f"{dim}_score"] = None
        inputs_missing.append(dim)

    if ceiling is None:
        # No top-risk input at all -- Safety First: default to a conservative
        # ceiling rather than reporting an unconstrained "100%".
        ceiling = 50.0
    ceiling = max(0.0, min(100.0, ceiling))

    if ceiling >= 70:
        recommendation = "NEW_ENTRY_ALLOWED"
    elif ceiling >= 40:
        recommendation = "REDUCE_ONLY"
    else:
        recommendation = "CASH_PRIORITY"

    n_critical_present = sum(1 for k in ("top_risk", "ftd", "breadth") if k in inputs_provided)
    if n_critical_present == 3 and regime_usable:
        confidence = "HIGH"
    elif n_critical_present >= 2:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return {
        "schema_version": "1.0",
        "exposure_ceiling_pct": round(ceiling, 1),
        "participation": participation,
        "recommendation": recommendation,
        "confidence": confidence,
        "component_scores": component_scores,
        "inputs_provided": inputs_provided,
        "inputs_missing": sorted(set(inputs_missing)),
    }
