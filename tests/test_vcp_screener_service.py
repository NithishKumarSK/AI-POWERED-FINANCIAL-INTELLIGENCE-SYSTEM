"""
Tests for core/vcp_screener_service.py -- the live orchestrator wiring
historical_price_service (symbol + SPY benchmark) into the ported
vcp_screener pipeline. No real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import vcp_screener_service as svc
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "vcp_screener_cache.json")
    return svc


def _chrono_bars(start_date: str, n_days: int, price=100.0):
    import datetime as _dt
    d0 = _dt.date.fromisoformat(start_date)
    out = []
    for i in range(n_days):
        d = d0 + _dt.timedelta(days=i)
        p = price + i * 0.05
        out.append({"date": d.isoformat(), "open": p, "high": p * 1.01, "low": p * 0.99, "close": p, "volume": 1_000_000})
    return out


def test_fetch_vcp_analysis_runs_end_to_end(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    def fake_fetch(symbol, start, end):
        return _chrono_bars("2025-09-01", 440, price=100.0 if symbol == "SPY" else 150.0), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = svc.fetch_vcp_analysis("AAPL", "2026-10-30", use_cache=False)
    assert data is not None
    assert err == ""
    assert data["symbol"] == "AAPL"
    assert "composite_score" in data


def test_fetch_vcp_analysis_no_symbol_history_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: ([], "down", {}))

    data, err = svc.fetch_vcp_analysis("AAPL", "2026-10-30", use_cache=False)
    assert data is None
    assert err != ""


def test_fetch_vcp_analysis_no_benchmark_history_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    def fake_fetch(symbol, start, end):
        if symbol == "SPY":
            return [], "benchmark down", {}
        return _chrono_bars("2025-09-01", 440, price=150.0), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = svc.fetch_vcp_analysis("AAPL", "2026-10-30", use_cache=False)
    assert data is None
    assert "benchmark" in err or "SPY" in err


def test_second_call_reuses_cache_not_a_second_fetch(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    call_count = {"n": 0}

    def fake_fetch(symbol, start, end):
        call_count["n"] += 1
        return _chrono_bars("2025-09-01", 440, price=100.0 if symbol == "SPY" else 150.0), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    svc.fetch_vcp_analysis("AAPL", "2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    svc.fetch_vcp_analysis("AAPL", "2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls


def test_to_most_recent_first_filters_future_dates():
    from vcp_screener_service import _to_most_recent_first
    bars = [{"date": "2026-01-01"}, {"date": "2026-06-01"}, {"date": "2026-12-01"}]
    result = _to_most_recent_first(bars, "2026-10-30")
    assert len(result) == 2
    assert result[0]["date"] == "2026-06-01"


def test_derive_quote_computes_price_and_year_high_low():
    from vcp_screener_service import _derive_quote
    history = [{"date": "d2", "close": 100, "high": 102, "low": 98}, {"date": "d1", "close": 95, "high": 97, "low": 93}]
    quote = _derive_quote(history)
    assert quote["price"] == 100
    assert quote["yearHigh"] == 102
    assert quote["yearLow"] == 93
