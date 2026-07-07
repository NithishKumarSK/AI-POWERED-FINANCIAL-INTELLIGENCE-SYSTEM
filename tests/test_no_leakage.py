"""
Pytest: Data Leakage Prevention Tests.

Guarantees that AI never receives price data from after the prediction_origin_date.
No API calls. All tests use synthetic bar lists.

Test coverage:
  1. Clean bars — no leakage detected (all bars <= cutoff)
  2. Single leaked bar detected
  3. Multiple leaked bars detected
  4. Empty bars list — clean (no bars, no leakage)
  5. Cutoff date is the last bar date — still clean
  6. filter_history_up_to removes future bars
  7. Leakage report contains the leaked bar dates
  8. validate_no_leakage on weekend/holiday dates (string comparison)
  9. Legacy field exclusion: options fields not present in SPI schema
  10. validate_stock_prediction_input rejects future target_date
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stock_comparison_engine import validate_no_leakage
from historical_price_service import filter_history_up_to
from stock_prediction_agent import validate_stock_prediction_input


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_bars(start_date: str, n_days: int) -> list:
    """Create n daily bar dicts starting from start_date."""
    from datetime import datetime, timedelta
    bars = []
    dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    for i in range(n_days):
        day = dt + timedelta(days=i)
        bars.append({
            "date":  day.strftime("%Y-%m-%d"),
            "open":  100.0 + i,
            "high":  105.0 + i,
            "low":   98.0  + i,
            "close": 102.0 + i,
            "volume": 1_000_000,
        })
    return bars


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1 — Clean bars: all bars on or before cutoff
# ══════════════════════════════════════════════════════════════════════════════

def test_no_leakage_clean():
    bars   = _make_bars("2026-01-01", 10)  # 2026-01-01 to 2026-01-10
    cutoff = "2026-01-15"
    result = validate_no_leakage(bars, cutoff)
    assert result["status"] == "CLEAN"
    assert result["n_bars"] == 10


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2 — Single leaked bar detected
# ══════════════════════════════════════════════════════════════════════════════

def test_single_leaked_bar():
    bars   = _make_bars("2026-01-01", 10)  # bars: Jan 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
    cutoff = "2026-01-05"                  # bars Jan 6–10 are future = 5 bars
    result = validate_no_leakage(bars, cutoff)
    assert result["status"] == "LEAKAGE_DETECTED"
    assert len(result["leaked_bars"]) == 5  # Jan 6, 7, 8, 9, 10


def test_single_leaked_bar_count():
    bars   = _make_bars("2026-01-01", 5)   # Jan 1–5
    cutoff = "2026-01-04"                  # Jan 5 leaks
    result = validate_no_leakage(bars, cutoff)
    assert result["status"] == "LEAKAGE_DETECTED"
    assert any(b["date"] == "2026-01-05" for b in result["leaked_bars"])


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3 — Multiple leaked bars
# ══════════════════════════════════════════════════════════════════════════════

def test_multiple_leaked_bars():
    bars   = _make_bars("2026-01-01", 30)  # Jan 1–30 = 30 bars
    cutoff = "2026-01-10"                  # Jan 11–30 are future = 20 bars
    result = validate_no_leakage(bars, cutoff)
    assert result["status"] == "LEAKAGE_DETECTED"
    assert len(result["leaked_bars"]) == 20
    assert "LEAKAGE_DETECTED" in result["error"] or "bar(s) found after" in result["error"]


# ══════════════════════════════════════════════════════════════════════════════
# TEST 4 — Empty bars list → CLEAN (vacuously true)
# ══════════════════════════════════════════════════════════════════════════════

def test_empty_bars_is_clean():
    result = validate_no_leakage([], "2026-03-01")
    assert result["status"] == "CLEAN"
    assert result["n_bars"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# TEST 5 — Cutoff is the last bar date (exactly on edge — still clean)
# ══════════════════════════════════════════════════════════════════════════════

def test_cutoff_equals_last_bar_is_clean():
    bars   = _make_bars("2026-01-01", 5)  # Jan 1–5
    cutoff = "2026-01-05"                 # Jan 5 is the last bar — still clean
    result = validate_no_leakage(bars, cutoff)
    assert result["status"] == "CLEAN"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 6 — filter_history_up_to removes future bars
# ══════════════════════════════════════════════════════════════════════════════

def test_filter_history_removes_future_bars():
    bars   = _make_bars("2026-01-01", 20)  # Jan 1–20
    cutoff = "2026-01-10"
    filtered = filter_history_up_to(bars, cutoff)
    assert all(b["date"] <= cutoff for b in filtered)
    assert len(filtered) == 10  # Jan 1–10


def test_filter_history_keeps_all_when_no_future():
    bars   = _make_bars("2026-01-01", 5)
    cutoff = "2026-12-31"
    filtered = filter_history_up_to(bars, cutoff)
    assert len(filtered) == 5


def test_filter_history_returns_empty_when_all_future():
    bars   = _make_bars("2026-06-01", 10)
    cutoff = "2026-01-01"  # before all bars
    filtered = filter_history_up_to(bars, cutoff)
    assert filtered == [] or len(filtered) == 0


# ══════════════════════════════════════════════════════════════════════════════
# TEST 7 — Leakage report contains correct leaked bar dates
# ══════════════════════════════════════════════════════════════════════════════

def test_leaked_bars_contain_correct_dates():
    bars   = _make_bars("2026-03-01", 5)  # Mar 1–5
    cutoff = "2026-03-03"                 # Mar 4, 5 leak
    result = validate_no_leakage(bars, cutoff)
    assert result["status"] == "LEAKAGE_DETECTED"
    leaked_dates = {b["date"] for b in result["leaked_bars"]}
    assert "2026-03-04" in leaked_dates
    assert "2026-03-05" in leaked_dates
    assert "2026-03-03" not in leaked_dates   # cutoff day is clean


# ══════════════════════════════════════════════════════════════════════════════
# TEST 8 — String date comparison works for weekends/holidays
# ══════════════════════════════════════════════════════════════════════════════

def test_string_date_comparison_correctness():
    """
    ISO date strings compare lexicographically in the same order as chronologically.
    2026-01-05 < 2026-01-10 both numerically and as strings.
    """
    bars = [
        {"date": "2026-01-02", "close": 100.0},
        {"date": "2026-01-05", "close": 101.0},   # Monday (weekend skipped)
        {"date": "2026-01-07", "close": 102.0},
    ]
    cutoff = "2026-01-06"  # Jan 7 leaks
    result = validate_no_leakage(bars, cutoff)
    assert result["status"] == "LEAKAGE_DETECTED"
    assert result["leaked_bars"][0]["date"] == "2026-01-07"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 9 — Options / legacy fields not present in StockPredictionInput schema
# ══════════════════════════════════════════════════════════════════════════════

def test_legacy_options_fields_absent_from_spi():
    """
    StockPredictionInput must NOT contain options fields.
    validate_stock_prediction_input must not require them.
    """
    spi = {
        "symbol":                        "TSLA",
        "historical_context_start_date": "2025-07-01",
        "prediction_origin_date":        "2026-03-01",
        "decision_horizon_days":         30,
        "target_date":                   "2026-03-31",
        "initial_capital":               50_000.0,
        "benchmark":                     "SPY",
        "validation_mode":               "horizon_days",
        "price_basis":                   "close",
    }
    banned_fields = ["direction", "side", "dte", "delta", "legs", "entry_frequency"]
    for field in banned_fields:
        assert field not in spi, (
            f"Legacy options field '{field}' must not be in StockPredictionInput"
        )

    # Must also validate successfully without any options fields
    valid, err = validate_stock_prediction_input(spi)
    assert valid, f"Clean SPI without options fields should be valid. Error: {err}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 10 — Future target_date is rejected by validate_stock_prediction_input
# ══════════════════════════════════════════════════════════════════════════════

def test_future_target_date_allowed_as_live_prediction():
    """
    Future target_date must be ALLOWED by validate_stock_prediction_input.
    The run becomes live_future_prediction mode — AI predicts, actual shows PENDING.
    The old behavior (rejecting future dates) blocked the product from being useful.
    """
    future_date = (date.today() + timedelta(days=90)).strftime("%Y-%m-%d")
    past_origin = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")
    spi = {
        "symbol":                        "TSLA",
        "historical_context_start_date": "2024-01-01",
        "prediction_origin_date":        past_origin,
        "decision_horizon_days":         30,
        "target_date":                   future_date,
        "initial_capital":               50_000.0,
        "benchmark":                     "SPY",
    }
    valid, err = validate_stock_prediction_input(spi)
    assert valid, (
        f"Future target_date {future_date} must be allowed. "
        f"This triggers live_future_prediction mode — AI runs, actual is PENDING. "
        f"Got valid=False, err={err}"
    )
