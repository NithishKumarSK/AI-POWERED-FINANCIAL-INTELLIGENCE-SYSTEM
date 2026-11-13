"""
Tests for core/stockbee_exhaustion_hammer_service.py -- the live
orchestrator wiring historical_price_service and
ibd_distribution_day_service (for market_gate) into the ported
stockbee_exhaustion_hammer_screener pipeline. No real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import stockbee_exhaustion_hammer_service as svc
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "stockbee_exhaustion_hammer_cache.json")
    return svc


def _chrono_bars(start_date: str, n_days: int, price=100.0):
    import datetime as _dt
    d0 = _dt.date.fromisoformat(start_date)
    out = []
    for i in range(n_days):
        d = d0 + _dt.timedelta(days=i)
        out.append({"date": d.isoformat(), "open": price, "high": price * 1.01, "low": price * 0.99, "close": price, "volume": 1_000_000})
    return out


def test_fetch_exhaustion_hammer_analysis_runs_end_to_end(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    import ibd_distribution_day_service as ibd

    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (_chrono_bars("2026-06-01", 150), "", {}))
    monkeypatch.setattr(ibd, "compute_ibd_distribution_day_status", lambda as_of: ({"overall_risk_level": "NORMAL"}, ""))

    data, err = svc.fetch_exhaustion_hammer_analysis("AAPL", "2026-10-30", use_cache=False)
    assert data is not None
    assert err == ""
    assert data["symbol"] == "AAPL"
    assert "setup_score" in data


def test_fetch_exhaustion_hammer_analysis_derives_market_gate_from_ibd_risk(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    import ibd_distribution_day_service as ibd

    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (_chrono_bars("2026-06-01", 150), "", {}))
    monkeypatch.setattr(ibd, "compute_ibd_distribution_day_status", lambda as_of: ({"overall_risk_level": "SEVERE"}, ""))

    gate = svc._derive_market_gate("2026-10-30")
    assert gate == "restrictive"


def test_derive_market_gate_defaults_to_neutral_on_failure(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import ibd_distribution_day_service as ibd
    monkeypatch.setattr(ibd, "compute_ibd_distribution_day_status", lambda as_of: (_ for _ in ()).throw(RuntimeError("boom")))
    assert svc._derive_market_gate("2026-10-30") == "neutral"


def test_fetch_exhaustion_hammer_analysis_no_price_history_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: ([], "down", {}))

    data, err = svc.fetch_exhaustion_hammer_analysis("AAPL", "2026-10-30", use_cache=False)
    assert data is None
    assert err != ""


def test_second_call_reuses_cache_not_a_second_fetch(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    import ibd_distribution_day_service as ibd

    call_count = {"n": 0}

    def fake_fetch(sym, a, b):
        call_count["n"] += 1
        return _chrono_bars("2026-06-01", 150), "", {}

    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)
    monkeypatch.setattr(ibd, "compute_ibd_distribution_day_status", lambda as_of: ({"overall_risk_level": "NORMAL"}, ""))

    svc.fetch_exhaustion_hammer_analysis("AAPL", "2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    svc.fetch_exhaustion_hammer_analysis("AAPL", "2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls
