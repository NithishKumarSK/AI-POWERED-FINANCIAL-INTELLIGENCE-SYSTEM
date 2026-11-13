"""
Pytest: sec_financials_service.py's quarterly/annual EPS+revenue series
and dividend/cash-flow-coverage extraction (added this session for
canslim-screener and dividend-growth-pullback-screener). No real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tools"))


def _entry(end, start, val, filed, form="10-Q"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


def _fake_facts_multi(tags_by_unit: dict):
    """tags_by_unit: {tag: {unit: entries}}"""
    return {"status": "SUCCESS", "data": {"facts": {"us-gaap": {
        tag: {"units": units} for tag, units in tags_by_unit.items()
    }}}}


def _patch_cik(monkeypatch, sec_edgar_client):
    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol", lambda sym: {"status": "SUCCESS", "cik": "0000000001"})


# ── fetch_quarterly_eps_revenue_series ────────────────────────────────────

def test_quarterly_eps_series_excludes_cumulative_ytd_entries(monkeypatch):
    import sec_financials_service as sfs
    import sec_edgar_client
    _patch_cik(monkeypatch, sec_edgar_client)

    monkeypatch.setattr(sec_edgar_client, "_get", lambda url: _fake_facts_multi({
        "EarningsPerShareDiluted": {"USD/shares": [
            _entry("2026-10-02", "2026-07-04", 0.93, "2026-10-28"),   # ~90d standalone quarter -- kept
            _entry("2026-10-02", "2026-01-01", 2.86, "2026-10-28"),   # ~9mo YTD -- excluded
            _entry("2026-07-03", "2026-04-04", 1.03, "2026-07-29"),
            _entry("2026-04-03", "2026-01-01", 0.91, "2026-04-30"),
            _entry("2025-09-26", "2025-06-28", 0.86, "2025-10-23"),
            _entry("2025-06-27", "2025-03-29", 0.88, "2025-07-25"),
        ]},
        "Revenues": {"USD": [
            _entry("2026-10-02", "2026-07-04", 13_380_000_000, "2026-10-28"),
            _entry("2026-07-03", "2026-04-04", 13_380_000_000, "2026-07-29"),
            _entry("2026-04-03", "2026-01-01", 12_472_000_000, "2026-04-30"),
            _entry("2025-09-26", "2025-06-28", 12_455_000_000, "2025-10-23"),
        ]},
    }))

    data, err = sfs.fetch_quarterly_eps_revenue_series("TEST", "2026-10-30")
    assert err == ""
    # 6 fixture entries; only the 2026-01-01..2026-10-02 (~9mo/274-day) YTD
    # entry falls outside the 80-100 day standalone-quarter span and is excluded.
    assert len(data) == 5
    assert data[0]["date"] == "2026-10-02"
    assert data[0]["eps"] == 0.93
    assert data[0]["revenue"] == 13_380_000_000


def test_quarterly_eps_series_no_standalone_quarters_is_an_error(monkeypatch):
    import sec_financials_service as sfs
    import sec_edgar_client
    _patch_cik(monkeypatch, sec_edgar_client)
    monkeypatch.setattr(sec_edgar_client, "_get", lambda url: _fake_facts_multi({
        "EarningsPerShareDiluted": {"USD/shares": [_entry("2026-12-31", "2026-01-01", 3.0, "2027-02-01", form="10-K")]},
    }))
    data, err = sfs.fetch_quarterly_eps_revenue_series("TEST", "2026-10-30")
    assert data is None
    assert "No standalone-quarter" in err


# ── fetch_annual_eps_revenue_series ────────────────────────────────────────

def test_annual_eps_series_returns_newest_first(monkeypatch):
    import sec_financials_service as sfs
    import sec_edgar_client
    _patch_cik(monkeypatch, sec_edgar_client)
    monkeypatch.setattr(sec_edgar_client, "_get", lambda url: _fake_facts_multi({
        "EarningsPerShareDiluted": {"USD/shares": [
            _entry("2026-12-31", "2026-01-01", 10.0, "2027-02-01", form="10-K"),
            _entry("2025-12-31", "2025-01-01", 7.0, "2026-02-01", form="10-K"),
            _entry("2024-12-31", "2024-01-01", 5.0, "2025-02-01", form="10-K"),
            _entry("2023-12-31", "2023-01-01", 3.5, "2024-02-01", form="10-K"),
        ]},
        "Revenues": {"USD": [
            _entry("2026-12-31", "2026-01-01", 1_000_000_000, "2027-02-01", form="10-K"),
        ]},
    }))
    data, err = sfs.fetch_annual_eps_revenue_series("TEST", "2027-03-01")
    assert err == ""
    assert [d["date"] for d in data] == ["2026-12-31", "2025-12-31", "2024-12-31", "2023-12-31"]
    assert data[0]["revenue"] == 1_000_000_000
    assert data[1]["revenue"] is None  # no revenue entry for that year


# ── fetch_annual_dividend_series ───────────────────────────────────────────

def test_annual_dividend_series_derives_per_share_from_total_and_shares(monkeypatch):
    import sec_financials_service as sfs
    import sec_edgar_client
    _patch_cik(monkeypatch, sec_edgar_client)
    monkeypatch.setattr(sec_edgar_client, "_get", lambda url: _fake_facts_multi({
        "PaymentsOfDividends": {"USD": [
            _entry("2025-12-31", "2025-01-01", 8_779_000_000, "2026-02-20", form="10-K"),
            _entry("2024-12-31", "2024-01-01", 8_359_000_000, "2025-02-20", form="10-K"),
            _entry("2023-12-31", "2023-01-01", 7_952_000_000, "2024-02-20", form="10-K"),
            _entry("2022-12-31", "2022-01-01", 7_616_000_000, "2023-02-20", form="10-K"),
        ]},
        "WeightedAverageNumberOfDilutedSharesOutstanding": {"shares": [
            _entry("2025-12-31", "2025-01-01", 4_313_000_000, "2026-02-20", form="10-K"),
        ]},
    }))
    data, err = sfs.fetch_annual_dividend_series("TEST", "2026-10-30")
    assert err == ""
    assert data[0]["date"] == "2025-12-31"
    assert round(data[0]["dividend_per_share"], 2) == 2.04
    assert data[1]["dividend_per_share"] is None  # no shares entry for 2024


def test_annual_dividend_series_falls_back_across_tag_names(monkeypatch):
    """Regression for the real finding: JNJ has no PaymentsOfDividends or
    PaymentsOfDividendsCommonStock at all -- only PaymentsOfOrdinaryDividends."""
    import sec_financials_service as sfs
    import sec_edgar_client
    _patch_cik(monkeypatch, sec_edgar_client)
    monkeypatch.setattr(sec_edgar_client, "_get", lambda url: _fake_facts_multi({
        "PaymentsOfOrdinaryDividends": {"USD": [
            _entry("2025-12-28", "2025-01-01", 12_381_000_000, "2026-02-01", form="10-K"),
        ]},
    }))
    data, err = sfs.fetch_annual_dividend_series("TEST", "2026-10-30")
    assert err == ""
    assert data[0]["dividends_paid_total"] == 12_381_000_000


def test_annual_dividend_series_no_data_is_an_error(monkeypatch):
    import sec_financials_service as sfs
    import sec_edgar_client
    _patch_cik(monkeypatch, sec_edgar_client)
    monkeypatch.setattr(sec_edgar_client, "_get", lambda url: _fake_facts_multi({}))
    data, err = sfs.fetch_annual_dividend_series("TEST", "2026-10-30")
    assert data is None
    assert err != ""


# ── fetch_cash_flow_coverage ───────────────────────────────────────────────

def test_cash_flow_coverage_computes_fcf(monkeypatch):
    import sec_financials_service as sfs
    import sec_edgar_client
    _patch_cik(monkeypatch, sec_edgar_client)
    monkeypatch.setattr(sec_edgar_client, "_get", lambda url: _fake_facts_multi({
        "PaymentsOfDividends": {"USD": [_entry("2025-12-31", "2025-01-01", 8_779_000_000, "2026-02-20", form="10-K")]},
        "NetCashProvidedByUsedInOperatingActivities": {"USD": [_entry("2025-12-31", "2025-01-01", 7_408_000_000, "2026-02-20", form="10-K")]},
        "PaymentsToAcquirePropertyPlantAndEquipment": {"USD": [_entry("2025-12-31", "2025-01-01", 2_112_000_000, "2026-02-20", form="10-K")]},
    }))
    data, err = sfs.fetch_cash_flow_coverage("TEST", "2026-10-30")
    assert err == ""
    assert data["dividends_paid"] == 8_779_000_000
    assert data["free_cash_flow"] == 5_296_000_000
    assert data["period_end"] == "2025-12-31"


def test_cash_flow_coverage_partial_data_still_usable(monkeypatch):
    import sec_financials_service as sfs
    import sec_edgar_client
    _patch_cik(monkeypatch, sec_edgar_client)
    monkeypatch.setattr(sec_edgar_client, "_get", lambda url: _fake_facts_multi({
        "NetCashProvidedByUsedInOperatingActivities": {"USD": [_entry("2025-12-31", "2025-01-01", 7_408_000_000, "2026-02-20", form="10-K")]},
    }))
    data, err = sfs.fetch_cash_flow_coverage("TEST", "2026-10-30")
    assert err == ""
    assert "dividends_paid" not in data
    assert "free_cash_flow" not in data  # needs both OCF and capex
    assert data["operating_cash_flow"] == 7_408_000_000
