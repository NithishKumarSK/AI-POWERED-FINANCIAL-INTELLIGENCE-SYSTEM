"""
Tests for core/crypto_regime_service.py -- the offline snapshot path is
pure/no-network; the live path's network calls are monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import crypto_regime_service as svc


def _rising_series(n, start=100.0, daily_pct=0.01):
    out = [start]
    for _ in range(n - 1):
        out.append(out[-1] * (1 + daily_pct))
    return out


def test_fetch_from_snapshot_missing_btc_is_an_error():
    data, err = svc.fetch_crypto_regime_from_snapshot({"series": {"ETH": [1.0, 2.0]}})
    assert data == {}
    assert err == "snapshot_missing_BTC_series"


def test_fetch_from_snapshot_builds_composite():
    series = {"BTC": _rising_series(400, start=50.0, daily_pct=0.005)}
    for i in range(6):
        series[f"ALT{i}"] = _rising_series(400, start=10.0, daily_pct=0.005)
    snapshot = {
        "as_of": "2026-07-01T00:00:00Z",
        "series": series,
        "dominance_series": [55.0 + i * 0.01 for i in range(40)],
        "funding": {"BTCUSDT": 0.0001, "ETHUSDT": 0.00008},
    }
    data, err = svc.fetch_crypto_regime_from_snapshot(snapshot)
    assert err == ""
    assert data["metadata"]["mode"] == "offline"
    assert data["composite"]["zone"] in ("RISK_ON", "NEUTRAL", "RISK_OFF")
    assert "btc_trend_structure" in data["components"]


def test_record_dominance_observation_dedups_by_date(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "DOMINANCE_HISTORY_PATH", tmp_path / "dominance_history.json")
    series1 = svc._record_dominance_observation(55.0)
    series2 = svc._record_dominance_observation(56.0)
    assert series1 == [55.0]
    assert series2 == [56.0]  # same UTC day -> overwrites, not appends


def test_fetch_crypto_regime_fails_fast_on_empty_markets(monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "crypto_regime_cache.json")
    import tools.coingecko_client as cg
    monkeypatch.setattr(cg, "fetch_top_markets", lambda top_n=20: (None, "http_429"))
    data, err = svc.fetch_crypto_regime(top_n=5, use_cache=False)
    assert data == {}
    assert "top_markets" in err


def test_fetch_crypto_regime_uses_same_day_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "crypto_regime_cache.json"
    monkeypatch.setattr(svc, "CACHE_PATH", cache_path)
    import time as _time
    today = _time.strftime("%Y-%m-%d", _time.gmtime())
    svc._save_json(cache_path, {"date": today, "data": {"cached": True}, "warnings": ""})

    import tools.coingecko_client as cg

    def _should_not_be_called(*a, **k):
        raise AssertionError("should not fetch when cache is fresh")
    monkeypatch.setattr(cg, "fetch_top_markets", _should_not_be_called)

    data, warnings = svc.fetch_crypto_regime(top_n=5, use_cache=True)
    assert data == {"cached": True}
