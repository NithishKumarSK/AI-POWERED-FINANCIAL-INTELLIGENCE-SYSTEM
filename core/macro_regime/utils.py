"""
Shared utility functions for macro regime calculators -- ported verbatim
from claude-trading-skills' macro-regime-detector skill
(vendor/claude-trading-skills/skills/macro-regime-detector/scripts/calculators/utils.py,
MIT License, Copyright (c) 2026 TraderMonty). See core/macro_regime/__init__.py.
"""
from __future__ import annotations

from typing import Optional


def downsample_to_monthly(daily_history: list) -> list:
    """Downsample daily OHLCV (most recent first) to monthly (last bar seen
    per year-month, since input is most-recent-first). Returns [{'date','close'}, ...]
    most recent first."""
    if not daily_history:
        return []
    monthly = {}
    for bar in daily_history:
        date_str = bar.get("date", "")
        close = bar.get("adjClose", bar.get("close", 0))
        if not date_str or close == 0:
            continue
        ym = date_str[:7]
        if ym not in monthly:
            monthly[ym] = {"date": date_str, "close": close}
    return sorted(monthly.values(), key=lambda x: x["date"], reverse=True)


def calculate_ratio(numerator_monthly: list, denominator_monthly: list) -> list:
    """Ratio of two monthly series aligned by year-month. Returns
    [{'date','value'}, ...] most recent first."""
    denom_lookup = {bar["date"][:7]: bar["close"] for bar in denominator_monthly}
    result = []
    for bar in numerator_monthly:
        ym = bar["date"][:7]
        if ym in denom_lookup and denom_lookup[ym] != 0:
            result.append({"date": bar["date"], "value": bar["close"] / denom_lookup[ym]})
    return result


def compute_sma(values: list, period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[:period]) / period


def detect_crossover(values: list, short_period: int = 6, long_period: int = 12) -> dict:
    """SMA crossover detection between short_period and long_period, looking
    back up to 12 months for the most recent golden/death cross."""
    if len(values) < long_period + 3:
        return {"type": "none", "bars_ago": None, "gap_pct": None}

    max_lookback = min(len(values), long_period + 12)
    sma_pairs = []
    for offset in range(max_lookback - long_period + 1):
        subset = values[offset:]
        short_sma = compute_sma(subset, short_period)
        long_sma = compute_sma(subset, long_period)
        if short_sma is not None and long_sma is not None:
            sma_pairs.append((short_sma, long_sma))

    if len(sma_pairs) < 2:
        return {"type": "none", "bars_ago": None, "gap_pct": None}

    current_short, current_long = sma_pairs[0]
    gap_pct = (current_short - current_long) / current_long * 100 if current_long != 0 else 0

    for i in range(1, len(sma_pairs)):
        prev_short, prev_long = sma_pairs[i]
        curr_short, curr_long = sma_pairs[i - 1]
        if prev_short <= prev_long and curr_short > curr_long:
            return {"type": "golden_cross", "bars_ago": i - 1, "gap_pct": round(gap_pct, 3)}
        if prev_short >= prev_long and curr_short < curr_long:
            return {"type": "death_cross", "bars_ago": i - 1, "gap_pct": round(gap_pct, 3)}

    if abs(gap_pct) < 1.0:
        return {"type": "converging", "bars_ago": None, "gap_pct": round(gap_pct, 3)}
    return {"type": "none", "bars_ago": None, "gap_pct": round(gap_pct, 3)}


def compute_roc(values: list, period: int) -> Optional[float]:
    """Rate of change (%) comparing values[0] to values[period]."""
    if len(values) <= period:
        return None
    current, past = values[0], values[period]
    if past == 0:
        return None
    return (current - past) / past * 100


def compute_percentile(values: list, current: float) -> Optional[float]:
    if not values:
        return None
    below = sum(1 for v in values if v < current)
    return below / len(values) * 100


def compute_rolling_correlation(series_a: list, series_b: list, window: int) -> Optional[float]:
    if len(series_a) < window or len(series_b) < window:
        return None
    a, b = series_a[:window], series_b[:window]
    n = window
    mean_a, mean_b = sum(a) / n, sum(b) / n
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n)) / n
    std_a = (sum((x - mean_a) ** 2 for x in a) / n) ** 0.5
    std_b = (sum((x - mean_b) ** 2 for x in b) / n) ** 0.5
    if std_a == 0 or std_b == 0:
        return 0.0
    return cov / (std_a * std_b)


STALE_CROSSOVER_MONTHS = 3


def determine_direction(
    crossover: dict, roc_3m: Optional[float], positive_label: str, negative_label: str,
    neutral_label: str = "neutral",
) -> tuple:
    """(direction, momentum_qualifier). A stale (>= STALE_CROSSOVER_MONTHS
    old) crossover yields to contradicting recent momentum ("reversing")."""
    cross_type = crossover.get("type", "none")
    bars_ago = crossover.get("bars_ago")
    is_stale = bars_ago is not None and bars_ago >= STALE_CROSSOVER_MONTHS

    cross_dir = positive_label if cross_type == "golden_cross" else (negative_label if cross_type == "death_cross" else None)
    mom_dir = positive_label if (roc_3m is not None and roc_3m > 0) else (negative_label if (roc_3m is not None and roc_3m < 0) else None)

    if cross_dir:
        if is_stale and mom_dir and mom_dir != cross_dir:
            return mom_dir, "reversing"
        qualifier = "confirmed" if mom_dir == cross_dir else ("fading" if mom_dir and mom_dir != cross_dir else "N/A")
        return cross_dir, qualifier
    elif mom_dir:
        return mom_dir, "N/A"
    return neutral_label, "N/A"


def score_transition_signal(
    crossover: dict, roc_short: Optional[float], roc_long: Optional[float],
    sma_short: Optional[float], sma_long: Optional[float],
) -> int:
    """0-100: Layer 1 crossover (0-40) + Layer 2 momentum shift (0-30) +
    Layer 3 signal-alignment confirmation (0-30)."""
    score = 0
    cross_type = crossover.get("type", "none")
    bars_ago = crossover.get("bars_ago")
    gap_pct = crossover.get("gap_pct", 0) or 0

    if cross_type in ("golden_cross", "death_cross"):
        if bars_ago is not None and bars_ago <= 2:
            score += 40
        elif bars_ago is not None and bars_ago <= 5:
            score += 30
        else:
            score += 20
    elif cross_type == "converging":
        score += int(max(0, 1.0 - abs(gap_pct)) * 25)

    if roc_short is not None and roc_long is not None:
        if roc_long < 0 and roc_short > 0:
            score += int(min(abs(roc_short), 5.0) / 5.0 * 30)
        elif roc_long > 0 and roc_short < 0:
            score += int(min(abs(roc_short), 5.0) / 5.0 * 30)
        elif abs(roc_short) > 3.0:
            score += 10

    signals_aligned = 0
    if cross_type in ("golden_cross", "death_cross"):
        signals_aligned += 1
    if cross_type == "golden_cross" and roc_short is not None and roc_short > 0:
        signals_aligned += 1
    elif cross_type == "death_cross" and roc_short is not None and roc_short < 0:
        signals_aligned += 1
    if sma_short is not None and sma_long is not None and sma_long != 0:
        if abs(sma_short - sma_long) / sma_long * 100 > 0.5:
            signals_aligned += 1
    score += signals_aligned * 10

    return min(100, max(0, score))
