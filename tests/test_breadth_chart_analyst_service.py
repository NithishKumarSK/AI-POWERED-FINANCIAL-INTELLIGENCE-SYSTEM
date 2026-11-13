"""
Tests for core/breadth_chart_analyst_service.py. market_breadth_service's
internal fetchers are monkeypatched -- no real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import breadth_chart_analyst_service as svc


def _breadth_rows(n=10):
    import datetime as dt
    d0 = dt.date(2026, 1, 1)
    return [{"date": (d0 + dt.timedelta(days=i)).isoformat(), "breadth_200ma": 0.50, "breadth_8ma": 0.50, "bearish_signal": False} for i in range(n)]


def _uptrend_rows(n=10):
    import datetime as dt
    d0 = dt.date(2026, 1, 1)
    return [{"date": (d0 + dt.timedelta(days=i)).isoformat(), "uptrend_ratio": 0.2, "uptrend_ma10": 0.2, "uptrend_trend": "neutral"} for i in range(n)]


def test_fetch_breadth_chart_analysis_no_breadth_data(monkeypatch):
    import market_breadth_service as mbs
    monkeypatch.setattr(mbs, "_fetch_breadth", lambda: (None, "down"))
    monkeypatch.setattr(mbs, "_fetch_uptrend", lambda: (_uptrend_rows(), ""))
    data, err = svc.fetch_breadth_chart_analysis("2026-01-10")
    assert data is None
    assert err == "down"


def test_fetch_breadth_chart_analysis_insufficient_history(monkeypatch):
    import market_breadth_service as mbs
    monkeypatch.setattr(mbs, "_fetch_breadth", lambda: (_breadth_rows(), ""))
    monkeypatch.setattr(mbs, "_fetch_uptrend", lambda: (_uptrend_rows(), ""))
    data, err = svc.fetch_breadth_chart_analysis("2026-01-01")  # only 1 row <= this date
    assert data is None
    assert err == "insufficient_history_as_of_date"


def test_fetch_breadth_chart_analysis_success(monkeypatch):
    import market_breadth_service as mbs
    monkeypatch.setattr(mbs, "_fetch_breadth", lambda: (_breadth_rows(), ""))
    monkeypatch.setattr(mbs, "_fetch_uptrend", lambda: (_uptrend_rows(), ""))
    data, err = svc.fetch_breadth_chart_analysis("2026-01-10")
    assert err == ""
    assert data["chart1_strategic"]["breadth_200ma"] == 50.0
    assert data["chart2_tactical"]["uptrend_ratio"] == 20.0
