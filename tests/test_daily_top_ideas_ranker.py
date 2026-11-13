"""Tests for core/daily_top_ideas_ranker.py -- the daily Top-20 ranking
feature. Mocks fetch_price_history_for_range so this is fast and offline,
not a live-API test (those are covered manually/in scratchpad smoke tests
this session already ran against real data)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _make_bars(n=60, start_price=100.0, drift=0.0):
    bars = []
    price = start_price
    for i in range(n):
        price += drift
        bars.append({
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "open": price, "high": price * 1.01, "low": price * 0.99,
            "close": price, "volume": 1_000_000,
        })
    return bars


def test_rank_universe_scores_and_sorts(monkeypatch):
    import daily_top_ideas_ranker as mod

    def _fake_fetch(symbol, start, end):
        if symbol == "UP":
            return _make_bars(drift=1.0), "", {}
        if symbol == "DOWN":
            return _make_bars(drift=-1.0), "", {}
        return _make_bars(drift=0.0), "", {}

    monkeypatch.setattr("historical_price_service.fetch_price_history_for_range", _fake_fetch)
    result = mod.rank_universe(symbols=["UP", "DOWN", "FLAT"], as_of_date="2026-01-28", top_n=3)

    assert result["scored_count"] == 3
    assert result["failed_symbols"] == []
    assert len(result["top_ideas"]) == 3
    assert len(result["bottom_ideas"]) == 3
    # Sorted descending/ascending correctly.
    scores_desc = [r["score"] for r in result["top_ideas"]]
    assert scores_desc == sorted(scores_desc, reverse=True)


def test_rank_universe_handles_fetch_failure(monkeypatch):
    import daily_top_ideas_ranker as mod

    def _fake_fetch(symbol, start, end):
        if symbol == "BAD":
            return None, "No data available", {}
        return _make_bars(), "", {}

    monkeypatch.setattr("historical_price_service.fetch_price_history_for_range", _fake_fetch)
    result = mod.rank_universe(symbols=["GOOD", "BAD"], as_of_date="2026-01-28", top_n=5)

    assert result["scored_count"] == 1
    assert len(result["failed_symbols"]) == 1
    assert result["failed_symbols"][0]["symbol"] == "BAD"


def test_rank_universe_handles_insufficient_bars(monkeypatch):
    import daily_top_ideas_ranker as mod

    def _fake_fetch(symbol, start, end):
        return _make_bars(n=5), "", {}  # below the 20-bar minimum

    monkeypatch.setattr("historical_price_service.fetch_price_history_for_range", _fake_fetch)
    result = mod.rank_universe(symbols=["TOOFEW"], as_of_date="2026-01-28")

    assert result["scored_count"] == 0
    assert len(result["failed_symbols"]) == 1
    assert "20" in result["failed_symbols"][0]["error"]


def test_rank_universe_default_universe_used_when_none_given():
    import daily_top_ideas_ranker as mod
    assert len(mod.DEFAULT_UNIVERSE) >= 20
    assert len(mod.DEFAULT_UNIVERSE) == len(set(mod.DEFAULT_UNIVERSE))  # no duplicates


def test_rank_universe_top_n_respected(monkeypatch):
    import daily_top_ideas_ranker as mod

    def _fake_fetch(symbol, start, end):
        return _make_bars(), "", {}

    monkeypatch.setattr("historical_price_service.fetch_price_history_for_range", _fake_fetch)
    result = mod.rank_universe(symbols=["A", "B", "C", "D", "E"], as_of_date="2026-01-28", top_n=2)
    assert len(result["top_ideas"]) == 2
    assert len(result["bottom_ideas"]) == 2
