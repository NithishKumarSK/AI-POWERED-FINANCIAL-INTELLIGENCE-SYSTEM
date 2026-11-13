"""
budget_allocator.py -- position-sizing allocation across multiple target
weights (e.g. copying a 13F filer's portfolio), adapted from trader-skill's
trader-budget skill (vendor/trader-skill/trader-budget/size.py, MIT
License, Copyright (c) 2026 Jake Schincariol).

Algorithm (from the source skill's own description, re-derived and
independently tested here, not copy-pasted since the original needs
trader-skill's own trader/config.json + trader/targets.json file
conventions this project doesn't use):
  1. Take a cash buffer off the top.
  2. Renormalize remaining weights to sum to 100% over the stock sleeve.
  3. Cap any single position at max_position_pct; redistribute the excess
     across the other (uncapped) positions by weight, iteratively, since
     redistributing can itself push another position over the cap.
  4. Drop any resulting slice under min_order_usd; redistribute that too.
  5. Round to whole dollars, giving the rounding remainder to the single
     largest uncapped position (not split arbitrarily).
  6. Report whatever genuinely can't be placed ("left idle") honestly,
     rather than silently forcing it into an order.
"""
from __future__ import annotations

from typing import Optional


def allocate_budget(
    weights: dict,
    budget: float,
    cash_buffer_pct: float = 10.0,
    max_position_pct: float = 25.0,
    min_order_usd: float = 5.0,
) -> dict:
    """weights: {"TICKER": pct_of_total} summing to ~100 (as produced by,
    e.g., institutional_holdings_service's per-filer weights, or any other
    target-weight source). Returns dollar allocations per ticker plus the
    amount left idle and unable to be placed.

    Returns:
        {"allocations": {"TICKER": dollars, ...}, "cash_buffer": float,
         "left_idle": float, "capped_tickers": [...], "dropped_tickers": [...]}
    """
    if budget <= 0:
        raise ValueError("budget must be positive")
    if not (0 <= cash_buffer_pct < 100):
        raise ValueError("cash_buffer_pct must be in [0, 100)")
    if not (0 < max_position_pct <= 100):
        raise ValueError("max_position_pct must be in (0, 100]")
    if not weights:
        return {"allocations": {}, "cash_buffer": round(budget * cash_buffer_pct / 100, 2),
                 "left_idle": round(budget * (1 - cash_buffer_pct / 100), 2),
                 "capped_tickers": [], "dropped_tickers": []}

    cash_buffer = budget * cash_buffer_pct / 100.0
    investable = budget - cash_buffer

    # Step 2: renormalize to 100 over the stock sleeve.
    total_w = sum(weights.values())
    pct = {t: (w / total_w * 100.0) for t, w in weights.items()} if total_w else dict(weights)

    capped_tickers: list = []
    dropped_tickers: list = []
    stranded_pct = 0.0  # excess that genuinely cannot be placed anywhere without breaking the cap

    # Step 3: iteratively cap + redistribute excess by weight among the
    # still-uncapped positions, until no position remains over the cap.
    for _ in range(len(pct) + 1):  # bounded -- each iteration caps at least one more ticker
        over = {t: p for t, p in pct.items() if p > max_position_pct and t not in capped_tickers}
        if not over:
            break
        for t in over:
            capped_tickers.append(t)
        excess = sum(p - max_position_pct for p in over.values())
        for t in over:
            pct[t] = max_position_pct
        uncapped = {t: p for t, p in pct.items() if t not in capped_tickers}
        uncapped_total = sum(uncapped.values())
        if uncapped_total <= 0:
            # Every position is already at (or now hits) the cap -- this
            # excess cannot be placed anywhere without violating
            # max_position_pct for someone. Leave it idle, don't force it
            # onto an arbitrary position (that would silently blow the cap
            # it was supposed to enforce).
            stranded_pct += excess
            break
        for t in uncapped:
            pct[t] += excess * (uncapped[t] / uncapped_total)

    # Step 4: drop slices under min_order_usd, redistribute to the rest.
    for _ in range(len(pct) + 1):
        dollars = {t: investable * p / 100.0 for t, p in pct.items()}
        under = {t for t, d in dollars.items() if d < min_order_usd and t not in dropped_tickers}
        if not under:
            break
        dropped_excess = sum(pct[t] for t in under)
        for t in under:
            dropped_tickers.append(t)
            pct[t] = 0.0
        remaining = {t: p for t, p in pct.items() if t not in dropped_tickers}
        remaining_total = sum(remaining.values())
        if remaining_total <= 0:
            break
        for t in remaining:
            pct[t] += dropped_excess * (remaining[t] / remaining_total)

    # Step 5: round to whole dollars, give the remainder to the single
    # largest uncapped, non-dropped position.
    allocations = {}
    for t, p in pct.items():
        if t in dropped_tickers:
            continue
        allocations[t] = round(investable * p / 100.0)

    # Give only the small integer-rounding remainder to the largest
    # uncapped position -- never the (potentially large) stranded_pct
    # excess computed above, which must stay idle, not silently blow the
    # cap it exists to enforce.
    allocatable_pct = sum(p for t, p in pct.items() if t not in dropped_tickers)
    placed = sum(allocations.values())
    rounding_remainder = round(investable * allocatable_pct / 100.0) - placed
    if rounding_remainder and allocations:
        eligible = {t: a for t, a in allocations.items() if t not in capped_tickers} or allocations
        biggest = max(eligible, key=eligible.get)
        allocations[biggest] += rounding_remainder

    left_idle = round(investable - sum(allocations.values()), 2)

    return {
        "allocations": allocations,
        "cash_buffer": round(cash_buffer, 2),
        "left_idle": left_idle,
        "capped_tickers": capped_tickers,
        "dropped_tickers": dropped_tickers,
    }
