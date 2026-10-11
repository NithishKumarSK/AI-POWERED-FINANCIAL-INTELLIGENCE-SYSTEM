"""
Pytest: Insider Activity Leakage Prevention Tests (Research Expansion Program,
Component 1).

Guarantees fetch_insider_activity() never counts a Form 4 filing (or an
individual transaction within one) dated after as_of_date -- same "don't
trust upstream alone" discipline as test_news_sentiment_no_leakage.py. No
real network calls; the SEC EDGAR client is monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tools"))


_FORM4_XML_TEMPLATE = """<?xml version="1.0"?>
<ownershipDocument>
    <issuer><issuerTradingSymbol>TEST</issuerTradingSymbol></issuer>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <transactionDate><value>{date}</value></transactionDate>
            <transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>{shares}</value></transactionShares>
                <transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
</ownershipDocument>"""


def _fake_submissions(forms_dates_accns):
    forms, dates, accns, docs = [], [], [], []
    for form, date, accn in forms_dates_accns:
        forms.append(form)
        dates.append(date)
        accns.append(accn)
        docs.append(f"{accn}.xml")
    return {
        "status": "SUCCESS",
        "data": {"filings": {"recent": {"form": forms, "filingDate": dates, "accessionNumber": accns, "primaryDocument": docs}}},
    }


def test_excludes_filings_dated_after_as_of_date(monkeypatch):
    """Even if SEC's submissions API returns a filing dated after as_of_date
    (shouldn't happen in practice, but must never be trusted blindly), it
    must not be counted."""
    import insider_activity_service as ias
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "get_submissions",
                         lambda cik: _fake_submissions([
                             ("4", "2026-03-01", "0000000001-26-000001"),   # before as_of -- counted
                             ("4", "2026-03-10", "0000000001-26-000002"),   # AFTER as_of -- must be excluded
                         ]))

    def fake_doc(cik, accn, doc_name):
        if accn.endswith("000001"):
            return {"status": "SUCCESS", "text": _FORM4_XML_TEMPLATE.format(date="2026-03-01", code="P", shares=100, ad="A")}
        return {"status": "SUCCESS", "text": _FORM4_XML_TEMPLATE.format(date="2026-03-10", code="S", shares=50, ad="D")}
    monkeypatch.setattr(sec_edgar_client, "get_filing_document_text", fake_doc)

    data, err = ias.fetch_insider_activity("TEST", as_of_date="2026-03-05", lookback_days=30)
    assert err == ""
    assert data["buy_count"] == 1
    assert data["sell_count"] == 0  # the 03-10 SELL filing must be excluded
    assert data["filings_parsed"] == 1


def test_excludes_transactions_dated_after_as_of_even_within_an_included_filing(monkeypatch):
    """Defense in depth: even a filing whose FILING date is in-window must
    have each individual TRANSACTION re-checked against as_of_date."""
    import insider_activity_service as ias
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "get_submissions",
                         lambda cik: _fake_submissions([("4", "2026-03-05", "0000000001-26-000001")]))

    # Filing's own filing-date is in-window, but the transaction it reports
    # happened after as_of_date (a backdated/late filing scenario).
    def fake_doc(cik, accn, doc_name):
        return {"status": "SUCCESS", "text": _FORM4_XML_TEMPLATE.format(date="2026-03-10", code="P", shares=100, ad="A")}
    monkeypatch.setattr(sec_edgar_client, "get_filing_document_text", fake_doc)

    data, err = ias.fetch_insider_activity("TEST", as_of_date="2026-03-05", lookback_days=30)
    assert err == ""
    assert data["buy_count"] == 0  # transaction itself is after as_of_date
    assert data["sell_count"] == 0


def test_lookback_window_excludes_old_filings(monkeypatch):
    import insider_activity_service as ias
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "get_submissions",
                         lambda cik: _fake_submissions([("4", "2025-01-01", "0000000001-26-000001")]))  # way outside lookback

    def fake_doc(cik, accn, doc_name):
        return {"status": "SUCCESS", "text": _FORM4_XML_TEMPLATE.format(date="2025-01-01", code="P", shares=100, ad="A")}
    monkeypatch.setattr(sec_edgar_client, "get_filing_document_text", fake_doc)

    data, err = ias.fetch_insider_activity("TEST", as_of_date="2026-03-05", lookback_days=30)
    assert data["filings_parsed"] == 0
    assert data["buy_count"] == 0


def test_malformed_as_of_date_rejected():
    from insider_activity_service import fetch_insider_activity
    data, err = fetch_insider_activity("TEST", "not-a-date")
    assert data is None
    assert err != ""


def test_cik_lookup_failure_propagates(monkeypatch):
    import insider_activity_service as ias
    import sec_edgar_client
    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "ERROR", "error_type": "SYMBOL_NOT_FOUND", "message": "not found"})
    data, err = ias.fetch_insider_activity("NOTASYMBOL", "2026-03-05")
    assert data is None
    assert err == "not found"


def test_net_signal_bounded_and_correct_sign(monkeypatch):
    """3 buys, 1 sell -> net_signal should be positive and in [-1, 1]."""
    import insider_activity_service as ias
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    filings = [("4", "2026-03-01", f"0000000001-26-00000{i}") for i in range(1, 5)]
    monkeypatch.setattr(sec_edgar_client, "get_submissions", lambda cik: _fake_submissions(filings))

    codes = ["A", "A", "A", "D"]  # 3 acquired, 1 disposed
    def fake_doc(cik, accn, doc_name):
        idx = int(accn[-1]) - 1
        return {"status": "SUCCESS", "text": _FORM4_XML_TEMPLATE.format(date="2026-03-01", code="P", shares=10, ad=codes[idx])}
    monkeypatch.setattr(sec_edgar_client, "get_filing_document_text", fake_doc)

    data, err = ias.fetch_insider_activity("TEST", as_of_date="2026-03-05", lookback_days=30)
    assert data["buy_count"] == 3
    assert data["sell_count"] == 1
    assert data["net_signal"] == 0.5
    assert -1.0 <= data["net_signal"] <= 1.0


def test_malformed_xml_skipped_not_fatal(monkeypatch):
    """One broken filing must not crash the whole aggregate."""
    import insider_activity_service as ias
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "get_submissions",
                         lambda cik: _fake_submissions([("4", "2026-03-01", "0000000001-26-000001")]))
    monkeypatch.setattr(sec_edgar_client, "get_filing_document_text",
                         lambda cik, accn, doc_name: {"status": "SUCCESS", "text": "<not valid xml"})

    data, err = ias.fetch_insider_activity("TEST", as_of_date="2026-03-05", lookback_days=30)
    assert err == ""
    assert data["buy_count"] == 0
    assert data["sell_count"] == 0
