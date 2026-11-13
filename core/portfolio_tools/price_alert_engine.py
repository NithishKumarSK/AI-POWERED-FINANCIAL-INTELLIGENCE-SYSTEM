"""
price_alert_engine.py -- price alert rule evaluation (above/below/stop/
pct_move/opening_bell), adapted from trader-skill's trader-alerts skill
(vendor/trader-skill/trader-alerts/alerts.py, MIT License, Copyright (c)
2026 Jake Schincariol).

Pure rule-evaluation logic only -- no quote fetching (this project already
has its own live/historical price infrastructure in
core/historical_price_service.py; this module takes a current price as
input rather than re-implementing a second Yahoo/Stooq quote client).

Rule types (adapted from the source skill):
  above / below   rings once when price crosses the threshold, then stays
                   silent until reset() or (if rearm=True) the price falls
                   back across the threshold the other way, re-arming it
  stop             same mechanism as below, named for its common use
  pct_move         rings once per day when price has moved +/- pct vs a
                   reference price (previous close by default)
  opening_bell     rings once per trading day, no further condition
"""
from __future__ import annotations

from typing import Optional


def evaluate_rule(rule: dict, current_price: float, today: str, state: Optional[dict] = None) -> dict:
    """rule: {"id", "type": "above"|"below"|"stop"|"pct_move"|"opening_bell",
              "price": float (for above/below/stop), "pct": float (for pct_move),
              "ref_price": float (for pct_move, defaults to None), "rearm": bool}
    state: this rule's prior state, as returned by a previous call (or None
    for a never-evaluated rule): {"rung_on": "YYYY-MM-DD"|None, "armed": bool}

    Returns {"rings": bool, "state": {...}} -- the new state to persist for
    next time. Pure function; the caller is responsible for storing/loading
    state between calls (this project has no persistent alert-state file,
    unlike the source skill's trader/state/alerts.json)."""
    state = dict(state) if state else {"rung_on": None, "armed": True}
    rule_type = rule.get("type")

    if rule_type == "opening_bell":
        if state.get("rung_on") == today:
            return {"rings": False, "state": state}
        return {"rings": True, "state": {"rung_on": today, "armed": True}}

    if rule_type in ("above", "below", "stop"):
        threshold = rule["price"]
        crossed = (
            current_price >= threshold if rule_type == "above"
            else current_price <= threshold
        )
        if crossed and state.get("armed", True):
            return {"rings": True, "state": {"rung_on": today, "armed": False}}
        if not crossed and rule.get("rearm") and not state.get("armed", True):
            # Price fell back across the threshold the other way -- re-arm
            # so a future crossing can ring again.
            return {"rings": False, "state": {"rung_on": state.get("rung_on"), "armed": True}}
        return {"rings": False, "state": state}

    if rule_type == "pct_move":
        ref = rule.get("ref_price")
        if ref is None or ref == 0:
            return {"rings": False, "state": state}
        if state.get("rung_on") == today:
            return {"rings": False, "state": state}
        move_pct = (current_price - ref) / ref * 100.0
        if abs(move_pct) >= rule["pct"]:
            return {"rings": True, "state": {"rung_on": today, "armed": True}}
        return {"rings": False, "state": state}

    raise ValueError(f"unknown rule type {rule_type!r}")
