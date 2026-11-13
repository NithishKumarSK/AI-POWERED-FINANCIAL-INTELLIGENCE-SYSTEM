"""
Tests for core/macro_calendar_service.py. No real network calls --
tools.fxmacrodata_client.fetch_calendar is monkeypatched throughout.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import macro_calendar_service as svc


def _payload(events):
    return {
        "currency": "USD",
        "data_quality": {"is_official": True, "is_proxy": False, "is_fallback": False},
        "data": events,
    }


def test_invalid_as_of_date_is_an_error():
    data, err = svc.fetch_macro_event_risk("not-a-date")
    assert data is None
    assert "invalid_as_of_date" in err


def test_no_qualifying_events_returns_none_not_error(monkeypatch):
    monkeypatch.setattr(svc, "fetch_calendar", lambda **k: (_payload([]), ""))
    data, err = svc.fetch_macro_event_risk("2026-11-02", lookahead_days=7, min_tier=2)
    assert data is None
    assert err == ""


def test_fetch_error_propagates(monkeypatch):
    monkeypatch.setattr(svc, "fetch_calendar", lambda **k: (None, "http_401"))
    data, err = svc.fetch_macro_event_risk("2026-11-02")
    assert data is None
    assert err == "http_401"


def test_finds_nearest_top_tier_event_in_window(monkeypatch):
    events = [
        {"market_tier": 2, "announcement_datetime_utc": "2026-11-04T13:30:00+00:00",
         "release": "trade_balance", "name": "Trade Balance", "event_importance": "medium"},
        {"market_tier": 1, "announcement_datetime_utc": "2026-11-08T13:30:00+00:00",
         "release": "cpi", "name": "CPI", "event_importance": "high"},
        {"market_tier": 3, "announcement_datetime_utc": "2026-11-03T13:30:00+00:00",
         "release": "job_openings", "name": "JOLTS", "event_importance": "low"},
    ]
    monkeypatch.setattr(svc, "fetch_calendar", lambda **k: (_payload(events), ""))
    data, err = svc.fetch_macro_event_risk("2026-11-02", lookahead_days=10, min_tier=2)
    assert err == ""
    assert data["has_event_risk"] is True
    assert data["nearest_event_name"] == "Trade Balance"
    assert data["days_to_nearest_event"] == 2
    assert data["events_in_window"] == 2


def test_event_outside_window_excluded(monkeypatch):
    events = [
        {"market_tier": 1, "announcement_datetime_utc": "2026-12-01T13:30:00+00:00",
         "release": "cpi", "name": "CPI", "event_importance": "high"},
    ]
    monkeypatch.setattr(svc, "fetch_calendar", lambda **k: (_payload(events), ""))
    data, err = svc.fetch_macro_event_risk("2026-11-02", lookahead_days=7, min_tier=2)
    assert data is None
    assert err == ""
