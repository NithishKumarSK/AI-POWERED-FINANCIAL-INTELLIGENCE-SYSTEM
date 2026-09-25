"""
SPX Gamma Exposure (GEX)
Estimates dealer gamma exposure per strike from the live ^SPX options chain
(open interest + implied volatility, fetched via yfinance) and Black-Scholes
gamma (SPX options are European-style and cash-settled, so Black-Scholes
applies cleanly -- no early-exercise premium to worry about).

Surfaces:
  - the strikes with the largest positive/negative net GEX (candidate
    pin/support-resistance zones)
  - the "zero-gamma flip" level, where cumulative GEX crosses from positive
    to negative -- a widely-watched volatility-regime marker (positive GEX
    regimes tend to suppress/dampen moves; negative GEX regimes amplify them)

IMPORTANT ASSUMPTION: open interest alone doesn't reveal which side of a
contract dealers are actually on. This module follows the standard public
convention used by most retail GEX trackers -- call open interest
contributes positive gamma exposure, put open interest contributes
negative -- which is a simplifying assumption, not an observed fact.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Dict, List

CONTRACT_MULTIPLIER = 100
DEFAULT_RISK_FREE_RATE = 0.045
YF_TICKER = "^SPX"
MAX_DAYS_OUT = 35  # near-term dailies/weeklies plus the next monthly OpEx
FLIP_BAND_PCT = 0.15  # restrict zero-gamma flip search to spot +/-15% -- far-OTM,
# near-zero-OI strikes otherwise produce spurious sign flips that have nothing
# to do with the actual near-the-money gamma regime


def _bs_gamma(spot: float, strike: float, t_years: float, iv: float, r: float = DEFAULT_RISK_FREE_RATE) -> float:
    if t_years <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    try:
        d1 = (math.log(spot / strike) + (r + 0.5 * iv ** 2) * t_years) / (iv * math.sqrt(t_years))
        pdf = math.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi)
        return pdf / (spot * iv * math.sqrt(t_years))
    except (ValueError, ZeroDivisionError, OverflowError):
        return 0.0


def fetch_gex_snapshot(spot: float, max_days_out: int = MAX_DAYS_OUT) -> Dict:
    import yfinance as yf

    ticker = yf.Ticker(YF_TICKER)
    all_expirations = ticker.options
    if not all_expirations:
        raise RuntimeError(f"No options chain available for {YF_TICKER}")

    today = date.today()
    expiries_to_use = [
        e for e in all_expirations
        if 0 <= (datetime.strptime(e, "%Y-%m-%d").date() - today).days <= max_days_out
    ]
    if not expiries_to_use:
        expiries_to_use = all_expirations[:1]

    by_strike: Dict[float, Dict[str, float]] = {}
    expiries_used: List[str] = []

    for exp_str in expiries_to_use:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
        t_years = max((exp_date - today).days, 0.5) / 365.0
        try:
            chain = ticker.option_chain(exp_str)
        except Exception:
            continue
        expiries_used.append(exp_str)

        for side, df in (("call", chain.calls), ("put", chain.puts)):
            for _, row in df.iterrows():
                strike = float(row["strike"])
                oi = float(row.get("openInterest", 0) or 0)
                iv = float(row.get("impliedVolatility", 0) or 0)
                # NaN comparisons are always False, so "oi <= 0" alone won't catch a NaN
                # openInterest/impliedVolatility cell (seen in live chains for newly-listed
                # or stale contracts) -- check explicitly or it corrupts every downstream sum.
                if math.isnan(oi) or math.isnan(iv) or oi <= 0 or iv <= 0:
                    continue
                gamma = _bs_gamma(spot, strike, t_years, iv)
                dollar_gamma = gamma * oi * CONTRACT_MULTIPLIER * spot ** 2 * 0.01

                bucket = by_strike.setdefault(strike, {"call_gex": 0.0, "put_gex": 0.0, "call_oi": 0.0, "put_oi": 0.0})
                bucket[f"{side}_gex"] += dollar_gamma
                bucket[f"{side}_oi"] += oi

    rows: List[Dict] = []
    for strike, d in sorted(by_strike.items()):
        net_gex = d["call_gex"] - d["put_gex"]
        rows.append({
            "strike": strike,
            "call_gex": round(d["call_gex"], 0),
            "put_gex": round(d["put_gex"], 0),
            "net_gex": round(net_gex, 0),
            "call_oi": int(d["call_oi"]),
            "put_oi": int(d["put_oi"]),
        })

    total_gex = sum(r["net_gex"] for r in rows)

    band_rows = [r for r in rows if spot * (1 - FLIP_BAND_PCT) <= r["strike"] <= spot * (1 + FLIP_BAND_PCT)]

    flip_level = None
    cumulative = 0.0
    prev_strike = None
    prev_cumulative = 0.0
    for r in band_rows:
        cumulative += r["net_gex"]
        if prev_strike is not None and (prev_cumulative < 0) != (cumulative < 0):
            span = r["strike"] - prev_strike
            denom = cumulative - prev_cumulative
            if span > 0 and denom != 0:
                frac = -prev_cumulative / denom
                flip_level = round(prev_strike + frac * span, 1)
        prev_strike = r["strike"]
        prev_cumulative = cumulative

    top_positive = sorted(rows, key=lambda r: -r["net_gex"])[:5]
    top_negative = sorted([r for r in rows if r["net_gex"] < 0], key=lambda r: r["net_gex"])[:5]

    return {
        "spot": spot,
        "expiries_used": expiries_used,
        "max_days_out": max_days_out,
        "total_net_gex": round(total_gex, 0),
        "regime": "Positive (historically vol-suppressing / pin-prone)" if total_gex > 0 else "Negative (historically vol-amplifying)",
        "zero_gamma_flip": flip_level,
        "top_positive_gex_strikes": top_positive,
        "top_negative_gex_strikes": top_negative,
        "rows": rows,
        "assumption_note": (
            "Dealer positioning is inferred, not observed: this follows the standard public convention "
            "that call open interest contributes positive gamma exposure and put open interest contributes "
            "negative. Open interest alone doesn't reveal which side of each contract dealers are actually "
            "on, so treat this as a widely-used estimate, not a certainty."
        ),
    }
