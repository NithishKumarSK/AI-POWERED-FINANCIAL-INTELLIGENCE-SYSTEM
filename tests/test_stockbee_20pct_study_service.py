"""
Tests for core/stockbee_20pct_study_service.py -- the live orchestrator
wiring historical_price_service into the ported stockbee_20pct_study
pipeline. No real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import stockbee_20pct_study_service as svc
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "stockbee_20pct_study_cache.json")
    return svc


def _flat_bars(start_date: str, n_days: int, price=50.0):
    import datetime as _dt
    d0 = _dt.date.fromisoformat(start_date)
    out = []
    for i in range(n_days):
        d = d0 + _dt.timedelta(days=i)
        out.append({"date": d.isoformat(), "open": price, "high": price * 1.01, "low": price * 0.99, "close": price, "volume": 10_000_000})
    return out


def test_fetch_20pct_study_no_event_returns_none_not_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (_flat_bars("2026-01-01", 280), "", {}))

    data, err = svc.fetch_20pct_study("AAPL", "2026-10-30", use_cache=False)
    assert data is None
    assert err == ""


def test_fetch_20pct_study_no_price_history_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: ([], "down", {}))

    data, err = svc.fetch_20pct_study("AAPL", "2026-10-30", use_cache=False)
    assert data is None
    assert err != ""


def test_fetch_20pct_study_detects_real_event(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    bars = _flat_bars("2026-01-01", 280, price=50.0)
    bars.append({"date": "2026-10-30", "open": 55.0, "high": 63.0, "low": 54.5, "close": 62.5, "volume": 50_000_000})
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (bars, "", {}))

    data, err = svc.fetch_20pct_study("AAPL", "2026-10-30", use_cache=False)
    assert data is not None
    assert err == ""
    assert data["direction"] == "UP"


def test_second_call_reuses_cache_not_a_second_fetch(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    call_count = {"n": 0}

    def fake_fetch(sym, a, b):
        call_count["n"] += 1
        return _flat_bars("2026-01-01", 280), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    svc.fetch_20pct_study("AAPL", "2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    svc.fetch_20pct_study("AAPL", "2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls
