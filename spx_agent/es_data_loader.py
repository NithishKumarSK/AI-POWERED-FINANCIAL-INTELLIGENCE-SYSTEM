"""
ES Futures Historical Data Loader
Fetches and caches ~5 years of daily E-mini S&P 500 futures (ES) OHLC bars
directly via yfinance's continuous front-month contract ("ES=F"). Futures
aren't covered by historical_price_service's exchange-mapping logic (built
for stocks/ETFs/indices), so this talks to yfinance directly rather than
going through that fallback chain.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "data" / "es_5y_daily.csv"
CACHE_FIELDS = ["date", "open", "high", "low", "close", "volume"]

YF_TICKER = "ES=F"
LOOKBACK_YEARS = 5


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


def fetch_es_daily(lookback_years: int = LOOKBACK_YEARS) -> List[Dict]:
    import yfinance as yf

    ticker = yf.Ticker(YF_TICKER)
    df = ticker.history(period=f"{lookback_years}y", interval="1d", auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned no daily bars for {YF_TICKER}")

    bars: List[Dict] = []
    for ts, row in df.iterrows():
        close = float(row.get("Close", 0) or 0)
        if close <= 0:
            continue
        bars.append({
            "date": ts.strftime("%Y-%m-%d"),
            "open": round(float(row.get("Open", 0) or close), 4),
            "high": round(float(row.get("High", 0) or close), 4),
            "low": round(float(row.get("Low", 0) or close), 4),
            "close": round(close, 4),
            "volume": float(row.get("Volume", 0) or 0),
        })
    if not bars:
        raise RuntimeError(f"yfinance parsed 0 valid daily bars for {YF_TICKER}")

    bars.sort(key=lambda b: b["date"])
    return bars


def load_es_history(refresh: bool = False) -> List[Dict]:
    """Return ~5 years of ES daily bars sorted by date ascending, using a
    local CSV cache (data/es_5y_daily.csv) considered fresh if its last bar
    is within 3 calendar days of today. Pass refresh=True to force a
    re-fetch."""
    cached = [] if refresh else _read_cache()
    today = date.today()

    if cached and cached[-1]["date"] >= (today - timedelta(days=3)).strftime("%Y-%m-%d"):
        return cached

    try:
        bars = fetch_es_daily()
    except Exception:
        if cached:
            return cached
        raise

    _write_cache(bars)
    return bars
