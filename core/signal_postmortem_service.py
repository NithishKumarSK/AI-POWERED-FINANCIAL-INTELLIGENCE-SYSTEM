"""
Live orchestrator for core/signal_postmortem.py -- loads validated
prediction records from the central DB (reusing
db.stock_prediction_repository.load_stock_prediction_records, no new
query) and macro_regime_service.compute_macro_regime (already disk-
cached by date) to get the regime label at signal time and at exit
time for each record, then classifies outcomes.

Standalone reporting tool, like weekly_performance_digest_service.py --
not wired into feature_packet.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Tuple

from signal_postmortem import build_signal_postmortem
from weekly_performance_digest import select_records_in_window


def _get_path(record: Dict[str, Any], *path: str) -> Any:
    node: Any = record
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _regime_label(as_of_date: Optional[str]) -> Optional[str]:
    if not as_of_date:
        return None
    try:
        from macro_regime_service import compute_macro_regime
        data, err = compute_macro_regime(as_of_date)
        if err or not data:
            return None
        return data.get("regime_label")
    except Exception:
        return None


def fetch_signal_postmortem(
    to_date: Optional[str] = None,
    from_date: Optional[str] = None,
    limit: int = 500,
    user_id: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Build a signal postmortem for [from_date, to_date] (default: trailing 30 days).

    Returns (data, error_string). Never raises.
    """
    try:
        to_d = _dt.date.fromisoformat(to_date) if to_date else _dt.date.today()
    except ValueError:
        return None, f"invalid_to_date:{to_date}"
    try:
        from_d = _dt.date.fromisoformat(from_date) if from_date else (to_d - _dt.timedelta(days=30))
    except ValueError:
        return None, f"invalid_from_date:{from_date}"

    try:
        from db.stock_prediction_repository import load_stock_prediction_records
        records = load_stock_prediction_records(limit=limit, user_id=user_id)
    except Exception as exc:
        return None, f"db_load_failed: {type(exc).__name__}: {exc}"

    windowed = select_records_in_window(records, from_d.isoformat(), to_d.isoformat())

    entries: List[Dict[str, Any]] = []
    for rec in windowed:
        symbol = _get_path(rec, "stock_prediction_input", "symbol")
        decision = _get_path(rec, "ai_prediction", "decision")
        realized_return_pct = _get_path(rec, "actual_validation", "actual_return_pct")
        origin_date = _get_path(rec, "actual_validation", "effective_origin_date")
        exit_date = _get_path(rec, "actual_validation", "effective_target_date")

        regime_at_signal = _regime_label(origin_date)
        regime_at_exit = _regime_label(exit_date)
        regime_changed = bool(
            regime_at_signal and regime_at_exit and regime_at_signal != regime_at_exit
        )

        entries.append({
            "symbol": symbol,
            "decision": decision,
            "realized_return_pct": realized_return_pct,
            "regime_at_signal": regime_at_signal,
            "regime_at_exit": regime_at_exit,
            "regime_changed": regime_changed,
        })

    return build_signal_postmortem(entries), ""
