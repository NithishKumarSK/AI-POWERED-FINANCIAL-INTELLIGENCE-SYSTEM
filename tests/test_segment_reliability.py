"""Tests for core/segment_reliability.py -- Phase 2 of the accuracy improvement
program: classifying a (symbol, horizon_bucket) segment as PROVEN / UNPROVEN /
INSUFFICIENT_DATA from its real historical track record."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _rec(symbol: str, horizon_days: int, directional_match: bool) -> dict:
    return {
        "stock_prediction_input": {"symbol": symbol, "decision_horizon_days": horizon_days},
        "comparison": {"directional_match": directional_match},
    }


# ── classify_segment: pure threshold logic ───────────────────────────────────

def test_classify_segment_insufficient_data_below_min_n():
    from segment_reliability import classify_segment, MIN_SAMPLE_SIZE
    assert classify_segment(MIN_SAMPLE_SIZE - 1, 90.0) == "INSUFFICIENT_DATA"


def test_classify_segment_insufficient_data_none_rate():
    from segment_reliability import classify_segment
    assert classify_segment(50, None) == "INSUFFICIENT_DATA"


def test_classify_segment_proven_at_threshold():
    from segment_reliability import classify_segment, MIN_SAMPLE_SIZE, PROVEN_THRESHOLD_PCT
    assert classify_segment(MIN_SAMPLE_SIZE, PROVEN_THRESHOLD_PCT) == "PROVEN"


def test_classify_segment_unproven_just_below_threshold():
    from segment_reliability import classify_segment, MIN_SAMPLE_SIZE, PROVEN_THRESHOLD_PCT
    assert classify_segment(MIN_SAMPLE_SIZE, PROVEN_THRESHOLD_PCT - 0.1) == "UNPROVEN"


def test_classify_segment_unproven_near_coin_flip():
    from segment_reliability import classify_segment
    assert classify_segment(17, 18.0) == "UNPROVEN"  # the real TSLA system-wide figure found this session


def test_classify_segment_proven_real_spy_figure():
    from segment_reliability import classify_segment
    assert classify_segment(18, 88.9) == "PROVEN"  # the real SPY 0-7d figure found this session


# ── segment_label ──────────────────────────────────────────────────────────

def test_segment_label_format():
    from segment_reliability import segment_label
    assert segment_label("tsla", 5) == "TSLA|0-7d"
    assert segment_label("SPY", 90) == "SPY|61-120d"


# ── classify_records: end-to-end from record-shaped dicts ────────────────────

def test_classify_records_filters_by_symbol_and_bucket():
    from segment_reliability import classify_records
    records = (
        [_rec("TSLA", 5, True)] * 3
        + [_rec("TSLA", 90, False)] * 20      # different horizon bucket -- must not count
        + [_rec("SPY", 5, True)] * 20          # different symbol -- must not count
    )
    result = classify_records(records, "TSLA", 5)
    assert result["n"] == 3  # only the TSLA/0-7d rows
    assert result["classification"] == "INSUFFICIENT_DATA"  # n=3 < MIN_SAMPLE_SIZE


def test_classify_records_proven_segment():
    from segment_reliability import classify_records
    records = [_rec("SPY", 5, True)] * 16 + [_rec("SPY", 5, False)] * 2  # 16/18 = 88.9%
    result = classify_records(records, "SPY", 7)  # horizon=7 -> same "0-7d" bucket as horizon=5
    assert result["n"] == 18
    assert result["direction_match_pct"] == 88.9
    assert result["classification"] == "PROVEN"


def test_classify_records_no_matching_rows():
    from segment_reliability import classify_records
    result = classify_records([_rec("SPY", 5, True)], "TSLA", 90)
    assert result["n"] == 0
    assert result["classification"] == "INSUFFICIENT_DATA"


def test_classify_records_symbol_case_insensitive():
    from segment_reliability import classify_records
    records = [_rec("spy", 5, True)] * 15
    result = classify_records(records, "SPY", 5)
    assert result["n"] == 15
