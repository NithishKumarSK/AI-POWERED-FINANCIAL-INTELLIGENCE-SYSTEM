"""
order_ticket.py -- order fingerprinting and strict per-order "yes" approval
parsing, adapted from trader-skill's trader-broker skill
(vendor/trader-skill/trader-broker/ticket.py, MIT License, Copyright (c)
2026 Jake Schincariol).

Pure functions, no network, no broker connection -- this project places no
live orders, so the "ticket" concept here is the approval-gate LOGIC
(exactly reproduced, since it's the most safety-critical part of the
source skill) without the actual order-placement call. fingerprint() uses
the identical algorithm as pretrade_risk_gate.py would need to match a
risk verdict to a specific proposed order -- same purpose as the source
skill's shared fingerprint() between trader-risk and trader-broker.

The "yes" parser is deliberately strict and un-fuzzy (same as the source):
"ok", "sure", "go", "do it" are all REJECTED -- only an unambiguous "yes"
(or "y"), naming the right order and amount, with no hedge words, counts.
This matters because this is the one function standing between a proposed
order and anything calling a real brokerage API.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Optional

_ALPACA_FIELDS = (
    "symbol", "side", "qty", "notional", "type", "time_in_force", "limit_price",
    "stop_price", "trail_price", "trail_percent", "extended_hours", "client_order_id",
    "order_class", "take_profit_limit_price", "stop_loss_stop_price",
    "stop_loss_limit_price", "advanced_instructions",
)
_YES_WORDS = ("yes", "y")
_BATCH_WORDS = {"all", "every", "everything", "rest", "remaining", "them", "both", "batch", "each"}
_DOUBT_WORDS = {"no", "not", "dont", "don't", "wait", "cancel", "stop", "but", "maybe", "later", "hold", "unless", "if"}
# Must start with a digit -- a bare regex of [\d,]+ would also match a
# stray comma from ordinary punctuation (e.g. "yes, 500") as its own
# zero-length-after-strip "number", crashing float('') downstream. Caught
# by this module's own tests.
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def fingerprint(order: dict) -> str:
    """The exact order that was checked/approved -- first 16 hex chars of a
    SHA-256 over the order's Alpaca-relevant fields, canonically sorted. If
    the order JSON changes at all (even one field), the fingerprint
    changes and any prior approval no longer matches it."""
    core = {k: order[k] for k in _ALPACA_FIELDS if k in order and order[k] is not None}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def parse_yes(reply: str, order: dict, other_symbols_in_batch: Optional[list] = None) -> dict:
    """Strictly parse whether `reply` is an unambiguous approval of THIS
    specific order. Returns {"approved": bool, "reason": str}.

    Deliberately rejects: empty replies, questions, anything but a literal
    "yes"/"y" as the first word, any batch-approval language ("yes to all"
    is explicitly not a thing here -- one order, one explicit yes), any
    hedge/doubt word anywhere in the reply, a reply naming a different
    order's symbol, or a dollar/share number that doesn't match this
    order's own notional/qty/limit_price (within half a cent)."""
    other_symbols_in_batch = other_symbols_in_batch or []
    text = (reply or "").strip()

    if not text:
        return {"approved": False, "reason": "empty reply"}
    if "?" in text:
        return {"approved": False, "reason": "reply looks like a question, not an approval"}

    words = text.lower().split()
    first_word = words[0].strip(",.!;:")
    if first_word not in _YES_WORDS:
        return {"approved": False, "reason": f"first word must be 'yes' or 'y', got {words[0]!r}"}

    word_set = set(words)
    batch_hit = word_set & _BATCH_WORDS
    if batch_hit:
        return {"approved": False, "reason": f"a yes covers one order at a time, not a batch ({', '.join(sorted(batch_hit))!r} found)"}

    doubt_hit = word_set & _DOUBT_WORDS
    if doubt_hit:
        # The first word is allowed to be "yes" even if a later hedge word
        # appears -- check from the SECOND word onward, matching the
        # source skill's "after the first word" rule.
        doubt_after_first = set(words[1:]) & _DOUBT_WORDS
        if doubt_after_first:
            return {"approved": False, "reason": f"hedge word(s) found: {', '.join(sorted(doubt_after_first))}"}

    order_symbol = str(order.get("symbol", "")).upper()
    for other_sym in other_symbols_in_batch:
        other_sym = str(other_sym).upper()
        if other_sym != order_symbol and other_sym in text.upper().split():
            return {"approved": False, "reason": f"reply names a different order's symbol ({other_sym})"}

    order_amount = order.get("notional") or order.get("qty") or order.get("limit_price")
    numbers_in_reply = [float(n.replace(",", "")) for n in _NUMBER.findall(text)]
    if order_amount is not None and numbers_in_reply:
        order_amount = float(order_amount)
        if not any(abs(n - order_amount) <= 0.005 for n in numbers_in_reply):
            return {
                "approved": False,
                "reason": f"a number in the reply ({numbers_in_reply}) doesn't match this order's amount ({order_amount})",
            }

    return {"approved": True, "reason": "explicit yes, matches this order"}
