"""
pead_screener_service.py -- live orchestrator for core/pead_screener.py.
Finds the symbol's most recent earnings-tagged 8-K (via
core/free_news_service.fetch_most_recent_earnings_8k -- see that
function's docstring for why FMP's own earnings-calendar couldn't be used:
confirmed free-tier-blocked beyond a ~few-day lookback), fetches daily
price history via historical_price_service.py, and runs the PEAD
weekly-candle pattern analysis.

Per-symbol (not market-wide) -- same category as
downtrend_duration_service.py. Cached on disk per symbol for a day.

LEAKAGE SAFETY: both the earnings-8K lookup and the price history are
filtered to on/before as_of_date before any calculation.

Honest gap carried over from free_news_service: SEC's submissions API
doesn't record BMO/AMC earnings-call timing (unlike FMP's calendar), so
calculate_price_gap always runs in "unknown" (AMC-style) mode here.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "pead_screener_cache.json"
CACHE_TTL_DAYS = 1
WATCH_WEEKS = 5
EARNINGS_LOOKBACK_DAYS = WATCH_WEEKS * 7 + 14  # a bit more than the watch window
PRICE_LOOKBACK_DAYS = EARNINGS_LOOKBACK_DAYS + 30


def _to_most_recent_first(bars: list, as_of_date: str) -> list:
    as_of = as_of_date[:10]
    filtered = [b for b in bars if b.get("date", "") <= as_of]
    return list(reversed(filtered))


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


def fetch_pead_analysis(symbol: str, as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """PEAD (Post-Earnings-Announcement-Drift) weekly-candle setup analysis
    for `symbol` as of a given date.

    Returns (data, error_string). data shape on success (see
    core.pead_screener.analyze_stock for the full field list):
        {"stage": str, "composite_score": float, "rating": str,
         "guidance": str, "weeks_since_earnings": int, ...}
    None (with a non-empty error) when there's no recent-enough earnings
    event to screen, or insufficient price history -- never a fabricated
    neutral result.
    """
    from pead_screener import analyze_stock, calculate_price_gap

    cache_key = f"{symbol}:{as_of_date[:10]}"
    if use_cache:
        cache = _load_cache()
        entry = cache.get(cache_key)
        if entry and (time.time() - entry.get("computed_at", 0)) < CACHE_TTL_DAYS * 86400:
            return entry["data"], ""

    from free_news_service import fetch_most_recent_earnings_8k
    earnings_data, earnings_err = fetch_most_recent_earnings_8k(symbol, as_of_date, lookback_days=EARNINGS_LOOKBACK_DAYS)
    if not earnings_data:
        return None, earnings_err

    earnings_date = earnings_data["earnings_date"]

    import datetime as _dt
    from historical_price_service import fetch_price_history_for_range

    as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
    start_dt = as_of_dt - _dt.timedelta(days=PRICE_LOOKBACK_DAYS)
    bars, price_err, _coverage = fetch_price_history_for_range(symbol, start_dt.isoformat(), as_of_dt.isoformat())
    if not bars:
        return None, price_err or f"No price history available for {symbol}"

    daily_prices = _to_most_recent_first(bars, as_of_date)
    if len(daily_prices) < 5:
        return None, f"Insufficient price history for {symbol}: {len(daily_prices)} bars"

    current_price = daily_prices[0]["close"]
    gap_pct = calculate_price_gap(daily_prices, earnings_date, timing="unknown")

    result = analyze_stock(
        symbol, daily_prices, earnings_date, earnings_timing="unknown",
        gap_pct=gap_pct, current_price=current_price, watch_weeks=WATCH_WEEKS,
    )
    if result is None:
        return None, f"PEAD analysis could not be computed for {symbol} (insufficient weekly candle data)"

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    return result, ""
