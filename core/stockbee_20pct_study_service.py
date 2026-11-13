"""
stockbee_20pct_study_service.py -- live orchestrator for
core/stockbee_20pct_study.py. Fetches daily price history via
historical_price_service.py and checks whether `as_of_date` qualifies as
a 20%+-over-5-days move event for the symbol.

Per-symbol. Cached on disk per symbol for a day.

LEAKAGE SAFETY: historical_price_service returns the full available
history; this module filters to bars with date <= as_of_date before any
calculation.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "stockbee_20pct_study_cache.json"
CACHE_TTL_DAYS = 1
PRICE_LOOKBACK_DAYS = 290  # covers the 252-bar 52wk window + lookback with buffer


def _chrono_bars(raw_bars: list, as_of_date: str) -> list:
    from stockbee_20pct_study import Bar

    as_of = as_of_date[:10]
    filtered = [b for b in raw_bars if b.get("date", "") <= as_of]  # LEAKAGE SAFETY
    return [Bar(date=b["date"], open=b["open"], high=b["high"], low=b["low"], close=b["close"], volume=b.get("volume", 0)) for b in filtered]


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


def fetch_20pct_study(symbol: str, as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """Checks whether `symbol` had a 20%+-over-5-days move as of a given
    date, and if so, classifies and scores it.

    Returns (data, error_string). data is None (with error_string=="") when
    there's simply no qualifying event -- an honest absence, not a failure.
    error_string is only non-empty on a real fetch/data problem.
    """
    from stockbee_20pct_study import detect_twenty_pct_event

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

    bars = _chrono_bars(raw_bars, as_of_date)
    if len(bars) < 10:
        return None, f"Insufficient price history for {symbol}: {len(bars)} bars"

    result = detect_twenty_pct_event(bars, as_of=as_of_date[:10])

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    return result, ""
