"""
Tests for core/exposure_coach_service.py. Every upstream *_service.py
import is monkeypatched at the module level it's imported from -- no
real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import exposure_coach_service as svc


def test_all_sources_succeed_no_warnings(monkeypatch):
    import market_breadth_service as mbs
    import macro_regime_service as mrs
    import market_top_detector_service as mtds
    import ftd_status_service as fss

    monkeypatch.setattr(mbs, "fetch_market_breadth_snapshot", lambda d: ({"breadth_200dma_pct": 70, "uptrend_ratio": 0.7}, ""))
    monkeypatch.setattr(mrs, "compute_macro_regime", lambda d, use_cache=True: ({"composite_score": 10, "confidence": "high"}, ""))
    monkeypatch.setattr(mtds, "compute_market_top_risk", lambda d, use_cache=True: ({"risk_budget": "100%", "composite_score": 5}, ""))
    monkeypatch.setattr(fss, "compute_ftd_status", lambda d, use_cache=True: ({"combined_state": "FTD_CONFIRMED"}, ""))

    data, warnings = svc.fetch_exposure_posture("2026-10-30")
    assert warnings == ""
    assert data["recommendation"] == "NEW_ENTRY_ALLOWED"


def test_one_source_failing_degrades_gracefully_not_a_crash(monkeypatch):
    import market_breadth_service as mbs
    import macro_regime_service as mrs
    import market_top_detector_service as mtds
    import ftd_status_service as fss

    monkeypatch.setattr(mbs, "fetch_market_breadth_snapshot", lambda d: (None, "network_error"))
    monkeypatch.setattr(mrs, "compute_macro_regime", lambda d, use_cache=True: ({"composite_score": 10, "confidence": "high"}, ""))
    monkeypatch.setattr(mtds, "compute_market_top_risk", lambda d, use_cache=True: ({"risk_budget": "100%", "composite_score": 5}, ""))
    monkeypatch.setattr(fss, "compute_ftd_status", lambda d, use_cache=True: ({"combined_state": "FTD_CONFIRMED"}, ""))

    data, warnings = svc.fetch_exposure_posture("2026-10-30")
    assert "breadth: network_error" in warnings
    assert "breadth" in data["inputs_missing"]
    assert data["recommendation"] == "NEW_ENTRY_ALLOWED"


def test_all_sources_raise_still_returns_a_usable_posture(monkeypatch):
    import market_breadth_service as mbs
    import macro_regime_service as mrs
    import market_top_detector_service as mtds
    import ftd_status_service as fss

    def _raise(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(mbs, "fetch_market_breadth_snapshot", _raise)
    monkeypatch.setattr(mrs, "compute_macro_regime", _raise)
    monkeypatch.setattr(mtds, "compute_market_top_risk", _raise)
    monkeypatch.setattr(fss, "compute_ftd_status", _raise)

    data, warnings = svc.fetch_exposure_posture("2026-10-30")
    assert data["confidence"] == "LOW"
    assert data["exposure_ceiling_pct"] == 50.0
    assert "breadth" in warnings and "regime" in warnings and "top_risk" in warnings and "ftd" in warnings
