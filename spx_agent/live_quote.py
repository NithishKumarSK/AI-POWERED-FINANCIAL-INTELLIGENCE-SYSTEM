"""
Live/Delayed Quote
Pulls the most recent available price for a given yfinance ticker via its
latest 1-minute bar. This is Yahoo Finance's free retail feed -- commonly
fresh to within a few minutes but NOT a true real-time tick feed. For
genuinely live/real-time data you'd need a broker/exchange feed (e.g.
Interactive Brokers, tastytrade, or a paid market-data vendor).

For SPX (cash index, 9:30-16:00 ET only), this naturally just returns the
last session's close outside market hours -- there's no overnight session
to be "live" against. For ES (nearly 24-hour futures), it stays close to
current price almost around the clock.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict


def get_live_quote(yf_ticker: str) -> Dict:
    import yfinance as yf

    ticker = yf.Ticker(yf_ticker)
    df = ticker.history(period="1d", interval="1m")
    if df is None or df.empty:
        raise RuntimeError(f"No recent 1-minute bars available for {yf_ticker} (market may be closed).")

    last_row = df.iloc[-1]
    last_bar_time = df.index[-1]
    now_utc = datetime.now(timezone.utc)
    last_bar_utc = last_bar_time.tz_convert("UTC") if last_bar_time.tzinfo else last_bar_time.tz_localize("UTC")
    staleness_minutes = round((now_utc - last_bar_utc).total_seconds() / 60, 1)

    if staleness_minutes < 60:
        staleness_display = f"~{staleness_minutes:.0f} min old"
    elif staleness_minutes < 60 * 24:
        staleness_display = f"~{staleness_minutes / 60:.1f} hours old (likely last session's close -- market closed)"
    else:
        staleness_display = f"~{staleness_minutes / 60 / 24:.1f} days old (market closed -- last session's close)"

    return {
        "ticker": yf_ticker,
        "price": round(float(last_row["Close"]), 2),
        "last_bar_time": last_bar_time.strftime("%Y-%m-%d %H:%M %Z"),
        "fetched_at": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "staleness_minutes": staleness_minutes,
        "staleness_display": staleness_display,
        "note": (
            "Yahoo Finance free retail feed -- commonly a few minutes behind the exchange, not a true "
            "real-time tick feed. A broker/exchange feed is required for genuinely live data."
        ),
    }
