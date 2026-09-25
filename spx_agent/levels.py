"""
SPX Level Detection
Builds support/resistance levels from swing highs/lows, moving averages,
prior-period ranges, and round numbers, across multiple lookback windows
(5y / 1y / 3m / 1m / 1w) so both structural and short-term levels show up.
"""
from __future__ import annotations

from statistics import mean
from typing import Dict, List, Optional


def _swing_points(bars: List[Dict], window: int = 3) -> Dict[str, List[float]]:
    """Fractal swing highs/lows: a bar's high/low that is the max/min among
    `window` bars on each side of it."""
    highs, lows = [], []
    n = len(bars)
    for i in range(window, n - window):
        seg = bars[i - window:i + window + 1]
        h, l = bars[i]["high"], bars[i]["low"]
        if h == max(b["high"] for b in seg):
            highs.append(h)
        if l == min(b["low"] for b in seg):
            lows.append(l)
    return {"highs": highs, "lows": lows}


def _sma(closes: List[float], window: int) -> Optional[float]:
    if len(closes) < window:
        return None
    return mean(closes[-window:])


def _round_levels(price: float, step: float = 25.0, span: int = 3) -> List[float]:
    base = round(price / step) * step
    return [base + i * step for i in range(-span, span + 1)]


def build_levels(bars: List[Dict]) -> Dict:
    """bars must be sorted ascending by date, already filtered to <= today."""
    closes = [b["close"] for b in bars]
    last = bars[-1]
    last_close = last["close"]

    windows = {
        "5y": bars,
        "1y": bars[-252:],
        "3m": bars[-63:],
        "1m": bars[-21:],
        "1w": bars[-5:],
    }

    swing_levels = {}
    for label, wbars in windows.items():
        if not wbars:
            swing_levels[label] = {"highs": [], "lows": []}
            continue
        if len(wbars) < 9:
            # Too few bars for fractal detection -- fall back to the plain
            # window high/low as a single level each.
            swing_levels[label] = {
                "highs": [round(max(b["high"] for b in wbars), 2)],
                "lows": [round(min(b["low"] for b in wbars), 2)],
            }
            continue
        sw = _swing_points(wbars, window=3)
        swing_levels[label] = {
            "highs": sorted({round(h, 2) for h in sw["highs"]}, reverse=True)[:5],
            "lows": sorted({round(l, 2) for l in sw["lows"]})[:5],
        }

    moving_averages = {
        "sma20": _sma(closes, 20),
        "sma50": _sma(closes, 50),
        "sma100": _sma(closes, 100),
        "sma200": _sma(closes, 200),
    }

    prior_day = bars[-2] if len(bars) >= 2 else last
    prior_week_bars = bars[-6:-1] if len(bars) >= 6 else bars[:-1] or bars
    prior_month_bars = bars[-22:-1] if len(bars) >= 22 else bars[:-1] or bars

    return {
        "as_of": last["date"],
        "last_close": last_close,
        "swing_levels": swing_levels,
        "moving_averages": {k: (round(v, 2) if v is not None else None) for k, v in moving_averages.items()},
        "round_number_levels": _round_levels(last_close),
        "prior_day": {"high": prior_day["high"], "low": prior_day["low"], "close": prior_day["close"]},
        "prior_week": {
            "high": max(b["high"] for b in prior_week_bars),
            "low": min(b["low"] for b in prior_week_bars),
        },
        "prior_month": {
            "high": max(b["high"] for b in prior_month_bars),
            "low": min(b["low"] for b in prior_month_bars),
        },
        "range_5y": {"high": max(b["high"] for b in bars), "low": min(b["low"] for b in bars)},
    }
