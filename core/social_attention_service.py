"""
social_attention_service.py — Research Expansion Program, Component 2.

Reddit mention/attention data for single-name symbols, via ApeWisdom
(tools/apewisdom_client.py). Free, keyless. Targets the same proven weak spot
as Phase 3 and Component 1: narrative-driven single names.

LIVE-ONLY, like RapidAPI's market movers -- ApeWisdom gives a current
snapshot with no historical/point-in-time capability. Callers MUST gate this
to live/recent predictions only (same _is_recent_origin gate already used for
market movers and the yfinance earnings fallback) -- using it for a
historical backtest origin would mean feeding the AI a snapshot of TODAY's
Reddit activity to "predict" a past date, the exact leakage class this
codebase's validate_no_leakage() exists to prevent for price bars.

Follows the (data, error_string) tuple convention from historical_price_service.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))


def fetch_reddit_attention(symbol: str) -> Tuple[Optional[dict], str]:
    """Fetch current Reddit mention/attention data for a symbol.

    LIVE-ONLY -- see module docstring. Callers must not call this for a
    historical-replay origin date.

    Returns (data, error_string). data shape on success:
        {"mentions": int, "mentions_24h_change": int, "rank": int}
        -- mentions=0 if the symbol has no significant current Reddit
        chatter (a real, meaningful result, not a failure).
    """
    from apewisdom_client import find_symbol_mentions

    result = find_symbol_mentions(symbol)
    if result.get("status") != "SUCCESS":
        return None, result.get("message", "ApeWisdom request failed")

    if not result.get("found"):
        return {"mentions": 0, "mentions_24h_change": 0, "rank": None}, ""

    mentions = result.get("mentions") or 0
    mentions_24h_ago = result.get("mentions_24h_ago") or 0
    return {
        "mentions": mentions,
        "mentions_24h_change": mentions - mentions_24h_ago,
        "rank": result.get("rank"),
    }, ""
