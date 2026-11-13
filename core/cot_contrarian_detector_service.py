"""
Live orchestrator for core/cot_contrarian_detector.py -- fetches CFTC's
own free, keyless COT data (tools/cftc_cot_client.py) and runs the
crowding analysis. Output is directly consumable by
core/contrarian_setup_gate.py's `crowding` parameter (both share the
`classification` key), completing all three real Shapiro-pipeline steps
end-to-end for the markets in MARKET_CODES.

LEAKAGE SAFETY: rows with a report date after as_of_date are dropped
before any calculation -- same discipline as every other context-
enrichment source in this project. Cached on disk for a day (COT data
is published weekly, so this is generous, not stale).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cot_contrarian_detector import LOOKBACK_WEEKS_DEFAULT, SHORT_LOOKBACK_WEEKS_DEFAULT, analyze_cot_crowding

CACHE_PATH = ROOT / "data" / "cot_crowding_cache.json"
CACHE_TTL_DAYS = 1


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


def fetch_cot_crowding(
    symbol: str,
    as_of_date: str,
    lookback_weeks: int = LOOKBACK_WEEKS_DEFAULT,
    short_lookback_weeks: int = SHORT_LOOKBACK_WEEKS_DEFAULT,
    use_cache: bool = True,
) -> Tuple[Optional[Dict[str, Any]], str]:
    from tools.cftc_cot_client import MARKET_CODES, fetch_cot_history

    symbol = symbol.upper()
    if symbol not in MARKET_CODES:
        return None, f"unsupported_symbol: {symbol} not in the curated CFTC market-code table"
    contract_code = MARKET_CODES[symbol]["code"]

    cache_key = f"{symbol}:{contract_code}"
    cache = _load_cache()
    entry = cache.get(cache_key)
    if use_cache and entry and (time.time() - entry.get("fetched_at", 0)) < CACHE_TTL_DAYS * 86400:
        rows = entry["rows"]
    else:
        rows, err = fetch_cot_history(contract_code, limit=max(lookback_weeks + 10, 260))
        if err or not rows:
            return None, err or "no_cot_data"
        if use_cache:
            cache[cache_key] = {"rows": rows, "fetched_at": time.time()}
            _save_cache(cache)

    truncated = [r for r in rows if (r.get("report_date_as_yyyy_mm_dd") or "")[:10] <= as_of_date[:10]]
    if not truncated:
        return None, "no_cot_data_on_or_before_as_of_date"

    result = analyze_cot_crowding(truncated, lookback_weeks=lookback_weeks, short_lookback_weeks=short_lookback_weeks)
    result["symbol"] = symbol
    return result, ""
