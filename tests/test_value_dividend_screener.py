"""
Tests for core/value_dividend_screener.py -- ported dividend stability +
revenue/EPS trend + sustainability composite (scope-reduced, see that
module's docstring). Synthetic data only, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from value_dividend_screener import (
    analyze_dividend_stability,
    analyze_earnings_trend,
    analyze_revenue_trend,
    calculate_composite_score,
    calculate_profit_margin_score,
    calculate_stability_score,
)


# ── analyze_dividend_stability ──────────────────────────────────────────────

def test_stability_low_volatility_consistent_growth():
    series = [  # newest first
        {"date": "2026", "dividend_per_share": 2.04},
        {"date": "2025", "dividend_per_share": 1.93},
        {"date": "2024", "dividend_per_share": 1.83},
        {"date": "2023", "dividend_per_share": 1.75},
    ]
    result = analyze_dividend_stability(series)
    assert result["is_stable"] is True
    assert result["years_of_growth"] >= 2
    assert result["is_growing"] is True


def test_stability_detects_a_cut_resets_growth_streak():
    series = [
        {"date": "2026", "dividend_per_share": 1.00},  # cut
        {"date": "2025", "dividend_per_share": 2.00},
        {"date": "2024", "dividend_per_share": 1.90},
        {"date": "2023", "dividend_per_share": 1.80},
    ]
    result = analyze_dividend_stability(series)
    assert result["years_of_growth"] == 0  # reset by the cut (most recent step)


def test_stability_insufficient_data():
    result = analyze_dividend_stability([{"date": "2026", "dividend_per_share": 2.0}])
    assert result["is_stable"] is False
    assert result["volatility_pct"] is None


# ── calculate_stability_score ───────────────────────────────────────────────

def test_stability_score_full_marks():
    stability = {"is_stable": True, "is_growing": True, "years_of_growth": 5, "volatility_pct": 5.0}
    assert calculate_stability_score(stability) == 100.0  # 40 + 30 + min(50,30)


def test_stability_score_zero_for_empty():
    assert calculate_stability_score({}) == 0.0


# ── analyze_revenue_trend / analyze_earnings_trend ────────────────────────

def test_revenue_trend_uptrend_detected():
    series = [  # newest first, 4 years
        {"date": "2026", "revenue": 130}, {"date": "2025", "revenue": 120},
        {"date": "2024", "revenue": 110}, {"date": "2023", "revenue": 100},
    ]
    result = analyze_revenue_trend(series)
    assert result["is_uptrend"] is True
    assert result["cagr"] is not None and result["cagr"] > 0


def test_revenue_trend_declining_is_not_uptrend():
    series = [
        {"date": "2026", "revenue": 90}, {"date": "2025", "revenue": 95},
        {"date": "2024", "revenue": 100}, {"date": "2023", "revenue": 105},
    ]
    result = analyze_revenue_trend(series)
    assert result["is_uptrend"] is False


def test_earnings_trend_uses_net_income_when_provided():
    series = [{"date": "2026", "eps": 1.0}, {"date": "2025", "eps": 1.0}, {"date": "2024", "eps": 1.0}]
    net_income_newest_first = [130, 120, 110]
    result = analyze_earnings_trend(series, annual_net_income_series=net_income_newest_first)
    assert result["is_uptrend"] is True


def test_trend_insufficient_data():
    result = analyze_revenue_trend([{"date": "2026", "revenue": 100}])
    assert result["is_uptrend"] is False
    assert result["cagr"] is None


# ── calculate_profit_margin_score ──────────────────────────────────────────

def test_profit_margin_score_scales_to_100():
    assert calculate_profit_margin_score(15.0) == 100.0
    assert calculate_profit_margin_score(7.5) == 50.0
    assert calculate_profit_margin_score(None) == 0.0


# ── calculate_composite_score ───────────────────────────────────────────────

def test_composite_score_all_strong_inputs_near_100():
    score = calculate_composite_score(div_cagr=20.0, stability_score=100.0, revenue_cagr=15.0, eps_cagr=20.0, sustainable=True, profit_margin_score=100.0)
    assert score == 100.0


def test_composite_score_all_weak_inputs_is_low():
    score = calculate_composite_score(div_cagr=0.0, stability_score=0.0, revenue_cagr=0.0, eps_cagr=0.0, sustainable=False, profit_margin_score=0.0)
    assert score == 0.0


def test_composite_score_missing_inputs_degrade_gracefully():
    score = calculate_composite_score(div_cagr=None, stability_score=50.0, revenue_cagr=None, eps_cagr=None, sustainable=False, profit_margin_score=50.0)
    assert 0 < score < 100
