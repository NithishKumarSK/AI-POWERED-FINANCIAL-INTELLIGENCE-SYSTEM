"""Tests for core/accuracy_decay_tracker.py, focused on the trading-cost-
adjusted reporting addition: a round-trip cost should lower (never raise)
mean strategy return and Sharpe for any month with at least one BUY/SELL."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _rec(symbol, origin_month_day, decision, actual_decision, actual_return_pct,
         decision_match=None, directional_match=None):
    return {
        "stock_prediction_input": {"symbol": symbol, "prediction_origin_date": origin_month_day},
        "ai_prediction": {"decision": decision},
        "actual_validation": {"actual_decision": actual_decision, "actual_return_pct": actual_return_pct},
        "comparison": {
            "decision_match": decision_match if decision_match is not None else (decision == actual_decision),
            "directional_match": directional_match if directional_match is not None else (decision == actual_decision),
        },
    }


def test_strategy_return_buy_matches_actual():
    from accuracy_decay_tracker import _strategy_return
    assert _strategy_return("BUY", 5.0) == 5.0


def test_strategy_return_sell_inverts_actual():
    from accuracy_decay_tracker import _strategy_return
    assert _strategy_return("SELL", 5.0) == -5.0


def test_strategy_return_hold_is_zero():
    from accuracy_decay_tracker import _strategy_return
    assert _strategy_return("HOLD", 5.0) == 0.0


def test_strategy_return_none_decision_returns_none():
    from accuracy_decay_tracker import _strategy_return
    assert _strategy_return("REVIEW", 5.0) is None
    assert _strategy_return("BUY", None) is None


def test_strategy_return_cost_adjustment_lowers_buy_return():
    from accuracy_decay_tracker import _strategy_return, ROUND_TRIP_COST_PCT
    raw = _strategy_return("BUY", 5.0, apply_cost=False)
    cost_adj = _strategy_return("BUY", 5.0, apply_cost=True)
    assert cost_adj == raw - ROUND_TRIP_COST_PCT


def test_strategy_return_cost_adjustment_lowers_sell_return_too():
    """SELL's cost must subtract, not add -- a -20bp cost on an already
    negated return is still a cost, not a bonus."""
    from accuracy_decay_tracker import _strategy_return, ROUND_TRIP_COST_PCT
    raw = _strategy_return("SELL", -5.0, apply_cost=False)   # = +5.0
    cost_adj = _strategy_return("SELL", -5.0, apply_cost=True)
    assert cost_adj == raw - ROUND_TRIP_COST_PCT


def test_strategy_return_cost_adjustment_does_not_apply_to_hold():
    from accuracy_decay_tracker import _strategy_return
    assert _strategy_return("HOLD", 5.0, apply_cost=True) == 0.0


def test_build_decay_report_includes_cost_adjusted_fields():
    from accuracy_decay_tracker import build_decay_report
    records = [
        _rec("TSLA", "2026-01-15", "BUY", "BUY", 5.0),
        _rec("TSLA", "2026-01-20", "BUY", "SELL", -3.0),
        _rec("TSLA", "2026-01-25", "SELL", "SELL", -2.0),
    ]
    report = build_decay_report(records)
    month = report["monthly"][0]
    assert "mean_strategy_return_pct_after_costs" in month
    assert "strategy_sharpe_after_costs_nonannualized" in month
    # Cost-adjusted mean must be lower than raw mean when any BUY/SELL exists.
    assert month["mean_strategy_return_pct_after_costs"] < month["mean_strategy_return_pct"]


def test_build_decay_report_skips_records_without_origin_date():
    from accuracy_decay_tracker import build_decay_report
    records = [{"stock_prediction_input": {}, "ai_prediction": {}, "actual_validation": {}, "comparison": {}}]
    report = build_decay_report(records)
    assert report["skipped_no_origin_date"] == 1
    assert report["monthly"] == []
