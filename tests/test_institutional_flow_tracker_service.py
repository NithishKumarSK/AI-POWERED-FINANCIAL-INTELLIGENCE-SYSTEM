"""
Tests for core/institutional_flow_tracker_service.py. SEC EDGAR access
and the local cache are monkeypatched -- no real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import institutional_flow_tracker_service as svc


def _fake_cache(filers):
    return {"built_at": "2026-10-01T00:00:00", "filers": filers}


def test_symbol_lookup_failure_is_an_error(monkeypatch):
    import sec_edgar_client as sec
    monkeypatch.setattr(sec, "get_cik_for_symbol", lambda symbol: {"status": "ERROR", "message": "not found"})
    data, err = svc.fetch_institutional_flow("ZZZZ", "2026-10-30")
    assert data is None
    assert err == "not found"


def test_no_cache_built_is_an_error(monkeypatch):
    import sec_edgar_client as sec
    monkeypatch.setattr(sec, "get_cik_for_symbol", lambda symbol: {"status": "SUCCESS", "company_name": "Apple Inc."})
    monkeypatch.setattr(svc, "_load_cache", lambda: {"built_at": None, "filers": {}})
    data, err = svc.fetch_institutional_flow("AAPL", "2026-10-30")
    assert data is None
    assert "cache" in err


def test_fetch_institutional_flow_classifies_accumulation(monkeypatch):
    import sec_edgar_client as sec
    monkeypatch.setattr(sec, "get_cik_for_symbol", lambda symbol: {"status": "SUCCESS", "company_name": "Apple Inc."})

    filers = {
        "0001": {
            "name": "Berkshire Hathaway", "filed": "2026-08-14",
            "rows": [{"issuer": "APPLE INC", "value": 1_200_000.0, "shares": 100}],
            "prior": {"filed": "2026-05-14", "rows": [{"issuer": "APPLE INC", "value": 1_000_000.0, "shares": 90}]},
        },
    }
    monkeypatch.setattr(svc, "_load_cache", lambda: _fake_cache(filers))

    data, err = svc.fetch_institutional_flow("AAPL", "2026-10-30")
    assert err == ""
    assert data["classification"] == "SMART_MONEY_ACCUMULATION"
    assert data["filer_flows"][0]["flow"] == "ACCUMULATION"


def test_fetch_institutional_flow_leakage_safety_excludes_future_filing(monkeypatch):
    import sec_edgar_client as sec
    monkeypatch.setattr(sec, "get_cik_for_symbol", lambda symbol: {"status": "SUCCESS", "company_name": "Apple Inc."})

    filers = {
        "0001": {
            "name": "Berkshire Hathaway", "filed": "2026-11-15",  # after as_of_date
            "rows": [{"issuer": "APPLE INC", "value": 1_200_000.0, "shares": 100}],
            "prior": None,
        },
    }
    monkeypatch.setattr(svc, "_load_cache", lambda: _fake_cache(filers))

    data, err = svc.fetch_institutional_flow("AAPL", "2026-10-30")
    assert err == ""
    assert data["filer_flows"] == []
    assert data["classification"] == "NO_SIGNAL"


def test_fetch_institutional_flow_no_position_in_either_period_excluded(monkeypatch):
    import sec_edgar_client as sec
    monkeypatch.setattr(sec, "get_cik_for_symbol", lambda symbol: {"status": "SUCCESS", "company_name": "Apple Inc."})

    filers = {
        "0001": {
            "name": "Berkshire Hathaway", "filed": "2026-08-14",
            "rows": [],  # no AAPL rows at all
            "prior": {"filed": "2026-05-14", "rows": []},
        },
    }
    monkeypatch.setattr(svc, "_load_cache", lambda: _fake_cache(filers))

    data, err = svc.fetch_institutional_flow("AAPL", "2026-10-30")
    assert err == ""
    assert data["filer_flows"] == []
