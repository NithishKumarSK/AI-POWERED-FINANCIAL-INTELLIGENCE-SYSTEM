"""
value_dividend_screener_service.py -- live orchestrator for
core/value_dividend_screener.py. Reuses the same sec_financials_service
sources as core/dividend_growth_pullback_screener_service.py (its sibling,
built in the same session) plus core/historical_price_service.py for RSI.

Per-symbol. Cached on disk per symbol for a day.

LEAKAGE SAFETY: every SEC source already filters to on/before as_of_date
on its own; price history is filtered the same way every other
price-based service in this project is.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "value_dividend_screener_cache.json"
CACHE_TTL_DAYS = 1
PRICE_LOOKBACK_DAYS = 60


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


def fetch_value_dividend_analysis(symbol: str, as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """Dividend stability + revenue/EPS trend + sustainability composite
    for `symbol` as of a given date.

    Returns (data, error_string). data shape on success:
        {"composite_score": float, "dividend_yield_pct": float|None,
         "dividend_stable": bool, "dividend_growing": bool,
         "revenue_uptrend": bool, "eps_uptrend": bool, "sustainable": bool, ...}
    """
    from dividend_growth_pullback_screener import analyze_payout_sustainability, calculate_rsi
    from value_dividend_screener import (
        analyze_dividend_stability, analyze_earnings_trend, analyze_revenue_trend,
        calculate_composite_score, calculate_profit_margin_score, calculate_stability_score,
    )

    cache_key = f"{symbol}:{as_of_date[:10]}"
    if use_cache:
        cache = _load_cache()
        entry = cache.get(cache_key)
        if entry and (time.time() - entry.get("computed_at", 0)) < CACHE_TTL_DAYS * 86400:
            return entry["data"], ""

    errors = []

    import datetime as _dt
    from historical_price_service import fetch_price_history_for_range

    as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
    start_dt = as_of_dt - _dt.timedelta(days=PRICE_LOOKBACK_DAYS)
    raw_bars, price_err, _coverage = fetch_price_history_for_range(symbol, start_dt.isoformat(), as_of_dt.isoformat())
    if not raw_bars:
        return None, price_err or f"No price history available for {symbol}"

    as_of = as_of_date[:10]
    chrono_bars = [b for b in raw_bars if b.get("date", "") <= as_of]  # LEAKAGE SAFETY
    if len(chrono_bars) < 15:
        return None, f"Insufficient price history for {symbol}: {len(chrono_bars)} bars"
    current_price = chrono_bars[-1]["close"]
    rsi = calculate_rsi([b["close"] for b in chrono_bars])

    from sec_financials_service import (
        fetch_annual_dividend_series, fetch_annual_eps_revenue_series, fetch_cash_flow_coverage, fetch_key_financials,
    )

    div_series, div_err = fetch_annual_dividend_series(symbol, as_of_date)
    if div_err:
        errors.append(f"dividend_series: {div_err}")
    stability = analyze_dividend_stability(div_series) if div_series else {"is_stable": False, "is_growing": False, "volatility_pct": None, "years_of_growth": 0}
    stability_score = calculate_stability_score(stability)
    div_cagr = None
    latest_annual_dividend = None
    if div_series:
        usable = [d for d in div_series if d.get("dividend_per_share")]
        if usable:
            latest_annual_dividend = usable[0]["dividend_per_share"]
            if len(usable) >= 4:
                from dividend_growth_pullback_screener import calculate_cagr
                chrono = list(reversed(usable[:4]))
                div_cagr = calculate_cagr(chrono[0]["dividend_per_share"], chrono[-1]["dividend_per_share"], 3)

    eps_rev_series, eps_err = fetch_annual_eps_revenue_series(symbol, as_of_date)
    if eps_err:
        errors.append(f"eps_revenue_series: {eps_err}")
    revenue_trend = analyze_revenue_trend(eps_rev_series) if eps_rev_series else {"is_uptrend": False, "years_of_growth": 0, "cagr": None}
    eps_trend = analyze_earnings_trend(eps_rev_series) if eps_rev_series else {"is_uptrend": False, "years_of_growth": 0, "cagr": None}

    cash_flow, cf_err = fetch_cash_flow_coverage(symbol, as_of_date)
    if cf_err:
        errors.append(f"cash_flow_coverage: {cf_err}")
    key_fin, fin_err = fetch_key_financials(symbol, as_of_date)
    if fin_err:
        errors.append(f"key_financials: {fin_err}")
    net_income = (key_fin or {}).get("net_income")
    revenue = (key_fin or {}).get("revenue")
    profit_margin = (net_income / revenue * 100) if (net_income and revenue) else None
    profit_margin_score = calculate_profit_margin_score(profit_margin)

    sustainability = analyze_payout_sustainability(cash_flow or {}, net_income)

    dividend_yield_pct = None
    if latest_annual_dividend and current_price:
        dividend_yield_pct = round(latest_annual_dividend / current_price * 100, 2)

    composite_score = calculate_composite_score(div_cagr, stability_score, revenue_trend.get("cagr"), eps_trend.get("cagr"), sustainability.get("sustainable", False), profit_margin_score)

    result = {
        "symbol": symbol, "composite_score": composite_score, "current_price": current_price,
        "dividend_cagr_3yr": div_cagr, "dividend_yield_pct": dividend_yield_pct,
        "dividend_stable": stability.get("is_stable"), "dividend_growing": stability.get("is_growing"),
        "dividend_volatility_pct": stability.get("volatility_pct"), "dividend_years_of_growth": stability.get("years_of_growth"),
        "revenue_uptrend": revenue_trend.get("is_uptrend"), "revenue_cagr_3yr": revenue_trend.get("cagr"),
        "eps_uptrend": eps_trend.get("is_uptrend"), "eps_cagr_3yr": eps_trend.get("cagr"),
        "profit_margin_pct": round(profit_margin, 2) if profit_margin is not None else None,
        "rsi_14": rsi, "sustainable": sustainability.get("sustainable", False),
        "sustainability_note": sustainability.get("sustainability_note"),
    }

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    return result, "; ".join(errors)
