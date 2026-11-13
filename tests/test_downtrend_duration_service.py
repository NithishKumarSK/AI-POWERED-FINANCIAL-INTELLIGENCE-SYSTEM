"""
Tests for core/downtrend_duration_service.py -- the live per-symbol
orchestrator. No real network calls; historical_price_service.fetch_price_history_for_range
is monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import downtrend_duration_service as svc
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "downtrend_duration_cache.json")
    return svc


def _wavy_bars(n_days: int, start_date: str):
    """Chronological bars that oscillate enough to produce real downtrends."""
    import datetime as _dt
    import math
    d0 = _dt.date.fromisoformat(start_date)
    out = []
    for i in range(n_days):
        d = d0 + _dt.timedelta(days=i)
        price = 100.0 + 20.0 * math.sin(i / 15.0)
        out.append({"date": d.isoformat(), "close": price, "open": price, "high": price, "low": price, "volume": 1000})
    return out


def test_fetch_downtrend_stats_with_sufficient_wavy_history(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    def fake_fetch(symbol, start, end):
        return _wavy_bars(500, "2025-01-01"), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = svc.fetch_downtrend_stats("AAPL", "2026-10-30", use_cache=False)
    assert data is not None
    assert err == ""
    assert data["total_downtrends"] > 0
    assert data["median_duration_days"] > 0


def test_fetch_downtrend_stats_insufficient_history_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    def fake_fetch(symbol, start, end):
        return _wavy_bars(10, "2026-10-01"), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = svc.fetch_downtrend_stats("AAPL", "2026-10-30", use_cache=False)
    assert data is None
    assert "Insufficient history" in err


def test_fetch_downtrend_stats_no_data_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda s, a, b: ([], "down", {}))

    data, err = svc.fetch_downtrend_stats("AAPL", "2026-10-30", use_cache=False)
    assert data is None
    assert err != ""


def test_leakage_safety_future_bars_excluded(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    def fake_fetch(symbol, start, end):
        bars = _wavy_bars(500, "2025-01-01")
        bars += [{"date": "2099-01-01", "close": 99999.0, "open": 99999.0, "high": 99999.0, "low": 99999.0, "volume": 1}]
        return bars, "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = svc.fetch_downtrend_stats("AAPL", "2026-10-30", use_cache=False)
    assert data is not None
    recent = data.get("most_recent_downtrend")
    if recent:
        assert recent["peak_price"] < 99999.0
        assert recent["trough_price"] < 99999.0


def test_second_call_reuses_cache_not_a_second_fetch(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    call_count = {"n": 0}

    def fake_fetch(symbol, start, end):
        call_count["n"] += 1
        return _wavy_bars(500, "2025-01-01"), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    svc.fetch_downtrend_stats("AAPL", "2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    svc.fetch_downtrend_stats("AAPL", "2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls
