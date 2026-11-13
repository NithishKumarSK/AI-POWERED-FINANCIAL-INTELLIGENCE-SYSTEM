"""Tests for core/portfolio_tools/pretrade_discipline_gate.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from portfolio_tools.pretrade_discipline_gate import check_discipline


def test_all_checklist_items_confirmed_goes():
    r = check_discipline("ENTRY_READY", True, True, True, 100, 100)
    assert r["decision"] == "GO"
    assert r["reasons"] == []


def test_missing_written_plan_blocks():
    r = check_discipline("ENTRY_READY", False, True, True, 100, 100)
    assert r["decision"] == "NO_GO"
    assert any("written plan" in reason for reason in r["reasons"])


def test_missing_predefined_stop_blocks():
    r = check_discipline("ENTRY_READY", True, False, True, 100, 100)
    assert r["decision"] == "NO_GO"


def test_size_not_confirmed_blocks():
    r = check_discipline("ENTRY_READY", True, True, False, 100, 100)
    assert r["decision"] == "NO_GO"


def test_actual_risk_exceeding_planned_blocks():
    r = check_discipline("ENTRY_READY", True, True, True, 100, 150)
    assert r["decision"] == "NO_GO"
    assert any("exceeds planned risk" in reason for reason in r["reasons"])


def test_actual_risk_equal_to_planned_passes():
    r = check_discipline("ENTRY_READY", True, True, True, 100, 100)
    assert r["decision"] == "GO"


def test_actual_risk_under_planned_passes():
    r = check_discipline("ENTRY_READY", True, True, True, 100, 50)
    assert r["decision"] == "GO"


def test_watchlist_intent_is_non_actionable():
    r = check_discipline("WATCHLIST")
    assert r["decision"] == "NO_ACTIONABLE_ORDERS"


def test_unknown_intent_requires_review():
    r = check_discipline("some_made_up_intent")
    assert r["decision"] == "REVIEW_REQUIRED"


def test_missing_planned_risk_requires_review():
    r = check_discipline("ENTRY_READY", True, True, True, None, 100)
    assert r["decision"] == "REVIEW_REQUIRED"


def test_missing_actual_risk_requires_review():
    r = check_discipline("ENTRY_READY", True, True, True, 100, None)
    assert r["decision"] == "REVIEW_REQUIRED"


def test_negative_risk_values_treated_as_invalid():
    r = check_discipline("ENTRY_READY", True, True, True, -5, 100)
    assert r["decision"] == "REVIEW_REQUIRED"


def test_no_go_outranks_review_required_when_both_present():
    # Missing stop (NO_GO) AND missing planned_risk (REVIEW_REQUIRED) at once
    # -- the stricter NO_GO must win per DECISION_RANK.
    r = check_discipline("ENTRY_READY", True, False, True, None, 100)
    assert r["decision"] == "NO_GO"
    assert len(r["reasons"]) >= 2


def test_lowercase_intent_normalized():
    r = check_discipline("entry_ready", True, True, True, 100, 100)
    assert r["decision"] == "GO"
