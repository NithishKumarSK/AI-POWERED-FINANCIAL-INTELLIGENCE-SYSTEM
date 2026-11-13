"""
Live orchestrator for core/breadth_chart_analyst.py -- reuses
core/market_breadth_service.py's existing CSV fetchers (no new network
call) and feeds the resulting series into the signal-detection layer.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from breadth_chart_analyst import analyze_breadth_charts


def fetch_breadth_chart_analysis(as_of_date: str) -> Tuple[Optional[Dict[str, Any]], str]:
    from market_breadth_service import _fetch_breadth, _fetch_uptrend

    breadth_rows, breadth_err = _fetch_breadth()
    uptrend_rows, uptrend_err = _fetch_uptrend()
    if not breadth_rows:
        return None, breadth_err or "no_breadth_data"
    if not uptrend_rows:
        return None, uptrend_err or "no_uptrend_data"

    breadth_as_of = [r for r in breadth_rows if r["date"] <= as_of_date[:10]]
    uptrend_as_of = [r for r in uptrend_rows if r["date"] <= as_of_date[:10]]
    if len(breadth_as_of) < 3 or len(uptrend_as_of) < 3:
        return None, "insufficient_history_as_of_date"

    # Breadth_Index_200MA/_8MA are 0-1 fractions in the raw feed (confirmed
    # live this session), but SKILL.md's thresholds (73%, 60%, 23%) and its
    # own "62.26%" expected-output example are percentages -- scaled here,
    # same convention already applied to uptrend_ratio below.
    result = analyze_breadth_charts(
        breadth_200ma_series=[r["breadth_200ma"] * 100 for r in breadth_as_of[-10:]],
        breadth_8ma_series=[r["breadth_8ma"] * 100 for r in breadth_as_of[-10:]],
        uptrend_ratio_series=[r["uptrend_ratio"] * 100 for r in uptrend_as_of[-10:]],
        uptrend_trend_series=[r.get("uptrend_trend") for r in uptrend_as_of[-10:]],
    )
    warnings = "; ".join(w for w in (breadth_err, uptrend_err) if w)
    return result, warnings
