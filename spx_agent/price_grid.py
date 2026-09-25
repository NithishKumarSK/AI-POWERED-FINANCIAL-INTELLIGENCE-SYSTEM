"""
SPX Price Grid -- Round-Number Reaction Study
Builds a fixed grid of levels at $5 increments above/below the current
price, out to +/-50 points (10 levels each side), and studies how SPX has
actually reacted each time it traded at that exact price over its 5-year
history: how many times it touched the level, whether it held (bounced
away) or broke through, and the average follow-through move 5 sessions
later.

Note: at a 5-point step, daily bars (whose average range is tens of points)
will show most levels as touched almost every time price passes through the
area -- the held/broke split is still meaningful, but "touches" here mostly
reflects "days price traded through this exact price", not discrete tests
of it as a level the way the 50+ point grid or the swing-based levels do.
"""
from __future__ import annotations

from statistics import mean
from typing import Dict, List, Optional

import pandas as pd

from spx_agent.technicals import compute_rsi

GRID_STEP_PTS = 5.0
GRID_LEVELS_PER_SIDE = 10
TOUCH_TOLERANCE_PTS = 1.0
FORWARD_DAYS = 5
MIN_GAP_DAYS = 3


def _episodes(bars: List[Dict], level: float, tolerance: float, min_gap: int) -> List[List[int]]:
    """Group consecutive/near-consecutive touching bars into one episode so
    a multi-day consolidation at a level isn't counted as many touches."""
    touch_idx = [
        i for i, b in enumerate(bars)
        if (b["low"] - tolerance) <= level <= (b["high"] + tolerance)
    ]
    episodes: List[List[int]] = []
    for idx in touch_idx:
        if episodes and idx - episodes[-1][-1] <= min_gap:
            episodes[-1].append(idx)
        else:
            episodes.append([idx])
    return episodes


def _strength_for_row(row: Dict) -> str:
    """Qualitative rank used to highlight rows in the report: 'strong' and
    'weak' need at least 2 touches to be meaningful; a single touch is
    'limited' regardless of its outcome."""
    if row["touches"] == 0:
        return "untested"
    if row["touches"] == 1:
        return "limited"
    if row["held_pct"] is not None and row["held_pct"] >= 65:
        return "strong"
    if row["broke_pct"] is not None and row["broke_pct"] >= 65:
        return "weak"
    return "mixed"


def _note_for_row(row: Dict) -> str:
    if row["touches"] == 0:
        return "No historical touches in the last 5 years -- untested/uncharted; treat as a soft reference only."
    held = row["held_pct"]
    if held is None:
        return f"Touched {row['touches']}x but the reaction was inconsistent."
    if held >= 65:
        return f"Tested {row['touches']}x, held {held:.0f}% of the time (price bounced away) -- has acted as real {row['kind']}."
    if held <= 35:
        return f"Tested {row['touches']}x, but broke through {row['broke_pct']:.0f}% of the time -- hasn't reliably held; expect it to give way rather than reverse price."
    return f"Tested {row['touches']}x with a mixed record (holds about as often as it breaks) -- a moderate, not decisive, level."


def _next_day_narrative(row: Dict, symbol: str = "SPX") -> str:
    if row["touches"] == 0:
        return "No historical touches -- no next-day precedent to draw on."

    up_pct, down_pct = row["next_day_up_pct"], row["next_day_down_pct"]
    avg_up, avg_down = row["avg_next_day_move_up_pts"], row["avg_next_day_move_down_pts"]
    rsi = row["avg_rsi_at_touch"]

    if up_pct is not None and up_pct >= down_pct:
        outcome = f"rose the next session {up_pct:.0f}% of the time (avg +{avg_up:,.1f} pts)"
    else:
        outcome = f"fell the next session {down_pct:.0f}% of the time (avg {avg_down:,.1f} pts)"

    if rsi is None:
        context = ""
    elif rsi >= 60:
        context = f" RSI was elevated (avg {rsi:.0f}) at these touches -- momentum was already stretched to the upside going in."
    elif rsi <= 40:
        context = f" RSI was depressed (avg {rsi:.0f}) at these touches -- momentum was already stretched to the downside going in."
    else:
        context = f" RSI was neutral (avg {rsi:.0f}) at these touches -- no strong momentum extreme either way."

    return f"After touching this level, {symbol} {outcome}.{context}"


def _reaction_for_level(bars: List[Dict], level: float, rsi_series: List[float]) -> Dict:
    episodes = _episodes(bars, level, TOUCH_TOLERANCE_PTS, MIN_GAP_DAYS)
    n = len(bars)

    from_below_held = from_below_broke = 0
    from_above_held = from_above_broke = 0
    forward_moves: List[float] = []
    next_day_moves: List[float] = []
    next_day_ups = next_day_downs = 0
    rsi_at_touch: List[float] = []

    for ep in episodes:
        touch_i = ep[0]
        approach_close = bars[max(0, touch_i - 3)]["close"]
        forward_i = min(touch_i + FORWARD_DAYS, n - 1)
        forward_close = bars[forward_i]["close"]
        forward_moves.append(forward_close - level)

        if approach_close < level:  # tested as resistance (approached from below)
            if forward_close > level:
                from_below_broke += 1
            else:
                from_below_held += 1
        elif approach_close > level:  # tested as support (approached from above)
            if forward_close < level:
                from_above_broke += 1
            else:
                from_above_held += 1

        touch_close = bars[touch_i]["close"]
        next_i = min(touch_i + 1, n - 1)
        next_move = round(bars[next_i]["close"] - touch_close, 1)
        next_day_moves.append(next_move)
        if next_move > 0:
            next_day_ups += 1
        elif next_move < 0:
            next_day_downs += 1

        if touch_i < len(rsi_series):
            rsi_at_touch.append(rsi_series[touch_i])

    total = len(episodes)
    held = from_below_held + from_above_held
    broke = from_below_broke + from_above_broke

    up_moves = [m for m in next_day_moves if m > 0]
    down_moves = [m for m in next_day_moves if m < 0]

    return {
        "level": round(level, 2),
        "touches": total,
        "tested_as_resistance": from_below_held + from_below_broke,
        "tested_as_support": from_above_held + from_above_broke,
        "held_pct": round(held / total * 100, 0) if total else None,
        "broke_pct": round(broke / total * 100, 0) if total else None,
        "avg_forward_5d_move_pts": round(sum(forward_moves) / len(forward_moves), 1) if forward_moves else None,
        "next_day_up_pct": round(next_day_ups / total * 100, 0) if total else None,
        "next_day_down_pct": round(next_day_downs / total * 100, 0) if total else None,
        "avg_next_day_move_up_pts": round(mean(up_moves), 1) if up_moves else None,
        "avg_next_day_move_down_pts": round(mean(down_moves), 1) if down_moves else None,
        "avg_rsi_at_touch": round(mean(rsi_at_touch)) if rsi_at_touch else None,
    }


def build_price_grid(bars: List[Dict], symbol: str = "SPX") -> Dict:
    last_close = bars[-1]["close"]
    rsi_series = compute_rsi(pd.Series([b["close"] for b in bars])).tolist()

    rows: List[Dict] = []
    for k in range(1, GRID_LEVELS_PER_SIDE + 1):
        level = round(last_close + GRID_STEP_PTS * k, 2)
        r = _reaction_for_level(bars, level, rsi_series)
        r["kind"] = "resistance"
        r["distance_pts"] = round(level - last_close, 1)
        r["note"] = _note_for_row(r)
        r["strength"] = _strength_for_row(r)
        r["next_day_note"] = _next_day_narrative(r, symbol)
        rows.append(r)
    for k in range(1, GRID_LEVELS_PER_SIDE + 1):
        level = round(last_close - GRID_STEP_PTS * k, 2)
        r = _reaction_for_level(bars, level, rsi_series)
        r["kind"] = "support"
        r["distance_pts"] = round(level - last_close, 1)
        r["note"] = _note_for_row(r)
        r["strength"] = _strength_for_row(r)
        r["next_day_note"] = _next_day_narrative(r, symbol)
        rows.append(r)

    rows.sort(key=lambda r: -r["level"])

    return {
        "step_pts": GRID_STEP_PTS,
        "levels_per_side": GRID_LEVELS_PER_SIDE,
        "last_close": last_close,
        "rows": rows,
    }
