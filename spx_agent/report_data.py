"""
Assembles the full historical-analysis report as one dict, ready to be
rendered to HTML by html_report.py. Generic over instrument (SPX, ES, ...)
via the `symbol`/`display_name` params -- all analysis modules operate on
plain OHLCV bars and don't care what they're priced in.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from spx_agent.entry_exit_plan import build_entry_exit_plan
from spx_agent.intraday_levels import build_intraday_levels
from spx_agent.level_narrative import build_level_narrative, build_open_scenarios
from spx_agent.levels import build_levels
from spx_agent.price_grid import build_price_grid
from spx_agent.projection import project_next_session
from spx_agent.recent_session_levels import build_recent_session_levels
from spx_agent.seasonality import build_monthly_seasonality
from spx_agent.technicals import build_technicals
from spx_agent.trade_plan import build_trade_plan


def build_report(bars: List[Dict], intraday_bars: Optional[List[Dict]] = None,
                  gex_snapshot: Optional[Dict] = None, symbol: str = "SPX",
                  display_name: Optional[str] = None, target_points: float = 30.0,
                  point_value_note: Optional[str] = None, live_quote: Optional[Dict] = None) -> Dict:
    display_name = display_name or symbol

    levels = build_levels(bars)
    technicals = build_technicals(bars)
    seasonality = build_monthly_seasonality(bars)
    projection = project_next_session(bars, technicals, seasonality, symbol=symbol)

    intraday = build_intraday_levels(intraday_bars) if intraday_bars else None
    level_narrative = build_level_narrative(levels, projection, intraday, gex_snapshot, symbol=symbol)
    open_scenarios = build_open_scenarios(levels, projection, intraday)
    price_grid = build_price_grid(bars, symbol=symbol)
    recent_session_levels = build_recent_session_levels(bars)
    trade_plan = build_trade_plan(levels, projection, intraday)
    entry_exit_plan = build_entry_exit_plan(levels, technicals, intraday, projection,
                                             target_points=target_points, symbol=symbol,
                                             point_value_note=point_value_note)

    report = {
        "symbol": symbol,
        "display_name": display_name,
        "bars_used": len(bars),
        "history_start": bars[0]["date"],
        "history_end": bars[-1]["date"],
        "levels": levels,
        "technicals": technicals,
        "seasonality": seasonality,
        "projection": projection,
        "recent_bars": bars[-90:],
        "level_narrative": level_narrative,
        "open_scenarios": open_scenarios,
        "price_grid": price_grid,
        "recent_session_levels": recent_session_levels,
        "trade_plan": trade_plan,
        "entry_exit_plan": entry_exit_plan,
    }

    if intraday:
        report["intraday"] = intraday
        report["intraday_bars"] = intraday_bars

    if gex_snapshot:
        report["gex"] = gex_snapshot

    if live_quote:
        report["live_quote"] = live_quote

    return report
