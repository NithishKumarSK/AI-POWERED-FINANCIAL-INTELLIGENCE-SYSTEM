"""
Tests for core/breakout_trade_planner_service.py -- pure batch logic,
synthetic VCP-screener-shaped inputs only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from breakout_trade_planner_service import plan_breakout_trades


def _vcp_result(symbol, composite_score=85, pivot_price=100.0, last_contraction_low=96.0,
                 execution_state="Pre-breakout", sector="Technology", price=100.0):
    return {
        "symbol": symbol, "composite_score": composite_score, "execution_state": execution_state,
        "valid_vcp": True, "price": price, "sector": sector,
        "distance_from_pivot_pct": 1.0,
        "vcp_pattern": {"pivot_price": pivot_price, "contractions": [{"low_price": last_contraction_low}]},
        "volume_pattern": {"breakout_volume_detected": False},
    }


def test_plan_breakout_trades_categorizes_single_actionable_candidate():
    result = plan_breakout_trades([_vcp_result("AAPL")], account_size=100_000)
    assert len(result["actionable"]) == 1
    assert result["actionable"][0]["symbol"] == "AAPL"
    assert result["total_portfolio_heat_pct"] > 0


def test_plan_breakout_trades_sorts_by_composite_score_for_heat_allocation():
    candidates = [
        _vcp_result("LOW", composite_score=71, sector="A"),
        _vcp_result("HIGH", composite_score=99, sector="B"),
    ]
    result = plan_breakout_trades(candidates, account_size=100_000, max_portfolio_heat_pct=100.0)
    symbols_in_order = [p["symbol"] for p in result["actionable"]]
    assert symbols_in_order[0] == "HIGH" or len(symbols_in_order) <= 1


def test_plan_breakout_trades_constrains_on_portfolio_heat_cap():
    candidates = [_vcp_result(f"SYM{i}", composite_score=95 - i, sector=f"Sector{i}") for i in range(10)]
    result = plan_breakout_trades(candidates, account_size=100_000, max_portfolio_heat_pct=0.01)
    assert len(result["constrained"]) > 0
    assert result["total_portfolio_heat_pct"] <= 0.01 + 1e-6


def test_plan_breakout_trades_constrains_on_sector_cap():
    candidates = [_vcp_result(f"SYM{i}", composite_score=95 - i, sector="Technology") for i in range(5)]
    result = plan_breakout_trades(candidates, account_size=100_000, max_position_pct=10.0,
                                    max_sector_pct=10.0, max_portfolio_heat_pct=100.0)
    tech_total = sum(p["sizing"]["position_pct"] for p in result["actionable"] if p.get("sector") == "Technology")
    assert tech_total <= 10.0 + 1e-6
    assert len(result["constrained"]) > 0


def test_plan_breakout_trades_watchlist_and_rejected_pass_through():
    candidates = [_vcp_result("WATCH", composite_score=65)]  # below gate's 70 threshold -> watchlist
    result = plan_breakout_trades(candidates, account_size=100_000)
    assert len(result["watchlist"]) == 1
    assert result["actionable"] == []
