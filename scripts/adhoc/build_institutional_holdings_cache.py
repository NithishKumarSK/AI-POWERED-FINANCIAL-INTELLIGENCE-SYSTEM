"""
build_institutional_holdings_cache.py — periodic refresh for
core/institutional_holdings_service.py's 23-well-known-filer 13F cache.

13F filings only update quarterly, so this is cheap to run on the same
schedule as everything else in scripts/scheduled_retraining.py despite
hitting SEC EDGAR for all 23 filers each time -- there's no meaningful
incremental-scan optimization here the way congress_trade_cache has (23
filers, not hundreds of yearly PTR filings).

Usage:
    python scripts/adhoc/build_institutional_holdings_cache.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tools"))

from institutional_holdings_service import build_cache  # noqa: E402

if __name__ == "__main__":
    summary, err = build_cache()
    print(f"Institutional holdings cache updated: {summary}")
    if summary and summary.get("failures"):
        for f in summary["failures"]:
            print(f"  FAILED: {f['name']} ({f['cik']}): {f['error']}")
    if err:
        print(f"err: {err}")
        sys.exit(1)
