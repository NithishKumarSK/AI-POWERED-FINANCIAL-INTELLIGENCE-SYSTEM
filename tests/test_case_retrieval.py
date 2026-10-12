"""Tests for core/case_retrieval.py — nearest-neighbor retrieval of similar
past validated predictions (the self-learning layer).

Leakage safety is the non-negotiable property here: a candidate whose own
prediction_origin_date is not strictly before the current prediction's
origin_date must never be returned, even if the caller's own filtering was
buggy -- this module is defense-in-depth, not the only line of defense.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import bootstrap_paths  # noqa: E402
bootstrap_paths.add_module_paths()

from case_retrieval import find_similar_cases  # noqa: E402


def _fp(return_1d=1.0, rsi=50.0, adx=20.0):
    """Minimal OK-status feature packet with a few FEATURE_SPEC fields set."""
    return {
        "status": "OK",
        "returns": {"return_1d": return_1d, "return_5d": None, "return_10d": None,
                     "return_20d": None, "return_60d": None},
        "trend": {"price_vs_sma_20_pct": None, "price_vs_sma_50_pct": None, "ADX_14": adx},
        "momentum": {"RSI_14": rsi, "MACD_histogram": None},
    }


def _record(symbol, horizon_days, origin_date, ai_decision, actual_decision,
            decision_match, directional_match=True, return_1d=1.0, rsi=50.0, adx=20.0,
            abs_return_error_pct=2.0):
    return {
        "stock_prediction_input": {
            "symbol": symbol,
            "decision_horizon_days": horizon_days,
            "prediction_origin_date": origin_date,
        },
        "ai_prediction": {
            "decision": ai_decision,
            "_feature_packet": _fp(return_1d=return_1d, rsi=rsi, adx=adx),
        },
        "actual_validation": {"actual_decision": actual_decision},
        "comparison": {
            "decision_match": decision_match,
            "directional_match": directional_match,
            "abs_return_error_pct": abs_return_error_pct,
        },
    }


def test_returns_empty_list_when_no_current_vector():
    assert find_similar_cases({}, "TSLA", 7, [_record("TSLA", 7, "2026-01-01", "BUY", "BUY", True)]) == []


def test_returns_empty_list_when_no_records():
    assert find_similar_cases(_fp(), "TSLA", 7, []) == []


def test_prefers_same_symbol_over_same_segment():
    current = _fp(return_1d=1.0, rsi=50.0, adx=20.0)
    records = [
        _record("TSLA", 7, "2026-01-01", "BUY", "BUY", True, return_1d=1.1, rsi=51.0, adx=21.0),
        _record("AAPL", 7, "2026-01-01", "SELL", "SELL", True, return_1d=1.0, rsi=50.0, adx=20.0),
    ]
    results = find_similar_cases(current, "TSLA", 7, records, k=5)
    assert len(results) == 2
    assert results[0]["match_tier"] == "SAME_SYMBOL"
    assert results[0]["symbol"] == "TSLA"


def test_closest_vector_ranked_first_within_same_tier():
    current = _fp(return_1d=1.0, rsi=50.0, adx=20.0)
    far  = _record("TSLA", 7, "2026-01-01", "BUY", "SELL", False, return_1d=10.0, rsi=90.0, adx=5.0)
    near = _record("TSLA", 7, "2026-01-02", "BUY", "BUY", True, return_1d=1.05, rsi=50.5, adx=20.1)
    results = find_similar_cases(current, "TSLA", 7, [far, near], k=5)
    assert results[0]["origin_date"] == "2026-01-02"  # the near one
    assert results[0]["distance"] <= results[1]["distance"]


def test_excludes_unresolved_records():
    current = _fp()
    unresolved = _record("TSLA", 7, "2026-01-01", "BUY", "?", None)
    results = find_similar_cases(current, "TSLA", 7, [unresolved], k=5)
    assert results == []


def test_excludes_records_missing_feature_packet():
    current = _fp()
    r = _record("TSLA", 7, "2026-01-01", "BUY", "BUY", True)
    r["ai_prediction"]["_feature_packet"] = None
    assert find_similar_cases(current, "TSLA", 7, [r], k=5) == []


def test_leakage_guard_excludes_candidate_on_or_after_current_origin_date():
    """The defense-in-depth check: even if a caller passes an unfiltered
    records list, a candidate whose own origin_date is not strictly before
    the current prediction's origin_date must never be returned."""
    current = _fp()
    same_day   = _record("TSLA", 7, "2026-06-01", "BUY", "BUY", True)
    future     = _record("TSLA", 7, "2026-06-15", "BUY", "BUY", True)
    genuinely_past = _record("TSLA", 7, "2026-05-01", "BUY", "BUY", True)

    results = find_similar_cases(
        current, "TSLA", 7, [same_day, future, genuinely_past],
        current_origin_date="2026-06-01", k=5,
    )
    returned_dates = {r["origin_date"] for r in results}
    assert "2026-06-01" not in returned_dates  # not strictly before -- excluded
    assert "2026-06-15" not in returned_dates  # future -- excluded
    assert returned_dates == {"2026-05-01"}


def test_backfills_with_same_segment_when_too_few_same_symbol():
    current = _fp()
    records = [_record("AAPL", 7, f"2026-01-0{i}", "BUY", "BUY", True) for i in range(1, 4)]
    results = find_similar_cases(current, "TSLA", 7, records, k=5)
    assert len(results) == 3
    assert all(r["match_tier"] == "SAME_SEGMENT" for r in results)


def test_respects_k_limit():
    current = _fp()
    records = [_record("TSLA", 7, f"2026-01-{i:02d}", "BUY", "BUY", True) for i in range(1, 11)]
    results = find_similar_cases(current, "TSLA", 7, records, k=3)
    assert len(results) == 3
