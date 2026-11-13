"""
Pytest: market_breadth_service.py leakage + caching + degrade-gracefully
tests (adapted from claude-trading-skills' market-breadth-analyzer /
uptrend-analyzer skills).

No real network calls; requests.get is monkeypatched, and the disk cache
is redirected to a tmp_path per test.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import market_breadth_service as mbs
    monkeypatch.setattr(mbs, "CACHE_PATH", tmp_path / "breadth_cache.json")
    return mbs


class _FakeResp:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


_BREADTH_CSV = (
    "Date,S&P500_Price,Breadth_Index_Raw,Breadth_Index_200MA,Breadth_Index_8MA,"
    "Breadth_200MA_Trend,Bearish_Signal,Is_Peak,Is_Trough,Is_Trough_8MA_Below_04\n"
    "2026-02-01,100,0.5,0.60,0.61,1,False,False,False,False\n"
    "2026-03-01,101,0.5,0.65,0.66,1,True,False,False,False\n"
)

_UPTREND_CSV = (
    "worksheet,date,count,total,ratio,ma_10,slope,trend\n"
    "sec_energy,2026-02-01,10,75,0.9,0.8,0.01,up\n"
    "all,2026-02-01,100,500,0.30,0.28,0.01,up\n"
    "all,2026-03-01,120,500,0.35,0.32,0.02,down\n"
)


def test_breadth_excludes_rows_after_as_of_date(monkeypatch, tmp_path):
    mbs = _isolate_cache(monkeypatch, tmp_path)
    import requests

    def fake_get(url, timeout=30):
        if "market-breadth" in url:
            return _FakeResp(200, _BREADTH_CSV)
        return _FakeResp(200, _UPTREND_CSV)
    monkeypatch.setattr(requests, "get", fake_get)

    data, err = mbs.fetch_market_breadth_snapshot("2026-02-15")
    assert data["breadth_200ma"] == 0.60  # NOT the 03-01 value
    assert data["uptrend_ratio"] == 0.30


def test_uptrend_only_uses_all_worksheet_not_sector_rows(monkeypatch, tmp_path):
    mbs = _isolate_cache(monkeypatch, tmp_path)
    import requests
    monkeypatch.setattr(requests, "get", lambda url, timeout=30:
                         _FakeResp(200, _BREADTH_CSV) if "market-breadth" in url else _FakeResp(200, _UPTREND_CSV))
    data, err = mbs.fetch_market_breadth_snapshot("2026-02-01")
    assert data["uptrend_ratio"] == 0.30  # the "all" row, not sec_energy's 0.9


def test_no_data_on_or_before_as_of_date_omits_fields(monkeypatch, tmp_path):
    mbs = _isolate_cache(monkeypatch, tmp_path)
    import requests
    monkeypatch.setattr(requests, "get", lambda url, timeout=30:
                         _FakeResp(200, _BREADTH_CSV) if "market-breadth" in url else _FakeResp(200, _UPTREND_CSV))
    data, err = mbs.fetch_market_breadth_snapshot("2025-01-01")
    assert data is None
    assert err != ""


def test_http_error_degrades_to_error_not_exception(monkeypatch, tmp_path):
    mbs = _isolate_cache(monkeypatch, tmp_path)
    import requests
    monkeypatch.setattr(requests, "get", lambda url, timeout=30: _FakeResp(500, ""))
    data, err = mbs.fetch_market_breadth_snapshot("2026-02-15")
    assert data is None
    assert "500" in err


def test_second_call_reuses_cache(monkeypatch, tmp_path):
    mbs = _isolate_cache(monkeypatch, tmp_path)
    import requests
    call_count = {"n": 0}

    def fake_get(url, timeout=30):
        call_count["n"] += 1
        return _FakeResp(200, _BREADTH_CSV) if "market-breadth" in url else _FakeResp(200, _UPTREND_CSV)
    monkeypatch.setattr(requests, "get", fake_get)

    mbs.fetch_market_breadth_snapshot("2026-02-15")
    first = call_count["n"]
    mbs.fetch_market_breadth_snapshot("2026-03-01")
    assert call_count["n"] == first  # cache hit, no new HTTP calls
