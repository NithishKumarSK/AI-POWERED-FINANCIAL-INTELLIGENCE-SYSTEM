"""The missing pending -> resolved loop (see the plan's "Key gap found").

No code anywhere previously re-checked a pending prediction once its
target_date arrived. This module closes that loop: it claims due 'pending'
rows, fetches the now-known actual prices, re-runs the same validation
pipeline the live app already uses synchronously for near-term predictions,
and writes the outcome back as 'validated' or 'invalid' -- so every
prediction eventually lands in the shared, central accuracy ledger.

Safe to call from multiple teammates' machines concurrently (claims rows
with FOR UPDATE SKIP LOCKED) and safe to re-run repeatedly (stuck
'resolving' rows older than 1 hour are reclaimed automatically).
"""
from __future__ import annotations

import traceback
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from db.connection import get_connection
from historical_price_service import fetch_price_history
from stock_walkforward_validator import run_stock_validation
from stock_accuracy_engine import _build_record, is_valid_stock_record

_STUCK_RESOLVING_MINUTES = 60
_CLAIM_BATCH_SIZE = 200


def _reset_stuck_rows() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update stock_predictions set status='pending', updated_at=now() "
                "where status='resolving' and updated_at < now() - interval '%s minutes'"
                % _STUCK_RESOLVING_MINUTES
            )


def _claim_candidates() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                with claimed as (
                    select id from stock_predictions
                    where status = 'pending' and target_date <= current_date
                    order by target_date
                    for update skip locked
                    limit %s
                )
                update stock_predictions sp
                set status = 'resolving', updated_at = now()
                from claimed
                where sp.id = claimed.id
                returning sp.*
                """,
                (_CLAIM_BATCH_SIZE,),
            )
            return cur.fetchall()


def _days_needed(spi: dict) -> int:
    try:
        ctx_start = str(spi.get("historical_context_start_date", "") or "")
        if ctx_start:
            ctx_dt = datetime.strptime(ctx_start[:10], "%Y-%m-%d").date()
            return max(400, (date.today() - ctx_dt).days + 60)
    except Exception:
        pass
    return 500


def _revert_to_pending(row_id: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update stock_predictions set status='pending', updated_at=now() where id=%s",
                (row_id,),
            )


def _mark_invalid(row_id: str, reason: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update stock_predictions set status='invalid', validity_reason=%s, "
                "resolved_at=now(), updated_at=now() where id=%s",
                (reason, row_id),
            )


def _mark_validated(row_id: str, av: dict, cmp: dict) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                update stock_predictions set
                    status = 'validated',
                    actual_origin_price = %(a_origin)s,
                    actual_target_price = %(a_target)s,
                    effective_origin_date = %(eff_origin)s::date,
                    effective_target_date = %(eff_target)s::date,
                    actual_return_pct = %(a_ret)s,
                    actual_final_capital = %(a_cap)s,
                    actual_total_pl = %(a_pl)s,
                    actual_decision = %(a_dec)s,
                    decision_match = %(dec_match)s,
                    directional_match = %(dir_match)s,
                    abs_return_error_pct = %(abs_ret_err)s,
                    abs_price_error = %(abs_price_err)s,
                    abs_capital_error = %(abs_cap_err)s,
                    comparison_raw = %(cmp_raw)s,
                    resolved_at = now(),
                    updated_at = now()
                where id = %(id)s
                """,
                {
                    "id": row_id,
                    "a_origin": av.get("origin_price"),
                    "a_target": av.get("target_price"),
                    "eff_origin": (av.get("effective_origin_date") or "")[:10] or None,
                    "eff_target": (av.get("effective_target_date") or "")[:10] or None,
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
                },
            )


def _log_resolver_run(started_at, candidates, resolved, invalid, skipped, error) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into resolver_runs (started_at, finished_at, candidates_count, "
                "resolved_count, invalid_count, skipped_count, error) "
                "values (%s, now(), %s, %s, %s, %s, %s)",
                (started_at, candidates, resolved, invalid, skipped, error),
            )


def resolve_pending_predictions() -> Dict[str, int]:
    """Claim and resolve all due pending predictions. Returns summary counts."""
    started_at = datetime.utcnow()
    resolved = invalid = skipped = 0
    top_level_error = None

    try:
        _reset_stuck_rows()
        rows = _claim_candidates()

        by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_symbol[row["symbol"]].append(row)

        for symbol, symbol_rows in by_symbol.items():
            max_days = max(_days_needed(r["stock_prediction_input"] or {}) for r in symbol_rows)
            history, hist_err = fetch_price_history(symbol, min_days=max_days)

            for row in symbol_rows:
                spi = row["stock_prediction_input"] or {}
                ai_prediction = row["ai_prediction_raw"] or {}

                if not history:
                    _revert_to_pending(row["id"])
                    skipped += 1
                    continue

                actual_validation = run_stock_validation(spi, ai_prediction, history)
                if actual_validation.get("status") != "SUCCESS":
                    # Target date data not available yet (provider lag / non-trading
                    # day) -- leave pending, retry on the next resolver pass.
                    _revert_to_pending(row["id"])
                    skipped += 1
                    continue

                record = _build_record(spi, ai_prediction, actual_validation)
                if is_valid_stock_record(record):
                    _mark_validated(row["id"], record["actual_validation"], record["comparison"])
                    resolved += 1
                else:
                    _mark_invalid(row["id"], "Resolved but failed the accuracy-ledger validity gate.")
                    invalid += 1

    except Exception:
        top_level_error = traceback.format_exc()[:4000]

    _log_resolver_run(started_at, resolved + invalid + skipped, resolved, invalid, skipped, top_level_error)
    return {
        "candidates": resolved + invalid + skipped,
        "resolved": resolved,
        "invalid": invalid,
        "skipped": skipped,
        "error": top_level_error,
    }
