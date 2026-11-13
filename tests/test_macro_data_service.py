"""
Pytest: macro_data_service.py leakage + caching + degrade-gracefully tests
(to-do item #9's macro/rate data piece).

No real API calls; alpha_vantage_client.alpha_vantage_get is monkeypatched,
and the disk cache is redirected to a tmp_path per test so tests never read
or write the real data/macro_data_cache.json.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tools"))


def _series(function_name: str, points: list) -> dict:
    return {"status": "SUCCESS", "data": {
        "name": function_name, "interval": "monthly", "unit": "percent",
        "data": points,
    }}


def _isolate_cache(monkeypatch, tmp_path):
    import macro_data_service as mds
    monkeypatch.setattr(mds, "CACHE_PATH", tmp_path / "macro_cache.json")
    return mds


# ── fetch_macro_snapshot: leakage guard ──────────────────────────────────────

def test_excludes_data_points_after_as_of_date(monkeypatch, tmp_path):
    mds = _isolate_cache(monkeypatch, tmp_path)
    import alpha_vantage_client

    def fake_get(function, params=None):
        if function == "FEDERAL_FUNDS_RATE":
            return _series(function, [
                {"date": "2026-03-01", "value": "4.50"},  # after as_of -- must be excluded
                {"date": "2026-02-01", "value": "4.40"},  # on-or-before as_of -- counted
                {"date": "2026-01-01", "value": "4.30"},
            ])
        return _series(function, [{"date": "2026-02-01", "value": "4.10"}])

    monkeypatch.setattr(alpha_vantage_client, "alpha_vantage_get", fake_get)

    data, err = mds.fetch_macro_snapshot("2026-02-15")
    assert data["fed_funds_rate_pct"] == 4.40  # NOT the 03-01 value


def test_value_as_of_picks_most_recent_not_first(monkeypatch, tmp_path):
    mds = _isolate_cache(monkeypatch, tmp_path)
    import alpha_vantage_client

    def fake_get(function, params=None):
        # Deliberately out-of-order to confirm the function doesn't just take
        # the first row -- it must find the max date <= as_of.
        return _series(function, [
            {"date": "2026-01-01", "value": "1.0"},
            {"date": "2026-03-01", "value": "3.0"},
            {"date": "2026-02-01", "value": "2.0"},
        ])

    monkeypatch.setattr(alpha_vantage_client, "alpha_vantage_get", fake_get)
    data, err = mds.fetch_macro_snapshot("2026-02-28")
    assert data["fed_funds_rate_pct"] == 2.0
    assert data["treasury_10y_yield_pct"] == 2.0


def test_no_data_points_on_or_before_as_of_date_omits_field(monkeypatch, tmp_path):
    mds = _isolate_cache(monkeypatch, tmp_path)
    import alpha_vantage_client

    def fake_get(function, params=None):
        return _series(function, [{"date": "2026-05-01", "value": "9.9"}])

    monkeypatch.setattr(alpha_vantage_client, "alpha_vantage_get", fake_get)
    data, err = mds.fetch_macro_snapshot("2026-01-01")
    assert data is None
    assert err != ""


# ── degrade gracefully ────────────────────────────────────────────────────────

def test_no_key_degrades_to_error_not_exception(monkeypatch, tmp_path):
    mds = _isolate_cache(monkeypatch, tmp_path)
    import alpha_vantage_client

    def fake_get(function, params=None):
        return {"status": "ERROR", "error_type": "NO_KEY", "message": "ALPHA_VANTAGE_API_KEY not set in .env"}

    monkeypatch.setattr(alpha_vantage_client, "alpha_vantage_get", fake_get)
    data, err = mds.fetch_macro_snapshot("2026-02-15")
    assert data is None
    assert "NO_KEY" in err or "not set" in err


def test_partial_failure_still_returns_the_series_that_worked(monkeypatch, tmp_path):
    mds = _isolate_cache(monkeypatch, tmp_path)
    import alpha_vantage_client

    def fake_get(function, params=None):
        if function == "FEDERAL_FUNDS_RATE":
            return _series(function, [{"date": "2026-02-01", "value": "4.40"}])
        return {"status": "ERROR", "error_type": "RATE_LIMIT", "message": "Thank you for using Alpha Vantage!"}

    monkeypatch.setattr(alpha_vantage_client, "alpha_vantage_get", fake_get)
    data, err = mds.fetch_macro_snapshot("2026-02-15")
    assert data["fed_funds_rate_pct"] == 4.40
    assert "treasury_10y_yield_pct" not in data
    assert "treasury_10y" in err and "Alpha Vantage" in err


def test_malformed_response_shape_degrades_gracefully(monkeypatch, tmp_path):
    mds = _isolate_cache(monkeypatch, tmp_path)
    import alpha_vantage_client

    def fake_get(function, params=None):
        return {"status": "SUCCESS", "data": {"data": "not-a-list"}}

    monkeypatch.setattr(alpha_vantage_client, "alpha_vantage_get", fake_get)
    data, err = mds.fetch_macro_snapshot("2026-02-15")
    assert data is None
    assert "shape" in err.lower() or "unexpected" in err.lower()


# ── caching ───────────────────────────────────────────────────────────────────

def test_second_call_reuses_cache_not_a_second_http_call(monkeypatch, tmp_path):
    mds = _isolate_cache(monkeypatch, tmp_path)
    import alpha_vantage_client

    call_count = {"n": 0}

    def fake_get(function, params=None):
        call_count["n"] += 1
        return _series(function, [{"date": "2026-02-01", "value": "4.40"}])

    monkeypatch.setattr(alpha_vantage_client, "alpha_vantage_get", fake_get)
    mds.fetch_macro_snapshot("2026-02-15")
    first_calls = call_count["n"]
    mds.fetch_macro_snapshot("2026-02-20")  # different as_of_date, same underlying series
    assert call_count["n"] == first_calls  # cache hit, no new HTTP calls


def test_stale_cache_used_as_fallback_when_refetch_fails(monkeypatch, tmp_path):
    mds = _isolate_cache(monkeypatch, tmp_path)
    import alpha_vantage_client
    import time

    # Prime the cache with an entry that's already expired. Values are
    # floats, matching what _fetch_series itself writes (already converted
    # via float(pt["value"]) before caching) -- never raw strings.
    mds._save_cache({
        "fed_funds_rate": {"data": [{"date": "2026-01-01", "value": 4.30}], "fetched_at": 0},
        "treasury_10y":   {"data": [{"date": "2026-01-01", "value": 4.10}], "fetched_at": 0},
    })

    def fake_get(function, params=None):
        return {"status": "ERROR", "error_type": "RATE_LIMIT", "message": "throttled"}

    monkeypatch.setattr(alpha_vantage_client, "alpha_vantage_get", fake_get)
    data, err = mds.fetch_macro_snapshot("2026-01-15")
    assert data["fed_funds_rate_pct"] == 4.30  # fell back to the stale cache, not empty
    assert "stale cache" in err.lower()
