"""
pretrade_risk_gate.py -- PASS/BLOCK pre-trade order validation, adapted
from trader-skill's trader-risk skill (vendor/trader-skill/trader-risk/check.py,
MIT License, Copyright (c) 2026 Jake Schincariol).

Checks a proposed order (Alpaca-shaped: symbol/side/qty-or-notional/type)
against configured risk rules and the current account state. Pure function,
no network, no file I/O -- this project has no live order/portfolio
execution state, so unlike the source skill (which reads/writes
trader/orders.json, trader/portfolio.json, trader/state/broker.json), the
caller supplies account state directly and gets a verdict back.

What blocks an order (from the source skill, re-derived here):
  format    missing symbol/side, both-or-neither of qty/notional,
            unknown order type
  asset     options symbols unless allow_options; anything not a plain stock ticker
  blocked   a ticker on the blocked list
  size      under min_order_usd, over max_order_usd
  position  the stock would exceed max_position_pct of the account after this fill
  cash      the buy would dip into the cash buffer, or need margin when not allowed
  short     selling more than currently held, unless allow_short
"""
from __future__ import annotations

import re
from typing import Optional

_TICKER = re.compile(r"^[A-Z]{1,5}([.\-][A-Z]{1,2})?$")
_OCC_OPTION = re.compile(r"^[A-Z]{1,6}\d{6}[CP]\d{8}$")

DEFAULT_RULES = {
    "cash_buffer_pct": 10.0,
    "max_position_pct": 25.0,
    "max_order_usd": 2000.0,
    "min_order_usd": 5.0,
    "allow_options": False,
    "allow_margin": False,
    "allow_short": False,
    "blocked": [],
}


def check_order(
    order: dict,
    account_cash: float,
    account_shares: Optional[dict] = None,
    account_prices: Optional[dict] = None,
    rules: Optional[dict] = None,
) -> dict:
    """Returns {"verdict": "PASS"|"BLOCK", "reasons": [...], "warnings": [...]}.

    order: {"symbol": str, "side": "buy"|"sell", "qty": float|None,
            "notional": float|None, "type": "market"|..., "limit_price": float|None}
    account_shares: {"TICKER": shares_held} -- current position, if any.
    account_prices: {"TICKER": price} -- needed to value notional/qty-based
                     orders against max_position_pct; a missing price for a
                     ticker being checked degrades that one check (position/cash)
                     to a warning, not a silent pass.
    """
    r = dict(DEFAULT_RULES)
    r.update(rules or {})
    shares = account_shares or {}
    prices = {k.upper(): v for k, v in (account_prices or {}).items()}

    reasons: list = []
    warnings: list = []

    sym = str(order.get("symbol", "")).strip().upper()
    side = str(order.get("side", "")).strip().lower()
    qty = order.get("qty")
    notional = order.get("notional")
    typ = str(order.get("type", "market")).strip().lower()

    # format
    if not sym:
        reasons.append("format: no symbol")
    if side not in ("buy", "sell"):
        reasons.append(f"format: side must be buy or sell, got {order.get('side')!r}")
    if (qty is None) == (notional is None):
        reasons.append("format: give exactly one of qty or notional")
    if typ not in ("market", "limit", "stop", "stop_limit", "trailing_stop"):
        reasons.append(f"format: unknown order type {typ!r}")

    # asset
    if sym:
        if _OCC_OPTION.match(sym) and not r["allow_options"]:
            reasons.append("asset: options order blocked (allow_options is false)")
        elif not _OCC_OPTION.match(sym) and not _TICKER.match(sym):
            reasons.append(f"asset: {sym!r} is not a recognized stock/ETF ticker")

    # blocked list
    blocked = {str(b).upper() for b in r.get("blocked") or []}
    if sym in blocked:
        reasons.append(f"blocked: {sym} is on your blocked list")

    # Resolve an order value for size/position/cash checks. A missing
    # price for a notional-less qty order degrades to a warning for those
    # specific checks rather than silently skipping them.
    price = prices.get(sym)
    if notional is not None:
        value = float(notional)
    elif qty is not None and price is not None:
        value = float(qty) * price
    else:
        value = None
        if qty is not None:
            warnings.append(f"no price for {sym}: cannot evaluate size/position/cash rules for this order")

    if value is not None:
        # size
        if value < r["min_order_usd"]:
            reasons.append(f"size: ${value:,.2f} is under min_order_usd (${r['min_order_usd']:,.2f})")
        if value > r["max_order_usd"]:
            reasons.append(f"size: ${value:,.2f} is over max_order_usd (${r['max_order_usd']:,.2f})")

        account_value = account_cash + sum(
            shares.get(t, 0) * prices.get(t, 0) for t in shares
        )
        if account_value > 0:
            # position (buys only -- a sell reduces concentration, never increases it)
            if side == "buy":
                current_value = shares.get(sym, 0) * (price or 0)
                post_fill_pct = (current_value + value) / account_value * 100
                if post_fill_pct > r["max_position_pct"]:
                    reasons.append(
                        f"position: this buy would bring {sym} to {post_fill_pct:.1f}% of the "
                        f"account (max_position_pct={r['max_position_pct']}%)"
                    )

            # cash
            if side == "buy":
                buffer_floor = account_value * r["cash_buffer_pct"] / 100.0
                cash_after = account_cash - value
                if cash_after < buffer_floor:
                    if not r["allow_margin"]:
                        reasons.append(
                            f"cash: this buy would dip below the {r['cash_buffer_pct']}% cash "
                            f"buffer (needs margin, allow_margin is false)"
                        )
                    else:
                        warnings.append("cash: this buy dips into margin (allow_margin is true)")

        # short
        if side == "sell":
            held = shares.get(sym, 0)
            sell_qty = qty if qty is not None else (value / price if price else None)
            if sell_qty is not None and sell_qty > held and not r["allow_short"]:
                reasons.append(
                    f"short: selling {sell_qty:g} shares of {sym} but only {held:g} held "
                    f"(allow_short is false)"
                )

    return {"verdict": "BLOCK" if reasons else "PASS", "reasons": reasons, "warnings": warnings}
