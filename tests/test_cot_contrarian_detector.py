"""
Tests for core/cot_contrarian_detector.py -- pure calculation, synthetic
CFTC-row-shaped data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from cot_contrarian_detector import (
    analyze_cot_crowding,
    classify_crowding,
    compute_cot_index,
    compute_net_position,
    compute_oi_normalized_net,
    compute_week_over_week_change,
    sort_dedupe_rows,
)


def _row(date, long_=1000, short_=500, oi=10000):
    return {"report_date_as_yyyy_mm_dd": date, "noncomm_positions_long_all": str(long_),
            "noncomm_positions_short_all": str(short_), "open_interest_all": str(oi)}


def test_compute_net_position_basic():
    assert compute_net_position(_row("d1", long_=1200, short_=500)) == 700.0


def test_compute_net_position_missing_field_returns_none():
    assert compute_net_position({"report_date_as_yyyy_mm_dd": "d1"}) is None


def test_compute_oi_normalized_net():
    assert compute_oi_normalized_net(500.0, "10000") == 0.05


def test_compute_oi_normalized_net_zero_oi_is_none():
    assert compute_oi_normalized_net(500.0, "0") is None


def test_compute_oi_normalized_net_none_position():
    assert compute_oi_normalized_net(None, "10000") is None


def test_sort_dedupe_rows_sorts_ascending_and_dedups_keeping_last():
    rows = [_row("2026-01-15", long_=1), _row("2026-01-01", long_=2), _row("2026-01-01", long_=3)]
    result = sort_dedupe_rows(rows)
    assert [r["noncomm_positions_long_all"] for r in result] == ["3", "1"]


def test_sort_dedupe_rows_drops_undated_rows():
    rows = [_row("2026-01-01"), {"noncomm_positions_long_all": "1"}]
    result = sort_dedupe_rows(rows)
    assert len(result) == 1


def test_compute_cot_index_insufficient_history():
    assert compute_cot_index([100.0, 200.0], lookback_weeks=156) is None


def test_compute_cot_index_zero_range_is_none():
    assert compute_cot_index([100.0] * 156, lookback_weeks=156) is None


def test_compute_cot_index_at_max_is_100():
    series = [0.0] * 155 + [100.0]
    assert compute_cot_index(series, lookback_weeks=156) == 100.0


def test_compute_cot_index_at_min_is_0():
    series = [100.0] * 155 + [0.0]
    assert compute_cot_index(series, lookback_weeks=156) == 0.0


def test_compute_cot_index_midpoint_is_50():
    series = [0.0] * 77 + [100.0] * 77 + [50.0]
    assert compute_cot_index(series, lookback_weeks=155) == 50.0


def test_compute_week_over_week_change():
    assert compute_week_over_week_change([100.0, 150.0]) == 50.0
    assert compute_week_over_week_change([100.0]) is None


def test_classify_crowding_boundaries():
    assert classify_crowding(90.0) == "CROWDED_LONG"
    assert classify_crowding(10.0) == "CROWDED_SHORT"
    assert classify_crowding(50.0) == "NEUTRAL"
    assert classify_crowding(None) == "NEUTRAL"


def test_analyze_cot_crowding_crowded_long():
    import datetime as dt
    d0 = dt.date(2023, 1, 3)
    rows = []
    for i in range(156):
        d = (d0 + dt.timedelta(weeks=i)).isoformat()
        rows.append(_row(d, long_=1000 + i, short_=500))  # steadily rising net -> current is the max
    result = analyze_cot_crowding(rows)
    assert result["classification"] == "CROWDED_LONG"
    assert result["cot_index_primary"] == 100.0
    assert result["weeks_used"] == 156


def test_analyze_cot_crowding_insufficient_history_is_neutral():
    rows = [_row("2026-01-01")]
    result = analyze_cot_crowding(rows)
    assert result["classification"] == "NEUTRAL"
    assert result["cot_index_primary"] is None
