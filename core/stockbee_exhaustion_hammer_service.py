"""
stockbee_exhaustion_hammer_service.py -- live orchestrator for
core/stockbee_exhaustion_hammer_screener.py. Fetches daily price history
via historical_price_service.py and runs the selling-exhaustion-hammer
pattern analysis for a single symbol.

market_gate (one of the composite's 6 scored components) is a real signal
here, not a hardcoded default: derived from
core/ibd_distribution_day_service.py's overall_risk_level (already built
and wired into feature_packet this session) -- NORMAL/CAUTION -> "allowed",
HIGH -> "neutral", SEVERE -> "restrictive". This is an honest cross-skill
reuse, not a guess: the source skill's own --market-gate flag says it
should reflect "latest market-regime/exposure decision," and this
project's own IBD distribution-day risk level is exactly that.

Per-symbol -- same category as pead_screener_service.py. Cached on disk
per symbol for a day.

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

CACHE_PATH = ROOT / "data" / "stockbee_exhaustion_hammer_cache.json"
CACHE_TTL_DAYS = 1
PRICE_LOOKBACK_DAYS = 160  # covers recent_high_lookback(40) + the 61-bar return window with buffer


def _to_most_recent_first_bars(raw_bars: list, as_of_date: str) -> list:
    from stockbee_exhaustion_hammer_screener import Bar

    as_of = as_of_date[:10]
    filtered = [b for b in raw_bars if b.get("date", "") <= as_of]
    filtered.reverse()  # historical_price_service is chronological; this module needs most-recent-first
    return [Bar(date=b["date"], open=b["open"], high=b["high"], low=b["low"], close=b["close"], volume=int(b.get("volume", 0))) for b in filtered]


def _derive_market_gate(as_of_date: str) -> str:
    try:
        from ibd_distribution_day_service import compute_ibd_distribution_day_status
        data, _err = compute_ibd_distribution_day_status(as_of_date)
        risk = (data or {}).get("overall_risk_level")
        if risk == "SEVERE":
            return "restrictive"
        if risk in ("NORMAL", "CAUTION"):
            return "allowed"
        if risk == "HIGH":
            return "neutral"
    except Exception:
        pass
    return "neutral"  # unknown -- same default the source skill's own CLI flag uses


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


def fetch_exhaustion_hammer_analysis(symbol: str, as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """Selling-exhaustion hammer setup analysis for `symbol` as of a given
    date.

    Returns (data, error_string). data shape on success (see
    core.stockbee_exhaustion_hammer_screener.analyze_symbol for the full
    field list):
        {"state": str, "rating": str, "setup_score": int,
         "primary_trigger": str, "downstream_action": str, ...}
    """
    from stockbee_exhaustion_hammer_screener import ScreenerConfig, analyze_symbol

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

    bars = _to_most_recent_first_bars(raw_bars, as_of_date)
    if len(bars) < 42:
        return None, f"Insufficient price history for {symbol}: {len(bars)} bars"

    cfg = ScreenerConfig(market_gate=_derive_market_gate(as_of_date))
    result = analyze_symbol(symbol, bars, cfg, profile_row=None)

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    return result, ""
