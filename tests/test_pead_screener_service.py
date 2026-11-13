"""
Tests for core/pead_screener_service.py -- the live orchestrator wiring
free_news_service's earnings-8K lookup and historical_price_service into
the ported pead_screener pipeline. No real network calls; both are
monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import pead_screener_service as svc
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "pead_screener_cache.json")
    return svc


def _chrono_bars(start_date: str, n_days: int, price=100.0):
    import datetime as _dt
    d0 = _dt.date.fromisoformat(start_date)
    out = []
    d = d0
    count = 0
    while count < n_days:
        if d.weekday() < 5:
            out.append({"date": d.isoformat(), "open": price, "high": price * 1.01, "low": price * 0.99, "close": price, "volume": 5_000_000})
            count += 1
        d += _dt.timedelta(days=1)
    return out


def test_fetch_pead_analysis_with_recent_earnings(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import free_news_service as fns
    import historical_price_service as hps

    monkeypatch.setattr(fns, "fetch_most_recent_earnings_8k", lambda sym, as_of, lookback_days=84: ({"earnings_date": "2026-09-10", "items": "2.02,9.01"}, ""))
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (_chrono_bars("2026-07-01", 90), "", {}))

    data, err = svc.fetch_pead_analysis("AAPL", "2026-10-30", use_cache=False)
    assert data is not None
    assert err == ""
    assert data["symbol"] == "AAPL"
    assert "composite_score" in data


def test_fetch_pead_analysis_no_recent_earnings_is_an_honest_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import free_news_service as fns

    monkeypatch.setattr(fns, "fetch_most_recent_earnings_8k", lambda sym, as_of, lookback_days=84: (None, "No earnings-tagged 8-K found"))

    data, err = svc.fetch_pead_analysis("AAPL", "2026-10-30", use_cache=False)
    assert data is None
    assert "No earnings-tagged 8-K found" in err


def test_fetch_pead_analysis_no_price_history_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import free_news_service as fns
    import historical_price_service as hps

    monkeypatch.setattr(fns, "fetch_most_recent_earnings_8k", lambda sym, as_of, lookback_days=84: ({"earnings_date": "2026-09-10", "items": "2.02,9.01"}, ""))
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: ([], "down", {}))

    data, err = svc.fetch_pead_analysis("AAPL", "2026-10-30", use_cache=False)
    assert data is None
    assert err != ""


def test_second_call_reuses_cache_not_a_second_fetch(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import free_news_service as fns
    import historical_price_service as hps

    call_count = {"n": 0}

    def fake_earnings(sym, as_of, lookback_days=84):
        call_count["n"] += 1
        return {"earnings_date": "2026-09-10", "items": "2.02,9.01"}, ""

    monkeypatch.setattr(fns, "fetch_most_recent_earnings_8k", fake_earnings)
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (_chrono_bars("2026-07-01", 90), "", {}))

    svc.fetch_pead_analysis("AAPL", "2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    svc.fetch_pead_analysis("AAPL", "2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls


def test_leakage_safety_future_price_bars_excluded(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import free_news_service as fns
    import historical_price_service as hps

    monkeypatch.setattr(fns, "fetch_most_recent_earnings_8k", lambda sym, as_of, lookback_days=84: ({"earnings_date": "2026-09-10", "items": "2.02,9.01"}, ""))

    def fake_fetch(sym, a, b):
        bars = _chrono_bars("2026-07-01", 90)
        bars.append({"date": "2099-01-01", "open": 99999.0, "high": 99999.0, "low": 99999.0, "close": 99999.0, "volume": 1})
        return bars, "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = svc.fetch_pead_analysis("AAPL", "2026-10-30", use_cache=False)
    assert data is not None
    assert data["current_price"] != 99999.0
