"""
Tests for core/dividend_growth_pullback_screener.py -- ported dividend
growth quality + RSI pullback-timing analysis (scope-reduced composite,
see that module's docstring). Synthetic data only, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from dividend_growth_pullback_screener import (
    analyze_dividend_growth,
    analyze_payout_sustainability,
    calculate_cagr,
    calculate_composite_score,
    calculate_rsi,
)


# ── calculate_rsi ──────────────────────────────────────────────────────────

def test_rsi_all_gains_is_100():
    prices = [100 + i for i in range(20)]  # steadily rising, chronological
    assert calculate_rsi(prices, period=14) == 100.0


def test_rsi_mixed_moves_is_between_0_and_100():
    prices = [100, 102, 101, 103, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108, 107]
    rsi = calculate_rsi(prices, period=14)
    assert rsi is not None
    assert 0 <= rsi <= 100


def test_rsi_insufficient_data():
    assert calculate_rsi([100, 101, 102], period=14) is None


# ── calculate_cagr ─────────────────────────────────────────────────────────

def test_calculate_cagr_basic():
    assert calculate_cagr(100, 133.1, 3) == 10.0  # 10% annual growth for 3 years


def test_calculate_cagr_invalid_inputs_return_none():
    assert calculate_cagr(0, 100, 3) is None
    assert calculate_cagr(100, -5, 3) is None
    assert calculate_cagr(100, 150, 0) is None


# ── analyze_dividend_growth ─────────────────────────────────────────────────

def test_analyze_dividend_growth_stable_consistent_series():
    series = [
        {"date": "2026-12-31", "dividend_per_share": 2.04},
        {"date": "2025-12-31", "dividend_per_share": 1.93},
        {"date": "2024-12-31", "dividend_per_share": 1.83},
        {"date": "2023-12-31", "dividend_per_share": 1.75},
    ]
    result = analyze_dividend_growth(series)
    assert result["consistent"] is True
    assert result["cagr_3yr"] is not None and result["cagr_3yr"] > 0
    assert result["latest_annual_dividend"] == 2.04
    assert result["years_of_growth"] >= 3


def test_analyze_dividend_growth_cut_detected_as_inconsistent():
    series = [
        {"date": "2026-12-31", "dividend_per_share": 1.00},  # big cut
        {"date": "2025-12-31", "dividend_per_share": 2.00},
        {"date": "2024-12-31", "dividend_per_share": 1.90},
        {"date": "2023-12-31", "dividend_per_share": 1.80},
    ]
    result = analyze_dividend_growth(series)
    assert result["consistent"] is False


def test_analyze_dividend_growth_insufficient_data():
    result = analyze_dividend_growth([{"date": "2026-12-31", "dividend_per_share": 2.0}])
    assert result["cagr_3yr"] is None
    assert result["years_of_growth"] == 0


def test_analyze_dividend_growth_missing_per_share_values_excluded():
    series = [
        {"date": "2026-12-31", "dividend_per_share": None},  # no shares data that year
        {"date": "2025-12-31", "dividend_per_share": 1.93},
        {"date": "2024-12-31", "dividend_per_share": 1.83},
        {"date": "2023-12-31", "dividend_per_share": 1.75},
        {"date": "2022-12-31", "dividend_per_share": 1.68},
    ]
    result = analyze_dividend_growth(series)
    assert result["cagr_3yr"] is not None  # falls back to the 4 usable entries


# ── analyze_payout_sustainability ───────────────────────────────────────────

def test_payout_sustainability_covered_and_sustainable():
    cash_flow = {"dividends_paid": 100.0, "free_cash_flow": 200.0}
    result = analyze_payout_sustainability(cash_flow, net_income=500.0)
    assert result["fcf_coverage_status"] == "COVERED"
    assert result["payout_ratio"] == 20.0
    assert result["fcf_payout_ratio"] == 50.0
    assert result["sustainable"] is True


def test_payout_sustainability_insufficient_fcf_not_sustainable():
    cash_flow = {"dividends_paid": 100.0, "free_cash_flow": 80.0}
    result = analyze_payout_sustainability(cash_flow, net_income=500.0)
    assert result["fcf_coverage_status"] == "INSUFFICIENT_FCF"
    assert result["sustainable"] is False


def test_payout_sustainability_negative_fcf():
    cash_flow = {"dividends_paid": 100.0, "free_cash_flow": -20.0}
    result = analyze_payout_sustainability(cash_flow, net_income=500.0)
    assert result["fcf_coverage_status"] == "NEGATIVE_FCF"
    assert result["fcf_payout_ratio"] is None


def test_payout_sustainability_no_dividends_data():
    result = analyze_payout_sustainability({}, net_income=500.0)
    assert result["sustainable"] is False
    assert "unavailable" in result["sustainability_note"]


def test_payout_sustainability_zero_dividends():
    result = analyze_payout_sustainability({"dividends_paid": 0.0}, net_income=500.0)
    assert result["fcf_coverage_status"] == "NO_DIVIDEND"


# ── calculate_composite_score ───────────────────────────────────────────────

def test_composite_score_strong_dividend_growth_and_oversold():
    score = calculate_composite_score(div_cagr=22.0, div_consistent=True, profit_margin=25.0, rsi=20.0)
    assert score == 100.0  # 45 (40+5) + 15 + 40 = 100


def test_composite_score_weak_everything():
    score = calculate_composite_score(div_cagr=5.0, div_consistent=False, profit_margin=2.0, rsi=70.0)
    assert score == 34.0  # 20 + 4 + 10


def test_composite_score_missing_inputs_use_neutral_defaults():
    score = calculate_composite_score(div_cagr=None, div_consistent=False, profit_margin=None, rsi=None)
    assert score == 34.0  # same as all-weak since defaults map to the weak bands
