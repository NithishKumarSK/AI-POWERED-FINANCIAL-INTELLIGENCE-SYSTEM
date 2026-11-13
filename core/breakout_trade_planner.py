"""
Breakout Trade Planner, adapted from claude-trading-skills'
`breakout-trade-planner` skill (vendor/claude-trading-skills/skills/
breakout-trade-planner/SKILL.md, references/minervini_entry_rules.md).
MIT License, Copyright (c) 2026 TraderMonty.

Consumes this project's own core/vcp_screener.py output (already ported
and live-verified this session) and produces Minervini-style breakout
trade plans: entry/stop/target price derivation, rating-based position
sizing, a sequential portfolio-heat/sector-exposure gate across
candidates, and Alpaca-bracket-order-shaped templates.

SCOPE REDUCTION, disclosed: the source skill's "Entry Quality Checks"
step (5-minute-bar RVOL/close-location confirmation via a separate
`breakout-monitor` skill) is not ported -- this project has no intraday
bar feed. The `post_confirm` order template is still produced (its
fields don't depend on intraday confirmation data), but nothing here
actually performs that confirmation check; the caller is responsible for
it, exactly as the source skill delegates it to `breakout-monitor`.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

# Rating-Based Sizing table, keyed by composite_score band (not the
# string rating label, which this project's vcp_screener.py renders with
# a " VCP" suffix e.g. "Textbook VCP" -- the underlying composite_score
# bands are identical and avoid string-matching fragility).
def rating_multiplier(composite_score: float) -> float:
    if composite_score >= 90:
        return 1.75
    if composite_score >= 80:
        return 1.0
    if composite_score >= 70:
        return 0.75
    return 0.0  # Developing (60-69) or below -- watch only, per the source table.


def compute_trade_prices(
    pivot_price: float,
    last_contraction_low: Optional[float],
    pivot_buffer_pct: float = 0.1,
    max_chase_pct: float = 2.0,
    stop_buffer_pct: float = 1.0,
) -> Optional[Dict[str, float]]:
    """signal_entry/worst_entry/stop_loss per minervini_entry_rules.md's
    "Trade Price Derivation" formulas. None when a required input is missing."""
    if not pivot_price or pivot_price <= 0 or not last_contraction_low or last_contraction_low <= 0:
        return None
    signal_entry = pivot_price * (1 + pivot_buffer_pct / 100)
    worst_entry = pivot_price * (1 + max_chase_pct / 100)
    stop_loss = last_contraction_low * (1 - stop_buffer_pct / 100)
    return {"signal_entry": round(signal_entry, 2), "worst_entry": round(worst_entry, 2), "stop_loss": round(stop_loss, 2)}


def compute_risk_pct(entry_price: float, stop_loss: float) -> Optional[float]:
    if not entry_price or entry_price <= 0 or stop_loss is None:
        return None
    return (entry_price - stop_loss) / entry_price * 100


def check_minervini_gate(
    valid_vcp: bool,
    composite_score: float,
    risk_pct_worst: Optional[float],
    execution_state: str,
    breakout_volume: bool,
    distance_from_pivot_pct: Optional[float],
    current_price: float,
    worst_entry: Optional[float],
    max_chase_pct: float = 2.0,
) -> Tuple[bool, List[str]]:
    """The source skill's "Minervini Gate" table, both rows. Returns (passed, reasons)."""
    reasons: List[str] = []
    is_breakout = execution_state in ("Breakout", "Early-post-breakout")

    if not valid_vcp:
        reasons.append("valid_vcp is False")
    if composite_score < 70:
        reasons.append(f"rating_band below good/strong/textbook (composite_score={composite_score})")
    if risk_pct_worst is None or risk_pct_worst > 8.0:
        reasons.append(f"risk_pct_worst {risk_pct_worst} exceeds 8.0% ceiling")

    if is_breakout:
        if not breakout_volume:
            reasons.append("breakout_volume is False")
        if distance_from_pivot_pct is None or distance_from_pivot_pct > max_chase_pct:
            reasons.append(f"distance_from_pivot_pct {distance_from_pivot_pct} exceeds max_chase_pct {max_chase_pct}")
        if worst_entry is None or current_price > worst_entry:
            reasons.append(f"current_price {current_price} exceeds worst_entry {worst_entry}")

    return (len(reasons) == 0), reasons


def calculate_position_size(
    account_size: float,
    risk_pct_base: float,
    rating_mult: float,
    entry_price: float,
    stop_loss: float,
    max_position_pct: float = 10.0,
) -> Dict[str, Any]:
    """Worst-case-entry-based sizing: risk $ = account_size * risk_pct_base% * rating_multiplier."""
    risk_per_share = entry_price - stop_loss
    if risk_per_share <= 0:
        return {"shares": 0, "dollar_risk": 0.0, "position_value": 0.0, "position_pct": 0.0}

    dollar_risk_budget = account_size * (risk_pct_base / 100) * rating_mult
    shares_by_risk = math.floor(dollar_risk_budget / risk_per_share) if dollar_risk_budget > 0 else 0

    max_position_value = account_size * (max_position_pct / 100)
    shares_by_cap = math.floor(max_position_value / entry_price) if entry_price > 0 else 0

    shares = max(0, min(shares_by_risk, shares_by_cap))
    position_value = shares * entry_price
    dollar_risk = shares * risk_per_share

    return {
        "shares": shares,
        "dollar_risk": round(dollar_risk, 2),
        "position_value": round(position_value, 2),
        "position_pct": round(position_value / account_size * 100, 2) if account_size else 0.0,
    }


def build_order_template(
    symbol: str,
    prices: Dict[str, float],
    shares: int,
    target_price: float,
    execution_mode: str,
) -> Dict[str, Any]:
    """Alpaca-bracket-order-shaped template (real Alpaca field names: side,
    type, qty, order_class=bracket, stop_loss.stop_price,
    take_profit.limit_price) -- a planning artifact, not a live broker call."""
    base = {
        "symbol": symbol,
        "side": "buy",
        "qty": shares,
        "order_class": "bracket",
        "time_in_force": "gtc",
        "take_profit": {"limit_price": round(target_price, 2)},
        "stop_loss": {"stop_price": prices["stop_loss"]},
    }
    if execution_mode == "pre_place":
        base.update({"type": "stop_limit", "stop_price": prices["signal_entry"], "limit_price": prices["worst_entry"]})
    else:  # post_confirm
        base.update({"type": "limit", "limit_price": prices["worst_entry"]})
    return base


def plan_trade_for_candidate(
    vcp_result: Dict[str, Any],
    account_size: float,
    risk_pct: float = 0.5,
    max_position_pct: float = 10.0,
    max_chase_pct: float = 2.0,
    stop_buffer_pct: float = 1.0,
    pivot_buffer_pct: float = 0.1,
    target_r_multiple: float = 2.0,
) -> Dict[str, Any]:
    """Build one candidate's plan from a core/vcp_screener.py `analyze_stock()` result."""
    symbol = vcp_result.get("symbol", "UNKNOWN")
    composite_score = vcp_result.get("composite_score", 0)
    execution_state = vcp_result.get("execution_state", "Invalid")
    valid_vcp = vcp_result.get("valid_vcp", False)
    current_price = vcp_result.get("price", 0)

    vcp_pattern = vcp_result.get("vcp_pattern", {}) or {}
    pivot_price = vcp_pattern.get("pivot_price")
    contractions = vcp_pattern.get("contractions") or []
    last_contraction_low = contractions[-1].get("low_price") if contractions else None

    volume_pattern = vcp_result.get("volume_pattern", {}) or {}
    breakout_volume = volume_pattern.get("breakout_volume_detected", False)
    distance_from_pivot_pct = vcp_result.get("distance_from_pivot_pct")

    prices = compute_trade_prices(pivot_price, last_contraction_low, pivot_buffer_pct, max_chase_pct, stop_buffer_pct)
    if prices is None:
        return {"symbol": symbol, "category": "REJECTED", "reasons": ["Missing pivot_price or last_contraction_low"]}

    risk_pct_worst = compute_risk_pct(prices["worst_entry"], prices["stop_loss"])

    passed, reasons = check_minervini_gate(
        valid_vcp=valid_vcp, composite_score=composite_score, risk_pct_worst=risk_pct_worst,
        execution_state=execution_state, breakout_volume=breakout_volume,
        distance_from_pivot_pct=distance_from_pivot_pct, current_price=current_price,
        worst_entry=prices["worst_entry"], max_chase_pct=max_chase_pct,
    )

    if not passed:
        category = "WATCHLIST" if execution_state == "Pre-breakout" else "REJECTED"
        return {"symbol": symbol, "category": category, "reasons": reasons, "composite_score": composite_score,
                "execution_state": execution_state, "prices": prices, "risk_pct_worst": risk_pct_worst}

    mult = rating_multiplier(composite_score)
    sizing = calculate_position_size(account_size, risk_pct, mult, prices["worst_entry"], prices["stop_loss"], max_position_pct)

    r_distance = prices["worst_entry"] - prices["stop_loss"]
    target_price = prices["worst_entry"] + r_distance * target_r_multiple
    reward_risk_ratio = target_r_multiple

    category = "ACTIONABLE" if execution_state == "Pre-breakout" else "REVALIDATION"
    execution_mode = "pre_place" if execution_state == "Pre-breakout" else "post_confirm"
    order_template = build_order_template(symbol, prices, sizing["shares"], target_price, execution_mode)

    return {
        "symbol": symbol, "category": category, "composite_score": composite_score,
        "execution_state": execution_state, "rating_multiplier": mult,
        "prices": prices, "risk_pct_worst": risk_pct_worst,
        "target_price": round(target_price, 2), "reward_risk_ratio": reward_risk_ratio,
        "sizing": sizing, "execution_mode": execution_mode, "order_template": order_template,
        "sector": vcp_result.get("sector", "Unknown"),
    }
