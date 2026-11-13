"""Tests for core/portfolio_tools/pretrade_risk_gate.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from portfolio_tools.pretrade_risk_gate import check_order


def test_normal_buy_passes():
    r = check_order({"symbol": "AAPL", "side": "buy", "notional": 500},
                     account_cash=10000, account_prices={"AAPL": 150})
    assert r["verdict"] == "PASS"
    assert r["reasons"] == []


def test_missing_symbol_blocks():
    r = check_order({"side": "buy", "notional": 500}, account_cash=10000)
    assert r["verdict"] == "BLOCK"
    assert any("no symbol" in reason for reason in r["reasons"])


def test_invalid_side_blocks():
    r = check_order({"symbol": "AAPL", "side": "hold", "notional": 500}, account_cash=10000)
    assert r["verdict"] == "BLOCK"


def test_both_qty_and_notional_blocks():
    r = check_order({"symbol": "AAPL", "side": "buy", "qty": 5, "notional": 500}, account_cash=10000)
    assert r["verdict"] == "BLOCK"
    assert any("exactly one" in reason for reason in r["reasons"])


def test_neither_qty_nor_notional_blocks():
    r = check_order({"symbol": "AAPL", "side": "buy"}, account_cash=10000)
    assert r["verdict"] == "BLOCK"


def test_options_symbol_blocked_by_default():
    r = check_order({"symbol": "AAPL260116C00150000", "side": "buy", "notional": 500}, account_cash=10000)
    assert r["verdict"] == "BLOCK"
    assert any("options" in reason for reason in r["reasons"])


def test_options_symbol_allowed_when_configured():
    r = check_order({"symbol": "AAPL260116C00150000", "side": "buy", "notional": 500},
                     account_cash=10000, rules={"allow_options": True})
    assert r["verdict"] == "PASS"


def test_blocked_ticker_list():
    r = check_order({"symbol": "XYZ", "side": "buy", "notional": 100},
                     account_cash=10000, rules={"blocked": ["XYZ"]})
    assert r["verdict"] == "BLOCK"
    assert any("blocked list" in reason for reason in r["reasons"])


def test_order_below_min_size_blocks():
    r = check_order({"symbol": "AAPL", "side": "buy", "notional": 2},
                     account_cash=10000, rules={"min_order_usd": 5})
    assert r["verdict"] == "BLOCK"
    assert any("under min_order_usd" in reason for reason in r["reasons"])


def test_order_above_max_size_blocks():
    r = check_order({"symbol": "AAPL", "side": "buy", "notional": 5000},
                     account_cash=20000, rules={"max_order_usd": 2000, "max_position_pct": 100})
    assert r["verdict"] == "BLOCK"
    assert any("over max_order_usd" in reason for reason in r["reasons"])


def test_position_cap_blocks_oversized_concentration():
    r = check_order({"symbol": "AAPL", "side": "buy", "notional": 3000},
                     account_cash=10000, rules={"max_position_pct": 25, "max_order_usd": 10000})
    assert r["verdict"] == "BLOCK"
    assert any("position:" in reason for reason in r["reasons"])


def test_buy_dipping_into_cash_buffer_blocks_without_margin():
    r = check_order({"symbol": "AAPL", "side": "buy", "notional": 9500},
                     account_cash=10000, rules={"cash_buffer_pct": 10, "max_order_usd": 10000, "max_position_pct": 100})
    assert r["verdict"] == "BLOCK"
    assert any("cash:" in reason for reason in r["reasons"])


def test_buy_dipping_into_buffer_warns_not_blocks_when_margin_allowed():
    r = check_order({"symbol": "AAPL", "side": "buy", "notional": 9500},
                     account_cash=10000,
                     rules={"cash_buffer_pct": 10, "max_order_usd": 10000, "max_position_pct": 100, "allow_margin": True})
    assert r["verdict"] == "PASS"
    assert any("margin" in w for w in r["warnings"])


def test_sell_more_than_held_blocks_without_allow_short():
    r = check_order({"symbol": "AAPL", "side": "sell", "qty": 10},
                     account_cash=10000, account_shares={"AAPL": 5}, account_prices={"AAPL": 150})
    assert r["verdict"] == "BLOCK"
    assert any("short:" in reason for reason in r["reasons"])


def test_sell_more_than_held_passes_with_allow_short():
    r = check_order({"symbol": "AAPL", "side": "sell", "qty": 10},
                     account_cash=10000, account_shares={"AAPL": 5}, account_prices={"AAPL": 150},
                     rules={"allow_short": True, "max_order_usd": 10000})
    assert r["verdict"] == "PASS"


def test_selling_exactly_what_is_held_passes():
    r = check_order({"symbol": "AAPL", "side": "sell", "qty": 5},
                     account_cash=10000, account_shares={"AAPL": 5}, account_prices={"AAPL": 150})
    assert r["verdict"] == "PASS"


def test_missing_price_degrades_to_warning_not_silent_pass_of_unchecked_rules():
    r = check_order({"symbol": "AAPL", "side": "buy", "qty": 10}, account_cash=10000, account_prices={})
    assert r["verdict"] == "PASS"  # no reasons to block, since size/position/cash couldn't be evaluated
    assert any("no price" in w for w in r["warnings"])
