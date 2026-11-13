"""
Tests for core/parabolic_short_plan.py -- pure calculation, synthetic
Phase-1-candidate-shaped input only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from parabolic_short_plan import (
    build_manual_broker_result,
    build_size_recipe,
    build_trigger_plans,
    check_ssr_triggered,
    generate_plan_for_candidate,
)


def _candidate(symbol="XYZ", grade="A", composite_score=92.0, state_cap=None):
    return {"symbol": symbol, "grade": grade, "composite_score": composite_score, "state_cap": state_cap,
            "components": {"ma_extension": {"atr_units_above": 5.0}}}


def test_check_ssr_triggered_at_exactly_10_pct():
    assert check_ssr_triggered(intraday_low=90.0, prior_regular_close=100.0) is True


def test_check_ssr_not_triggered_below_threshold():
    assert check_ssr_triggered(intraday_low=91.0, prior_regular_close=100.0) is False


def test_check_ssr_handles_missing_prior_close():
    assert check_ssr_triggered(90.0, 0) is False


def test_build_size_recipe_basic():
    recipe = build_size_recipe(account_size=100_000, risk_bps=50, max_position_pct=10.0)
    assert recipe["risk_usd"] == 500.0
    assert recipe["max_position_value_usd"] == 10_000.0
    assert "shares_formula" in recipe
    assert recipe["exposure_cap_applied"] is False


def test_build_size_recipe_applies_exposure_cap_when_short_book_mostly_used():
    recipe = build_size_recipe(account_size=100_000, risk_bps=50, max_position_pct=10.0,
                                 current_short_exposure_usd=19_000, max_short_book_pct=20.0)
    assert recipe["exposure_cap_applied"] is True
    assert recipe["remaining_short_exposure_capacity_usd"] == 1_000.0
    assert recipe["max_position_value_usd"] == 1_000.0


def test_build_trigger_plans_has_all_three_types():
    plans = build_trigger_plans(atr14=None)
    types = {p["trigger_type"] for p in plans}
    assert types == {"orl_break", "first_red_5min", "vwap_fail"}
    for plan in plans:
        assert plan["entry_hint"]
        assert plan["stop_hint"]


def test_build_manual_broker_result_always_unavailable():
    result = build_manual_broker_result("XYZ")
    assert result["can_open_new_short"] is False
    assert result["manual_locate_required"] is True


def test_generate_plan_always_watch_only():
    plan = generate_plan_for_candidate(_candidate(), account_size=100_000)
    assert plan["plan_status"] == "watch_only"
    assert "borrow_inventory_unavailable" in plan["blocking_manual_reasons"]


def test_generate_plan_flags_ssr_active():
    plan = generate_plan_for_candidate(
        _candidate(), account_size=100_000,
        prior_regular_close=100.0, intraday_low_today=85.0,
    )
    assert plan["ssr_active"] is True
    assert "ssr_active" in plan["blocking_manual_reasons"]


def test_generate_plan_flags_still_in_markup_warning():
    plan = generate_plan_for_candidate(_candidate(state_cap="still_in_markup"), account_size=100_000)
    assert any("too_early_to_short" in r for r in plan["advisory_manual_reasons"])


def test_generate_plan_flags_recent_earnings_catalyst():
    plan = generate_plan_for_candidate(
        _candidate(), account_size=100_000, earnings_within_days_backward=5, earnings_catalyst_window_days=10,
    )
    assert any("recent_earnings_catalyst" in r for r in plan["advisory_manual_reasons"])


def test_generate_plan_three_trigger_plans_present():
    plan = generate_plan_for_candidate(_candidate(), account_size=100_000)
    assert len(plan["trigger_plans"]) == 3
