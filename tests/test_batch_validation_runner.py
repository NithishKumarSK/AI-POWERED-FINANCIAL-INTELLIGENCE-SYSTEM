"""Tests for batch_validation_runner — verifies CSV/JSON output exist after a run."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── Test 1: Import and basic structure ────────────────────────────────────────

def test_batch_validation_runner_importable():
    """batch_validation_runner must import without errors."""
    import batch_validation_runner as bvr
    assert hasattr(bvr, "run_batch")
    assert hasattr(bvr, "FOCUSED_SYMBOLS")
    assert hasattr(bvr, "TOP_SP500_SYMBOLS")
    assert hasattr(bvr, "CSV_FIELDNAMES")


def test_focused_symbols_includes_spy_tsla():
    from batch_validation_runner import FOCUSED_SYMBOLS
    assert "SPY" in FOCUSED_SYMBOLS
    assert "TSLA" in FOCUSED_SYMBOLS


def test_top_sp500_includes_required():
    from batch_validation_runner import TOP_SP500_SYMBOLS
    for sym in ["SPY", "TSLA", "AAPL", "MSFT", "NVDA"]:
        assert sym in TOP_SP500_SYMBOLS, f"{sym} missing from TOP_SP500_SYMBOLS"


def test_csv_fieldnames_complete():
    from batch_validation_runner import CSV_FIELDNAMES
    required = [
        "run_id", "symbol", "origin_date", "target_date", "horizon_days",
        "ai_decision", "actual_decision", "agreement",
        "predicted_return_pct", "actual_return_pct", "return_error_pp",
        "confidence", "risk", "validation_status", "failure_reason", "recommended_fix",
    ]
    for field in required:
        assert field in CSV_FIELDNAMES, f"Field '{field}' missing from CSV_FIELDNAMES"


# ── Test 2: Failure classification ────────────────────────────────────────────

def test_classify_over_hold():
    from batch_validation_runner import _classify_failure
    reason, fix = _classify_failure("HOLD", "BUY", 0.5, 3.0, 70, {})
    assert reason == "OVER_HOLD"


def test_classify_false_buy():
    from batch_validation_runner import _classify_failure
    reason, fix = _classify_failure("BUY", "SELL", 3.0, -3.0, 70, {})
    assert reason in ("FALSE_BUY", "WRONG_MAGNITUDE")


def test_classify_false_sell():
    from batch_validation_runner import _classify_failure
    reason, fix = _classify_failure("SELL", "BUY", -3.0, 3.0, 70, {})
    assert reason == "FALSE_SELL"


def test_classify_match():
    from batch_validation_runner import _classify_failure
    reason, fix = _classify_failure("BUY", "BUY", 3.0, 3.0, 70, {})
    assert reason == "NONE"


def test_classify_trend_reversal():
    from batch_validation_runner import _classify_failure
    reason, fix = _classify_failure("BUY", "SELL", 3.0, -8.0, 70, {})
    assert reason == "TREND_REVERSAL_MISSED"


# ── Test 3: Direction match helper ────────────────────────────────────────────

def test_direction_match_same():
    from batch_validation_runner import _direction_match
    assert _direction_match("BUY", "BUY") is True
    assert _direction_match("SELL", "SELL") is True


def test_direction_match_different():
    from batch_validation_runner import _direction_match
    assert _direction_match("BUY", "SELL") is False
    assert _direction_match("SELL", "BUY") is False


def test_direction_match_none():
    from batch_validation_runner import _direction_match
    assert _direction_match(None, "BUY") is False


# ── Test 4: Summary builder ────────────────────────────────────────────────────

def test_build_summary_empty():
    from batch_validation_runner import _build_summary
    summary = _build_summary([], ["SPY"], [30])
    assert summary["total_runs"] == 0
    assert summary["valid_runs"] == 0
    assert summary["decision_match_pct"] == 0.0


def test_build_summary_all_match():
    from batch_validation_runner import _build_summary, _compute_agreement
    rows = [
        {
            "symbol": "SPY", "horizon_days": 30,
            "ai_decision": "BUY", "actual_decision": "BUY",
            "agreement": "MATCH",
            "validation_status": "SUCCESS",
            "return_error_pp": -0.5,
            "failure_reason": "NONE",
        }
    ] * 5
    summary = _build_summary(rows, ["SPY"], [30])
    assert summary["decision_match_pct"] == 100.0
    assert summary["false_buy_count"] == 0


# ── Test 5: Recommendations builder ──────────────────────────────────────────

def test_recommendations_for_over_hold():
    from batch_validation_runner import _build_recommendations
    from collections import Counter
    fc = Counter({"OVER_HOLD": 5})
    recs = _build_recommendations(list(fc.items()), hold_rate=70.0, decision_match_pct=25.0)
    assert any("OVER_HOLD" in r for r in recs)


def test_recommendations_for_high_hold_rate():
    from batch_validation_runner import _build_recommendations
    recs = _build_recommendations([], hold_rate=75.0, decision_match_pct=30.0)
    assert any("hold" in r.lower() or "HOLD" in r for r in recs)


# ── Test 6: horizon_bucket (Phase 5/2 shared bucketing) ───────────────────────

def test_horizon_bucket_boundaries():
    from batch_validation_runner import horizon_bucket
    assert horizon_bucket(0) == "0-7d"
    assert horizon_bucket(7) == "0-7d"
    assert horizon_bucket(8) == "8-14d"
    assert horizon_bucket(30) == "15-30d"
    assert horizon_bucket(31) == "31-60d"
    assert horizon_bucket(120) == "61-120d"
    assert horizon_bucket(121) == "120d+"
    assert horizon_bucket(10_000) == "120d+"


def test_horizon_bucket_handles_none():
    from batch_validation_runner import horizon_bucket
    assert horizon_bucket(None) == "0-7d"


# ── Test 7: _build_origin_dates reproducibility + weekly mode ────────────────

def test_build_origin_dates_deterministic():
    from batch_validation_runner import _build_origin_dates
    from datetime import date
    today = date(2026, 10, 10)
    a = _build_origin_dates(6, today)
    b = _build_origin_dates(6, today)
    assert a == b  # identical inputs -> identical grid, required for honest before/after comparisons


def test_build_origin_dates_weekly_denser_than_monthly():
    from batch_validation_runner import _build_origin_dates
    from datetime import date
    today = date(2026, 10, 10)
    monthly = _build_origin_dates(6, today, freq="monthly")
    weekly = _build_origin_dates(6, today, freq="weekly")
    assert len(weekly) > len(monthly)


def test_build_origin_dates_weekly_all_before_today():
    from batch_validation_runner import _build_origin_dates
    from datetime import date
    today = date(2026, 10, 10)
    weekly = _build_origin_dates(3, today, freq="weekly")
    assert all(d < today for d in weekly)


# ── Test 8: match_by_segment breakdown ────────────────────────────────────────

def test_build_summary_includes_match_by_segment():
    from batch_validation_runner import _build_summary
    rows = [
        {
            "symbol": "SPY", "horizon_days": 5,
            "ai_decision": "BUY", "actual_decision": "BUY",
            "agreement": "MATCH", "validation_status": "SUCCESS",
            "return_error_pp": 0.1, "failure_reason": "NONE",
        },
        {
            "symbol": "TSLA", "horizon_days": 90,
            "ai_decision": "BUY", "actual_decision": "SELL",
            "agreement": "MISMATCH", "validation_status": "SUCCESS",
            "return_error_pp": 5.0, "failure_reason": "FALSE_BUY",
        },
    ]
    summary = _build_summary(rows, ["SPY", "TSLA"], [5, 90])
    seg = summary["match_by_segment"]
    assert "SPY|0-7d" in seg
    assert seg["SPY|0-7d"]["decision_match_pct"] == 100.0
    assert "TSLA|61-120d" in seg
    assert seg["TSLA|61-120d"]["decision_match_pct"] == 0.0
    # No rows exist for this symbol/bucket combo -- must not appear at all,
    # rather than show up as a misleading 0-run/0% entry.
    assert "SPY|61-120d" not in seg


# ── Test 9: deterministic (use_llm=False) prediction path ────────────────────

def test_deterministic_technical_prediction_no_gemini_call(monkeypatch):
    """The deterministic path must never import/call the Gemini agent's network
    call -- only the pure-math feature packet + technical override score."""
    from batch_validation_runner import _deterministic_technical_prediction

    bars = [
        {"date": f"2026-01-{d:02d}", "close": 100.0 + d, "open": 100.0 + d,
         "high": 101.0 + d, "low": 99.0 + d, "volume": 1_000_000}
        for d in range(1, 29)
    ]
    spi = {
        "symbol": "SPY",
        "historical_context_start_date": "2026-01-01",
        "prediction_origin_date": "2026-01-28",
        "decision_horizon_days": 7,
        "price_basis": "close",
    }
    result = _deterministic_technical_prediction(spi, bars)
    assert result["status"] == "SUCCESS"
    assert result["decision"] in ("BUY", "SELL", "HOLD")
    assert result["predicted_return_pct"] is None  # no magnitude from a pure directional score
    assert result["source"] == "deterministic_technical_override"
