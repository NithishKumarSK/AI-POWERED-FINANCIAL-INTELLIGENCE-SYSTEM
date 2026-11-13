"""
tax_lot_optimizer.py -- cost-basis lot selection, gain/loss, and wash-sale
checking, adapted from trader-skill's trader-tax skill
(vendor/trader-skill/trader-tax/lots.py, MIT License, Copyright (c) 2026
Jake Schincariol).

Pure functions, no network, no file I/O -- this project has no live
portfolio-lot tracking, so the caller supplies lots directly rather than
reading trader/portfolio.json as the source skill does.

Not tax advice (same explicit disclaimer the source skill carries): this
can't see other accounts, IRAs, or a spouse's separate holdings, and tax
rules vary by jurisdiction and situation.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

LONG_TERM_DAYS = 365
WASH_SALE_WINDOW_DAYS = 30


def family(ticker: str) -> str:
    """Treats same-issuer share classes (GOOG/GOOGL, BRK.A/BRK.B) as one
    family for wash-sale purposes -- a loss on GOOGL followed by a buy of
    GOOG within the window is still a wash sale. Adapted from the source
    skill's own family() function."""
    t = ticker.upper().split(".")[0].split("-")[0]
    # Known share-class families (same list this project already vendors
    # in core/well_known_13f_filers.json's sibling, share_classes.json --
    # kept small/explicit here rather than importing that unrelated file).
    pairs = {"GOOGL": "GOOG", "GOOG": "GOOG", "BRK.A": "BRK", "BRK.B": "BRK",
             "BRK": "BRK", "FOXA": "FOX", "FOX": "FOX"}
    return pairs.get(ticker.upper(), t)


def term(acquired_date: str, sale_date: str) -> str:
    """"long" if held > LONG_TERM_DAYS, else "short"."""
    held_days = (_dt.date.fromisoformat(sale_date) - _dt.date.fromisoformat(acquired_date)).days
    return "long" if held_days > LONG_TERM_DAYS else "short"


def pick_lots(lots: list, shares_to_sell: float, method: str = "fifo") -> list:
    """Select which lots to sell from, in order, to cover shares_to_sell.

    lots: [{"id", "date", "shares", "cost"}] (cost = total basis for that lot).
    method: "fifo" (oldest first), "hifo" (highest cost-per-share first, to
    minimize taxable gain / maximize harvestable loss).

    Returns a list of {"id", "date", "shares_sold", "cost_basis_sold"}
    entries, partial-filling the last lot if needed. Raises ValueError if
    there aren't enough shares across all lots."""
    if shares_to_sell <= 0:
        raise ValueError("shares_to_sell must be positive")
    total_available = sum(l["shares"] for l in lots)
    if shares_to_sell > total_available + 1e-9:
        raise ValueError(f"only {total_available:g} shares available, cannot sell {shares_to_sell:g}")

    if method == "fifo":
        ordered = sorted(lots, key=lambda l: l["date"])
    elif method == "hifo":
        ordered = sorted(lots, key=lambda l: -(l["cost"] / l["shares"] if l["shares"] else 0))
    else:
        raise ValueError(f"unknown method {method!r} -- use 'fifo' or 'hifo'")

    remaining = shares_to_sell
    out = []
    for lot in ordered:
        if remaining <= 1e-9:
            break
        take = min(lot["shares"], remaining)
        cost_per_share = lot["cost"] / lot["shares"] if lot["shares"] else 0
        out.append({
            "id": lot.get("id"), "date": lot["date"],
            "shares_sold": take, "cost_basis_sold": round(take * cost_per_share, 2),
        })
        remaining -= take
    return out


def simulate_sale(picked_lots: list, sale_price: float, sale_date: str) -> dict:
    """Gain/loss and term breakdown for a set of picked lots sold at
    sale_price on sale_date. Returns {"proceeds", "cost_basis", "gain_loss",
    "long_term_gain_loss", "short_term_gain_loss"}."""
    proceeds = sum(l["shares_sold"] for l in picked_lots) * sale_price
    cost_basis = sum(l["cost_basis_sold"] for l in picked_lots)
    gain_loss = round(proceeds - cost_basis, 2)

    long_gl, short_gl = 0.0, 0.0
    for l in picked_lots:
        lot_proceeds = l["shares_sold"] * sale_price
        lot_gl = lot_proceeds - l["cost_basis_sold"]
        if term(l["date"], sale_date) == "long":
            long_gl += lot_gl
        else:
            short_gl += lot_gl

    return {
        "proceeds": round(proceeds, 2), "cost_basis": round(cost_basis, 2),
        "gain_loss": gain_loss,
        "long_term_gain_loss": round(long_gl, 2), "short_term_gain_loss": round(short_gl, 2),
    }


def check_wash_sale(ticker: str, loss_sale_date: str, other_transactions: list) -> dict:
    """Checks whether a loss sale is disallowed under the wash-sale rule:
    buying the same security (or a same-family share class) within 30 days
    before or after the loss sale.

    other_transactions: [{"ticker", "date", "side": "buy"|"sell"}, ...] --
    held lots' acquisition dates, planned future buys, or other logged
    transactions to check against.

    Returns {"disallowed": bool, "triggering_transactions": [...]}."""
    sale_dt = _dt.date.fromisoformat(loss_sale_date)
    window_start = sale_dt - _dt.timedelta(days=WASH_SALE_WINDOW_DAYS)
    window_end = sale_dt + _dt.timedelta(days=WASH_SALE_WINDOW_DAYS)
    fam = family(ticker)

    triggers = []
    for txn in other_transactions:
        if txn.get("side") != "buy":
            continue
        if family(txn.get("ticker", "")) != fam:
            continue
        try:
            txn_date = _dt.date.fromisoformat(txn["date"])
        except (KeyError, ValueError):
            continue
        if window_start <= txn_date <= window_end and txn_date != sale_dt:
            triggers.append(txn)

    return {"disallowed": bool(triggers), "triggering_transactions": triggers}


def find_harvest_candidates(
    positions: list, prices: dict, min_loss_usd: float = 0.0, min_loss_pct: float = 0.0,
) -> list:
    """Scan positions for unrealized-loss harvesting candidates.

    positions: [{"ticker", "lots": [{"id","date","shares","cost"}]}].
    prices: {"ticker": current_price}.

    Returns candidates sorted by largest loss first:
        [{"ticker", "unrealized_loss", "unrealized_loss_pct", "shares", "cost_basis"}]
    Positions with no price available are skipped, not silently assumed
    at-cost (that would hide a real gain or loss)."""
    out = []
    for pos in positions:
        ticker = pos["ticker"]
        price = prices.get(ticker.upper())
        if price is None:
            continue
        shares = sum(l["shares"] for l in pos.get("lots", []))
        cost_basis = sum(l["cost"] for l in pos.get("lots", []))
        if shares <= 0 or cost_basis <= 0:
            continue
        market_value = shares * price
        loss = round(market_value - cost_basis, 2)
        loss_pct = round(loss / cost_basis * 100, 2)
        if loss < 0 and abs(loss) >= min_loss_usd and abs(loss_pct) >= min_loss_pct:
            out.append({
                "ticker": ticker, "shares": shares, "cost_basis": round(cost_basis, 2),
                "market_value": round(market_value, 2),
                "unrealized_loss": loss, "unrealized_loss_pct": loss_pct,
            })
    out.sort(key=lambda c: c["unrealized_loss"])  # most negative (biggest loss) first
    return out
