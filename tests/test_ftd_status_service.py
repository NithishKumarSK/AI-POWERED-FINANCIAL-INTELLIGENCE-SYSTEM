"""
Tests for core/ftd_status_service.py -- the live orchestrator wiring real
SPY/QQQ price history into the ported ftd_detector state machine. No real
network calls; historical_price_service.fetch_price_history_for_range is
monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import ftd_status_service as fss
    monkeypatch.setattr(fss, "CACHE_PATH", tmp_path / "ftd_status_cache.json")
    return fss


def _synthetic_bars(n_days: int, start_date: str, start_price: float, daily_change: float):
    """ASC-sorted {date,close,...} bars, historical_price_service's own shape."""
    import datetime as _dt
    d0 = _dt.date.fromisoformat(start_date)
    out = []
    for i in range(n_days):
        d = d0 + _dt.timedelta(days=i)
        price = start_price + i * daily_change
        out.append({"date": d.isoformat(), "close": price, "open": price, "high": price, "low": price, "volume": 1000})
    return out


def test_compute_ftd_status_with_both_tickers_available(monkeypatch, tmp_path):
    fss = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    def fake_fetch(symbol, start, end):
        return _synthetic_bars(150, "2026-06-01", 100.0, 0.3), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = fss.compute_ftd_status("2026-10-30", use_cache=False)
    assert data is not None
    assert err == ""
    assert "combined_state" in data
    assert data["sp500_state"] is not None
    assert data["nasdaq_state"] is not None


def test_compute_ftd_status_one_ticker_fails_other_still_used(monkeypatch, tmp_path):
    fss = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    def fake_fetch(symbol, start, end):
        if symbol == "QQQ":
            return [], "no data for QQQ", {}
        return _synthetic_bars(150, "2026-06-01", 100.0, 0.3), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = fss.compute_ftd_status("2026-10-30", use_cache=False)
    assert data is not None  # SPY alone is enough to not fail outright
    assert "QQQ" in err
    assert data["sp500_state"] is not None
    assert data["nasdaq_state"] == "NO_SIGNAL"  # empty history -> default state, not a crash


def test_compute_ftd_status_both_tickers_fail_is_an_error(monkeypatch, tmp_path):
    fss = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda s, a, b: ([], "down", {}))

    data, err = fss.compute_ftd_status("2026-10-30", use_cache=False)
    assert data is None
    assert err != ""


def test_second_call_reuses_cache_not_a_second_fetch(monkeypatch, tmp_path):
    fss = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    call_count = {"n": 0}

    def fake_fetch(symbol, start, end):
        call_count["n"] += 1
        return _synthetic_bars(150, "2026-06-01", 100.0, 0.3), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    fss.compute_ftd_status("2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    fss.compute_ftd_status("2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls  # cache hit, no new fetches


def test_filter_chronological_excludes_future_dates():
    from ftd_status_service import _filter_chronological
    bars = [
        {"date": "2026-01-01", "close": 1},
        {"date": "2026-06-01", "close": 2},
        {"date": "2026-12-01", "close": 3},  # after as_of -- must be excluded
    ]
    result = _filter_chronological(bars, "2026-10-30")
    assert len(result) == 2
    assert result[-1]["date"] == "2026-06-01"  # chronological order preserved (oldest first)
