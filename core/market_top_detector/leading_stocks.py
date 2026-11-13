"""
Component 2: Leading Stock Health (Weight: 20%). Ported from
calculators/leading_stock_calculator.py -- static basket only; the source
skill's dynamic 20-ETF candidate-pool basket selection (select_dynamic_basket,
which needs a live quote for every candidate) was not ported, to keep this
to a single, fixed, well-known basket with no extra data dependency.

Default ETF Basket: ARKK, WCLD, IGV, XBI, SOXX, SMH, KWEB, TAN.

Unlike the source skill (which takes `quotes` from an FMP batch-quote call),
core/market_top_detector_service.py derives the "quote" dict locally from
each ETF's own OHLCV history (price = most recent close, yearHigh = max
high over the trailing ~252 bars) -- FMP's free tier returns 402 PREMIUM_REQUIRED
for ETF quotes (confirmed live this session; stock quotes like AAPL work,
ETF quotes like QQQ/ARKK/XLU do not), and this project already has
historical_price_service.py, which is both free and leakage-safe (point-in-
time correct for backtesting) where a live quote snapshot wouldn't be.
"""
from __future__ import annotations

from typing import Optional

DEFAULT_LEADING_ETFS = ["ARKK", "WCLD", "IGV", "XBI", "SOXX", "SMH", "KWEB", "TAN"]

MIN_HISTORY_BARS = 50


def calculate_leading_stock_health(quotes: dict, historical: dict, etf_list: Optional[list] = None) -> dict:
    """
    Args:
        quotes: {symbol: {"price": float, "yearHigh": float}}
        historical: {symbol: most-recent-first OHLCV list, ~60+ days}
        etf_list: explicit symbol list, defaults to DEFAULT_LEADING_ETFS.
    """
    eval_list = list(etf_list) if etf_list is not None else list(DEFAULT_LEADING_ETFS)
    total_attempted = len(eval_list)
    fetch_successes = 0
    partial_data_count = 0

    etf_scores = []
    etf_details = {}
    for symbol in eval_list:
        quote = quotes.get(symbol)
        hist = historical.get(symbol, [])
        if not quote:
            continue
        if len(hist) >= MIN_HISTORY_BARS:
            fetch_successes += 1
        else:
            partial_data_count += 1
        detail = _evaluate_etf(quote, hist)
        etf_scores.append(detail["deterioration_score"])
        etf_details[symbol] = detail

    fetch_success_rate = fetch_successes / total_attempted if total_attempted > 0 else 0.0

    if not etf_scores:
        return {
            "score": 50, "signal": "INSUFFICIENT DATA", "etf_details": {}, "etfs_evaluated": 0,
            "etfs_deteriorating": 0, "data_available": False, "fetch_success_rate": fetch_success_rate,
            "partial_data_count": partial_data_count, "basket": eval_list,
        }

    data_available = fetch_success_rate >= 0.75
    avg_deterioration = sum(etf_scores) / len(etf_scores)
    deteriorating_count = sum(1 for s in etf_scores if s >= 50)
    deteriorating_pct = deteriorating_count / len(etf_scores)

    final_score = min(100, avg_deterioration * 1.3) if deteriorating_pct >= 0.60 else avg_deterioration
    final_score = round(min(100, max(0, final_score)))

    if final_score >= 70:
        signal = "CRITICAL: Leadership broadly deteriorating"
    elif final_score >= 50:
        signal = "WARNING: Multiple leaders weakening"
    elif final_score >= 30:
        signal = "CAUTION: Some leaders showing strain"
    else:
        signal = "HEALTHY: Leadership intact"

    return {
        "score": final_score, "signal": signal, "avg_deterioration": round(avg_deterioration, 1),
        "etfs_evaluated": len(etf_scores), "etfs_deteriorating": deteriorating_count,
        "deteriorating_pct": round(deteriorating_pct * 100, 1), "amplified": deteriorating_pct >= 0.60,
        "etf_details": etf_details, "data_available": data_available,
        "fetch_success_rate": round(fetch_success_rate, 2), "partial_data_count": partial_data_count,
        "basket": eval_list,
    }


def _evaluate_etf(quote: dict, history: list) -> dict:
    score = 0
    flags = []
    price = quote.get("price", 0)
    year_high = quote.get("yearHigh", 0)

    distance_pct = 0.0
    if year_high > 0:
        distance_pct = (price - year_high) / year_high * 100
        if distance_pct <= -25:
            score += 40
            flags.append(f">{abs(distance_pct):.0f}% below 52wk high (bear territory)")
        elif distance_pct <= -15:
            score += 30
            flags.append(f"{abs(distance_pct):.0f}% below 52wk high (correction)")
        elif distance_pct <= -10:
            score += 20
            flags.append(f"{abs(distance_pct):.0f}% below 52wk high")
        elif distance_pct <= -5:
            score += 10
            flags.append(f"{abs(distance_pct):.0f}% below 52wk high")

    if history and len(history) >= 50:
        closes = [d.get("close", d.get("adjClose", 0)) for d in history]
        sma50 = sum(closes[:50]) / 50
        if price < sma50:
            score += 20
            flags.append(f"Below 50DMA (${sma50:.2f})")
        if len(closes) >= 200:
            sma200 = sum(closes[:200]) / 200
            if price < sma200:
                score += 20
                flags.append(f"Below 200DMA (${sma200:.2f})")
        elif price < sma50 * 0.95:
            score += 10
            flags.append("Likely below 200DMA (estimated)")
    elif history and len(history) >= 20:
        closes = [d.get("close", d.get("adjClose", 0)) for d in history]
        sma20 = sum(closes[:20]) / 20
        if price < sma20:
            score += 15
            flags.append(f"Below 20DMA (${sma20:.2f})")

    if history and len(history) >= 20 and _detect_lower_highs(history):
        score += 20
        flags.append("Lower highs pattern detected")

    return {
        "deterioration_score": min(100, score), "price": price, "year_high": year_high,
        "distance_from_high_pct": round(distance_pct, 1), "flags": flags,
    }


def _detect_lower_highs(history: list, lookback: int = 20) -> bool:
    if len(history) < lookback:
        return False
    highs = [d.get("high", d.get("close", 0)) for d in history[:lookback]]
    swing_highs = []
    for i in range(1, len(highs) - 1):
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            swing_highs.append(highs[i])
    if len(swing_highs) < 2:
        return False
    return swing_highs[0] < swing_highs[1]
