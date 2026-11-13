"""
survivorship_bias_audit.py -- Research Expansion Program: a one-time,
documented check of whether our training/prediction symbol universe has a
survivorship-bias problem, the gap flagged (but not fixed) in both Zhong &
Hitchcock (who explicitly included 67 delisted S&P 500 names to counter it)
and the Al Ridhawi/Haj Ali/Al Osman papers (whose own Limitations section
calls survivorship bias "the most consequential concern," unaddressed).

This is NOT a claim that we've solved survivorship bias (we haven't -- our
universe is still 10 current mega-caps/indices, not an exhaustive historical
universe). It is an honest, checkable answer to a narrower, real question:
"has any symbol WE currently train/predict on silently changed identity
(ticker reuse, name change, reverse-merger successor) in a way that would
make our price history discontinuous or misattributed?" That's a concrete,
checkable risk -- the thing this audit actually tests.

Two free, no-new-dependency checks per symbol:
  1. SEC EDGAR submissions metadata -- `formerNames` field lists any prior
     company name + the date range it was used. A populated list doesn't
     necessarily mean a problem (plenty of real companies renamed without
     any ticker discontinuity), but it's a disclosed flag worth a human
     looking at once.
  2. Price-history continuity -- fetch the full training window
     (historical_price_service, same provider chain every other feature in
     this project already relies on) and flag any gap of more than 10
     consecutive calendar days between bars, which would be consistent with
     a trading halt, delisting, or ticker handoff.

Usage: python core/survivorship_bias_audit.py [--symbols A,B,C] [--start YYYY-MM-DD] [--out path.json]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))

import bootstrap_paths
bootstrap_paths.add_module_paths()

# Same 10-symbol universe ml_training_runner.py --bulk uses by default.
DEFAULT_SYMBOLS = ["SPY", "TSLA", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "QQQ", "IWM"]


def _check_former_names(symbol: str) -> dict:
    """SEC EDGAR has no filer record at all for pure index ETFs (SPY, QQQ,
    IWM aren't operating companies with 10-Ks) -- that's an expected,
    disclosed non-result, not an error."""
    from sec_edgar_client import get_cik_for_symbol, get_submissions

    cik_result = get_cik_for_symbol(symbol)
    if cik_result.get("status") != "SUCCESS":
        return {"symbol": symbol, "sec_filer": False,
                "note": cik_result.get("message", "No SEC filer record (expected for index ETFs)")}

    subs = get_submissions(cik_result["cik"])
    if subs.get("status") != "SUCCESS":
        return {"symbol": symbol, "sec_filer": True, "cik": cik_result["cik"],
                "note": f"Submissions fetch failed: {subs.get('message')}"}

    data = subs.get("data", {})
    former_names = data.get("formerNames", []) or []
    return {
        "symbol": symbol,
        "sec_filer": True,
        "cik": cik_result["cik"],
        "current_name": data.get("name", ""),
        "former_names": [
            {"name": fn.get("name"), "from": fn.get("from", "")[:10], "to": fn.get("to", "")[:10]}
            for fn in former_names
        ],
        "flag": bool(former_names),
    }


def _check_price_continuity(symbol: str, start: str, end: str) -> dict:
    from historical_price_service import fetch_price_history_for_range

    bars, err, coverage = fetch_price_history_for_range(symbol, start, end)
    if not bars:
        return {"symbol": symbol, "bars_found": 0, "note": f"No price data: {err}", "flag": True}

    dates = sorted(_dt.date.fromisoformat(b["date"][:10]) for b in bars)
    max_gap_days = 0
    gap_start = gap_end = None
    for i in range(1, len(dates)):
        gap = (dates[i] - dates[i - 1]).days
        if gap > max_gap_days:
            max_gap_days = gap
            gap_start, gap_end = dates[i - 1], dates[i]

    return {
        "symbol": symbol,
        "bars_found": len(bars),
        "first_bar": str(dates[0]),
        "last_bar": str(dates[-1]),
        "requested_start": start,
        "coverage_status": coverage.get("coverage_status"),
        "max_gap_calendar_days": max_gap_days,
        "max_gap_window": f"{gap_start} to {gap_end}" if gap_start else None,
        # >10 calendar days with no bar at all is unusual for an actively
        # traded large-cap/ETF outside normal weekends/holidays (~4 days max).
        "flag": max_gap_days > 10 or coverage.get("coverage_status") != "FULL",
    }


def run_audit(symbols: List[str], start: str, end: Optional[str] = None) -> dict:
    end = end or _dt.date.today().isoformat()
    results = []
    for sym in symbols:
        name_check = _check_former_names(sym)
        continuity_check = _check_price_continuity(sym, start, end)
        results.append({"symbol": sym, "former_names_check": name_check, "continuity_check": continuity_check})

    flagged = [r["symbol"] for r in results
               if r["former_names_check"].get("flag") or r["continuity_check"].get("flag")]

    return {
        "symbols_checked": symbols,
        "window": {"start": start, "end": end},
        "results": results,
        "flagged_symbols": flagged,
        "honest_summary": (
            "This audit checks ticker/identity continuity for the CURRENT universe "
            "only -- it does NOT add delisted/failed companies to the training set, "
            "so it does not fix survivorship bias in the classic academic sense "
            "(Zhong & Hitchcock's 67-delisted-name approach). It answers a narrower "
            "question: is any symbol we currently use silently discontinuous? "
            f"{'No symbols flagged -- all ' + str(len(symbols)) + ' resolved cleanly.' if not flagged else 'Flagged: ' + ', '.join(flagged) + ' -- see results for details.'}"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=str, default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--start", type=str, default="2021-01-01")
    parser.add_argument("--out", type=str, default=str(ROOT / "data" / "survivorship_bias_audit.json"))
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    report = run_audit(symbols, args.start)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for r in report["results"]:
        fn = r["former_names_check"]
        cc = r["continuity_check"]
        print(f"{r['symbol']:6s}  sec_filer={fn.get('sec_filer')!s:5s}  "
              f"former_names={len(fn.get('former_names', []))}  "
              f"bars={cc.get('bars_found')}  max_gap_days={cc.get('max_gap_calendar_days')}  "
              f"coverage={cc.get('coverage_status')}  flagged={r['symbol'] in report['flagged_symbols']}")
    print()
    print(report["honest_summary"])
    print(f"\nFull report written to {out_path}")


if __name__ == "__main__":
    main()
