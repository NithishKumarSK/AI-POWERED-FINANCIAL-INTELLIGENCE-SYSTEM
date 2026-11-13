"""
Tests for tools/cftc_cot_client.py. No real network calls -- requests.get
is monkeypatched throughout.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.cftc_cot_client import MARKET_CODES, fetch_cot_history


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else []

    def json(self):
        return self._json_data


def test_market_codes_table_has_expected_symbols():
    for sym in ("ES", "NQ", "GC", "SI", "CL", "E6", "ZB"):
        assert sym in MARKET_CODES
        assert MARKET_CODES[sym]["code"]


def test_fetch_cot_history_success(monkeypatch):
    import tools.cftc_cot_client as mod
    rows = [{"report_date_as_yyyy_mm_dd": "2026-10-27T00:00:00.000"}]
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(200, rows))
    result, err = fetch_cot_history("13874A")
    assert err == ""
    assert result == rows


def test_fetch_cot_history_http_error(monkeypatch):
    import tools.cftc_cot_client as mod
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(404, []))
    result, err = fetch_cot_history("BADCODE")
    assert result is None
    assert err == "http_404"


def test_fetch_cot_history_empty_is_an_error(monkeypatch):
    import tools.cftc_cot_client as mod
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(200, []))
    result, err = fetch_cot_history("13874A")
    assert result is None
    assert err == "no_cot_data"


def test_fetch_cot_history_network_error(monkeypatch):
    import tools.cftc_cot_client as mod
    import requests

    def _raise(*a, **k):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr(mod.requests, "get", _raise)
    result, err = fetch_cot_history("13874A")
    assert result is None
    assert "network_error" in err
