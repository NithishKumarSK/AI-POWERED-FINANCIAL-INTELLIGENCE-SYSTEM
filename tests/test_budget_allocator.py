"""Tests for core/portfolio_tools/budget_allocator.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from portfolio_tools.budget_allocator import allocate_budget


def test_basic_allocation_respects_cash_buffer():
    r = allocate_budget({"AAPL": 50, "MSFT": 50}, budget=10000, cash_buffer_pct=10)
    assert r["cash_buffer"] == 1000.0
    assert sum(r["allocations"].values()) + r["cash_buffer"] + r["left_idle"] == 10000.0


def test_single_position_over_cap_redistributes_to_others():
    # cap=40%: AAPL's excess (20pp) fully absorbs into MSFT/GOOGL (20->30 each)
    # without either of THEM then exceeding the cap too -- a cleanly
    # satisfiable case, unlike a 25% cap across 3 positions (mathematically
    # impossible to place 100% of capital, since 3*25=75 < 100).
    r = allocate_budget({"AAPL": 60, "MSFT": 20, "GOOGL": 20}, budget=10000, cash_buffer_pct=0, max_position_pct=40)
    assert r["allocations"]["AAPL"] == 4000  # capped at 40% of 10000
    assert "AAPL" in r["capped_tickers"]
    assert r["allocations"]["MSFT"] == r["allocations"]["GOOGL"] == 3000
    assert r["left_idle"] == 0.0


def test_all_positions_simultaneously_over_cap_leaves_excess_idle_not_dumped():
    """Regression test for a real bug caught this session: when every
    position is over the cap at once, the uncapped-redistribution pool is
    empty, and the un-placeable excess must stay idle -- not get dumped
    entirely onto one ticker, which would silently blow the very cap it
    exists to enforce (first version did exactly this: one ticker ended up
    at 50% despite a 25% cap)."""
    r = allocate_budget({"AAPL": 40, "MSFT": 30, "GOOGL": 30}, budget=10000, cash_buffer_pct=10, max_position_pct=25)
    investable = 9000
    for ticker, dollars in r["allocations"].items():
        assert dollars / investable <= 0.25 + 1e-6, f"{ticker} exceeded the cap: {dollars}/{investable}"
    assert r["left_idle"] > 0  # the un-placeable 25pp must show up here, not vanish


def test_small_slice_dropped_and_redistributed():
    # max_position_pct=100 isolates this test to the min_order_usd drop
    # logic alone -- otherwise the default 25% cap would also kick in on
    # AAPL's 98% weight and confound the result being checked here.
    r = allocate_budget({"AAPL": 98, "PENNY": 2}, budget=1000, cash_buffer_pct=0,
                         max_position_pct=100, min_order_usd=50)
    assert "PENNY" in r["dropped_tickers"]
    assert "PENNY" not in r["allocations"]
    assert r["allocations"]["AAPL"] == 1000  # PENNY's slice redistributed entirely to AAPL


def test_rejects_non_positive_budget():
    import pytest
    with pytest.raises(ValueError):
        allocate_budget({"AAPL": 100}, budget=0)


def test_empty_weights_returns_all_cash():
    r = allocate_budget({}, budget=10000, cash_buffer_pct=10)
    assert r["allocations"] == {}
    assert r["cash_buffer"] == 1000.0
    assert r["left_idle"] == 9000.0


def test_allocations_sum_plus_buffer_plus_idle_equals_budget():
    """Conservation check: every dollar is accounted for across allocations,
    buffer and idle, for a range of weight distributions."""
    cases = [
        {"AAPL": 40, "MSFT": 30, "GOOGL": 30},
        {"AAPL": 90, "MSFT": 5, "GOOGL": 5},
        {"A": 20, "B": 20, "C": 20, "D": 20, "E": 20},
    ]
    for weights in cases:
        r = allocate_budget(weights, budget=50000, cash_buffer_pct=10, max_position_pct=25, min_order_usd=100)
        total = sum(r["allocations"].values()) + r["cash_buffer"] + r["left_idle"]
        assert abs(total - 50000) < 1.0
