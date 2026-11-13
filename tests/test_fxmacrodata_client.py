"""
Tests for tools/fxmacrodata_client.py. No real network calls --
requests.get is monkeypatched throughout.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.fxmacrodata_client import fetch_calendar, filter_top_tier_events


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


def _good_payload(currency="USD", events=None):
    return {
        "currency": currency,
        "data_quality": {"is_official": True, "is_proxy": False, "is_fallback": False},
        "data": events if events is not None else [],
    }


def test_fetch_calendar_rejects_unsupported_currency():
    data, err = fetch_calendar(currency="xyz")
    assert data is None
    assert "unsupported_currency" in err


def test_fetch_calendar_success(monkeypatch):
    import tools.fxmacrodata_client as mod
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(200, _good_payload()))
    data, err = fetch_calendar(currency="usd")
    assert err == ""
    assert data["currency"] == "USD"


def test_fetch_calendar_http_error(monkeypatch):
    import tools.fxmacrodata_client as mod
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(401, {}))
    data, err = fetch_calendar(currency="usd")
    assert data is None
    assert err == "http_401"


def test_fetch_calendar_currency_mismatch(monkeypatch):
    import tools.fxmacrodata_client as mod
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(200, _good_payload(currency="EUR")))
    data, err = fetch_calendar(currency="usd")
    assert data is None
    assert err == "currency_mismatch"


def test_fetch_calendar_rejects_proxy_source(monkeypatch):
    import tools.fxmacrodata_client as mod
    payload = _good_payload()
    payload["data_quality"]["is_proxy"] = True
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(200, payload))
    data, err = fetch_calendar(currency="usd")
    assert data is None
    assert err == "data_quality_proxy_or_fallback"


def test_fetch_calendar_rejects_non_official(monkeypatch):
    import tools.fxmacrodata_client as mod
    payload = _good_payload()
    payload["data_quality"]["is_official"] = False
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(200, payload))
    data, err = fetch_calendar(currency="usd")
    assert data is None
    assert err == "data_quality_not_official"


def test_fetch_calendar_network_error(monkeypatch):
    import tools.fxmacrodata_client as mod
    import requests

    def _raise(*a, **k):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr(mod.requests, "get", _raise)
    data, err = fetch_calendar(currency="usd")
    assert data is None
    assert "network_error" in err


def test_filter_top_tier_events_drops_low_tier_and_malformed():
    payload = _good_payload(events=[
        {"market_tier": 1, "announcement_datetime_utc": "2026-11-05T13:30:00+00:00", "release": "cpi"},
        {"market_tier": 3, "announcement_datetime_utc": "2026-11-06T13:30:00+00:00", "release": "job_openings"},
        {"market_tier": 2, "announcement_datetime_utc": "", "release": "gdp"},
        {"market_tier": None, "announcement_datetime_utc": "2026-11-07T13:30:00+00:00", "release": "ppi"},
    ])
    result = filter_top_tier_events(payload, min_tier=2)
    assert len(result) == 1
    assert result[0]["release"] == "cpi"


def test_filter_top_tier_events_empty_data():
    assert filter_top_tier_events(_good_payload(events=[]), min_tier=2) == []
