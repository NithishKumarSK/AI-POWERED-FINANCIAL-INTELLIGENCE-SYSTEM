"""
SPX Level Narrative
Attaches a plain-English "why this level matters" reason to every level the
agent has already computed, and builds a small set of "if tomorrow opens
near X" playbook scenarios referencing those levels. This module adds no
new statistics -- it's narrative over numbers computed elsewhere.
"""
from __future__ import annotations

from typing import Dict, List, Optional


def build_level_narrative(levels: Dict, projection: Dict, intraday: Optional[Dict],
                           gex: Optional[Dict] = None, symbol: str = "SPX") -> List[Dict]:
    """Returns a flat list of {level, kind: 'support'|'resistance', label,
    reason}, sorted high -> low, covering every level surfaced elsewhere in
    the report. Near-duplicate levels (within $3) are merged."""
    last_close = levels["last_close"]
    entries: List[Dict] = []

    def add(level, reason: str, source: str) -> None:
        if level is None:
            return
        kind = "resistance" if level >= last_close else "support"
        entries.append({"level": round(level, 2), "kind": kind, "label": source, "reason": reason})

    tf_labels = {"5y": "5-year", "1y": "1-year", "3m": "3-month", "1m": "1-month", "1w": "1-week"}
    for tf, label in tf_labels.items():
        sw = levels["swing_levels"].get(tf, {})
        for h in sw.get("highs", []):
            add(h, f"A {label} swing high -- price reversed down from here at least once in that window.", f"{label} swing high")
        for l in sw.get("lows", []):
            add(l, f"A {label} swing low -- price reversed up from here at least once in that window.", f"{label} swing low")

    ma = levels["moving_averages"]
    ma_reasons = {
        "sma20": "20-day moving average -- short-term trend line; often acts as dynamic support in an uptrend / resistance in a downtrend.",
        "sma50": "50-day moving average -- medium-term trend line, widely watched by trend-following flow.",
        "sma100": "100-day moving average -- intermediate trend reference.",
        "sma200": "200-day moving average -- the classic long-term bull/bear dividing line.",
    }
    for k, v in ma.items():
        add(v, ma_reasons[k], k.upper())

    pd_ = levels["prior_day"]
    add(pd_["high"], "Prior day's high -- a break above often triggers momentum buying / short covering.", "Prior day high")
    add(pd_["low"], "Prior day's low -- a break below often triggers momentum selling.", "Prior day low")

    pw = levels["prior_week"]
    add(pw["high"], "Prior week's high.", "Prior week high")
    add(pw["low"], "Prior week's low.", "Prior week low")

    pm = levels["prior_month"]
    add(pm["high"], "Prior month's high.", "Prior month high")
    add(pm["low"], "Prior month's low.", "Prior month low")

    add(projection["projected_high"], "Statistical upper bound for tomorrow (last close + expected move, from ATR/recent range).", "Projected high (tomorrow)")
    add(projection["projected_low"], "Statistical lower bound for tomorrow (last close - expected move, from ATR/recent range).", "Projected low (tomorrow)")

    band_pts = projection.get("fixed_band_points", 40)
    add(
        projection.get("fixed_band_high"),
        (
            f"Fixed +{band_pts:.0f}-point reference above today's close -- always shown, independent of "
            f"ATR/volatility. {symbol} closing beyond this the next session is a stronger-than-typical up "
            f"move; staying under it is an average/contained day."
        ),
        f"+{band_pts:.0f} pt fixed band",
    )
    add(
        projection.get("fixed_band_low"),
        (
            f"Fixed -{band_pts:.0f}-point reference below today's close -- always shown, independent of "
            f"ATR/volatility. {symbol} closing beyond this the next session is a stronger-than-typical down "
            f"move; staying above it is an average/contained day."
        ),
        f"-{band_pts:.0f} pt fixed band",
    )

    if intraday:
        sessions_used = intraday.get("sessions_used", 0)
        for z in intraday.get("resistance_zones", []):
            add(z["level"], f"15-min confluence zone -- price touched this ~$10-wide band {z['touches']}x in the last {sessions_used} sessions.", "Intraday confluence")
        for z in intraday.get("support_zones", []):
            add(z["level"], f"15-min confluence zone -- price touched this ~$10-wide band {z['touches']}x in the last {sessions_used} sessions.", "Intraday confluence")
        last = intraday.get("last_session")
        if last:
            add(last["vwap"], "Last session's volume-weighted average price -- a common day-trading fair-value pivot.", "Last session VWAP")
            add(last["or_high"], "Last session's opening-range (first 30 min) high.", "Opening range high")
            add(last["or_low"], "Last session's opening-range (first 30 min) low.", "Opening range low")

    if gex:
        for r in gex.get("top_positive_gex_strikes", [])[:3]:
            add(
                r["strike"],
                (
                    f"Large positive gamma concentration (~${r['net_gex'] / 1e9:.1f}B) at this strike -- "
                    f"historically a 'pinning' zone where dealer hedging can dampen movement toward it."
                ),
                "GEX pin (positive)",
            )
        for r in gex.get("top_negative_gex_strikes", [])[:3]:
            add(
                r["strike"],
                (
                    f"Large negative gamma concentration (~${r['net_gex'] / 1e9:.1f}B) at this strike -- "
                    f"historically a zone where dealer hedging can amplify moves through it."
                ),
                "GEX (negative)",
            )
        if gex.get("zero_gamma_flip"):
            add(
                gex["zero_gamma_flip"],
                (
                    "Zero-gamma flip level -- where aggregate dealer gamma crosses from positive to "
                    "negative. Historically, crossing it tends to shift the market from a calmer/pin-prone "
                    "regime to a faster/more volatile one, or vice versa."
                ),
                "GEX zero-gamma flip",
            )

    entries.sort(key=lambda e: -e["level"])
    deduped: List[Dict] = []
    for e in entries:
        if deduped and abs(deduped[-1]["level"] - e["level"]) < 3:
            if e["label"] not in deduped[-1]["label"]:
                deduped[-1]["label"] += f" / {e['label']}"
            continue
        deduped.append(e)

    return deduped


def build_open_scenarios(levels: Dict, projection: Dict, intraday: Optional[Dict]) -> List[Dict]:
    """Playbook-style scenarios keyed off where tomorrow's open lands
    relative to today's key levels. Qualitative -- describes what to watch,
    not a guaranteed outcome."""
    last_close = levels["last_close"]
    proj_high, proj_low = projection["projected_high"], projection["projected_low"]
    pd_high, pd_low = levels["prior_day"]["high"], levels["prior_day"]["low"]

    scenarios = [
        {
            "condition": f"Opens above {proj_high:,.0f} (above the projected range)",
            "read": (
                f"Gap up beyond the statistical band. Watch whether price holds above "
                f"{pd_high:,.0f} (prior day high) in the first 30 minutes -- holding favors "
                f"continuation toward new highs; a fast fade back under {pd_high:,.0f} often "
                f"means the gap gets filled back toward VWAP or {last_close:,.0f}."
            ),
        },
        {
            "condition": f"Opens between {min(pd_high, proj_high):,.0f} and {max(pd_high, proj_high):,.0f} (upper half of range)",
            "read": (
                f"In-range but strong. {pd_high:,.0f} (prior day high) becomes first support on a "
                f"pullback; {proj_high:,.0f} is the statistical ceiling to fade into, or break through "
                f"on above-average volume."
            ),
        },
        {
            "condition": f"Opens between {pd_low:,.0f} and {pd_high:,.0f} (inside prior day's range)",
            "read": (
                f"Balanced/rangebound open. Expect chop between prior-day high {pd_high:,.0f} and "
                f"low {pd_low:,.0f} until one side breaks; the opening-range high/low from the first "
                f"30 minutes usually defines the day's initial direction from here."
            ),
        },
        {
            "condition": f"Opens between {min(proj_low, pd_low):,.0f} and {max(proj_low, pd_low):,.0f} (lower half of range)",
            "read": (
                f"In-range but weak. {pd_low:,.0f} (prior day low) becomes first resistance on a "
                f"bounce; {proj_low:,.0f} is the statistical floor to watch for a reclaim vs a "
                f"breakdown continuation."
            ),
        },
        {
            "condition": f"Opens below {proj_low:,.0f} (below the projected range)",
            "read": (
                f"Gap down beyond the statistical band. Watch whether price holds below "
                f"{pd_low:,.0f} (prior day low) in the first 30 minutes -- holding favors "
                f"continuation lower; a fast reclaim of {pd_low:,.0f} often means the gap gets "
                f"filled back toward VWAP or {last_close:,.0f}."
            ),
        },
    ]

    if intraday and intraday.get("nearest_resistance") and intraday.get("nearest_support"):
        nearest_res = intraday["nearest_resistance"]
        nearest_sup = intraday["nearest_support"]
        scenarios.append({
            "condition": f"Regardless of open: tightest intraday pivot zone is {nearest_sup:,.0f}-{nearest_res:,.0f}",
            "read": (
                f"This is where 15-min price action has clustered most in the last "
                f"{intraday['sessions_used']} sessions. A clean break of either side on volume is "
                f"the highest-conviction day-trade signal in this report; staying inside it usually "
                f"means chop -- fade the edges rather than chase."
            ),
        })

    scenarios.append({
        "condition": "General rule: any level below traded through and closed beyond",
        "read": (
            "Every level in the tables above is labeled Support or Resistance based on today's close -- "
            "that label isn't fixed. If price opens or trades through a level marked Resistance and holds "
            "above it (doesn't just wick through), treat that same level as the new Support on any pullback "
            "-- the classic support/resistance 'polarity flip'. The same applies in reverse: a broken "
            "Support level tends to act as new Resistance on a bounce back up to it. Re-running the report "
            "after such a move will relabel every level automatically, since each level's Support/Resistance "
            "tag is recalculated from the latest close, not stored as a fixed designation."
        ),
    })

    return scenarios
