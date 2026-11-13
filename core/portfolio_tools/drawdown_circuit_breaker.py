"""
drawdown_circuit_breaker.py -- account-level risk gate for new trade risk,
adapted from claude-trading-skills' drawdown-circuit-breaker skill
(vendor/claude-trading-skills/skills/drawdown-circuit-breaker/, MIT
License, Copyright (c) 2026 TraderMonty).

Pure function over a caller-supplied list of closed-trade P&L events --
this project has no trader-memory-core-style thesis YAML ledger, so unlike
the source skill (which reads/aggregates those files), the caller supplies
realized trade outcomes directly.

Four independent rules, any of which can block new risk (HALTED ranks
above COOLDOWN ranks above TRADING_ALLOWED):
  max_daily_loss     today's realized P&L breaches -max_daily_loss_pct% of
                      account_size -> HALTED until the next session.
  losing_streak       >= losing_streak_n consecutive losing closes ->
                      COOLDOWN for cooldown_hours from the last loss.
  weekly_drawdown     week-to-date realized P&L breaches
                      -weekly_drawdown_pct% -> HALTED until next Monday.
  monthly_drawdown    month-to-date realized P&L breaches
                      -monthly_drawdown_pct% -> HALTED until next month.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, asdict
from typing import Optional

_RANK = {"TRADING_ALLOWED": 0, "COOLDOWN": 1, "HALTED": 2}


@dataclass(frozen=True)
class CircuitConfig:
    max_daily_loss_pct: float = 2.0
    losing_streak_n: int = 2
    cooldown_hours: float = 24.0
    weekly_drawdown_pct: float = 5.0
    monthly_drawdown_pct: float = 8.0


def _consecutive_losses(closed_trades: list) -> tuple:
    """closed_trades sorted oldest-first. Returns (count, last_loss_closed_at)."""
    count = 0
    last_loss_at = None
    for t in reversed(closed_trades):
        if t["pnl"] >= 0:
            break
        count += 1
        if last_loss_at is None:
            last_loss_at = t["closed_at"]
    return count, last_loss_at


def evaluate_circuit_breaker(
    closed_trades: list,
    account_size: float,
    as_of: str,
    config: Optional[CircuitConfig] = None,
) -> dict:
    """closed_trades: [{"closed_at": "YYYY-MM-DDTHH:MM:SS", "pnl": float}, ...],
    any order (sorted internally by closed_at). as_of: "YYYY-MM-DD" or full
    ISO timestamp.

    Returns {"recommendation": "TRADING_ALLOWED"|"COOLDOWN"|"HALTED",
             "triggered_rules": [...], "metrics": {...}, "rationale": str}."""
    if account_size <= 0:
        raise ValueError("account_size must be positive")
    cfg = config or CircuitConfig()

    as_of_date = _dt.date.fromisoformat(as_of[:10])
    week_start = as_of_date - _dt.timedelta(days=as_of_date.weekday())
    month_start = as_of_date.replace(day=1)

    trades = sorted(
        ({**t, "closed_at": t["closed_at"]} for t in closed_trades if t["closed_at"][:10] <= as_of_date.isoformat()),
        key=lambda t: t["closed_at"],
    )

    def _sum_between(start: _dt.date, end: _dt.date) -> float:
        return sum(t["pnl"] for t in trades if start.isoformat() <= t["closed_at"][:10] <= end.isoformat())

    realized_today = _sum_between(as_of_date, as_of_date)
    realized_wtd = _sum_between(week_start, as_of_date)
    realized_mtd = _sum_between(month_start, as_of_date)
    consecutive_losses, last_loss_at = _consecutive_losses(trades)

    triggered = []

    daily_threshold = account_size * cfg.max_daily_loss_pct / 100.0
    if realized_today <= -daily_threshold:
        triggered.append({
            "rule": "max_daily_loss", "severity": "HALTED",
            "threshold": round(daily_threshold, 2), "observed": round(realized_today, 2),
            "detail": f"Realized P&L today is {realized_today:.2f}, breaching the {cfg.max_daily_loss_pct}% daily loss limit.",
        })

    if consecutive_losses >= cfg.losing_streak_n and last_loss_at:
        last_loss_dt = _dt.datetime.fromisoformat(last_loss_at)
        active_until = last_loss_dt + _dt.timedelta(hours=cfg.cooldown_hours)
        as_of_dt = _dt.datetime.fromisoformat(as_of if "T" in as_of else as_of + "T00:00:00")
        if as_of_dt < active_until:
            triggered.append({
                "rule": "losing_streak_cooldown", "severity": "COOLDOWN",
                "threshold": cfg.losing_streak_n, "observed": consecutive_losses,
                "active_until": active_until.isoformat(),
                "detail": f"{consecutive_losses} consecutive losing closes; last loss exit {last_loss_at}.",
            })

    weekly_threshold = account_size * cfg.weekly_drawdown_pct / 100.0
    if realized_wtd <= -weekly_threshold:
        triggered.append({
            "rule": "weekly_drawdown_halt", "severity": "HALTED",
            "threshold": round(weekly_threshold, 2), "observed": round(realized_wtd, 2),
            "detail": f"Week-to-date realized P&L is {realized_wtd:.2f}, breaching the {cfg.weekly_drawdown_pct}% weekly loss limit.",
        })

    monthly_threshold = account_size * cfg.monthly_drawdown_pct / 100.0
    if realized_mtd <= -monthly_threshold:
        triggered.append({
            "rule": "monthly_drawdown_halt", "severity": "HALTED",
            "threshold": round(monthly_threshold, 2), "observed": round(realized_mtd, 2),
            "detail": f"Month-to-date realized P&L is {realized_mtd:.2f}, breaching the {cfg.monthly_drawdown_pct}% monthly loss limit.",
        })

    recommendation = "TRADING_ALLOWED"
    for rule in triggered:
        if _RANK[rule["severity"]] > _RANK[recommendation]:
            recommendation = rule["severity"]

    if recommendation == "TRADING_ALLOWED":
        rationale = "No account-level circuit breaker rules are active; new trade risk may proceed."
    elif recommendation == "COOLDOWN":
        rationale = "Recent losing closes triggered a cooldown. Avoid new entries until the cooldown expires."
    else:
        rationale = "Realized losses breached one or more drawdown limits. Halt new entries and focus on review."

    return {
        "recommendation": recommendation,
        "triggered_rules": triggered,
        "metrics": {
            "realized_pnl_today": round(realized_today, 2),
            "realized_pnl_wtd": round(realized_wtd, 2),
            "realized_pnl_mtd": round(realized_mtd, 2),
            "consecutive_losses": consecutive_losses,
            "trades_scanned": len(trades),
        },
        "account_size": account_size,
        "config": asdict(cfg),
        "rationale": rationale,
    }
