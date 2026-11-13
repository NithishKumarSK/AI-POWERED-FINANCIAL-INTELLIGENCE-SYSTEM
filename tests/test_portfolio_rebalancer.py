"""Tests for core/portfolio_tools/portfolio_rebalancer.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from portfolio_tools.portfolio_rebalancer import plan_rebalance


def test_drifted_position_generates_sell_and_buy():
    r = plan_rebalance(
        holdings={"AAPL": 60, "MSFT": 20}, prices={"AAPL": 10, "MSFT": 20},
        target_weights={"AAPL": 50, "MSFT": 50}, cash=0,
        cash_buffer_pct=0, max_position_pct=100, drift_band_pct=5,
    )
    sides = {o["ticker"]: o["side"] for o in r["orders"]}
    assert sides["AAPL"] == "sell"
    assert sides["MSFT"] == "buy"


def test_drift_within_band_generates_no_trades():
    r = plan_rebalance(
        holdings={"AAPL": 52, "MSFT": 48}, prices={"AAPL": 10, "MSFT": 10},
        target_weights={"AAPL": 50, "MSFT": 50}, cash=0,
        cash_buffer_pct=0, max_position_pct=100, drift_band_pct=5,
    )
    assert r["orders"] == []


def test_sells_appear_before_buys_in_order_list():
    r = plan_rebalance(
        holdings={"AAPL": 80, "MSFT": 0}, prices={"AAPL": 10, "MSFT": 10},
        target_weights={"AAPL": 50, "MSFT": 50}, cash=0,
        cash_buffer_pct=0, max_position_pct=100, drift_band_pct=5,
    )
    sides_in_order = [o["side"] for o in r["orders"]]
    assert sides_in_order.index("sell") < sides_in_order.index("buy")


def test_untracked_holding_left_alone_by_default():
    r = plan_rebalance(
        holdings={"AAPL": 50, "UNTRACKED": 10}, prices={"AAPL": 10, "UNTRACKED": 10},
        target_weights={"AAPL": 100}, cash=0,
        cash_buffer_pct=0, max_position_pct=100, drift_band_pct=5,
    )
    assert "UNTRACKED" in r["untracked"]
    assert not any(o["ticker"] == "UNTRACKED" for o in r["orders"])


def test_sell_untracked_liquidates_it():
    r = plan_rebalance(
        holdings={"AAPL": 50, "UNTRACKED": 10}, prices={"AAPL": 10, "UNTRACKED": 10},
        target_weights={"AAPL": 100}, cash=0,
        cash_buffer_pct=0, max_position_pct=100, drift_band_pct=5, sell_untracked=True,
    )
    assert any(o["ticker"] == "UNTRACKED" and o["side"] == "sell" for o in r["orders"])
    assert r["untracked"] == []


def test_buys_scaled_down_when_cash_insufficient():
    # Sells free $0 (nothing over target to sell); starting cash is small,
    # so the buy must be scaled down to what's actually available.
    r = plan_rebalance(
        holdings={}, prices={"AAPL": 10},
        target_weights={"AAPL": 100}, cash=100,
        cash_buffer_pct=0, max_position_pct=100, drift_band_pct=5,
        min_order_usd=1,
    )
    # account_value = 100 (cash only, no holdings) -> target AAPL = $100 -> buy $100, fully fundable
    assert r["orders"] == [{"ticker": "AAPL", "side": "buy", "dollars": 100.0}]


def test_order_below_min_order_usd_is_skipped():
    r = plan_rebalance(
        holdings={"AAPL": 52, "MSFT": 48}, prices={"AAPL": 10, "MSFT": 10},
        target_weights={"AAPL": 50, "MSFT": 50}, cash=0,
        cash_buffer_pct=0, max_position_pct=100, drift_band_pct=0, min_order_usd=1000,
    )
    assert r["orders"] == []


def test_order_above_max_order_usd_is_capped_and_reported():
    r = plan_rebalance(
        holdings={}, prices={"AAPL": 10},
        target_weights={"AAPL": 100}, cash=5000,
        cash_buffer_pct=0, max_position_pct=100, drift_band_pct=5,
        max_order_usd=1000,
    )
    buy = next(o for o in r["orders"] if o["ticker"] == "AAPL")
    assert buy["dollars"] == 1000
    assert r["capped_orders"]


def test_rejects_zero_account_value():
    import pytest
    with pytest.raises(ValueError):
        plan_rebalance(holdings={}, prices={}, target_weights={}, cash=0)
