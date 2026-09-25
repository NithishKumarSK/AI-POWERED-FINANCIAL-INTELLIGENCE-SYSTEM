"""
SPX 15-Minute Intraday Data
Fetches recent 15-minute OHLCV bars for SPX (^GSPC) directly via yfinance.
Yahoo only serves 15m intraday history for roughly the trailing 60 calendar
days, so this is a separate, shorter-horizon feed from the 5-year daily
history in data_loader.py -- it exists purely to build day-trading levels
from the last week/month of sessions, not long-term stats.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "data" / "spx_15m_recent.csv"
CACHE_FIELDS = ["datetime", "date", "time", "open", "high", "low", "close", "volume"]

YF_TICKER = "^GSPC"


def _read_cache() -> List[Dict]:
    if not CACHE_PATH.exists():
        return []
    with CACHE_PATH.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("open", "high", "low", "close", "volume"):
            r[k] = float(r[k]) if r.get(k) not in (None, "") else None
    return sorted(rows, key=lambda r: r["datetime"])


def _write_cache(bars: List[Dict]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CACHE_FIELDS)
        writer.writeheader()
        for b in bars:
            writer.writerow({k: b.get(k) for k in CACHE_FIELDS})


def fetch_15m_bars(period: str = "1mo") -> List[Dict]:
    """Fetch recent 15-minute SPX bars (Yahoo's practical limit for 15m data
    is ~60 calendar days; default period="1mo" comfortably covers "last
    week"/"last day" day-trading levels). Returns bars sorted ascending by
    datetime, each carrying both 'date' (YYYY-MM-DD) and 'time' (HH:MM,
    exchange-local) for per-session grouping."""
    import yfinance as yf

    ticker = yf.Ticker(YF_TICKER)
    df = ticker.history(period=period, interval="15m", auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned no 15m bars for {YF_TICKER}")

    bars: List[Dict] = []
    for ts, row in df.iterrows():
        close = float(row.get("Close", 0) or 0)
        if close <= 0:
            continue
        bars.append({
            "datetime": ts.strftime("%Y-%m-%d %H:%M"),
            "date": ts.strftime("%Y-%m-%d"),
            "time": ts.strftime("%H:%M"),
            "open": round(float(row.get("Open", 0) or close), 4),
            "high": round(float(row.get("High", 0) or close), 4),
            "low": round(float(row.get("Low", 0) or close), 4),
            "close": round(close, 4),
            "volume": float(row.get("Volume", 0) or 0),
        })
    if not bars:
        raise RuntimeError(f"yfinance parsed 0 valid 15m bars for {YF_TICKER}")

    bars.sort(key=lambda b: b["datetime"])
    _write_cache(bars)
    return bars


def load_intraday_bars(period: str = "1mo") -> List[Dict]:
    """Fetch fresh 15m bars; fall back to the last successful cache on
    failure (rate limit, network) so the report can still render."""
    try:
        return fetch_15m_bars(period=period)
    except Exception:
        cached = _read_cache()
        if cached:
            return cached
        raise
