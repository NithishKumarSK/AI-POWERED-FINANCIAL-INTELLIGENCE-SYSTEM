"""
Tests for core/sector_rotation_service.py. No real network calls --
requests.get is monkeypatched throughout.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import sector_rotation_service as svc

_SAMPLE_CSV = (
    "Sector,Ratio,10MA,Trend,Slope,Status\n"
    "Energy,0.4276729559748428,0.4351206114162885,Up,0.009433962264150886,Overbought\n"
    "Healthcare,0.3567961165048544,0.3188069676621512,Up,0.01403782060570935,Normal\n"
    "Technology,0.2813299232736573,0.32285703602116644,Up,0.007776758230673586,Normal\n"
    "Utilities,0.02666666666666667,0.021333333333333336,Up,0.0013333333333333357,Oversold\n"
)


class _FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


def test_parse_sector_summary_csv():
    rows = svc._parse_sector_summary_csv(_SAMPLE_CSV)
    assert len(rows) == 4
    assert rows[0]["sector"] == "Energy"
    assert rows[0]["status"] == "Overbought"


def test_fetch_sector_summary_success(monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "sector_rotation_cache.json")
    monkeypatch.setattr(svc.requests, "get", lambda *a, **k: _FakeResponse(200, _SAMPLE_CSV))
    rows, err = svc.fetch_sector_summary(use_cache=False)
    assert err == ""
    assert len(rows) == 4


def test_fetch_sector_summary_http_error(monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "sector_rotation_cache.json")
    monkeypatch.setattr(svc.requests, "get", lambda *a, **k: _FakeResponse(404, ""))
    rows, err = svc.fetch_sector_summary(use_cache=False)
    assert rows is None
    assert "404" in err


def test_fetch_sector_summary_uses_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "sector_rotation_cache.json"
    monkeypatch.setattr(svc, "CACHE_PATH", cache_path)
    call_count = {"n": 0}

    def _fake_get(*a, **k):
        call_count["n"] += 1
        return _FakeResponse(200, _SAMPLE_CSV)
    monkeypatch.setattr(svc.requests, "get", _fake_get)

    svc.fetch_sector_summary(use_cache=True)
    svc.fetch_sector_summary(use_cache=True)
    assert call_count["n"] == 1


def test_fetch_sector_rotation_analysis_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "sector_rotation_cache.json")
    monkeypatch.setattr(svc.requests, "get", lambda *a, **k: _FakeResponse(200, _SAMPLE_CSV))
    data, err = svc.fetch_sector_rotation_analysis(use_cache=False)
    assert err == ""
    assert data["ranked_sectors"][0]["sector"] == "Energy"
