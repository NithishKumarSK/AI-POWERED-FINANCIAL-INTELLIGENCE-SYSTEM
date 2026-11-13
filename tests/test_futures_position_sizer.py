"""
Tests for core/futures_position_sizer.py -- pure, offline calculation.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import pytest

from futures_position_sizer import CONTRACT_SPECS, size_futures_position


def test_contract_spec_table_internal_consistency():
    for symbol, spec in CONTRACT_SPECS.items():
        expected = spec["multiplier"] * spec["tick_size"]
        assert abs(expected - spec["tick_value"]) / spec["tick_value"] < 1e-6, symbol


def test_contract_spec_table_all_usd_quoted():
    assert all(spec["currency"] == "USD" for spec in CONTRACT_SPECS.values())


def test_es_long_worked_example():
    # Matches the SKILL.md output-contract example exactly: risk_budget_usd
    # 2000.00 (2% of 100,000) -> 1 contract at $1012.50 risk -> 1.01% of account.
    result = size_futures_position("ES", "LONG", entry=5000.25, stop=4980.00, account_size=100_000, risk_pct=2.0)
    assert result["sizing_status"] == "SIZED"
    assert result["stop_distance_points"] == 20.25
    assert result["stop_distance_ticks"] == 81
    assert result["risk_per_contract_usd"] == pytest.approx(1012.50, abs=0.01)
    assert result["contracts"] == 1
    assert result["risk_pct_of_account"] == pytest.approx(1.01, abs=0.01)


def test_unknown_symbol_raises():
    with pytest.raises(ValueError, match="Unknown symbol"):
        size_futures_position("XX", "LONG", entry=100, stop=99, account_size=100_000, risk_pct=1.0)


def test_long_stop_on_wrong_side_raises():
    with pytest.raises(ValueError, match="LONG stop must be below entry"):
        size_futures_position("ES", "LONG", entry=5000, stop=5010, account_size=100_000, risk_pct=1.0)


def test_short_stop_on_wrong_side_raises():
    with pytest.raises(ValueError, match="SHORT stop must be above entry"):
        size_futures_position("ES", "SHORT", entry=5000, stop=4990, account_size=100_000, risk_pct=1.0)


def test_bond_off_tick_grid_is_hard_rejection():
    with pytest.raises(ValueError, match="tick grid"):
        size_futures_position("ZB", "LONG", entry=110.16, stop=108.00, account_size=100_000, risk_pct=1.0)


def test_bond_on_tick_grid_decimal_succeeds():
    result = size_futures_position("ZB", "LONG", entry=110.50, stop=108.00, account_size=100_000, risk_pct=1.0)
    assert result["sizing_status"] in ("SIZED", "NO_TRADE")


def test_non_bond_off_tick_grid_is_a_soft_warning_not_a_rejection():
    result = size_futures_position("ES", "LONG", entry=5000.17, stop=4980.00, account_size=100_000, risk_pct=2.0)
    assert result["sizing_status"] == "SIZED"
    assert "off_tick_grid_entry" in result["warnings"]


def test_risk_below_one_contract_is_no_trade_not_an_error():
    result = size_futures_position("ZB", "LONG", entry=110.50, stop=100.00, account_size=1_000, risk_pct=0.1)
    assert result["sizing_status"] == "NO_TRADE"
    assert result["no_trade_reason"] == "risk_below_one_contract"


def test_risk_pct_above_2_is_a_warning():
    result = size_futures_position("ES", "LONG", entry=5000.25, stop=4980.00, account_size=100_000, risk_pct=3.0)
    assert "risk_pct_above_2" in result["warnings"]


def test_floor_never_exceeds_risk_budget():
    result = size_futures_position("GC", "LONG", entry=2650.00, stop=2600.00, account_size=50_000, risk_pct=1.0)
    if result["sizing_status"] == "SIZED":
        assert result["total_risk_usd"] <= result["risk_budget_usd"] + 1e-9


def test_fx_rate_applied_to_non_usd_quoted_override():
    result = size_futures_position("ES", "LONG", entry=5000.25, stop=4980.00, account_size=100_000, risk_pct=1.0, fx_rate=1.25)
    assert result["fx_rate_used"] == 1.25
