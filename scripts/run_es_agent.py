"""
ES Futures Historical Analysis Agent -- CLI entry point.

Same analysis as run_spx_agent.py (levels across multiple timeframes,
technicals, monthly seasonality, next-session projection, day-trading
levels, price grid, trade-plan) but for E-mini S&P 500 futures (ES),
fetched directly via yfinance's continuous front-month contract ("ES=F").
Writes a self-contained HTML report to data/es_analysis_report.html.

Two known differences from the SPX report:
  - No GEX panel: CME/ES futures options aren't available through this
    data source (yfinance has no options chain for "ES=F"). The SPX report
    includes GEX, which is a reasonable read-across given ES and SPX trade
    in near lockstep.
  - "Sessions" in the day-trading levels panel are grouped by calendar date
    of the bar timestamp, not CME's official 6pm ET session rollover -- ES
    trades nearly 24 hours, so this is an approximation. Regular-hours
    (9:30-16:00 ET) volume still dominates the VWAP/opening-range math in
    practice.

This is historical-data analysis only -- it does not place trades.

Usage:
    python run_es_agent.py            # use cache if fresh, else fetch
    python run_es_agent.py --refresh  # force re-fetch from providers
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from spx_agent.es_data_loader import load_es_history  # noqa: E402
from spx_agent.es_intraday_data import load_intraday_bars  # noqa: E402
from spx_agent.html_report import render_html_report  # noqa: E402
from spx_agent.live_quote import get_live_quote  # noqa: E402
from spx_agent.report_data import build_report  # noqa: E402

LIVE_TICKER = "ES=F"

REPORT_PATH = ROOT / "data" / "es_analysis_report.html"
SYMBOL = "ES"
DISPLAY_NAME = "E-mini S&P 500 Futures (ES)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the ES futures historical analysis report.")
    parser.add_argument("--refresh", action="store_true",
                         help="Force re-fetch history from providers instead of using the cache.")
    parser.add_argument("--target", type=float, default=30.0,
                         help="Point target for the entry/exit plan (default: 30).")
    args = parser.parse_args()

    print(f"Loading ES history{' (forcing refresh)' if args.refresh else ''}...")
    bars = load_es_history(refresh=args.refresh)
    print(f"Loaded {len(bars)} daily bars: {bars[0]['date']} -> {bars[-1]['date']}")

    print("Loading ES 15-minute intraday bars (last ~1 month of sessions)...")
    try:
        intraday_bars = load_intraday_bars()
        print(f"Loaded {len(intraday_bars)} 15m bars: {intraday_bars[0]['datetime']} -> {intraday_bars[-1]['datetime']}")
    except Exception as exc:
        intraday_bars = None
        print(f"  Skipping day-trading levels -- intraday fetch failed: {exc}")

    print("Fetching live/delayed quote...")
    try:
        live_quote = get_live_quote(LIVE_TICKER)
        print(f"  {live_quote['price']:,.2f} as of {live_quote['last_bar_time']} "
              f"({live_quote['staleness_display']})")
    except Exception as exc:
        live_quote = None
        print(f"  Skipping live quote -- fetch failed: {exc}")

    point_value_note = "Standard ES = $50/point per contract; Micro ES (MES) = $5/point."
    report = build_report(bars, intraday_bars=intraday_bars, symbol=SYMBOL, display_name=DISPLAY_NAME,
                           target_points=args.target, point_value_note=point_value_note,
                           live_quote=live_quote)
    html = render_html_report(report)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(html, encoding="utf-8")

    proj = report["projection"]
    print(f"\nAs of {proj['as_of_date']} close {proj['as_of_close']:,.2f}:")
    print(f"  Next-session lean: {proj['directional_lean']}")
    print(f"  Projected range: {proj['projected_low']:,.2f} - {proj['projected_high']:,.2f} "
          f"(+/- {proj['expected_move_points']:,.1f} pts)")

    intraday = report.get("intraday")
    if intraday:
        print(f"\nDay-trading levels ({intraday['sessions_used']} sessions, "
              f"{intraday['date_range'][0]} -> {intraday['date_range'][1]}):")
        print(f"  Nearest resistance: {intraday['nearest_resistance']}")
        print(f"  Nearest support:    {intraday['nearest_support']}")
        print(f"  Median session range: {intraday['median_session_range_pts']} pts")

    print(f"\nReport written to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
