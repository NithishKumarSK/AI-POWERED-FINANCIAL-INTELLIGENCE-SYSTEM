"""
SPX Levels Chart
Renders daily or 15-minute candlestick charts (matplotlib) with horizontal
lines for the key support/resistance levels surfaced elsewhere in the
report, each labeled with its source, so you can see exactly where each
level sits relative to recent price action. Returns PNG bytes for
embedding as a data: URI in the self-contained HTML report.
"""
from __future__ import annotations

import io
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.patches import Rectangle

MAX_LABELED_LEVELS = 12


def _draw_candles(ax, bars: List[Dict]) -> None:
    for i, b in enumerate(bars):
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        color = "#1e9e5a" if c >= o else "#c0392b"
        ax.plot([i, i], [l, h], color=color, linewidth=0.8, zorder=2)
        body_low, body_high = min(o, c), max(o, c)
        ax.add_patch(Rectangle((i - 0.3, body_low), 0.6, max(body_high - body_low, 0.01),
                                facecolor=color, edgecolor=color, zorder=3))


def _draw_level_lines(ax, level_entries: List[Dict], grid_rows: Optional[List[Dict]],
                       plot_low: float, plot_high: float, n: int) -> None:
    if grid_rows:
        visible_grid = [r for r in grid_rows if plot_low * 0.9 <= r["level"] <= plot_high * 1.1]
        for r in visible_grid:
            ax.axhline(r["level"], color="#9aa0a8", linewidth=0.6, linestyle=":", alpha=0.5, zorder=0)
        if visible_grid and len(grid_rows) > 1:
            step = abs(grid_rows[0]["level"] - grid_rows[1]["level"])
            ax.text(-0.5, visible_grid[-1]["level"], f"${step:,.0f} price grid",
                    fontsize=6.5, color="#9aa0a8", va="top", ha="right")

    visible = [e for e in level_entries if plot_low * 0.985 <= e["level"] <= plot_high * 1.015]
    visible = visible[:MAX_LABELED_LEVELS]
    for e in visible:
        color = "#c0392b" if e["kind"] == "resistance" else "#1e9e5a"
        ax.axhline(e["level"], color=color, linewidth=0.9, linestyle="--", alpha=0.55, zorder=1)
        ax.text(n - 0.5, e["level"], f" {e['level']:,.0f}  {e['label']}",
                fontsize=7.2, color=color, va="center", ha="left")


def _draw_projection_band(ax, projection: Dict) -> None:
    ax.axhspan(projection["projected_low"], projection["projected_high"], color="#2563eb", alpha=0.07, zorder=0)
    ax.axhline(projection["projected_high"], color="#2563eb", linewidth=1, linestyle=":", alpha=0.8, zorder=1)
    ax.axhline(projection["projected_low"], color="#2563eb", linewidth=1, linestyle=":", alpha=0.8, zorder=1)
    ax.text(0, projection["projected_high"], "projected high (tomorrow)  ", fontsize=7.2, color="#2563eb", va="bottom", ha="left")
    ax.text(0, projection["projected_low"], "projected low (tomorrow)  ", fontsize=7.2, color="#2563eb", va="top", ha="left")


def render_levels_chart(bars: List[Dict], level_entries: List[Dict], projection: Dict,
                         grid_rows: List[Dict] = None, recent_levels: List[Dict] = None,
                         recent_lookback: int = 10, lookback_days: int = 60, symbol: str = "SPX") -> bytes:
    """Daily candlestick chart, last `lookback_days` sessions."""
    plot_bars = bars[-lookback_days:]
    n = len(plot_bars)

    fig = Figure(figsize=(11, 6.2), dpi=110)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)

    _draw_candles(ax, plot_bars)

    plot_low = min(b["low"] for b in plot_bars)
    plot_high = max(b["high"] for b in plot_bars)

    if n > recent_lookback:
        ax.axvspan(n - recent_lookback - 0.5, n - 0.5, color="#2563eb", alpha=0.05, zorder=0)
        ax.text(n - recent_lookback - 0.3, plot_high, "last 10 sessions",
                fontsize=7, color="#2563eb", va="top", ha="left")

    if recent_levels:
        date_to_idx = {b["date"]: i for i, b in enumerate(plot_bars)}
        for lv in recent_levels:
            idx = date_to_idx.get(lv["date"])
            if idx is None:
                continue
            color = "#c0392b" if lv["kind"] == "resistance" else "#1e9e5a"
            marker = "v" if lv["kind"] == "resistance" else "^"
            ax.scatter([idx], [lv["level"]], marker=marker, color=color, s=45,
                       zorder=5, edgecolor="white", linewidth=0.6)

    _draw_level_lines(ax, level_entries, grid_rows, plot_low, plot_high, n)
    _draw_projection_band(ax, projection)

    tick_idx = list(range(0, n, max(1, n // 12)))
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([plot_bars[i]["date"] for i in tick_idx], rotation=45, ha="right", fontsize=8)
    ax.set_xlim(-6, n + 14)
    ax.set_title(f"{symbol} -- last {n} sessions with key levels")
    ax.set_ylabel("Price")
    ax.grid(alpha=0.2)
    fig.tight_layout()

    buf = io.BytesIO()
    canvas.print_png(buf)
    return buf.getvalue()


def render_intraday_levels_chart(bars_15m: List[Dict], level_entries: List[Dict], projection: Dict,
                                  grid_rows: List[Dict] = None, sessions: int = 5, symbol: str = "SPX") -> bytes:
    """15-minute candlestick chart, last `sessions` full trading sessions,
    with vertical dividers between days -- same key levels overlaid so you
    can see exactly how intraday price action relates to them."""
    dates_seen: List[str] = []
    for b in bars_15m:
        if b["date"] not in dates_seen:
            dates_seen.append(b["date"])
    keep_dates = set(dates_seen[-sessions:])
    plot_bars = [b for b in bars_15m if b["date"] in keep_dates]
    n = len(plot_bars)

    fig = Figure(figsize=(11, 6.2), dpi=110)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)

    _draw_candles(ax, plot_bars)

    plot_low = min(b["low"] for b in plot_bars)
    plot_high = max(b["high"] for b in plot_bars)

    session_starts: List[int] = []
    prev_date = None
    for i, b in enumerate(plot_bars):
        if b["date"] != prev_date:
            session_starts.append(i)
            prev_date = b["date"]
    for idx in session_starts[1:]:
        ax.axvline(idx - 0.5, color="#9aa0a8", linewidth=0.7, linestyle="-", alpha=0.35, zorder=0)

    _draw_level_lines(ax, level_entries, grid_rows, plot_low, plot_high, n)
    _draw_projection_band(ax, projection)

    ax.set_xticks(session_starts)
    ax.set_xticklabels([plot_bars[i]["date"] for i in session_starts], rotation=45, ha="right", fontsize=8)
    ax.set_xlim(-6, n + 14)
    ax.set_title(f"{symbol} -- last {len(keep_dates)} sessions, 15-min candles, with key levels")
    ax.set_ylabel("Price")
    ax.grid(alpha=0.2)
    fig.tight_layout()

    buf = io.BytesIO()
    canvas.print_png(buf)
    return buf.getvalue()
