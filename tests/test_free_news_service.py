"""
Pytest: free_news_service.py leakage safety (SEC 8-K count) and keyword
tagging (Yahoo headlines), adapted from trader-news. No real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tools"))


def _fake_submissions(forms_dates):
    forms, dates = [], []
    for form, date in forms_dates:
        forms.append(form)
        dates.append(date)
    return {"status": "SUCCESS", "data": {"filings": {"recent": {"form": forms, "filingDate": dates}}}}


def _fake_submissions_with_items(forms_dates_items):
    forms, dates, items = [], [], []
    for form, date, item in forms_dates_items:
        forms.append(form)
        dates.append(date)
        items.append(item)
    return {"status": "SUCCESS", "data": {"filings": {"recent": {"form": forms, "filingDate": dates, "items": items}}}}


# ── fetch_most_recent_earnings_8k ────────────────────────────────────────────

def test_finds_most_recent_earnings_tagged_8k(monkeypatch):
    import free_news_service as fns
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "get_submissions", lambda cik: _fake_submissions_with_items([
        ("8-K", "2026-07-30", "2.02,9.01"),  # earnings
        ("8-K", "2026-08-20", "5.02"),       # NOT earnings (exec change) -- must be excluded
        ("8-K", "2026-10-29", "2.02,9.01"),  # most recent earnings
        ("10-K", "2026-10-29", ""),           # wrong form
    ]))

    data, err = fns.fetch_most_recent_earnings_8k("TEST", as_of_date="2026-10-30")
    assert err == ""
    assert data["earnings_date"] == "2026-10-29"
    assert data["items"] == "2.02,9.01"


def test_excludes_earnings_8k_filed_after_as_of_date(monkeypatch):
    import free_news_service as fns
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "get_submissions", lambda cik: _fake_submissions_with_items([
        ("8-K", "2026-04-30", "2.02,9.01"),
        ("8-K", "2026-07-30", "2.02,9.01"),  # AFTER as_of -- must be excluded (LEAKAGE SAFETY)
    ]))

    data, err = fns.fetch_most_recent_earnings_8k("TEST", as_of_date="2026-05-15")
    assert err == ""
    assert data["earnings_date"] == "2026-04-30"


def test_no_earnings_tagged_8k_is_an_honest_error(monkeypatch):
    import free_news_service as fns
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "get_submissions", lambda cik: _fake_submissions_with_items([
        ("8-K", "2026-04-20", "5.02"),
    ]))

    data, err = fns.fetch_most_recent_earnings_8k("TEST", as_of_date="2026-10-30")
    assert data is None
    assert "No earnings-tagged 8-K found" in err


# ── fetch_sec_8k_count: leakage safety ───────────────────────────────────────

def test_excludes_8k_filings_after_as_of_date(monkeypatch):
    import free_news_service as fns
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "get_submissions", lambda cik: _fake_submissions([
        ("8-K", "2026-03-01"),   # before as_of -- counted
        ("8-K", "2026-03-10"),   # AFTER as_of -- must be excluded
        ("10-K", "2026-03-01"),  # wrong form -- must be excluded
    ]))

    data, err = fns.fetch_sec_8k_count("TEST", as_of_date="2026-03-05", lookback_days=90)
    assert err == ""
    assert data["filing_count"] == 1
    assert data["most_recent_filed"] == "2026-03-01"


def test_lookback_window_excludes_old_8k_filings(monkeypatch):
    import free_news_service as fns
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "get_submissions", lambda cik: _fake_submissions([
        ("8-K", "2024-01-01"),
    ]))

    data, err = fns.fetch_sec_8k_count("TEST", as_of_date="2026-03-05", lookback_days=30)
    assert data["filing_count"] == 0
    assert data["most_recent_filed"] is None


def test_no_8k_filings_is_a_real_zero(monkeypatch):
    import free_news_service as fns
    import sec_edgar_client

    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "SUCCESS", "cik": "0000000001"})
    monkeypatch.setattr(sec_edgar_client, "get_submissions", lambda cik: _fake_submissions([]))

    data, err = fns.fetch_sec_8k_count("TEST", as_of_date="2026-03-05")
    assert err == ""
    assert data["filing_count"] == 0


def test_malformed_as_of_date_rejected():
    from free_news_service import fetch_sec_8k_count
    data, err = fetch_sec_8k_count("TEST", "not-a-date")
    assert data is None
    assert err != ""


def test_cik_lookup_failure_propagates(monkeypatch):
    import free_news_service as fns
    import sec_edgar_client
    monkeypatch.setattr(sec_edgar_client, "get_cik_for_symbol",
                         lambda sym: {"status": "ERROR", "message": "not found"})
    data, err = fns.fetch_sec_8k_count("NOTASYMBOL", "2026-03-05")
    assert data is None
    assert err == "not found"


# ── fetch_yahoo_headline_tags: keyword tagging ───────────────────────────────

_RSS_TEMPLATE = """<?xml version="1.0"?>
<rss version="2.0"><channel>
{items}
</channel></rss>"""


def _rss_with_titles(*titles):
    items = "\n".join(f"<item><title>{t}</title></item>" for t in titles)
    return _RSS_TEMPLATE.format(items=items)


class _FakeResp:
    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content.encode("utf-8")


def test_tags_headlines_by_category(monkeypatch):
    import free_news_service as fns
    import requests

    def fake_get(url, headers=None, timeout=20):
        return _FakeResp(200, _rss_with_titles(
            "Company beats earnings guidance",
            "Analyst upgrade sends stock higher",
            "Company announces dividend buyback",
            "Unrelated headline about nothing tagged",
        ))
    monkeypatch.setattr(requests, "get", fake_get)

    data, err = fns.fetch_yahoo_headline_tags("TEST")
    assert err == ""
    assert data["headline_count"] == 4
    assert data["tags"]["earnings"] == 1
    assert data["tags"]["analyst"] == 1
    assert data["tags"]["capital"] == 1
    assert "legal" not in data["tags"]  # zero-count tags are dropped, not shown as 0


def test_http_error_degrades_gracefully(monkeypatch):
    import free_news_service as fns
    import requests
    monkeypatch.setattr(requests, "get", lambda url, headers=None, timeout=20: _FakeResp(500, ""))
    data, err = fns.fetch_yahoo_headline_tags("TEST")
    assert data is None
    assert "500" in err


def test_no_headlines_is_a_real_zero(monkeypatch):
    import free_news_service as fns
    import requests
    monkeypatch.setattr(requests, "get", lambda url, headers=None, timeout=20: _FakeResp(200, _rss_with_titles()))
    data, err = fns.fetch_yahoo_headline_tags("TEST")
    assert err == ""
    assert data["headline_count"] == 0
    assert data["tags"] == {}
