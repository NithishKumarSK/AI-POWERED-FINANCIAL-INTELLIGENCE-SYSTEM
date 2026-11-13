"""
Tests for core/contrarian_confirmation_service.py. historical_price_service
is monkeypatched -- no real network calls.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import contrarian_confirmation_service as svc


def _daily_bars(start="2026-01-05", n_weeks=35, price=100.0):
    """n_weeks complete 5-day trading weeks starting on a Monday."""
    d0 = dt.date.fromisoformat(start)
    bars = []
    for w in range(n_weeks):
        for day in range(5):
            d = d0 + dt.timedelta(weeks=w, days=day)
            bars.append({"date": d.isoformat(), "open": price, "high": price + 2, "low": price - 2, "close": price})
    return bars


def test_resample_to_completed_weeks_groups_by_iso_week():
    bars = _daily_bars(n_weeks=3)
    weekly = svc._resample_to_completed_weeks(bars)
    assert len(weekly) == 3
    assert weekly[0]["high"] == 102.0
    assert weekly[0]["low"] == 98.0


def test_resample_drops_incomplete_trailing_week():
    bars = _daily_bars(n_weeks=3)
    bars = bars[:-3]  # last week only has 2 sessions
    weekly = svc._resample_to_completed_weeks(bars)
    assert len(weekly) == 2


def test_fetch_contrarian_confirmation_no_price_history_is_an_error(monkeypatch):
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: ([], "down", {}))
    data, err = svc.fetch_contrarian_confirmation("XYZ", "CROWDED_LONG", "2026-10-30")
    assert data is None
    assert err == "down"


def test_fetch_contrarian_confirmation_insufficient_data(monkeypatch):
    import historical_price_service as hps
    bars = _daily_bars(n_weeks=5)
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (bars, "", {}))
    data, err = svc.fetch_contrarian_confirmation("XYZ", "CROWDED_LONG", bars[-1]["date"])
    assert err == ""
    assert data["verdict"] == "INSUFFICIENT_DATA"
    assert data["symbol"] == "XYZ"


def test_fetch_contrarian_confirmation_full_pipeline(monkeypatch):
    import historical_price_service as hps
    bars = _daily_bars(n_weeks=35)
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (bars, "", {}))
    data, err = svc.fetch_contrarian_confirmation("XYZ", "CROWDED_LONG", bars[-1]["date"])
    assert err == ""
    assert data["verdict"] in ("CONFIRMED", "NOT_CONFIRMED", "INSUFFICIENT_DATA")
    assert data["symbol"] == "XYZ"
