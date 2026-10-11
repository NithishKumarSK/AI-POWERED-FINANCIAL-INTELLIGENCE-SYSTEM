"""
One-off backfill: recompute actual_decision / decision_match / directional_match
for already-validated stock_predictions rows using the new horizon-scaled
decision threshold (stock_comparison_engine.decision_thresholds_for_horizon),
replacing the old flat ±2% band those rows were originally labeled under.

Pure math only -- reads actual_return_pct, predicted_return_pct, decision,
decision_horizon_days already stored on each row; makes no new API/price calls.

Usage:
    python scripts/adhoc/backfill_horizon_thresholds.py            # dry run, prints a diff summary
    python scripts/adhoc/backfill_horizon_thresholds.py --apply    # writes the recomputed columns
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_paths
bootstrap_paths.add_module_paths()

from db.connection import get_connection
from stock_comparison_engine import decision_thresholds_for_horizon


def _directional_match(ai_ret: float, actual_ret: float, horizon_days: int) -> bool:
    buy_th, _ = decision_thresholds_for_horizon(horizon_days)
    return (
        (ai_ret > 0 and actual_ret > 0)
        or (ai_ret < 0 and actual_ret < 0)
        or (abs(ai_ret) <= buy_th and abs(actual_ret) <= buy_th)
    )


def main() -> None:
    apply = "--apply" in sys.argv

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, decision, predicted_return_pct, actual_return_pct,
                       decision_horizon_days, actual_decision, decision_match, directional_match
                FROM stock_predictions
                WHERE status = 'validated'
                  AND actual_return_pct IS NOT NULL
                  AND predicted_return_pct IS NOT NULL
            """)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    print(f"Validated rows with actual/predicted return present: {len(rows)}")

    changed = []
    for r in rows:
        horizon = int(r["decision_horizon_days"] or 7)
        actual_ret = float(r["actual_return_pct"])
        ai_ret = float(r["predicted_return_pct"])
        ai_decision = r["decision"]

        buy_th, sell_th = decision_thresholds_for_horizon(horizon)
        if actual_ret > buy_th:
            new_actual_decision = "BUY"
        elif actual_ret < sell_th:
            new_actual_decision = "SELL"
        else:
            new_actual_decision = "HOLD"

        new_decision_match = (ai_decision == new_actual_decision)
        new_directional_match = _directional_match(ai_ret, actual_ret, horizon)

        old_actual_decision = r["actual_decision"]
        old_decision_match = r["decision_match"]
        old_directional_match = r["directional_match"]

        if (
            new_actual_decision != old_actual_decision
            or new_decision_match != old_decision_match
            or new_directional_match != old_directional_match
        ):
            changed.append({
                "id": r["id"],
                "horizon": horizon,
                "actual_return_pct": actual_ret,
                "old_actual_decision": old_actual_decision,
                "new_actual_decision": new_actual_decision,
                "old_decision_match": old_decision_match,
                "new_decision_match": new_decision_match,
                "old_directional_match": old_directional_match,
                "new_directional_match": new_directional_match,
            })

    print(f"Rows whose labels change under the horizon-scaled threshold: {len(changed)}")
    for c in changed[:20]:
        print(
            f"  id={c['id']} horizon={c['horizon']}d actual_ret={c['actual_return_pct']:+.2f}% "
            f"actual_decision: {c['old_actual_decision']} -> {c['new_actual_decision']}  "
            f"decision_match: {c['old_decision_match']} -> {c['new_decision_match']}  "
            f"directional_match: {c['old_directional_match']} -> {c['new_directional_match']}"
        )
    if len(changed) > 20:
        print(f"  ... and {len(changed) - 20} more")

    old_dm_rate = sum(1 for r in rows if r["decision_match"]) / len(rows) * 100 if rows else 0
    old_drm_rate = sum(1 for r in rows if r["directional_match"]) / len(rows) * 100 if rows else 0
    new_dm_count = sum(
        1 for r in rows
        if next((c["new_decision_match"] for c in changed if c["id"] == r["id"]), r["decision_match"])
    )
    new_drm_count = sum(
        1 for r in rows
        if next((c["new_directional_match"] for c in changed if c["id"] == r["id"]), r["directional_match"])
    )
    print(f"\ndecision_match:    {old_dm_rate:.1f}% -> {new_dm_count / len(rows) * 100:.1f}%" if rows else "")
    print(f"directional_match: {old_drm_rate:.1f}% -> {new_drm_count / len(rows) * 100:.1f}%" if rows else "")

    if not apply:
        print("\nDry run only -- no rows written. Re-run with --apply to write these changes.")
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            for c in changed:
                cur.execute(
                    """
                    UPDATE stock_predictions
                    SET actual_decision = %s, decision_match = %s, directional_match = %s,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (c["new_actual_decision"], c["new_decision_match"], c["new_directional_match"], c["id"]),
                )
        conn.commit()
    print(f"\nApplied: {len(changed)} row(s) updated.")


if __name__ == "__main__":
    main()
