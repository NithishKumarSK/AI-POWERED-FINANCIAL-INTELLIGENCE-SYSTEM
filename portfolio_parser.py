"""Portfolio input parser.

Accepts compact portfolio text such as:
- AAPL 40% MSFT 30% TSLA 20% NVDA 10%
- AAPL:40, MSFT:30
- AAPL=40
- AAPL,40
- AAPL MSFT TSLA
- [{"ticker":"AAPL","weight":0.4}]
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _clean_ticker(value: Any) -> str:
    return re.sub(r"[^A-Z0-9.\-]", "", str(value or "").upper().strip())


def _parse_weight(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    text = text.replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        raw = float(text)
    except Exception:
        return None
    if raw < 0:
        return None
    return raw / 100.0 if raw > 1 else raw


def _dedupe_and_normalize(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    issues: List[str] = []
    merged: Dict[str, Optional[float]] = {}

    for item in items:
        ticker = _clean_ticker(item.get("ticker"))
        if not ticker or not TICKER_RE.match(ticker):
            issues.append(f"Invalid ticker skipped: {item.get('ticker')}")
            continue
        weight = item.get("weight")
        parsed_weight = _parse_weight(weight) if weight is not None else None
        if ticker in merged:
            issues.append(f"Duplicate ticker merged: {ticker}")
            existing = merged[ticker]
            if existing is None or parsed_weight is None:
                merged[ticker] = None
            else:
                merged[ticker] = existing + parsed_weight
        else:
            merged[ticker] = parsed_weight

    if not merged:
        return {"status": "ERROR", "holdings": [], "issues": issues or ["Portfolio is empty."]}

    specified = [w for w in merged.values() if w is not None]
    if len(specified) == 0:
        equal = 1.0 / len(merged)
        holdings = [{"ticker": ticker, "weight": equal} for ticker in sorted(merged)]
        return {"status": "SUCCESS", "holdings": holdings, "issues": issues}

    if len(specified) != len(merged):
        issues.append("Mixed weighted/unweighted input detected; unspecified names were assigned equal residual weight.")
        specified_sum = sum(specified)
        residual = max(0.0, 1.0 - specified_sum)
        missing_count = sum(1 for w in merged.values() if w is None)
        fallback = residual / missing_count if missing_count else 0.0
        for ticker, weight in list(merged.items()):
            if weight is None:
                merged[ticker] = fallback

    total = sum(float(w or 0.0) for w in merged.values())
    if total <= 0:
        equal = 1.0 / len(merged)
        merged = {ticker: equal for ticker in merged}
    elif abs(total - 1.0) > 0.005:
        issues.append(f"Weights normalized from total {total:.2%}.")
        merged = {ticker: float(weight or 0.0) / total for ticker, weight in merged.items()}

    holdings = [{"ticker": ticker, "weight": float(weight or 0.0)} for ticker, weight in sorted(merged.items())]
    return {"status": "SUCCESS", "holdings": holdings, "issues": issues}


def _items_from_json(raw: str) -> Optional[List[Dict[str, Any]]]:
    try:
        payload = json.loads(raw)
    except Exception:
        return None

    if isinstance(payload, dict):
        if "holdings" in payload and isinstance(payload["holdings"], list):
            payload = payload["holdings"]
        else:
            payload = [{"ticker": key, "weight": value} for key, value in payload.items()]

    if not isinstance(payload, list):
        return None

    items: List[Dict[str, Any]] = []
    for entry in payload:
        if isinstance(entry, dict):
            ticker = entry.get("ticker") or entry.get("symbol") or entry.get("name")
            weight = entry.get("weight")
            if weight is None:
                weight = entry.get("allocation") or entry.get("percent") or entry.get("percentage")
            items.append({"ticker": ticker, "weight": weight})
        elif isinstance(entry, str):
            items.append({"ticker": entry, "weight": None})
    return items


def parse_portfolio_input(raw: str) -> Dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {"status": "ERROR", "holdings": [], "issues": ["Portfolio input is empty."]}

    json_items = _items_from_json(text)
    if json_items is not None:
        return _dedupe_and_normalize(json_items)

    items: List[Dict[str, Any]] = []

    pair_pattern = re.compile(
        r"\b([A-Za-z][A-Za-z0-9.\-]{0,9})\b\s*(?:[:=,\-]\s*|\s+)(\d+(?:\.\d+)?)\s*%?",
        flags=re.IGNORECASE,
    )
    consumed_spans = []
    for match in pair_pattern.finditer(text):
        ticker = _clean_ticker(match.group(1))
        weight = match.group(2)
        if ticker and TICKER_RE.match(ticker):
            items.append({"ticker": ticker, "weight": weight})
            consumed_spans.append(match.span())

    if items:
        return _dedupe_and_normalize(items)

    token_candidates = re.split(r"[\s,;|/]+", text)
    for token in token_candidates:
        ticker = _clean_ticker(token)
        if ticker and TICKER_RE.match(ticker) and not ticker.isdigit():
            items.append({"ticker": ticker, "weight": None})

    return _dedupe_and_normalize(items)


def parse_tickers(raw: str) -> List[str]:
    parsed = parse_portfolio_input(raw)
    if parsed.get("status") != "SUCCESS":
        return []
    return [item["ticker"] for item in parsed.get("holdings", [])]

