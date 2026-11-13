"""
Pre-Market Plan Generator (Phase 2), adapted from claude-trading-skills'
`parabolic-short-trade-planner` skill's `generate_pre_market_plan.py`
(vendor/claude-trading-skills/skills/parabolic-short-trade-planner/,
references/short_risk_management.md, references/intraday_trigger_playbook.md).
MIT License, Copyright (c) 2026 TraderMonty.

Takes a Phase 1 `core/parabolic_short_screener.py` candidate and renders
three trigger plans (ORL break / first-red-5min / VWAP-fail) with
entry_hint/stop_hint formula strings -- never a baked-in share count,
per the source skill's own design ("ORL / first-red / VWAP-fail entries
only have known prices intraday, so committing to a share count
pre-market would be inaccurate").

SCOPE REDUCTION, disclosed: this project has no Alpaca brokerage
account, so `ManualBrokerAdapter` is the ONLY broker adapter here (the
source skill's real Alpaca short-inventory check is not ported --
there's no account to check). Every plan is therefore always
`borrow_inventory_unavailable` / `plan_status: watch_only`, exactly as
the source skill's own documented behavior for a user without Alpaca
credentials -- this is the honest, real behavior for this project, not
a simulation of a different one.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def check_ssr_triggered(intraday_low: float, prior_regular_close: float) -> bool:
    """SEC Rule 201: triggered when intraday price drops >= 10% from
    the prior regular-session close."""
    if not prior_regular_close or prior_regular_close <= 0:
        return False
    return (prior_regular_close - intraday_low) / prior_regular_close >= 0.10


def build_size_recipe(
    account_size: float,
    risk_bps: float,
    max_position_pct: float,
    current_short_exposure_usd: float = 0.0,
    max_short_book_pct: float = 20.0,
) -> Dict[str, Any]:
    risk_usd = account_size * (risk_bps / 10000)
    max_position_value_usd = account_size * (max_position_pct / 100)
    max_short_book_usd = account_size * (max_short_book_pct / 100)
    remaining_capacity = max(0.0, max_short_book_usd - current_short_exposure_usd)

    exposure_cap_applied = remaining_capacity < max_position_value_usd
    effective_max_position_usd = min(max_position_value_usd, remaining_capacity) if exposure_cap_applied else max_position_value_usd

    return {
        "risk_usd": round(risk_usd, 2),
        "max_position_value_usd": round(effective_max_position_usd, 2),
        "shares_formula": "floor(risk_usd / (stop_actual - entry_actual))",
        "exposure_cap_applied": exposure_cap_applied,
        "remaining_short_exposure_capacity_usd": round(remaining_capacity, 2),
    }


def build_trigger_plans(atr14: Optional[float]) -> List[Dict[str, Any]]:
    """The three trigger types from parabolic_short_methodology.md --
    formula strings only, never a live intraday evaluation (Phase 3,
    not ported -- needs a live Alpaca 5-min bar feed this project has
    no account for)."""
    atr_term = f"{atr14:.2f}" if atr14 is not None else "ATR14"
    return [
        {
            "trigger_type": "orl_break",
            "entry_hint": "short break of opening_range_low (first 5-min bar low) on >= 1.2x that bar's volume",
            "stop_hint": f"session_HOD + 0.25 * {atr_term}",
        },
        {
            "trigger_type": "first_red_5min",
            "entry_hint": "short break of the first red 5-min candle's low",
            "stop_hint": "that candle's high",
        },
        {
            "trigger_type": "vwap_fail",
            "entry_hint": "5-min close back below VWAP after a retest, plus a lower-high break",
            "stop_hint": "VWAP reclaim (5-min close back above VWAP invalidates instantly)",
        },
    ]


def build_manual_broker_result(symbol: str) -> Dict[str, Any]:
    """ManualBrokerAdapter -- the only broker adapter available without an
    Alpaca account. Always reports inventory as unavailable, per the
    source skill's own documented fallback behavior."""
    return {
        "adapter": "ManualBrokerAdapter",
        "shortable": None,
        "easy_to_borrow": None,
        "can_open_new_short": False,
        "borrow_fee_apr": None,
        "manual_locate_required": True,
    }


def generate_plan_for_candidate(
    candidate: Dict[str, Any],
    account_size: float,
    risk_bps: float = 50.0,
    max_position_pct: float = 10.0,
    prior_regular_close: Optional[float] = None,
    intraday_low_today: Optional[float] = None,
    ssr_carryover_from_prior_day: bool = False,
    earnings_within_days_backward: Optional[int] = None,
    earnings_catalyst_window_days: int = 10,
    current_short_exposure_usd: float = 0.0,
) -> Dict[str, Any]:
    """candidate: a Phase 1 `screen_symbol()` CANDIDATE result."""
    symbol = candidate["symbol"]
    broker_result = build_manual_broker_result(symbol)

    ssr_triggered_today = (
        check_ssr_triggered(intraday_low_today, prior_regular_close)
        if intraday_low_today is not None and prior_regular_close is not None
        else False
    )
    ssr_active = ssr_triggered_today or ssr_carryover_from_prior_day

    blocking_manual_reasons = ["borrow_inventory_unavailable"]
    if ssr_active:
        blocking_manual_reasons.append("ssr_active")

    advisory_manual_reasons = ["manual_locate_required"]
    if candidate.get("state_cap") == "still_in_markup":
        advisory_manual_reasons.append("warning:too_early_to_short")
    if earnings_within_days_backward is not None and earnings_within_days_backward <= earnings_catalyst_window_days:
        advisory_manual_reasons.append("warning:recent_earnings_catalyst")

    # Phase 1 retains only the ATR-UNITS ratio (atr_units_above), not the raw
    # ATR14 dollar value, so the stop_hint formula stays symbolic ("ATR14")
    # rather than a fabricated number.
    trigger_plans = build_trigger_plans(atr14=None)
    size_recipe = build_size_recipe(account_size, risk_bps, max_position_pct, current_short_exposure_usd)

    return {
        "schema_version": "1.0",
        "symbol": symbol,
        "grade": candidate.get("grade"),
        "composite_score": candidate.get("composite_score"),
        "plan_status": "watch_only",  # always, per ManualBrokerAdapter -- see module docstring.
        "broker_result": broker_result,
        "ssr_active": ssr_active,
        "blocking_manual_reasons": blocking_manual_reasons,
        "advisory_manual_reasons": advisory_manual_reasons,
        "trigger_plans": trigger_plans,
        "size_recipe": size_recipe,
    }
