"""
ftd_status_service.py -- live orchestrator for core/ftd_detector.py (the
ported claude-trading-skills ftd-detector state machine). Fetches real
daily price history for SPY (S&P 500 proxy) and QQQ (NASDAQ proxy) via
this project's existing core/historical_price_service.py, runs the
correction -> rally attempt -> Follow-Through-Day state machine on each,
and returns the combined market state.

Market-wide, NOT symbol-specific -- same category as macro_regime_service.py
and market_breadth_service.py. Cached on disk for a day since the FTD state
only meaningfully changes on new daily bars.

LEAKAGE SAFETY: historical_price_service returns the full available
history; this module filters to bars with date <= as_of_date before any
calculation, so a historical backtest origin never sees future price bars
-- same discipline as every other context-enrichment source.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "ftd_status_cache.json"
CACHE_TTL_DAYS = 1
MIN_DAYS = 120  # covers the 60-day analysis window + 40-day swing-low lookback

_TICKERS = ("SPY", "QQQ")


def _filter_chronological(bars: list, as_of_date: str) -> list:
    """historical_price_service returns ASC-sorted (chronological,
    oldest-first) {date,close,...} dicts -- exactly what ftd_detector's
    analyze_single_index expects. Filter to on/before as_of_date
    (LEAKAGE SAFETY)."""
    as_of = as_of_date[:10]
    return [b for b in bars if b.get("date", "") <= as_of]


def _fetch_histories(as_of_date: str) -> Tuple[dict, list]:
    import datetime as _dt
    from historical_price_service import fetch_price_history_for_range

    as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
    start_dt = as_of_dt - _dt.timedelta(days=MIN_DAYS + 30)

    histories = {}
    errors = []
    for ticker in _TICKERS:
        bars, err, _coverage = fetch_price_history_for_range(
            ticker, start_dt.isoformat(), as_of_dt.isoformat()
        )
        if not bars:
            errors.append(f"{ticker}: {err or 'no bars returned'}")
            histories[ticker] = []
            continue
        histories[ticker] = _filter_chronological(bars, as_of_date)
    return histories, errors


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


def compute_ftd_status(as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """O'Neil Follow-Through Day market state as of a given date.

    Returns (data, error_string). data shape on success:
        {"combined_state": str, "dual_confirmation": bool, "ftd_index": str|None,
         "sp500_state": str, "nasdaq_state": str,
         "sp500_correction_depth_pct": float|None, "nasdaq_correction_depth_pct": float|None}
    (a trimmed view of core.ftd_detector.get_market_state's full output,
    which is kept under data["_full"] for callers that want it).
    """
    from ftd_detector import get_market_state

    cache_key = as_of_date[:10]
    if use_cache:
        cache = _load_cache()
        entry = cache.get(cache_key)
        if entry and (time.time() - entry.get("computed_at", 0)) < CACHE_TTL_DAYS * 86400:
            return entry["data"], ""

    histories, errors = _fetch_histories(as_of_date)
    if not histories.get("SPY") and not histories.get("QQQ"):
        return None, "; ".join(errors) if errors else "No price history available for SPY or QQQ"

    full = get_market_state(histories.get("SPY", []), histories.get("QQQ", []))

    result = {
        "combined_state": full["combined_state"],
        "dual_confirmation": full["dual_confirmation"],
        "ftd_index": full["ftd_index"],
        "sp500_state": full["sp500"].get("state"),
        "nasdaq_state": full["nasdaq"].get("state"),
        "sp500_correction_depth_pct": full["sp500"].get("correction_depth_pct"),
        "nasdaq_correction_depth_pct": full["nasdaq"].get("correction_depth_pct"),
        "_full": full,
    }

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    err = "; ".join(errors) if errors else ""
    return result, err
