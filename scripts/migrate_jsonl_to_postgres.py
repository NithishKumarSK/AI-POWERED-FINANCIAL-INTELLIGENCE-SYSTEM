"""One-off migration: backfill local JSONL history into the central Postgres DB.

Reads stock_prediction_evaluation_runs.jsonl (validated) and
pending_future_predictions.jsonl (still-pending) from the repo root and
inserts them into the `stock_predictions` table. Idempotent -- safe to run
from multiple teammates' machines, since the (symbol, prediction_origin_date,
decision_horizon_days, target_date) unique constraint silently skips anything
already present, so running this twice (or from two different people's old
local files) never creates duplicates.

Historical records are attributed to a "Legacy Import" profile rather than
guessing who originally ran them -- see db/profiles.py for the attribution
model.

Run from the repo root:
    python scripts/migrate_jsonl_to_postgres.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from psycopg.types.json import Jsonb  # noqa: E402

from db.connection import get_connection  # noqa: E402
from db.profiles import get_or_create_profile_id  # noqa: E402

VALIDATED_FILE = ROOT / "stock_prediction_evaluation_runs.jsonl"
PENDING_FILE = ROOT / "pending_future_predictions.jsonl"

_LEGACY_USER = "Legacy Import"


def _date_or_none(v):
    s = str(v or "").strip()
    return s[:10] if s else None


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        print(f"  (not found, skipping: {path.name})")
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def migrate_validated(user_id: str) -> tuple[int, int]:
    records = _load_jsonl(VALIDATED_FILE)
    inserted = skipped = 0
    with get_connection() as conn:
        for r in records:
            spi = r.get("stock_prediction_input") or {}
            aip = r.get("ai_prediction") or {}
            av = r.get("actual_validation") or {}
            cmp = r.get("comparison") or {}
            symbol = str(spi.get("symbol", "") or "").upper()
            if not symbol:
                skipped += 1
                continue
            params = {
                "run_id": r.get("run_id") or "LEGACY",
                "user_id": user_id,
                "model_version": r.get("model_version", "legacy_import"),
                "symbol": symbol,
                "hist_start": _date_or_none(spi.get("historical_context_start_date")),
                "origin_date": _date_or_none(spi.get("prediction_origin_date")),
                "horizon": int(spi.get("decision_horizon_days", 30) or 30),
                "target_date": _date_or_none(spi.get("target_date")),
                "capital": spi.get("initial_capital"),
                "benchmark": spi.get("benchmark"),
                "val_mode": spi.get("validation_mode"),
                "price_basis": spi.get("price_basis"),
                "spi": Jsonb(spi),
                "input_hash": r.get("stock_prediction_input_hash", ""),
                "pred_price": aip.get("predicted_target_price"),
                "pred_ret": aip.get("predicted_return_pct"),
                "pred_cap": aip.get("predicted_final_capital"),
                "pred_pl": aip.get("predicted_total_pl"),
                "decision": aip.get("decision"),
                "conf": aip.get("confidence_score"),
                "risk": aip.get("risk_score"),
                "ai_raw": Jsonb(aip),
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
                "ts": r.get("timestamp"),
            }
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
                        created_at, resolved_at
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
                        coalesce(%(ts)s::timestamptz, now()), now()
                    )
                    on conflict (symbol, prediction_origin_date, decision_horizon_days, target_date)
                    do nothing
                    returning id
                    """,
                    params,
                )
                if cur.fetchone():
                    inserted += 1
                else:
                    skipped += 1
    return inserted, skipped


def migrate_pending(user_id: str) -> tuple[int, int]:
    records = _load_jsonl(PENDING_FILE)
    inserted = skipped = 0
    with get_connection() as conn:
        for r in records:
            symbol = str(r.get("symbol", "") or "").upper()
            if not symbol:
                skipped += 1
                continue
            # The old pending-file record's own "status" field means
            # "PENDING_VALIDATION" (this record's lifecycle state), not
            # "did the AI prediction succeed" -- dumping it verbatim into
            # ai_prediction_raw would make run_stock_validation()'s
            # ai_prediction.get("status") != "SUCCESS" gate reject every
            # migrated row. Every record that reached the old pending file
            # was, by construction, one where the AI had already succeeded,
            # so build a proper ai_prediction-shaped payload instead.
            ai_raw = {
                "status": "SUCCESS",
                "stock_prediction_input_hash": r.get("validation_input_hash", ""),
                "predicted_target_price": r.get("predicted_target_price"),
                "predicted_return_pct": r.get("predicted_return_pct"),
                "predicted_final_capital": r.get("predicted_final_capital"),
                "predicted_total_pl": r.get("predicted_total_pl"),
                "decision": r.get("ai_decision", ""),
                "confidence_score": r.get("confidence_score"),
                "risk_score": r.get("risk_score"),
                "model_version": r.get("model_version", ""),
                "origin_price_used": r.get("origin_price_used"),
                "effective_origin_date": r.get("effective_origin_date", ""),
                "data_quality_score": r.get("data_quality_score"),
                "features_used": r.get("features_used", {}),
            }
            params = {
                "run_id": "LEGACY",
                "user_id": user_id,
                "model_version": r.get("model_version", "legacy_import"),
                "symbol": symbol,
                "hist_start": _date_or_none(r.get("historical_context_start_date")),
                "origin_date": _date_or_none(r.get("prediction_origin_date")),
                "horizon": int(r.get("decision_horizon_days", 30) or 30),
                "target_date": _date_or_none(r.get("target_date")),
                "capital": r.get("initial_capital", 50000),
                "benchmark": r.get("benchmark", "SPY"),
                "val_mode": r.get("validation_mode", "horizon_days"),
                "price_basis": r.get("price_basis", "close"),
                "spi": Jsonb(r),
                "input_hash": r.get("validation_input_hash", ""),
                "pred_price": r.get("predicted_target_price"),
                "pred_ret": r.get("predicted_return_pct"),
                "pred_cap": r.get("predicted_final_capital"),
                "pred_pl": r.get("predicted_total_pl"),
                "decision": r.get("ai_decision", ""),
                "conf": r.get("confidence_score"),
                "risk": r.get("risk_score"),
                "ai_raw": Jsonb(ai_raw),
                "ts": r.get("saved_at"),
            }
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
                        status, created_at
                    ) values (
                        %(run_id)s, %(user_id)s, %(model_version)s, %(symbol)s,
                        %(hist_start)s::date, %(origin_date)s::date,
                        %(horizon)s, %(target_date)s::date, %(capital)s,
                        %(benchmark)s, %(val_mode)s, %(price_basis)s,
                        %(spi)s, %(input_hash)s,
                        %(pred_price)s, %(pred_ret)s,
                        %(pred_cap)s, %(pred_pl)s, %(decision)s,
                        %(conf)s, %(risk)s, %(ai_raw)s,
                        'pending', coalesce(%(ts)s::timestamptz, now())
                    )
                    on conflict (symbol, prediction_origin_date, decision_horizon_days, target_date)
                    do nothing
                    returning id
                    """,
                    params,
                )
                if cur.fetchone():
                    inserted += 1
                else:
                    skipped += 1
    return inserted, skipped


def main() -> int:
    user_id = get_or_create_profile_id(_LEGACY_USER)

    print(f"Migrating {VALIDATED_FILE.name} ...")
    v_ins, v_skip = migrate_validated(user_id)
    print(f"  validated: {v_ins} inserted, {v_skip} skipped (duplicate or no symbol)")

    print(f"Migrating {PENDING_FILE.name} ...")
    p_ins, p_skip = migrate_pending(user_id)
    print(f"  pending:   {p_ins} inserted, {p_skip} skipped (duplicate or no symbol)")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
