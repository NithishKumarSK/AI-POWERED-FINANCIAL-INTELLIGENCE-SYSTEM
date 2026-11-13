"""
downtrend_duration_analyzer.py -- peak-to-trough downtrend duration/depth
detection, ported from claude-trading-skills' downtrend-duration-analyzer
skill (vendor/claude-trading-skills/skills/downtrend-duration-analyzer/scripts/analyze_downtrends.py,
MIT License, Copyright (c) 2026 TraderMonty).

SCOPE REDUCTION (disclosed, not hidden): the source skill's main point is
a market-wide SURVEY across ~100-500 stocks via FMP's company-screener
endpoint, grouped by sector and market-cap tier. That endpoint is
confirmed premium-gated on the free tier (HTTP 402, same as the ETF-quote
finding in market_top_detector_service.py) -- there is no free source for
a stock universe with sector/market-cap metadata, so the sector/market-cap
survey itself could not be rebuilt. What WAS ported is the pure peak/
trough/duration detection math (detect_peaks_troughs, find_downtrends,
compute_statistics), applied per-symbol instead of across a universe --
core/downtrend_duration_service.py answers "how long and how deep have
THIS symbol's past corrections typically run", a real, narrower, but
genuinely free and leakage-safe question, not the full original scope.
group_statistics (sector/market-cap grouping) was not ported since it has
nothing to group without a universe.

Also ported without pandas/numpy (project convention: plain lists/dicts),
and chronological order (oldest-first) is used throughout, matching
historical_price_service's own native bar order -- no MRF conversion needed.
"""
from __future__ import annotations

from typing import Tuple


def detect_peaks_troughs(closes: list, window: int = 20) -> Tuple[list, list]:
    """Detect local peaks and troughs using a centered rolling window.
    closes: chronological (oldest first). Returns (peak_indices, trough_indices)."""
    n = len(closes)
    peaks = []
    troughs = []
    for i in range(window, n - window):
        win = closes[i - window : i + window + 1]
        if closes[i] == max(win):
            peaks.append(i)
        if closes[i] == min(win):
            troughs.append(i)
    return peaks, troughs


def find_downtrends(
    dates: list,
    closes: list,
    peaks: list,
    troughs: list,
    min_depth_pct: float = 5.0,
    min_duration_days: int = 3,
) -> list:
    """Identify downtrend periods from peaks to the deepest subsequent
    trough before the next peak. dates/closes: chronological (oldest first)."""
    downtrends = []

    for peak_idx in peaks:
        peak_price = closes[peak_idx]
        peak_date = dates[peak_idx]

        subsequent_troughs = [t for t in troughs if t > peak_idx]
        if not subsequent_troughs:
            continue

        next_peaks = [p for p in peaks if p > peak_idx]
        end_idx = next_peaks[0] if next_peaks else len(closes)

        valid_troughs = [t for t in subsequent_troughs if t < end_idx]
        if not valid_troughs:
            continue

        trough_idx = min(valid_troughs, key=lambda t: closes[t])
        trough_price = closes[trough_idx]
        trough_date = dates[trough_idx]

        depth_pct = (trough_price - peak_price) / peak_price * 100
        duration_days = int(trough_idx - peak_idx)

        if abs(depth_pct) < min_depth_pct:
            continue
        if duration_days < min_duration_days:
            continue

        downtrends.append({
            "peak_idx": peak_idx, "trough_idx": trough_idx,
            "peak_date": peak_date, "trough_date": trough_date,
            "peak_price": float(peak_price), "trough_price": float(trough_price),
            "duration_days": duration_days, "depth_pct": round(depth_pct, 2),
        })

    return downtrends


def compute_statistics(downtrends: list) -> dict:
    """Median/mean/percentile duration across a list of downtrend dicts."""
    if not downtrends:
        return {
            "total_downtrends": 0, "median_duration_days": 0, "mean_duration_days": 0,
            "p25_duration_days": 0, "p75_duration_days": 0, "p90_duration_days": 0,
        }

    durations = sorted(dt["duration_days"] for dt in downtrends)
    return {
        "total_downtrends": len(downtrends),
        "median_duration_days": int(_percentile(durations, 50)),
        "mean_duration_days": round(sum(durations) / len(durations), 1),
        "p25_duration_days": int(_percentile(durations, 25)),
        "p75_duration_days": int(_percentile(durations, 75)),
        "p90_duration_days": int(_percentile(durations, 90)),
    }


def _percentile(sorted_values: list, pct: float) -> float:
    """Linear-interpolation percentile (matches numpy.percentile's default)."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return float(sorted_values[f])
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)
