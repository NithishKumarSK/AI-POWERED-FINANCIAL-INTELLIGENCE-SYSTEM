"""
Tests for core/stockbee_episodic_pivot_analyzer_service.py -- the live
orchestrator wiring earnings_trade_analyzer_service and
free_news_service's live Yahoo headlines into the ported
stockbee_episodic_pivot_analyzer pipeline. No real network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import stockbee_episodic_pivot_analyzer_service as svc
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "stockbee_episodic_pivot_cache.json")
    return svc


def _chrono_bars(start_date: str, n_days: int, price=100.0):
    import datetime as _dt
    d0 = _dt.date.fromisoformat(start_date)
    out = []
    for i in range(n_days):
        d = d0 + _dt.timedelta(days=i)
        out.append({"date": d.isoformat(), "open": price, "high": price * 1.01, "low": price * 0.99, "close": price, "volume": 1_000_000})
    return out


def test_fetch_episodic_pivot_analysis_uses_earnings_source_when_available(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import earnings_trade_analyzer_service as eta
    import free_news_service as fns
    import historical_price_service as hps

    monkeypatch.setattr(eta, "fetch_earnings_trade_analysis", lambda sym, as_of: ({"composite": {"grade": "A", "composite_score": 92.0}, "gap": {"gap_pct": 8.0}}, ""))
    monkeypatch.setattr(fns, "fetch_most_recent_earnings_8k", lambda sym, as_of: ({"earnings_date": "2026-10-28", "items": "2.02,9.01"}, ""))
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (_chrono_bars("2026-08-01", 90), "", {}))

    data, err = svc.fetch_episodic_pivot_analysis("AAPL", "2026-10-30", use_cache=False)
    assert data is not None
    assert err == ""
    assert data["catalyst_type"] == "earnings"
    assert data["source_grade"] == "A"


def test_fetch_episodic_pivot_analysis_falls_back_to_yahoo_headlines(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import earnings_trade_analyzer_service as eta
    import free_news_service as fns
    import historical_price_service as hps

    monkeypatch.setattr(eta, "fetch_earnings_trade_analysis", lambda sym, as_of: (None, "no recent earnings"))
    monkeypatch.setattr(fns, "fetch_yahoo_headline_tags", lambda sym: ({"headline_count": 1, "tags": {}, "titles": ["Company wins major new government contract"]}, ""))
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (_chrono_bars("2026-08-01", 90), "", {}))

    data, err = svc.fetch_episodic_pivot_analysis("TEST", "2026-10-30", use_cache=False)
    assert data is not None
    assert err == ""
    assert data["catalyst_type"] == "major_contract"


def test_fetch_episodic_pivot_analysis_no_catalyst_is_an_honest_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import earnings_trade_analyzer_service as eta
    import free_news_service as fns

    monkeypatch.setattr(eta, "fetch_earnings_trade_analysis", lambda sym, as_of: (None, "no recent earnings"))
    monkeypatch.setattr(fns, "fetch_yahoo_headline_tags", lambda sym: ({"headline_count": 1, "tags": {}, "titles": ["Company holds annual picnic"]}, ""))

    data, err = svc.fetch_episodic_pivot_analysis("TEST", "2026-10-30", use_cache=False)
    assert data is None
    assert "No catalyst keyword matched" in err


def test_second_call_reuses_cache_not_a_second_fetch(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import earnings_trade_analyzer_service as eta
    import free_news_service as fns
    import historical_price_service as hps

    call_count = {"n": 0}

    def fake_eta(sym, as_of):
        call_count["n"] += 1
        return {"composite": {"grade": "B", "composite_score": 75.0}, "gap": {"gap_pct": 5.0}}, ""

    monkeypatch.setattr(eta, "fetch_earnings_trade_analysis", fake_eta)
    monkeypatch.setattr(fns, "fetch_most_recent_earnings_8k", lambda sym, as_of: ({"earnings_date": "2026-10-28", "items": "2.02,9.01"}, ""))
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda sym, a, b: (_chrono_bars("2026-08-01", 90), "", {}))

    svc.fetch_episodic_pivot_analysis("AAPL", "2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    svc.fetch_episodic_pivot_analysis("AAPL", "2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls
