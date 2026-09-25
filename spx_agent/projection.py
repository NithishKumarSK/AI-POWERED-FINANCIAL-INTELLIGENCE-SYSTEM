"""
SPX Next-Session Projection
A statistical (not guaranteed) read on the next trading day: an expected
high/low band in points, and a directional lean (green/red) derived from
technicals + recent momentum + monthly seasonality. This is a
historical-pattern lean, not a forecast guarantee -- SPX can gap or trend
beyond this band on news/macro events.
"""
from __future__ import annotations

from statistics import mean, median
from typing import Dict, List

FIXED_BAND_POINTS = 40.0


def _daily_point_changes(bars: List[Dict]) -> List[float]:
    return [bars[i]["close"] - bars[i - 1]["close"] for i in range(1, len(bars))]


def _daily_ranges(bars: List[Dict]) -> List[float]:
    return [b["high"] - b["low"] for b in bars]


def project_next_session(bars: List[Dict], technicals: Dict, seasonality: Dict, symbol: str = "SPX") -> Dict:
    last = bars[-1]
    last_close = last["close"]

    recent_60 = bars[-60:] if len(bars) >= 60 else bars
    ranges_60 = _daily_ranges(recent_60)
    changes_60 = _daily_point_changes(recent_60)

    atr = technicals["atr14"] or 0.0
    median_range = median(ranges_60) if ranges_60 else 0.0
    avg_abs_change = mean(abs(c) for c in changes_60) if changes_60 else 0.0

    expected_move_pts = round((atr + median_range) / 2, 1)

    up_days = sum(1 for c in changes_60 if c > 0)
    recent_up_pct = round(up_days / len(changes_60) * 100, 0) if changes_60 else None

    score = technicals["bias_score"]

    current_month_stats = seasonality.get("current_month_stats")
    month_win_rate = current_month_stats["win_rate_pct"] if current_month_stats else None
    if month_win_rate is not None:
        if month_win_rate >= 60:
            score += 1
        elif month_win_rate <= 40:
            score -= 1

    if score >= 3:
        lean = "Green (bullish lean)"
    elif score <= -3:
        lean = "Red (bearish lean)"
    elif score > 0:
        lean = "Slight green lean"
    elif score < 0:
        lean = "Slight red lean"
    else:
        lean = "Coin-flip / no clear lean"

    return {
        "as_of_date": last["date"],
        "as_of_close": last_close,
        "expected_move_points": expected_move_pts,
        "projected_high": round(last_close + expected_move_pts, 2),
        "projected_low": round(last_close - expected_move_pts, 2),
        "fixed_band_points": FIXED_BAND_POINTS,
        "fixed_band_high": round(last_close + FIXED_BAND_POINTS, 2),
        "fixed_band_low": round(last_close - FIXED_BAND_POINTS, 2),
        "atr14_points": atr,
        "median_60d_range_points": round(median_range, 1),
        "avg_abs_daily_change_60d_points": round(avg_abs_change, 1),
        "recent_60d_up_day_pct": recent_up_pct,
        "directional_lean": lean,
        "lean_score": score,
        "caveat": (
            "Statistical read from historical price patterns, not a guarantee. "
            f"{symbol} can gap or trend beyond this band on news/macro events."
        ),
    }
