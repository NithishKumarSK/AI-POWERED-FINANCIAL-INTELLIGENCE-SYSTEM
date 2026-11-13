"""
day_by_day_path_predictor.py -- Research Expansion Program: a real,
deterministic day-by-day predicted-price path across a prediction's full
horizon, requested specifically to support options entry/exit timing
(core/options_path_evaluator.py uses this).

Honesty note on what this IS and ISN'T: this project has two pieces of
real, backtested evidence --
  (1) the TERMINAL predicted_return_pct from the Gemini consensus call
      (direction/magnitude at the full horizon), and
  (2) the terminal low/high BAND (ATR_daily_pct x sqrt(horizon_days)),
      independently measured at 79.9% real containment across 304 cases
      this session (core/conformal_range_calibrator.py).
Neither of those is a day-by-day forecast. This module INTERPOLATES
between day 0 (origin_price, known) and day horizon_days (the terminal
prediction above) using the same sqrt-of-time scaling already used for the
terminal band -- a standard, defensible random-walk assumption, not a
fresh AI guess per day. It is NOT separately validated at each
intermediate day; only the two endpoints it connects have real backtested
numbers behind them. This is disclosed in the returned dict's own
"methodology_note" field so no caller can present it as something it isn't.
"""
from __future__ import annotations

import math
from typing import List, Optional


def predict_daily_path(
    origin_price: float,
    predicted_return_pct: float,
    horizon_days: int,
    atr_daily_pct: Optional[float] = None,
) -> dict:
    """
    Returns:
        {"path": [{"day_offset", "predicted_price", "predicted_return_pct",
                   "predicted_low_price", "predicted_high_price"}, ...],
         "methodology_note": str}
    path has one entry per day_offset from 1 to horizon_days inclusive.
    day_offset == horizon_days reproduces predicted_return_pct exactly
    (the real terminal prediction); earlier days are the sqrt-time
    interpolation described in the module docstring.
    """
    if origin_price is None or origin_price <= 0 or horizon_days is None or horizon_days < 1:
        return {"path": [], "methodology_note": "Invalid origin_price or horizon_days"}

    path = []
    for d in range(1, horizon_days + 1):
        frac = d / horizon_days
        cum_return_pct = round(predicted_return_pct * math.sqrt(frac), 4)
        central_price = round(origin_price * (1 + cum_return_pct / 100.0), 4)

        band_pct = round(atr_daily_pct * math.sqrt(d), 4) if atr_daily_pct else None
        low_price = round(origin_price * (1 + (cum_return_pct - band_pct) / 100.0), 4) if band_pct is not None else None
        high_price = round(origin_price * (1 + (cum_return_pct + band_pct) / 100.0), 4) if band_pct is not None else None

        path.append({
            "day_offset": d,
            "predicted_price": central_price,
            "predicted_return_pct": cum_return_pct,
            "predicted_low_price": low_price,
            "predicted_high_price": high_price,
        })

    return {
        "path": path,
        "methodology_note": (
            "Interpolated between the known origin price (day 0) and the real, "
            "AI-predicted terminal return (day " + str(horizon_days) + ") using "
            "sqrt-of-time scaling -- the same scaling already used for this "
            "project's independently-measured 79.9% range-containment rate. "
            "Only the two endpoints have real backtested accuracy numbers; the "
            "days in between are a deterministic formula, not a fresh AI "
            "forecast per day."
        ),
    }


def best_entry_exit_days(path: List[dict], bullish: bool = True) -> dict:
    """From a predicted price path, find the best (lowest-price) day to buy
    and the best (highest-price) day AFTER it to sell, for a bullish view
    (buy low, sell high). bullish=False inverts this (sell high first, buy
    back low later -- for a bearish/short view). Pure price-path logic, no
    options math -- see options_path_evaluator.py for the options version."""
    if not path:
        return {"entry_day": None, "exit_day": None, "note": "Empty path"}

    if bullish:
        entry = min(path, key=lambda p: p["predicted_price"])
        after = [p for p in path if p["day_offset"] > entry["day_offset"]]
        exit_ = max(after, key=lambda p: p["predicted_price"]) if after else None
    else:
        entry = max(path, key=lambda p: p["predicted_price"])
        after = [p for p in path if p["day_offset"] > entry["day_offset"]]
        exit_ = min(after, key=lambda p: p["predicted_price"]) if after else None

    return {
        "entry_day": entry["day_offset"],
        "entry_price": entry["predicted_price"],
        "exit_day": exit_["day_offset"] if exit_ else None,
        "exit_price": exit_["predicted_price"] if exit_ else None,
        "note": "No day after entry to exit on" if not exit_ else "",
    }
