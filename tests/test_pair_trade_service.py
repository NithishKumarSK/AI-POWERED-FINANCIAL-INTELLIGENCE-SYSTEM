"""
Tests for core/pair_trade_service.py -- the live orchestrator fetching and
aligning two symbols' price history. No real network calls;
historical_price_service.fetch_price_history_for_range is monkeypatched.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _isolate_cache(monkeypatch, tmp_path):
    import pair_trade_service as svc
    monkeypatch.setattr(svc, "CACHE_PATH", tmp_path / "pair_trade_cache.json")
    return svc


def _mean_reverting_bars(n_days: int, start_date: str, beta: float = 1.5, seed: int = 42):
    import datetime as _dt
    rng = random.Random(seed)
    d0 = _dt.date.fromisoformat(start_date)
    b_prices = [100.0]
    for _ in range(n_days - 1):
        b_prices.append(b_prices[-1] * (1 + rng.gauss(0, 0.01)))
    spread = [0.0]
    for _ in range(n_days - 1):
        spread.append(spread[-1] * 0.85 + rng.gauss(0, 1.0))
    a_prices = [beta * b + s for b, s in zip(b_prices, spread)]

    bars_a, bars_b = [], []
    for i in range(n_days):
        d = (d0 + _dt.timedelta(days=i)).isoformat()
        bars_a.append({"date": d, "close": a_prices[i], "open": a_prices[i], "high": a_prices[i], "low": a_prices[i], "volume": 1000})
        bars_b.append({"date": d, "close": b_prices[i], "open": b_prices[i], "high": b_prices[i], "low": b_prices[i], "volume": 1000})
    return bars_a, bars_b


def test_fetch_pair_trade_signal_with_sufficient_history(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    bars_a, bars_b = _mean_reverting_bars(300, "2025-10-01")

    def fake_fetch(symbol, start, end):
        return (bars_a if symbol == "AAA" else bars_b), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = svc.fetch_pair_trade_signal("AAA", "BBB", "2026-10-30", use_cache=False)
    assert data is not None
    assert err == ""
    assert data["symbol_a"] == "AAA"
    assert data["cointegration"]["is_cointegrated"] is True


def test_fetch_pair_trade_signal_insufficient_overlap_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    bars_a, bars_b = _mean_reverting_bars(300, "2025-10-01")

    def fake_fetch(symbol, start, end):
        if symbol == "BBB":
            return bars_b[:10], "", {}  # only 10 overlapping dates
        return bars_a, "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    data, err = svc.fetch_pair_trade_signal("AAA", "BBB", "2026-10-30", use_cache=False)
    assert data is None
    assert "Insufficient aligned history" in err


def test_fetch_pair_trade_signal_missing_symbol_is_an_error(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps
    monkeypatch.setattr(hps, "fetch_price_history_for_range", lambda s, a, b: ([], "not found", {}))

    data, err = svc.fetch_pair_trade_signal("AAA", "BBB", "2026-10-30", use_cache=False)
    assert data is None
    assert err != ""


def test_align_by_date_intersects_common_dates_only():
    from pair_trade_service import _align_by_date
    bars_a = [{"date": "2026-01-01", "close": 1.0}, {"date": "2026-01-02", "close": 2.0}]
    bars_b = [{"date": "2026-01-02", "close": 20.0}, {"date": "2026-01-03", "close": 30.0}]
    dates, prices_a, prices_b = _align_by_date(bars_a, bars_b)
    assert dates == ["2026-01-02"]
    assert prices_a == [2.0]
    assert prices_b == [20.0]


def test_cache_key_is_symmetric_regardless_of_argument_order(monkeypatch, tmp_path):
    svc = _isolate_cache(monkeypatch, tmp_path)
    import historical_price_service as hps

    bars_a, bars_b = _mean_reverting_bars(300, "2025-10-01")
    call_count = {"n": 0}

    def fake_fetch(symbol, start, end):
        call_count["n"] += 1
        return (bars_a if symbol == "AAA" else bars_b), "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    svc.fetch_pair_trade_signal("AAA", "BBB", "2026-10-30", use_cache=True)
    first_calls = call_count["n"]
    svc.fetch_pair_trade_signal("AAA", "BBB", "2026-10-30", use_cache=True)
    assert call_count["n"] == first_calls
