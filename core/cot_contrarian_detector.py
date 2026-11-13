"""
COT Contrarian Detector (Shapiro Step 1), adapted from claude-trading-
skills' `cot-contrarian-detector` skill (vendor/claude-trading-skills/
skills/cot-contrarian-detector/, references/cot-index-calculation.md).
MIT License, Copyright (c) 2026 TraderMonty.

Pure calculation over CFTC Legacy-report rows: net large-speculator
position, the "stochastics of positioning" COT Index (3-year primary +
26-week short lookback), open-interest normalization (context only,
never used in classification), and CROWDED_LONG/CROWDED_SHORT/NEUTRAL
classification at the 90/10 threshold -- every formula and threshold
taken directly from the source skill's own reference doc, not
re-derived. Unlike most skills in this project needing FMP Premium+ for
COT data, this one is NOT scope-reduced: see
tools/cftc_cot_client.py's module docstring for the free, official CFTC
data source this project found and wired in instead.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

THRESHOLD_HIGH_DEFAULT = 90.0
THRESHOLD_LOW_DEFAULT = 10.0
LOOKBACK_WEEKS_DEFAULT = 156
SHORT_LOOKBACK_WEEKS_DEFAULT = 26


def sort_dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ascending by date; on a duplicate date, keep the LAST one in input
    order (treated as the more recently fetched/corrected value). Rows
    missing a date are dropped."""
    dated = [(r.get("report_date_as_yyyy_mm_dd"), i, r) for i, r in enumerate(rows) if r.get("report_date_as_yyyy_mm_dd")]
    by_date: Dict[str, Any] = {}
    for date, idx, row in dated:
        by_date[date] = (idx, row)  # later idx overwrites earlier -> "keep the last"
    return [row for _date, (_idx, row) in sorted(by_date.items(), key=lambda kv: kv[0])]


def compute_net_position(row: Dict[str, Any]) -> Optional[float]:
    try:
        long_ = float(row["noncomm_positions_long_all"])
        short_ = float(row["noncomm_positions_short_all"])
    except (KeyError, TypeError, ValueError):
        return None
    return long_ - short_


def compute_oi_normalized_net(net_position: Optional[float], open_interest: Any) -> Optional[float]:
    """Context only -- never used in CROWDED_LONG/SHORT classification."""
    if net_position is None:
        return None
    try:
        oi = float(open_interest)
    except (TypeError, ValueError):
        return None
    if oi == 0:
        return None
    return net_position / oi


def compute_cot_index(net_series: List[float], lookback_weeks: int) -> Optional[float]:
    """(current - window_min) / (window_max - window_min) * 100 over the
    trailing `lookback_weeks` values (including the current week).
    None when there's insufficient history or the window has zero range."""
    if len(net_series) < lookback_weeks:
        return None
    window = net_series[-lookback_weeks:]
    window_min, window_max = min(window), max(window)
    if window_max == window_min:
        return None
    current = window[-1]
    return (current - window_min) / (window_max - window_min) * 100


def compute_week_over_week_change(net_series: List[float]) -> Optional[float]:
    if len(net_series) < 2:
        return None
    return net_series[-1] - net_series[-2]


def classify_crowding(
    cot_index_primary: Optional[float],
    threshold_high: float = THRESHOLD_HIGH_DEFAULT,
    threshold_low: float = THRESHOLD_LOW_DEFAULT,
) -> str:
    """CROWDED_LONG / CROWDED_SHORT / NEUTRAL. Inclusive boundaries: exactly
    at threshold_high classifies CROWDED_LONG. None (undefined index) ->
    NEUTRAL, the conservative default (never fabricate an extreme from no data)."""
    if cot_index_primary is None:
        return "NEUTRAL"
    if cot_index_primary >= threshold_high:
        return "CROWDED_LONG"
    if cot_index_primary <= threshold_low:
        return "CROWDED_SHORT"
    return "NEUTRAL"


def analyze_cot_crowding(
    rows: List[Dict[str, Any]],
    lookback_weeks: int = LOOKBACK_WEEKS_DEFAULT,
    short_lookback_weeks: int = SHORT_LOOKBACK_WEEKS_DEFAULT,
    threshold_high: float = THRESHOLD_HIGH_DEFAULT,
    threshold_low: float = THRESHOLD_LOW_DEFAULT,
) -> Dict[str, Any]:
    """rows: CFTC Legacy-report rows for one market, any order (sorted here)."""
    sorted_rows = sort_dedupe_rows(rows)
    net_series = [n for n in (compute_net_position(r) for r in sorted_rows) if n is not None]

    cot_index_primary = compute_cot_index(net_series, lookback_weeks)
    cot_index_short = compute_cot_index(net_series, short_lookback_weeks)
    classification = classify_crowding(cot_index_primary, threshold_high, threshold_low)

    latest_row = sorted_rows[-1] if sorted_rows else None
    latest_net = net_series[-1] if net_series else None
    oi_normalized_net = compute_oi_normalized_net(latest_net, (latest_row or {}).get("open_interest_all"))

    return {
        "schema_version": "1.0",
        "classification": classification,
        "cot_index_primary": cot_index_primary, "lookback_weeks_primary": lookback_weeks,
        "cot_index_short": cot_index_short, "lookback_weeks_short": short_lookback_weeks,
        "net_position": latest_net,
        "oi_normalized_net": oi_normalized_net,
        "week_over_week_change": compute_week_over_week_change(net_series),
        "report_date": (latest_row or {}).get("report_date_as_yyyy_mm_dd"),
        "weeks_used": len(net_series),
    }
