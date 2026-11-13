"""
Tests for core/downtrend_duration_analyzer.py -- ported peak/trough/
downtrend-duration detection math. Synthetic data only, no network.
Chronological order (oldest first), matching historical_price_service's
own native bar order.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from downtrend_duration_analyzer import compute_statistics, detect_peaks_troughs, find_downtrends


def _dates(n, start="2024-01-01"):
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range(n)]


def test_detect_peaks_troughs_finds_a_clean_v_shape():
    # Rise 0..29 (peak at 29), fall 29..0 (trough at 59), rise again.
    closes = list(range(100, 130)) + list(range(129, 99, -1)) + list(range(100, 130))
    peaks, troughs = detect_peaks_troughs(closes, window=10)
    assert 29 in peaks
    assert 59 in troughs


def test_find_downtrends_computes_depth_and_duration():
    # Strictly unimodal (no plateau at the peak) so there's exactly one
    # unambiguous peak index: rise 100->129 (idx0-29), fall 129->101 (idx30-58), rise again.
    closes = [float(c) for c in (list(range(100, 130)) + list(range(128, 100, -1)) + list(range(101, 130)))]
    dates = _dates(len(closes))
    peaks, troughs = detect_peaks_troughs(closes, window=10)
    downtrends = find_downtrends(dates, closes, peaks, troughs, min_depth_pct=5.0, min_duration_days=3)
    assert len(downtrends) == 1
    dt = downtrends[0]
    assert dt["peak_idx"] == 29
    assert dt["peak_price"] == 129.0
    assert dt["trough_price"] == closes[dt["trough_idx"]]
    assert dt["duration_days"] == dt["trough_idx"] - dt["peak_idx"]
    assert dt["depth_pct"] < -5.0


def test_find_downtrends_filters_shallow_moves():
    # Decline of only ~2% -- below the 5% min_depth_pct filter.
    closes = [100.0] * 15 + [99.0, 98.5, 98.0] + [100.0] * 15
    dates = _dates(len(closes))
    peaks, troughs = detect_peaks_troughs(closes, window=10)
    downtrends = find_downtrends(dates, closes, peaks, troughs, min_depth_pct=5.0, min_duration_days=1)
    assert downtrends == []


def test_compute_statistics_empty_list():
    stats = compute_statistics([])
    assert stats["total_downtrends"] == 0
    assert stats["median_duration_days"] == 0


def test_compute_statistics_matches_known_percentiles():
    downtrends = [{"duration_days": d} for d in (5, 10, 15, 20, 25)]
    stats = compute_statistics(downtrends)
    assert stats["total_downtrends"] == 5
    assert stats["median_duration_days"] == 15
    assert stats["mean_duration_days"] == 15.0
