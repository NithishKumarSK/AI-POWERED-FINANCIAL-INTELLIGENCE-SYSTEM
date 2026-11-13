"""
canslim_screener_service.py -- live orchestrator for core/canslim_screener.py.
Wires 5 already-built sources into the 7 CANSLIM components:

  C, A -- core/sec_financials_service.fetch_quarterly_eps_revenue_series /
          fetch_annual_eps_revenue_series (new this session, SEC XBRL).
  N, S -- core/historical_price_service.py (price/volume), "quote" derived
          the same way market_top_detector_service.py/vcp_screener_service.py do.
  L    -- core/vcp_screener.calculate_relative_strength vs SPY (see
          canslim_screener.py's docstring for why this is reused rather
          than a near-duplicate port).
  I    -- core/institutional_holdings_service.py's 23-well-known-filer
          holder count, an honest PROXY for true institutional sponsorship
          (not a full-market holder count or a real ownership %) --
          canslim_screener.score_institutional_sponsorship() scores this
          path conservatively (halved) to reflect that it's a weaker
          signal than the FMP/Finviz-backed original.
  M    -- SPY (S&P 500 proxy, since ^GSPC isn't a free-tier-resolvable
          symbol via this project's price providers) + "^VIX", both
          already confirmed resolvable via historical_price_service.py.

Per-symbol. Cached on disk per symbol for a day.

LEAKAGE SAFETY: every source above already filters to on/before
as_of_date on its own (SEC XBRL filed-date filtering, price-history
date filtering) -- this module adds no additional filtering because none
is needed beyond what each source already guarantees.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "canslim_screener_cache.json"
CACHE_TTL_DAYS = 1
PRICE_LOOKBACK_DAYS = 420
MARKET_PROXY = "SPY"
VIX_TICKER = "^VIX"


def _to_most_recent_first(bars: list, as_of_date: str) -> list:
    as_of = as_of_date[:10]
    filtered = [b for b in bars if b.get("date", "") <= as_of]
    return list(reversed(filtered))


def _derive_quote(history: list) -> dict:
    if not history:
        return {}
    price = history[0].get("close", 0)
    window = history[:252]
    year_high = max((d.get("high", d.get("close", 0)) for d in window), default=0)
    year_low = min((d.get("low", d.get("close", 0)) for d in window if d.get("low", d.get("close", 0)) > 0), default=0)
    recent_20 = history[:20]
    avg_volume = sum(d.get("volume", 0) for d in recent_20) / len(recent_20) if recent_20 else 0
    return {"price": price, "yearHigh": year_high, "yearLow": year_low, "volume": history[0].get("volume", 0), "avgVolume": avg_volume}


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


def fetch_canslim_analysis(symbol: str, as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """Full 7-component CANSLIM analysis for `symbol` as of a given date.

    Returns (data, error_string). data shape on success:
        {"composite_score": float, "rating": str, "guidance": str,
         "weakest_component": str, "component_scores": {...},
         "threshold_check": {...}, "c": {...}, "a": {...}, ...}
    A missing component degrades that component's score (never a crash);
    the whole analysis only fails if price history itself is unavailable.
    """
    from canslim_screener import (
        calculate_annual_growth, calculate_composite_score_phase3, calculate_institutional_sponsorship,
        calculate_market_direction, calculate_newness, calculate_quarterly_growth, calculate_supply_demand,
        check_minimum_thresholds_phase3,
    )
    from vcp_screener import calculate_relative_strength

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
    historical_mrf = _to_most_recent_first(raw_bars, as_of_date)
    if len(historical_mrf) < 60:
        return None, f"Insufficient price history for {symbol}: {len(historical_mrf)} bars"
    quote = _derive_quote(historical_mrf)

    errors = []

    # C: quarterly earnings
    from sec_financials_service import fetch_annual_eps_revenue_series, fetch_quarterly_eps_revenue_series
    q_series, q_err = fetch_quarterly_eps_revenue_series(symbol, as_of_date)
    c_result = calculate_quarterly_growth(q_series) if q_series else {"score": 0, "error": q_err}
    if q_err:
        errors.append(f"C (quarterly earnings): {q_err}")

    # A: annual growth
    a_series, a_err = fetch_annual_eps_revenue_series(symbol, as_of_date)
    a_result = calculate_annual_growth(a_series) if a_series else {"score": 50, "error": a_err}
    if a_err:
        errors.append(f"A (annual growth): {a_err}")

    # N: newness
    n_result = calculate_newness(quote)

    # S: supply/demand
    s_result = calculate_supply_demand({"historical": historical_mrf})

    # L: leadership / relative strength vs SPY
    spy_raw, spy_err, _c2 = fetch_price_history_for_range(MARKET_PROXY, start_dt.isoformat(), as_of_dt.isoformat())
    spy_mrf = _to_most_recent_first(spy_raw, as_of_date) if spy_raw else []
    l_full = calculate_relative_strength(historical_mrf, spy_mrf)
    l_result = {"score": l_full["score"], "rs_rank_estimate": l_full["rs_rank_estimate"], "weighted_rs": l_full.get("weighted_rs"), "error": l_full.get("error")}
    if l_full.get("error"):
        errors.append(f"L (leadership): {l_full['error']}")

    # I: institutional sponsorship (proxy)
    from institutional_holdings_service import fetch_institutional_holders
    from canslim_screener import SUPERINVESTORS
    inst_data, inst_err = fetch_institutional_holders(symbol, as_of_date)
    if inst_data:
        superinvestors_found = [h["name"] for h in inst_data.get("holders", []) if any(s in h["name"].upper() for s in SUPERINVESTORS)]
        i_result = calculate_institutional_sponsorship(inst_data.get("holder_count", 0), superinvestors_found)
    else:
        i_result = calculate_institutional_sponsorship(0, [])
        if inst_err:
            errors.append(f"I (institutional): {inst_err}")

    # M: market direction (SPY proxy for S&P 500, VIX)
    sp500_quote = _derive_quote(spy_mrf) if spy_mrf else {}
    vix_raw, vix_err, _c3 = fetch_price_history_for_range(VIX_TICKER, start_dt.isoformat(), as_of_dt.isoformat())
    vix_mrf = _to_most_recent_first(vix_raw, as_of_date) if vix_raw else []
    vix_quote = {"price": vix_mrf[0]["close"]} if vix_mrf else None
    m_result = calculate_market_direction(sp500_quote, spy_mrf, vix_quote)
    if not vix_mrf and vix_err:
        errors.append(f"M (VIX): {vix_err}")

    composite = calculate_composite_score_phase3(
        c_score=c_result.get("score", 0), a_score=a_result.get("score", 50), n_score=n_result.get("score", 0),
        s_score=s_result.get("score", 0), l_score=l_result.get("score", 0), i_score=i_result.get("score", 0), m_score=m_result.get("score", 50),
    )
    threshold_check = check_minimum_thresholds_phase3(
        c_score=c_result.get("score", 0), a_score=a_result.get("score", 50), n_score=n_result.get("score", 0),
        s_score=s_result.get("score", 0), l_score=l_result.get("score", 0), i_score=i_result.get("score", 0), m_score=m_result.get("score", 50),
    )

    result = {
        "symbol": symbol, "composite_score": composite["composite_score"], "rating": composite["rating"],
        "rating_description": composite["rating_description"], "guidance": composite["guidance"],
        "weakest_component": composite["weakest_component"], "weakest_score": composite["weakest_score"],
        "component_scores": composite["component_scores"], "threshold_check": threshold_check,
        "c_component": c_result, "a_component": a_result, "n_component": n_result, "s_component": s_result,
        "l_component": l_result, "i_component": i_result, "m_component": m_result,
    }

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    return result, "; ".join(errors)
