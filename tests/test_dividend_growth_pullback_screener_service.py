"""
Tests for core/dividend_growth_pullback_screener_service.py -- the live
orchestrator wiring sec_financials_service's new dividend/cash-flow
extraction and historical_price_service into the ported
dividend_growth_pullback_screener pipeline. No real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import dividend_growth_pullback_screener_service as svc
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "dividend_growth_pullback_cache.json")
    return svc


def _chrono_bars(start_date: str, n_days: int, price=100.0):
    import datetime as _dt
    d0 = _dt.date.fromisoformat(start_date)
    out = []
    for i in range(n_days):
        d = d0 + _dt.timedelta(days=i)
        p = price - i * 0.3  # mild decline -- gives a real, non-trivial RSI
        out.append({"date": d.isoformat(), "open": p, "high": p * 1.01, "low": p * 0.99, "close": p, "volume": 1_000_000})
    return out


def _div_series():
    return [
        {"date": "2025-12-31", "dividend_per_share": 2.04, "dividends_paid_total": 8_779_000_000},
        {"date": "2024-12-31", "dividend_per_share": 1.93, "dividends_paid_total": 8_359_000_000},
        {"date": "2023-12-31", "dividend_per_share": 1.83, "dividends_paid_total": 7_952_000_000},
        {"date": "2022-12-31", "dividend_per_share": 1.75, "dividends_paid_total": 7_616_000_000},
    ]


def _patch_all(monkeypatch):
    import historical_price_service as hps
    import sec_financials_service as sfs

    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (_chrono_bars("2026-09-01", 55), "", {}))
    monkeypatch.setattr(sfs, "fetch_annual_dividend_series", lambda sym, as_of: (_div_series(), ""))
    monkeypatch.setattr(sfs, "fetch_cash_flow_coverage", lambda sym, as_of: ({"dividends_paid": 8_779_000_000, "free_cash_flow": 5_296_000_000}, ""))
    monkeypatch.setattr(sfs, "fetch_key_financials", lambda sym, as_of: ({"net_income": 10_000_000_000, "revenue": 47_000_000_000}, ""))


def test_fetch_dividend_growth_pullback_analysis_runs_end_to_end(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    _patch_all(monkeypatch)

    data, err = svc.fetch_dividend_growth_pullback_analysis("KO", "2026-10-30", use_cache=False)
    assert data is not None
    assert data["symbol"] == "KO"
    assert data["dividend_cagr_3yr"] is not None
    assert data["rsi_14"] is not None
    assert data["dividend_yield_pct"] is not None
    assert 0 <= data["composite_score"] <= 100


def test_fetch_dividend_growth_pullback_analysis_no_price_history_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: ([], "down", {}))

    data, err = svc.fetch_dividend_growth_pullback_analysis("KO", "2026-10-30", use_cache=False)
    assert data is None
    assert err != ""


def test_fetch_dividend_growth_pullback_analysis_missing_dividend_data_degrades_not_crashes(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    _patch_all(monkeypatch)
    import sec_financials_service as sfs
    monkeypatch.setattr(sfs, "fetch_annual_dividend_series", lambda sym, as_of: (None, "no dividend data"))

    data, err = svc.fetch_dividend_growth_pullback_analysis("KO", "2026-10-30", use_cache=False)
    assert data is not None
    assert data["dividend_cagr_3yr"] is None
    assert "dividend_series" in err


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

    svc.fetch_dividend_growth_pullback_analysis("KO", "2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    svc.fetch_dividend_growth_pullback_analysis("KO", "2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls
