"""Tests for core/social_attention_service.py -- Research Expansion Program,
Component 2 (ApeWisdom Reddit attention, free, keyless, LIVE-ONLY)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tools"))


def test_fetch_reddit_attention_found(monkeypatch):
    import social_attention_service as sas
    import apewisdom_client

    monkeypatch.setattr(apewisdom_client, "find_symbol_mentions", lambda sym: {
        "status": "SUCCESS", "found": True, "rank": 5, "mentions": 100, "mentions_24h_ago": 60, "upvotes": 300,
    })
    data, err = sas.fetch_reddit_attention("TSLA")
    assert err == ""
    assert data["mentions"] == 100
    assert data["mentions_24h_change"] == 40
    assert data["rank"] == 5


def test_fetch_reddit_attention_not_found_is_not_an_error(monkeypatch):
    """A symbol with no current Reddit chatter is a real, meaningful zero --
    not an error state."""
    import social_attention_service as sas
    import apewisdom_client

    monkeypatch.setattr(apewisdom_client, "find_symbol_mentions", lambda sym: {"status": "SUCCESS", "found": False})
    data, err = sas.fetch_reddit_attention("OBSCURESTOCK")
    assert err == ""
    assert data == {"mentions": 0, "mentions_24h_change": 0, "rank": None}


def test_fetch_reddit_attention_api_error_propagates(monkeypatch):
    import social_attention_service as sas
    import apewisdom_client

    monkeypatch.setattr(apewisdom_client, "find_symbol_mentions",
                         lambda sym: {"status": "ERROR", "error_type": "TIMEOUT", "message": "Request timed out"})
    data, err = sas.fetch_reddit_attention("TSLA")
    assert data is None
    assert err == "Request timed out"


def test_find_symbol_mentions_searches_multiple_pages(monkeypatch):
    """A symbol on page 2 (not page 1) must still be found."""
    import apewisdom_client as ac

    def fake_page(page, filter_name="all-stocks", timeout=15):
        if page == 1:
            return {"status": "SUCCESS", "data": {"results": [{"ticker": "AAA", "rank": 1, "mentions": 50}]}}
        if page == 2:
            return {"status": "SUCCESS", "data": {"results": [{"ticker": "TSLA", "rank": 55, "mentions": 10, "mentions_24h_ago": 5, "upvotes": 20}]}}
        return {"status": "SUCCESS", "data": {"results": []}}

    import unittest.mock as mock
    with mock.patch.object(ac, "get_mentions_page", side_effect=fake_page):
        result = ac.find_symbol_mentions("TSLA")
    assert result["found"] is True
    assert result["rank"] == 55
