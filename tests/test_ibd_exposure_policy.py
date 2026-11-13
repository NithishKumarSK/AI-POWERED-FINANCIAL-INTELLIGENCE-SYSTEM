"""Tests for core/portfolio_tools/ibd_exposure_policy.py -- risk-level ->
TQQQ/QQQ exposure action mapping, ported from claude-trading-skills."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from portfolio_tools.ibd_exposure_policy import generate_portfolio_action


def test_normal_risk_holds_full_exposure():
    action = generate_portfolio_action("NORMAL", "TQQQ", current_exposure_pct=100, base_trailing_stop_pct=10)
    assert action.recommended_action == "HOLD_OR_FOLLOW_BASE_STRATEGY"
    assert action.target_exposure_pct == 100
    assert action.exposure_delta_pct == 0


def test_tqqq_cuts_faster_than_qqq_at_same_risk_level():
    tqqq = generate_portfolio_action("HIGH", "TQQQ", current_exposure_pct=100, base_trailing_stop_pct=10)
    qqq = generate_portfolio_action("HIGH", "QQQ", current_exposure_pct=100, base_trailing_stop_pct=10)
    assert tqqq.target_exposure_pct < qqq.target_exposure_pct


def test_severe_tqqq_has_switch_to_cash_alternative():
    action = generate_portfolio_action("SEVERE", "TQQQ", current_exposure_pct=100, base_trailing_stop_pct=10)
    assert action.alternative_action == "SWITCH_TO_QQQ_OR_CASH"
    assert action.target_exposure_pct == 25


def test_qqq_has_no_alternative_action():
    action = generate_portfolio_action("SEVERE", "QQQ", current_exposure_pct=100, base_trailing_stop_pct=10)
    assert action.alternative_action is None


def test_trailing_stop_capped_but_not_raised():
    # base stop (3%) is already tighter than the SEVERE cap (3) -- stays at 3, not raised.
    action = generate_portfolio_action("SEVERE", "TQQQ", current_exposure_pct=100, base_trailing_stop_pct=3)
    assert action.trailing_stop_pct == 3
    # base stop (20%) is looser than the cap -- gets capped down to 3.
    action2 = generate_portfolio_action("SEVERE", "TQQQ", current_exposure_pct=100, base_trailing_stop_pct=20)
    assert action2.trailing_stop_pct == 3


def test_unknown_risk_level_raises():
    import pytest
    with pytest.raises(ValueError):
        generate_portfolio_action("BOGUS", "QQQ", current_exposure_pct=100, base_trailing_stop_pct=10)
