"""
Pytest: sec_financials_service.py -- tag-staleness regression (a real bug
caught this session: AAPL's "Revenues" XBRL tag only has data through
FY2018, before the switch to RevenueFromContractWithCustomerExcludingAssessedTax
post-ASC606; picking the first tag with ANY data silently returned 7-year-
stale figures) and leakage safety. No real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tools"))


def _annual_entry(end, start, val, filed, form="10-K"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


def _fake_facts(tags: dict):
    return {"status": "SUCCESS", "data": {"facts": {"us-gaap": {
        tag: {"units": {"USD": entries}} for tag, entries in tags.items()
    }}}}


def test_picks_most_recent_revenue_tag_not_first_with_any_data(monkeypatch):
    """Regression test for the real bug: a stale first-choice tag with old
    data must not win over a second tag with current data."""
    import sec_financials_service as sfs
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "_get", lambda url: _fake_facts({
        "Revenues": [_annual_entry("2018-09-29", "2017-09-30", 265595000000, "2018-11-05")],
        "RevenueFromContractWithCustomerExcludingAssessedTax": [
            _annual_entry("2025-09-27", "2024-09-28", 416161000000, "2025-10-31"),
        ],
    }))

    data, err = sfs.fetch_key_financials("TEST", "2026-10-30")
    assert err == ""
    assert data["revenue"] == 416161000000
    assert data["period_end"] == "2025-09-27"


def test_period_end_reflects_most_recent_metric_not_first_resolved(monkeypatch):
    """Regression test: period_end must track the most recent period seen
    across ALL metrics, not freeze on whichever metric resolved first."""
    import sec_financials_service as sfs
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})

    def fake_get(url):
        return {"status": "SUCCESS", "data": {"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [_annual_entry("2018-09-29", "2017-09-30", 1, "2018-11-05")]}},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": []}},
            "NetIncomeLoss": {"units": {"USD": [_annual_entry("2025-09-27", "2024-09-28", 2, "2025-10-31")]}},
            "EarningsPerShareDiluted": {"units": {"USD/shares": []}},
        }}}}
    monkeypatch.setattr(sec_edgar_client, "_get", fake_get)

    data, err = sfs.fetch_key_financials("TEST", "2026-10-30")
    assert data["period_end"] == "2025-09-27"  # net_income's recent period, not revenue's stale one


def test_excludes_facts_filed_after_as_of_date(monkeypatch):
    import sec_financials_service as sfs
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "_get", lambda url: _fake_facts({
        "Revenues": [
            _annual_entry("2025-09-27", "2024-09-28", 999, "2026-03-01"),  # filed AFTER as_of -- excluded
            _annual_entry("2024-09-28", "2023-09-30", 500, "2024-11-01"),  # filed before as_of -- counted
        ],
    }))

    data, err = sfs.fetch_key_financials("TEST", "2026-01-01")
    assert data["revenue"] == 500
    assert data["period_end"] == "2024-09-28"


def test_quarterly_span_entries_excluded_from_annual_selection(monkeypatch):
    """A ~90-day quarterly entry must never be mistaken for an annual one."""
    import sec_financials_service as sfs
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "_get", lambda url: _fake_facts({
        "Revenues": [
            _annual_entry("2026-06-27", "2026-03-29", 100, "2026-07-31"),   # ~90 days -- quarterly, excluded
            _annual_entry("2025-09-27", "2024-09-28", 400, "2025-10-31"),   # ~365 days -- annual, kept
        ],
    }))

    data, err = sfs.fetch_key_financials("TEST", "2026-10-30")
    assert data["revenue"] == 400


def test_no_usable_data_returns_error(monkeypatch):
    import sec_financials_service as sfs
    import sec_edgar_client
    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "_get", lambda url: _fake_facts({}))
    data, err = sfs.fetch_key_financials("TEST", "2026-10-30")
    assert data is None
    assert err != ""


def test_cik_lookup_failure_propagates(monkeypatch):
    import sec_financials_service as sfs
    import sec_edgar_client
    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "ERROR", "message": "not found"})
    data, err = sfs.fetch_key_financials("NOTASYMBOL", "2026-10-30")
    assert data is None
    assert err == "not found"
