"""
SPX Historical Data Loader
Fetches and caches ~5 years of daily SPX (S&P 500 index) OHLC bars.

Reuses the existing historical_price_service fallback chain (RapidAPI
TradingView -> NASDAQ external -> yfinance -> Yahoo direct) so SPX history
reaches back further than any single provider's own limit.
"""
from __future__ import annotations

import csv
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from historical_price_service import fetch_price_history_for_range  # noqa: E402

SYMBOL = "SPX"
CACHE_PATH = ROOT / "data" / "spx_5y_daily.csv"
LOOKBACK_YEARS = 5
CACHE_FIELDS = ["date", "open", "high", "low", "close", "volume"]


def _read_cache() -> List[Dict]:
    if not CACHE_PATH.exists():
        return []
    with CACHE_PATH.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("open", "high", "low", "close", "volume"):
            r[k] = float(r[k]) if r.get(k) not in (None, "") else None
    return sorted(rows, key=lambda r: r["date"])


def _write_cache(bars: List[Dict]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CACHE_FIELDS)
        writer.writeheader()
        for b in bars:
            writer.writerow({k: b.get(k) for k in CACHE_FIELDS})


def load_spx_history(refresh: bool = False) -> List[Dict]:
    """Return ~5 years of SPX daily bars sorted by date ascending.

    Uses a local CSV cache (data/spx_5y_daily.csv) that's considered fresh
    if its last bar is within 3 calendar days of today. Pass refresh=True
    to force a re-fetch from providers.
    """
    cached = [] if refresh else _read_cache()
    today = date.today()

    if cached and cached[-1]["date"] >= (today - timedelta(days=3)).strftime("%Y-%m-%d"):
        return cached

    start = (today - timedelta(days=LOOKBACK_YEARS * 365 + 10)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    bars, err, coverage = fetch_price_history_for_range(SYMBOL, start, end)
    if not bars:
        if cached:
            return cached
        raise RuntimeError(f"Could not fetch SPX history from any provider: {err}")

    bars = sorted(bars, key=lambda b: b["date"])
    _write_cache(bars)
    return bars
