"""
Signal postmortem, adapted from claude-trading-skills' `signal-postmortem`
skill (vendor/claude-trading-skills/skills/signal-postmortem/SKILL.md).
MIT License, Copyright (c) 2026 TraderMonty.

SCOPE REDUCTION, disclosed: the source skill is a feedback step in a
multi-skill "edge pipeline" (edge-signal-aggregator issues independently-
weighted signals from many source skills; this skill feeds false-positive
rates back into those per-skill weights, plus a skill-improvement
backlog). This project has no such pipeline -- there is exactly one
decision-maker (the Gemini consensus engine) per prediction, not many
competing skills to re-weight. The two parts of the source skill that
depend on that pipeline are therefore dropped entirely, not faked:
  - `MISSED_OPPORTUNITY` classification never applies here (there is no
    "signal considered but not taken" concept -- every prediction this
    project makes is "taken").
  - The `edge-signal-aggregator` weight-feedback JSON and the skill-
    improvement-backlog YAML are not generated -- there is no aggregator
    or backlog to feed.
What IS ported faithfully: TRUE_POSITIVE/FALSE_POSITIVE/REGIME_MISMATCH
classification (predicted direction vs. realized return sign, with a
market-regime-change check distinguishing a genuine miscall from a signal
that failed because the macro regime shifted underneath it), applied to
this project's own real validated predictions, plus the "20+ samples
before trusting a rate" minimum-sample-size principle (Key Principle 3).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

MIN_SAMPLE_THRESHOLD = 20

_DIRECTION_MAP = {"BUY": "LONG", "SELL": "SHORT"}


def decision_to_direction(decision: Optional[str]) -> Optional[str]:
    """Map this project's BUY/SELL/HOLD decision to LONG/SHORT. HOLD -> None (no direction to test)."""
    if not decision:
        return None
    return _DIRECTION_MAP.get(str(decision).upper())


def classify_outcome_category(
    predicted_direction: str,
    realized_return_pct: Optional[float],
    regime_changed: bool = False,
) -> str:
    """TRUE_POSITIVE / FALSE_POSITIVE / REGIME_MISMATCH / UNKNOWN.

    `regime_changed` means the macro regime label at signal time differs
    from the regime label at exit time -- a wrong call made in a regime
    that then flipped is attributed to REGIME_MISMATCH rather than a flat
    FALSE_POSITIVE, per the source skill's own distinction.
    """
    if realized_return_pct is None:
        return "UNKNOWN"
    predicted_up = predicted_direction == "LONG"
    realized_up = realized_return_pct > 0
    if realized_return_pct == 0:
        return "FALSE_POSITIVE"
    if predicted_up == realized_up:
        return "TRUE_POSITIVE"
    return "REGIME_MISMATCH" if regime_changed else "FALSE_POSITIVE"


def _bucket_update(buckets: Dict[str, Dict[str, int]], key: str, category: str) -> None:
    b = buckets.setdefault(key, {"TRUE_POSITIVE": 0, "FALSE_POSITIVE": 0, "REGIME_MISMATCH": 0, "UNKNOWN": 0, "total": 0})
    b["total"] += 1
    b[category] = b.get(category, 0) + 1


def _finalize(buckets: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for key, b in buckets.items():
        classified = b["TRUE_POSITIVE"] + b["FALSE_POSITIVE"] + b["REGIME_MISMATCH"]
        out[key] = {
            **b,
            "true_positive_rate": (b["TRUE_POSITIVE"] / classified) if classified else None,
            "false_positive_rate": (b["FALSE_POSITIVE"] / classified) if classified else None,
            "regime_mismatch_rate": (b["REGIME_MISMATCH"] / classified) if classified else None,
            "sample_size_sufficient": classified >= MIN_SAMPLE_THRESHOLD,
        }
    return out


def build_signal_postmortem(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """entries: list of {symbol, decision, realized_return_pct, regime_changed}.

    Each entry is already classified by this module's caller gathering the
    regime context (this function stays pure/no-I/O, consistent with
    every other *_screener.py / *_analyzer.py in this project).
    """
    by_symbol: Dict[str, Dict[str, int]] = {}
    by_decision: Dict[str, Dict[str, int]] = {}
    overall = {"TRUE_POSITIVE": 0, "FALSE_POSITIVE": 0, "REGIME_MISMATCH": 0, "UNKNOWN": 0, "total": 0}
    records_out = []

    for entry in entries:
        direction = decision_to_direction(entry.get("decision"))
        if direction is None:
            continue
        category = classify_outcome_category(
            direction, entry.get("realized_return_pct"), entry.get("regime_changed", False)
        )
        symbol = str(entry.get("symbol", "UNKNOWN")).upper()
        decision = str(entry.get("decision", "UNKNOWN")).upper()

        _bucket_update(by_symbol, symbol, category)
        _bucket_update(by_decision, decision, category)
        overall["total"] += 1
        overall[category] = overall.get(category, 0) + 1

        records_out.append({
            "symbol": symbol,
            "decision": decision,
            "predicted_direction": direction,
            "realized_return_pct": entry.get("realized_return_pct"),
            "outcome_category": category,
            "regime_at_signal": entry.get("regime_at_signal"),
            "regime_at_exit": entry.get("regime_at_exit"),
        })

    classified_total = overall["TRUE_POSITIVE"] + overall["FALSE_POSITIVE"] + overall["REGIME_MISMATCH"]
    return {
        "schema_version": "1.0",
        "report_type": "signal_postmortem",
        "overall": {
            **overall,
            "true_positive_rate": (overall["TRUE_POSITIVE"] / classified_total) if classified_total else None,
            "false_positive_rate": (overall["FALSE_POSITIVE"] / classified_total) if classified_total else None,
            "regime_mismatch_rate": (overall["REGIME_MISMATCH"] / classified_total) if classified_total else None,
            "sample_size_sufficient": classified_total >= MIN_SAMPLE_THRESHOLD,
        },
        "by_symbol": _finalize(by_symbol),
        "by_decision": _finalize(by_decision),
        "records": records_out,
    }
