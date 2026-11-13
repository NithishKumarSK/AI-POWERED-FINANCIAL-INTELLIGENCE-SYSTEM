"""
Tests for core/canslim_screener.py -- ported William O'Neil CANSLIM
methodology (C/A/N/S/I/M components + Phase 3 composite scorer). Synthetic
data only, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from canslim_screener import (
    calculate_annual_growth,
    calculate_composite_score_phase3,
    calculate_institutional_sponsorship,
    calculate_market_direction,
    calculate_newness,
    calculate_quarterly_growth,
    calculate_supply_demand,
    check_minimum_thresholds_phase3,
    score_current_earnings,
)


# ── calculate_quarterly_growth (C) ────────────────────────────────────────

def test_quarterly_growth_exceptional_scores_100():
    quarters = [
        {"date": "2026-06-30", "eps": 2.70, "revenue": 13_507_000_000},
        {"date": "2026-03-31", "eps": 1.09, "revenue": 7_192_000_000},
        {"date": "2025-12-31", "eps": 0.88, "revenue": 6_051_000_000},
        {"date": "2025-09-30", "eps": 0.58, "revenue": 5_931_000_000},
        {"date": "2025-06-30", "eps": 0.51, "revenue": 6_704_000_000},  # year-ago
    ]
    result = calculate_quarterly_growth(quarters)
    assert result["score"] == 100
    assert result["error"] is None


def test_quarterly_growth_turnaround_handles_negative_prior_eps():
    # year_ago_eps is negative (not exactly zero) -- real % growth, not the capped path.
    quarters = [
        {"date": "2026-06-30", "eps": 0.50, "revenue": 10_000_000_000},
        {"date": "2026-03-31", "eps": 0.20, "revenue": 9_500_000_000},
        {"date": "2025-12-31", "eps": -0.10, "revenue": 9_000_000_000},
        {"date": "2025-09-30", "eps": -0.30, "revenue": 8_500_000_000},
        {"date": "2025-06-30", "eps": -0.40, "revenue": 8_000_000_000},
    ]
    result = calculate_quarterly_growth(quarters)
    assert result["latest_qtr_eps_growth"] == 225.0  # (0.50 - (-0.40)) / abs(-0.40) * 100
    assert result["score"] == 100  # revenue growth is also >=25%


def test_quarterly_growth_exact_zero_prior_eps_reads_as_missing():
    # `eps or epsdiluted or netIncomePerShare` treats a real 0.0 EPS as falsy
    # and falls through to the other (unset) field names -- the same
    # "or"-chain quirk the ported original has, not something introduced here.
    quarters = [
        {"date": "2026-06-30", "eps": 0.50, "revenue": 10_000_000_000},
        {"date": "2026-03-31", "eps": 0.20, "revenue": 9_500_000_000},
        {"date": "2025-12-31", "eps": -0.10, "revenue": 9_000_000_000},
        {"date": "2025-09-30", "eps": -0.30, "revenue": 8_500_000_000},
        {"date": "2025-06-30", "eps": 0.0, "revenue": 8_000_000_000},  # exactly zero
    ]
    result = calculate_quarterly_growth(quarters)
    assert result["score"] == 0
    assert result["error"] == "EPS data missing or invalid"


def test_quarterly_growth_insufficient_data():
    result = calculate_quarterly_growth([{"date": "d", "eps": 1.0, "revenue": 100}])
    assert result["score"] == 0
    assert "Insufficient" in result["error"]


def test_score_current_earnings_bands():
    assert score_current_earnings(55, 30) == 100
    assert score_current_earnings(35, 20) == 80
    assert score_current_earnings(20, 12) == 60
    assert score_current_earnings(12, 0) == 40
    assert score_current_earnings(5, 0) == 0


# ── calculate_annual_growth (A) ────────────────────────────────────────────

def test_annual_growth_stable_high_cagr_scores_well():
    years = [
        {"date": "2026-12-31", "eps": 10.0, "revenue": 1_000_000_000},
        {"date": "2025-12-31", "eps": 7.0, "revenue": 800_000_000},
        {"date": "2024-12-31", "eps": 5.0, "revenue": 600_000_000},
        {"date": "2023-12-31", "eps": 3.5, "revenue": 500_000_000},
    ]
    result = calculate_annual_growth(years)
    assert result["stability"] == "stable"
    assert result["eps_cagr_3yr"] > 40
    assert result["score"] >= 90


def test_annual_growth_negative_eps_year_rejects():
    years = [
        {"date": "2026-12-31", "eps": 5.0, "revenue": 500_000_000},
        {"date": "2025-12-31", "eps": -1.0, "revenue": 400_000_000},
        {"date": "2024-12-31", "eps": 3.0, "revenue": 300_000_000},
        {"date": "2023-12-31", "eps": 2.0, "revenue": 250_000_000},
    ]
    result = calculate_annual_growth(years)
    assert result["score"] == 0
    assert "Negative or zero EPS" in result["error"]


def test_annual_growth_insufficient_years_is_neutral():
    result = calculate_annual_growth([{"date": "d", "eps": 1.0, "revenue": 100}])
    assert result["score"] == 50


# ── calculate_newness (N) ──────────────────────────────────────────────────

def test_newness_at_high_with_breakout_scores_100():
    quote = {"price": 496.0, "yearHigh": 496.0, "yearLow": 280.0, "volume": 60_000_000, "avgVolume": 40_000_000}
    result = calculate_newness(quote)
    assert result["score"] == 100
    assert result["breakout_detected"] is True


def test_newness_far_from_high_scores_low():
    quote = {"price": 50.0, "yearHigh": 80.0, "yearLow": 45.0, "volume": 1_000_000, "avgVolume": 1_200_000}
    result = calculate_newness(quote)
    assert result["score"] == 20


def test_newness_missing_quote_data():
    result = calculate_newness({})
    assert result["score"] == 0


# ── calculate_supply_demand (S) ────────────────────────────────────────────

def _price_history(n, up_days, down_days):
    """n days alternating up/down to hit the requested up/down day counts."""
    bars = []
    price = 100.0
    for i in range(n):
        if i % 2 == 0 and up_days > 0:
            price += 1.0
            vol = 2_000_000
            up_days -= 1
        elif down_days > 0:
            price -= 1.0
            vol = 1_000_000
            down_days -= 1
        else:
            vol = 500_000
        bars.append({"date": f"2026-01-{i+1:02d}", "close": price, "volume": vol})
    return list(reversed(bars))  # most-recent-first


def test_supply_demand_accumulation_scores_high():
    hist = {"historical": _price_history(65, up_days=30, down_days=30)}
    result = calculate_supply_demand(hist)
    assert result["up_down_ratio"] > 1.0
    assert result["score"] >= 60


def test_supply_demand_insufficient_data():
    result = calculate_supply_demand({"historical": [{"date": "d", "close": 1, "volume": 1}]})
    assert result["score"] == 0


# ── calculate_institutional_sponsorship (I, simplified proxy) ────────────

def test_institutional_sponsorship_superinvestor_present_scores_higher():
    with_super = calculate_institutional_sponsorship(num_holders=6, superinvestors_found=["BERKSHIRE HATHAWAY INC"])
    without_super = calculate_institutional_sponsorship(num_holders=6, superinvestors_found=[])
    assert with_super["score"] > without_super["score"]
    assert with_super["ownership_pct"] is None  # honest proxy, never fabricated


def test_institutional_sponsorship_zero_holders_scores_zero():
    result = calculate_institutional_sponsorship(num_holders=0, superinvestors_found=[])
    assert result["score"] == 0


# ── calculate_market_direction (M) ─────────────────────────────────────────

def test_market_direction_strong_uptrend_low_vix():
    sp500_quote = {"price": 510.0}
    sp500_prices = [{"close": 500.0 - i * 0.05} for i in range(60)]
    vix_quote = {"price": 12.0}
    result = calculate_market_direction(sp500_quote, sp500_prices, vix_quote)
    assert result["trend"] == "strong_uptrend"
    assert result["score"] == 100


def test_market_direction_high_vix_overrides_to_zero():
    sp500_quote = {"price": 510.0}
    sp500_prices = [{"close": 500.0 - i * 0.05} for i in range(60)]
    vix_quote = {"price": 35.0}
    result = calculate_market_direction(sp500_quote, sp500_prices, vix_quote)
    assert result["score"] == 0


def test_market_direction_insufficient_history_is_neutral():
    result = calculate_market_direction({"price": 500.0}, sp500_prices=None)
    assert result["score"] == 50
    assert result["trend"] == "unknown"


# ── calculate_composite_score_phase3 / check_minimum_thresholds_phase3 ───

def test_composite_score_weighted_correctly():
    result = calculate_composite_score_phase3(c_score=100, a_score=100, n_score=100, s_score=100, l_score=100, i_score=100, m_score=100)
    assert result["composite_score"] == 100.0
    assert result["rating"] == "Exceptional+"


def test_composite_score_identifies_weakest():
    result = calculate_composite_score_phase3(c_score=90, a_score=90, n_score=90, s_score=90, l_score=10, i_score=90, m_score=90)
    assert result["weakest_component"] == "L"


def test_threshold_check_bear_market_overrides_everything():
    result = check_minimum_thresholds_phase3(c_score=100, a_score=100, n_score=100, s_score=100, l_score=100, i_score=100, m_score=0)
    assert result["recommendation"] == "avoid"
    assert result["failed_components"] == ["M"]


def test_threshold_check_all_pass_recommends_buy():
    result = check_minimum_thresholds_phase3(c_score=70, a_score=60, n_score=50, s_score=50, l_score=60, i_score=50, m_score=50)
    assert result["passes_all"] is True
    assert result["recommendation"] == "buy"


def test_threshold_check_weak_leadership_forces_avoid():
    result = check_minimum_thresholds_phase3(c_score=70, a_score=60, n_score=50, s_score=50, l_score=30, i_score=50, m_score=50)
    assert result["recommendation"] == "avoid"
    assert "L" in result["failed_components"]
