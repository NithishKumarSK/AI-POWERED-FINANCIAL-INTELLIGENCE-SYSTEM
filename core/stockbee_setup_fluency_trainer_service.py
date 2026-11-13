"""
stockbee_setup_fluency_trainer_service.py -- thin persistence wrapper for
core/stockbee_setup_fluency_trainer.py's model book. NOT wired into
feature_packet (see that module's own docstring for why). Meant to be
called manually -- e.g. once a day after running
core/stockbee_momentum_burst_service.py on a watchlist -- or from a future
cron, the same way the source skill's own CLI is meant to be run daily.

Store format: JSONL at data/stockbee_model_book.jsonl, one record per
line, matching the source skill's own on-disk format exactly (so a file
produced by either implementation is interchangeable).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STORE_PATH = ROOT / "data" / "stockbee_model_book.jsonl"


def load_model_book(path: Path = STORE_PATH) -> list:
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if isinstance(record, dict):
                records.append(record)
    return records


def save_model_book(records: list, path: Path = STORE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = sorted(records, key=lambda r: (r.get("setup_date", ""), r.get("symbol", ""), r.get("record_id", "")))
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def ingest_momentum_burst_candidate(symbol: str, as_of_date: str, path: Path = STORE_PATH) -> Tuple[dict, str]:
    """Fetch today's Momentum Burst analysis for `symbol` (via
    core/stockbee_momentum_burst_service.py) and upsert it into the model
    book as a study example. Non-studyable or REJECTED-with-no-setup-date
    candidates are skipped honestly, not force-recorded.

    Returns (upsert_stats, error_string).
    """
    from stockbee_momentum_burst_service import fetch_momentum_burst_analysis
    from stockbee_setup_fluency_trainer import is_studyable_candidate, make_record, upsert_records

    candidate, err = fetch_momentum_burst_analysis(symbol, as_of_date)
    if not candidate:
        return {}, err

    studyable, reason = is_studyable_candidate(candidate)
    if not studyable:
        return {"inserted": 0, "updated": 0, "total": len(load_model_book(path)), "skipped_reason": reason}, ""

    record = make_record(candidate)
    existing = load_model_book(path)
    merged, stats = upsert_records(existing, [record])
    save_model_book(merged, path)
    return stats, ""


def mature_pending_outcomes(as_of_date: str, path: Path = STORE_PATH) -> Tuple[dict, str]:
    """Fetch forward price history for every pending record's symbol (via
    historical_price_service.py) and mature 3d/5d outcomes where enough
    future bars now exist on/before as_of_date.
    """
    from stockbee_momentum_burst_screener import Bar
    from stockbee_setup_fluency_trainer import update_record_outcomes

    records = load_model_book(path)
    pending_symbols = sorted({r["symbol"] for r in records if not r.get("matured")})
    if not pending_symbols:
        return {"updated": 0, "matured": 0, "still_pending": 0, "skipped_no_prices": 0}, ""

    import datetime as _dt
    from historical_price_service import fetch_price_history_for_range

    as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
    earliest_setup = min((r["setup_date"] for r in records if not r.get("matured")), default=as_of_date[:10])
    start_dt = _dt.datetime.strptime(earliest_setup[:10], "%Y-%m-%d").date()

    prices_by_symbol = {}
    for symbol in pending_symbols:
        bars, _err, _coverage = fetch_price_history_for_range(symbol, start_dt.isoformat(), as_of_dt.isoformat())
        if not bars:
            continue
        as_of = as_of_date[:10]
        prices_by_symbol[symbol] = [
            Bar(date=b["date"], open=b["open"], high=b["high"], low=b["low"], close=b["close"], volume=int(b.get("volume", 0)))
            for b in bars if b.get("date", "") <= as_of  # LEAKAGE SAFETY
        ]

    records, stats = update_record_outcomes(records, prices_by_symbol)
    save_model_book(records, path)
    return stats, ""


def summarize(group_by_fields: list = None, min_sample: int = 3, path: Path = STORE_PATH) -> dict:
    from stockbee_setup_fluency_trainer import summarize_model_book
    records = load_model_book(path)
    return summarize_model_book(records, group_by_fields or ["setup_tags", "rating", "primary_trigger"], min_sample=min_sample)
