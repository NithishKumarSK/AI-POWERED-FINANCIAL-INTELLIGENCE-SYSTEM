"""
Pytest: News/Sentiment Leakage Prevention Tests (Phase 3).

Guarantees fetch_news_sentiment_score() never counts an article published
after as_of_date, even if the upstream Alpha Vantage API's own time_to filter
were bypassed, wrong, or returned extra rows -- the same "don't trust,
verify" discipline validate_no_leakage() applies to price bars elsewhere in
this codebase. No real API calls; the Alpha Vantage client is monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tools"))


def _article(time_published: str, score: float) -> dict:
    return {"time_published": time_published, "overall_sentiment_score": score}


# ── fetch_news_sentiment_score: leakage guard ─────────────────────────────────

def test_excludes_articles_published_after_as_of_date(monkeypatch):
    """Even if the mocked upstream API (incorrectly) returns a future article,
    it must never be counted."""
    import news_sentiment_service as nss

    def fake_get(function, params=None):
        assert function == "NEWS_SENTIMENT"
        return {"status": "SUCCESS", "data": {"feed": [
            _article("20260301T090000", 0.5),   # before as_of_date -- counted
            _article("20260303T090000", -0.8),  # ON as_of_date -- counted (same day, not leakage)
            _article("20260305T090000", 0.9),   # AFTER as_of_date -- must be excluded
        ]}}

    # fetch_news_sentiment_score does `from alpha_vantage_client import
    # alpha_vantage_get` inside the function body -- patch the real source
    # module so the inline import picks up the fake at call time.
    import alpha_vantage_client
    monkeypatch.setattr(alpha_vantage_client, "alpha_vantage_get", fake_get)

    data, err = nss.fetch_news_sentiment_score("TSLA", "2026-03-03")
    assert err == ""
    assert data["article_count"] == 2  # the 03-01 and 03-03 articles only
    assert data["avg_sentiment_score"] == round((0.5 + -0.8) / 2, 4)


def test_all_articles_after_as_of_date_yields_empty_not_error(monkeypatch):
    import news_sentiment_service as nss
    import alpha_vantage_client

    def fake_get(function, params=None):
        return {"status": "SUCCESS", "data": {"feed": [
            _article("20260310T090000", 0.5),
            _article("20260312T090000", 0.5),
        ]}}
    monkeypatch.setattr(alpha_vantage_client, "alpha_vantage_get", fake_get)

    data, err = nss.fetch_news_sentiment_score("TSLA", "2026-03-01")
    assert err == ""
    assert data["article_count"] == 0
    assert data["avg_sentiment_score"] is None


def test_malformed_as_of_date_rejected(monkeypatch):
    import news_sentiment_service as nss
    data, err = nss.fetch_news_sentiment_score("TSLA", "not-a-date")
    assert data is None
    assert err != ""


def test_api_error_propagates_as_error_string(monkeypatch):
    import news_sentiment_service as nss
    import alpha_vantage_client

    def fake_get(function, params=None):
        return {"status": "ERROR", "error_type": "RATE_LIMIT", "message": "Thank you for using Alpha Vantage!"}
    monkeypatch.setattr(alpha_vantage_client, "alpha_vantage_get", fake_get)

    data, err = nss.fetch_news_sentiment_score("TSLA", "2026-03-03")
    assert data is None
    assert "Alpha Vantage" in err


def test_malformed_feed_shape_degrades_gracefully(monkeypatch):
    import news_sentiment_service as nss
    import alpha_vantage_client

    def fake_get(function, params=None):
        return {"status": "SUCCESS", "data": {"feed": "not-a-list"}}
    monkeypatch.setattr(alpha_vantage_client, "alpha_vantage_get", fake_get)

    data, err = nss.fetch_news_sentiment_score("TSLA", "2026-03-03")
    assert data is None
    assert "feed" in err.lower() or "shape" in err.lower()


# ── earnings_days_away: window bounds ─────────────────────────────────────────

def test_earnings_days_away_within_window():
    from news_sentiment_service import earnings_days_away
    earnings = {"quarterly_earnings": [{"reported_date": "2026-03-10"}]}
    days = earnings_days_away(earnings, as_of_date="2026-03-01", target_date="2026-03-31")
    assert days == 9


def test_earnings_days_away_excludes_dates_before_as_of():
    """A past earnings date (before as_of_date) is not an upcoming-window
    event and must not be reported as if it were still ahead."""
    from news_sentiment_service import earnings_days_away
    earnings = {"quarterly_earnings": [{"reported_date": "2026-02-01"}]}
    days = earnings_days_away(earnings, as_of_date="2026-03-01", target_date="2026-03-31")
    assert days is None


def test_earnings_days_away_excludes_dates_after_target():
    from news_sentiment_service import earnings_days_away
    earnings = {"quarterly_earnings": [{"reported_date": "2026-04-15"}]}
    days = earnings_days_away(earnings, as_of_date="2026-03-01", target_date="2026-03-31")
    assert days is None


def test_earnings_days_away_no_data():
    from news_sentiment_service import earnings_days_away
    assert earnings_days_away(None, "2026-03-01", "2026-03-31") is None
    assert earnings_days_away({"quarterly_earnings": []}, "2026-03-01", "2026-03-31") is None


def test_earnings_days_away_picks_nearest_when_multiple():
    from news_sentiment_service import earnings_days_away
    earnings = {"quarterly_earnings": [
        {"reported_date": "2026-03-20"},
        {"reported_date": "2026-03-05"},  # nearest
    ]}
    days = earnings_days_away(earnings, as_of_date="2026-03-01", target_date="2026-03-31")
    assert days == 4
