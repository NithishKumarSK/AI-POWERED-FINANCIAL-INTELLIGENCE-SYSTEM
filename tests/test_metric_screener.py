"""Tests for core/portfolio_tools/metric_screener.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from portfolio_tools.metric_screener import check_rule, screen, rank


# ── check_rule / operators ────────────────────────────────────────────────

def test_gt_and_gte_operators():
    assert check_rule({"x": 10}, {"metric": "x", "op": ">", "value": 5})["passed"] is True
    assert check_rule({"x": 5}, {"metric": "x", "op": ">", "value": 5})["passed"] is False
    assert check_rule({"x": 5}, {"metric": "x", "op": ">=", "value": 5})["passed"] is True


def test_between_operator():
    assert check_rule({"x": 15}, {"metric": "x", "op": "between", "value": (10, 20)})["passed"] is True
    assert check_rule({"x": 25}, {"metric": "x", "op": "between", "value": (10, 20)})["passed"] is False


def test_in_and_not_in_operators():
    assert check_rule({"sector": "Tech"}, {"metric": "sector", "op": "in", "value": ["Tech", "Health"]})["passed"] is True
    assert check_rule({"sector": "Energy"}, {"metric": "sector", "op": "not in", "value": ["Tech", "Health"]})["passed"] is True


def test_unknown_op_raises():
    import pytest
    with pytest.raises(ValueError):
        check_rule({"x": 1}, {"metric": "x", "op": "~=", "value": 1})


def test_missing_metric_fails_by_default():
    r = check_rule({}, {"metric": "x", "op": ">", "value": 5})
    assert r["passed"] is False


def test_missing_metric_skipped_when_configured():
    r = check_rule({}, {"metric": "x", "op": ">", "value": 5}, missing="skip")
    assert r["passed"] is True


# ── screen ────────────────────────────────────────────────────────────────

def test_screen_filters_rows():
    rows = [{"ticker": "A", "growth": 20}, {"ticker": "B", "growth": 5}]
    result = screen(rows, [{"metric": "growth", "op": ">=", "value": 10}])
    assert [r["ticker"] for r in result["passed"]] == ["A"]
    assert len(result["failed"]) == 1
    assert "growth" in result["failed"][0]["failures"][0]


def test_screen_all_pass_with_no_rules():
    rows = [{"ticker": "A"}, {"ticker": "B"}]
    result = screen(rows, [])
    assert len(result["passed"]) == 2


# ── rank ──────────────────────────────────────────────────────────────────

def test_rank_desc_favors_higher_values():
    rows = [{"ticker": "LOW", "growth": 5}, {"ticker": "HIGH", "growth": 20}]
    ranked = rank(rows, [{"metric": "growth", "order": "desc", "weight": 1}])
    assert ranked[0]["ticker"] == "HIGH"


def test_rank_asc_favors_lower_values():
    rows = [{"ticker": "LOW_PE", "pe": 10}, {"ticker": "HIGH_PE", "pe": 30}]
    ranked = rank(rows, [{"metric": "pe", "order": "asc", "weight": 1}])
    assert ranked[0]["ticker"] == "LOW_PE"


def test_rank_top_limits_result_count():
    rows = [{"ticker": f"T{i}", "x": i} for i in range(10)]
    ranked = rank(rows, [{"metric": "x", "order": "desc", "weight": 1}], top=3)
    assert len(ranked) == 3


def test_rank_missing_metric_scores_zero_contribution_not_excluded():
    rows = [{"ticker": "HAS", "x": 10}, {"ticker": "MISSING"}]
    ranked = rank(rows, [{"metric": "x", "order": "desc", "weight": 1}])
    assert len(ranked) == 2  # MISSING still appears, just ranked lower
    assert ranked[0]["ticker"] == "HAS"


def test_rank_empty_rows_returns_empty():
    assert rank([], [{"metric": "x", "order": "desc", "weight": 1}]) == []


def test_rank_all_tied_values_scores_neutral_max():
    rows = [{"ticker": "A", "x": 5}, {"ticker": "B", "x": 5}]
    ranked = rank(rows, [{"metric": "x", "order": "desc", "weight": 1}])
    assert ranked[0]["_score"] == ranked[1]["_score"] == 1.0
