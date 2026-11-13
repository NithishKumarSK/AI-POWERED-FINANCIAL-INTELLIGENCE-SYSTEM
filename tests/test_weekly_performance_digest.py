"""
Tests for core/weekly_performance_digest.py -- pure calculation over
synthetic validated-prediction records shaped like
db.stock_prediction_repository._row_to_jsonl_record's output.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from weekly_performance_digest import build_weekly_digest, classify_outcome, select_records_in_window


def _record(symbol, decision, actual_total_pl, decision_match, directional_match,
            target_date="2026-06-15", horizon_days=30):
    return {
        "timestamp": "2026-06-15T10:00:00Z",
        "stock_prediction_input": {"symbol": symbol, "decision_horizon_days": horizon_days},
        "ai_prediction": {"decision": decision},
        "actual_validation": {
            "actual_total_pl": actual_total_pl,
            "effective_target_date": target_date,
        },
        "comparison": {"decision_match": decision_match, "directional_match": directional_match},
    }


def test_classify_outcome_win_loss_breakeven():
    assert classify_outcome(_record("AAPL", "BUY", 50.0, True, True)) == "win"
    assert classify_outcome(_record("AAPL", "BUY", -30.0, False, False)) == "loss"
    assert classify_outcome(_record("AAPL", "HOLD", 0.0, True, True)) == "breakeven"
    assert classify_outcome(_record("AAPL", "HOLD", None, None, None)) == "breakeven"


def test_select_records_in_window_filters_by_effective_target_date():
    records = [
        _record("AAPL", "BUY", 10.0, True, True, target_date="2026-06-13"),
        _record("MSFT", "SELL", -5.0, True, False, target_date="2026-06-20"),
        _record("TSLA", "HOLD", 0.0, True, True, target_date="2026-07-01"),
    ]
    windowed = select_records_in_window(records, "2026-06-13", "2026-06-20")
    assert len(windowed) == 2
    symbols = {r["stock_prediction_input"]["symbol"] for r in windowed}
    assert symbols == {"AAPL", "MSFT"}


def test_select_records_in_window_invalid_dates_returns_empty():
    assert select_records_in_window([_record("AAPL", "BUY", 10.0, True, True)], "not-a-date", "2026-06-20") == []


def test_build_weekly_digest_empty_week_is_valid_and_zeroed():
    digest = build_weekly_digest([], "2026-06-13", "2026-06-20")
    assert digest["summary"]["total_trades"] == 0
    assert digest["summary"]["win_rate"] == 0.0
    assert digest["summary"]["profit_factor"] == 0.0
    assert digest["lessons"]["top_winners"] == []


def test_build_weekly_digest_summary_metrics():
    records = [
        _record("AAPL", "BUY", 100.0, True, True),
        _record("MSFT", "SELL", -50.0, False, False),
    ]
    digest = build_weekly_digest(records, "2026-06-13", "2026-06-20")
    s = digest["summary"]
    assert s["total_trades"] == 2
    assert s["winners"] == 1
    assert s["losers"] == 1
    assert s["win_rate"] == 0.5
    assert s["profit_factor"] == 2.0
    assert s["total_realized_pnl"] == 50.0
    assert s["expectancy"] == 25.0


def test_build_weekly_digest_profit_factor_no_losses_is_infinite():
    records = [_record("AAPL", "BUY", 100.0, True, True)]
    digest = build_weekly_digest(records, "2026-06-13", "2026-06-20")
    assert digest["summary"]["profit_factor"] == float("inf")


def test_build_weekly_digest_pattern_analysis_by_decision():
    records = [
        _record("AAPL", "BUY", 100.0, True, True),
        _record("MSFT", "BUY", -50.0, False, False),
        _record("TSLA", "SELL", 20.0, True, True),
    ]
    digest = build_weekly_digest(records, "2026-06-13", "2026-06-20")
    by_decision = digest["pattern_analysis"]["by_decision"]
    assert by_decision["BUY"]["total"] == 2
    assert by_decision["BUY"]["wins"] == 1
    assert by_decision["SELL"]["wins"] == 1


def test_build_weekly_digest_top_winners_and_losers():
    records = [
        _record("AAPL", "BUY", 100.0, True, True),
        _record("MSFT", "SELL", -50.0, False, False),
        _record("TSLA", "BUY", 200.0, True, True),
    ]
    digest = build_weekly_digest(records, "2026-06-13", "2026-06-20", top_n=2)
    top_winners = digest["lessons"]["top_winners"]
    assert top_winners[0]["symbol"] == "TSLA"
    assert top_winners[1]["symbol"] == "AAPL"
    top_losers = digest["lessons"]["top_losers"]
    assert top_losers[0]["symbol"] == "MSFT"


def test_build_weekly_digest_process_improvement_flagged_for_low_win_rate_decision():
    records = [
        _record("AAPL", "BUY", -10.0, False, False),
        _record("MSFT", "BUY", -5.0, False, False),
        _record("TSLA", "BUY", -1.0, False, False),
        _record("NVDA", "BUY", 100.0, True, True),
    ]
    digest = build_weekly_digest(records, "2026-06-13", "2026-06-20")
    improvements = digest["lessons"]["process_improvements"]
    assert any("BUY" in msg for msg in improvements)
