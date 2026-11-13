"""
Tests for core/weekly_performance_digest_service.py. DB access
(db.stock_prediction_repository.load_stock_prediction_records) is
monkeypatched throughout -- no real database connection.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import weekly_performance_digest_service as svc


def _record(symbol, target_date, pnl=10.0):
    return {
        "timestamp": "2026-06-15T10:00:00Z",
        "stock_prediction_input": {"symbol": symbol, "decision_horizon_days": 30},
        "ai_prediction": {"decision": "BUY"},
        "actual_validation": {"actual_total_pl": pnl, "effective_target_date": target_date},
        "comparison": {"decision_match": True, "directional_match": True},
    }


def test_invalid_to_date_is_an_error():
    data, err = svc.fetch_weekly_digest(to_date="not-a-date")
    assert data is None
    assert "invalid_to_date" in err


def test_invalid_from_date_is_an_error():
    data, err = svc.fetch_weekly_digest(to_date="2026-06-20", from_date="bogus")
    assert data is None
    assert "invalid_from_date" in err


def test_db_failure_is_an_error_not_a_crash(monkeypatch):
    import db.stock_prediction_repository as repo

    def _raise(*a, **k):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(repo, "load_stock_prediction_records", _raise)
    data, err = svc.fetch_weekly_digest(to_date="2026-06-20", from_date="2026-06-13")
    assert data is None
    assert "db_load_failed" in err


def test_fetch_weekly_digest_filters_and_builds(monkeypatch):
    import db.stock_prediction_repository as repo
    records = [
        _record("AAPL", "2026-06-14"),
        _record("MSFT", "2026-07-01"),
    ]
    monkeypatch.setattr(repo, "load_stock_prediction_records", lambda limit=500, user_id=None: records)
    data, err = svc.fetch_weekly_digest(to_date="2026-06-20", from_date="2026-06-13")
    assert err == ""
    assert data["summary"]["total_trades"] == 1


def test_fetch_weekly_digest_default_window_is_trailing_7_days(monkeypatch):
    import db.stock_prediction_repository as repo
    monkeypatch.setattr(repo, "load_stock_prediction_records", lambda limit=500, user_id=None: [])
    data, err = svc.fetch_weekly_digest()
    assert err == ""
    assert data["summary"]["total_trades"] == 0
