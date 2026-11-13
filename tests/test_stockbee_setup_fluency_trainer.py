"""
Tests for core/stockbee_setup_fluency_trainer.py -- ported model-book
ingest/outcome-maturation/summarization logic. Synthetic data only, no
network. Bars are CHRONOLOGICAL (oldest first).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from stockbee_momentum_burst_screener import Bar
from stockbee_setup_fluency_trainer import (
    calculate_window_outcome,
    classify_outcome,
    derive_overall_outcome,
    derive_setup_tags,
    is_downgrade_candidate,
    is_promote_candidate,
    is_studyable_candidate,
    make_record,
    summarize_group,
    summarize_model_book,
    update_record_outcomes,
    upsert_records,
)


def _candidate(symbol="AAPL", date="2026-06-01", **overrides):
    base = {
        "symbol": symbol, "date": date, "primary_trigger": "4pct_breakout", "trigger_tags": ["4pct_breakout"],
        "soft_failure_tags": [], "reject_reasons": [], "rating": "A-", "setup_score": 85, "state": "ACTIONABLE_DAY1",
        "entry_reference": 100.0, "stop_reference": 95.0, "risk_pct_to_stop": 5.0, "day_gain_pct": 5.0,
        "volume_ratio_1d": 2.0, "close_location_pct": 90.0, "prior_base_days": 10, "base_width_pct": 7.0,
    }
    base.update(overrides)
    return base


def _bar(date_str, close, high=None, low=None):
    return Bar(date=date_str, open=close, high=high if high is not None else close * 1.01, low=low if low is not None else close * 0.99, close=close, volume=1_000_000)


# ── is_studyable_candidate / make_record ──────────────────────────────────

def test_is_studyable_candidate_requires_symbol_and_date():
    assert is_studyable_candidate(_candidate())[0] is True
    assert is_studyable_candidate({"symbol": "AAPL"})[0] is False
    assert is_studyable_candidate({"date": "2026-06-01"})[0] is False


def test_make_record_builds_stable_record_id():
    record = make_record(_candidate())
    assert record["record_id"] == "stockbee_mb:AAPL:2026-06-01:4pct_breakout"
    assert record["overall_outcome"] == "PENDING"
    assert record["matured"] is False


def test_make_record_missing_fields_raises():
    import pytest
    with pytest.raises(ValueError):
        make_record({"symbol": "", "date": "2026-06-01"})


# ── derive_setup_tags ──────────────────────────────────────────────────────

def test_derive_setup_tags_includes_rating_and_quality_tags():
    tags = derive_setup_tags(_candidate(rating="A-", close_location_pct=90, volume_ratio_1d=4, base_width_pct=5, prior_base_days=10, risk_pct_to_stop=2))
    assert "rating_Aminus" in tags
    assert "close_near_high" in tags
    assert "high_volume_expansion" in tags
    assert "tight_base" in tags
    assert "controlled_3_to_20_day_base" in tags
    assert "compact_risk" in tags


# ── upsert_records ─────────────────────────────────────────────────────────

def test_upsert_records_preserves_human_annotations_on_update():
    existing = [{"record_id": "r1", "human_label": "great_setup", "value": 1}]
    new = [{"record_id": "r1", "value": 2}]
    merged, stats = upsert_records(existing, new)
    assert merged[0]["value"] == 2
    assert merged[0]["human_label"] == "great_setup"
    assert stats == {"inserted": 0, "updated": 1, "total": 1}


def test_upsert_records_preserves_matured_outcomes_against_fresh_ingest():
    existing = [{"record_id": "r1", "outcomes": {"5d": {"matured": True}}, "matured": True, "overall_outcome": "WORKED"}]
    new = [{"record_id": "r1", "setup_score": 90}]  # fresh re-ingest, no outcomes yet
    merged, _ = upsert_records(existing, new)
    assert merged[0]["matured"] is True
    assert merged[0]["overall_outcome"] == "WORKED"
    assert merged[0]["setup_score"] == 90


# ── classify_outcome / calculate_window_outcome ───────────────────────────

def test_classify_outcome_stop_hit_overrides_everything():
    assert classify_outcome(fwd_return_pct=20, mfe_pct=20, mae_pct=-1, stop_hit=True) == "FAILED_STOP"


def test_classify_outcome_bands():
    assert classify_outcome(15, 15, 0, False) == "STRONG_WINNER"
    assert classify_outcome(5, 5, 0, False) == "WORKED"
    assert classify_outcome(-3, 0, 0, False) == "FAILED_FADE"
    assert classify_outcome(1, 0, -6, False) == "CHOPPY_FAILURE"
    assert classify_outcome(0, 0, 0, False) == "NEUTRAL"


def test_calculate_window_outcome_matures_with_enough_future_bars():
    record = {"entry_reference": 100.0, "stop_reference": 95.0, "setup_date": "2026-06-01"}
    bars = [_bar("2026-06-01", 100), _bar("2026-06-02", 102), _bar("2026-06-03", 105), _bar("2026-06-04", 108)]
    outcome = calculate_window_outcome(record, bars, horizon=3)
    assert outcome["matured"] is True
    assert outcome["forward_return_pct"] == 8.0
    assert outcome["outcome_tag"] == "STRONG_WINNER"


def test_calculate_window_outcome_not_enough_future_bars():
    record = {"entry_reference": 100.0, "stop_reference": 95.0, "setup_date": "2026-06-01"}
    bars = [_bar("2026-06-01", 100), _bar("2026-06-02", 102)]
    outcome = calculate_window_outcome(record, bars, horizon=5)
    assert outcome["matured"] is False
    assert outcome["reason"] == "not_enough_future_bars"


def test_calculate_window_outcome_detects_stop_hit():
    record = {"entry_reference": 100.0, "stop_reference": 95.0, "setup_date": "2026-06-01"}
    bars = [_bar("2026-06-01", 100), _bar("2026-06-02", 90, low=90), _bar("2026-06-03", 92), _bar("2026-06-04", 93)]
    outcome = calculate_window_outcome(record, bars, horizon=3)
    assert outcome["stop_hit"] is True
    assert outcome["outcome_tag"] == "FAILED_STOP"


def test_derive_overall_outcome_pending_when_primary_horizon_not_matured():
    assert derive_overall_outcome({"3d": {"matured": True, "outcome_tag": "WORKED"}}, primary_horizon=5) == "PENDING"
    assert derive_overall_outcome({"5d": {"matured": True, "outcome_tag": "WORKED"}}, primary_horizon=5) == "WORKED"


# ── update_record_outcomes / summarize_group / summarize_model_book ───────

def test_update_record_outcomes_matures_records_with_sufficient_prices():
    record = make_record(_candidate())
    bars = [_bar("2026-06-01", 100), _bar("2026-06-02", 103), _bar("2026-06-03", 106), _bar("2026-06-04", 109), _bar("2026-06-05", 111), _bar("2026-06-06", 112)]
    records, stats = update_record_outcomes([record], {"AAPL": bars})
    assert stats["matured"] == 1
    assert records[0]["matured"] is True


def test_summarize_group_computes_win_rate():
    records = [
        {"matured": True, "overall_outcome": "WORKED", "outcomes": {"5d": {"forward_return_pct": 5.0, "mfe_pct": 6.0, "mae_pct": -1.0, "stop_hit": False}, "3d": {"forward_return_pct": 3.0}}},
        {"matured": True, "overall_outcome": "FAILED_FADE", "outcomes": {"5d": {"forward_return_pct": -3.0, "mfe_pct": 0.0, "mae_pct": -4.0, "stop_hit": False}, "3d": {"forward_return_pct": -2.0}}},
    ]
    stats = summarize_group(records)
    assert stats["sample_size"] == 2
    assert stats["win_rate_pct"] == 50.0
    assert stats["failure_rate_pct"] == 50.0


def test_is_promote_and_downgrade_candidate_thresholds():
    strong_row = {"sample_size": 10, "win_rate_pct": 70, "avg_5d_return_pct": 4, "avg_5d_mae_pct": -2}
    assert is_promote_candidate(strong_row) is True
    weak_row = {"sample_size": 10, "failure_rate_pct": 60, "avg_5d_return_pct": -2}
    assert is_downgrade_candidate(weak_row) is True


def test_summarize_model_book_produces_rule_candidates():
    records = []
    for i in range(6):
        c = _candidate(symbol=f"SYM{i}", date="2026-06-01")
        r = make_record(c)
        r["matured"] = True
        r["overall_outcome"] = "WORKED"
        r["outcomes"] = {"5d": {"forward_return_pct": 5.0, "mfe_pct": 6.0, "mae_pct": -1.0, "stop_hit": False}, "3d": {"forward_return_pct": 3.0}}
        records.append(r)
    summary = summarize_model_book(records, group_by_fields=["rating"], min_sample=3)
    assert summary["matured_records"] == 6
    assert any(rc["action"] == "promote" for rc in summary["rule_candidates"])
