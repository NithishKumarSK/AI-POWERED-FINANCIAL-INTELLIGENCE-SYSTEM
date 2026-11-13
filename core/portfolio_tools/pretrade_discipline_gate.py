"""
pretrade_discipline_gate.py -- manual-order execution discipline checklist,
adapted from claude-trading-skills' pre-trade-discipline-gate skill
(vendor/claude-trading-skills/skills/pre-trade-discipline-gate/, MIT
License, Copyright (c) 2026 TraderMonty).

Checks whether a proposed manual trade has a written plan, a predefined
stop, confirmed sizing, and actual risk not exceeding planned risk --
blocks on missing discipline, not on market conditions (that's
drawdown_circuit_breaker.py's job). Pure function; no thesis-file reading
(this project has no trader-memory-core state), no journaling.
"""
from __future__ import annotations

from typing import Optional

ACTIONABLE_INTENTS = {"ENTRY_READY", "ACTIONABLE", "ACTIONABLE_DAY1", "MANUAL_ORDER"}
NON_ACTIONABLE_INTENTS = {"WATCHLIST", "DELAYED_EP_WATCH", "PEAD_HANDOFF", "IGNORE", "REJECTED"}
DECISION_RANK = {"GO": 0, "NO_ACTIONABLE_ORDERS": 1, "REVIEW_REQUIRED": 2, "NO_GO": 3}


def check_discipline(
    order_intent: str,
    entry_in_written_plan: bool = False,
    stop_predefined: bool = False,
    size_within_plan: bool = False,
    planned_risk_dollars: Optional[float] = None,
    actual_risk_dollars: Optional[float] = None,
) -> dict:
    """Returns {"decision": "GO"|"REVIEW_REQUIRED"|"NO_GO"|"NO_ACTIONABLE_ORDERS",
    "reasons": [...]}.

    GO only when the intent is actionable AND every checklist item is
    confirmed AND actual risk doesn't exceed planned risk. Missing/invalid
    risk numbers get REVIEW_REQUIRED (can't verify, not a free pass); any
    failed checklist item or risk overrun gets NO_GO (the strictest
    outcome, consistent with DECISION_RANK's own ordering)."""
    intent = (order_intent or "").strip().upper()

    if intent not in ACTIONABLE_INTENTS:
        if intent in NON_ACTIONABLE_INTENTS:
            return {"decision": "NO_ACTIONABLE_ORDERS", "reasons": [f"order_intent {intent} has no manual order to place"]}
        return {"decision": "REVIEW_REQUIRED", "reasons": [f"order_intent {intent or '<missing>'} is unknown; review before acting"]}

    decision = "GO"
    reasons: list = []

    def _raise(new_decision: str, reason: str) -> None:
        nonlocal decision
        if DECISION_RANK[new_decision] > DECISION_RANK[decision]:
            decision = new_decision
        reasons.append(reason)

    if not entry_in_written_plan:
        _raise("NO_GO", "entry is not confirmed in the written plan")
    if not stop_predefined:
        _raise("NO_GO", "stop is not predefined")
    if not size_within_plan:
        _raise("NO_GO", "size is not confirmed within plan")

    def _valid_nonneg(v) -> bool:
        try:
            return v is not None and float(v) >= 0
        except (TypeError, ValueError):
            return False

    if not _valid_nonneg(planned_risk_dollars):
        _raise("REVIEW_REQUIRED", "planned_risk_dollars is required and must be a finite non-negative number")
    if not _valid_nonneg(actual_risk_dollars):
        _raise("REVIEW_REQUIRED", "actual_risk_dollars is required and must be a finite non-negative number")

    if _valid_nonneg(planned_risk_dollars) and _valid_nonneg(actual_risk_dollars):
        if float(actual_risk_dollars) > float(planned_risk_dollars):
            _raise("NO_GO", f"actual risk {actual_risk_dollars} exceeds planned risk {planned_risk_dollars}")

    return {"decision": decision, "reasons": reasons}
