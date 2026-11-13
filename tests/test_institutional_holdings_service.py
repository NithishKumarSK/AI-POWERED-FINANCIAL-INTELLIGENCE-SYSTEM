"""
Pytest: 13F institutional holdings tracking
(core/institutional_holdings_service.py) -- fuzzy issuer-name matching,
XML parsing, and leakage safety for fetch_institutional_holders' cache-based
as_of_date filtering.

No real network calls; the on-disk cache path is redirected to tmp_path
per test.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tools"))


def _isolate_cache(monkeypatch, tmp_path):
    import institutional_holdings_service as ihs
    monkeypatch.setattr(ihs, "CACHE_PATH", tmp_path / "inst_cache.json")
    return ihs


# ── parse_info_table ──────────────────────────────────────────────────────

def test_parse_info_table_extracts_rows():
    from institutional_holdings_service import parse_info_table
    xml = b"""<?xml version="1.0"?>
    <informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable>
        <nameOfIssuer>APPLE INC</nameOfIssuer>
        <titleOfClass>COM</titleOfClass>
        <cusip>037833100</cusip>
        <value>1000000</value>
        <shrsOrPrnAmt><sshPrnamt>5000</sshPrnamt></shrsOrPrnAmt>
      </infoTable>
    </informationTable>"""
    rows = parse_info_table(xml)
    assert len(rows) == 1
    assert rows[0]["issuer"] == "APPLE INC"
    assert rows[0]["cusip"] == "037833100"
    assert rows[0]["value"] == 1000000.0
    assert rows[0]["shares"] == 5000.0


def test_parse_info_table_malformed_xml_raises():
    from institutional_holdings_service import parse_info_table
    import pytest
    with pytest.raises(Exception):
        parse_info_table(b"<not valid xml")


# ── _name_matches: fuzzy issuer-name matching ────────────────────────────

def test_name_matches_handles_punctuation_and_suffix_differences():
    from institutional_holdings_service import _name_matches
    assert _name_matches("APPLE INC", "Apple Inc.")
    assert _name_matches("ALPHABET INC", "Alphabet Inc. Class A")
    assert _name_matches("COCA COLA CO", "Coca-Cola Co")


def test_name_matches_rejects_unrelated_companies():
    from institutional_holdings_service import _name_matches
    assert not _name_matches("APPLE INC", "Microsoft Corp")
    assert not _name_matches("BANK OF AMER CORP", "Bank of New York Mellon Corp")


# ── fetch_institutional_holders: leakage safety ──────────────────────────

def _filer(name, filed, rows):
    return {"name": name, "person": "", "filed": filed, "period": "", "rows": rows}


def test_excludes_filings_filed_after_as_of_date(monkeypatch, tmp_path):
    ihs = _isolate_cache(monkeypatch, tmp_path)
    import sec_edgar_client
    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
        lambda sym: {"status": "SUCCESS", "cik": "0000000001", "company_name": "Test Company Inc."})
    ihs._save_cache({
        "filers": {
            "cik1": _filer("Early Fund", "2026-02-01", [{"issuer": "TEST COMPANY INC", "value": 100.0}]),
            "cik2": _filer("Late Fund", "2026-04-01", [{"issuer": "TEST COMPANY INC", "value": 999.0}]),
        },
        "built_at": "2026-04-15T00:00:00",
    })
    data, err = ihs.fetch_institutional_holders("TEST", as_of_date="2026-03-01")
    assert err == ""
    assert data["holder_count"] == 1
    assert data["holders"][0]["name"] == "Early Fund"


def test_no_cache_built_yet_is_an_error(monkeypatch, tmp_path):
    ihs = _isolate_cache(monkeypatch, tmp_path)
    import sec_edgar_client
    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
        lambda sym: {"status": "SUCCESS", "cik": "0000000001", "company_name": "Test Company Inc."})
    data, err = ihs.fetch_institutional_holders("TEST", as_of_date="2026-03-01")
    assert data is None
    assert "cache" in err.lower()


def test_no_holders_is_a_real_zero_not_an_error(monkeypatch, tmp_path):
    ihs = _isolate_cache(monkeypatch, tmp_path)
    import sec_edgar_client
    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
        lambda sym: {"status": "SUCCESS", "cik": "0000000001", "company_name": "Nobody Holds This Inc."})
    ihs._save_cache({
        "filers": {"cik1": _filer("Some Fund", "2026-02-01", [{"issuer": "SOMETHING ELSE", "value": 1.0}])},
        "built_at": "2026-04-15T00:00:00",
    })
    data, err = ihs.fetch_institutional_holders("TEST", as_of_date="2026-03-01")
    assert err == ""
    assert data["holder_count"] == 0


def test_cik_lookup_failure_propagates(monkeypatch, tmp_path):
    ihs = _isolate_cache(monkeypatch, tmp_path)
    import sec_edgar_client
    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
        lambda sym: {"status": "ERROR", "message": "not found"})
    data, err = ihs.fetch_institutional_holders("NOTASYMBOL", as_of_date="2026-03-01")
    assert data is None
    assert err == "not found"
