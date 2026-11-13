"""
Tests for core/news_reaction_failure_service.py. historical_price_service
is monkeypatched -- no real network calls.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import news_reaction_failure_service as svc


def _bars(n=120, start="2026-01-02"):
    d0 = dt.date.fromisoformat(start)
    out = []
    d = d0
    while len(out) < n:
        if d.weekday() < 5:
            price = 100.0 + (0.1 if len(out) % 2 == 0 else -0.1)
            out.append({"date": d.isoformat(), "close": price})
        d += dt.timedelta(days=1)
    return out


def test_no_price_history_is_an_error(monkeypatch):
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: ([], "down", {}))
    data, err = svc.fetch_news_reaction_analysis("XYZ", [], "2026-10-30")
    assert data is None
    assert err == "down"


def test_full_pipeline_with_no_events_is_insufficient_evidence(monkeypatch):
    import historical_price_service as hps
    bars = _bars()
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (bars, "", {}))
    data, err = svc.fetch_news_reaction_analysis("XYZ", [], bars[-1]["date"])
    assert err == ""
    assert data["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert data["symbol"] == "XYZ"


def test_full_pipeline_with_events(monkeypatch):
    import historical_price_service as hps
    bars = _bars(n=100)
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (bars, "", {}))
    events = [
        {"event_id": "e1", "event": "x", "event_time": f"{bars[70]['date']}T10:00:00-05:00",
         "source_url": "u", "source_tier": "wire", "expected_impact": "BULLISH"},
        {"event_id": "e2", "event": "x", "event_time": f"{bars[80]['date']}T10:00:00-05:00",
         "source_url": "u", "source_tier": "wire", "expected_impact": "BULLISH"},
        {"event_id": "e3", "event": "x", "event_time": f"{bars[90]['date']}T10:00:00-05:00",
         "source_url": "u", "source_tier": "wire", "expected_impact": "BULLISH"},
    ]
    data, err = svc.fetch_news_reaction_analysis("XYZ", events, bars[95]["date"])
    assert err == ""
    assert data["verdict"] in ("CONFIRMED", "NOT_CONFIRMED")
