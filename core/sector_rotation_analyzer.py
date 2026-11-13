"""
Sector Analyst, adapted from claude-trading-skills' `sector-analyst`
skill (vendor/claude-trading-skills/skills/sector-analyst/SKILL.md,
references/sector_rotation.md). MIT License, Copyright (c) 2026
TraderMonty.

Pure calculation over TraderMonty's own free, keyless, publicly-updated
`sector_summary.csv` (confirmed live this session: real per-sector
uptrend ratio/10-day-MA/trend/slope/overbought-oversold status rows,
HTTP 200, no key) -- the same GitHub-hosted data family as
market_breadth_service.py's breadth/uptrend CSVs.

Faithfully ported: the sector ranking, the cyclical-vs-defensive
grouping and the four-cycle-phase mapping are taken directly from the
source skill's own `references/sector_rotation.md` knowledge base
("Sector Characteristics Summary" section), not guessed.

SCOPE REDUCTION, disclosed: the source skill's optional chart-image
industry-level supplement, and its narrative Markdown report (executive
summary / scenario analysis / recommended positioning, meant to be
written by an LLM reading this script's output) are not ported -- this
module produces the structured, numeric analysis the source skill's own
script computes; turning that into prose is a presentation step, not a
calculation this project's pipeline needs to do twice (the Gemini
consensus engine already writes prose from structured inputs elsewhere
in this project).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CYCLICAL_SECTORS = {
    "Technology", "Consumer Cyclical", "Industrials", "Basic Materials", "Financial", "Energy",
}
DEFENSIVE_SECTORS = {
    "Utilities", "Consumer Defensive", "Healthcare", "Communication Services", "Real Estate",
}

# Outperforming-sector sets per references/sector_rotation.md's "Outperforming
# Sectors" lists, normalized to this CSV's own sector-name spelling.
CYCLE_PHASE_OUTPERFORMERS = {
    "Early Cycle Recovery": {"Technology", "Consumer Cyclical", "Industrials", "Financial", "Real Estate"},
    "Mid Cycle Expansion": {"Technology", "Industrials", "Consumer Cyclical", "Basic Materials", "Energy"},
    "Late Cycle": {"Energy", "Basic Materials", "Financial", "Healthcare", "Consumer Defensive"},
    "Recession": {"Utilities", "Consumer Defensive", "Healthcare", "Communication Services"},
}


def rank_sectors(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sectors ranked by uptrend Ratio, descending."""
    return sorted(rows, key=lambda r: r.get("ratio", 0.0), reverse=True)


def compute_risk_regime_score(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Cyclical-vs-defensive score: mean(cyclical ratios) - mean(defensive
    ratios), scaled to roughly [-100, 100]. Positive = cyclical leadership
    (risk-on); negative = defensive leadership (risk-off)."""
    cyclical_ratios = [r["ratio"] for r in rows if r.get("sector") in CYCLICAL_SECTORS]
    defensive_ratios = [r["ratio"] for r in rows if r.get("sector") in DEFENSIVE_SECTORS]
    if not cyclical_ratios or not defensive_ratios:
        return {"score": None, "regime": "UNKNOWN", "cyclical_avg": None, "defensive_avg": None}

    cyclical_avg = sum(cyclical_ratios) / len(cyclical_ratios)
    defensive_avg = sum(defensive_ratios) / len(defensive_ratios)
    score = (cyclical_avg - defensive_avg) * 100

    if score > 5:
        regime = "CYCLICAL_LEADERSHIP"
    elif score < -5:
        regime = "DEFENSIVE_LEADERSHIP"
    else:
        regime = "MIXED"

    return {"score": round(score, 1), "regime": regime, "cyclical_avg": round(cyclical_avg, 4), "defensive_avg": round(defensive_avg, 4)}


def find_overbought_oversold(rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Directly from the CSV's own Status column -- no re-derivation."""
    return {
        "overbought": [r["sector"] for r in rows if r.get("status") == "Overbought"],
        "oversold": [r["sector"] for r in rows if r.get("status") == "Oversold"],
    }


def estimate_cycle_phase(rows: List[Dict[str, Any]], top_n: int = 5) -> Dict[str, Any]:
    """Match the top-N ranked sectors against each cycle phase's documented
    outperformer set; the best-overlapping phase wins. Confidence reflects
    how much better the winner overlaps vs. the runner-up, per the source
    skill's own probability-band language (not a numeric probability claim)."""
    ranked = rank_sectors(rows)
    top_sectors = {r["sector"] for r in ranked[:top_n]}

    overlaps = {
        phase: len(top_sectors & outperformers)
        for phase, outperformers in CYCLE_PHASE_OUTPERFORMERS.items()
    }
    best_phase = max(overlaps, key=overlaps.get)
    best_overlap = overlaps[best_phase]
    sorted_overlaps = sorted(overlaps.values(), reverse=True)
    runner_up = sorted_overlaps[1] if len(sorted_overlaps) > 1 else 0

    if best_overlap == 0:
        return {"phase": "UNCLEAR", "confidence": "LOW", "overlaps": overlaps}

    margin = best_overlap - runner_up
    confidence = "HIGH" if margin >= 2 else ("MEDIUM" if margin == 1 else "LOW")

    return {"phase": best_phase, "confidence": confidence, "overlaps": overlaps,
            "matching_sectors": sorted(top_sectors & CYCLE_PHASE_OUTPERFORMERS[best_phase])}


def analyze_sector_rotation(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """rows: parsed sector_summary.csv rows, each
    {"sector": str, "ratio": float, "ma10": float, "trend": str, "slope": float, "status": str}."""
    ranked = rank_sectors(rows)
    risk_regime = compute_risk_regime_score(rows)
    extremes = find_overbought_oversold(rows)
    cycle = estimate_cycle_phase(rows)

    return {
        "schema_version": "1.0",
        "ranked_sectors": [{"sector": r["sector"], "ratio": r["ratio"], "trend": r.get("trend"), "status": r.get("status")} for r in ranked],
        "risk_regime": risk_regime,
        "overbought_oversold": extremes,
        "cycle_phase": cycle,
    }
