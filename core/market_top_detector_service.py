"""
market_top_detector_service.py -- live orchestrator for core/market_top_detector/
(the ported claude-trading-skills market-top-detector). Combines 6 weighted
components into a 0-100 heuristic market-top risk score.

All price history comes from core/historical_price_service.py (no FMP
needed -- FMP's free-tier /quote endpoint returns 402 PREMIUM_REQUIRED for
ETF quotes, confirmed live this session, so "current price"/"52-week high"
for every ETF used here are instead derived directly from each ETF's own
OHLCV history, which is also leakage-safe, unlike a live quote snapshot).
Breadth percentages come from core/market_breadth_service.py (extended
this session with breadth_200dma_pct/breadth_50dma_pct specifically for
this calculator).

Market-wide, NOT symbol-specific -- same category as ftd_status_service.py,
ibd_distribution_day_service.py, macro_regime_service.py. Cached on disk
for a day.

LEAKAGE SAFETY: historical_price_service returns the full available
history; this module filters to bars with date <= as_of_date before any
calculation.

Sentiment gap (disclosed, not hidden): put/call ratio, VIX term structure,
and margin debt YoY have no free, keyless, programmatic source -- even the
source skill only gets them via a human running WebSearch. Only vix_level
(from "^VIX" via historical_price_service) is populated; the other three
sentiment sub-inputs are left None, same as the source skill without a
human collecting them.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "market_top_detector_cache.json"
CACHE_TTL_DAYS = 1
MIN_DAYS = 420  # covers the 200-bar SMA + 252-bar 52wk-high lookback with buffer

INDEX_TICKERS = ("SPY", "QQQ")
ROTATION_TICKERS = ("XLU", "XLP", "XLV", "VNQ", "XLK", "XLC", "XLY")  # QQQ reused from INDEX_TICKERS
LEADING_ETFS = ("ARKK", "WCLD", "IGV", "XBI", "SOXX", "SMH", "KWEB", "TAN")
VIX_TICKER = "^VIX"

_ALL_TICKERS = tuple(dict.fromkeys(INDEX_TICKERS + ROTATION_TICKERS + LEADING_ETFS + (VIX_TICKER,)))


def _to_most_recent_first(bars: list, as_of_date: str) -> list:
    as_of = as_of_date[:10]
    filtered = [b for b in bars if b.get("date", "") <= as_of]
    return list(reversed(filtered))


def _fetch_histories(as_of_date: str) -> Tuple[dict, list]:
    import datetime as _dt
    from historical_price_service import fetch_price_history_for_range

    as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
    start_dt = as_of_dt - _dt.timedelta(days=MIN_DAYS + 30)

    histories = {}
    errors = []
    for ticker in _ALL_TICKERS:
        bars, err, _coverage = fetch_price_history_for_range(ticker, start_dt.isoformat(), as_of_dt.isoformat())
        if not bars:
            errors.append(f"{ticker}: {err or 'no bars returned'}")
            histories[ticker] = []
            continue
        histories[ticker] = _to_most_recent_first(bars, as_of_date)
    return histories, errors


def _derive_quote(history: list) -> Optional[dict]:
    """price = most recent close; yearHigh = max high over trailing ~252 bars."""
    if not history:
        return None
    price = history[0].get("close", 0)
    if price <= 0:
        return None
    window = history[:252]
    year_high = max((d.get("high", d.get("close", 0)) for d in window), default=0)
    return {"price": price, "yearHigh": year_high}


def _distance_from_high_pct(history: list, lookback: int = 252) -> Optional[float]:
    if not history:
        return None
    price = history[0].get("close", 0)
    window = history[:lookback]
    year_high = max((d.get("high", d.get("close", 0)) for d in window), default=0)
    if price <= 0 or year_high <= 0:
        return None
    return (price - year_high) / year_high * 100


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


def compute_market_top_risk(as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """6-component market-top risk composite as of a given date.

    Returns (data, error_string). data shape on success:
        {"composite_score": float, "zone": str, "risk_budget": str,
         "component_scores": {...}, "data_quality": {...}}
    (a trimmed view of market_top_detector.scorer.calculate_composite_score's
    full output, kept under data["_full"] for callers that want it).
    """
    from market_top_detector.breadth_divergence import calculate_breadth_divergence
    from market_top_detector.defensive_rotation import calculate_defensive_rotation
    from market_top_detector.distribution_days import calculate_distribution_days
    from market_top_detector.index_technical import calculate_index_technical
    from market_top_detector.leading_stocks import calculate_leading_stock_health
    from market_top_detector.scorer import calculate_composite_score
    from market_top_detector.sentiment import calculate_sentiment

    cache_key = as_of_date[:10]
    if use_cache:
        cache = _load_cache()
        entry = cache.get(cache_key)
        if entry and (time.time() - entry.get("computed_at", 0)) < CACHE_TTL_DAYS * 86400:
            return entry["data"], ""

    histories, errors = _fetch_histories(as_of_date)
    sp500_hist = histories.get("SPY", [])
    nasdaq_hist = histories.get("QQQ", [])
    if not sp500_hist and not nasdaq_hist:
        return None, "; ".join(errors) if errors else "No price history available for SPY or QQQ"

    dd_result = calculate_distribution_days(sp500_hist, nasdaq_hist)
    tech_result = calculate_index_technical(sp500_hist, nasdaq_hist)

    rotation_hist = {t: histories.get(t, []) for t in ROTATION_TICKERS}
    rotation_hist["QQQ"] = nasdaq_hist
    rotation_result = calculate_defensive_rotation(rotation_hist)

    import market_breadth_service
    breadth_data, breadth_err = market_breadth_service.fetch_market_breadth_snapshot(as_of_date)
    if breadth_err:
        errors.append(f"market_breadth: {breadth_err}")
    breadth_200dma = (breadth_data or {}).get("breadth_200dma_pct")
    breadth_50dma = (breadth_data or {}).get("breadth_50dma_pct")
    spy_distance = _distance_from_high_pct(sp500_hist)
    breadth_result = calculate_breadth_divergence(breadth_200dma, breadth_50dma, spy_distance if spy_distance is not None else 0.0)

    leading_quotes = {}
    for symbol in LEADING_ETFS:
        q = _derive_quote(histories.get(symbol, []))
        if q:
            leading_quotes[symbol] = q
    leading_historical = {symbol: histories.get(symbol, []) for symbol in LEADING_ETFS}
    leading_result = calculate_leading_stock_health(leading_quotes, leading_historical)

    vix_hist = histories.get(VIX_TICKER, [])
    vix_level = vix_hist[0].get("close") if vix_hist else None
    sentiment_result = calculate_sentiment(vix_level=vix_level)

    component_scores = {
        "distribution_days": dd_result["score"],
        "leading_stocks": leading_result["score"],
        "defensive_rotation": rotation_result["score"],
        "breadth_divergence": breadth_result["score"],
        "index_technical": tech_result["score"],
        "sentiment": sentiment_result["score"],
    }
    data_availability = {
        "distribution_days": bool(sp500_hist or nasdaq_hist),
        "leading_stocks": leading_result.get("data_available", False),
        "defensive_rotation": rotation_result.get("data_available", False),
        "breadth_divergence": breadth_result.get("data_available", False),
        "index_technical": tech_result.get("data_available", False),
        "sentiment": sentiment_result.get("data_available", False),
    }

    composite = calculate_composite_score(component_scores, data_availability)

    result = {
        "composite_score": composite["composite_score"],
        "zone": composite["zone"],
        "risk_budget": composite["risk_budget"],
        "component_scores": component_scores,
        "data_quality": composite["data_quality"],
        "_full": {
            "composite": composite,
            "distribution_days": dd_result,
            "leading_stocks": leading_result,
            "defensive_rotation": rotation_result,
            "breadth_divergence": breadth_result,
            "index_technical": tech_result,
            "sentiment": sentiment_result,
        },
    }

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    err = "; ".join(errors) if errors else ""
    return result, err
