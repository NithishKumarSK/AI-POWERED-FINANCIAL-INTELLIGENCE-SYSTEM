"""
Futures Position Sizer, adapted from claude-trading-skills'
`futures-position-sizer` skill (vendor/claude-trading-skills/skills/
futures-position-sizer/SKILL.md, references/futures-contract-specs.md).
MIT License, Copyright (c) 2026 TraderMonty.

Pure, offline risk-based contract-count sizing: direction + entry + stop
+ account risk budget -> contract count, using the source skill's own
verified 23-market contract-spec table (multiplier/tick size/tick value,
sourced from official CME/CBOT/COMEX/NYMEX/CFE/ICE rulebook pages, not
aggregator sites). No API keys, no network -- this file faithfully
reproduces the table and the sizing math; the per-row `source_url`
citations live in the reference doc this was ported from, not
duplicated here.

SCOPE REDUCTION, disclosed: only Mode A (explicit symbol/direction/
entry/stop) is ported. Mode B (gate handoff from `contrarian-setup-gate`)
is not -- that upstream skill needs FMP Premium+ COT data this project
doesn't have (see vendor/README.md's "needs infrastructure" section),
so there is no real `READY_FOR_PLAN` gate report to hand off from.

Floor, never round up -- exact by construction: contracts =
floor(risk_budget / risk_per_contract) is computed with Python's
`fractions.Fraction`, not float division, so
`contracts * risk_per_contract <= risk_budget` holds by construction,
per the source skill's own documented rationale (Guardrail 2).
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Any, Dict, Optional

# Verified 23-market core table, ported verbatim from
# references/futures-contract-specs.md's own table (official CME/CBOT/
# COMEX/NYMEX/CFE/ICE rulebook/contract-spec sources, not aggregators).
# tick_value == multiplier * tick_size for every row (asserted by this
# module's own test suite, mirroring the source skill's table-wide
# invariant check).
CONTRACT_SPECS: Dict[str, Dict[str, Any]] = {
    "ES": {"multiplier": 50,         "tick_size": 0.25,        "tick_value": 12.50,  "currency": "USD", "exchange": "CME"},
    "NQ": {"multiplier": 20,         "tick_size": 0.25,        "tick_value": 5.00,   "currency": "USD", "exchange": "CME"},
    "YM": {"multiplier": 5,          "tick_size": 1.00,        "tick_value": 5.00,   "currency": "USD", "exchange": "CBOT"},
    "QR": {"multiplier": 50,         "tick_size": 0.10,        "tick_value": 5.00,   "currency": "USD", "exchange": "CME"},
    "VX": {"multiplier": 1000,       "tick_size": 0.05,        "tick_value": 50.00,  "currency": "USD", "exchange": "CFE"},
    "ZT": {"multiplier": 2000,       "tick_size": 0.00390625,  "tick_value": 7.8125, "currency": "USD", "exchange": "CBOT"},
    "ZF": {"multiplier": 1000,       "tick_size": 0.0078125,   "tick_value": 7.8125, "currency": "USD", "exchange": "CBOT"},
    "ZN": {"multiplier": 1000,       "tick_size": 0.015625,    "tick_value": 15.625, "currency": "USD", "exchange": "CBOT"},
    "ZB": {"multiplier": 1000,       "tick_size": 0.03125,     "tick_value": 31.25,  "currency": "USD", "exchange": "CBOT"},
    "DX": {"multiplier": 1000,       "tick_size": 0.005,       "tick_value": 5.00,   "currency": "USD", "exchange": "ICE"},
    "E6": {"multiplier": 125_000,    "tick_size": 0.00005,     "tick_value": 6.25,   "currency": "USD", "exchange": "CME"},
    "J6": {"multiplier": 12_500_000, "tick_size": 0.0000005,   "tick_value": 6.25,   "currency": "USD", "exchange": "CME"},
    "B6": {"multiplier": 62_500,     "tick_size": 0.0001,      "tick_value": 6.25,   "currency": "USD", "exchange": "CME"},
    "A6": {"multiplier": 100_000,    "tick_size": 0.00005,     "tick_value": 5.00,   "currency": "USD", "exchange": "CME"},
    "D6": {"multiplier": 100_000,    "tick_size": 0.00005,     "tick_value": 5.00,   "currency": "USD", "exchange": "CME"},
    "S6": {"multiplier": 125_000,    "tick_size": 0.00005,     "tick_value": 6.25,   "currency": "USD", "exchange": "CME"},
    "GC": {"multiplier": 100,        "tick_size": 0.10,        "tick_value": 10.00,  "currency": "USD", "exchange": "COMEX"},
    "SI": {"multiplier": 5_000,      "tick_size": 0.005,       "tick_value": 25.00,  "currency": "USD", "exchange": "COMEX"},
    "HG": {"multiplier": 25_000,     "tick_size": 0.0005,      "tick_value": 12.50,  "currency": "USD", "exchange": "COMEX"},
    "PL": {"multiplier": 50,         "tick_size": 0.10,        "tick_value": 5.00,   "currency": "USD", "exchange": "NYMEX"},
    "CL": {"multiplier": 1_000,      "tick_size": 0.01,        "tick_value": 10.00,  "currency": "USD", "exchange": "NYMEX"},
    "NG": {"multiplier": 10_000,     "tick_size": 0.001,       "tick_value": 10.00,  "currency": "USD", "exchange": "NYMEX"},
    "BT": {"multiplier": 5,          "tick_size": 5.00,        "tick_value": 25.00,  "currency": "USD", "exchange": "CME"},
}

BOND_FAMILY = {"ZT", "ZF", "ZN", "ZB"}
TICK_GRID_TOLERANCE = 1e-6


def list_specs() -> Dict[str, Dict[str, Any]]:
    return CONTRACT_SPECS


def _is_on_tick_grid(price: float, tick_size: float) -> bool:
    ratio = price / tick_size
    return abs(ratio - round(ratio)) < TICK_GRID_TOLERANCE


def size_futures_position(
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    account_size: float,
    risk_pct: float = 1.0,
    fx_rate: float = 1.0,
) -> Dict[str, Any]:
    """Mode A: explicit sizing. Raises ValueError for operator-caused usage
    errors (unknown symbol, stop on the wrong side of entry, bond price off
    the 32nds/64ths tick grid) -- matching the source skill's "usage error,
    never a crash" distinction for Mode A inputs the operator typed
    directly (Guardrail 3). Returns a dict with sizing_status SIZED or
    NO_TRADE (never raises) for a well-formed but unaffordable setup.
    """
    symbol = symbol.upper()
    direction = direction.upper()
    if symbol not in CONTRACT_SPECS:
        raise ValueError(f"Unknown symbol '{symbol}' -- not in the verified 23-market core table")
    if direction not in ("LONG", "SHORT"):
        raise ValueError(f"direction must be LONG or SHORT, got '{direction}'")
    if entry <= 0 or stop <= 0 or account_size <= 0 or risk_pct <= 0:
        raise ValueError("entry, stop, account_size, and risk_pct must all be positive")

    spec = CONTRACT_SPECS[symbol]
    tick_size = spec["tick_size"]

    if symbol in BOND_FAMILY and (not _is_on_tick_grid(entry, tick_size) or not _is_on_tick_grid(stop, tick_size)):
        raise ValueError(
            f"{symbol} entry/stop is off the {tick_size} tick grid -- likely a 32nds/64ths "
            f"notation mistype (e.g. '110.16' instead of '110.50' for 110'16)"
        )

    if direction == "LONG" and stop >= entry:
        raise ValueError("LONG stop must be below entry")
    if direction == "SHORT" and stop <= entry:
        raise ValueError("SHORT stop must be above entry")

    stop_distance_points = abs(entry - stop)
    stop_distance_ticks = stop_distance_points / tick_size

    warnings = []
    if symbol not in BOND_FAMILY:
        if not _is_on_tick_grid(entry, tick_size):
            warnings.append("off_tick_grid_entry")
        if not _is_on_tick_grid(stop, tick_size):
            warnings.append("off_tick_grid_stop")

    risk_per_contract_usd = stop_distance_ticks * spec["tick_value"] * fx_rate
    risk_budget_usd = account_size * (risk_pct / 100)

    if risk_pct > 2.0:
        warnings.append("risk_pct_above_2")

    if risk_per_contract_usd <= 0:
        return {
            "schema_version": "1.0", "symbol": symbol, "direction": direction,
            "sizing_status": "NO_TRADE", "no_trade_reason": "zero_risk_per_contract",
            "entry": entry, "stop": stop, "warnings": warnings,
        }

    # Exact-rational floor -- never float division, per Guardrail 2.
    contracts_fraction = Fraction(risk_budget_usd).limit_denominator(10**9) / Fraction(risk_per_contract_usd).limit_denominator(10**9)
    contracts = math.floor(contracts_fraction)

    if contracts < 1:
        return {
            "schema_version": "1.0", "symbol": symbol, "direction": direction,
            "sizing_status": "NO_TRADE", "no_trade_reason": "risk_below_one_contract",
            "entry": entry, "stop": stop, "stop_distance_points": round(stop_distance_points, 8),
            "stop_distance_ticks": round(stop_distance_ticks, 4),
            "contract_spec": {**spec, "symbol": symbol},
            "risk_per_contract_usd": round(risk_per_contract_usd, 4),
            "risk_budget_usd": round(risk_budget_usd, 2),
            "fx_rate_used": fx_rate,
            "warnings": warnings,
        }

    total_risk_usd = contracts * risk_per_contract_usd
    return {
        "schema_version": "1.0", "symbol": symbol, "direction": direction,
        "sizing_status": "SIZED", "no_trade_reason": None,
        "entry": entry, "stop": stop, "stop_distance_points": round(stop_distance_points, 8),
        "stop_distance_ticks": round(stop_distance_ticks, 4),
        "contract_spec": {**spec, "symbol": symbol},
        "risk_per_contract_usd": round(risk_per_contract_usd, 4),
        "risk_budget_usd": round(risk_budget_usd, 2),
        "contracts": contracts,
        "total_risk_usd": round(total_risk_usd, 2),
        "risk_pct_of_account": round(total_risk_usd / account_size * 100, 4),
        "fx_rate_used": fx_rate,
        "margin_note": "Exchange margin requirements are broker/time-dependent and NOT computed here; verify initial/maintenance margin with your broker.",
        "warnings": warnings,
    }
