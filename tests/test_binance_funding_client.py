"""
Tests for tools/binance_funding_client.py. No real network calls --
requests.get is monkeypatched throughout.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.binance_funding_client import fetch_funding_for_symbols, fetch_latest_funding


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}

    def json(self):
        return self._json_data


def test_fetch_latest_funding_success(monkeypatch):
    import tools.binance_funding_client as mod
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(200, {"lastFundingRate": "0.0001"}))
    rate, err = fetch_latest_funding("BTCUSDT")
    assert err == ""
    assert rate == 0.0001


def test_fetch_latest_funding_http_error(monkeypatch):
    import tools.binance_funding_client as mod
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(451, {}))
    rate, err = fetch_latest_funding("BTCUSDT")
    assert rate is None
    assert err == "http_451"


def test_fetch_funding_for_symbols_partial_failure(monkeypatch):
    import tools.binance_funding_client as mod

    def _fake_get(url, params=None, timeout=None):
        if params["symbol"] == "BTCUSDT":
            return _FakeResponse(200, {"lastFundingRate": "0.0002"})
        return _FakeResponse(500, {})
    monkeypatch.setattr(mod.requests, "get", _fake_get)

    funding, errors = fetch_funding_for_symbols(["BTCUSDT", "DEADUSDT"])
    assert funding == {"BTCUSDT": 0.0002}
    assert "DEADUSDT" in errors
