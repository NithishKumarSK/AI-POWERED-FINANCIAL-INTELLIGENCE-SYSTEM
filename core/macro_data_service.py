"""
macro_data_service.py — to-do item #9's remaining gap: macro/rate data, the
one alternative-data category the Research Expansion Program's SEC EDGAR
insider + ApeWisdom Reddit work (Components 1-2) didn't cover.

Fed funds rate + 10-year Treasury yield via Alpha Vantage's economic-
indicator endpoints (tools/alpha_vantage_client.py). Response shape verified
live this session via the assistant's own Alpha Vantage MCP connector
(FEDERAL_FUNDS_RATE and TREASURY_YIELD both return
{"name", "interval", "unit", "data": [{"date": "YYYY-MM-DD", "value": "..."}]},
most-recent-first) -- not assumed from docs, same discipline as every other
new data source this project has added. NOTE: that MCP connector is NOT
callable by this deployed app (see tools/alpha_vantage_client.py's own
docstring) -- this module hits the real HTTP API with ALPHA_VANTAGE_API_KEY,
which was not configured as of this writing; it degrades to "unavailable"
until a key is added, exactly like Phase 3's earnings/news-sentiment calls
already do for the same reason.

Unlike SEC EDGAR insider / ApeWisdom Reddit data (single-name only, gated to
non-index symbols), macro/rate data applies market-wide -- every symbol gets
the same fed_funds_rate_pct / treasury_10y_yield_pct, so this is NOT gated by
_is_index_symbol.

Deliberately cached on disk (data/macro_data_cache.json): these series move
at most monthly, so re-fetching the full history on every prediction would
waste the limited free-tier quota (and real money, per this project's
explicit token/API-cost caution) for data that hasn't changed. A cached
series is reused for up to CACHE_TTL_DAYS regardless of how many different
as_of_date values are sliced from it -- the slicing itself (which value was
"current" as of a given date) is a pure local computation, so this is safe
for historical replay too (LEAKAGE SAFETY: only data points with
date <= as_of_date are ever returned -- same discipline as
news_sentiment_service.py / insider_activity_service.py).

Follows the (data, error_string) tuple convention from historical_price_service.py.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))

CACHE_PATH = ROOT / "data" / "macro_data_cache.json"
CACHE_TTL_DAYS = 7

_SERIES = {
    "fed_funds_rate": {"function": "FEDERAL_FUNDS_RATE", "params": {"interval": "monthly"}},
    "treasury_10y":   {"function": "TREASURY_YIELD", "params": {"interval": "monthly", "maturity": "10year"}},
}


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
        pass  # cache is a pure optimization -- never let a write failure break a prediction


def _fetch_series(series_key: str) -> Tuple[Optional[list], str]:
    """Return (data_points, error_string) for one named series, using the
    disk cache if fresh enough. data_points is a list of
    {"date": "YYYY-MM-DD", "value": float}, most-recent-first."""
    cache = _load_cache()
    entry = cache.get(series_key)
    if entry and (time.time() - entry.get("fetched_at", 0)) < CACHE_TTL_DAYS * 86400:
        return entry["data"], ""

    from alpha_vantage_client import alpha_vantage_get

    spec = _SERIES[series_key]
    result = alpha_vantage_get(spec["function"], {**spec["params"], "datatype": "json"})
    if result.get("status") != "SUCCESS":
        # Stale cache beats no data at all -- fall back to it if present.
        if entry:
            return entry["data"], f"Using stale cache ({result.get('message', 'fetch failed')})"
        return None, result.get("message", f"{spec['function']} request failed")

    raw = (result.get("data") or {}).get("data") or []
    if not isinstance(raw, list):
        return None, f"Unexpected {spec['function']} response shape (data not a list)"

    cleaned = []
    for pt in raw:
        try:
            cleaned.append({"date": pt["date"], "value": float(pt["value"])})
        except (KeyError, TypeError, ValueError):
            continue
    if not cleaned:
        return None, f"No usable data points in {spec['function']} response"

    cache[series_key] = {"data": cleaned, "fetched_at": time.time()}
    _save_cache(cache)
    return cleaned, ""


def _value_as_of(data_points: list, as_of_date: str) -> Optional[float]:
    """Most recent value with date <= as_of_date. LEAKAGE SAFETY: a backtest
    origin must never see a value whose date is after it."""
    as_of = as_of_date[:10]
    candidates = [p for p in data_points if p["date"] <= as_of]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p["date"])["value"]


def fetch_macro_snapshot(as_of_date: str) -> Tuple[Optional[dict], str]:
    """Fetch fed funds rate + 10yr Treasury yield as of a given date.

    Returns (data, error_string). data shape on success (fields present only
    if that series resolved -- a partial result is still useful, not an
    all-or-nothing failure):
        {"fed_funds_rate_pct": float, "treasury_10y_yield_pct": float}

    Returns (None, error_string) only if BOTH series failed to resolve.
    """
    out = {}
    errors = []

    ff_points, ff_err = _fetch_series("fed_funds_rate")
    if ff_points:
        val = _value_as_of(ff_points, as_of_date)
        if val is not None:
            out["fed_funds_rate_pct"] = val
    if ff_err:
        errors.append(f"fed_funds_rate: {ff_err}")

    ty_points, ty_err = _fetch_series("treasury_10y")
    if ty_points:
        val = _value_as_of(ty_points, as_of_date)
        if val is not None:
            out["treasury_10y_yield_pct"] = val
    if ty_err:
        errors.append(f"treasury_10y: {ty_err}")

    if not out:
        return None, "; ".join(errors) if errors else "No macro data resolved"
    return out, "; ".join(errors)
