"""
backtest_quality_scorer.py -- 5-dimension backtest quality scoring (sample
size, expectancy, risk management, robustness, execution realism), ported
from claude-trading-skills' backtest-expert skill
(vendor/claude-trading-skills/skills/backtest-expert/scripts/evaluate_backtest.py,
MIT License, Copyright (c) 2026 TraderMonty).

The skill's own framing: "find strategies that break the least, not that
profit the most." Metrics are user/caller-supplied -- this scores a
backtest result, it doesn't run one. Directly complementary to this
project's own evidence-gating discipline (segment_reliability.py's
PROVEN_THRESHOLD_PCT/MIN_SAMPLE_SIZE, ml_training_runner.py's
MIN_HOLDOUT_TEST_SAMPLES) -- same spirit, applied to a different artifact
(a strategy backtest result rather than a prediction segment).

Expectancy and profit factor are computed in exact Decimal arithmetic from
the inputs, not float, because float cancellation error can flip a
break-even strategy's sign (e.g. expectancy 2.2e-16 for 40/3/2 inputs) --
ported verbatim for this reason, not simplified to float math.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Tuple


def _exact(value: float) -> Decimal:
    return Decimal(repr(float(value)))


def _exact_components(win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> Tuple[Decimal, Decimal]:
    wr = _exact(win_rate)
    with localcontext() as ctx:
        ctx.prec = 100
        return wr * _exact(avg_win_pct), (Decimal(100) - wr) * _exact(avg_loss_pct)


def expectancy_sign(win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> int:
    profit, loss = _exact_components(win_rate, avg_win_pct, avg_loss_pct)
    return (profit > loss) - (profit < loss)


def calc_profit_factor(win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> float:
    profit, loss = _exact_components(win_rate, avg_win_pct, avg_loss_pct)
    if loss == 0:
        return float("inf") if profit > 0 else 0.0
    with localcontext() as ctx:
        ctx.prec = 100
        return float(profit / loss)


def calc_expectancy(win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> float:
    profit, loss = _exact_components(win_rate, avg_win_pct, avg_loss_pct)
    with localcontext() as ctx:
        ctx.prec = 100
        return float((profit - loss) / 100)


def score_sample_size(total_trades: int) -> int:
    """<30 -> 0; 30 -> 8; 100 -> 15; 200+ -> 20."""
    if total_trades < 30:
        return 0
    if total_trades < 100:
        return 8 + int((total_trades - 30) / 70 * 7)
    if total_trades < 200:
        return 15 + int((total_trades - 100) / 100 * 5)
    return 20


def score_expectancy(win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> int:
    """<=0 -> 0; 0..0.5 -> 5..10; 0.5..1.5 -> 10..18; >=1.5 -> 20."""
    if expectancy_sign(win_rate, avg_win_pct, avg_loss_pct) <= 0:
        return 0
    exp = calc_expectancy(win_rate, avg_win_pct, avg_loss_pct)
    if exp < 0.5:
        return 5 + int(exp / 0.5 * 5)
    if exp < 1.5:
        return 10 + int((exp - 0.5) / 1.0 * 8)
    return 20


def score_risk_management(max_drawdown_pct: float, win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> int:
    """Drawdown component (0-12) + profit-factor component (0-8), capped at
    20. 50%+ drawdown overrides the whole dimension to 0 (catastrophic)."""
    if max_drawdown_pct >= 50:
        return 0
    dd_score = 12 if max_drawdown_pct < 20 else int(12 * (50 - max_drawdown_pct) / 30)

    pf = calc_profit_factor(win_rate, avg_win_pct, avg_loss_pct)
    if expectancy_sign(win_rate, avg_win_pct, avg_loss_pct) <= 0:
        pf_score = 0
    elif pf >= 3.0:
        pf_score = 8
    else:
        pf_score = int((pf - 1.0) / 2.0 * 8)

    return min(20, dd_score + pf_score)


def score_robustness(years_tested: int, num_parameters: int) -> int:
    """Years component (0-15) + parameter-count component (0-5, penalizing
    over-fitting-prone high parameter counts), capped at 20."""
    if years_tested < 5:
        years_score = 0
    elif years_tested >= 10:
        years_score = 15
    else:
        years_score = 5 + int((years_tested - 5) / 5 * 10)

    if num_parameters <= 4:
        param_score = 5
    elif num_parameters <= 6:
        param_score = 3
    elif num_parameters == 7:
        param_score = 1
    else:
        param_score = 0

    return min(20, years_score + param_score)


def score_execution_realism(slippage_tested: bool) -> int:
    return 20 if slippage_tested else 0


def get_verdict(total_score: int) -> str:
    if total_score >= 70:
        return "Deploy"
    if total_score >= 40:
        return "Refine"
    return "Abandon"


def detect_red_flags(
    total_trades: int, win_rate: float, avg_win_pct: float, avg_loss_pct: float,
    max_drawdown_pct: float, years_tested: int, num_parameters: int, slippage_tested: bool,
) -> list:
    flags = []
    if total_trades < 30:
        flags.append({"id": "small_sample", "severity": "high",
                       "message": f"Only {total_trades} trades -- minimum 30 required for statistical confidence."})
    if not slippage_tested:
        flags.append({"id": "no_slippage_test", "severity": "high",
                       "message": "Slippage/friction not tested -- results may not survive real-world execution."})
    if max_drawdown_pct >= 50:
        flags.append({"id": "excessive_drawdown", "severity": "high",
                       "message": f"Max drawdown {max_drawdown_pct}% meets or exceeds the 50% hard ceiling -- catastrophic risk."})
    if num_parameters >= 7:
        flags.append({"id": "over_optimized", "severity": "medium",
                       "message": f"{num_parameters} parameters suggests over-optimization / curve-fitting risk."})
    if years_tested < 5:
        flags.append({"id": "short_test_period", "severity": "medium",
                       "message": f"Only {years_tested} years tested -- may miss regime changes (minimum 5 recommended)."})
    exp = calc_expectancy(win_rate, avg_win_pct, avg_loss_pct)
    if expectancy_sign(win_rate, avg_win_pct, avg_loss_pct) < 0:
        flags.append({"id": "negative_expectancy", "severity": "high",
                       "message": f"Negative expectancy ({exp:.3f}%) -- strategy loses money on average."})
    if win_rate > 90 and max_drawdown_pct < 5:
        flags.append({"id": "too_good", "severity": "medium",
                       "message": "Results look too good -- audit for look-ahead bias or data issues."})
    return flags


def evaluate(
    total_trades: int, win_rate: float, avg_win_pct: float, avg_loss_pct: float,
    max_drawdown_pct: float, years_tested: int, num_parameters: int, slippage_tested: bool,
) -> dict:
    """Full evaluation: 5 dimension scores (0-20 each), total (0-100),
    verdict (Deploy/Refine/Abandon), and red flags.

    Returns {"scores": {...}, "total_score": int, "verdict": str,
             "red_flags": [...], "expectancy_pct": float, "profit_factor": float}."""
    scores = {
        "sample_size": score_sample_size(total_trades),
        "expectancy": score_expectancy(win_rate, avg_win_pct, avg_loss_pct),
        "risk_management": score_risk_management(max_drawdown_pct, win_rate, avg_win_pct, avg_loss_pct),
        "robustness": score_robustness(years_tested, num_parameters),
        "execution_realism": score_execution_realism(slippage_tested),
    }
    total = sum(scores.values())
    return {
        "scores": scores,
        "total_score": total,
        "verdict": get_verdict(total),
        "red_flags": detect_red_flags(total_trades, win_rate, avg_win_pct, avg_loss_pct,
                                       max_drawdown_pct, years_tested, num_parameters, slippage_tested),
        "expectancy_pct": round(calc_expectancy(win_rate, avg_win_pct, avg_loss_pct), 4),
        "profit_factor": calc_profit_factor(win_rate, avg_win_pct, avg_loss_pct),
    }
