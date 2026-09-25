"""
Shared dedup helpers for stock prediction evaluation records.

Retried/re-run predictions get appended to the eval log as new rows with the
same (symbol, prediction_origin_date, decision_horizon_days, target_date).
Left unfiltered, these retries are double-counted as independent evidence in
accuracy stats and calibration summaries. This module provides a single,
shared definition of "canonical record" (earliest timestamp wins) used by
every reader/aggregator of the eval log.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

DedupKey = Tuple[str, str, int, str]


def extract_dedup_key(record: Dict[str, Any]) -> Optional[DedupKey]:
    """(symbol, prediction_origin_date, decision_horizon_days, target_date), or None if unkeyable.

    Records missing any of these fields are left unkeyable on purpose — callers
    must pass them through untouched rather than dropping them, since we can't
    tell whether an unkeyable record duplicates another one.
    """
    spi = record.get("stock_prediction_input") or {}
    symbol = spi.get("symbol")
    origin_date = spi.get("prediction_origin_date")
    horizon_days = spi.get("decision_horizon_days")
    target_date = spi.get("target_date")
    if not symbol or not origin_date or horizon_days is None or not target_date:
        return None
    return (str(symbol), str(origin_date), int(horizon_days), str(target_date))


def record_timestamp(record: Dict[str, Any]) -> str:
    """ISO-8601 timestamp string, lexicographically sortable. Empty string if missing."""
    return record.get("timestamp") or ""


def dedup_records(
    records: List[Dict[str, Any]],
    key_fn=extract_dedup_key,
    ts_fn=record_timestamp,
) -> List[Dict[str, Any]]:
    """Drop later retries, keeping the earliest-timestamp record per dedup key.

    Unkeyable records (key_fn returns None) are never treated as duplicates and
    always survive. Relative order of surviving records is preserved from the
    original input list (not the sort order used to pick canonical records).
    """
    indexed = list(enumerate(records))
    # Stable sort by (timestamp, original_index) so "earliest attempt" wins
    # deterministically even when timestamps tie or are missing.
    by_time = sorted(indexed, key=lambda pair: (ts_fn(pair[1]), pair[0]))

    seen_keys = set()
    duplicate_indices = set()
    for idx, record in by_time:
        key = key_fn(record)
        if key is None:
            continue
        if key in seen_keys:
            duplicate_indices.add(idx)
        else:
            seen_keys.add(key)

    return [record for idx, record in indexed if idx not in duplicate_indices]


def sort_by_target_date(
    records: List[Dict[str, Any]],
    key_fn=extract_dedup_key,
    ts_fn=record_timestamp,
) -> List[Dict[str, Any]]:
    """Ascending by (target_date, timestamp); robust to non-chronological append order.

    Records whose target_date can't be determined sort first (empty string),
    matching the conservative "don't assume freshness" default.
    """
    def sort_key(record: Dict[str, Any]) -> Tuple[str, str]:
        key = key_fn(record)
        target_date = key[3] if key is not None else ""
        return (target_date, ts_fn(record))

    return sorted(records, key=sort_key)
