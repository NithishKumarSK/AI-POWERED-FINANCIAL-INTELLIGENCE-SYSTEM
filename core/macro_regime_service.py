"""
macro_regime_service.py -- live orchestrator for core/macro_regime/ (the
ported claude-trading-skills macro-regime-detector). Fetches real daily
price history for the 8 ETF tickers the 6 calculators need (RSP, SPY, HYG,
LQD, IWM, TLT, XLY, XLP) via this project's existing, already-battle-tested
core/historical_price_service.py (not a new data client -- reuses what's
already here), runs all 6 calculators + the composite scorer, and returns
the full regime classification.

Yield curve tries the primary Treasury-rate path (FMP's /stable/treasury-rates,
tools/fmp_client.py) but falls back to the keyless SHY/TLT proxy in
practice: confirmed live this session that FMP's free tier hard-caps this
endpoint at ~63 days of history regardless of the from/to range requested,
while calculate_yield_curve's primary path needs >= 12 months of monthly
data to run its SMA/crossover analysis -- so it correctly, automatically
falls through to the proxy every time on the free tier. Left wired in (not
removed) since it will start working the moment a paid FMP plan lifts that
history cap, and the fallback is honest, not a silent failure.

Market-wide, NOT symbol-specific -- same category as macro_data_service.py
and market_breadth_service.py. Cached on disk (price history itself is
already cached by historical_price_service; this module additionally
caches the computed regime result for a day, since recomputing 6
calculators from ~2 years of daily bars on every prediction would be
wasteful for a signal that only meaningfully changes monthly).

LEAKAGE SAFETY: historical_price_service.fetch_price_history returns the
full available history; this module filters to bars with date <= as_of_date
before any calculation, so a historical backtest origin never sees future
price bars -- same discipline as every other context-enrichment source.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "macro_regime_cache.json"
CACHE_TTL_DAYS = 1
MIN_DAYS = 800  # ~2.2 years -- covers the 24-month crossover lookback the calculators use

_TICKERS = ("RSP", "SPY", "HYG", "LQD", "IWM", "TLT", "XLY", "XLP", "SHY")


def _bars_to_history(bars: list, as_of_date: str) -> list:
    """historical_price_service returns ASC-sorted {date,close,...} dicts;
    the macro_regime calculators expect MOST-RECENT-FIRST, filtered to
    on/before as_of_date (LEAKAGE SAFETY)."""
    as_of = as_of_date[:10]
    filtered = [b for b in bars if b.get("date", "") <= as_of]
    return list(reversed(filtered))


def _fetch_all_histories(as_of_date: str) -> Tuple[dict, list]:
    # fetch_price_history() (the simpler, cached helper) does NOT include
    # yfinance in its fallback chain -- confirmed live this session: it
    # failed on RSP and SHY (RapidAPI TradingView 404 + NASDAQ external
    # provider empty) even though yfinance itself resolves RSP fine.
    # fetch_price_history_for_range() does include yfinance as a fallback,
    # so it's used here instead for these less commonly-traded ETF tickers.
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
        histories[ticker] = _bars_to_history(bars, as_of_date)
    return histories, errors


def _fetch_treasury_rates(as_of_date: str) -> Tuple[Optional[list], str]:
    """FMP's /stable/treasury-rates response already has 'date'/'year10'/
    'year2' keys exactly matching what macro_regime.yield_curve.calculate_yield_curve
    expects for its primary (non-proxy) path -- no field renaming needed.
    LEAKAGE SAFETY: filtered to date <= as_of_date."""
    sys.path.insert(1, str(ROOT / "tools"))
    from fmp_client import fmp_get

    result = fmp_get("treasury-rates")
    if result.get("status") != "SUCCESS":
        return None, result.get("message", "FMP treasury-rates request failed")
    rows = result.get("data") or []
    as_of = as_of_date[:10]
    filtered = [r for r in rows if r.get("date", "") <= as_of]
    if not filtered:
        return None, "No treasury-rates entries on/before as_of_date"
    return filtered, ""


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


def compute_macro_regime(as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """Full 6-component macro regime classification as of a given date.

    Returns (data, error_string). data shape on success:
        {"composite_score": float, "zone": str, "current_regime": str,
         "regime_label": str, "confidence": str, "component_scores": {...}}
    (a trimmed view of the full classify_regime/calculate_composite_score
    output -- the full detail is under data["_full"] for callers that want it).
    """
    from macro_regime.concentration import calculate_concentration
    from macro_regime.yield_curve import calculate_yield_curve
    from macro_regime.credit_conditions import calculate_credit_conditions
    from macro_regime.size_factor import calculate_size_factor
    from macro_regime.equity_bond import calculate_equity_bond
    from macro_regime.sector_rotation import calculate_sector_rotation
    from macro_regime.scorer import calculate_composite_score, classify_regime

    cache_key = as_of_date[:10]
    if use_cache:
        cache = _load_cache()
        entry = cache.get(cache_key)
        if entry and (time.time() - entry.get("computed_at", 0)) < CACHE_TTL_DAYS * 86400:
            return entry["data"], ""

    histories, errors = _fetch_all_histories(as_of_date)
    if not any(histories.values()):
        return None, "; ".join(errors) if errors else "No price history available for any required ticker"

    treasury_rates, treasury_err = _fetch_treasury_rates(as_of_date)
    if treasury_err:
        errors.append(f"treasury_rates: {treasury_err}")

    component_results = {
        "concentration": calculate_concentration(histories["RSP"], histories["SPY"]),
        "yield_curve": calculate_yield_curve(
            treasury_rates=treasury_rates, shy_history=histories["SHY"], tlt_history=histories["TLT"]
        ),
        "credit_conditions": calculate_credit_conditions(histories["HYG"], histories["LQD"]),
        "size_factor": calculate_size_factor(histories["IWM"], histories["SPY"]),
        "equity_bond": calculate_equity_bond(histories["SPY"], histories["TLT"]),
        "sector_rotation": calculate_sector_rotation(histories["XLY"], histories["XLP"]),
    }

    component_scores = {k: v.get("score", 0) for k, v in component_results.items()}
    data_availability = {k: v.get("data_available", False) for k, v in component_results.items()}
    composite = calculate_composite_score(component_scores, data_availability)
    regime = classify_regime(component_results)

    result = {
        "composite_score": composite["composite_score"],
        "zone": composite["zone"],
        "current_regime": regime["current_regime"],
        "regime_label": regime["regime_label"],
        "confidence": regime["confidence"],
        "component_scores": component_scores,
        "component_directions": {k: v.get("direction", "unknown") for k, v in component_results.items()},
        "_full": {"composite": composite, "regime": regime, "components": component_results},
    }

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    err = "; ".join(errors) if errors else ""
    return result, err
