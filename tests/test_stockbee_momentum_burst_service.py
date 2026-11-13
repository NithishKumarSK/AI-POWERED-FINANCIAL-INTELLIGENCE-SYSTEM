"""
Tests for core/stockbee_momentum_burst_service.py -- the live orchestrator
wiring historical_price_service and ibd_distribution_day_service (for
market_gate) into the ported stockbee_momentum_burst_screener pipeline.
No real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import stockbee_momentum_burst_service as svc
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "stockbee_momentum_burst_cache.json")
    return svc


def _chrono_bars(start_date: str, n_days: int, price=100.0):
    import datetime as _dt
    d0 = _dt.date.fromisoformat(start_date)
    out = []
    for i in range(n_days):
        d = d0 + _dt.timedelta(days=i)
        out.append({"date": d.isoformat(), "open": price, "high": price * 1.01, "low": price * 0.99, "close": price, "volume": 1_000_000})
    return out


def test_fetch_momentum_burst_analysis_runs_end_to_end(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    import ibd_distribution_day_service as ibd

    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (_chrono_bars("2026-08-01", 90), "", {}))
    monkeypatch.setattr(ibd, "compute_ibd_distribution_day_status", lambda as_of: ({"overall_risk_level": "NORMAL"}, ""))

    data, err = svc.fetch_momentum_burst_analysis("NVDA", "2026-10-30", use_cache=False)
    assert data is not None
    assert err == ""
    assert data["symbol"] == "NVDA"
    assert "setup_score" in data


def test_fetch_momentum_burst_analysis_no_price_history_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: ([], "down", {}))

    data, err = svc.fetch_momentum_burst_analysis("NVDA", "2026-10-30", use_cache=False)
    assert data is None
    assert err != ""


def test_second_call_reuses_cache_not_a_second_fetch(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    import ibd_distribution_day_service as ibd

    call_count = {"n": 0}

    def fake_fetch(sym, a, b):
        call_count["n"] += 1
        return _chrono_bars("2026-08-01", 90), "", {}

    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)
    monkeypatch.setattr(ibd, "compute_ibd_distribution_day_status", lambda as_of: ({"overall_risk_level": "NORMAL"}, ""))

    svc.fetch_momentum_burst_analysis("NVDA", "2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    svc.fetch_momentum_burst_analysis("NVDA", "2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls
