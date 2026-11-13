"""
Tests for core/canslim_screener_service.py -- the live orchestrator
wiring sec_financials_service (C/A), historical_price_service (N/S/M),
vcp_screener's relative-strength calc (L), and institutional_holdings_service
(I) into the ported canslim_screener pipeline. No real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import canslim_screener_service as svc
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "canslim_screener_cache.json")
    return svc


def _chrono_bars(start_date: str, n_days: int, price=100.0, volume=1_000_000):
    import datetime as _dt
    d0 = _dt.date.fromisoformat(start_date)
    out = []
    for i in range(n_days):
        d = d0 + _dt.timedelta(days=i)
        p = price + i * 0.05
        out.append({"date": d.isoformat(), "open": p, "high": p * 1.01, "low": p * 0.99, "close": p, "volume": volume})
    return out


def _quarterly_series():
    return [
        {"date": "2026-06-30", "eps": 2.70, "revenue": 13_507_000_000},
        {"date": "2026-03-31", "eps": 1.09, "revenue": 7_192_000_000},
        {"date": "2025-12-31", "eps": 0.88, "revenue": 6_051_000_000},
        {"date": "2025-09-30", "eps": 0.58, "revenue": 5_931_000_000},
        {"date": "2025-06-30", "eps": 0.51, "revenue": 6_704_000_000},
    ]


def _annual_series():
    return [
        {"date": "2026-12-31", "eps": 10.0, "revenue": 1_000_000_000},
        {"date": "2025-12-31", "eps": 7.0, "revenue": 800_000_000},
        {"date": "2024-12-31", "eps": 5.0, "revenue": 600_000_000},
        {"date": "2023-12-31", "eps": 3.5, "revenue": 500_000_000},
    ]


def _patch_all(monkeypatch):
    import historical_price_service as hps
    import institutional_holdings_service as ihs
    import sec_financials_service as sfs

    def fake_fetch(symbol, start, end):
        return _chrono_bars("2025-06-01", 440, price=100.0 if symbol in ("SPY", "^VIX") else 150.0), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)
    monkeypatch.setattr(sfs, "fetch_quarterly_eps_revenue_series", lambda sym, as_of: (_quarterly_series(), ""))
    monkeypatch.setattr(sfs, "fetch_annual_eps_revenue_series", lambda sym, as_of: (_annual_series(), ""))
    monkeypatch.setattr(ihs, "fetch_institutional_holders", lambda sym, as_of: ({"holder_count": 3, "holders": [{"name": "BERKSHIRE HATHAWAY INC", "pct_of_13f": 1.0, "filed": "2026-08-01"}]}, ""))


def test_fetch_canslim_analysis_runs_end_to_end(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    _patch_all(monkeypatch)

    data, err = svc.fetch_canslim_analysis("NVDA", "2026-10-30", use_cache=False)
    assert data is not None
    assert data["symbol"] == "NVDA"
    assert "composite_score" in data
    assert set(data["component_scores"].keys()) == {"C", "A", "N", "S", "L", "I", "M"}
    assert data["i_component"]["superinvestor_present"] is True


def test_fetch_canslim_analysis_no_price_history_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: ([], "down", {}))

    data, err = svc.fetch_canslim_analysis("NVDA", "2026-10-30", use_cache=False)
    assert data is None
    assert err != ""


def test_fetch_canslim_analysis_missing_sec_data_degrades_not_crashes(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    _patch_all(monkeypatch)
    import sec_financials_service as sfs
    monkeypatch.setattr(sfs, "fetch_quarterly_eps_revenue_series", lambda sym, as_of: (None, "no quarterly data"))

    data, err = svc.fetch_canslim_analysis("NVDA", "2026-10-30", use_cache=False)
    assert data is not None  # must not fail outright over one missing component
    assert data["c_component"]["score"] == 0
    assert "C (quarterly earnings)" in err


def test_second_call_reuses_cache_not_a_second_fetch(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    _patch_all(monkeypatch)
    import historical_price_service as hps

    call_count = {"n": 0}
    real_fetch = hps.fetch_price_history_for_range

    def counting_fetch(symbol, start, end):
        call_count["n"] += 1
        return real_fetch(symbol, start, end)
    monkeypatch.setattr(hps, "fetch_price_history_for_range", counting_fetch)

    svc.fetch_canslim_analysis("NVDA", "2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    svc.fetch_canslim_analysis("NVDA", "2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls


def test_derive_quote_computes_avg_volume():
    from canslim_screener_service import _derive_quote
    history = [{"date": "d2", "close": 100, "high": 102, "low": 98, "volume": 2_000_000}] + [{"date": f"d{i}", "close": 90, "high": 92, "low": 88, "volume": 1_000_000} for i in range(19)]
    quote = _derive_quote(history)
    assert quote["price"] == 100
    assert quote["avgVolume"] > 1_000_000
