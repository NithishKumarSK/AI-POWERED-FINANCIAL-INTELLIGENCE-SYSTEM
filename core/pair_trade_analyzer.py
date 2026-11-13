"""
pair_trade_analyzer.py -- pairs-trading spread analysis (hedge ratio via
OLS, cointegration via ADF test, mean-reversion half-life, rolling
z-score), ported from claude-trading-skills' pair-trade-screener skill
(vendor/claude-trading-skills/skills/pair-trade-screener/scripts/analyze_spread.py,
MIT License, Copyright (c) 2026 TraderMonty).

SCOPE REDUCTION (disclosed, not hidden): the skill ships two tools --
find_pairs.py (scans an entire FMP-sector universe via `company-screener`
to DISCOVER candidate pairs) and analyze_spread.py (ANALYZES one given
pair). `company-screener` is confirmed premium-gated on the free tier
(same finding as downtrend_duration_analyzer.py/market_top_detector_service.py),
so pair DISCOVERY across a universe wasn't rebuilt. What IS ported is the
pure pair-ANALYSIS math from analyze_spread.py, applied to a caller-given
pair -- this project already knows which symbol it's predicting, so
"is there a cointegrated, mean-reverting partner for this symbol" is a
real, answerable, free question without needing to scan a universe.

Ported without pandas (plain lists, this project's own convention); the
underlying hedge-ratio regression (scipy.stats.linregress) and
cointegration/half-life tests (statsmodels) are unchanged, standard,
independently-verifiable statistical methods.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np
from scipy import stats


def calculate_hedge_ratio(prices_a: list, prices_b: list) -> dict:
    """OLS hedge ratio (beta): prices_a ~ beta * prices_b + intercept.
    Both lists must be the same length and date-aligned already."""
    if len(prices_a) != len(prices_b):
        raise ValueError("prices_a and prices_b must be the same length (date-aligned)")
    a = np.asarray(prices_a, dtype=float)
    b = np.asarray(prices_b, dtype=float)
    if len(a) < 2 or len(set(a.tolist())) < 2 or len(set(b.tolist())) < 2 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("at least two finite observations and non-constant prices are required")

    slope, intercept, r_value, _p_value, _std_err = stats.linregress(b, a)
    return {"beta": slope, "intercept": intercept, "r_value": r_value, "r_squared": r_value ** 2}


def check_cointegration(spread: list) -> Optional[dict]:
    """Augmented Dickey-Fuller test for stationarity of the spread
    (p < 0.05 -> cointegrated / mean-reverting)."""
    from statsmodels.tsa.stattools import adfuller

    try:
        result = adfuller(spread, maxlag=1, regression="c")
        return {
            "adf_statistic": result[0],
            "p_value": result[1],
            "critical_values": result[4],
            "is_cointegrated": bool(result[1] < 0.05),
        }
    except Exception:
        return None


def calculate_half_life(spread: list) -> Optional[float]:
    """Estimate mean-reversion half-life (in days) via an AR(1) fit."""
    from statsmodels.tsa.ar_model import AutoReg

    try:
        model = AutoReg(np.asarray(spread, dtype=float), lags=1)
        result = model.fit()
        phi = np.asarray(result.params)[1]
        if phi >= 1.0 or phi <= 0:
            return None
        return -math.log(2) / math.log(phi)
    except Exception:
        return None


def calculate_zscore_series(spread: list, window: int = 90) -> list:
    """Rolling z-score of the spread; first `window-1` entries are None
    (insufficient trailing data for that window), same as a pandas
    rolling().mean()/.std() would yield as NaN."""
    n = len(spread)
    out = [None] * n
    for i in range(window - 1, n):
        win = spread[i - window + 1 : i + 1]
        mean = sum(win) / window
        variance = sum((x - mean) ** 2 for x in win) / (window - 1)  # sample std, ddof=1 (pandas default)
        std = math.sqrt(variance)
        out[i] = (spread[i] - mean) / std if std > 0 else None
    return out


def analyze_pair(
    symbol_a: str,
    symbol_b: str,
    prices_a: list,
    prices_b: list,
    entry_zscore: float = 2.0,
) -> dict:
    """Full pair-analysis pipeline. prices_a/prices_b: chronological
    (oldest first), same length, date-aligned.

    Returns a dict with hedge ratio, cointegration, half-life, current
    z-score, and a trade signal ("LONG_SPREAD"/"SHORT_SPREAD"/"WAIT"/
    "NO_TRADE_NOT_COINTEGRATED").
    """
    hedge = calculate_hedge_ratio(prices_a, prices_b)
    spread = [a - hedge["beta"] * b for a, b in zip(prices_a, prices_b)]

    coint = check_cointegration(spread)
    half_life = calculate_half_life(spread)
    zscore_series = calculate_zscore_series(spread, window=min(90, max(10, len(spread) // 4)))
    current_zscore = zscore_series[-1] if zscore_series else None

    if coint is None or current_zscore is None or not math.isfinite(current_zscore):
        signal = "INSUFFICIENT_DATA"
    elif not coint["is_cointegrated"]:
        signal = "NO_TRADE_NOT_COINTEGRATED"
    elif current_zscore > entry_zscore:
        signal = "SHORT_SPREAD"  # short A, long B
    elif current_zscore < -entry_zscore:
        signal = "LONG_SPREAD"  # long A, short B
    else:
        signal = "WAIT"

    return {
        "symbol_a": symbol_a,
        "symbol_b": symbol_b,
        "hedge_ratio": hedge,
        "cointegration": coint,
        "half_life_days": half_life,
        "current_spread": spread[-1] if spread else None,
        "current_zscore": current_zscore,
        "signal": signal,
    }
