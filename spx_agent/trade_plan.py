"""
SPX Tomorrow Trade-Plan Levels
Translates levels already computed elsewhere in the report into conditional
call/put watch-levels for the next session. This restates existing levels
as "if X breaks/holds, here's the bullish/bearish read" -- it is NOT a
recommendation to place a trade, and carries no new statistics of its own.
"""
from __future__ import annotations

from typing import Dict, Optional


def build_trade_plan(levels: Dict, projection: Dict, intraday: Optional[Dict]) -> Dict:
    pd_high, pd_low = levels["prior_day"]["high"], levels["prior_day"]["low"]

    resistance = intraday["nearest_resistance"] if intraday else pd_high
    support = intraday["nearest_support"] if intraday else pd_low
    resistance_label = "nearest 15-min confluence resistance" if intraday else "prior day high"
    support_label = "nearest 15-min confluence support" if intraday else "prior day low"

    calls_setups = [
        {
            "trigger": f"Breaks and holds above {resistance:,.0f} ({resistance_label}) for 15-30 min",
            "read": (
                f"Momentum breakout -- favors calls / long, targeting {projection['projected_high']:,.0f} "
                f"(projected high) next."
            ),
        },
        {
            "trigger": f"Pulls back to {support:,.0f} ({support_label}) and holds/reclaims",
            "read": f"Bounce/reversal setup -- favors calls / long back toward {resistance:,.0f} and {pd_high:,.0f}.",
        },
    ]

    puts_setups = [
        {
            "trigger": f"Breaks and holds below {support:,.0f} ({support_label}) for 15-30 min",
            "read": (
                f"Momentum breakdown -- favors puts / short, targeting {projection['projected_low']:,.0f} "
                f"(projected low) next."
            ),
        },
        {
            "trigger": f"Rallies to {resistance:,.0f} ({resistance_label}) and gets rejected",
            "read": f"Rejection/reversal setup -- favors puts / short back toward {support:,.0f} and {pd_low:,.0f}.",
        },
    ]

    return {
        "bias_note": (
            f"Overall statistical lean for tomorrow: {projection['directional_lean']}. Use that to weight "
            f"which side of this plan you favor -- it doesn't mean ignore the other side if price shows you "
            f"otherwise."
        ),
        "resistance": resistance,
        "support": support,
        "calls_setups": calls_setups,
        "puts_setups": puts_setups,
        "caveat": (
            "These are conditional levels to watch, not trade recommendations. Confirm with actual price "
            "action/volume before entering, and define your own risk (stop level / max loss) before buying "
            "any option."
        ),
    }
