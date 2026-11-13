"""
downtrend_duration_service.py -- live orchestrator for
core/downtrend_duration_analyzer.py, answering "how long and how deep have
THIS symbol's past corrections typically run" from its own price history
(see that module's docstring for why this is a narrower scope than the
source skill's cross-universe sector/market-cap survey).

Per-symbol (unlike ftd_status_service.py/ibd_distribution_day_service.py/
market_top_detector_service.py, which are market-wide) -- same category as
historical_price_service.py itself. Cached on disk per symbol for a day.

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

CACHE_PATH = ROOT / "data" / "downtrend_duration_cache.json"
CACHE_TTL_DAYS = 1
LOOKBACK_YEARS = 5
PEAK_TROUGH_WINDOW = 20
MIN_DEPTH_PCT = 5.0
MIN_DURATION_DAYS = 3
MIN_BARS_REQUIRED = PEAK_TROUGH_WINDOW * 2 + 1


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


def fetch_downtrend_stats(symbol: str, as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """Downtrend duration/depth statistics for `symbol` as of a given date.

    Returns (data, error_string). data shape on success:
        {"total_downtrends": int, "median_duration_days": int, "mean_duration_days": float,
         "p75_duration_days": int, "p90_duration_days": int,
         "most_recent_downtrend": {...} | None}
    """
    from downtrend_duration_analyzer import compute_statistics, detect_peaks_troughs, find_downtrends

    cache_key = f"{symbol}:{as_of_date[:10]}"
    if use_cache:
        cache = _load_cache()
        entry = cache.get(cache_key)
        if entry and (time.time() - entry.get("computed_at", 0)) < CACHE_TTL_DAYS * 86400:
            return entry["data"], ""

    import datetime as _dt
    from historical_price_service import fetch_price_history_for_range

    as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
    start_dt = as_of_dt - _dt.timedelta(days=LOOKBACK_YEARS * 365 + 30)

    bars, err, _coverage = fetch_price_history_for_range(symbol, start_dt.isoformat(), as_of_dt.isoformat())
    if not bars:
        return None, err or f"No price history available for {symbol}"

    as_of = as_of_date[:10]
    bars = [b for b in bars if b.get("date", "") <= as_of]  # LEAKAGE SAFETY
    if len(bars) < MIN_BARS_REQUIRED:
        return None, f"Insufficient history for {symbol}: {len(bars)} bars, need >= {MIN_BARS_REQUIRED}"

    dates = [b["date"] for b in bars]
    closes = [b["close"] for b in bars]

    peaks, troughs = detect_peaks_troughs(closes, PEAK_TROUGH_WINDOW)
    downtrends = find_downtrends(dates, closes, peaks, troughs, MIN_DEPTH_PCT, MIN_DURATION_DAYS)
    stats = compute_statistics(downtrends)

    most_recent = max(downtrends, key=lambda d: d["peak_idx"]) if downtrends else None

    result = {
        "total_downtrends": stats["total_downtrends"],
        "median_duration_days": stats["median_duration_days"],
        "mean_duration_days": stats["mean_duration_days"],
        "p75_duration_days": stats["p75_duration_days"],
        "p90_duration_days": stats["p90_duration_days"],
        "most_recent_downtrend": most_recent,
    }

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    return result, ""
