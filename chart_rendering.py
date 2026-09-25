"""
Renders OHLC candlestick chart images for Gemini's chart-vision input.

LEAKAGE GUARANTEE: this module never fetches or filters price history itself.
Every function here takes `bars` as-is and only ever slices the TAIL of that
list (the most recent N entries) -- it is entirely the caller's responsibility
to pass bars already filtered to date <= the prediction origin, exactly like
build_stock_feature_packet() already requires. Do not "fix" this by adding a
convenience fetch here.

Uses matplotlib's object-oriented Figure/FigureCanvasAgg API directly (not
pyplot) because pyplot keeps shared global figure state that isn't safe when
multiple chart renders can run concurrently (this app calls into price/AI
enrichment under asyncio.to_thread elsewhere).
"""
from __future__ import annotations

import io
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.patches import Rectangle

DEFAULT_WIDE_LOOKBACK_DAYS = 240
DEFAULT_DETAIL_LOOKBACK_DAYS = 90


def _compute_full_sma(closes: List[float], window: int) -> List[float]:
    """Simple moving average over the FULL closes series (index i uses up to
    `window` prior closes ending at i). Must be computed on the full series
    BEFORE slicing to a display window -- computing it only on an already
    sliced window understates the lookback for the first ~`window` visible
    points (this was a real bug found and fixed during prototyping).
    """
    out = []
    for i in range(len(closes)):
        start = max(0, i - window + 1)
        chunk = closes[start:i + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def render_chart(bars: List[dict], symbol: str, origin: str, lookback_days: int) -> bytes:
    """Single OHLC candlestick PNG with SMA20/SMA50 overlays.

    `bars` must already be filtered to date <= origin by the caller. Only the
    last `lookback_days` bars are displayed, but SMA20/SMA50 are computed over
    the full `bars` history first so they're accurate at the left edge too.
    """
    full_closes = [b["close"] for b in bars]
    full_sma20 = _compute_full_sma(full_closes, 20)
    full_sma50 = _compute_full_sma(full_closes, 50)

    plot_bars = bars[-lookback_days:]
    sma20 = full_sma20[-lookback_days:]
    sma50 = full_sma50[-lookback_days:]

    # Smaller figure than the original prototype (14x7@130dpi ~1820x910px): a
    # pilot run with the larger size saw an 8/20 outright-failure rate on Gemini
    # 503/504/timeout errors (zero such failures with vision off on the same
    # inputs) -- cutting pixel area materially reduces per-request image
    # processing load. 10x5@100dpi (~1000x500px) is still legible for chart
    # reading while being roughly a third of the pixel count.
    fig = Figure(figsize=(10, 5), dpi=100)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)

    for i, b in enumerate(plot_bars):
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        color = "#2ca02c" if c >= o else "#d62728"
        ax.plot([i, i], [l, h], color=color, linewidth=0.8, zorder=2)
        body_low, body_high = min(o, c), max(o, c)
        ax.add_patch(Rectangle((i - 0.3, body_low), 0.6, max(body_high - body_low, 0.01),
                                facecolor=color, edgecolor=color, zorder=3))

    n = len(plot_bars)
    ax.plot(range(n), sma20, color="#1f77b4", linewidth=1.2, label="SMA20")
    ax.plot(range(n), sma50, color="#ff7f0e", linewidth=1.2, label="SMA50")

    tick_idx = list(range(0, n, max(1, n // 15)))
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([plot_bars[i]["date"] for i in tick_idx], rotation=45, ha="right")
    ax.set_xlim(-1, n)
    ax.set_title(f"{symbol} daily chart through {origin} (prediction origin -- no data after this date) -- last {n} trading days")
    ax.set_ylabel("Price ($)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.25)
    fig.tight_layout()

    buf = io.BytesIO()
    canvas.print_png(buf)
    return buf.getvalue()


def render_chart_pair(
    bars: List[dict],
    symbol: str,
    origin: str,
    wide_lookback_days: int = DEFAULT_WIDE_LOOKBACK_DAYS,
    detail_lookback_days: int = DEFAULT_DETAIL_LOOKBACK_DAYS,
) -> Dict[str, bytes]:
    """Returns {"wide": <png bytes>, "detail": <png bytes>}.

    A single timeframe isn't enough: a wide chart shows genuine multi-month
    support/resistance/channel structure but has illegible daily candles; a
    short chart has legible candles but loses that structure. Sending both
    together was validated (this session, against known historical misses) to
    outperform sending either alone.
    """
    return {
        "wide": render_chart(bars, symbol, origin, wide_lookback_days),
        "detail": render_chart(bars, symbol, origin, detail_lookback_days),
    }
