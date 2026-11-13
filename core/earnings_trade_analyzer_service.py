"""
earnings_trade_analyzer_service.py -- live orchestrator for
core/earnings_trade_analyzer.py. Finds the symbol's most recent
earnings-tagged 8-K (via core/free_news_service.fetch_most_recent_earnings_8k,
same source built for pead_screener_service.py -- see that function's
docstring for why FMP's own earnings-calendar couldn't be used), fetches
daily price history via historical_price_service.py, and runs the
5-factor post-earnings reaction scoring.

RECENCY CONSTRAINT (disclosed, not hidden): earnings_trade_analyzer.py's
volume-trend factor assumes the most-recent bars in daily_prices are close
to the earnings date (the source skill's own default --lookback-days is
2-5) -- this service only runs the analysis when the most recent earnings
happened within RECENCY_DAYS of as_of_date, returning an honest "stale"
error otherwise rather than silently misinterpreting an old earnings date
as a "recent reaction."

Per-symbol -- same category as pead_screener_service.py. Cached on disk
per symbol for a day.

LEAKAGE SAFETY: both the earnings-8K lookup and the price history are
filtered to on/before as_of_date before any calculation.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "earnings_trade_analyzer_cache.json"
CACHE_TTL_DAYS = 1
RECENCY_DAYS = 10  # matches the source skill's own near-term scope (lookback-days 2-5, with margin)
EARNINGS_LOOKBACK_DAYS = RECENCY_DAYS + 5
PRICE_LOOKBACK_DAYS = 310  # >= 200 TRADING days (260 calendar days under-covers this once weekends/holidays are excluded)


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


def fetch_earnings_trade_analysis(symbol: str, as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """5-factor post-earnings reaction score for `symbol` as of a given
    date. Only runs when the most recent earnings happened within
    RECENCY_DAYS of as_of_date (see module docstring).

    Returns (data, error_string). data shape on success (see
    core.earnings_trade_analyzer.analyze_stock for the full field list):
        {"composite": {"composite_score": float, "grade": str, ...},
         "gap": {...}, "pre_earnings_trend": {...}, ...}
    """
    from earnings_trade_analyzer import analyze_stock

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
    as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
    earnings_dt = _dt.datetime.strptime(earnings_date[:10], "%Y-%m-%d").date()
    days_since_earnings = (as_of_dt - earnings_dt).days
    if days_since_earnings > RECENCY_DAYS:
        return None, f"Most recent earnings for {symbol} ({earnings_date}) is {days_since_earnings} days old, beyond the {RECENCY_DAYS}-day recency window this analyzer needs"

    from historical_price_service import fetch_price_history_for_range
    start_dt = as_of_dt - _dt.timedelta(days=PRICE_LOOKBACK_DAYS)
    bars, price_err, _coverage = fetch_price_history_for_range(symbol, start_dt.isoformat(), as_of_dt.isoformat())
    if not bars:
        return None, price_err or f"No price history available for {symbol}"

    daily_prices = _to_most_recent_first(bars, as_of_date)
    if len(daily_prices) < 50:
        return None, f"Insufficient price history for {symbol}: {len(daily_prices)} bars"

    result = analyze_stock(daily_prices, earnings_date, timing="unknown")

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    return result, ""
