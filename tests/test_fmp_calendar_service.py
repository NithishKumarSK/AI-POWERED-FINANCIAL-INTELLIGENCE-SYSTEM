"""Pytest: fmp_calendar_service.py -- earnings/economic calendar via FMP.
No real network calls; fmp_client.fmp_get is monkeypatched."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tools"))


def test_fetch_earnings_calendar_filters_by_symbol(monkeypatch):
    import fmp_calendar_service as fcs
    import fmp_client

    monkeypatch.setattr(fmp_client, "fmp_get", lambda endpoint, params=None: {
        "status": "SUCCESS", "data": [
            {"symbol": "AAPL", "date": "2026-11-02", "epsEstimated": 1.99, "revenueEstimated": 113401200000},
            {"symbol": "MSFT", "date": "2026-11-03", "epsEstimated": 3.1, "revenueEstimated": 70000000000},
        ],
    })

    data, err = fcs.fetch_earnings_calendar("2026-11-01", "2026-11-07", symbol="AAPL")
    assert err == ""
    assert len(data) == 1
    assert data[0]["symbol"] == "AAPL"
    assert data[0]["eps_estimated"] == 1.99


def test_fetch_earnings_calendar_no_symbol_filter_returns_all(monkeypatch):
    import fmp_calendar_service as fcs
    import fmp_client

    monkeypatch.setattr(fmp_client, "fmp_get", lambda endpoint, params=None: {
        "status": "SUCCESS", "data": [
            {"symbol": "AAPL", "date": "2026-11-02"}, {"symbol": "MSFT", "date": "2026-11-03"},
        ],
    })
    data, err = fcs.fetch_earnings_calendar("2026-11-01", "2026-11-07")
    assert len(data) == 2


def test_fetch_earnings_calendar_propagates_error(monkeypatch):
    import fmp_calendar_service as fcs
    import fmp_client
    monkeypatch.setattr(fmp_client, "fmp_get", lambda endpoint, params=None: {"status": "ERROR", "message": "no key"})
    data, err = fcs.fetch_earnings_calendar("2026-11-01", "2026-11-07")
    assert data is None
    assert err == "no key"


def test_fetch_economic_calendar_filters_by_country(monkeypatch):
    import fmp_calendar_service as fcs
    import fmp_client

    monkeypatch.setattr(fmp_client, "fmp_get", lambda endpoint, params=None: {
        "status": "SUCCESS", "data": [
            {"date": "2026-11-05", "country": "US", "event": "CPI", "currency": "USD", "impact": "High"},
            {"date": "2026-11-05", "country": "EU", "event": "ECB Rate", "currency": "EUR", "impact": "High"},
        ],
    })
    data, err = fcs.fetch_economic_calendar("2026-11-01", "2026-11-07", countries=["US"])
    assert len(data) == 1
    assert data[0]["country"] == "US"


def test_fetch_economic_calendar_premium_required_propagates(monkeypatch):
    """Real finding this session: FMP's economic-calendar endpoint returns
    HTTP 402 on the free tier -- must surface as PREMIUM_REQUIRED, not crash."""
    import fmp_calendar_service as fcs
    import fmp_client
    monkeypatch.setattr(fmp_client, "fmp_get", lambda endpoint, params=None: {
        "status": "ERROR", "error_type": "PREMIUM_REQUIRED", "message": "FMP returned 402 -- this endpoint needs a paid plan",
    })
    data, err = fcs.fetch_economic_calendar("2026-11-01", "2026-11-07")
    assert data is None
    assert "paid plan" in err
