"""
SPX Last-10-Session Support/Resistance
Finds swing highs/lows within just the last 10 trading sessions and
narrates what price actually did right after touching each one -- the
freshest, most-relevant levels for planning tomorrow's session.
"""
from __future__ import annotations

from typing import Dict, List


def _local_extrema(bars: List[Dict]) -> List[Dict]:
    """A bar's high/low counts as a swing point if it's the highest/lowest
    among itself and its immediate neighbors -- a short-window version of
    the fractal detection used for the longer timeframes elsewhere."""
    n = len(bars)
    points: List[Dict] = []
    for i in range(1, n - 1):
        h, l = bars[i]["high"], bars[i]["low"]
        if h >= bars[i - 1]["high"] and h >= bars[i + 1]["high"]:
            points.append({"type": "high", "level": h, "date": bars[i]["date"], "index": i})
        if l <= bars[i - 1]["low"] and l <= bars[i + 1]["low"]:
            points.append({"type": "low", "level": l, "date": bars[i]["date"], "index": i})
    return points


def build_recent_session_levels(bars: List[Dict], lookback: int = 10) -> Dict:
    window = bars[-lookback:]
    if len(window) < 3:
        return {"lookback": lookback, "date_range": None, "levels": []}

    points = _local_extrema(window)
    levels: List[Dict] = []

    for p in points:
        idx = p["index"]
        after = window[idx + 1:]
        if after:
            follow_close = after[min(2, len(after) - 1)]["close"]
            move = round(follow_close - p["level"], 1)
            if p["type"] == "high":
                if move < 0:
                    action = (
                        f"Swing high on {p['date']} at {p['level']:,.0f} -- price pulled back "
                        f"{abs(move):,.0f} pts to {follow_close:,.0f} within the next few sessions. Held as resistance."
                    )
                else:
                    action = (
                        f"Swing high on {p['date']} at {p['level']:,.0f} -- price kept pushing higher "
                        f"afterward. Broken through, not a lasting top."
                    )
            else:
                if move > 0:
                    action = (
                        f"Swing low on {p['date']} at {p['level']:,.0f} -- price bounced "
                        f"{abs(move):,.0f} pts to {follow_close:,.0f} within the next few sessions. Held as support."
                    )
                else:
                    action = (
                        f"Swing low on {p['date']} at {p['level']:,.0f} -- price kept falling afterward. "
                        f"Broken through, not a lasting bottom."
                    )
        else:
            action = f"Formed on {p['date']} at {p['level']:,.0f} -- too recent to know how it plays out yet."

        levels.append({
            "level": round(p["level"], 2),
            "kind": "resistance" if p["type"] == "high" else "support",
            "date": p["date"],
            "action": action,
        })

    levels.sort(key=lambda l: l["date"])
    deduped: List[Dict] = []
    for lv in levels:
        if deduped and abs(deduped[-1]["level"] - lv["level"]) < 3:
            deduped[-1] = lv
            continue
        deduped.append(lv)
    deduped.sort(key=lambda l: -l["level"])

    return {
        "lookback": lookback,
        "date_range": (window[0]["date"], window[-1]["date"]),
        "levels": deduped,
    }
