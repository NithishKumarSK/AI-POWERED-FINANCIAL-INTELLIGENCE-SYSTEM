"""
Weekly performance digest, adapted from claude-trading-skills'
`weekly-performance-digest` skill (vendor/claude-trading-skills/skills/
weekly-performance-digest/SKILL.md). MIT License, Copyright (c) 2026
TraderMonty.

SCOPE REDUCTION, disclosed: the source skill reads CLOSED theses tracked
by `trader-memory-core` (`state/theses/th_*.yaml` -- real broker fills,
stop-losses, MAE/MFE excursion tracking). This project has no equivalent
state (same reason `trader-memory-core` itself was not ported -- see
vendor/README.md). The honest substitute used here is this project's own
"closed" unit: a VALIDATED prediction record from `stock_predictions`
(symbol + origin/target date + decision vs. actual_decision + the
simulated `actual_total_pl` already computed from the user's chosen
initial_capital and the real market move). Consequences of that
substitution, applied consistently rather than silently:
  - "win/loss" uses `actual_total_pl` sign, exactly as the source skill's
    `outcome.pnl_dollars` rule, but this is a SIMULATED capital P&L, not
    a real brokerage fill.
  - R-multiple and MAE/MFE are DROPPED entirely (not faked) -- this
    project tracks no stop-loss or intraday price-excursion per
    prediction, so there is nothing honest to compute them from.
  - Pattern dimensions are rescoped to what this project actually has:
    by symbol, by decision, by horizon bucket (reusing
    `core/segment_reliability.py`'s bucket labels), by decision-match
    correctness -- not sector/mechanism-tag/screening-grade, which this
    project's records don't carry.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

from batch_validation_runner import horizon_bucket


def _get_path(record: Dict[str, Any], *path: str) -> Any:
    node: Any = record
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def select_records_in_window(
    records: List[Dict[str, Any]],
    from_date: str,
    to_date: str,
) -> List[Dict[str, Any]]:
    """Filter to records whose effective_target_date falls in [from_date, to_date].

    Falls back to the record's timestamp when effective_target_date is
    missing (an edge case for very old rows), rather than silently
    dropping it.
    """
    try:
        start = _dt.date.fromisoformat(from_date)
        end = _dt.date.fromisoformat(to_date)
    except (ValueError, TypeError):
        return []

    out = []
    for rec in records:
        date_str = _get_path(rec, "actual_validation", "effective_target_date") or rec.get("timestamp")
        if not date_str:
            continue
        try:
            d = _dt.date.fromisoformat(str(date_str)[:10])
        except ValueError:
            continue
        if start <= d <= end:
            out.append(rec)
    return out


def classify_outcome(record: Dict[str, Any]) -> str:
    """'win' / 'loss' / 'breakeven', from the simulated actual_total_pl sign."""
    pnl = _get_path(record, "actual_validation", "actual_total_pl")
    if pnl is None:
        return "breakeven"
    if pnl > 0:
        return "win"
    if pnl < 0:
        return "loss"
    return "breakeven"


def _bucket_update(buckets: Dict[str, Dict[str, int]], key: str, outcome: str) -> None:
    b = buckets.setdefault(key, {"wins": 0, "losses": 0, "breakeven": 0, "total": 0})
    b["total"] += 1
    if outcome == "win":
        b["wins"] += 1
    elif outcome == "loss":
        b["losses"] += 1
    else:
        b["breakeven"] += 1


def _finalize_buckets(buckets: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for key, b in buckets.items():
        decided = b["wins"] + b["losses"]
        out[key] = {**b, "win_rate": (b["wins"] / decided) if decided else None}
    return out


def build_weekly_digest(
    records: List[Dict[str, Any]],
    from_date: str,
    to_date: str,
    top_n: int = 3,
) -> Dict[str, Any]:
    """Pure calculation over an already date-filtered record list.

    An empty week still produces a valid, zeroed report -- matching the
    source skill's "An empty week still produces a valid report" rule.
    """
    total = len(records)
    wins = losses = breakeven = 0
    pnls: List[float] = []
    by_symbol: Dict[str, Dict[str, int]] = {}
    by_decision: Dict[str, Dict[str, int]] = {}
    by_horizon_bucket: Dict[str, Dict[str, int]] = {}
    by_decision_match: Dict[str, Dict[str, int]] = {}
    scored: List[Dict[str, Any]] = []

    for rec in records:
        outcome = classify_outcome(rec)
        if outcome == "win":
            wins += 1
        elif outcome == "loss":
            losses += 1
        else:
            breakeven += 1

        pnl = _get_path(rec, "actual_validation", "actual_total_pl")
        if pnl is not None:
            pnls.append(float(pnl))

        symbol = _get_path(rec, "stock_prediction_input", "symbol") or "UNKNOWN"
        decision = _get_path(rec, "ai_prediction", "decision") or "UNKNOWN"
        horizon_days = _get_path(rec, "stock_prediction_input", "decision_horizon_days")
        bucket = horizon_bucket(int(horizon_days)) if horizon_days is not None else "unknown"
        dec_match = _get_path(rec, "comparison", "decision_match")
        dec_match_key = "correct" if dec_match else "incorrect" if dec_match is not None else "unknown"

        _bucket_update(by_symbol, str(symbol).upper(), outcome)
        _bucket_update(by_decision, str(decision).upper(), outcome)
        _bucket_update(by_horizon_bucket, bucket, outcome)
        _bucket_update(by_decision_match, dec_match_key, outcome)

        scored.append({
            "symbol": symbol,
            "decision": decision,
            "actual_total_pl": pnl,
            "directional_match": _get_path(rec, "comparison", "directional_match"),
            "decision_match": dec_match,
        })

    decided_total = wins + losses
    win_rate = (wins / decided_total) if decided_total else 0.0
    winner_pnls = [p for p in pnls if p > 0]
    loser_pnls = [p for p in pnls if p < 0]
    avg_winner = (sum(winner_pnls) / len(winner_pnls)) if winner_pnls else 0.0
    avg_loser = (sum(loser_pnls) / len(loser_pnls)) if loser_pnls else 0.0
    loss_rate = (losses / decided_total) if decided_total else 0.0
    expectancy = (win_rate * avg_winner) + (loss_rate * avg_loser)
    gross_profit = sum(winner_pnls)
    gross_loss = abs(sum(loser_pnls))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    total_realized_pnl = sum(pnls)

    scored_with_pnl = [s for s in scored if s["actual_total_pl"] is not None]
    top_winners = sorted(scored_with_pnl, key=lambda s: s["actual_total_pl"], reverse=True)[:top_n]
    top_losers = sorted(scored_with_pnl, key=lambda s: s["actual_total_pl"])[:top_n]

    process_improvements: List[str] = []
    for decision_label, stats in by_decision.items():
        decided = stats["wins"] + stats["losses"]
        if decided >= 3 and (stats["wins"] / decided) < 0.4:
            process_improvements.append(
                f"{decision_label} decisions had a low win rate this week "
                f"({stats['wins']}/{decided} = {stats['wins']/decided:.0%}) -- review that decision class."
            )

    return {
        "schema_version": "1.0",
        "report_type": "weekly_performance_digest",
        "period": {"from": from_date, "to": to_date},
        "summary": {
            "total_trades": total,
            "winners": wins,
            "losers": losses,
            "breakeven": breakeven,
            "win_rate": win_rate,
            "expectancy": expectancy,
            "profit_factor": profit_factor,
            "total_realized_pnl": total_realized_pnl,
        },
        "pattern_analysis": {
            "by_symbol": _finalize_buckets(by_symbol),
            "by_decision": _finalize_buckets(by_decision),
            "by_horizon_bucket": _finalize_buckets(by_horizon_bucket),
            "by_decision_match": _finalize_buckets(by_decision_match),
        },
        "lessons": {
            "top_winners": top_winners,
            "top_losers": top_losers,
            "process_improvements": process_improvements,
        },
    }
