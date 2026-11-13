"""
vcp_screener_service.py -- live orchestrator for core/vcp_screener.py.
Fetches the symbol's price history plus the SPY benchmark via
historical_price_service.py and runs the full VCP analysis pipeline.
Entirely price-history-based -- no FMP/fundamentals needed.

"quote" (price/yearHigh/yearLow/marketCap) is derived directly from the
symbol's own OHLCV history, same approach as market_top_detector_service.py's
_derive_quote -- free and leakage-safe, where a live quote snapshot
wouldn't be. marketCap has no free per-symbol source here, so it's left 0
(the calculator never actually uses it -- confirmed by reading
analyze_stock(), which only echoes quote.get("marketCap") into the output).

Per-symbol. Cached on disk per symbol for a day.

LEAKAGE SAFETY: historical_price_service returns the full available
history; this module filters both the symbol's and SPY's bars to
date <= as_of_date before any calculation.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "vcp_screener_cache.json"
CACHE_TTL_DAYS = 1
PRICE_LOOKBACK_DAYS = 420  # covers the 252-day RS window + 222-day SMA200-trend check with buffer
BENCHMARK = "SPY"


def _to_most_recent_first(bars: list, as_of_date: str) -> list:
    as_of = as_of_date[:10]
    filtered = [b for b in bars if b.get("date", "") <= as_of]
    return list(reversed(filtered))


def _derive_quote(history: list) -> dict:
    """price = most recent close; yearHigh/yearLow over trailing ~252 bars."""
    price = history[0].get("close", 0) if history else 0
    window = history[:252]
    year_high = max((d.get("high", d.get("close", 0)) for d in window), default=0)
    year_low = min((d.get("low", d.get("close", 0)) for d in window if d.get("low", d.get("close", 0)) > 0), default=0)
    return {"price": price, "yearHigh": year_high, "yearLow": year_low, "marketCap": 0}


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass


def fetch_vcp_analysis(symbol: str, as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """VCP (Volatility Contraction Pattern) analysis for `symbol` as of a
    given date.

    Returns (data, error_string). data shape on success (see
    core.vcp_screener.analyze_stock for the full field list):
        {"composite_score": float, "rating": str, "execution_state": str,
         "pattern_type": str, "valid_vcp": bool, ...}
    """
    from vcp_screener import analyze_stock

    cache_key = f"{symbol}:{as_of_date[:10]}"
    if use_cache:
        cache = _load_cache()
        entry = cache.get(cache_key)
        if entry and (time.time() - entry.get("computed_at", 0)) < CACHE_TTL_DAYS * 86400:
            return entry["data"], ""

    import datetime as _dt
    from historical_price_service import fetch_price_history_for_range

    as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
    start_dt = as_of_dt - _dt.timedelta(days=PRICE_LOOKBACK_DAYS + 30)

    raw_bars, err, _coverage = fetch_price_history_for_range(symbol, start_dt.isoformat(), as_of_dt.isoformat())
    if not raw_bars:
        return None, err or f"No price history available for {symbol}"

    sp500_raw, sp500_err, _coverage2 = fetch_price_history_for_range(BENCHMARK, start_dt.isoformat(), as_of_dt.isoformat())
    if not sp500_raw:
        return None, sp500_err or f"No price history available for benchmark {BENCHMARK}"

    historical = _to_most_recent_first(raw_bars, as_of_date)
    sp500_history = _to_most_recent_first(sp500_raw, as_of_date)
    if len(historical) < 50:
        return None, f"Insufficient price history for {symbol}: {len(historical)} bars"

    quote = _derive_quote(historical)
    result = analyze_stock(symbol, historical, quote, sp500_history)

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    return result, ""
