"""
options_path_evaluator.py -- Research Expansion Program: day-by-day options
position valuation across a predicted underlying price path, using the
real, already-tested Black-Scholes pricer (core/portfolio_tools/options_pricer.py,
ported from claude-trading-skills' options-strategy-advisor).

Reprices the option EVERY day of a day_by_day_path_predictor.py path, with
DTE shrinking day by day (real time decay, not just underlying price
movement) -- answers "which day should I buy/sell this option" for both a
new hypothetical position and an already-owned one.

Honesty notes:
  - Uses the CENTRAL predicted underlying price per day (not a Monte Carlo
    distribution) -- one path, not a probability-weighted fan. The
    day-by-day underlying path itself is an interpolation, not an
    independently-validated day-level forecast (see
    day_by_day_path_predictor.py's own methodology_note).
  - Implied volatility is approximated from this project's own
    ATR-derived annualized_volatility (feature_packet), NOT a real options
    chain's actual IV -- a real options chain was unavailable (disclosed
    in every live prediction's data_limitations field already). This is a
    real, disclosed approximation, not fabricated certainty.
  - Risk-free rate defaults to this project's own live treasury_10y_yield_pct
    feature when available, else a conservative fallback.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import bootstrap_paths
bootstrap_paths.add_module_paths()

_DEFAULT_RISK_FREE_RATE_PCT = 4.0


def evaluate_options_path(
    daily_path: List[dict],
    strike: float,
    option_type: str,
    dte_at_day0: int,
    contracts: int,
    annual_volatility_pct: float,
    premium_paid_per_share: Optional[float] = None,
    risk_free_rate_pct: float = _DEFAULT_RISK_FREE_RATE_PCT,
) -> dict:
    """
    daily_path: the "path" list from day_by_day_path_predictor.predict_daily_path.
    option_type: "call" or "put".
    dte_at_day0: real calendar days to expiration as of day_offset=0 (origin).
    premium_paid_per_share: if given (an already-owned position), computes
        P&L at each day and the best exit day. If omitted, only prices the
        option path (useful for a NEW hypothetical position's entry/exit).

    Returns {"daily_option_path": [...], "new_position_recommendation": {...},
             "existing_position_recommendation": {...} | None, "warnings": [...]}
    """
    from portfolio_tools.options_pricer import OptionPricer

    option_type = option_type.lower().strip()
    if option_type not in ("call", "put"):
        return {"status": "ERROR", "error": f"option_type must be 'call' or 'put', got {option_type!r}"}

    sigma = max(0.05, float(annual_volatility_pct) / 100.0) if annual_volatility_pct else 0.30
    r = float(risk_free_rate_pct) / 100.0

    rows = []
    warnings = []
    for day in daily_path:
        d = day["day_offset"]
        dte_remaining = dte_at_day0 - d
        if dte_remaining <= 0:
            warnings.append(f"day_offset={d} is on/after expiration (dte_at_day0={dte_at_day0}) -- skipped")
            continue
        T = dte_remaining / 365.0
        S = day["predicted_price"]
        try:
            pricer = OptionPricer(S=S, K=strike, T=T, r=r, sigma=sigma)
            value_per_share = pricer.call_price() if option_type == "call" else pricer.put_price()
        except ValueError as exc:
            warnings.append(f"day_offset={d}: {exc}")
            continue

        row = {
            "day_offset": d,
            "dte_remaining": dte_remaining,
            "predicted_underlying_price": S,
            "predicted_option_value_per_share": round(value_per_share, 4),
            "predicted_option_value_per_contract": round(value_per_share * 100, 2),
            "predicted_total_position_value": round(value_per_share * 100 * contracts, 2),
        }
        if premium_paid_per_share is not None:
            cost_basis = premium_paid_per_share * 100 * contracts
            row["predicted_pl_if_closed_this_day"] = round(row["predicted_total_position_value"] - cost_basis, 2)
        rows.append(row)

    if not rows:
        return {"status": "ERROR", "error": "No valid days to price (check dte_at_day0 vs path length)", "warnings": warnings}

    # New-position recommendation: cheapest day to enter, best later day to exit.
    best_buy = min(rows, key=lambda r: r["predicted_option_value_per_share"])
    after_buy = [r for r in rows if r["day_offset"] > best_buy["day_offset"]]
    best_sell = max(after_buy, key=lambda r: r["predicted_option_value_per_share"]) if after_buy else None

    new_position_rec = {
        "best_buy_day": best_buy["day_offset"],
        "best_buy_value_per_share": best_buy["predicted_option_value_per_share"],
        "best_sell_day": best_sell["day_offset"] if best_sell else None,
        "best_sell_value_per_share": best_sell["predicted_option_value_per_share"] if best_sell else None,
        "predicted_profit_per_share": (
            round(best_sell["predicted_option_value_per_share"] - best_buy["predicted_option_value_per_share"], 4)
            if best_sell else None
        ),
        "predicted_profit_total": (
            round((best_sell["predicted_option_value_per_share"] - best_buy["predicted_option_value_per_share"]) * 100 * contracts, 2)
            if best_sell else None
        ),
    }

    existing_position_rec = None
    if premium_paid_per_share is not None:
        best_exit = max(rows, key=lambda r: r["predicted_option_value_per_share"])
        total_cost = round(premium_paid_per_share * 100 * contracts, 2)
        existing_position_rec = {
            "premium_paid_per_share": premium_paid_per_share,
            "total_cost": total_cost,
            "best_exit_day": best_exit["day_offset"],
            "best_exit_value_per_share": best_exit["predicted_option_value_per_share"],
            "predicted_pl_at_best_exit": round(best_exit["predicted_total_position_value"] - total_cost, 2),
        }

    return {
        "status": "OK",
        "option_type": option_type,
        "strike": strike,
        "contracts": contracts,
        "dte_at_day0": dte_at_day0,
        "implied_vol_used_pct": round(sigma * 100, 2),
        "risk_free_rate_used_pct": round(r * 100, 2),
        "daily_option_path": rows,
        "new_position_recommendation": new_position_rec,
        "existing_position_recommendation": existing_position_rec,
        "warnings": warnings,
        "methodology_caveat": (
            "Implied volatility approximated from this project's own ATR-derived "
            "annualized_volatility, not a real live options chain (unavailable). "
            "Priced along one central predicted underlying path, not a probability "
            "distribution -- a real, disclosed simplification."
        ),
    }
