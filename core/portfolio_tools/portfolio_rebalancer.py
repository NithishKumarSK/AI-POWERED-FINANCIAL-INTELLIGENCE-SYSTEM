"""
portfolio_rebalancer.py -- drift-based rebalancing to target weights,
adapted from trader-skill's trader-rebalance skill
(vendor/trader-skill/trader-rebalance/rebalance.py, MIT License,
Copyright (c) 2026 Jake Schincariol).

Algorithm (re-derived from the source skill's own description):
  1. Account value = cash + current holdings at market price.
  2. Target weights = the desired weights, capped/redistributed the same
     way budget_allocator.allocate_budget caps an initial allocation
     (reused directly here, not re-implemented a second time).
  3. Drift = current% - target% per ticker. Only drift beyond the band
     (default 5 points) trades -- small drift is left alone, not chased.
  4. Sells are listed before buys (frees cash first). Buys are capped to
     cash actually available above the buffer, scaled down proportionally
     if there isn't enough to fully fund every buy.
  5. Trades under min_order_usd are skipped. Trades over max_order_usd are
     capped (with a note that another rebalance run is needed to finish).
  6. Untracked holdings (not in the target weights) are left alone unless
     explicitly told to liquidate them.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from portfolio_tools.budget_allocator import allocate_budget  # noqa: E402


def plan_rebalance(
    holdings: dict,
    prices: dict,
    target_weights: dict,
    cash: float,
    cash_buffer_pct: float = 10.0,
    max_position_pct: float = 25.0,
    min_order_usd: float = 5.0,
    max_order_usd: float = 2000.0,
    drift_band_pct: float = 5.0,
    sell_untracked: bool = False,
) -> dict:
    """holdings: {"TICKER": shares}. prices: {"TICKER": price}.
    target_weights: {"TICKER": pct} for the desired portfolio (not
    necessarily summing to 100 -- renormalized the same way
    allocate_budget renormalizes over the stock sleeve).

    Returns {"orders": [{"ticker","side","dollars"}], "untracked": [...],
             "capped_orders": [...], "account_value": float}.
    orders are sells first, then buys, matching the source skill's order.
    """
    priced_holdings = {t: s * prices.get(t, 0) for t, s in holdings.items() if s > 0}
    account_value = cash + sum(priced_holdings.values())
    if account_value <= 0:
        raise ValueError("account value (cash + priced holdings) must be positive")

    # Step 2: target dollar amounts, via the same capping/redistribution
    # logic as a fresh allocation -- a rebalance target is just "what would
    # a fresh allocation of the WHOLE account value look like."
    alloc = allocate_budget(
        target_weights, budget=account_value, cash_buffer_pct=cash_buffer_pct,
        max_position_pct=max_position_pct, min_order_usd=0,  # don't drop small targets here; drift band handles that
    )
    target_dollars = alloc["allocations"]

    untracked = [t for t in holdings if t not in target_weights and holdings[t] > 0]
    if sell_untracked:
        for t in untracked:
            target_dollars.setdefault(t, 0)

    all_tickers = set(target_dollars) | set(priced_holdings)
    sells, buys = [], []
    for t in sorted(all_tickers):
        current_dollars = priced_holdings.get(t, 0)
        target = target_dollars.get(t, 0 if (t in untracked and sell_untracked) else current_dollars)
        current_pct = current_dollars / account_value * 100
        target_pct = target / account_value * 100
        drift = current_pct - target_pct
        if abs(drift) < drift_band_pct:
            continue
        diff_dollars = round(target - current_dollars, 2)
        if abs(diff_dollars) < min_order_usd:
            continue
        (buys if diff_dollars > 0 else sells).append({"ticker": t, "dollars": diff_dollars})

    # Step 4: buys capped to cash actually freed by sells + buffer-adjusted
    # starting cash, scaled down proportionally if short.
    cash_after_sells = cash + sum(-s["dollars"] for s in sells)
    buffer_floor = account_value * cash_buffer_pct / 100.0
    available_for_buys = max(0.0, cash_after_sells - buffer_floor)
    total_buy_dollars = sum(b["dollars"] for b in buys)
    scale = min(1.0, available_for_buys / total_buy_dollars) if total_buy_dollars > 0 else 1.0

    capped_orders = []
    orders = []
    for s in sells:
        orders.append({"ticker": s["ticker"], "side": "sell", "dollars": round(abs(s["dollars"]), 2)})
    for b in buys:
        dollars = round(b["dollars"] * scale, 2)
        if dollars < min_order_usd:
            continue
        if dollars > max_order_usd:
            capped_orders.append({"ticker": b["ticker"], "wanted": dollars, "capped_to": max_order_usd})
            dollars = max_order_usd
        orders.append({"ticker": b["ticker"], "side": "buy", "dollars": dollars})

    return {
        "orders": orders, "untracked": untracked if not sell_untracked else [],
        "capped_orders": capped_orders, "account_value": round(account_value, 2),
    }
