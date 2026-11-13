"""
Parabolic Short Screener (Phase 1), adapted from claude-trading-skills'
`parabolic-short-trade-planner` skill's `screen_parabolic.py`
(vendor/claude-trading-skills/skills/parabolic-short-trade-planner/,
references/parabolic_short_methodology.md,
references/short_invalidation_rules.md). MIT License, Copyright (c) 2026
TraderMonty.

Pure daily-bar scoring: qualifying preconditions (5-day return, MA
extension, acceleration, volume climax, liquidity), hard invalidation
rules (mode-aware), a 5-factor weighted composite (30/25/20/15/10 per
the source skill's own documented weights), and the "still in markup"
state cap.

SCOPE REDUCTION, disclosed: the source skill's internal per-factor 0-100
sub-scoring formulas are implementation details of `screen_parabolic.py`,
which this project can read for understanding but not execute (platform
guardrail) to verify a byte-for-byte reproduction against. The reference
docs only give the qualifying PRECONDITION thresholds (e.g. "5-day
return >= +30%", "volume ratio >= 1.5x") and the top-level 30/25/20/15/10
weights -- not a graded 0-100 curve within each factor. This port
therefore uses its OWN documented graduated-scoring curve (score scales
from 0 at the qualifying threshold up to 100 at ~2x the threshold,
clamped), built honestly from the real preconditions rather than guessed
internals. The qualifying preconditions and hard invalidation thresholds
themselves ARE byte-faithful to the reference docs.

Cross-sectional universe discovery (S&P 500 scan) is NOT ported -- same
scope reduction as every other skill needing FMP's premium company-
screener. This screens ONE caller-supplied symbol at a time.
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Tuple

WEIGHTS = {"ma_extension": 30, "acceleration": 25, "volume_climax": 20, "range_expansion": 15, "liquidity": 10}

MODE_PARAMS = {
    "safe_largecap": {"five_day_return_min": 30.0, "market_cap_floor": 2_000_000_000, "adv_floor": 20_000_000},
    "classic_qm": {"five_day_return_min": 100.0, "market_cap_floor": 300_000_000, "adv_floor": 5_000_000},
}


def _sma(values: List[float], window: int) -> Optional[float]:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def _atr(highs: List[float], lows: List[float], closes: List[float], window: int = 14) -> Optional[float]:
    if len(closes) < window + 1:
        return None
    trs = []
    for i in range(len(closes) - window, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    return sum(trs) / len(trs)


def _graduated_score(value: float, threshold: float, cap_multiple: float = 2.0) -> float:
    """0 at `threshold`, 100 at `threshold * cap_multiple`, clamped [0, 100].
    This project's own documented curve -- see module docstring."""
    if threshold <= 0:
        return 0.0
    span = threshold * (cap_multiple - 1)
    if span <= 0:
        return 100.0 if value >= threshold else 0.0
    return max(0.0, min(100.0, (value - threshold) / span * 100))


def calculate_ma_extension(closes: List[float], highs: Optional[List[float]] = None, lows: Optional[List[float]] = None) -> Dict[str, Any]:
    if len(closes) < 21:
        return {"qualifies": False, "score": 0.0, "pct_above_sma20": None, "atr_units_above": None}
    sma20 = _sma(closes, 20)
    atr14 = _atr(highs, lows, closes, 14) if (highs and lows) else None
    pct_above = (closes[-1] - sma20) / sma20 * 100 if sma20 else None
    atr_units = (closes[-1] - sma20) / atr14 if (atr14 and sma20) else None
    qualifies = bool(pct_above is not None and pct_above >= 25 and atr_units is not None and atr_units >= 4)
    score = (_graduated_score(pct_above, 25) + _graduated_score(atr_units, 4)) / 2 if qualifies or (pct_above and atr_units) else 0.0
    return {"qualifies": qualifies, "score": round(score, 1), "pct_above_sma20": pct_above, "atr_units_above": atr_units}


def calculate_acceleration(closes: List[float]) -> Dict[str, Any]:
    if len(closes) < 11:
        return {"qualifies": False, "score": 0.0, "consecutive_green_days": 0, "accel_ratio": None}
    daily_returns = [(closes[i] / closes[i - 1] - 1) * 100 for i in range(len(closes) - 10, len(closes))]
    consecutive_green = 0
    for ret in reversed(daily_returns):
        if ret > 0:
            consecutive_green += 1
        else:
            break
    mean_3d = statistics.mean(daily_returns[-3:])
    mean_10d = statistics.mean(daily_returns)
    accel_ratio = (mean_3d / mean_10d) if mean_10d not in (0, None) else None
    qualifies = bool(consecutive_green >= 3 and accel_ratio is not None and accel_ratio > 1.0)
    score = min(100.0, consecutive_green / 3 * 50 + (_graduated_score(accel_ratio, 1.0, cap_multiple=3.0) if accel_ratio else 0) * 0.5) if accel_ratio else 0.0
    return {"qualifies": qualifies, "score": round(score, 1), "consecutive_green_days": consecutive_green, "accel_ratio": accel_ratio}


def calculate_volume_climax(volumes: List[float]) -> Dict[str, Any]:
    if len(volumes) < 20:
        return {"qualifies": False, "score": 0.0, "volume_ratio": None}
    avg20 = _sma(volumes, 20)
    ratio = volumes[-1] / avg20 if avg20 else None
    qualifies = bool(ratio is not None and ratio >= 1.5)
    score = _graduated_score(ratio, 1.5, cap_multiple=3.0) if ratio else 0.0
    return {"qualifies": qualifies, "score": round(score, 1), "volume_ratio": ratio}


def calculate_range_expansion(highs: List[float], lows: List[float], closes: List[float]) -> Dict[str, Any]:
    if len(closes) < 21:
        return {"qualifies": False, "score": 0.0, "range_expansion_ratio": None}
    today_range = highs[-1] - lows[-1]
    avg_range_20d = sum(highs[i] - lows[i] for i in range(len(closes) - 20, len(closes))) / 20
    ratio = today_range / avg_range_20d if avg_range_20d else None
    qualifies = bool(ratio is not None and ratio >= 1.3)
    score = _graduated_score(ratio, 1.3, cap_multiple=3.0) if ratio else 0.0
    return {"qualifies": qualifies, "score": round(score, 1), "range_expansion_ratio": ratio}


def calculate_liquidity(closes: List[float], volumes: List[float], mode: str = "safe_largecap") -> Dict[str, Any]:
    if len(closes) < 20 or len(volumes) < 20:
        return {"qualifies": False, "score": 0.0, "avg_dollar_volume_20d": None}
    dollar_volumes = [closes[i] * volumes[i] for i in range(len(closes) - 20, len(closes))]
    avg_dv = sum(dollar_volumes) / 20
    floor = MODE_PARAMS[mode]["adv_floor"]
    qualifies = avg_dv >= floor
    score = _graduated_score(avg_dv, floor, cap_multiple=3.0)
    return {"qualifies": qualifies, "score": round(score, 1), "avg_dollar_volume_20d": avg_dv}


def check_hard_invalidations(
    five_day_return_pct: Optional[float],
    latest_close: float,
    market_cap: Optional[float],
    days_since_ipo_trading: Optional[int],
    earnings_within_days_forward: Optional[int],
    exclude_earnings_within_days: int,
    mode: str = "safe_largecap",
) -> Tuple[bool, List[str]]:
    params = MODE_PARAMS[mode]
    reasons = []
    if latest_close < 5.0:
        reasons.append(f"Latest close ${latest_close:.2f} below $5.00 floor")
    if market_cap is not None and market_cap < params["market_cap_floor"]:
        reasons.append(f"Market cap ${market_cap:,.0f} below {mode} floor ${params['market_cap_floor']:,.0f}")
    if days_since_ipo_trading is not None and days_since_ipo_trading < 60:
        reasons.append(f"Only {days_since_ipo_trading} trading days since IPO (< 60)")
    if earnings_within_days_forward is not None and earnings_within_days_forward <= exclude_earnings_within_days:
        reasons.append(f"Earnings in {earnings_within_days_forward} day(s) (<= {exclude_earnings_within_days}-day exclusion window)")
    return (len(reasons) > 0), reasons


def grade_from_score(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def check_state_cap(
    latest_close: float,
    latest_high: float,
    latest_low: float,
    is_fresh_52w_high: bool,
) -> Optional[str]:
    """'still_in_markup' when the candidate closed near its session high at
    a fresh 52-week high -- per parabolic_short_methodology.md's "Why state
    caps matter" section."""
    session_range = latest_high - latest_low
    close_location = (latest_close - latest_low) / session_range if session_range > 0 else 0.5
    if is_fresh_52w_high and close_location >= 0.80:
        return "still_in_markup"
    return None


def screen_symbol(
    symbol: str,
    closes: List[float],
    highs: List[float],
    lows: List[float],
    volumes: List[float],
    market_cap: Optional[float],
    days_since_ipo_trading: Optional[int],
    earnings_within_days_forward: Optional[int],
    mode: str = "safe_largecap",
    exclude_earnings_within_days: int = 2,
) -> Optional[Dict[str, Any]]:
    """Returns None (not an error) when the symbol doesn't meet the basic
    parabolic preconditions -- an honest "not a candidate," matching this
    project's convention for every other point-in-time detector."""
    if len(closes) < 21:
        return None

    five_day_return_pct = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 else None
    min_return = MODE_PARAMS[mode]["five_day_return_min"]
    if five_day_return_pct is None or five_day_return_pct < min_return:
        return None

    ma_ext = calculate_ma_extension(closes, highs, lows)
    accel = calculate_acceleration(closes)
    vol_climax = calculate_volume_climax(volumes)
    if not (ma_ext["qualifies"] and accel["qualifies"] and vol_climax["qualifies"]):
        return None

    rejected, reasons = check_hard_invalidations(
        five_day_return_pct, closes[-1], market_cap, days_since_ipo_trading,
        earnings_within_days_forward, exclude_earnings_within_days, mode,
    )
    if rejected:
        return {"symbol": symbol, "status": "REJECTED", "reasons": reasons, "five_day_return_pct": five_day_return_pct}

    range_exp = calculate_range_expansion(highs, lows, closes)
    liquidity = calculate_liquidity(closes, volumes, mode)

    components = {
        "ma_extension": ma_ext["score"], "acceleration": accel["score"], "volume_climax": vol_climax["score"],
        "range_expansion": range_exp["score"], "liquidity": liquidity["score"],
    }
    composite = sum(components[k] * WEIGHTS[k] for k in WEIGHTS) / sum(WEIGHTS.values())
    grade = grade_from_score(composite)

    fresh_52w_high = closes[-1] >= max(highs[-252:]) if len(highs) >= 1 else False
    state_cap = check_state_cap(closes[-1], highs[-1], lows[-1], fresh_52w_high)

    return {
        "symbol": symbol, "status": "CANDIDATE", "five_day_return_pct": five_day_return_pct,
        "composite_score": round(composite, 1), "grade": grade, "state_cap": state_cap,
        "components": {
            "ma_extension": ma_ext, "acceleration": accel, "volume_climax": vol_climax,
            "range_expansion": range_exp, "liquidity": liquidity,
        },
        "latest_close": closes[-1], "market_cap": market_cap,
    }
