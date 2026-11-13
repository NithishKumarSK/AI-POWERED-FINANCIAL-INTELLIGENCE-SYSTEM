"""Tests for core/portfolio_tools/backtest_quality_scorer.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from portfolio_tools.backtest_quality_scorer import (
    expectancy_sign, calc_expectancy, calc_profit_factor,
    score_sample_size, score_expectancy, score_risk_management, score_robustness,
    score_execution_realism, get_verdict, detect_red_flags, evaluate,
)


# ── exact-decimal edge case (the reason this module exists) ──────────────

def test_breakeven_expectancy_sign_is_exactly_zero_not_float_noise():
    """win_rate=40, avg_win=3, avg_loss=2 -> 40*3 == 60*2 == 120, exactly
    break-even. Naive float math gives expectancy ~2.2e-16 (not exactly 0),
    which would wrongly score as positive -- this must come back 0."""
    assert expectancy_sign(40, 3, 2) == 0
    assert calc_expectancy(40, 3, 2) == 0.0


def test_positive_expectancy_sign():
    assert expectancy_sign(60, 2, 1) == 1


def test_negative_expectancy_sign():
    assert expectancy_sign(30, 1, 2) == -1


def test_profit_factor_zero_losses_is_infinite():
    assert calc_profit_factor(100, 5, 0) == float("inf")


def test_profit_factor_no_wins_and_no_losses_is_zero():
    assert calc_profit_factor(0, 5, 0) == 0.0


# ── score_sample_size ─────────────────────────────────────────────────────

def test_sample_size_below_30_scores_zero():
    assert score_sample_size(10) == 0


def test_sample_size_200_plus_scores_max():
    assert score_sample_size(200) == 20
    assert score_sample_size(500) == 20


def test_sample_size_increases_monotonically():
    assert score_sample_size(30) < score_sample_size(100) < score_sample_size(200)


# ── score_expectancy ──────────────────────────────────────────────────────

def test_expectancy_breakeven_or_negative_scores_zero():
    assert score_expectancy(40, 3, 2) == 0
    assert score_expectancy(30, 1, 2) == 0


def test_expectancy_strong_positive_scores_max():
    assert score_expectancy(70, 5, 1) == 20


# ── score_risk_management ──────────────────────────────────────────────────

def test_catastrophic_drawdown_overrides_to_zero():
    assert score_risk_management(max_drawdown_pct=55, win_rate=70, avg_win_pct=5, avg_loss_pct=1) == 0


def test_low_drawdown_good_profit_factor_scores_well():
    score = score_risk_management(max_drawdown_pct=10, win_rate=70, avg_win_pct=5, avg_loss_pct=1)
    assert score > 15


# ── score_robustness ──────────────────────────────────────────────────────

def test_short_test_period_scores_zero_years_component():
    assert score_robustness(years_tested=2, num_parameters=3) == 5  # 0 years + 5 params


def test_long_test_period_few_params_scores_well():
    assert score_robustness(years_tested=10, num_parameters=2) == 20


def test_many_parameters_penalized():
    assert score_robustness(years_tested=10, num_parameters=8) < score_robustness(years_tested=10, num_parameters=2)


# ── score_execution_realism ────────────────────────────────────────────────

def test_execution_realism_binary():
    assert score_execution_realism(True) == 20
    assert score_execution_realism(False) == 0


# ── get_verdict ───────────────────────────────────────────────────────────

def test_verdict_thresholds():
    assert get_verdict(70) == "Deploy"
    assert get_verdict(69) == "Refine"
    assert get_verdict(40) == "Refine"
    assert get_verdict(39) == "Abandon"


# ── detect_red_flags ────────────────────────────────────────────────────────

def test_red_flags_small_sample():
    flags = detect_red_flags(10, 60, 5, 1, 10, 10, 2, True)
    assert any(f["id"] == "small_sample" for f in flags)


def test_red_flags_too_good_to_be_true():
    flags = detect_red_flags(100, 95, 5, 1, 2, 10, 2, True)
    assert any(f["id"] == "too_good" for f in flags)


def test_red_flags_negative_expectancy():
    flags = detect_red_flags(100, 30, 1, 2, 10, 10, 2, True)
    assert any(f["id"] == "negative_expectancy" for f in flags)


def test_no_red_flags_for_clean_result():
    flags = detect_red_flags(200, 60, 3, 1, 10, 10, 3, True)
    assert flags == []


# ── evaluate (full pipeline) ──────────────────────────────────────────────

def test_evaluate_this_projects_own_real_ev_numbers_flags_honestly():
    """This project's own real shadow-EV probe (38.5% win rate, cited in
    position_sizing.py's docstring) with only 13 trades and no slippage
    test -- should score honestly (Refine, not Deploy) and surface real
    red flags, not be rubber-stamped just because expectancy is positive."""
    result = evaluate(total_trades=13, win_rate=38.5, avg_win_pct=2904.74, avg_loss_pct=319.02,
                       max_drawdown_pct=10, years_tested=2, num_parameters=3, slippage_tested=False)
    assert result["verdict"] != "Deploy"
    assert any(f["id"] == "small_sample" for f in result["red_flags"])
    assert any(f["id"] == "no_slippage_test" for f in result["red_flags"])


def test_evaluate_total_score_is_sum_of_dimensions():
    result = evaluate(total_trades=200, win_rate=60, avg_win_pct=3, avg_loss_pct=1,
                       max_drawdown_pct=10, years_tested=10, num_parameters=2, slippage_tested=True)
    assert result["total_score"] == sum(result["scores"].values())
