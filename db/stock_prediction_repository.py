"""Central-database replacement for stock_accuracy_engine.py + pending_predictions_engine.py.

Exposes the SAME function names/signatures those two modules used, so the
call-site diff in stock_prediction_app.py is just the import line -- see the
Phase 1 section of the plan. Record-building/validity logic is reused
unchanged from stock_accuracy_engine (pure functions, no file I/O); only the
persistence layer changes, from local JSONL files to the shared
`stock_predictions` / `run_attempts` tables in Supabase.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from db.connection import get_connection
from db.profiles import get_current_profile_id
from stock_accuracy_engine import _build_record, is_valid_stock_record, get_accuracy_summary  # noqa: F401  (re-exported)

__all__ = [
    "save_stock_prediction_record",
    "load_stock_prediction_records",
    "get_accuracy_summary",
    "save_pending_prediction",
    "load_pending_predictions",
    "count_pending_predictions",
    "get_pending_summary",
]


def _d(value: Any) -> str:
    """Normalize a DB date/datetime value back to an ISO string, '' if empty."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _date_or_none(value: Any) -> Optional[str]:
    """Empty string -> None, so date columns don't choke on ''::date."""
    s = str(value or "").strip()
    return s[:10] if s else None


def _log_attempt(
    user_id: str,
    run_id: str,
    mode: str,
    input_hash: str,
    outcome: str,
    linked_prediction_id: Optional[str] = None,
) -> None:
    """Best-effort per-user activity log. Never blocks the main save path."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into run_attempts "
                    "(user_id, run_id, mode, input_hash, outcome, linked_prediction_id) "
                    "values (%s,%s,%s,%s,%s,%s)",
                    (user_id, run_id, mode, input_hash, outcome, linked_prediction_id),
                )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════
# VALIDATED RECORDS (replaces stock_accuracy_engine.py)
# ══════════════════════════════════════════════════════════════════════════

def save_stock_prediction_record(
    spi: dict,
    ai_prediction: dict,
    actual_validation: dict,
) -> Tuple[bool, str]:
    """Save a validated stock prediction record to the central database.
    Returns (saved, message) -- same contract as the old JSONL-backed version.
    """
    record = _build_record(spi, ai_prediction, actual_validation)
    user_id = get_current_profile_id()
    run_id = record["run_id"]
    input_hash = record["stock_prediction_input_hash"]

    if not is_valid_stock_record(record):
        _log_attempt(user_id, run_id, "stock_price_validation", input_hash, "invalid")
        return False, "Record failed validation — not saved."

    aip = record["ai_prediction"]
    av = record["actual_validation"]
    cmp = record["comparison"]

    params = {
        "run_id": run_id,
        "user_id": user_id,
        "model_version": record["model_version"],
        "symbol": str(spi.get("symbol", "") or "").upper(),
        "hist_start": _date_or_none(spi.get("historical_context_start_date")),
        "origin_date": _date_or_none(spi.get("prediction_origin_date")),
        "horizon": int(spi.get("decision_horizon_days", 30) or 30),
        "target_date": _date_or_none(spi.get("target_date")),
        "capital": spi.get("initial_capital"),
        "benchmark": spi.get("benchmark"),
        "val_mode": spi.get("validation_mode"),
        "price_basis": spi.get("price_basis"),
        "spi": Jsonb(spi),
        "input_hash": input_hash,
        "pred_price": aip.get("predicted_target_price"),
        "pred_ret": aip.get("predicted_return_pct"),
        "pred_cap": aip.get("predicted_final_capital"),
        "pred_pl": aip.get("predicted_total_pl"),
        "decision": aip.get("decision"),
        "conf": aip.get("confidence_score"),
        "risk": aip.get("risk_score"),
        "ai_raw": Jsonb(ai_prediction),
        "a_origin": av.get("origin_price"),
        "a_target": av.get("target_price"),
        "eff_origin": _date_or_none(av.get("effective_origin_date")),
        "eff_target": _date_or_none(av.get("effective_target_date")),
        "a_ret": av.get("actual_return_pct"),
        "a_cap": av.get("actual_final_capital"),
        "a_pl": av.get("actual_total_pl"),
        "a_dec": av.get("actual_decision"),
        "dec_match": cmp.get("decision_match"),
        "dir_match": cmp.get("directional_match"),
        "abs_ret_err": cmp.get("abs_return_error_pct"),
        "abs_price_err": cmp.get("abs_price_error"),
        "abs_cap_err": cmp.get("abs_capital_error"),
        "cmp_raw": Jsonb(cmp),
    }

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into stock_predictions (
                    run_id, user_id, model_version, symbol,
                    historical_context_start_date, prediction_origin_date,
                    decision_horizon_days, target_date, initial_capital,
                    benchmark, validation_mode, price_basis,
                    stock_prediction_input, stock_prediction_input_hash,
                    predicted_target_price, predicted_return_pct,
                    predicted_final_capital, predicted_total_pl, decision,
                    confidence_score, risk_score, ai_prediction_raw,
                    status,
                    actual_origin_price, actual_target_price,
                    effective_origin_date, effective_target_date,
                    actual_return_pct, actual_final_capital, actual_total_pl,
                    actual_decision,
                    decision_match, directional_match, abs_return_error_pct,
                    abs_price_error, abs_capital_error, comparison_raw,
                    resolved_at
                ) values (
                    %(run_id)s, %(user_id)s, %(model_version)s, %(symbol)s,
                    %(hist_start)s::date, %(origin_date)s::date,
                    %(horizon)s, %(target_date)s::date, %(capital)s,
                    %(benchmark)s, %(val_mode)s, %(price_basis)s,
                    %(spi)s, %(input_hash)s,
                    %(pred_price)s, %(pred_ret)s,
                    %(pred_cap)s, %(pred_pl)s, %(decision)s,
                    %(conf)s, %(risk)s, %(ai_raw)s,
                    'validated',
                    %(a_origin)s, %(a_target)s,
                    %(eff_origin)s::date, %(eff_target)s::date,
                    %(a_ret)s, %(a_cap)s, %(a_pl)s,
                    %(a_dec)s,
                    %(dec_match)s, %(dir_match)s, %(abs_ret_err)s,
                    %(abs_price_err)s, %(abs_cap_err)s, %(cmp_raw)s,
                    now()
                )
                on conflict (symbol, prediction_origin_date, decision_horizon_days, target_date)
                do nothing
                returning id
                """,
                params,
            )
            row = cur.fetchone()

    if row:
        _log_attempt(user_id, run_id, "stock_price_validation", input_hash, "stored_validated", row[0])
        return True, "Record saved."

    # Someone (possibly this same user re-running) already recorded this exact
    # (symbol, origin, horizon, target) combination -- DB-level dedup, same
    # semantics as record_dedup.py's "earliest timestamp wins", just enforced
    # by the unique constraint instead of app-level dedup-on-read.
    existing_id = _find_existing_id(params["symbol"], params["origin_date"], params["horizon"], params["target_date"])
    _log_attempt(user_id, run_id, "stock_price_validation", input_hash, "duplicate_ignored", existing_id)
    return True, "Already recorded previously (duplicate skipped)."


def _find_existing_id(symbol: str, origin_date: Optional[str], horizon: int, target_date: Optional[str]) -> Optional[str]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select id from stock_predictions where symbol=%s and prediction_origin_date=%s::date "
                    "and decision_horizon_days=%s and target_date=%s::date",
                    (symbol, origin_date, horizon, target_date),
                )
                row = cur.fetchone()
                return str(row[0]) if row else None
    except Exception:
        return None


def _row_to_jsonl_record(row: Dict[str, Any]) -> dict:
    """Reconstruct the old nested JSONL record shape from a DB row, so
    downstream code (get_accuracy_summary, _render_records, Gemini's
    build_calibration_summary) keeps working unchanged."""
    return {
        "timestamp": _d(row.get("created_at")),
        "run_id": row.get("run_id"),
        "source": "stock_prediction_validation",
        "model_version": row.get("model_version"),
        "stock_prediction_input": row.get("stock_prediction_input") or {},
        "stock_prediction_input_hash": row.get("stock_prediction_input_hash"),
        "ai_prediction": {
            "predicted_target_price": row.get("predicted_target_price"),
            "predicted_return_pct": row.get("predicted_return_pct"),
            "predicted_final_capital": row.get("predicted_final_capital"),
            "predicted_total_pl": row.get("predicted_total_pl"),
            "decision": row.get("decision"),
            "confidence_score": row.get("confidence_score"),
            "risk_score": row.get("risk_score"),
        },
        "actual_validation": {
            "origin_price": row.get("actual_origin_price"),
            "target_price": row.get("actual_target_price"),
            "effective_origin_date": _d(row.get("effective_origin_date")),
            "effective_target_date": _d(row.get("effective_target_date")),
            "actual_return_pct": row.get("actual_return_pct"),
            "actual_final_capital": row.get("actual_final_capital"),
            "actual_total_pl": row.get("actual_total_pl"),
            "actual_decision": row.get("actual_decision"),
        },
        "comparison": row.get("comparison_raw") or {},
    }


def load_stock_prediction_records(limit: int = 200) -> List[dict]:
    """Load recent validated records from the central DB, newest first."""
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select * from stock_predictions where status = 'validated' "
                "order by created_at desc limit %s",
                (limit,),
            )
            rows = cur.fetchall()
    return [_row_to_jsonl_record(r) for r in rows]


# get_accuracy_summary is re-exported unchanged from stock_accuracy_engine --
# it's pure logic operating on the list of dicts above, no file I/O.


# ══════════════════════════════════════════════════════════════════════════
# PENDING PREDICTIONS (replaces pending_predictions_engine.py)
# ══════════════════════════════════════════════════════════════════════════

def save_pending_prediction(spi: dict, ai_result: dict) -> Tuple[bool, str]:
    """Save a live future prediction (target_date in the future) to the
    central DB with status='pending'. Resolved later by db.resolver."""
    user_id = get_current_profile_id()
    run_id = str(uuid.uuid4())[:8].upper()
    input_hash = str(ai_result.get("stock_prediction_input_hash", "") or "")

    params = {
        "run_id": run_id,
        "user_id": user_id,
        "model_version": ai_result.get("model_version", ""),
        "symbol": str(spi.get("symbol", "") or "").upper(),
        "hist_start": _date_or_none(spi.get("historical_context_start_date")),
        "origin_date": _date_or_none(spi.get("prediction_origin_date")),
        "horizon": int(spi.get("decision_horizon_days", 30) or 30),
        "target_date": _date_or_none(spi.get("target_date")),
        "capital": spi.get("initial_capital", 50000),
        "benchmark": spi.get("benchmark", "SPY"),
        "val_mode": spi.get("validation_mode", "horizon_days"),
        "price_basis": spi.get("price_basis", "close"),
        "spi": Jsonb(spi),
        "input_hash": input_hash,
        "pred_price": ai_result.get("predicted_target_price"),
        "pred_ret": ai_result.get("predicted_return_pct"),
        "pred_cap": ai_result.get("predicted_final_capital"),
        "pred_pl": ai_result.get("predicted_total_pl"),
        "decision": ai_result.get("decision", ""),
        "conf": ai_result.get("confidence_score"),
        "risk": ai_result.get("risk_score"),
        "ai_raw": Jsonb(ai_result),
    }

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into stock_predictions (
                        run_id, user_id, model_version, symbol,
                        historical_context_start_date, prediction_origin_date,
                        decision_horizon_days, target_date, initial_capital,
                        benchmark, validation_mode, price_basis,
                        stock_prediction_input, stock_prediction_input_hash,
                        predicted_target_price, predicted_return_pct,
                        predicted_final_capital, predicted_total_pl, decision,
                        confidence_score, risk_score, ai_prediction_raw,
                        status
                    ) values (
                        %(run_id)s, %(user_id)s, %(model_version)s, %(symbol)s,
                        %(hist_start)s::date, %(origin_date)s::date,
                        %(horizon)s, %(target_date)s::date, %(capital)s,
                        %(benchmark)s, %(val_mode)s, %(price_basis)s,
                        %(spi)s, %(input_hash)s,
                        %(pred_price)s, %(pred_ret)s,
                        %(pred_cap)s, %(pred_pl)s, %(decision)s,
                        %(conf)s, %(risk)s, %(ai_raw)s,
                        'pending'
                    )
                    on conflict (symbol, prediction_origin_date, decision_horizon_days, target_date)
                    do nothing
                    returning id
                    """,
                    params,
                )
                row = cur.fetchone()
    except Exception as exc:
        return False, f"Failed to save pending prediction: {exc}"

    if row:
        _log_attempt(user_id, run_id, "stock_price_validation", input_hash, "stored_pending", row[0])
        return True, "Pending prediction saved."

    existing_id = _find_existing_id(params["symbol"], params["origin_date"], params["horizon"], params["target_date"])
    _log_attempt(user_id, run_id, "stock_price_validation", input_hash, "duplicate_ignored", existing_id)
    return True, "Already recorded as pending previously (duplicate skipped)."


def _row_to_pending_record(row: Dict[str, Any]) -> dict:
    ai_raw = row.get("ai_prediction_raw") or {}
    return {
        "record_type": "pending_future_prediction",
        "status": "PENDING_VALIDATION",
        "saved_at": _d(row.get("created_at")),
        "symbol": row.get("symbol"),
        "historical_context_start_date": _d(row.get("historical_context_start_date")),
        "prediction_origin_date": _d(row.get("prediction_origin_date")),
        "effective_origin_date": ai_raw.get("effective_origin_date", ""),
        "target_date": _d(row.get("target_date")),
        "decision_horizon_days": row.get("decision_horizon_days"),
        "initial_capital": row.get("initial_capital"),
        "price_basis": row.get("price_basis"),
        "benchmark": row.get("benchmark"),
        "validation_mode": row.get("validation_mode"),
        "ai_decision": row.get("decision"),
        "origin_price_used": ai_raw.get("origin_price_used"),
        "predicted_target_price": row.get("predicted_target_price"),
        "predicted_return_pct": row.get("predicted_return_pct"),
        "predicted_final_capital": row.get("predicted_final_capital"),
        "predicted_total_pl": row.get("predicted_total_pl"),
        "confidence_score": row.get("confidence_score"),
        "risk_score": row.get("risk_score"),
        "data_quality_score": ai_raw.get("data_quality_score"),
        "model_version": row.get("model_version"),
        "validation_input_hash": row.get("stock_prediction_input_hash"),
        "features_used": ai_raw.get("features_used", {}),
    }


def load_pending_predictions() -> List[Dict]:
    """Load all pending/resolving records from the central DB."""
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select * from stock_predictions where status in ('pending','resolving') "
                "order by target_date asc"
            )
            rows = cur.fetchall()
    return [_row_to_pending_record(r) for r in rows]


def count_pending_predictions() -> int:
    """Return number of records still waiting for validation."""
    records = load_pending_predictions()
    return sum(1 for r in records if r.get("status") == "PENDING_VALIDATION")


def get_pending_summary() -> Dict[str, Any]:
    """Summary of pending predictions for the accuracy section."""
    records = load_pending_predictions()
    pending = [r for r in records if r.get("status") == "PENDING_VALIDATION"]
    return {
        "total_pending": len(pending),
        "symbols": list({r["symbol"] for r in pending if r.get("symbol")}),
        "earliest_target": min((r["target_date"] for r in pending if r.get("target_date")), default=""),
        "latest_target": max((r["target_date"] for r in pending if r.get("target_date")), default=""),
    }
