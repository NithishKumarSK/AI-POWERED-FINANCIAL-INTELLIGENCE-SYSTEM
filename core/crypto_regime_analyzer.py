"""
Crypto Regime Analyzer, adapted from claude-trading-skills'
`crypto-regime-analyzer` skill (vendor/claude-trading-skills/skills/
crypto-regime-analyzer/SKILL.md, references/crypto_regime_methodology.md).
MIT License, Copyright (c) 2026 TraderMonty.

6-component, 0-100 crypto market regime score (100 = risk-on) from free,
keyless CoinGecko + Binance public data. Pure calculation layer -- every
function here takes already-fetched price/dominance/funding series and
returns a component result dict; core/crypto_regime_service.py does the
live fetching (tools/coingecko_client.py, tools/binance_funding_client.py).

Faithfully ported: every threshold table, weight, and the proportional-
weight-redistribution composite rule are taken directly from the source
skill's own methodology reference, not re-derived. No scope reduction on
the component math itself -- this skill's data (CoinGecko/Binance public
endpoints) is free and fully available, unlike the FMP-premium-gated
skills elsewhere in this project.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional, Tuple

WEIGHTS = {
    "btc_trend_structure": 25,
    "alt_breadth_participation": 20,
    "btc_dominance_regime": 15,
    "perpetual_funding_regime": 15,
    "drawdown_volatility_position": 15,
    "momentum_thrust_washout": 10,
}


def _sma(values: List[float], window: int) -> Optional[float]:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def _result(score: Optional[float], signal: str, data_available: bool, **extra: Any) -> Dict[str, Any]:
    out = {"score": score, "signal": signal, "data_available": data_available}
    out.update(extra)
    return out


# ── 1. BTC Trend Structure (25%) ─────────────────────────────────────────

def btc_trend_structure(closes: List[float]) -> Dict[str, Any]:
    if len(closes) < 220:
        return _result(None, "Insufficient BTC history (need >= 220 daily closes)", False)

    price = closes[-1]
    ma50 = _sma(closes, 50)
    ma200 = _sma(closes, 200)
    ma200_prior = _sma(closes[:-20], 200)

    flat_tol = 0.001
    if abs(price - ma50) / ma50 < flat_tol and abs(price - ma200) / ma200 < flat_tol:
        base, structure = 50, "price = 50DMA = 200DMA (flat)"
    elif price > ma50 > ma200:
        base, structure = 90, "price > 50DMA > 200DMA (bull stack)"
    elif ma200 <= price <= ma50 and ma50 > ma200:
        base, structure = 65, "price between 200DMA and 50DMA, stack intact (pullback)"
    elif price < ma50 and price < ma200 and ma50 > ma200:
        base, structure = 55, "price below both, 50DMA still > 200DMA"
    elif price > ma50 and ma50 <= ma200:
        base, structure = 45, "price > 50DMA but 50DMA <= 200DMA (recovery attempt)"
    else:
        base, structure = 15, "price < 50DMA < 200DMA (bear stack)"

    if ma200_prior:
        slope_pct = (ma200 - ma200_prior) / ma200_prior
        if slope_pct > 0.002:
            modifier, slope_desc = 10, "rising"
        elif slope_pct < -0.002:
            modifier, slope_desc = -10, "falling"
        else:
            modifier, slope_desc = 0, "flat"
    else:
        modifier, slope_desc = 0, "unknown"

    score = max(0.0, min(100.0, base + modifier))
    signal = f"{structure}; 200DMA slope {slope_desc}"
    gap_pct = abs(ma50 - ma200) / ma200
    if gap_pct <= 0.015:
        signal += " (50/200DMA gap within 1.5% -- imminent cross watch)"

    return _result(score, signal, True, ma50=ma50, ma200=ma200)


# ── 2. Alt Breadth Participation (20%) ───────────────────────────────────

def alt_breadth_participation(alt_closes: Dict[str, List[float]]) -> Dict[str, Any]:
    usable = {sym: c for sym, c in alt_closes.items() if len(c) >= 200}
    skipped = [sym for sym in alt_closes if sym not in usable]
    if len(usable) < 5:
        return _result(None, f"Insufficient alt universe (need >= 5 alts with >= 200 obs, have {len(usable)})",
                        False, skipped=skipped)

    above_200 = above_50 = 0
    for closes in usable.values():
        price = closes[-1]
        if price > _sma(closes, 200):
            above_200 += 1
        if price > _sma(closes, 50):
            above_50 += 1

    n = len(usable)
    pct_200 = above_200 / n * 100
    pct_50 = above_50 / n * 100

    if pct_200 >= 80:
        base = 95
    elif pct_200 >= 65:
        base = 80
    elif pct_200 >= 50:
        base = 65
    elif pct_200 >= 35:
        base = 45
    elif pct_200 >= 20:
        base = 25
    else:
        base = 10

    gap = pct_50 - pct_200
    if gap >= 15:
        modifier, desc = 5, "fresh thrust (50DMA breadth leading)"
    elif gap <= -15:
        modifier, desc = -5, "rolling over (50DMA breadth lagging)"
    else:
        modifier, desc = 0, "breadth aligned"

    score = max(0.0, min(100.0, base + modifier))
    signal = f"{pct_200:.0f}% of alts above 200DMA, {pct_50:.0f}% above 50DMA; {desc}"
    return _result(score, signal, True, pct_above_200dma=pct_200, pct_above_50dma=pct_50, skipped=skipped)


# ── 3. BTC Dominance Regime (15%) ────────────────────────────────────────

def btc_dominance_regime(dominance_series: List[float], btc_trend_score: Optional[float]) -> Dict[str, Any]:
    if len(dominance_series) < 31 or btc_trend_score is None:
        return _result(None, "Insufficient dominance history (need >= 31 daily observations) or no BTC trend score",
                        False)

    change = dominance_series[-1] - dominance_series[-31]
    if change > 0.5:
        direction = "rising"
    elif change < -0.5:
        direction = "falling"
    else:
        direction = "flat"

    trend_up = btc_trend_score >= 60
    table = {
        (True, "falling"): (90, "Alt rotation (risk-on down the risk curve)"),
        (True, "flat"): (75, "--"),
        (True, "rising"): (65, "BTC-led, alts lagging"),
        (False, "rising"): (30, "Defensive rotation inside crypto"),
        (False, "flat"): (25, "--"),
        (False, "falling"): (10, "Indiscriminate de-risking"),
    }
    base, reading = table[(trend_up, direction)]

    modifier = 0
    last_dom = dominance_series[-1]
    if not trend_up and last_dom >= 62:
        modifier = 5
    elif trend_up and last_dom <= 40:
        modifier = -5

    score = max(0.0, min(100.0, base + modifier))
    return _result(score, f"BTC dominance {direction} ({last_dom:.1f}%); {reading}", True,
                    dominance_pct=last_dom, direction=direction)


# ── 4. Perpetual Funding Regime (15%) ────────────────────────────────────

def perpetual_funding_regime(funding: Dict[str, float]) -> Dict[str, Any]:
    if len(funding) < 2:
        return _result(None, f"Insufficient funding data (need >= 2 symbols, have {len(funding)})", False)

    avg_pct = statistics.mean(funding.values()) * 100

    if avg_pct <= -0.010:
        score, reading = 80, "Washed out (shorts pay)"
    elif avg_pct <= 0:
        score, reading = 65, "Skeptical"
    elif avg_pct <= 0.010:
        score, reading = 75, "Neutral"
    elif avg_pct <= 0.030:
        score, reading = 55, "Long leverage building"
    elif avg_pct <= 0.060:
        score, reading = 30, "Crowded longs"
    else:
        score, reading = 10, "Euphoric; liquidation-cascade risk"

    return _result(float(score), f"Avg 8h funding {avg_pct:.4f}%; {reading}", True, avg_funding_pct=avg_pct)


# ── 5. Drawdown & Volatility Position (15%) ──────────────────────────────

def _annualized_vol(closes: List[float]) -> Optional[float]:
    if len(closes) < 31:
        return None
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 30, len(closes))]
    if len(log_returns) < 2:
        return None
    return statistics.stdev(log_returns) * math.sqrt(365) * 100


def drawdown_volatility_position(closes: List[float]) -> Dict[str, Any]:
    if len(closes) < 365:
        return _result(None, "Insufficient BTC history (need >= 365 daily closes)", False)

    trailing_high = max(closes[-365:])
    current = closes[-1]
    drawdown_pct = (trailing_high - current) / trailing_high * 100

    if drawdown_pct <= 10:
        base = 90
    elif drawdown_pct <= 20:
        base = 75
    elif drawdown_pct <= 35:
        base = 55
    elif drawdown_pct <= 50:
        base = 35
    elif drawdown_pct <= 65:
        base = 20
    else:
        base = 10

    weekly_vols = []
    for offset in range(30, 365, 7):
        window = closes[-(offset + 30):len(closes) - offset] if offset > 0 else closes[-30:]
        v = _annualized_vol(window) if len(window) >= 31 else None
        if v is not None:
            weekly_vols.append(v)

    current_vol = _annualized_vol(closes)
    modifier = 0
    vol_tertile = "unknown"
    if current_vol is not None and len(weekly_vols) >= 6:
        sorted_vols = sorted(weekly_vols)
        third = max(1, len(sorted_vols) // 3)
        bottom_cutoff = sorted_vols[third - 1]
        top_cutoff = sorted_vols[-third]
        if current_vol <= bottom_cutoff:
            modifier, vol_tertile = 10, "bottom"
        elif current_vol >= top_cutoff:
            modifier, vol_tertile = -10, "top"
        else:
            modifier, vol_tertile = 0, "middle"

    score = max(0.0, min(100.0, base + modifier))
    if drawdown_pct > 65 and vol_tertile == "top":
        score = max(score, 15.0)

    signal = f"Drawdown {drawdown_pct:.1f}% from 1y high; realized vol {vol_tertile} tertile"
    return _result(score, signal, True, drawdown_pct=drawdown_pct, realized_vol_annualized_pct=current_vol)


# ── 6. Momentum Thrust / Washout (10%) ───────────────────────────────────

def momentum_thrust_washout(all_closes: Dict[str, List[float]]) -> Dict[str, Any]:
    usable = {sym: c for sym, c in all_closes.items() if len(c) >= 31}
    if len(usable) < 5:
        return _result(None, f"Insufficient universe (need >= 5 coins with >= 31 obs, have {len(usable)})", False)

    positive = sum(1 for c in usable.values() if c[-1] / c[-31] - 1 > 0)
    pct_positive = positive / len(usable) * 100

    if pct_positive >= 85:
        score, reading = 90, "Broad thrust"
    elif pct_positive >= 65:
        score, reading = 75, "Healthy participation"
    elif pct_positive >= 45:
        score, reading = 55, "Mixed"
    elif pct_positive >= 25:
        score, reading = 35, "Weak"
    elif pct_positive >= 10:
        score, reading = 20, "Broad weakness"
    else:
        score, reading = 35, "Washout (contrarian bump)"

    return _result(float(score), f"{pct_positive:.0f}% of universe positive over 30d; {reading}", True,
                    pct_positive_30d=pct_positive)


# ── Composite scorer ──────────────────────────────────────────────────────

_MIN_COMPONENTS = 4
_MIN_WEIGHT_PCT = 65


def compute_composite(component_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    present = {
        name: res for name, res in component_results.items()
        if res.get("data_available") and res.get("score") is not None and name in WEIGHTS
    }
    present_weight = sum(WEIGHTS[name] for name in present)

    if len(present) < _MIN_COMPONENTS or present_weight < _MIN_WEIGHT_PCT:
        return {
            "score": None, "zone": "UNKNOWN",
            "guidance": "Insufficient components for a reliable composite reading.",
            "effective_weights": {}, "components_used": list(present.keys()),
        }

    effective_weights = {name: WEIGHTS[name] / present_weight * 100 for name in present}
    score = sum(present[name]["score"] * effective_weights[name] for name in present) / 100

    if score >= 80:
        zone, guidance = "RISK_ON", "Broad risk-on conditions observed; review risk limits before decisions"
    elif score >= 40:
        zone, guidance = "NEUTRAL", "Mixed conditions observed; no strong regime conclusion"
    else:
        zone, guidance = "RISK_OFF", "Defensive market conditions observed; review existing risk controls"

    return {
        "score": round(score, 1), "zone": zone, "guidance": guidance,
        "effective_weights": {k: round(v, 1) for k, v in effective_weights.items()},
        "components_used": list(present.keys()),
    }
