"""
Pytest: Congress trade tracking (core/congress_trade_service.py) --
parsing correctness against real PDF-extract line shapes, and leakage
safety for fetch_congress_trades' cache-based as_of_date filtering.

No real network calls; the on-disk cache path is redirected to tmp_path
per test so tests never read or write the real
data/congress_trade_cache.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tools"))


def _isolate_cache(monkeypatch, tmp_path):
    import congress_trade_service as cts
    monkeypatch.setattr(cts, "CACHE_PATH", tmp_path / "congress_cache.json")
    return cts


# ── parse_ptr_text: anchor-based parsing against real PyMuPDF line shapes ──

def test_parse_single_transaction_ticker_directly_before_type():
    from congress_trade_service import parse_ptr_text
    text = "\n".join([
        "Amazon.com, Inc. - Common Stock",
        "(AMZN) [ST]",
        "S (partial)",
        "03/16/2026 03/16/2026",
        "$1,001 - $15,000",
        "Filing Status: New",
    ])
    rows = parse_ptr_text(text, filed="2026-03-31", doc_id="X1", member="Test Member")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AMZN"
    assert rows[0]["type"] == "S (partial)"
    assert rows[0]["date"] == "2026-03-16"
    assert rows[0]["amount_low"] == 1001
    assert rows[0]["amount_high"] == 15000


def test_parse_ticker_two_lines_before_type():
    """Covers "Apple Inc. - Common Stock (AAPL)" / "[ST]" / type -- the
    ticker is on the line BEFORE the trailing [ST] continuation line."""
    from congress_trade_service import parse_ptr_text
    text = "\n".join([
        "Apple Inc. - Common Stock (AAPL)",
        "[ST]",
        "P",
        "01/02/2026 01/05/2026",
        "$1,001 - $15,000",
    ])
    rows = parse_ptr_text(text, filed="2026-01-15", doc_id="X2", member="Test Member")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["type"] == "P"
    assert rows[0]["type_name"] == "purchase"


def test_parse_multiple_transactions_with_description_between():
    """Description text between two transactions must not be mistaken for
    the next transaction's asset name, and must not leak a false ticker
    (description references tickers unparenthesized, e.g. "AMZN – 25
    shares", which must NOT match the ticker-in-parens requirement)."""
    from congress_trade_service import parse_ptr_text
    text = "\n".join([
        "Amazon.com, Inc. - Common Stock",
        "(AMZN) [ST]",
        "S (partial)",
        "03/16/2026 03/16/2026",
        "$1,001 - $15,000",
        "Filing Status: New",
        "Subholding Of: Putnam Investments",
        "Description: The full transaction included the following sales: AMZN – 25 shares sold",
        "AAPL – 20 shares sold",
        "Apple Inc. - Common Stock (AAPL)",
        "[ST]",
        "S (partial)",
        "03/16/2026 03/16/2026",
        "$1,001 - $15,000",
    ])
    rows = parse_ptr_text(text, filed="2026-03-31", doc_id="X3", member="Test Member")
    assert len(rows) == 2
    assert rows[0]["ticker"] == "AMZN"
    assert rows[1]["ticker"] == "AAPL"


def test_parse_skips_page_header_lines():
    from congress_trade_service import parse_ptr_text
    text = "\n".join([
        "ID",
        "Owner Asset",
        "Transaction",
        "Type",
        "Date",
        "Notification",
        "Date",
        "Amount",
        "Cap.",
        "Gains >",
        "$200?",
        "Berkshire Hathaway Inc. New",
        "Common Stock (BRK.B) [ST]",
        "S (partial)",
        "03/16/2026 03/16/2026",
        "$1,001 - $15,000",
    ])
    rows = parse_ptr_text(text, filed="2026-03-31", doc_id="X4", member="Test Member")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "BRK.B"


def test_parse_no_type_line_yields_no_rows():
    from congress_trade_service import parse_ptr_text
    text = "Some unrelated text with no transaction markers at all."
    rows = parse_ptr_text(text, filed="2026-03-31", doc_id="X5", member="Test Member")
    assert rows == []


def test_parse_index_filters_to_ptr_type_only():
    from congress_trade_service import parse_index
    xml = b"""<?xml version="1.0"?>
    <FinancialDisclosure>
      <Member><Last>Smith</Last><First>Jane</First><FilingType>P</FilingType>
        <FilingDate>03/01/2026</FilingDate><DocID>111</DocID><Year>2026</Year></Member>
      <Member><Last>Jones</Last><First>Bob</First><FilingType>O</FilingType>
        <FilingDate>03/02/2026</FilingDate><DocID>222</DocID><Year>2026</Year></Member>
    </FinancialDisclosure>"""
    rows = parse_index(xml, 2026)
    assert len(rows) == 1
    assert rows[0]["doc_id"] == "111"


# ── fetch_congress_trades: leakage safety (cache-based as_of_date filter) ──

def _tx(ticker, type_, filed, date="2026-01-01"):
    return {"ticker": ticker, "type": type_, "date": date, "filed": filed}


def test_excludes_transactions_filed_after_as_of_date(monkeypatch, tmp_path):
    cts = _isolate_cache(monkeypatch, tmp_path)
    cts._save_cache({
        "by_ticker": {
            "TEST": [
                _tx("TEST", "P", filed="2026-03-01"),   # before as_of -- counted
                _tx("TEST", "S", filed="2026-03-10"),   # AFTER as_of -- must be excluded
            ]
        },
        "scanned_doc_ids": [], "built_at": "2026-03-15T00:00:00",
    })
    data, err = cts.fetch_congress_trades("TEST", as_of_date="2026-03-05", lookback_days=90)
    assert err == ""
    assert data["buy_count"] == 1
    assert data["sell_count"] == 0


def test_lookback_window_excludes_old_transactions(monkeypatch, tmp_path):
    cts = _isolate_cache(monkeypatch, tmp_path)
    cts._save_cache({
        "by_ticker": {"TEST": [_tx("TEST", "P", filed="2025-01-01")]},
        "scanned_doc_ids": [], "built_at": "2026-03-15T00:00:00",
    })
    data, err = cts.fetch_congress_trades("TEST", as_of_date="2026-03-05", lookback_days=30)
    assert data["buy_count"] == 0
    assert data["transactions_considered"] == 0


def test_no_cache_built_yet_is_an_error_not_silent_zero(monkeypatch, tmp_path):
    cts = _isolate_cache(monkeypatch, tmp_path)
    data, err = cts.fetch_congress_trades("TEST", as_of_date="2026-03-05")
    assert data is None
    assert "cache" in err.lower()


def test_cache_built_but_symbol_unseen_is_a_real_zero_not_an_error(monkeypatch, tmp_path):
    cts = _isolate_cache(monkeypatch, tmp_path)
    cts._save_cache({"by_ticker": {}, "scanned_doc_ids": [], "built_at": "2026-03-15T00:00:00"})
    data, err = cts.fetch_congress_trades("UNSEEN", as_of_date="2026-03-05")
    assert err == ""
    assert data["buy_count"] == 0
    assert data["sell_count"] == 0


def test_net_signal_bounded_and_correct_sign(monkeypatch, tmp_path):
    cts = _isolate_cache(monkeypatch, tmp_path)
    cts._save_cache({
        "by_ticker": {"TEST": [
            _tx("TEST", "P", filed="2026-03-01"),
            _tx("TEST", "P", filed="2026-03-01"),
            _tx("TEST", "S", filed="2026-03-01"),
        ]},
        "scanned_doc_ids": [], "built_at": "2026-03-15T00:00:00",
    })
    data, err = cts.fetch_congress_trades("TEST", as_of_date="2026-03-05", lookback_days=90)
    assert data["buy_count"] == 2
    assert data["sell_count"] == 1
    assert -1.0 <= data["net_signal"] <= 1.0
    assert data["net_signal"] > 0


def test_malformed_as_of_date_rejected(monkeypatch, tmp_path):
    cts = _isolate_cache(monkeypatch, tmp_path)
    data, err = cts.fetch_congress_trades("TEST", "not-a-date")
    assert data is None
    assert err != ""
