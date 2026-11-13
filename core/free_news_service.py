"""
free_news_service.py — free, keyless news/filing monitoring, adapted from
trader-news (vendor/trader-skill/trader-news/news.py, MIT License,
Copyright (c) 2026 Jake Schincariol -- see vendor/trader-skill/LICENSE).

Built because this project's existing Alpha Vantage NEWS_SENTIMENT path
(news_sentiment_service.py) needs a paid Alpha Vantage plan this project
doesn't currently have (see core/macro_data_service.py's docstring and
earlier session notes) -- this is a free alternative/supplement, not a
replacement for that code path.

Two genuinely different signals, with different leakage-safety properties:

  fetch_sec_8k_count() -- SEC EDGAR 8-K filing count in a lookback window.
    8-K filings have a real, point-in-time filing date, so this IS safe for
    historical replay (LEAKAGE SAFETY: only filings filed on/before
    as_of_date are counted, same discipline as insider_activity_service.py).
    Reuses tools/sec_edgar_client.py -- no new HTTP client needed.

  fetch_yahoo_headline_tags() -- Yahoo Finance headline RSS, keyword-tagged
    by category (earnings/analyst/legal/deal/capital/people/risk). LIVE
    ONLY -- Yahoo's RSS feed has no historical/point-in-time capability, so
    this is gated to _is_recent_origin in the caller, same as ApeWisdom
    Reddit attention and RapidAPI market movers elsewhere in this project.

Follows the (data, error_string) tuple convention from historical_price_service.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))

YAHOO_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
_BROWSER_UA = "Mozilla/5.0 (compatible; Stock-Prediction-Agent/1.0; research tool)"

# Adapted verbatim from trader-news' keyword categories (see module docstring).
_KEYWORDS = [
    ("earnings", re.compile(r"\bearnings\b|\bresults\b|\bEPS\b|\bguidance\b|\bforecast\b", re.I)),
    ("analyst", re.compile(r"\bupgrade[sd]?\b|\bdowngrade[sd]?\b|price target|\boutperform\b|\bunderperform\b", re.I)),
    ("legal", re.compile(r"\blawsuit\b|\bsued\b|\bprobe\b|\binvestigation\b|\bSEC charges\b|\bantitrust\b", re.I)),
    ("deal", re.compile(r"\bacqui(?:re|res|red|sition)\b|\bmerger\b|\bbuyout\b|\btakeover\b", re.I)),
    ("capital", re.compile(r"\bdividend\b|\bbuyback\b|\brepurchase\b|\bstock split\b|\boffering\b", re.I)),
    ("people", re.compile(r"\bCEO\b|\bCFO\b|\bresign|\bsteps down\b|\bappoint", re.I)),
    ("risk", re.compile(r"\brecall\b|\bbankrupt|\bdefault\b|\bdelist|\bhack|\bbreach\b|\boutage\b", re.I)),
]


def fetch_sec_8k_count(symbol: str, as_of_date: str, lookback_days: int = 30) -> Tuple[Optional[dict], str]:
    """Count SEC 8-K filings for a symbol in [as_of_date - lookback_days, as_of_date]
    (LEAKAGE SAFETY). Returns (data, error_string). data shape on success:
        {"filing_count": int, "most_recent_filed": "YYYY-MM-DD"|None}
    """
    import datetime as _dt
    from sec_edgar_client import get_cik_for_symbol, get_submissions

    try:
        as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d")
    except ValueError:
        return None, f"Malformed as_of_date: {as_of_date!r}"
    lookback_start = (as_of_dt - _dt.timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    as_of_str = as_of_dt.strftime("%Y-%m-%d")

    cik_result = get_cik_for_symbol(symbol)
    if cik_result.get("status") != "SUCCESS":
        return None, cik_result.get("message", "CIK lookup failed")
    cik = cik_result["cik"]

    sub_result = get_submissions(cik)
    if sub_result.get("status") != "SUCCESS":
        return None, sub_result.get("message", "SEC submissions request failed")

    rec = (sub_result.get("data") or {}).get("filings", {}).get("recent", {})
    forms = rec.get("form", [])
    dates = rec.get("filingDate", [])

    filed_dates = [
        dates[i] for i in range(len(forms))
        if forms[i] == "8-K" and lookback_start <= dates[i] <= as_of_str
    ]
    return {
        "filing_count": len(filed_dates),
        "most_recent_filed": max(filed_dates) if filed_dates else None,
    }, ""


def fetch_most_recent_earnings_8k(symbol: str, as_of_date: str, lookback_days: int = 120) -> Tuple[Optional[dict], str]:
    """The most recent 8-K filing on/before as_of_date whose SEC 'items'
    field includes 2.02 ("Results of Operations and Financial Condition")
    -- the official SEC item code for an earnings release, confirmed live
    this session (e.g. AAPL's 8-Ks tagged "2.02,9.01" land exactly on its
    known quarterly earnings dates). A free, accurate, backtest-safe
    earnings-date source, built because FMP's free-tier earnings-calendar
    endpoint is confirmed to reject date ranges more than a few days in
    the past (HTTP 402) -- it only serves near-term/future dates, so it
    can't answer "when did this company last report" for anything but the
    last few days. SEC doesn't record BMO/AMC timing, unlike FMP's
    calendar -- callers needing a gap calculation should pass timing="unknown".

    LEAKAGE SAFETY: only filings filed on/before as_of_date are considered.

    Returns (data, error_string). data shape on success:
        {"earnings_date": "YYYY-MM-DD", "items": "2.02,9.01"} or None if
        no earnings-tagged 8-K was found within lookback_days.
    """
    import datetime as _dt
    from sec_edgar_client import get_cik_for_symbol, get_submissions

    try:
        as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d")
    except ValueError:
        return None, f"Malformed as_of_date: {as_of_date!r}"
    lookback_start = (as_of_dt - _dt.timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    as_of_str = as_of_dt.strftime("%Y-%m-%d")

    cik_result = get_cik_for_symbol(symbol)
    if cik_result.get("status") != "SUCCESS":
        return None, cik_result.get("message", "CIK lookup failed")
    cik = cik_result["cik"]

    sub_result = get_submissions(cik)
    if sub_result.get("status") != "SUCCESS":
        return None, sub_result.get("message", "SEC submissions request failed")

    rec = (sub_result.get("data") or {}).get("filings", {}).get("recent", {})
    forms = rec.get("form", [])
    dates = rec.get("filingDate", [])
    items = rec.get("items", [])

    candidates = [
        (dates[i], items[i] if i < len(items) else "")
        for i in range(len(forms))
        if forms[i] == "8-K"
        and lookback_start <= dates[i] <= as_of_str
        and "2.02" in (items[i] if i < len(items) else "").split(",")
    ]
    if not candidates:
        return None, f"No earnings-tagged 8-K found for {symbol} within {lookback_days} days of {as_of_str}"

    best_date, best_items = max(candidates, key=lambda c: c[0])
    return {"earnings_date": best_date, "items": best_items}, ""


def fetch_yahoo_headline_tags(symbol: str) -> Tuple[Optional[dict], str]:
    """LIVE-ONLY (no historical capability) Yahoo Finance headline RSS,
    keyword-tagged by category. Returns (data, error_string). data shape
    on success: {"headline_count": int, "tags": {"earnings": 2, "legal": 1, ...},
    "titles": [str, ...]} ("titles" added for stockbee_episodic_pivot_analyzer_service.py,
    which needs the raw text for its own, finer-grained catalyst classifier).
    """
    import requests
    import xml.etree.ElementTree as ET

    url = YAHOO_RSS_URL.format(symbol=symbol.upper())
    try:
        resp = requests.get(url, headers={"User-Agent": _BROWSER_UA}, timeout=20)
        if resp.status_code != 200:
            return None, f"Yahoo RSS returned HTTP {resp.status_code}"
        root = ET.fromstring(resp.content)
    except requests.Timeout:
        return None, "Request timed out"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"

    titles = [item.findtext("title") or "" for item in root.iter("item")]
    tags = {name: 0 for name, _ in _KEYWORDS}
    for title in titles:
        for name, pattern in _KEYWORDS:
            if pattern.search(title):
                tags[name] += 1

    return {"headline_count": len(titles), "tags": {k: v for k, v in tags.items() if v > 0}, "titles": titles}, ""
