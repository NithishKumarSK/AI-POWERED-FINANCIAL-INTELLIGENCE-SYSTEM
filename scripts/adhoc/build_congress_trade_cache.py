"""
build_congress_trade_cache.py — periodic refresh for
core/congress_trade_service.py's ticker-indexed PTR cache.

Scans the current year's House PTR filings (most-recent-first, bounded per
run) and updates data/congress_trade_cache.json. Safe to re-run repeatedly
-- already-scanned filings are skipped, so each run only processes new
filings since the last one (incremental, not a full rescan).

Usage:
    python scripts/adhoc/build_congress_trade_cache.py
    python scripts/adhoc/build_congress_trade_cache.py --max-filings 200
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tools"))

from congress_trade_service import build_cache, DEFAULT_MAX_FILINGS_PER_RUN  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--max-filings", type=int, default=DEFAULT_MAX_FILINGS_PER_RUN)
    args = ap.parse_args()

    summary, err = build_cache(year=args.year, max_filings=args.max_filings)
    if summary is None:
        print(f"FAILED: {err}")
        sys.exit(1)
    print(f"Congress trade cache updated: {summary}")
    if err:
        print(f"(partial, with notes: {err})")
