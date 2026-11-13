"""
Tests for core/stockbee_setup_fluency_trainer_service.py -- the JSONL
persistence wrapper + ingestion from stockbee_momentum_burst_service +
forward-outcome maturation from historical_price_service. No real
network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def test_ingest_momentum_burst_candidate_persists_a_record(monkeypatch, tmp_path):
    import stockbee_momentum_burst_service as mbs
    import stockbee_setup_fluency_trainer_service as svc

    candidate = {
        "symbol": "AAPL", "date": "2026-10-28", "primary_trigger": "4pct_breakout",
        "trigger_tags": ["4pct_breakout"], "soft_failure_tags": [], "reject_reasons": [],
        "rating": "A-", "setup_score": 85, "state": "ACTIONABLE_DAY1",
        "entry_reference": 100.0, "stop_reference": 95.0, "risk_pct_to_stop": 5.0,
        "day_gain_pct": 5.0, "volume_ratio_1d": 2.0, "close_location_pct": 90.0,
        "prior_base_days": 10, "base_width_pct": 7.0,
    }
    monkeypatch.setattr(mbs, "fetch_momentum_burst_analysis", lambda sym, as_of: (candidate, ""))

    store_path = tmp_path / "model_book.jsonl"
    stats, err = svc.ingest_momentum_burst_candidate("AAPL", "2026-10-28", path=store_path)
    assert err == ""
    assert stats["inserted"] == 1

    records = svc.load_model_book(store_path)
    assert len(records) == 1
    assert records[0]["record_id"] == "stockbee_mb:AAPL:2026-10-28:4pct_breakout"


def test_ingest_momentum_burst_candidate_propagates_fetch_error(monkeypatch, tmp_path):
    import stockbee_momentum_burst_service as mbs
    import stockbee_setup_fluency_trainer_service as svc

    monkeypatch.setattr(mbs, "fetch_momentum_burst_analysis", lambda sym, as_of: (None, "no price history"))
    stats, err = svc.ingest_momentum_burst_candidate("AAPL", "2026-10-28", path=tmp_path / "model_book.jsonl")
    assert err == "no price history"
    assert stats == {}


def test_ingest_twice_upserts_not_duplicates(monkeypatch, tmp_path):
    import stockbee_momentum_burst_service as mbs
    import stockbee_setup_fluency_trainer_service as svc

    candidate = {
        "symbol": "AAPL", "date": "2026-10-28", "primary_trigger": "4pct_breakout",
        "trigger_tags": [], "soft_failure_tags": [], "reject_reasons": [], "rating": "B",
        "setup_score": 72, "state": "MANUAL_REVIEW", "entry_reference": 100.0, "stop_reference": 96.0,
    }
    monkeypatch.setattr(mbs, "fetch_momentum_burst_analysis", lambda sym, as_of: (candidate, ""))

    store_path = tmp_path / "model_book.jsonl"
    svc.ingest_momentum_burst_candidate("AAPL", "2026-10-28", path=store_path)
    svc.ingest_momentum_burst_candidate("AAPL", "2026-10-28", path=store_path)
    assert len(svc.load_model_book(store_path)) == 1


def test_mature_pending_outcomes_updates_records_with_forward_prices(monkeypatch, tmp_path):
    import historical_price_service as hps
    import stockbee_setup_fluency_trainer_service as svc

    store_path = tmp_path / "model_book.jsonl"
    record = {
        "record_id": "stockbee_mb:AAPL:2026-06-01:4pct_breakout", "symbol": "AAPL", "setup_date": "2026-06-01",
        "entry_reference": 100.0, "stop_reference": 95.0, "matured": False, "outcomes": {},
    }
    svc.save_model_book([record], store_path)

    def fake_fetch(sym, start, end):
        import datetime as dt
        d0 = dt.date(2026, 6, 1)
        bars = []
        price = 100.0
        for i in range(10):
            d = d0 + dt.timedelta(days=i)
            price *= 1.02
            bars.append({"date": d.isoformat(), "open": price, "high": price * 1.01, "low": price * 0.99, "close": price, "volume": 1_000_000})
        return bars, "", {}
    monkeypatch.setattr(hps, "fetch_price_history_for_range", fake_fetch)

    stats, err = svc.mature_pending_outcomes("2026-06-10", path=store_path)
    assert err == ""
    assert stats["matured"] == 1

    records = svc.load_model_book(store_path)
    assert records[0]["matured"] is True


def test_mature_pending_outcomes_no_pending_records_is_a_noop(tmp_path):
    import stockbee_setup_fluency_trainer_service as svc
    stats, err = svc.mature_pending_outcomes("2026-06-10", path=tmp_path / "model_book.jsonl")
    assert err == ""
    assert stats["updated"] == 0


def test_summarize_reads_from_store(tmp_path):
    import stockbee_setup_fluency_trainer_service as svc
    records = [{
        "record_id": f"r{i}", "symbol": "AAPL", "setup_date": "2026-06-01", "matured": True,
        "overall_outcome": "WORKED", "rating": "A", "primary_trigger": "4pct_breakout", "setup_tags": ["tag_a"],
        "outcomes": {"5d": {"forward_return_pct": 5.0, "mfe_pct": 6.0, "mae_pct": -1.0, "stop_hit": False}, "3d": {"forward_return_pct": 3.0}},
    } for i in range(4)]
    svc.save_model_book(records, tmp_path / "model_book.jsonl")

    summary = svc.summarize(group_by_fields=["rating"], min_sample=3, path=tmp_path / "model_book.jsonl")
    assert summary["matured_records"] == 4
    assert summary["groups"]["rating"][0]["group"] == "A"
