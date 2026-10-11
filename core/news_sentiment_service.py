"""
news_sentiment_service.py — Phase 3 of the accuracy improvement program.

Earnings-proximity and news-sentiment context for single-name symbols, via
Alpha Vantage (tools/alpha_vantage_client.py). Scoped deliberately to
single-name, narrative-driven symbols (TSLA-like) -- the data this session
analyzed showed broad-index symbols (SPY/QQQ) already do fine on technical
indicators alone; this is additive context for the segment that's actually
missing it, not a blanket addition everywhere.

Uses the EARNINGS endpoint (JSON) rather than EARNINGS_CALENDAR, which Alpha
Vantage returns as CSV by design -- avoids a second format to parse/trust.

LEAKAGE SAFETY: fetch_news_sentiment_score's as_of_date filtering is NOT
optional. A historical backtest origin date must only see news published on
or before that date -- feeding it articles published after the origin would
be the exact same leakage class validate_no_leakage() exists to catch for
price bars elsewhere in this codebase. See test_news_sentiment_no_leakage.py.

Follows the (data, error_string) tuple convention from historical_price_service.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))


def fetch_earnings_calendar(symbol: str) -> Tuple[Optional[dict], str]:
    """Fetch this symbol's earnings history + most recent reported date via
    the EARNINGS endpoint. Returns (data, error_string).

    data shape (on success): {"symbol": str, "quarterly_earnings": [
        {"fiscal_date_ending": "YYYY-MM-DD", "reported_date": "YYYY-MM-DD", ...}, ...
    ]}
    """
    from alpha_vantage_client import alpha_vantage_get

    result = alpha_vantage_get("EARNINGS", {"symbol": symbol})
    if result.get("status") != "SUCCESS":
        return None, result.get("message", "Alpha Vantage EARNINGS request failed")

    raw = result.get("data") or {}
    quarterly = raw.get("quarterlyEarnings") or []
    if not isinstance(quarterly, list):
        return None, "Unexpected EARNINGS response shape (quarterlyEarnings not a list)"

    cleaned = []
    for q in quarterly:
        if not isinstance(q, dict):
            continue
        cleaned.append({
            "fiscal_date_ending": q.get("fiscalDateEnding"),
            "reported_date":      q.get("reportedDate"),
            "reported_eps":       q.get("reportedEPS"),
            "estimated_eps":      q.get("estimatedEPS"),
            "surprise_pct":       q.get("surprisePercentage"),
        })
    return {"symbol": symbol.upper(), "quarterly_earnings": cleaned}, ""


def earnings_days_away(earnings_data: Optional[dict], as_of_date: str, target_date: str) -> Optional[int]:
    """Given fetch_earnings_calendar()'s output and a prediction window
    [as_of_date, target_date], return the number of days from as_of_date to
    the nearest known earnings date that falls on/after as_of_date and
    on/before target_date, or None if no such date is known.

    LEAKAGE NOTE: Alpha Vantage's EARNINGS endpoint returns PAST reported
    dates, not a forward-looking calendar -- it cannot tell you about a
    not-yet-announced future earnings date. This is safe for historical
    replay (the "upcoming" earnings as of a past as_of_date already happened
    and is in the historical record) but for LIVE predictions this alone
    under-informs about not-yet-scheduled near-term earnings; combine with
    the existing yfinance .calendar fallback (_get_earnings_warning in
    gemini_stock_prediction_agent.py) for live runs, which this function
    deliberately does not duplicate.
    """
    if not earnings_data:
        return None
    candidates = []
    for q in earnings_data.get("quarterly_earnings", []):
        d = q.get("reported_date")
        if d and as_of_date <= d <= target_date:
            candidates.append(d)
    if not candidates:
        return None
    nearest = min(candidates)
    from datetime import datetime
    try:
        delta = (datetime.strptime(nearest, "%Y-%m-%d") - datetime.strptime(as_of_date, "%Y-%m-%d")).days
        return delta
    except ValueError:
        return None


def fetch_news_sentiment_score(symbol: str, as_of_date: str) -> Tuple[Optional[dict], str]:
    """Fetch news sentiment for this symbol via NEWS_SENTIMENT, filtered to
    articles published on/before as_of_date (LEAKAGE SAFETY -- see module
    docstring). Returns (data, error_string).

    data shape (on success): {"symbol": str, "article_count": int,
        "avg_sentiment_score": float | None}  (-1=bearish .. +1=bullish, per
        Alpha Vantage's own scale)
    """
    from alpha_vantage_client import alpha_vantage_get
    from datetime import datetime, timedelta

    try:
        as_of_dt = datetime.strptime(as_of_date[:10], "%Y-%m-%d")
    except ValueError:
        return None, f"Malformed as_of_date: {as_of_date!r}"

    # Alpha Vantage's time_from/time_to are YYYYMMDDTHHMM, inclusive. Look back
    # 14 days from as_of_date for a recent-sentiment window; time_to=as_of_date
    # is what actually enforces leakage safety here, not the lookback length.
    time_from = (as_of_dt - timedelta(days=14)).strftime("%Y%m%dT0000")
    time_to   = as_of_dt.strftime("%Y%m%dT2359")

    result = alpha_vantage_get("NEWS_SENTIMENT", {
        "tickers": symbol.upper(), "time_from": time_from, "time_to": time_to,
        "sort": "RELEVANCE", "limit": 50,
    })
    if result.get("status") != "SUCCESS":
        return None, result.get("message", "Alpha Vantage NEWS_SENTIMENT request failed")

    raw = result.get("data") or {}
    feed = raw.get("feed") or []
    if not isinstance(feed, list):
        return None, "Unexpected NEWS_SENTIMENT response shape (feed not a list)"

    # Defense in depth: even though time_to already bounds the request, don't
    # trust the upstream filter alone -- re-check each article's own
    # published timestamp against as_of_date before counting it, the same
    # "don't trust, verify" discipline validate_no_leakage() applies to bars.
    as_of_str = as_of_dt.strftime("%Y%m%d")
    scores = []
    for article in feed:
        if not isinstance(article, dict):
            continue
        published = str(article.get("time_published") or "")[:8]
        if not published or published > as_of_str:
            continue  # future-relative-to-as_of_date -- excluded, leakage guard
        score = article.get("overall_sentiment_score")
        if score is not None:
            try:
                scores.append(float(score))
            except (TypeError, ValueError):
                pass

    avg_score = round(sum(scores) / len(scores), 4) if scores else None
    return {
        "symbol": symbol.upper(),
        "article_count": len(scores),
        "avg_sentiment_score": avg_score,
    }, ""
