"""
stockbee_setup_fluency_trainer.py -- a persistent "model book" that
records stockbee-momentum-burst-screener candidates as study examples,
matures them with 3/5-day forward MFE/MAE/outcome tags once enough future
price data exists, and summarizes win-rate evidence by setup tag/rating/
trigger. Ported from claude-trading-skills' stockbee-setup-fluency-trainer
skill (vendor/claude-trading-skills/skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py,
MIT License, Copyright (c) 2026 TraderMonty).

This is explicitly a journaling/research tool, not a live signal -- same
category as this project's own core/portfolio_tools/backtest_quality_scorer.py.
It is NOT wired into feature_packet: its value only accrues over many
days of real ingestion (the source skill's own design), and this
project's prediction pipeline runs one symbol at a time rather than a
daily batch screener sweep, so there is no natural "ingest every
candidate automatically" hook. core/stockbee_setup_fluency_trainer_service.py
(the thin persistence wrapper) is meant to be called manually, or wired
into a future cron, the same way the source skill's own CLI is meant to
be run daily.

The FMP-batch-price-fetch and file-based screener-report ingestion (the
skill's own "Mode A" input) were not ported -- this project already has
core/stockbee_momentum_burst_service.py (one symbol at a time) and
core/historical_price_service.py for forward-outcome price bars.

Reuses the Bar dataclass from core/stockbee_momentum_burst_screener.py
rather than redefining an identical one.
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime
from typing import Any, Optional

from stockbee_momentum_burst_screener import Bar

SCHEMA_VERSION = "1.0"
DEFAULT_HORIZONS = (3, 5)


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def upsert_records(existing: list, new_records: list) -> tuple:
    """Merge new_records into existing by record_id, preserving human
    annotations and already-matured outcomes against a fresh re-ingest."""
    by_id = {r.get("record_id"): dict(r) for r in existing if r.get("record_id")}
    inserted = updated = 0
    for record in new_records:
        record_id = record["record_id"]
        if record_id in by_id:
            previous = by_id[record_id]
            merged = dict(previous)
            preserved = {k: previous[k] for k in ("human_label", "human_decision", "human_notes") if k in previous}
            previous_has_outcome = bool(previous.get("outcomes")) or previous.get("matured")
            if previous_has_outcome and not record.get("outcomes"):
                for key in ("outcomes", "overall_outcome", "matured", "last_outcome_update_at"):
                    if key in previous:
                        preserved[key] = previous[key]
            merged.update(record)
            merged.update(preserved)
            by_id[record_id] = merged
            updated += 1
        else:
            by_id[record_id] = record
            inserted += 1
    return list(by_id.values()), {"inserted": inserted, "updated": updated, "total": len(by_id)}


def derive_setup_tags(candidate: dict) -> list:
    tags = set()
    for tag in candidate.get("trigger_tags", []) or []:
        if tag:
            tags.add(str(tag))
    for tag in candidate.get("soft_failure_tags", []) or []:
        if tag:
            tags.add(f"soft_{tag}")
    for tag in candidate.get("reject_reasons", []) or []:
        if tag:
            tags.add(f"reject_{tag}")

    rating = str(candidate.get("rating") or "")
    if rating:
        tags.add(f"rating_{rating.replace('+', 'plus').replace('-', 'minus')}")

    close_location = to_float(candidate.get("close_location_pct"))
    if close_location >= 85:
        tags.add("close_near_high")
    elif close_location < 50:
        tags.add("weak_close_location")

    volume_ratio = to_float(candidate.get("volume_ratio_1d"))
    if volume_ratio >= 3:
        tags.add("high_volume_expansion")
    elif 0 < volume_ratio < 1.2:
        tags.add("thin_volume_confirmation")

    base_width = to_float(candidate.get("base_width_pct"))
    if 0 < base_width <= 8:
        tags.add("tight_base")
    elif base_width >= 15:
        tags.add("wide_base")

    prior_base_days = to_int(candidate.get("prior_base_days"))
    if 3 <= prior_base_days <= 20:
        tags.add("controlled_3_to_20_day_base")
    elif prior_base_days > 30:
        tags.add("long_base")

    risk = to_float(candidate.get("risk_pct_to_stop"))
    if 0 < risk <= 3:
        tags.add("compact_risk")
    elif risk >= 6:
        tags.add("wide_risk")

    if candidate.get("volume_dry_up"):
        tags.add("volume_dry_up")
    if candidate.get("recent_4pct_breakdown"):
        tags.add("recent_4pct_breakdown")
    if to_int(candidate.get("prior_up_streak")) >= 3:
        tags.add("three_days_up_before_trigger")

    return sorted(tags)


def make_record(candidate: dict, source_skill: str = "stockbee-momentum-burst-screener") -> dict:
    symbol = normalize_symbol(candidate.get("symbol"))
    setup_date = str(candidate.get("date") or candidate.get("setup_date") or "")[:10]
    if not symbol or len(setup_date) != 10:
        raise ValueError(f"candidate missing symbol or setup date: {candidate}")
    primary_trigger = str(candidate.get("primary_trigger") or "unknown")
    record_id = f"stockbee_mb:{symbol}:{setup_date}:{primary_trigger}"

    entry = to_float(candidate.get("entry_reference"), default=to_float(candidate.get("close")))
    stop = to_float(candidate.get("stop_reference"), default=to_float(candidate.get("low")))

    return {
        "schema_version": SCHEMA_VERSION, "record_id": record_id, "source_skill": source_skill,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol, "setup_date": setup_date, "setup_type": "stockbee_momentum_burst",
        "primary_trigger": primary_trigger, "trigger_tags": candidate.get("trigger_tags", []) or [],
        "setup_tags": derive_setup_tags(candidate), "rating": candidate.get("rating"),
        "setup_score": to_float(candidate.get("setup_score")), "state_at_ingest": candidate.get("state"),
        "entry_reference": entry, "stop_reference": stop,
        "risk_pct_to_stop": to_float(candidate.get("risk_pct_to_stop")),
        "day_gain_pct": to_float(candidate.get("day_gain_pct")),
        "volume_ratio_1d": to_float(candidate.get("volume_ratio_1d")),
        "volume_ratio_20d": to_float(candidate.get("volume_ratio_20d")),
        "close_location_pct": to_float(candidate.get("close_location_pct")),
        "prior_base_days": to_int(candidate.get("prior_base_days")), "base_width_pct": to_float(candidate.get("base_width_pct")),
        "human_label": None, "human_decision": "unknown", "human_notes": "",
        "outcomes": {}, "overall_outcome": "PENDING", "matured": False, "raw_candidate": candidate,
    }


def is_studyable_candidate(candidate: dict) -> tuple:
    symbol = normalize_symbol(candidate.get("symbol"))
    setup_date = str(candidate.get("date") or candidate.get("setup_date") or "")[:10]
    if not symbol:
        return False, "missing_symbol"
    if len(setup_date) != 10:
        return False, "missing_setup_date"
    return True, None


def future_bars_after_setup(bars: list, setup_date: str) -> list:
    """bars: chronological (oldest first) Bar list."""
    from datetime import datetime as _dt
    setup_dt = _dt.strptime(setup_date[:10], "%Y-%m-%d").date()
    return [bar for bar in bars if _dt.strptime(bar.date[:10], "%Y-%m-%d").date() > setup_dt]


def calculate_window_outcome(record: dict, bars: list, horizon: int) -> dict:
    """Forward close return plus MFE/MAE for N future trading days."""
    entry = to_float(record.get("entry_reference"))
    stop = to_float(record.get("stop_reference"))
    if entry <= 0:
        return {"horizon_days": horizon, "matured": False, "reason": "missing_entry"}

    future = future_bars_after_setup(bars, str(record.get("setup_date")))
    if len(future) < horizon:
        return {"horizon_days": horizon, "matured": False, "available_future_bars": len(future), "reason": "not_enough_future_bars"}

    window = future[:horizon]
    close_bar = window[-1]
    max_high = max(bar.high for bar in window)
    min_low = min(bar.low for bar in window)
    fwd = (close_bar.close / entry - 1.0) * 100.0
    mfe = (max_high / entry - 1.0) * 100.0
    mae = (min_low / entry - 1.0) * 100.0

    stop_hit, stop_hit_date = False, None
    if stop > 0:
        for bar in window:
            if bar.low <= stop:
                stop_hit, stop_hit_date = True, bar.date
                break

    tag = classify_outcome(fwd_return_pct=fwd, mfe_pct=mfe, mae_pct=mae, stop_hit=stop_hit)
    return {
        "horizon_days": horizon, "matured": True, "close_date": close_bar.date, "close": round(close_bar.close, 4),
        "forward_return_pct": round(fwd, 2), "mfe_pct": round(mfe, 2), "mae_pct": round(mae, 2),
        "max_high": round(max_high, 4), "min_low": round(min_low, 4),
        "stop_hit": stop_hit, "stop_hit_date": stop_hit_date, "outcome_tag": tag,
    }


def classify_outcome(fwd_return_pct: float, mfe_pct: float, mae_pct: float, stop_hit: bool) -> str:
    if stop_hit:
        return "FAILED_STOP"
    if mfe_pct >= 12 or fwd_return_pct >= 8:
        return "STRONG_WINNER"
    if mfe_pct >= 6 or fwd_return_pct >= 4:
        return "WORKED"
    if fwd_return_pct <= -2:
        return "FAILED_FADE"
    if mae_pct <= -5 and fwd_return_pct < 2:
        return "CHOPPY_FAILURE"
    return "NEUTRAL"


def derive_overall_outcome(outcomes: dict, primary_horizon: int = 5) -> str:
    preferred = outcomes.get(f"{primary_horizon}d")
    if not preferred or not preferred.get("matured"):
        return "PENDING"
    return str(preferred.get("outcome_tag", "UNKNOWN"))


def update_record_outcomes(records: list, prices_by_symbol: dict, horizons: tuple = DEFAULT_HORIZONS, only_pending: bool = True) -> tuple:
    """prices_by_symbol: {symbol: list[Bar]} (chronological)."""
    stats = {"updated": 0, "matured": 0, "still_pending": 0, "skipped_no_prices": 0}
    for record in records:
        if only_pending and record.get("matured"):
            continue
        symbol = normalize_symbol(record.get("symbol"))
        bars = prices_by_symbol.get(symbol)
        if not bars:
            record["update_error"] = "missing_prices"
            stats["skipped_no_prices"] += 1
            continue
        outcomes = dict(record.get("outcomes") or {})
        for horizon in horizons:
            outcomes[f"{horizon}d"] = calculate_window_outcome(record, bars, horizon)
        record["outcomes"] = outcomes
        record["overall_outcome"] = derive_overall_outcome(outcomes, primary_horizon=max(horizons))
        record["matured"] = record["overall_outcome"] != "PENDING"
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        record["last_outcome_update_at"] = record["updated_at"]
        stats["matured" if record["matured"] else "still_pending"] += 1
        stats["updated"] += 1
    return records, stats


def values_for_metric(records: list, metric_path: str) -> list:
    parts = metric_path.split(".")
    values = []
    for record in records:
        node: Any = record
        for part in parts:
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(part)
        value = to_float(node, default=float("nan"))
        if not math.isnan(value):
            values.append(value)
    return values


def group_records(records: list, group_by: str) -> dict:
    groups: dict = {}
    for record in records:
        if group_by == "setup_tags":
            for tag in (record.get("setup_tags") or ["untagged"]):
                groups.setdefault(str(tag), []).append(record)
        else:
            key = record.get(group_by) or "unknown"
            groups.setdefault(str(key), []).append(record)
    return groups


def summarize_group(records: list) -> dict:
    matured = [r for r in records if r.get("matured")]
    sample = len(matured)
    if sample == 0:
        return {"sample_size": 0, "pending": len(records), "win_rate_pct": None}

    winners = [r for r in matured if r.get("overall_outcome") in {"WORKED", "STRONG_WINNER"}]
    failures = [r for r in matured if str(r.get("overall_outcome", "")).startswith("FAILED") or r.get("overall_outcome") == "CHOPPY_FAILURE"]
    strong = [r for r in matured if r.get("overall_outcome") == "STRONG_WINNER"]
    stop = [r for r in matured if r.get("outcomes", {}).get("5d", {}).get("stop_hit")]

    ret3 = values_for_metric(matured, "outcomes.3d.forward_return_pct")
    ret5 = values_for_metric(matured, "outcomes.5d.forward_return_pct")
    mfe5 = values_for_metric(matured, "outcomes.5d.mfe_pct")
    mae5 = values_for_metric(matured, "outcomes.5d.mae_pct")

    return {
        "sample_size": sample, "pending": len(records) - sample,
        "win_rate_pct": round(len(winners) / sample * 100, 1),
        "failure_rate_pct": round(len(failures) / sample * 100, 1),
        "strong_winner_rate_pct": round(len(strong) / sample * 100, 1),
        "stop_hit_rate_pct": round(len(stop) / sample * 100, 1),
        "avg_3d_return_pct": round(statistics.fmean(ret3), 2) if ret3 else None,
        "avg_5d_return_pct": round(statistics.fmean(ret5), 2) if ret5 else None,
        "median_5d_return_pct": round(statistics.median(ret5), 2) if ret5 else None,
        "avg_5d_mfe_pct": round(statistics.fmean(mfe5), 2) if mfe5 else None,
        "avg_5d_mae_pct": round(statistics.fmean(mae5), 2) if mae5 else None,
    }


def is_promote_candidate(row: dict) -> bool:
    sample, win_rate = row.get("sample_size") or 0, row.get("win_rate_pct") or 0
    avg5, mae = row.get("avg_5d_return_pct") or 0, row.get("avg_5d_mae_pct") or 0
    return sample >= 5 and win_rate >= 60 and avg5 >= 2 and mae > -5


def is_downgrade_candidate(row: dict) -> bool:
    sample, fail_rate = row.get("sample_size") or 0, row.get("failure_rate_pct") or 0
    avg5 = row.get("avg_5d_return_pct") or 0
    return sample >= 5 and (fail_rate >= 50 or avg5 <= -1)


def summarize_model_book(records: list, group_by_fields: list, min_sample: int = 3) -> dict:
    matured = [r for r in records if r.get("matured")]
    summary: dict = {
        "schema_version": SCHEMA_VERSION, "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_records": len(records), "matured_records": len(matured), "pending_records": len(records) - len(matured),
        "overall": summarize_group(records), "groups": {}, "rule_candidates": [],
    }
    for group_by in group_by_fields:
        groups = group_records(records, group_by)
        rows = []
        for key, group in groups.items():
            stats = summarize_group(group)
            if stats.get("sample_size", 0) < min_sample:
                continue
            row = {"group": key, **stats}
            rows.append(row)
            if is_promote_candidate(row):
                summary["rule_candidates"].append({"action": "promote", "group_by": group_by, "group": key,
                    "reason": "High win rate with positive 5d expectancy and acceptable drawdown.", "evidence": row})
            elif is_downgrade_candidate(row):
                summary["rule_candidates"].append({"action": "downgrade_or_filter", "group_by": group_by, "group": key,
                    "reason": "Weak 5d expectancy or high failure rate. Review examples before changing rules.", "evidence": row})
        rows.sort(key=lambda r: (r.get("avg_5d_return_pct") if r.get("avg_5d_return_pct") is not None else -999,
                                   r.get("win_rate_pct") if r.get("win_rate_pct") is not None else -999), reverse=True)
        summary["groups"][group_by] = rows
    return summary
