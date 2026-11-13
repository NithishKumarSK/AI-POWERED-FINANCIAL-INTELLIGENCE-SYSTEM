"""
dividend_growth_pullback_screener_service.py -- live orchestrator for
core/dividend_growth_pullback_screener.py. Wires together:
  - core/sec_financials_service.py: fetch_annual_dividend_series (dividend
    CAGR/consistency), fetch_cash_flow_coverage (FCF payout), and
    fetch_key_financials (net income, for the earnings payout ratio and
    profit margin).
  - core/historical_price_service.py: daily closes for RSI(14) and the
    current price (for dividend yield).

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

CACHE_PATH = ROOT / "data" / "dividend_growth_pullback_cache.json"
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


def fetch_dividend_growth_pullback_analysis(symbol: str, as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """Dividend growth quality + RSI pullback-timing analysis for `symbol`
    as of a given date.

    Returns (data, error_string). data shape on success:
        {"composite_score": float, "dividend_cagr_3yr": float|None,
         "dividend_yield_pct": float|None, "rsi_14": float|None,
         "payout_ratio_pct": float|None, "fcf_payout_ratio_pct": float|None,
         "sustainable": bool, "sustainability_note": str, ...}
    A missing component degrades that part of the score (never a crash);
    the analysis only fails outright if price history is unavailable.
    """
    from dividend_growth_pullback_screener import analyze_dividend_growth, analyze_payout_sustainability, calculate_composite_score, calculate_rsi

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

    from sec_financials_service import fetch_annual_dividend_series, fetch_cash_flow_coverage, fetch_key_financials

    div_series, div_err = fetch_annual_dividend_series(symbol, as_of_date)
    growth = analyze_dividend_growth(div_series) if div_series else {"cagr_3yr": None, "consistent": False, "latest_annual_dividend": None, "years_of_growth": 0}
    if div_err:
        errors.append(f"dividend_series: {div_err}")

    cash_flow, cf_err = fetch_cash_flow_coverage(symbol, as_of_date)
    if cf_err:
        errors.append(f"cash_flow_coverage: {cf_err}")

    key_fin, fin_err = fetch_key_financials(symbol, as_of_date)
    net_income = (key_fin or {}).get("net_income")
    revenue = (key_fin or {}).get("revenue")
    if fin_err:
        errors.append(f"key_financials: {fin_err}")

    profit_margin = (net_income / revenue * 100) if (net_income and revenue) else None
    sustainability = analyze_payout_sustainability(cash_flow or {}, net_income)

    dividend_yield_pct = None
    if growth.get("latest_annual_dividend") and current_price:
        dividend_yield_pct = round(growth["latest_annual_dividend"] / current_price * 100, 2)

    composite_score = calculate_composite_score(growth.get("cagr_3yr"), growth.get("consistent", False), profit_margin, rsi)

    result = {
        "symbol": symbol, "composite_score": composite_score,
        "dividend_cagr_3yr": growth.get("cagr_3yr"), "dividend_consistent": growth.get("consistent", False),
        "dividend_years_of_growth": growth.get("years_of_growth", 0), "latest_annual_dividend": growth.get("latest_annual_dividend"),
        "dividend_yield_pct": dividend_yield_pct, "current_price": current_price, "rsi_14": rsi,
        "profit_margin_pct": round(profit_margin, 2) if profit_margin is not None else None,
        "payout_ratio_pct": round(sustainability["payout_ratio"], 2) if sustainability.get("payout_ratio") is not None else None,
        "fcf_payout_ratio_pct": round(sustainability["fcf_payout_ratio"], 2) if sustainability.get("fcf_payout_ratio") is not None else None,
        "fcf_coverage_status": sustainability.get("fcf_coverage_status"), "sustainable": sustainability.get("sustainable", False),
        "sustainability_note": sustainability.get("sustainability_note"),
    }

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    return result, "; ".join(errors)
