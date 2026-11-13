"""
Tests for core/macro_regime_service.py -- the live orchestrator wiring
real price history into the 6 ported macro-regime-detector calculators.
No real network calls; historical_price_service.fetch_price_history_for_range
is monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import macro_regime_service as mrs
    monkeypatch.setattr(mrs, "CACHE_PATH", tmp_path / "macro_regime_cache.json")
    return mrs


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


def test_compute_macro_regime_with_all_tickers_available(monkeypatch, tmp_path):
    mrs = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    def fake_fetch(symbol, start, end):
        bars = _synthetic_bars(820, "2024-09-01", 100.0, 0.05)
        return bars, "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = mrs.compute_macro_regime("2026-10-30", use_cache=False)
    assert data is not None
    assert "composite_score" in data
    assert "current_regime" in data
    assert data["confidence"] in ("high", "moderate", "low", "very_low")


def test_compute_macro_regime_partial_ticker_failure_degrades_gracefully(monkeypatch, tmp_path):
    mrs = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    def fake_fetch(symbol, start, end):
        if symbol == "RSP":
            return [], "no data for RSP", {}
        bars = _synthetic_bars(820, "2024-09-01", 100.0, 0.05)
        return bars, "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = mrs.compute_macro_regime("2026-10-30", use_cache=False)
    assert data is not None  # must not fail outright just because one ticker is missing
    assert "RSP" in err
    assert data["component_scores"]["concentration"] == 0  # the component needing RSP degrades to 0


def test_compute_macro_regime_all_tickers_fail_is_an_error(monkeypatch, tmp_path):
    mrs = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda s, a, b: ([], "down", {}))

    data, err = mrs.compute_macro_regime("2026-10-30", use_cache=False)
    assert data is None
    assert err != ""


def test_second_call_reuses_cache_not_a_second_fetch(monkeypatch, tmp_path):
    mrs = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    call_count = {"n": 0}

    def fake_fetch(symbol, start, end):
        call_count["n"] += 1
        bars = _synthetic_bars(820, "2024-09-01", 100.0, 0.05)
        return bars, "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    mrs.compute_macro_regime("2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    mrs.compute_macro_regime("2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls  # cache hit, no new fetches


def test_bars_to_history_filters_future_dates_and_reverses_order():
    from macro_regime_service import _bars_to_history
    bars = [
        {"date": "2026-01-01", "close": 1},
        {"date": "2026-06-01", "close": 2},
        {"date": "2026-12-01", "close": 3},  # after as_of -- must be excluded
    ]
    result = _bars_to_history(bars, "2026-10-30")
    assert len(result) == 2
    assert result[0]["date"] == "2026-06-01"  # most recent first
    assert result[1]["date"] == "2026-01-01"
