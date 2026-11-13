"""
metric_screener.py -- rule-based filtering and weighted ranking of a list
of metric dicts (e.g. fundamentals per symbol), adapted from trader-skill's
trader-screener skill (vendor/trader-skill/trader-screener/screen.py, MIT
License, Copyright (c) 2026 Jake Schincariol).

Pure, no network -- filters/ranks whatever metrics the caller supplies
(this project already has its own data sources; this is a generic
filter+rank engine, not a new data fetcher).
"""
from __future__ import annotations

from typing import Optional

_OPS = {
    ">":  lambda v, target: v > target,
    ">=": lambda v, target: v >= target,
    "<":  lambda v, target: v < target,
    "<=": lambda v, target: v <= target,
    "==": lambda v, target: v == target,
    "!=": lambda v, target: v != target,
    "between": lambda v, target: target[0] <= v <= target[1],
    "in": lambda v, target: v in target,
    "not in": lambda v, target: v not in target,
}


def check_rule(row: dict, rule: dict, missing: str = "fail") -> dict:
    """Check one rule ({"metric", "op", "value"}) against one row.
    Returns {"passed": bool, "reason": str|None}."""
    metric = rule["metric"]
    op = rule["op"]
    if op not in _OPS:
        raise ValueError(f"unknown op {op!r} -- use one of {sorted(_OPS)}")
    if metric not in row or row[metric] is None:
        if missing == "skip":
            return {"passed": True, "reason": f"{metric} missing, skipped (missing='skip')"}
        return {"passed": False, "reason": f"{metric} missing (missing='fail')"}
    v = row[metric]
    passed = _OPS[op](v, rule["value"])
    reason = None if passed else f"{metric}={v!r} fails {op} {rule['value']!r}"
    return {"passed": passed, "reason": reason}


def screen(rows: list, rules: list, missing: str = "fail") -> dict:
    """Filter rows against every rule. Returns {"passed": [...], "failed": [...]}
    where each entry is {"row": dict, "failures": [reason, ...]} for failed
    rows, and the raw row for passed ones."""
    passed, failed = [], []
    for row in rows:
        failures = []
        for rule in rules:
            result = check_rule(row, rule, missing)
            if not result["passed"]:
                failures.append(result["reason"])
        if failures:
            failed.append({"row": row, "failures": failures})
        else:
            passed.append(row)
    return {"passed": passed, "failed": failed}


def rank(rows: list, rank_rules: list, top: Optional[int] = None) -> list:
    """Weighted-rank rows by one or more metrics. rank_rules:
    [{"metric", "order": "asc"|"desc", "weight": float}, ...].

    Each metric is min-max normalized to [0, 1] across the row set (asc:
    higher value -> higher normalized score; desc: lower value -> higher
    score), then combined by weight. Rows missing a ranked metric get 0 for
    that metric's contribution, not excluded entirely.

    Returns rows sorted by descending combined score, each with an added
    "_score" key. Rows with no valid ranked metrics are sorted last."""
    if not rows:
        return []

    bounds = {}
    for rr in rank_rules:
        metric = rr["metric"]
        values = [r[metric] for r in rows if r.get(metric) is not None]
        if values:
            bounds[metric] = (min(values), max(values))

    scored = []
    for row in rows:
        total_weight = 0.0
        score = 0.0
        for rr in rank_rules:
            metric, order, weight = rr["metric"], rr.get("order", "desc"), rr.get("weight", 1.0)
            total_weight += weight
            if metric not in bounds or row.get(metric) is None:
                continue
            lo, hi = bounds[metric]
            if hi == lo:
                normalized = 1.0  # every row ties on this metric -- treat as neutral max
            else:
                normalized = (row[metric] - lo) / (hi - lo)
                if order == "asc":
                    normalized = 1.0 - normalized  # lower raw value -> higher score
            score += normalized * weight
        combined = score / total_weight if total_weight else 0.0
        scored.append({**row, "_score": round(combined, 4)})

    scored.sort(key=lambda r: -r["_score"])
    return scored[:top] if top else scored
