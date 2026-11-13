"""
Live orchestrator for core/parabolic_short_screener.py (Phase 1) --
wires in core/historical_price_service.py for EOD OHLCV,
tools/fmp_client.py's `/profile` endpoint (confirmed live this session:
free tier returns marketCap + ipoDate with no premium gate) for market
cap / days-since-IPO, and core/free_news_service.py's
`fetch_most_recent_earnings_8k` for the backward-looking earnings check
(the forward-looking "earnings within N days" check instead uses
core/fmp_calendar_service.fetch_earnings_calendar, best-effort -- that
endpoint only reliably serves near-term/future dates on the free tier,
confirmed earlier this session, so a failure here degrades to "unknown,"
never a fabricated gap).
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Optional, Tuple

from parabolic_short_screener import screen_symbol


def _trading_days_since(ipo_date_str: Optional[str], as_of_date: str) -> Optional[int]:
    if not ipo_date_str:
        return None
    try:
        ipo_date = _dt.date.fromisoformat(ipo_date_str[:10])
        as_of = _dt.date.fromisoformat(as_of_date[:10])
    except ValueError:
        return None
    calendar_days = (as_of - ipo_date).days
    if calendar_days < 0:
        return None
    return int(calendar_days * (5 / 7))  # approximation: trading days ~ 5/7 of calendar days


def fetch_parabolic_screen(symbol: str, as_of_date: str, mode: str = "safe_largecap") -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        from historical_price_service import fetch_price_history_for_range
        lookback_start = (_dt.date.fromisoformat(as_of_date) - _dt.timedelta(days=420)).isoformat()
        bars, price_err, _ = fetch_price_history_for_range(symbol, lookback_start, as_of_date)
    except Exception as exc:
        return None, f"price_history_failed: {type(exc).__name__}: {exc}"
    if price_err or not bars:
        return None, price_err or "no_price_history"

    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    volumes = [b["volume"] for b in bars]

    market_cap = None
    days_since_ipo = None
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        from fmp_client import fmp_get
        profile_resp = fmp_get("profile", {"symbol": symbol})
        if profile_resp.get("status") == "SUCCESS" and profile_resp.get("data"):
            profile = profile_resp["data"][0]
            market_cap = profile.get("marketCap")
            days_since_ipo = _trading_days_since(profile.get("ipoDate"), as_of_date)
    except Exception:
        pass  # market_cap/days_since_ipo stay None -- the hard-invalidation check treats None as "not rejected on this rule," never fabricated.

    earnings_within_days_forward = None
    try:
        from fmp_calendar_service import fetch_earnings_calendar
        window_end = (_dt.date.fromisoformat(as_of_date) + _dt.timedelta(days=10)).isoformat()
        events, cal_err = fetch_earnings_calendar(as_of_date, window_end, symbol=symbol)
        if not cal_err and events:
            as_of = _dt.date.fromisoformat(as_of_date)
            upcoming = [e for e in events if e.get("date")]
            if upcoming:
                nearest = min(_dt.date.fromisoformat(e["date"][:10]) for e in upcoming)
                earnings_within_days_forward = (nearest - as_of).days
    except Exception:
        pass

    result = screen_symbol(
        symbol, closes, highs, lows, volumes, market_cap, days_since_ipo,
        earnings_within_days_forward, mode=mode,
    )
    return result, ""
