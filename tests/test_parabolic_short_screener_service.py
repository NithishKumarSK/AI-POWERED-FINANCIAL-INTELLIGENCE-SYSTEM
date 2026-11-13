"""
Tests for core/parabolic_short_screener_service.py. historical_price_service,
fmp_client, and fmp_calendar_service are monkeypatched -- no real network.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import parabolic_short_screener_service as svc


def _parabolic_bars(n=280, base=10.0, start="2026-01-01"):
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    closes = [base] * (n - 5)
    last = base
    for _ in range(5):
        last *= 1.15
        closes.append(last)
    bars = []
    for i, c in enumerate(closes):
        bars.append({"date": (d0 + dt.timedelta(days=i)).isoformat(), "open": c, "high": c * 1.02,
                     "low": c * 0.97, "close": c, "volume": 1_000_000 if i < len(closes) - 1 else 2_500_000})
    return bars


def test_trading_days_since_handles_missing_and_malformed():
    assert svc._trading_days_since(None, "2026-11-02") is None
    assert svc._trading_days_since("not-a-date", "2026-11-02") is None


def test_fetch_parabolic_screen_no_price_history_is_an_error(monkeypatch):
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: ([], "down", {}))
    data, err = svc.fetch_parabolic_screen("XYZ", "2026-11-02")
    assert data is None
    assert err == "down"


def test_fetch_parabolic_screen_full_pipeline(monkeypatch):
    import historical_price_service as hps
    bars = _parabolic_bars()
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (bars, "", {}))

    import fmp_client as fc
    monkeypatch.setattr(fc, "fmp_get", lambda endpoint, params=None, timeout=20: (
        {"status": "SUCCESS", "data": [{"marketCap": 5_000_000_000, "ipoDate": "2000-01-01"}]}
        if endpoint == "profile" else {"status": "ERROR"}
    ))

    import fmp_calendar_service as fcs
    monkeypatch.setattr(fcs, "fetch_earnings_calendar", lambda start, end, symbol=None: ([], ""))

    data, err = svc.fetch_parabolic_screen("XYZ", bars[-1]["date"])
    assert err == ""
    assert data is not None
    assert data["status"] == "CANDIDATE"


def test_fetch_parabolic_screen_degrades_gracefully_when_profile_fails(monkeypatch):
    import historical_price_service as hps
    bars = _parabolic_bars()
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (bars, "", {}))

    import fmp_client as fc

    def _raise(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(fc, "fmp_get", _raise)

    import fmp_calendar_service as fcs
    monkeypatch.setattr(fcs, "fetch_earnings_calendar", lambda start, end, symbol=None: ([], ""))

    data, err = svc.fetch_parabolic_screen("XYZ", bars[-1]["date"])
    assert err == ""
    assert data is not None  # market_cap=None never rejects on the cap-floor rule
