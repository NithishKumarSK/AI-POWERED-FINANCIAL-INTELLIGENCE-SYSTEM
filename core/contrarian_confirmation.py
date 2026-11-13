"""
Contrarian Confirmation Mode (Shapiro Step 3), adapted from claude-
trading-skills' `technical-analyst` skill's data-driven fallback,
`scripts/check_weekly_price_action.py` (vendor/claude-trading-skills/
skills/technical-analyst/, references/contrarian-confirmation-
checklist.md). MIT License, Copyright (c) 2026 TraderMonty.

Pure calculation over weekly-resampled OHLC bars: three signal checks
(weekly key reversal, failed extreme, failed breakout), a continuation
veto that always wins over a triggered signal, 5-week-fractal swing
levels for a stop reference, and a CONFIRMED/NOT_CONFIRMED/
INSUFFICIENT_DATA verdict with HIGH/MEDIUM confidence -- every rule
(window terminology, strict-inequality discipline, the "FAILURE week,
not the breakout week" invariant on failed_breakout, the continuation
veto's "scan starts the week after the signal" rule, the confidence-HIGH
two-condition test) ported directly from the reference doc's word-for-
word definitions, not reinterpreted.

SCOPE REDUCTION, disclosed: `--detector-json` (Mode B, consuming a
`cot-contrarian-detector` report for the crowd direction) is not
ported -- that upstream skill needs FMP Premium+ COT data this project
doesn't have (see vendor/README.md). Only the explicit-direction path
is built, mirroring the same Mode-A-only reduction already applied to
`futures-position-sizer`. Chart-mode (reading a user-supplied chart
image) is also not ported -- same "CSV/data primary, image path not
built" reasoning used throughout this project; the data-driven script
mode is the part with real, testable logic.

Direction convention, applied via mirroring (CROWDED_SHORT bars have
high/low swapped and price-negated before running the CROWDED_LONG
logic, then negated back): every internal function below is written
once, assuming CROWDED_LONG, per the reference doc's own "every rule
below is stated for CROWDED_LONG; swap high<->low and above<->below for
CROWDED_SHORT" instruction.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

DEFAULT_SWING_LOOKBACK_WEEKS = 13
DEFAULT_EXTREME_LOOKBACK_WEEKS = 52
DEFAULT_SIGNAL_RECENCY_WEEKS = 4
DEFAULT_MIN_WEEKS = 30
MAX_FAILED_BREAKOUT_WEEKS = 3


def _mirror_bars(bars: List[Dict[str, Any]], direction: str) -> List[Dict[str, Any]]:
    if direction == "CROWDED_LONG":
        return bars
    return [{"week_of": b["week_of"], "high": -b["low"], "low": -b["high"], "close": -b["close"]} for b in bars]


def _unmirror_price(price: Optional[float], direction: str) -> Optional[float]:
    if price is None or direction == "CROWDED_LONG":
        return price
    return -price


def _max_high_window(bars: List[Dict[str, Any]], end_idx: int, window: int) -> List[Dict[str, Any]]:
    """Prior completed weeks strictly before end_idx, up to `window` of them."""
    return bars[max(0, end_idx - window):end_idx]


def check_weekly_key_reversal(bars: List[Dict[str, Any]], i: int, swing_lookback: int, extreme_lookback: int) -> Optional[Dict[str, Any]]:
    swing_window = _max_high_window(bars, i, swing_lookback)
    if not swing_window or i == 0:
        return None
    evaluated = bars[i]
    prior_swing_high = max(b["high"] for b in swing_window)
    if not (evaluated["high"] > prior_swing_high):
        return None
    prior_week_low = bars[i - 1]["low"]
    if not (evaluated["close"] < prior_week_low):
        return None

    extreme_window = _max_high_window(bars, i, extreme_lookback)
    extreme_window_weeks_used = len(extreme_window)
    is_full_window_extreme = bool(
        extreme_window_weeks_used >= extreme_lookback and extreme_window
        and evaluated["high"] > max(b["high"] for b in extreme_window)
    )
    return {
        "triggered": True, "week_of": evaluated["week_of"],
        "swing_window_weeks_used": len(swing_window), "extreme_window_weeks_used": extreme_window_weeks_used,
        "is_full_window_extreme": is_full_window_extreme,
        "detail": f"New {len(swing_window)}-week high {evaluated['high']:.4f} followed by a close {evaluated['close']:.4f} below the prior week's low {prior_week_low:.4f}",
    }


def check_failed_extreme(bars: List[Dict[str, Any]], i: int, extreme_lookback: int) -> Optional[Dict[str, Any]]:
    window = _max_high_window(bars, i, extreme_lookback)
    if not window:
        return None
    evaluated = bars[i]
    prior_high = max(b["high"] for b in window)
    if not (evaluated["high"] > prior_high):
        return None
    if not (evaluated["close"] < prior_high):
        return None
    return {
        "triggered": True, "attempted_level": prior_high, "week_of": evaluated["week_of"],
        "window_weeks_used": len(window),
        "detail": f"Intraweek high {evaluated['high']:.4f} poked above prior {len(window)}-week high {prior_high:.4f} but closed back below at {evaluated['close']:.4f}",
    }


def _find_failed_breakouts(bars: List[Dict[str, Any]], last_idx: int, extreme_lookback: int) -> List[Dict[str, Any]]:
    """All (breakout_week, failure_week) pairs with failure within
    MAX_FAILED_BREAKOUT_WEEKS of the breakout, only the FIRST close back
    through the level counting as that breakout's failure."""
    results = []
    for b in range(0, last_idx + 1):
        window = _max_high_window(bars, b, extreme_lookback)
        if not window:
            continue
        breakout_level = max(w["high"] for w in window)
        if not (bars[b]["close"] > breakout_level):
            continue
        for k in range(b + 1, min(b + MAX_FAILED_BREAKOUT_WEEKS, last_idx) + 1):
            if bars[k]["close"] < breakout_level:
                results.append({
                    "breakout_week": b, "failure_week": k, "breakout_level": breakout_level,
                    "window_weeks_used": len(window),
                })
                break
    return results


def check_failed_breakout_in_recency(bars: List[Dict[str, Any]], last_idx: int, recency_start: int, extreme_lookback: int) -> Optional[Dict[str, Any]]:
    candidates = [r for r in _find_failed_breakouts(bars, last_idx, extreme_lookback) if r["failure_week"] >= recency_start]
    if not candidates:
        return None
    newest = max(candidates, key=lambda r: r["failure_week"])
    failure_bar = bars[newest["failure_week"]]
    breakout_bar = bars[newest["breakout_week"]]
    return {
        "triggered": True, "breakout_level": newest["breakout_level"], "week_of": failure_bar["week_of"],
        "window_weeks_used": newest["window_weeks_used"],
        "detail": f"Closing breakout above {newest['breakout_level']:.4f} at week {breakout_bar['week_of']} failed, closing back below at week {failure_bar['week_of']}",
    }


def _is_new_closing_extreme(bars: List[Dict[str, Any]], i: int, extreme_lookback: int) -> bool:
    window = _max_high_window(bars, i, extreme_lookback)
    if not window:
        return False
    return bars[i]["close"] > max(b["close"] for b in window)


def check_continuation_veto(
    bars: List[Dict[str, Any]], last_idx: int, recency_start: int, extreme_lookback: int, newest_signal_week: Optional[int],
) -> Optional[Dict[str, Any]]:
    scan_start = (newest_signal_week + 1) if newest_signal_week is not None else recency_start
    for i in range(scan_start, last_idx + 1):
        if _is_new_closing_extreme(bars, i, extreme_lookback):
            return {"new_closing_extreme_with_crowd": True, "week_of": bars[i]["week_of"],
                    "window_weeks_used": len(_max_high_window(bars, i, extreme_lookback))}
    return None


def find_swing_levels(bars: List[Dict[str, Any]], last_idx: int, swing_lookback: int, extreme_lookback: int) -> Dict[str, Any]:
    """5-week fractal pivots within the extreme-lookback window, newest first."""
    window_start = max(0, last_idx - extreme_lookback + 1)
    swing_high = None
    swing_low = None
    for i in range(last_idx, window_start - 1, -1):
        if i - 2 < 0 or i + 2 > last_idx:
            continue
        neighborhood_highs = [bars[j]["high"] for j in (i - 2, i - 1, i + 1, i + 2)]
        neighborhood_lows = [bars[j]["low"] for j in (i - 2, i - 1, i + 1, i + 2)]
        if swing_high is None and bars[i]["high"] > max(neighborhood_highs):
            swing_high = {"price": bars[i]["high"], "week_of": bars[i]["week_of"], "fallback": False}
        if swing_low is None and bars[i]["low"] < min(neighborhood_lows):
            swing_low = {"price": bars[i]["low"], "week_of": bars[i]["week_of"], "fallback": False}
        if swing_high and swing_low:
            break

    swing_lookback_window = _max_high_window(bars, last_idx + 1, swing_lookback)
    if swing_high is None and swing_lookback_window:
        best = max(swing_lookback_window, key=lambda b: b["high"])
        swing_high = {"price": best["high"], "week_of": best["week_of"], "fallback": True}
    if swing_low is None and swing_lookback_window:
        best = min(swing_lookback_window, key=lambda b: b["low"])
        swing_low = {"price": best["low"], "week_of": best["week_of"], "fallback": True}

    return {"nearest_swing_high": swing_high, "nearest_swing_low": swing_low}


def run_contrarian_confirmation(
    weekly_bars: List[Dict[str, Any]],
    direction: str,
    swing_lookback_weeks: int = DEFAULT_SWING_LOOKBACK_WEEKS,
    extreme_lookback_weeks: int = DEFAULT_EXTREME_LOOKBACK_WEEKS,
    signal_recency_weeks: int = DEFAULT_SIGNAL_RECENCY_WEEKS,
    min_weeks: int = DEFAULT_MIN_WEEKS,
) -> Dict[str, Any]:
    """weekly_bars: completed weekly OHLC dicts, oldest -> newest, each
    {"week_of": str, "open": float, "high": float, "low": float, "close": float}.
    """
    if direction not in ("CROWDED_LONG", "CROWDED_SHORT"):
        raise ValueError(f"direction must be CROWDED_LONG or CROWDED_SHORT, got '{direction}'")

    if len(weekly_bars) < min_weeks:
        return {"schema_version": "1.0", "symbol": None, "direction": direction, "mode": "data",
                "verdict": "INSUFFICIENT_DATA", "confidence": None, "verdict_reason": "insufficient_weekly_bars",
                "checks": None, "swing_levels": None, "weekly_bars_used": len(weekly_bars)}

    bars = _mirror_bars(weekly_bars, direction)
    last_idx = len(bars) - 1
    recency_start = max(0, last_idx - signal_recency_weeks + 1)

    key_reversal_hits = [check_weekly_key_reversal(bars, i, swing_lookback_weeks, extreme_lookback_weeks) for i in range(recency_start, last_idx + 1)]
    key_reversal_hits = [h for h in key_reversal_hits if h]
    key_reversal = key_reversal_hits[-1] if key_reversal_hits else {"triggered": False}

    failed_extreme_hits = [check_failed_extreme(bars, i, extreme_lookback_weeks) for i in range(recency_start, last_idx + 1)]
    failed_extreme_hits = [h for h in failed_extreme_hits if h]
    failed_extreme = failed_extreme_hits[-1] if failed_extreme_hits else {"triggered": False}

    failed_breakout = check_failed_breakout_in_recency(bars, last_idx, recency_start, extreme_lookback_weeks) or {"triggered": False}

    signal_weeks = {}
    if key_reversal.get("triggered"):
        signal_weeks["key_reversal"] = next(i for i in range(recency_start, last_idx + 1) if bars[i]["week_of"] == key_reversal["week_of"])
    if failed_extreme.get("triggered"):
        signal_weeks["failed_extreme"] = next(i for i in range(recency_start, last_idx + 1) if bars[i]["week_of"] == failed_extreme["week_of"])
    if failed_breakout.get("triggered"):
        signal_weeks["failed_breakout"] = next(i for i in range(0, last_idx + 1) if bars[i]["week_of"] == failed_breakout["week_of"])

    newest_signal_week = max(signal_weeks.values()) if signal_weeks else None
    newest_signal_types = [k for k, v in signal_weeks.items() if v == newest_signal_week] if newest_signal_week is not None else []
    # Disambiguation priority when multiple checks trigger on the exact same
    # week (not specified by the source doc -- this project's own tie-break).
    priority = ["key_reversal", "failed_extreme", "failed_breakout"]
    verdict_reason_candidate = next((p for p in priority if p in newest_signal_types), None)

    continuation = check_continuation_veto(bars, last_idx, recency_start, extreme_lookback_weeks, newest_signal_week)

    if continuation:
        verdict, confidence, verdict_reason = "NOT_CONFIRMED", None, "continuation_intact"
    elif verdict_reason_candidate:
        verdict, verdict_reason = "CONFIRMED", verdict_reason_candidate
        distinct_types = len(signal_weeks)
        full_window_bonus = bool(key_reversal.get("triggered") and key_reversal.get("extreme_window_weeks_used", 0) >= extreme_lookback_weeks and key_reversal.get("is_full_window_extreme"))
        confidence = "HIGH" if (distinct_types >= 2 or full_window_bonus) else "MEDIUM"
    else:
        verdict, confidence, verdict_reason = "NOT_CONFIRMED", None, "no_reversal_evidence"

    swing_levels_mirrored = find_swing_levels(bars, last_idx, swing_lookback_weeks, extreme_lookback_weeks)
    nearest_swing_high = swing_levels_mirrored["nearest_swing_high"]
    nearest_swing_low = swing_levels_mirrored["nearest_swing_low"]
    if direction == "CROWDED_SHORT":
        nearest_swing_high, nearest_swing_low = nearest_swing_low, nearest_swing_high
    if nearest_swing_high:
        nearest_swing_high = {**nearest_swing_high, "price": _unmirror_price(nearest_swing_high["price"], direction)}
    if nearest_swing_low:
        nearest_swing_low = {**nearest_swing_low, "price": _unmirror_price(nearest_swing_low["price"], direction)}

    # Fade direction: CROWDED_LONG -> go short -> stop ABOVE at nearest swing high.
    # CROWDED_SHORT -> go long -> stop BELOW at nearest swing low.
    stop_reference = (nearest_swing_high or {}).get("price") if direction == "CROWDED_LONG" else (nearest_swing_low or {}).get("price")

    return {
        "schema_version": "1.0", "symbol": None, "direction": direction, "mode": "data",
        "verdict": verdict, "confidence": confidence, "verdict_reason": verdict_reason,
        "checks": {
            "weekly_key_reversal": key_reversal, "failed_extreme": failed_extreme,
            "failed_breakout": failed_breakout,
            "continuation": continuation or {"new_closing_extreme_with_crowd": False},
        },
        "swing_levels": {
            "nearest_swing_high": nearest_swing_high, "nearest_swing_low": nearest_swing_low,
            "stop_reference": stop_reference,
        },
        "weekly_bars_used": len(weekly_bars), "last_completed_week": weekly_bars[-1]["week_of"],
    }
