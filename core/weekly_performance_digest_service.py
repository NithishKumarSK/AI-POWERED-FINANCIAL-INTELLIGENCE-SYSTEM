"""
Live orchestrator for core/weekly_performance_digest.py -- loads recent
validated prediction records from the central DB (reusing
db.stock_prediction_repository.load_stock_prediction_records, no new
query), filters to the requested date window, and produces the digest.

Standalone/reporting tool, like core/portfolio_tools/ -- not wired into
feature_packet, since a weekly digest over past predictions has nothing
to contribute to a single new prediction's inputs.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Optional, Tuple

from weekly_performance_digest import build_weekly_digest, select_records_in_window


def fetch_weekly_digest(
    to_date: Optional[str] = None,
    from_date: Optional[str] = None,
    limit: int = 500,
    user_id: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Build a weekly digest for [from_date, to_date] (default: trailing 7 days).

    Returns (data, error_string). Never raises -- a DB outage degrades to
    an honest error, not a crash, matching every other *_service.py in
    this project.
    """
    try:
        to_d = _dt.date.fromisoformat(to_date) if to_date else _dt.date.today()
    except ValueError:
        return None, f"invalid_to_date:{to_date}"
    try:
        from_d = _dt.date.fromisoformat(from_date) if from_date else (to_d - _dt.timedelta(days=7))
    except ValueError:
        return None, f"invalid_from_date:{from_date}"

    try:
        from db.stock_prediction_repository import load_stock_prediction_records
        records = load_stock_prediction_records(limit=limit, user_id=user_id)
    except Exception as exc:
        return None, f"db_load_failed: {type(exc).__name__}: {exc}"

    windowed = select_records_in_window(records, from_d.isoformat(), to_d.isoformat())
    digest = build_weekly_digest(windowed, from_d.isoformat(), to_d.isoformat())
    return digest, ""
