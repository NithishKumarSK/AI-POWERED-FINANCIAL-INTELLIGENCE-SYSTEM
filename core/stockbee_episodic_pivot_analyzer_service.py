"""
stockbee_episodic_pivot_analyzer_service.py -- live orchestrator for
core/stockbee_episodic_pivot_analyzer.py. The source skill is
"catalyst-first" and does not discover news itself; this service supplies
a real catalyst event from two sources, tried in order:

1. core/earnings_trade_analyzer_service.py's recent-earnings result
   (LEAKAGE-SAFE -- same recency window/8-K-date discipline as that
   service). catalyst_type="earnings", source_grade/source_score carried
   over from its composite.
2. core/free_news_service.fetch_yahoo_headline_tags's live RSS headline
   titles (LIVE-ONLY -- no historical capability, same as every other
   Yahoo-headline use in this project), classified via this module's own
   keyword table.

If neither resolves a real catalyst, this returns an honest "no catalyst
identified" error rather than fabricating a neutral/default one --
matching the source skill's own catalyst-first design.

Per-symbol. Cached on disk per symbol for a day (only meaningful for the
earnings-sourced path; the Yahoo-headline path is gated to
_origin_is_recent by the caller, same as free_news_service's other
live-only functions).

LEAKAGE SAFETY: the earnings-sourced path inherits
earnings_trade_analyzer_service's own as_of_date filtering; price bars
here are filtered to on/before as_of_date before any calculation.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "stockbee_episodic_pivot_cache.json"
CACHE_TTL_DAYS = 1
PRICE_LOOKBACK_DAYS = 90
MAX_RISK_PCT = 10.0  # matches the source skill's own --max-risk-pct default


def _build_catalyst_event(symbol: str, as_of_date: str) -> Tuple[Optional[dict], str]:
    from earnings_trade_analyzer_service import fetch_earnings_trade_analysis
    eta_data, _eta_err = fetch_earnings_trade_analysis(symbol, as_of_date)
    if eta_data:
        from free_news_service import fetch_most_recent_earnings_8k
        earnings_info, _ = fetch_most_recent_earnings_8k(symbol, as_of_date)
        composite = eta_data.get("composite", {})
        return {
            "symbol": symbol,
            "event_date": (earnings_info or {}).get("earnings_date"),
            "catalyst_type": "earnings",
            "headline": f"Post-earnings reaction for {symbol}",
            "summary": "earnings-trade-analyzer input",
            "source_input": "earnings_trade_analyzer",
            "source_grade": composite.get("grade"),
            "source_score": composite.get("composite_score"),
            "gap_pct": eta_data.get("gap", {}).get("gap_pct"),
            "catalyst_reasons": ["source:earnings-trade-analyzer"],
        }, ""

    from free_news_service import fetch_yahoo_headline_tags
    from stockbee_episodic_pivot_analyzer import classify_catalyst
    yh_data, yh_err = fetch_yahoo_headline_tags(symbol)
    if yh_data and yh_data.get("titles"):
        combined_text = " | ".join(yh_data["titles"])
        catalyst_type, reasons = classify_catalyst({"headline": combined_text})
        if catalyst_type != "unknown":
            return {
                "symbol": symbol,
                "event_date": as_of_date[:10],  # live-only -- "now" is the only point-in-time this has
                "catalyst_type": catalyst_type,
                "headline": yh_data["titles"][0],
                "summary": combined_text[:500],
                "source_input": "yahoo_headlines_live",
                "catalyst_reasons": reasons,
            }, ""
        return None, "No catalyst keyword matched in current Yahoo headlines"

    return None, yh_err or f"No earnings or headline-based catalyst identified for {symbol}"


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


def fetch_episodic_pivot_analysis(symbol: str, as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """Day-1 Episodic Pivot analysis for `symbol` as of a given date.

    Returns (data, error_string). data shape on success (see
    core.stockbee_episodic_pivot_analyzer.analyze_candidate for the full
    field list):
        {"catalyst_type": str, "ep_type": str, "state": str, "rating": str,
         "composite_score": float, ...}
    None (with a non-empty error) when no real catalyst could be
    identified -- never a fabricated one.
    """
    cache_key = f"{symbol}:{as_of_date[:10]}"
    if use_cache:
        cache = _load_cache()
        entry = cache.get(cache_key)
        if entry and (time.time() - entry.get("computed_at", 0)) < CACHE_TTL_DAYS * 86400:
            return entry["data"], ""

    event, event_err = _build_catalyst_event(symbol, as_of_date)
    if not event:
        return None, event_err
    if event.get("event_date") is None:
        event["event_date"] = as_of_date[:10]

    from stockbee_episodic_pivot_analyzer import analyze_candidate

    import datetime as _dt
    from historical_price_service import fetch_price_history_for_range

    as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
    start_dt = as_of_dt - _dt.timedelta(days=PRICE_LOOKBACK_DAYS)
    bars, price_err, _coverage = fetch_price_history_for_range(symbol, start_dt.isoformat(), as_of_dt.isoformat())
    if not bars:
        return None, price_err or f"No price history available for {symbol}"

    as_of = as_of_date[:10]
    bars = [b for b in bars if b.get("date", "") <= as_of]  # LEAKAGE SAFETY

    result = analyze_candidate(event, bars, max_risk_pct=MAX_RISK_PCT)

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    return result, ""
