"""Tests for core/portfolio_tools/order_ticket.py -- the approval-gate
logic standing between a proposed order and anything calling a real
brokerage API, so this is tested deliberately thoroughly."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from portfolio_tools.order_ticket import fingerprint, parse_yes


# ── fingerprint ───────────────────────────────────────────────────────────

def test_fingerprint_identical_orders_match():
    order = {"symbol": "AAPL", "side": "buy", "notional": 500, "type": "market", "time_in_force": "day"}
    assert fingerprint(dict(order)) == fingerprint(order)


def test_fingerprint_changes_if_any_field_changes():
    order1 = {"symbol": "AAPL", "side": "buy", "notional": 500}
    order2 = {"symbol": "AAPL", "side": "buy", "notional": 501}
    assert fingerprint(order1) != fingerprint(order2)


def test_fingerprint_ignores_non_alpaca_fields():
    order1 = {"symbol": "AAPL", "side": "buy", "notional": 500, "reasoning": "A"}
    order2 = {"symbol": "AAPL", "side": "buy", "notional": 500, "reasoning": "B"}
    assert fingerprint(order1) == fingerprint(order2)


def test_fingerprint_ignores_key_order():
    order1 = {"symbol": "AAPL", "side": "buy", "notional": 500}
    order2 = {"notional": 500, "side": "buy", "symbol": "AAPL"}
    assert fingerprint(order1) == fingerprint(order2)


# ── parse_yes: approvals ────────────────────────────────────────────────

def test_plain_yes_approves():
    order = {"symbol": "AAPL", "side": "buy", "notional": 500}
    assert parse_yes("yes", order)["approved"] is True


def test_y_approves():
    order = {"symbol": "AAPL", "side": "buy", "notional": 500}
    assert parse_yes("y", order)["approved"] is True


def test_yes_with_matching_amount_approves():
    order = {"symbol": "AAPL", "side": "buy", "notional": 500}
    assert parse_yes("yes, 500", order)["approved"] is True


def test_case_insensitive_yes():
    order = {"symbol": "AAPL", "side": "buy", "notional": 500}
    assert parse_yes("YES", order)["approved"] is True


# ── parse_yes: rejections ────────────────────────────────────────────────

def test_empty_reply_rejected():
    order = {"symbol": "AAPL", "side": "buy", "notional": 500}
    assert parse_yes("", order)["approved"] is False


def test_question_rejected():
    order = {"symbol": "AAPL", "side": "buy", "notional": 500}
    assert parse_yes("yes, is that right?", order)["approved"] is False


def test_ok_sure_go_do_it_all_rejected():
    order = {"symbol": "AAPL", "side": "buy", "notional": 500}
    for reply in ("ok", "sure", "go", "do it"):
        r = parse_yes(reply, order)
        assert r["approved"] is False, f"{reply!r} should have been rejected"


def test_batch_words_rejected():
    order = {"symbol": "AAPL", "side": "buy", "notional": 500}
    for reply in ("yes to all", "yes, everything", "yes both", "yes batch"):
        assert parse_yes(reply, order)["approved"] is False


def test_doubt_words_after_yes_rejected():
    order = {"symbol": "AAPL", "side": "buy", "notional": 500}
    for reply in ("yes but wait", "yes, unless the price changes", "yes maybe"):
        assert parse_yes(reply, order)["approved"] is False


def test_wrong_symbol_in_batch_rejected():
    order = {"symbol": "AAPL", "side": "buy", "notional": 500}
    r = parse_yes("yes MSFT", order, other_symbols_in_batch=["MSFT"])
    assert r["approved"] is False
    assert "MSFT" in r["reason"]


def test_mismatched_amount_rejected():
    order = {"symbol": "AAPL", "side": "buy", "notional": 500}
    r = parse_yes("yes, 999", order)
    assert r["approved"] is False


def test_order_with_no_amount_field_skips_amount_check():
    order = {"symbol": "AAPL", "side": "sell", "qty": None, "notional": None}
    # No notional/qty/limit_price on the order -- amount check can't apply,
    # a plain "yes" with no numbers should still be approved.
    assert parse_yes("yes", order)["approved"] is True
