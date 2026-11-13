"""
Live orchestrator for core/crypto_regime_analyzer.py -- fetches CoinGecko
top-N markets + daily closes, CoinGecko global BTC dominance, and Binance
perpetual funding, then runs the 6-component scorer.

Standalone, crypto-market-wide tool (this project's domain is equities,
so this is NOT wired into feature_packet) -- but a free, keyless,
fully-portable skill in its own right, matching the source skill's own
framing as "the crypto analog of market-breadth-analyzer + exposure-coach."

Caches raw fetches for one UTC day (CACHE_TTL_DAYS=1, same convention as
market_breadth_service.py) since CoinGecko's free tier rate-limits
history calls -- a fresh run at the default top_n=20 takes a couple of
minutes due to the ~6.5s inter-call throttle documented in the source
skill; same-day re-runs hit the cache and are instant.

KNOWN LIMITATION, disclosed (same as the source skill's own "Known
Limitations"): CoinGecko's free tier only exposes CURRENT dominance, not
history, so this service accumulates one observation per calendar day in
data/crypto_dominance_history.json. The dominance component reports
`data_available: false` until 31 daily observations have accumulated.
Offline/snapshot mode (fetch_crypto_regime_from_snapshot) accepts a full
dominance_series directly and is not subject to this limitation -- useful
for tests and for seeding faster, exactly as the source skill documents.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crypto_regime_analyzer import (
    alt_breadth_participation,
    btc_dominance_regime,
    btc_trend_structure,
    compute_composite,
    drawdown_volatility_position,
    momentum_thrust_washout,
    perpetual_funding_regime,
)

CACHE_PATH = ROOT / "data" / "crypto_regime_cache.json"
DOMINANCE_HISTORY_PATH = ROOT / "data" / "crypto_dominance_history.json"
CACHE_TTL_DAYS = 1
FUNDING_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTER_CALL_THROTTLE_SECONDS = 6.5


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _record_dominance_observation(pct: float) -> List[float]:
    """Append today's UTC-day dominance observation (dedup by date) and
    return the accumulated series oldest -> newest."""
    today = time.strftime("%Y-%m-%d", time.gmtime())
    history = _load_json(DOMINANCE_HISTORY_PATH)
    history[today] = pct
    _save_json(DOMINANCE_HISTORY_PATH, history)
    return [history[d] for d in sorted(history.keys())]


def _run_components(
    btc_closes: List[float],
    alt_closes: Dict[str, List[float]],
    dominance_series: List[float],
    funding: Dict[str, float],
) -> Dict[str, Dict[str, Any]]:
    trend_result = btc_trend_structure(btc_closes)
    all_closes = dict(alt_closes)
    all_closes["BTC"] = btc_closes
    return {
        "btc_trend_structure": trend_result,
        "alt_breadth_participation": alt_breadth_participation(alt_closes),
        "btc_dominance_regime": btc_dominance_regime(dominance_series, trend_result.get("score")),
        "perpetual_funding_regime": perpetual_funding_regime(funding),
        "drawdown_volatility_position": drawdown_volatility_position(btc_closes),
        "momentum_thrust_washout": momentum_thrust_washout(all_closes),
    }


def fetch_crypto_regime_from_snapshot(snapshot: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """Offline mode -- pure, no network. See module docstring for the schema."""
    series = snapshot.get("series", {})
    if "BTC" not in series:
        return {}, "snapshot_missing_BTC_series"
    btc_closes = series["BTC"]
    alt_closes = {sym: closes for sym, closes in series.items() if sym != "BTC"}
    dominance_series = snapshot.get("dominance_series", [])
    funding = snapshot.get("funding", {})

    components = _run_components(btc_closes, alt_closes, dominance_series, funding)
    composite = compute_composite(components)
    return {"metadata": {"as_of": snapshot.get("as_of"), "mode": "offline"},
            "components": components, "composite": composite}, ""


def fetch_crypto_regime(top_n: int = 20, use_cache: bool = True) -> Tuple[Dict[str, Any], str]:
    """Live mode -- fetches CoinGecko + Binance. Returns (data, warnings_string)."""
    from tools.coingecko_client import fetch_btc_dominance, fetch_market_chart_daily, fetch_top_markets
    from tools.binance_funding_client import fetch_funding_for_symbols

    today = time.strftime("%Y-%m-%d", time.gmtime())
    cache = _load_json(CACHE_PATH)
    if use_cache and cache.get("date") == today:
        return cache["data"], cache.get("warnings", "")

    warnings = []

    markets, markets_err = fetch_top_markets(top_n=top_n)
    if markets_err or not markets:
        return {}, f"top_markets: {markets_err or 'empty'}"

    btc_entry = next((m for m in markets if m.get("symbol", "").lower() == "btc"), None)
    if not btc_entry:
        return {}, "BTC not found in top markets"

    btc_closes, err = fetch_market_chart_daily(btc_entry["id"], days=365)
    if err or not btc_closes:
        return {}, f"btc_history: {err or 'empty'}"

    alt_closes: Dict[str, List[float]] = {}
    for coin in markets:
        if coin["id"] == btc_entry["id"]:
            continue
        time.sleep(INTER_CALL_THROTTLE_SECONDS)
        closes, err = fetch_market_chart_daily(coin["id"], days=365)
        if err or not closes:
            warnings.append(f"{coin['symbol'].upper()}: {err or 'empty'}")
            continue
        alt_closes[coin["symbol"].upper()] = closes

    dominance_pct, dom_err = fetch_btc_dominance()
    dominance_series = _record_dominance_observation(dominance_pct) if dominance_pct is not None else []
    if dom_err:
        warnings.append(f"dominance: {dom_err}")

    funding, funding_errors = fetch_funding_for_symbols(FUNDING_SYMBOLS)
    for sym, err in funding_errors.items():
        warnings.append(f"funding/{sym}: {err}")

    components = _run_components(btc_closes, alt_closes, dominance_series, funding)
    composite = compute_composite(components)
    data = {
        "metadata": {"as_of": today, "mode": "live", "top_n": top_n},
        "components": components,
        "composite": composite,
    }
    warnings_str = "; ".join(warnings)

    if use_cache:
        _save_json(CACHE_PATH, {"date": today, "data": data, "warnings": warnings_str})

    return data, warnings_str
