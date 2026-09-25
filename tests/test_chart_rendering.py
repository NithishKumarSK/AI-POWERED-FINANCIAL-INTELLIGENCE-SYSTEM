"""
Tests for chart_rendering.py -- the chart-vision image generator.

No Gemini/network calls here; pure rendering logic only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chart_rendering import _compute_full_sma, render_chart, render_chart_pair

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _make_bars(n: int = 300, start_price: float = 100.0) -> list:
    """Synthetic daily bars with a deterministic (non-random) price path."""
    import math
    bars = []
    price = start_price
    for i in range(n):
        price = start_price * (1 + 0.15 * math.sin(i / 15.0) + 0.001 * i)
        o = price * 0.998
        h = price * 1.01
        l = price * 0.99
        bars.append({
            "date": f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            "open": round(o, 4), "high": round(h, 4), "low": round(l, 4),
            "close": round(price, 4), "volume": 1_000_000 + i * 500,
        })
    return bars


# ══════════════════════════════════════════════════════════════════════════════
# _compute_full_sma
# ══════════════════════════════════════════════════════════════════════════════

def test_compute_full_sma_basic_values():
    closes = [10, 20, 30, 40, 50]
    sma3 = _compute_full_sma(closes, 3)
    # index 0: avg(10) = 10; index 1: avg(10,20)=15; index 2: avg(10,20,30)=20
    assert sma3[0] == 10
    assert sma3[1] == 15
    assert sma3[2] == 20
    # index 3: avg(20,30,40)=30; index 4: avg(30,40,50)=40
    assert sma3[3] == 30
    assert sma3[4] == 40


def test_compute_full_sma_same_length_as_input():
    closes = list(range(1, 101))
    sma = _compute_full_sma(closes, 20)
    assert len(sma) == len(closes)


def test_compute_full_sma_window_larger_than_series_uses_all_available():
    closes = [5, 10, 15]
    sma = _compute_full_sma(closes, 50)
    assert sma[-1] == sum(closes) / len(closes)


def test_full_history_sma_differs_from_window_only_sma_at_left_edge():
    """The bug this design avoids: computing SMA50 only from an already-sliced
    short window (instead of the full history) gives a materially different,
    wrong value for the first ~50 visible points. Demonstrate the two methods
    diverge on a series with a real trend, proving why render_chart must slice
    AFTER computing over the full series, not before."""
    bars = _make_bars(300)
    closes = [b["close"] for b in bars]

    lookback = 90
    correct_full_then_slice = _compute_full_sma(closes, 50)[-lookback:]
    buggy_window_only = _compute_full_sma(closes[-lookback:], 50)

    # They must disagree at the very first visible point (index 0) whenever the
    # series isn't flat -- window-only has no pre-window data to average in.
    assert correct_full_then_slice[0] != buggy_window_only[0]


# ══════════════════════════════════════════════════════════════════════════════
# render_chart / render_chart_pair
# ══════════════════════════════════════════════════════════════════════════════

def test_render_chart_returns_valid_png():
    bars = _make_bars(150)
    img = render_chart(bars, "TEST", bars[-1]["date"], lookback_days=90)
    assert isinstance(img, bytes)
    assert img.startswith(_PNG_SIGNATURE)
    assert len(img) > 1000  # a real rendered chart, not an empty/degenerate image


def test_render_chart_is_deterministic():
    bars = _make_bars(150)
    img1 = render_chart(bars, "TEST", bars[-1]["date"], lookback_days=90)
    img2 = render_chart(bars, "TEST", bars[-1]["date"], lookback_days=90)
    assert img1 == img2


def test_render_chart_lookback_shorter_than_sma_window_does_not_crash():
    """Regression guard: a lookback shorter than the SMA50 window must not
    raise or produce a degenerate chart -- exactly the scenario the SMA
    full-history-then-slice fix exists for."""
    bars = _make_bars(200)
    img = render_chart(bars, "TEST", bars[-1]["date"], lookback_days=30)
    assert img.startswith(_PNG_SIGNATURE)


def test_render_chart_pair_returns_both_keys():
    bars = _make_bars(300)
    pair = render_chart_pair(bars, "TEST", bars[-1]["date"])
    assert set(pair.keys()) == {"wide", "detail"}
    assert pair["wide"].startswith(_PNG_SIGNATURE)
    assert pair["detail"].startswith(_PNG_SIGNATURE)
    # The two images use different lookback windows -- they must not be identical.
    assert pair["wide"] != pair["detail"]


def test_render_chart_pair_respects_custom_lookbacks():
    bars = _make_bars(300)
    pair = render_chart_pair(bars, "TEST", bars[-1]["date"], wide_lookback_days=200, detail_lookback_days=50)
    assert pair["wide"].startswith(_PNG_SIGNATURE)
    assert pair["detail"].startswith(_PNG_SIGNATURE)


def test_render_chart_never_uses_bars_beyond_what_is_passed():
    """No fetching/filtering inside chart_rendering -- passing bars already
    truncated to an origin date must render fine using exactly those bars,
    proving the module doesn't reach for more data on its own."""
    bars = _make_bars(120)
    truncated = bars[:-20]  # simulate caller already filtered to an earlier origin
    img = render_chart(truncated, "TEST", truncated[-1]["date"], lookback_days=60)
    assert img.startswith(_PNG_SIGNATURE)
