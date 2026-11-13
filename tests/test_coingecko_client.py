"""
Tests for tools/coingecko_client.py. No real network calls --
requests.get is monkeypatched throughout.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.coingecko_client import fetch_btc_dominance, fetch_market_chart_daily, fetch_top_markets


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}

    def json(self):
        return self._json_data


def test_fetch_top_markets_excludes_stablecoins(monkeypatch):
    import tools.coingecko_client as mod
    coins = [
        {"id": "bitcoin", "symbol": "btc"},
        {"id": "tether", "symbol": "usdt"},
        {"id": "ethereum", "symbol": "eth"},
    ]
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(200, coins))
    result, err = fetch_top_markets(top_n=10)
    assert err == ""
    symbols = {c["symbol"] for c in result}
    assert symbols == {"btc", "eth"}


def test_fetch_top_markets_http_error(monkeypatch):
    import tools.coingecko_client as mod
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(429, {}))
    result, err = fetch_top_markets()
    assert result is None
    assert err == "http_429"


def test_fetch_market_chart_daily_success(monkeypatch):
    import tools.coingecko_client as mod
    payload = {"prices": [[1000, 50.0], [2000, 51.0], [3000, 52.0]]}
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(200, payload))
    closes, err = fetch_market_chart_daily("bitcoin")
    assert err == ""
    assert closes == [50.0, 51.0, 52.0]


def test_fetch_market_chart_daily_no_data(monkeypatch):
    import tools.coingecko_client as mod
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(200, {"prices": []}))
    closes, err = fetch_market_chart_daily("bitcoin")
    assert closes is None
    assert err == "no_price_data"


def test_fetch_btc_dominance_success(monkeypatch):
    import tools.coingecko_client as mod
    payload = {"data": {"market_cap_percentage": {"btc": 56.3, "eth": 12.1}}}
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(200, payload))
    pct, err = fetch_btc_dominance()
    assert err == ""
    assert pct == 56.3


def test_fetch_btc_dominance_network_error(monkeypatch):
    import tools.coingecko_client as mod
    import requests

    def _raise(*a, **k):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr(mod.requests, "get", _raise)
    pct, err = fetch_btc_dominance()
    assert pct is None
    assert "network_error" in err
