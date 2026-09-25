"""
SPX Historical Analysis Agent -- CLI entry point.

Fetches (or reuses a fresh cache of) ~5 years of SPX daily history, builds
support/resistance levels across multiple timeframes, technical indicators,
monthly seasonality stats, and a next-session statistical projection, then
writes a self-contained HTML report to data/spx_analysis_report.html.

This is historical-data analysis only -- it does not place trades.

Usage:
    python run_spx_agent.py            # use cache if fresh, else fetch
    python run_spx_agent.py --refresh  # force re-fetch from providers
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from spx_agent.data_loader import load_spx_history  # noqa: E402
from spx_agent.gex import fetch_gex_snapshot  # noqa: E402
from spx_agent.html_report import render_html_report  # noqa: E402
from spx_agent.intraday_data import load_intraday_bars  # noqa: E402
from spx_agent.live_quote import get_live_quote  # noqa: E402
from spx_agent.report_data import build_report  # noqa: E402

REPORT_PATH = ROOT / "data" / "spx_analysis_report.html"
LIVE_TICKER = "^SPX"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the SPX historical analysis report.")
    parser.add_argument("--refresh", action="store_true",
                         help="Force re-fetch history from providers instead of using the cache.")
    parser.add_argument("--target", type=float, default=30.0,
                         help="Point target for the entry/exit plan (default: 30).")
    args = parser.parse_args()

    print(f"Loading SPX history{' (forcing refresh)' if args.refresh else ''}...")
    bars = load_spx_history(refresh=args.refresh)
    print(f"Loaded {len(bars)} daily bars: {bars[0]['date']} -> {bars[-1]['date']}")

    print("Loading SPX 15-minute intraday bars (last ~1 month of sessions)...")
    try:
        intraday_bars = load_intraday_bars()
        print(f"Loaded {len(intraday_bars)} 15m bars: {intraday_bars[0]['datetime']} -> {intraday_bars[-1]['datetime']}")
    except Exception as exc:
        intraday_bars = None
        print(f"  Skipping day-trading levels -- intraday fetch failed: {exc}")

    print("Loading SPX options chain for gamma exposure (GEX)...")
    try:
        gex_snapshot = fetch_gex_snapshot(spot=bars[-1]["close"])
        print(f"  {len(gex_snapshot['expiries_used'])} expiries used, total net GEX "
              f"{gex_snapshot['total_net_gex']:,.0f} ({gex_snapshot['regime']})")
    except Exception as exc:
        gex_snapshot = None
        print(f"  Skipping GEX panel -- options chain fetch failed: {exc}")

    print("Fetching live/delayed quote...")
    try:
        live_quote = get_live_quote(LIVE_TICKER)
        print(f"  {live_quote['price']:,.2f} as of {live_quote['last_bar_time']} "
              f"({live_quote['staleness_display']})")
    except Exception as exc:
        live_quote = None
        print(f"  Skipping live quote -- fetch failed: {exc}")

    point_value_note = "SPX options are $100/point per contract; SPY options (roughly 1/10th SPX) are $100/point on SPY's own price."
    report = build_report(bars, intraday_bars=intraday_bars, gex_snapshot=gex_snapshot,
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

    gex = report.get("gex")
    if gex:
        print(f"\nGamma exposure ({len(gex['expiries_used'])} expiries):")
        print(f"  Regime: {gex['regime']}")
        print(f"  Zero-gamma flip: {gex['zero_gamma_flip']}")

    print(f"\nReport written to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
