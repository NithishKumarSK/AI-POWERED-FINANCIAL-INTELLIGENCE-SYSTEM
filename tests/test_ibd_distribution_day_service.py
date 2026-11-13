"""
Tests for core/ibd_distribution_day_service.py -- the live orchestrator
wiring real SPY/QQQ price history into the ported ibd_distribution_day_monitor
pipeline. No real network calls; historical_price_service.fetch_price_history_for_range
is monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import ibd_distribution_day_service as svc
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "ibd_distribution_day_cache.json")
    return svc


def _synthetic_bars(n_days: int, start_date: str, price: float = 100.0):
    """ASC-sorted {date,close,...} bars, flat (no distribution days)."""
    import datetime as _dt
    d0 = _dt.date.fromisoformat(start_date)
    out = []
    for i in range(n_days):
        d = d0 + _dt.timedelta(days=i)
        out.append({"date": d.isoformat(), "close": price, "open": price, "high": price, "low": price, "volume": 1000})
    return out


def test_compute_ibd_status_with_both_tickers_available(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    def fake_fetch(symbol, start, end):
        return _synthetic_bars(140, "2026-06-01"), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = svc.compute_ibd_distribution_day_status("2026-10-30", use_cache=False)
    assert data is not None
    assert err == ""
    assert data["overall_risk_level"] == "NORMAL"
    assert data["qqq_risk_level"] == "NORMAL"
    assert data["qqq_distribution_day_today"] is False
    # must be JSON-serializable end to end (DDRecord dataclasses get dict-ified)
    import json
    json.dumps(data)


def test_compute_ibd_status_one_ticker_fails_other_still_used(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    def fake_fetch(symbol, start, end):
        if symbol == "QQQ":
            return [], "no data for QQQ", {}
        return _synthetic_bars(140, "2026-06-01"), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = svc.compute_ibd_distribution_day_status("2026-10-30", use_cache=False)
    assert data is not None
    assert "QQQ" in err
    assert data["spy_risk_level"] == "NORMAL"
    assert data["qqq_risk_level"] is None


def test_compute_ibd_status_both_tickers_fail_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda s, a, b: ([], "down", {}))

    data, err = svc.compute_ibd_distribution_day_status("2026-10-30", use_cache=False)
    assert data is None
    assert err != ""


def test_second_call_reuses_cache_not_a_second_fetch(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    call_count = {"n": 0}

    def fake_fetch(symbol, start, end):
        call_count["n"] += 1
        return _synthetic_bars(140, "2026-06-01"), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    svc.compute_ibd_distribution_day_status("2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    svc.compute_ibd_distribution_day_status("2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls


def test_to_most_recent_first_filters_future_dates_and_reverses():
    from ibd_distribution_day_service import _to_most_recent_first
    bars = [
        {"date": "2026-01-01", "close": 1},
        {"date": "2026-06-01", "close": 2},
        {"date": "2026-12-01", "close": 3},  # after as_of -- must be excluded
    ]
    result = _to_most_recent_first(bars, "2026-10-30")
    assert len(result) == 2
    assert result[0]["date"] == "2026-06-01"  # most recent first
    assert result[1]["date"] == "2026-01-01"
