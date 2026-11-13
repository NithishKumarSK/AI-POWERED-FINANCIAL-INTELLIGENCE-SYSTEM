"""
Breadth Chart Analyst, adapted from claude-trading-skills'
`breadth-chart-analyst` skill (vendor/claude-trading-skills/skills/
breadth-chart-analyst/SKILL.md). MIT License, Copyright (c) 2026
TraderMonty.

CSV-data-only mode (the source skill's own documented PRIMARY,
MANDATORY-first path -- "CSV data is the PRIMARY source for all Breadth
values... OpenCV image detection is fragile"). Reuses
core/market_breadth_service.py's already-fetched `breadth_200ma`/
`breadth_8ma` (Chart 1: the S&P 500 Breadth Index) and `uptrend_ratio`/
`uptrend_trend` (Chart 2: Uptrend Stock Ratio) -- no new data source,
just the signal-detection layer this skill's own strategy adds on top.

SCOPE REDUCTION, disclosed: the chart-IMAGE analysis path (two-stage
full-chart + right-edge-crop OpenCV/vision reading) is NOT ported. The
source skill's own documentation calls image analysis "SUPPLEMENTARY
only" and CSV data "the authoritative source for all subsequent
analysis" -- this project has no vision pipeline for TraderMonty's
specific dashboard chart images (its existing chart_rendering.py renders
this project's own price charts for Gemini, a different image
entirely), so building a fragile, untestable OpenCV/vision reader for
someone else's chart images would be a worse outcome than the honestly-
narrower CSV-only path the source skill itself prefers.

Faithfully ported thresholds (from SKILL.md's "Key Elements" and
"Expected Output" sections): 73% = Chart 1 overheating/peak-sell zone,
23% = Chart 1 extreme-oversold/trough-buy zone, 60% = Chart 1 "healthy"
floor; 10% = Chart 2 extreme-oversold bottom, 40% = Chart 2 overheating
top.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def classify_200ma_zone(value: float) -> str:
    if value >= 73:
        return "overheating_peak_zone"
    if value <= 23:
        return "extreme_oversold_trough_zone"
    if value >= 60:
        return "healthy"
    return "neutral"


def classify_8ma_zone(value: float) -> str:
    if value >= 73:
        return "overheating"
    if value <= 23:
        return "extreme_oversold"
    if 60 <= value < 73:
        return "healthy_bullish"
    return "neutral"


def detect_dead_cross(breadth_8ma: float, breadth_200ma: float) -> Dict[str, Any]:
    """8MA below 200MA = dead cross (bearish), per SKILL.md's "Dead Cross
    status determined (8MA < 200MA = dead cross)" validation step."""
    gap_pct = breadth_8ma - breadth_200ma
    return {"dead_cross": gap_pct < 0, "gap_pct": round(gap_pct, 2)}


def detect_local_trough(series: List[float]) -> bool:
    """True when the second-to-last point is a local minimum that the
    series has just turned up from -- the "8MA reverses from a trough" BUY
    trigger. Needs at least 3 points."""
    if len(series) < 3:
        return False
    prev, trough, latest = series[-3], series[-2], series[-1]
    return trough <= prev and latest > trough


def detect_local_peak(series: List[float]) -> bool:
    """True when the second-to-last point is a local maximum the series has
    just turned down from -- the "200MA forms a peak" SELL trigger."""
    if len(series) < 3:
        return False
    prev, peak, latest = series[-3], series[-2], series[-1]
    return peak >= prev and latest < peak


def classify_uptrend_zone(ratio_pct: float) -> str:
    if ratio_pct <= 10:
        return "extreme_oversold_bottom"
    if ratio_pct <= 15:
        return "near_bottom"
    if ratio_pct >= 40:
        return "overheating_top"
    if ratio_pct >= 35:
        return "near_top"
    return "neutral"


def uptrend_color(trend: Optional[str]) -> str:
    """GREEN/RED/NEUTRAL, derived from the feed's own trend direction --
    per SKILL.md's own definition ("Green Regions: Market in uptrend
    phase; Red Regions: downtrend phase"), not a separate raw CSV field
    (the live feed has no color column, confirmed this session)."""
    t = (trend or "").strip().lower()
    if t == "up":
        return "GREEN"
    if t == "down":
        return "RED"
    return "NEUTRAL"


def detect_color_transition(trend_series: List[Optional[str]]) -> Optional[str]:
    """'RED_TO_GREEN' (enter long) / 'GREEN_TO_RED' (exit long) / None."""
    if len(trend_series) < 2:
        return None
    prev_color = uptrend_color(trend_series[-2])
    curr_color = uptrend_color(trend_series[-1])
    if prev_color == "RED" and curr_color == "GREEN":
        return "RED_TO_GREEN"
    if prev_color == "GREEN" and curr_color == "RED":
        return "GREEN_TO_RED"
    return None


def analyze_breadth_charts(
    breadth_200ma_series: List[float],
    breadth_8ma_series: List[float],
    uptrend_ratio_series: List[float],
    uptrend_trend_series: List[Optional[str]],
) -> Dict[str, Any]:
    """Combines Chart 1 (strategic, 200MA-based) and Chart 2 (tactical,
    uptrend ratio) signals, per SKILL.md's "Dual-Timeframe Analysis"
    principle. Every series is oldest -> newest, most-recent value last."""
    latest_200ma = breadth_200ma_series[-1]
    latest_8ma = breadth_8ma_series[-1]
    latest_uptrend_ratio = uptrend_ratio_series[-1]
    latest_trend = uptrend_trend_series[-1]

    dead_cross = detect_dead_cross(latest_8ma, latest_200ma)
    trough_reversal = detect_local_trough(breadth_8ma_series)
    peak_formation = detect_local_peak(breadth_200ma_series)
    color_transition = detect_color_transition(uptrend_trend_series)

    chart1_signal = "NONE"
    if trough_reversal and classify_8ma_zone(breadth_8ma_series[-2]) == "extreme_oversold":
        chart1_signal = "BUY"
    elif peak_formation and classify_200ma_zone(breadth_200ma_series[-2]) == "overheating_peak_zone":
        chart1_signal = "SELL"

    chart2_signal = "NONE"
    if color_transition == "RED_TO_GREEN" and classify_uptrend_zone(uptrend_ratio_series[-2]) in ("extreme_oversold_bottom", "near_bottom"):
        chart2_signal = "ENTER_LONG"
    elif color_transition == "GREEN_TO_RED" and classify_uptrend_zone(uptrend_ratio_series[-2]) in ("overheating_top", "near_top"):
        chart2_signal = "EXIT_LONG"

    return {
        "schema_version": "1.0",
        "chart1_strategic": {
            "breadth_200ma": latest_200ma, "breadth_8ma": latest_8ma,
            "zone_200ma": classify_200ma_zone(latest_200ma), "zone_8ma": classify_8ma_zone(latest_8ma),
            "dead_cross": dead_cross, "trough_reversal": trough_reversal, "peak_formation": peak_formation,
            "signal": chart1_signal,
        },
        "chart2_tactical": {
            "uptrend_ratio": latest_uptrend_ratio, "trend": latest_trend,
            "color": uptrend_color(latest_trend), "zone": classify_uptrend_zone(latest_uptrend_ratio),
            "color_transition": color_transition, "signal": chart2_signal,
        },
        "combined_outlook": (
            "BULLISH" if chart1_signal == "BUY" or chart2_signal == "ENTER_LONG"
            else "BEARISH" if chart1_signal == "SELL" or chart2_signal == "EXIT_LONG"
            else "NEUTRAL"
        ),
    }
