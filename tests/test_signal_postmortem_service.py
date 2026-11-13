"""
Tests for core/signal_postmortem_service.py. DB access and
macro_regime_service.compute_macro_regime are monkeypatched throughout --
no real database connection or network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import signal_postmortem_service as svc


def _record(symbol, decision, realized_return_pct, target_date, origin_date="2026-06-01"):
    return {
        "timestamp": "2026-06-15T10:00:00Z",
        "stock_prediction_input": {"symbol": symbol, "decision_horizon_days": 30},
        "ai_prediction": {"decision": decision},
        "actual_validation": {
            "actual_return_pct": realized_return_pct,
            "effective_origin_date": origin_date,
            "effective_target_date": target_date,
        },
        "comparison": {},
    }


def test_invalid_to_date_is_an_error():
    data, err = svc.fetch_signal_postmortem(to_date="not-a-date")
    assert data is None
    assert "invalid_to_date" in err


def test_db_failure_is_an_error_not_a_crash(monkeypatch):
    import db.stock_prediction_repository as repo

    def _raise(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(repo, "load_stock_prediction_records", _raise)
    data, err = svc.fetch_signal_postmortem(to_date="2026-06-20", from_date="2026-06-13")
    assert data is None
    assert "db_load_failed" in err


def test_fetch_signal_postmortem_classifies_with_regime_lookup(monkeypatch):
    import db.stock_prediction_repository as repo
    records = [_record("AAPL", "BUY", 5.0, "2026-06-14")]
    monkeypatch.setattr(repo, "load_stock_prediction_records", lambda limit=500, user_id=None: records)
    monkeypatch.setattr(svc, "_regime_label", lambda d: "RISK_ON" if d else None)

    data, err = svc.fetch_signal_postmortem(to_date="2026-06-20", from_date="2026-06-13")
    assert err == ""
    assert data["overall"]["total"] == 1
    assert data["overall"]["TRUE_POSITIVE"] == 1


def test_fetch_signal_postmortem_detects_regime_change(monkeypatch):
    import db.stock_prediction_repository as repo
    records = [_record("AAPL", "BUY", -5.0, "2026-06-14")]
    monkeypatch.setattr(repo, "load_stock_prediction_records", lambda limit=500, user_id=None: records)

    labels = {"2026-06-01": "RISK_ON", "2026-06-14": "RISK_OFF"}
    monkeypatch.setattr(svc, "_regime_label", lambda d: labels.get(d))

    data, err = svc.fetch_signal_postmortem(to_date="2026-06-20", from_date="2026-06-13")
    assert err == ""
    assert data["overall"]["REGIME_MISMATCH"] == 1


def test_regime_label_handles_missing_date_and_errors(monkeypatch):
    import macro_regime_service as mrs
    assert svc._regime_label(None) is None

    def _raise(as_of_date):
        raise RuntimeError("network down")
    monkeypatch.setattr(mrs, "compute_macro_regime", _raise)
    assert svc._regime_label("2026-06-14") is None
