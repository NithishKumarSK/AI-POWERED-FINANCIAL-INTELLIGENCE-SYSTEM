"""
Tests for core/market_top_detector_service.py -- the live orchestrator
wiring real price history (via historical_price_service) and breadth data
(via market_breadth_service) into the ported market_top_detector pipeline.
No real network calls; both are monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import market_top_detector_service as svc
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "market_top_detector_cache.json")
    return svc


def _synthetic_bars(n_days: int, start_date: str, price: float = 100.0):
    import datetime as _dt
    d0 = _dt.date.fromisoformat(start_date)
    out = []
    for i in range(n_days):
        d = d0 + _dt.timedelta(days=i)
        out.append({"date": d.isoformat(), "close": price, "open": price, "high": price, "low": price, "volume": 1000})
    return out


def test_compute_market_top_risk_with_all_data_available(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    import market_breadth_service as mbs

    def fake_fetch(symbol, start, end):
        return _synthetic_bars(450, "2025-06-01"), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)
    monkeypatch.setattr(mbs, "fetch_market_breadth_snapshot", lambda as_of: ({"breadth_200dma_pct": 65.0, "breadth_50dma_pct": 60.0}, ""))

    data, err = svc.compute_market_top_risk("2026-10-30", use_cache=False)
    assert data is not None
    assert "composite_score" in data
    assert "zone" in data
    assert data["data_quality"]["available_count"] >= 5
    import json
    json.dumps(data)  # must be JSON-serializable end to end


def test_compute_market_top_risk_breadth_failure_degrades_gracefully(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    import market_breadth_service as mbs

    def fake_fetch(symbol, start, end):
        return _synthetic_bars(450, "2025-06-01"), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)
    monkeypatch.setattr(mbs, "fetch_market_breadth_snapshot", lambda as_of: (None, "breadth feed down"))

    data, err = svc.compute_market_top_risk("2026-10-30", use_cache=False)
    assert data is not None  # must not fail outright over one missing component
    assert "market_breadth" in err
    assert data["component_scores"]["breadth_divergence"] == 50  # neutral default


def test_compute_market_top_risk_all_tickers_fail_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda s, a, b: ([], "down", {}))

    data, err = svc.compute_market_top_risk("2026-10-30", use_cache=False)
    assert data is None
    assert err != ""


def test_second_call_reuses_cache_not_a_second_fetch(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    import market_breadth_service as mbs

    call_count = {"n": 0}

    def fake_fetch(symbol, start, end):
        call_count["n"] += 1
        return _synthetic_bars(450, "2025-06-01"), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)
    monkeypatch.setattr(mbs, "fetch_market_breadth_snapshot", lambda as_of: ({"breadth_200dma_pct": 65.0, "breadth_50dma_pct": 60.0}, ""))

    svc.compute_market_top_risk("2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    svc.compute_market_top_risk("2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls


def test_to_most_recent_first_filters_future_dates_and_reverses():
    from market_top_detector_service import _to_most_recent_first
    bars = [
        {"date": "2026-01-01", "close": 1},
        {"date": "2026-06-01", "close": 2},
        {"date": "2026-12-01", "close": 3},
    ]
    result = _to_most_recent_first(bars, "2026-10-30")
    assert len(result) == 2
    assert result[0]["date"] == "2026-06-01"


def test_derive_quote_and_distance_from_high():
    from market_top_detector_service import _derive_quote, _distance_from_high_pct
    history = [{"date": "d2", "close": 90, "high": 90}, {"date": "d1", "close": 100, "high": 100}]
    quote = _derive_quote(history)
    assert quote == {"price": 90, "yearHigh": 100}
    assert _distance_from_high_pct(history) == -10.0
