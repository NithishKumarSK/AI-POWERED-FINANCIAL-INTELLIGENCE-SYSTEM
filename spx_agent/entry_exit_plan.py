"""
Entry & Exit Level Plan
Turns the levels/volatility/tomorrow's-projection already computed
elsewhere into a concrete long and short trade structure: entry, two
targets, and a stop.

  - Entry: nearest support (long) / resistance (short) -- the realistic
    trigger price.
  - Target 1 ("near-term"): the requested point target, capped at the next
    real structural level (swing high/low, prior week/month extreme, or
    intraday confluence zone) if that's closer -- a sensible place to take
    partial profit.
  - Target 2 ("tomorrow's swing"): tomorrow's statistically projected
    high/low (from the same ATR/recent-range projection used elsewhere in
    the report) -- where price could reasonably extend to if the move
    continues past Target 1.
  - Stop: ATR-based distance beyond entry.

The side matching tomorrow's statistical directional lean is flagged
"primary"; the other is "counter-trend" (a reversal play, lower
conviction). This is a mechanical translation of existing levels into a
trade structure, not a new prediction -- confirm with actual price action
before acting on it, and the stop is a hard risk limit, not a suggestion.
"""
from __future__ import annotations

from typing import Dict, List, Optional

DEFAULT_TARGET_POINTS = 30.0
STOP_ATR_FRACTION = 0.5  # stop = 0.5x ATR(14) beyond entry, floored by a fraction of the target
MIN_CAP_DISTANCE_PTS = 10.0  # ignore candidate levels closer than this to entry -- too close to be a
# meaningful barrier, and without this floor, the always-on 5-point price grid or noise near entry
# would collapse every target down to a few points


def _nearest_level_beyond(candidates: List[float], entry: float, direction: str,
                           min_distance: float = MIN_CAP_DISTANCE_PTS) -> Optional[float]:
    """direction='up' -> nearest level far enough above entry; 'down' -> nearest level far enough below."""
    if direction == "up":
        above = [lv for lv in candidates if lv - entry >= min_distance]
        return min(above) if above else None
    below = [lv for lv in candidates if entry - lv >= min_distance]
    return max(below) if below else None


def _collect_structural_levels(levels: Dict, intraday: Optional[Dict]) -> List[float]:
    """Genuine structural levels only -- swing highs/lows, prior week/month
    extremes, and intraday confluence zones. Deliberately excludes the
    price_grid: that's an always-on $5-spaced statistical grid, not a set
    of real barriers, and would otherwise cap every target down to a few
    points just by construction."""
    out: List[float] = []
    for tf_data in levels.get("swing_levels", {}).values():
        out.extend(tf_data.get("highs", []))
        out.extend(tf_data.get("lows", []))
    for key in ("prior_week", "prior_month"):
        for side in ("high", "low"):
            v = levels.get(key, {}).get(side)
            if v is not None:
                out.append(v)
    if intraday:
        for z in intraday.get("resistance_zones", []):
            out.append(z["level"])
        for z in intraday.get("support_zones", []):
            out.append(z["level"])
    return out


def _quality_note(rr: Optional[float], capped: bool) -> str:
    if rr is None:
        return ""
    if rr < 0.75:
        return (
            "Poor reward:risk to Target 1 -- the nearest support/resistance are too close together for a "
            "clean move there. Target 2 (tomorrow's projected extreme) is the more realistic objective if "
            "this side plays out."
            if capped else
            "Poor reward:risk given current volatility -- consider tightening the stop or waiting for a "
            "clearer setup."
        )
    if rr < 1.5:
        return "Modest reward:risk to Target 1 -- workable, but not a high-conviction setup on its own."
    return "Solid reward:risk to Target 1."


def build_entry_exit_plan(levels: Dict, technicals: Dict, intraday: Optional[Dict], projection: Dict,
                           target_points: float = DEFAULT_TARGET_POINTS, symbol: str = "ES",
                           point_value_note: Optional[str] = None) -> Dict:
    atr = technicals.get("atr14") or 0.0
    stop_distance = round(max(atr * STOP_ATR_FRACTION, target_points * 0.4), 1)

    support = intraday["nearest_support"] if intraday else levels["prior_day"]["low"]
    resistance = intraday["nearest_resistance"] if intraday else levels["prior_day"]["high"]
    level_source = "Nearest 15-min confluence" if intraday else "Prior day"

    structural_levels = _collect_structural_levels(levels, intraday)
    lean_score = projection.get("lean_score", 0)
    long_primary = lean_score > 0
    short_primary = lean_score < 0

    # LONG: enter near support, target up, stop below entry.
    long_entry = support
    long_raw_target1 = long_entry + target_points
    long_capped = _nearest_level_beyond(structural_levels, long_entry, "up")
    long_target1 = min(long_raw_target1, long_capped) if long_capped else long_raw_target1
    long_target2 = max(long_target1, projection["projected_high"])
    long_stop = round(long_entry - stop_distance, 1)
    long_reward1 = round(long_target1 - long_entry, 1)
    long_reward2 = round(long_target2 - long_entry, 1)
    long_risk = round(long_entry - long_stop, 1)

    # SHORT: enter near resistance, target down, stop above entry.
    short_entry = resistance
    short_raw_target1 = short_entry - target_points
    short_capped = _nearest_level_beyond(structural_levels, short_entry, "down")
    short_target1 = max(short_raw_target1, short_capped) if short_capped else short_raw_target1
    short_target2 = min(short_target1, projection["projected_low"])
    short_stop = round(short_entry + stop_distance, 1)
    short_reward1 = round(short_entry - short_target1, 1)
    short_reward2 = round(short_entry - short_target2, 1)
    short_risk = round(short_stop - short_entry, 1)

    long_rr1 = round(long_reward1 / long_risk, 2) if long_risk else None
    long_rr2 = round(long_reward2 / long_risk, 2) if long_risk else None
    short_rr1 = round(short_reward1 / short_risk, 2) if short_risk else None
    short_rr2 = round(short_reward2 / short_risk, 2) if short_risk else None

    return {
        "target_points_requested": target_points,
        "stop_distance_pts": stop_distance,
        "point_value_note": point_value_note,
        "lean_note": (
            f"Tomorrow's statistical lean is {projection['directional_lean']} -- LONG is flagged primary."
            if long_primary else
            f"Tomorrow's statistical lean is {projection['directional_lean']} -- SHORT is flagged primary."
            if short_primary else
            f"Tomorrow's statistical lean is {projection['directional_lean']} -- no side favored, both are equal-weight."
        ),
        "long": {
            "primary": long_primary,
            "entry": round(long_entry, 2),
            "entry_reason": f"{level_source} support",
            "target1": round(long_target1, 2),
            "target1_reason": (
                f"Capped at the next real structural level above entry ({long_capped:,.0f}) rather than "
                f"the full +{target_points:.0f}-pt request"
                if long_capped and long_capped < long_raw_target1
                else f"Requested +{target_points:.0f}-point target (no closer structural level in the way)"
            ),
            "target2": round(long_target2, 2),
            "target2_reason": "Tomorrow's statistically projected high -- the extended objective if the move continues past Target 1.",
            "stop": long_stop,
            "reward1_pts": long_reward1,
            "reward2_pts": long_reward2,
            "risk_pts": long_risk,
            "reward_risk_ratio": long_rr1,
            "reward_risk_ratio2": long_rr2,
            "quality_note": _quality_note(long_rr1, bool(long_capped and long_capped < long_raw_target1)),
        },
        "short": {
            "primary": short_primary,
            "entry": round(short_entry, 2),
            "entry_reason": f"{level_source} resistance",
            "target1": round(short_target1, 2),
            "target1_reason": (
                f"Capped at the next real structural level below entry ({short_capped:,.0f}) rather than "
                f"the full -{target_points:.0f}-pt request"
                if short_capped and short_capped > short_raw_target1
                else f"Requested -{target_points:.0f}-point target (no closer structural level in the way)"
            ),
            "target2": round(short_target2, 2),
            "target2_reason": "Tomorrow's statistically projected low -- the extended objective if the move continues past Target 1.",
            "stop": short_stop,
            "reward1_pts": short_reward1,
            "reward2_pts": short_reward2,
            "risk_pts": short_risk,
            "reward_risk_ratio": short_rr1,
            "reward_risk_ratio2": short_rr2,
            "quality_note": _quality_note(short_rr1, bool(short_capped and short_capped > short_raw_target1)),
        },
        "caveat": (
            f"Mechanical translation of the levels above into a {symbol} trade structure -- confirm with "
            f"live price action (does it actually hold/reject at the entry level?) before acting, and "
            f"treat the stop as a hard risk limit, not a suggestion."
        ),
    }
