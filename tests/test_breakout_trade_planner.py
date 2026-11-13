"""
Tests for core/breakout_trade_planner.py -- pure calculation, synthetic
VCP-screener-shaped input only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from breakout_trade_planner import (
    build_order_template,
    calculate_position_size,
    check_minervini_gate,
    compute_risk_pct,
    compute_trade_prices,
    plan_trade_for_candidate,
    rating_multiplier,
)


def _vcp_result(symbol="AAPL", composite_score=85, execution_state="Pre-breakout", valid_vcp=True,
                 price=100.0, pivot_price=100.0, last_contraction_low=96.0, breakout_volume=False,
                 distance_from_pivot_pct=1.0, sector="Technology"):
    return {
        "symbol": symbol, "composite_score": composite_score, "execution_state": execution_state,
        "valid_vcp": valid_vcp, "price": price, "sector": sector,
        "distance_from_pivot_pct": distance_from_pivot_pct,
        "vcp_pattern": {"pivot_price": pivot_price, "contractions": [{"low_price": last_contraction_low}]},
        "volume_pattern": {"breakout_volume_detected": breakout_volume},
    }


def test_rating_multiplier_bands():
    assert rating_multiplier(95) == 1.75
    assert rating_multiplier(85) == 1.0
    assert rating_multiplier(75) == 0.75
    assert rating_multiplier(65) == 0.0


def test_compute_trade_prices_formulas():
    prices = compute_trade_prices(pivot_price=100.0, last_contraction_low=94.0,
                                   pivot_buffer_pct=0.1, max_chase_pct=2.0, stop_buffer_pct=1.0)
    assert prices["signal_entry"] == 100.1
    assert prices["worst_entry"] == 102.0
    assert prices["stop_loss"] == 93.06


def test_compute_trade_prices_missing_inputs_returns_none():
    assert compute_trade_prices(None, 94.0) is None
    assert compute_trade_prices(100.0, None) is None


def test_compute_risk_pct():
    assert abs(compute_risk_pct(102.0, 93.06) - 8.76) < 0.01


def test_check_minervini_gate_pre_breakout_passes_without_volume_check():
    passed, reasons = check_minervini_gate(
        valid_vcp=True, composite_score=85, risk_pct_worst=5.0, execution_state="Pre-breakout",
        breakout_volume=False, distance_from_pivot_pct=None, current_price=100.0, worst_entry=102.0,
    )
    assert passed is True
    assert reasons == []


def test_check_minervini_gate_breakout_requires_volume():
    passed, reasons = check_minervini_gate(
        valid_vcp=True, composite_score=85, risk_pct_worst=5.0, execution_state="Breakout",
        breakout_volume=False, distance_from_pivot_pct=1.0, current_price=100.0, worst_entry=102.0,
    )
    assert passed is False
    assert any("breakout_volume" in r for r in reasons)


def test_check_minervini_gate_rejects_high_risk():
    passed, reasons = check_minervini_gate(
        valid_vcp=True, composite_score=85, risk_pct_worst=12.0, execution_state="Pre-breakout",
        breakout_volume=False, distance_from_pivot_pct=None, current_price=100.0, worst_entry=102.0,
    )
    assert passed is False
    assert any("risk_pct_worst" in r for r in reasons)


def test_calculate_position_size_respects_risk_and_cap():
    sizing = calculate_position_size(account_size=100_000, risk_pct_base=0.5, rating_mult=1.0,
                                       entry_price=102.0, stop_loss=93.06, max_position_pct=10.0)
    assert sizing["shares"] > 0
    assert sizing["position_value"] <= 10_000.01
    assert sizing["dollar_risk"] <= 500.01


def test_calculate_position_size_zero_risk_per_share_is_zero_shares():
    sizing = calculate_position_size(100_000, 0.5, 1.0, entry_price=100.0, stop_loss=100.0)
    assert sizing["shares"] == 0


def test_build_order_template_pre_place():
    prices = {"signal_entry": 100.1, "worst_entry": 102.0, "stop_loss": 93.06}
    order = build_order_template("AAPL", prices, shares=10, target_price=110.0, execution_mode="pre_place")
    assert order["type"] == "stop_limit"
    assert order["order_class"] == "bracket"
    assert order["take_profit"]["limit_price"] == 110.0


def test_build_order_template_post_confirm():
    prices = {"signal_entry": 100.1, "worst_entry": 102.0, "stop_loss": 93.06}
    order = build_order_template("AAPL", prices, shares=10, target_price=110.0, execution_mode="post_confirm")
    assert order["type"] == "limit"
    assert order["limit_price"] == 102.0


def test_plan_trade_for_candidate_actionable_pre_breakout():
    plan = plan_trade_for_candidate(_vcp_result(), account_size=100_000)
    assert plan["category"] == "ACTIONABLE"
    assert plan["execution_mode"] == "pre_place"
    assert plan["sizing"]["shares"] > 0


def test_plan_trade_for_candidate_revalidation_breakout_state():
    vcp = _vcp_result(execution_state="Breakout", breakout_volume=True, distance_from_pivot_pct=1.5, price=101.0)
    plan = plan_trade_for_candidate(vcp, account_size=100_000)
    assert plan["category"] == "REVALIDATION"
    assert plan["execution_mode"] == "post_confirm"


def test_plan_trade_for_candidate_rejected_invalid_vcp():
    vcp = _vcp_result(valid_vcp=False)
    plan = plan_trade_for_candidate(vcp, account_size=100_000)
    assert plan["category"] == "WATCHLIST"  # Pre-breakout + gate failure -> watchlist, not hard reject


def test_plan_trade_for_candidate_missing_pivot_is_rejected():
    vcp = _vcp_result()
    vcp["vcp_pattern"]["pivot_price"] = None
    plan = plan_trade_for_candidate(vcp, account_size=100_000)
    assert plan["category"] == "REJECTED"
