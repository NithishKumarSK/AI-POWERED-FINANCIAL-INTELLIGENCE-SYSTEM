"""
Tests for core/data_quality_checker.py -- pure text-processing, no
network/no file I/O dependency.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from data_quality_checker import (
    check_allocations,
    check_dates,
    check_price_scale,
    check_units,
    run_all_checks,
)


def test_price_scale_flags_etf_priced_like_futures():
    findings = check_price_scale("GLD: $2,800 today, up sharply.")
    assert len(findings) == 1
    assert findings[0]["category"] == "price_scale"
    assert "GLD" in findings[0]["message"]


def test_price_scale_accepts_valid_etf_price():
    assert check_price_scale("GLD: $268 today.") == []


def test_price_scale_accepts_valid_futures_price():
    assert check_price_scale("GC: $2,650 per ounce.") == []


def test_price_scale_flags_futures_priced_like_etf():
    findings = check_price_scale("GC: $26 per ounce.")
    assert len(findings) == 1


def test_price_scale_multiple_tickers_same_line():
    findings = check_price_scale("SPY: $5800 vs SPX: $580")
    assert len(findings) == 2


def test_check_dates_flags_real_mismatch():
    findings = check_dates("The report covers January 1, 2026 (Monday) through month-end.")
    assert len(findings) == 1
    assert findings[0]["severity"] == "ERROR"
    assert "actual weekday is Thursday" in findings[0]["message"]


def test_check_dates_accepts_correct_weekday():
    assert check_dates("The report covers January 1, 2026 (Thursday) through month-end.") == []


def test_check_dates_ignores_lines_without_weekday_annotation():
    assert check_dates("The report covers January 1, 2026 through month-end.") == []


def test_check_allocations_flags_total_over_100():
    text = "## Allocation\n- Stocks: 60%\n- Bonds: 50%\n"
    findings = check_allocations(text)
    assert len(findings) == 1
    assert "110.0%" in findings[0]["message"]


def test_check_allocations_accepts_total_near_100():
    text = "## Allocation\n- Stocks: 60%\n- Bonds: 40%\n"
    assert check_allocations(text) == []


def test_check_allocations_ignores_percentages_outside_allocation_section():
    text = "## Market Summary\nRSI is at 72% overbought, YoY growth 15%.\n"
    assert check_allocations(text) == []


def test_check_allocations_stops_at_next_heading():
    text = "## Allocation\n- Stocks: 60%\n- Bonds: 40%\n## Risk\nRSI at 72%.\n"
    assert check_allocations(text) == []


def test_check_units_flags_mixed_bp_and_percent():
    findings = check_units("The Fed raised rates 25bps to 5.25%.")
    assert len(findings) == 1
    assert findings[0]["severity"] == "INFO"


def test_check_units_no_flag_when_only_percent():
    assert check_units("Returns were up 5.25% this week.") == []


def test_run_all_checks_combines_and_sorts_by_line():
    text = (
        "GC: $26 per ounce.\n"
        "## Allocation\n- Stocks: 60%\n- Bonds: 50%\n"
    )
    findings = run_all_checks(text)
    assert len(findings) == 2
    assert findings[0]["line_number"] == 1
    assert findings[1]["line_number"] == 3


def test_run_all_checks_respects_checks_filter():
    text = "GC: $26 per ounce.\n## Allocation\n- Stocks: 60%\n- Bonds: 50%\n"
    findings = run_all_checks(text, checks=["price_scale"])
    assert len(findings) == 1
    assert findings[0]["category"] == "price_scale"
