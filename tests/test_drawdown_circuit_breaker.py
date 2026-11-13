"""Tests for core/portfolio_tools/drawdown_circuit_breaker.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from portfolio_tools.drawdown_circuit_breaker import evaluate_circuit_breaker, CircuitConfig


def test_no_trades_allows_trading():
    r = evaluate_circuit_breaker([], account_size=10000, as_of="2026-10-30")
    assert r["recommendation"] == "TRADING_ALLOWED"
    assert r["triggered_rules"] == []


def test_daily_loss_breach_halts():
    trades = [{"closed_at": "2026-10-30T10:00:00", "pnl": -300}]
    r = evaluate_circuit_breaker(trades, account_size=10000, as_of="2026-10-30",
                                  config=CircuitConfig(max_daily_loss_pct=2.0))
    assert r["recommendation"] == "HALTED"
    assert any(t["rule"] == "max_daily_loss" for t in r["triggered_rules"])


def test_daily_loss_within_threshold_allows():
    trades = [{"closed_at": "2026-10-30T10:00:00", "pnl": -50}]
    r = evaluate_circuit_breaker(trades, account_size=10000, as_of="2026-10-30",
                                  config=CircuitConfig(max_daily_loss_pct=2.0))
    assert r["recommendation"] == "TRADING_ALLOWED"


def test_losing_streak_triggers_cooldown():
    trades = [
        {"closed_at": "2026-10-29T10:00:00", "pnl": -10},
        {"closed_at": "2026-10-29T14:00:00", "pnl": -10},
    ]
    r = evaluate_circuit_breaker(trades, account_size=10000, as_of="2026-10-29T15:00:00",
                                  config=CircuitConfig(losing_streak_n=2, cooldown_hours=24))
    assert r["recommendation"] == "COOLDOWN"


def test_losing_streak_expires_after_cooldown_hours():
    trades = [
        {"closed_at": "2026-10-29T10:00:00", "pnl": -10},
        {"closed_at": "2026-10-29T14:00:00", "pnl": -10},
    ]
    r = evaluate_circuit_breaker(trades, account_size=10000, as_of="2026-10-31T15:00:00",
                                  config=CircuitConfig(losing_streak_n=2, cooldown_hours=24))
    assert r["recommendation"] == "TRADING_ALLOWED"


def test_a_win_breaks_the_losing_streak():
    trades = [
        {"closed_at": "2026-10-29T10:00:00", "pnl": -10},
        {"closed_at": "2026-10-29T12:00:00", "pnl": 50},  # win resets the streak
        {"closed_at": "2026-10-29T14:00:00", "pnl": -10},
    ]
    r = evaluate_circuit_breaker(trades, account_size=10000, as_of="2026-10-29T15:00:00",
                                  config=CircuitConfig(losing_streak_n=2, cooldown_hours=24))
    assert r["metrics"]["consecutive_losses"] == 1
    assert r["recommendation"] == "TRADING_ALLOWED"


def test_weekly_drawdown_breach_halts():
    trades = [
        {"closed_at": "2026-10-26T10:00:00", "pnl": -300},  # Monday of that week
        {"closed_at": "2026-10-28T10:00:00", "pnl": -300},
    ]
    r = evaluate_circuit_breaker(trades, account_size=10000, as_of="2026-10-30",
                                  config=CircuitConfig(max_daily_loss_pct=100, weekly_drawdown_pct=5.0))
    assert r["recommendation"] == "HALTED"
    assert any(t["rule"] == "weekly_drawdown_halt" for t in r["triggered_rules"])


def test_monthly_drawdown_breach_halts():
    trades = [{"closed_at": "2026-10-05T10:00:00", "pnl": -900}]
    r = evaluate_circuit_breaker(trades, account_size=10000, as_of="2026-10-30",
                                  config=CircuitConfig(max_daily_loss_pct=100, weekly_drawdown_pct=100, monthly_drawdown_pct=8.0))
    assert r["recommendation"] == "HALTED"
    assert any(t["rule"] == "monthly_drawdown_halt" for t in r["triggered_rules"])


def test_halted_ranks_above_cooldown_when_both_trigger():
    trades = [
        {"closed_at": "2026-10-30T09:00:00", "pnl": -10},
        {"closed_at": "2026-10-30T10:00:00", "pnl": -300},  # also breaches daily loss
    ]
    r = evaluate_circuit_breaker(trades, account_size=10000, as_of="2026-10-30T15:00:00",
                                  config=CircuitConfig(max_daily_loss_pct=2.0, losing_streak_n=2, cooldown_hours=24))
    assert r["recommendation"] == "HALTED"


def test_future_trades_after_as_of_excluded():
    trades = [{"closed_at": "2026-11-05T10:00:00", "pnl": -5000}]
    r = evaluate_circuit_breaker(trades, account_size=10000, as_of="2026-10-30",
                                  config=CircuitConfig(max_daily_loss_pct=2.0))
    assert r["recommendation"] == "TRADING_ALLOWED"
    assert r["metrics"]["trades_scanned"] == 0


def test_rejects_non_positive_account_size():
    import pytest
    with pytest.raises(ValueError):
        evaluate_circuit_breaker([], account_size=0, as_of="2026-10-30")
