"""
Tests for core/cot_contrarian_detector_service.py. CFTC client access
is monkeypatched -- no real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import cot_contrarian_detector_service as svc


def _rows(n=160, start="2023-01-03", long_=1000, short_=500):
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    out = []
    for i in range(n):
        d = (d0 + dt.timedelta(weeks=i)).isoformat() + "T00:00:00.000"
        out.append({"report_date_as_yyyy_mm_dd": d, "noncomm_positions_long_all": str(long_ + i),
                    "noncomm_positions_short_all": str(short_), "open_interest_all": "10000"})
    return out


def test_unsupported_symbol_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "cot_cache.json")
    data, err = svc.fetch_cot_crowding("ZZZZ", "2026-10-30", use_cache=False)
    assert data is None
    assert "unsupported_symbol" in err


def test_fetch_error_propagates(monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "cot_cache.json")
    import tools.cftc_cot_client as cot
    monkeypatch.setattr(cot, "fetch_cot_history", lambda code, limit=250: (None, "http_500"))
    data, err = svc.fetch_cot_crowding("ES", "2026-10-30", use_cache=False)
    assert data is None
    assert err == "http_500"


def test_fetch_cot_crowding_full_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "cot_cache.json")
    import tools.cftc_cot_client as cot
    rows = _rows()
    monkeypatch.setattr(cot, "fetch_cot_history", lambda code, limit=250: (rows, ""))
    as_of = rows[-1]["report_date_as_yyyy_mm_dd"][:10]
    data, err = svc.fetch_cot_crowding("ES", as_of, use_cache=False)
    assert err == ""
    assert data["symbol"] == "ES"
    assert data["classification"] in ("CROWDED_LONG", "CROWDED_SHORT", "NEUTRAL")


def test_leakage_safety_truncates_future_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "cot_cache.json")
    import tools.cftc_cot_client as cot
    rows = _rows()
    monkeypatch.setattr(cot, "fetch_cot_history", lambda code, limit=250: (rows, ""))
    early_as_of = rows[0]["report_date_as_yyyy_mm_dd"][:10]
    data, err = svc.fetch_cot_crowding("ES", early_as_of, use_cache=False)
    assert err == ""
    assert data["weeks_used"] == 1


def test_uses_same_day_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "cot_cache.json"
    monkeypatch.setattr(svc, "CACHE_PATH", cache_path)
    import tools.cftc_cot_client as cot
    rows = _rows()
    call_count = {"n": 0}

    def _fake_fetch(code, limit=250):
        call_count["n"] += 1
        return rows, ""
    monkeypatch.setattr(cot, "fetch_cot_history", _fake_fetch)

    as_of = rows[-1]["report_date_as_yyyy_mm_dd"][:10]
    svc.fetch_cot_crowding("ES", as_of, use_cache=True)
    svc.fetch_cot_crowding("ES", as_of, use_cache=True)
    assert call_count["n"] == 1
