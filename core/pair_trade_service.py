"""
pair_trade_service.py -- live orchestrator for core/pair_trade_analyzer.py.
Fetches both symbols' price history via historical_price_service.py,
aligns them to common trading dates, and runs the cointegration/z-score
pipeline.

Per-pair (not market-wide, not single-symbol) -- a new category, but
reuses the same historical_price_service.py everything else here does.
Cached on disk per (symbol_a, symbol_b) pair for a day.

LEAKAGE SAFETY: historical_price_service returns the full available
history; this module filters to bars with date <= as_of_date before any
calculation.

NOT wired into feature_packet/gemini_stock_prediction_agent.py: the main
prediction pipeline runs on one symbol at a time with no natural "partner
symbol" to pair it against (the skill's own pair-discovery step, which
would have picked one, needs the premium-gated FMP universe -- see
pair_trade_analyzer.py's docstring). Same category as
core/portfolio_tools/options_pricer.py: a real, tested, standalone utility
callable directly for any two symbols, not force-fit into the single-
symbol feature vector.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "pair_trade_cache.json"
CACHE_TTL_DAYS = 1
LOOKBACK_DAYS = 365
MIN_OBSERVATIONS = 90  # need enough for a meaningful rolling z-score window


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


def _align_by_date(bars_a: list, bars_b: list) -> Tuple[list, list, list]:
    """Intersect on common dates, chronological order preserved."""
    by_date_a = {b["date"]: b["close"] for b in bars_a}
    by_date_b = {b["date"]: b["close"] for b in bars_b}
    common_dates = sorted(set(by_date_a) & set(by_date_b))
    prices_a = [by_date_a[d] for d in common_dates]
    prices_b = [by_date_b[d] for d in common_dates]
    return common_dates, prices_a, prices_b


def fetch_pair_trade_signal(
    symbol_a: str, symbol_b: str, as_of_date: str, entry_zscore: float = 2.0, use_cache: bool = True,
) -> Tuple[Optional[dict], str]:
    """Pairs-trading spread analysis between symbol_a and symbol_b as of a
    given date.

    Returns (data, error_string). data shape on success (see
    core.pair_trade_analyzer.analyze_pair for the full field list):
        {"symbol_a": str, "symbol_b": str, "current_zscore": float,
         "signal": str, "cointegration": {...}, "half_life_days": float|None}
    """
    from pair_trade_analyzer import analyze_pair

    pair_key = ":".join(sorted([symbol_a.upper(), symbol_b.upper()])) + f":{as_of_date[:10]}"
    if use_cache:
        cache = _load_cache()
        entry = cache.get(pair_key)
        if entry and (time.time() - entry.get("computed_at", 0)) < CACHE_TTL_DAYS * 86400:
            return entry["data"], ""

    import datetime as _dt
    from historical_price_service import fetch_price_history_for_range

    as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
    start_dt = as_of_dt - _dt.timedelta(days=LOOKBACK_DAYS + 30)
    as_of = as_of_date[:10]

    bars_a, err_a, _ = fetch_price_history_for_range(symbol_a, start_dt.isoformat(), as_of_dt.isoformat())
    bars_b, err_b, _ = fetch_price_history_for_range(symbol_b, start_dt.isoformat(), as_of_dt.isoformat())

    if not bars_a:
        return None, err_a or f"No price history available for {symbol_a}"
    if not bars_b:
        return None, err_b or f"No price history available for {symbol_b}"

    bars_a = [b for b in bars_a if b.get("date", "") <= as_of]  # LEAKAGE SAFETY
    bars_b = [b for b in bars_b if b.get("date", "") <= as_of]

    _dates, prices_a, prices_b = _align_by_date(bars_a, bars_b)
    if len(prices_a) < MIN_OBSERVATIONS:
        return None, f"Insufficient aligned history for {symbol_a}/{symbol_b}: {len(prices_a)} common dates, need >= {MIN_OBSERVATIONS}"

    try:
        result = analyze_pair(symbol_a, symbol_b, prices_a, prices_b, entry_zscore=entry_zscore)
    except ValueError as exc:
        return None, str(exc)

    if use_cache:
        cache = _load_cache()
        cache[pair_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    return result, ""
