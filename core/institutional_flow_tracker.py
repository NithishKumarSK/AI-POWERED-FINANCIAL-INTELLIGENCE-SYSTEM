"""
Institutional Flow Tracker, adapted from claude-trading-skills'
`institutional-flow-tracker` skill (vendor/claude-trading-skills/skills/
institutional-flow-tracker/SKILL.md). MIT License, Copyright (c) 2026
TraderMonty.

Quarter-over-quarter accumulation/distribution classification, reusing
core/institutional_holdings_service.py's already-built, free, keyless
SEC EDGAR 13F-HR parsing (the same 23-well-known-filer list already used
as a proxy in canslim_screener.py's institutional-sponsorship component)
-- extended this session with a "prior quarter" fetch
(fetch_13f_holdings_at_offset) so two consecutive quarters per filer can
be diffed.

SCOPE REDUCTION, disclosed: the source skill's cross-sectional "--top 50
stocks by institutional change" screening needs FMP's premium company-
screener/institutional-ownership-change endpoints (same reduction as
every other cross-universe skill this session). This tracks ONE
caller-supplied symbol's flow across the SAME curated 23-filer list
already vetted for canslim_screener.py, not a market-wide scan, and not
FMP's full universe of institutional filers (thousands of 13F filers
exist; this project only has free, keyless, verified parsing for these
23 well-known names).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def classify_filer_flow(current_value: float, prior_value: Optional[float]) -> str:
    """ACCUMULATION / DISTRIBUTION / NEW_POSITION / EXITED / FLAT / NO_POSITION,
    per the source skill's core "smart money" direction concept."""
    if current_value <= 0 and (prior_value is None or prior_value <= 0):
        return "NO_POSITION"
    if current_value > 0 and (prior_value is None or prior_value <= 0):
        return "NEW_POSITION"
    if current_value <= 0 and prior_value and prior_value > 0:
        return "EXITED"
    change_pct = (current_value - prior_value) / prior_value * 100 if prior_value else 0.0
    if change_pct >= 10:
        return "ACCUMULATION"
    if change_pct <= -10:
        return "DISTRIBUTION"
    return "FLAT"


def compute_flow_score(filer_flows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Net flow score (-100..+100): (accumulating - distributing) / active filers.
    NEW_POSITION counts as accumulating, EXITED as distributing; FLAT/NO_POSITION
    are excluded from the denominator (they carry no directional signal)."""
    directional = [f for f in filer_flows if f["flow"] in ("ACCUMULATION", "DISTRIBUTION", "NEW_POSITION", "EXITED")]
    if not directional:
        return {"flow_score": 0.0, "classification": "NO_SIGNAL", "active_filers": 0}

    accumulating = sum(1 for f in directional if f["flow"] in ("ACCUMULATION", "NEW_POSITION"))
    distributing = sum(1 for f in directional if f["flow"] in ("DISTRIBUTION", "EXITED"))
    score = (accumulating - distributing) / len(directional) * 100

    if score >= 25:
        classification = "SMART_MONEY_ACCUMULATION"
    elif score <= -25:
        classification = "SMART_MONEY_DISTRIBUTION"
    else:
        classification = "MIXED"

    return {"flow_score": round(score, 1), "classification": classification, "active_filers": len(directional),
            "accumulating_count": accumulating, "distributing_count": distributing}
