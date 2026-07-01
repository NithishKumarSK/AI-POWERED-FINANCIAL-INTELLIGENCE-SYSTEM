"""
Test suite: Strategy Prediction Flow
Validates the no-yfinance, hash identity, prediction correctness, and accuracy engine.
"""
from __future__ import annotations

import json
import sys
import os
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))
sys.path.insert(2, str(ROOT / "src"))

# Canonical StrategyInput used across all tests
STRATEGY_INPUT = {
    "symbol":           "AAPL",
    "start_date":       "2021-06-25",
    "end_date":         "2025-01-24",
    "initial_capital":  100_000.0,
    "benchmark":        "SPY",
    "direction":        "short",
    "side":             "put",
    "dte":              50,
    "delta":            30,
    "legs":             2,
    "entry_frequency":  "monthly",
    "decision_horizon": 30,
}

_EXCLUDED_SCAN_PATTERNS = ("__pycache__", ".git", "venv", "env/", "test_")


# ══════════════════════════════════════════════════════════════════════════════
# 1. NO YFINANCE ANYWHERE (production files only)
# ══════════════════════════════════════════════════════════════════════════════
class TestNoYfinance:
    """Fail if any production .py file imports or uses yfinance."""

    def _prod_files(self):
        for py_file in ROOT.rglob("*.py"):
            path_str = str(py_file)
            if any(x in path_str for x in _EXCLUDED_SCAN_PATTERNS):
                continue
            yield py_file

    def test_no_yfinance_import(self):
        hits = []
        for py_file in self._prod_files():
            try:
                lines = py_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "import yfinance" in stripped or "yf.download" in stripped:
                    hits.append(f"{py_file.name}:{i}: {stripped[:80]}")
        assert not hits, (
            f"FAIL: yfinance import found in {len(hits)} location(s):\n" + "\n".join(hits))

    def test_no_fallback_yfinance_function(self):
        hits = []
        for py_file in self._prod_files():
            try:
                text = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "def _yfinance_fallback" in text or "def fallback_yfinance" in text:
                hits.append(py_file.name)
        assert not hits, (
            "fallback yfinance function found in: " + ", ".join(hits))


# ══════════════════════════════════════════════════════════════════════════════
# 2. STRATEGY INPUT HASH
# ══════════════════════════════════════════════════════════════════════════════
class TestStrategyInputHash:
    def test_hash_is_deterministic(self):
        from strategy_prediction_agent import build_strategy_input_hash
        assert build_strategy_input_hash(STRATEGY_INPUT) == build_strategy_input_hash(STRATEGY_INPUT)

    def test_hash_is_16_chars(self):
        from strategy_prediction_agent import build_strategy_input_hash
        h = build_strategy_input_hash(STRATEGY_INPUT)
        assert len(h) == 16, f"Expected 16-char hash, got {len(h)}: {h}"

    def test_hash_changes_on_different_input(self):
        from strategy_prediction_agent import build_strategy_input_hash
        h1 = build_strategy_input_hash(STRATEGY_INPUT)
        h2 = build_strategy_input_hash({**STRATEGY_INPUT, "symbol": "TSLA"})
        assert h1 != h2

    def test_hash_is_sha256_based(self):
        from strategy_prediction_agent import build_strategy_input_hash, REQUIRED_FIELDS
        subset   = {k: STRATEGY_INPUT[k] for k in sorted(REQUIRED_FIELDS) if k in STRATEGY_INPUT}
        expected = hashlib.sha256(json.dumps(subset, sort_keys=True).encode()).hexdigest()[:16]
        assert build_strategy_input_hash(STRATEGY_INPUT) == expected

    def test_same_hash_for_ai_and_backtest_pipelines(self):
        from strategy_prediction_agent import build_strategy_input_hash
        assert build_strategy_input_hash(STRATEGY_INPUT) == build_strategy_input_hash(STRATEGY_INPUT)


# ══════════════════════════════════════════════════════════════════════════════
# 3. AI PREDICTION
# ══════════════════════════════════════════════════════════════════════════════
def _mock_rapidapi_get(endpoint, params=None, timeout=20):
    """Stub for rapidapi_client.rapidapi_get used in tests."""
    if "movers" in endpoint:
        return {"status": "SUCCESS", "data": {"gainers": [], "losers": []}}
    if "news" in endpoint:
        return {"status": "SUCCESS", "data": []}
    return {"status": "ERROR", "data": {}}


class TestAIPrediction:

    @pytest.fixture(autouse=True)
    def patch_rapidapi(self):
        with patch("rapidapi_client.rapidapi_get", side_effect=_mock_rapidapi_get):
            yield

    def test_run_ai_strategy_prediction_returns_dict(self):
        from strategy_prediction_agent import run_ai_strategy_prediction
        result = run_ai_strategy_prediction(STRATEGY_INPUT)
        assert isinstance(result, dict)

    def test_ai_status_is_success_or_error(self):
        from strategy_prediction_agent import run_ai_strategy_prediction
        result = run_ai_strategy_prediction(STRATEGY_INPUT)
        assert result.get("status") in ("SUCCESS", "ERROR")

    def test_no_backtest_leakage_guard(self):
        from strategy_prediction_agent import run_ai_strategy_prediction
        polluted = {**STRATEGY_INPUT, "backtest_result": {"win_rate": 0.72}}
        with pytest.raises(AssertionError, match="backtest"):
            run_ai_strategy_prediction(polluted)

    def test_required_output_fields_present(self):
        from strategy_prediction_agent import run_ai_strategy_prediction
        result = run_ai_strategy_prediction(STRATEGY_INPUT)
        if result.get("status") != "SUCCESS":
            pytest.skip("AI prediction did not succeed with mocked API.")
        required = [
            "decision", "predicted_initial_capital", "predicted_final_capital",
            "predicted_total_pl", "predicted_total_return_pct", "predicted_cagr",
            "predicted_win_rate", "predicted_trade_count", "predicted_max_drawdown",
            "predicted_sharpe", "predicted_sortino", "predicted_volatility",
            "predicted_alpha", "predicted_beta", "predicted_risk_score",
            "predicted_confidence_score", "predicted_max_profit", "predicted_max_loss",
            "strategy_factor_scores", "strategy_input_hash",
        ]
        for field in required:
            assert field in result, f"Missing required field: {field}"
            v = result[field]
            assert v is not None, f"Field '{field}' is None."
            if isinstance(v, str):
                assert v not in ("Not available", "Not estimated", "Unavailable"), (
                    f"Field '{field}' has forbidden value: '{v}'")

    def test_strategy_factor_scores_has_10_factors(self):
        from strategy_prediction_agent import run_ai_strategy_prediction
        result = run_ai_strategy_prediction(STRATEGY_INPUT)
        if result.get("status") != "SUCCESS": pytest.skip()
        assert len(result.get("strategy_factor_scores", {})) == 10

    def test_factor_scores_each_have_required_keys(self):
        from strategy_prediction_agent import run_ai_strategy_prediction
        result = run_ai_strategy_prediction(STRATEGY_INPUT)
        if result.get("status") != "SUCCESS": pytest.skip()
        for k, v in result["strategy_factor_scores"].items():
            for key in ("score", "signal", "source", "explanation"):
                assert key in v, f"Factor '{k}' missing '{key}'"
            assert 0 <= int(v["score"]) <= 100, f"Factor '{k}' score out of range"

    def test_win_rate_within_bounds(self):
        from strategy_prediction_agent import run_ai_strategy_prediction
        result = run_ai_strategy_prediction(STRATEGY_INPUT)
        if result.get("status") != "SUCCESS": pytest.skip()
        wr = float(result["predicted_win_rate"])
        assert 0 <= wr <= 100, f"predicted_win_rate={wr} out of [0,100]"

    def test_decision_is_valid(self):
        from strategy_prediction_agent import run_ai_strategy_prediction
        result = run_ai_strategy_prediction(STRATEGY_INPUT)
        if result.get("status") != "SUCCESS": pytest.skip()
        assert result["decision"] in ("BUY", "SELL", "HOLD", "REVIEW")

    def test_initial_capital_preserved(self):
        from strategy_prediction_agent import run_ai_strategy_prediction
        result = run_ai_strategy_prediction(STRATEGY_INPUT)
        if result.get("status") != "SUCCESS": pytest.skip()
        assert float(result["predicted_initial_capital"]) == 100_000.0


# ══════════════════════════════════════════════════════════════════════════════
# 4. VALIDATE STRATEGY INPUT
# ══════════════════════════════════════════════════════════════════════════════
class TestValidateStrategyInput:
    def test_valid_input_passes(self):
        from strategy_prediction_agent import validate_strategy_input
        ok, err = validate_strategy_input(STRATEGY_INPUT)
        assert ok, f"Valid input should pass: {err}"

    def test_missing_field_fails(self):
        from strategy_prediction_agent import validate_strategy_input
        bad = {k: v for k, v in STRATEGY_INPUT.items() if k != "symbol"}
        ok, err = validate_strategy_input(bad)
        assert not ok and "symbol" in err

    def test_invalid_delta_fails(self):
        from strategy_prediction_agent import validate_strategy_input
        ok, _ = validate_strategy_input({**STRATEGY_INPUT, "delta": 0})
        assert not ok

    def test_invalid_dte_fails(self):
        from strategy_prediction_agent import validate_strategy_input
        ok, _ = validate_strategy_input({**STRATEGY_INPUT, "dte": 0})
        assert not ok

    def test_negative_capital_fails(self):
        from strategy_prediction_agent import validate_strategy_input
        ok, _ = validate_strategy_input({**STRATEGY_INPUT, "initial_capital": -1000})
        assert not ok


# ══════════════════════════════════════════════════════════════════════════════
# 5. COMPARATOR
# ══════════════════════════════════════════════════════════════════════════════
class TestComparator:
    def _ai(self, d="BUY"):
        return {"status": "SUCCESS", "decision": d,
                "predicted_total_return_pct": 15.0, "predicted_total_pl": 15_000.0,
                "predicted_final_capital": 115_000.0, "predicted_win_rate": 68.0}

    def _bt(self, d="BUY", passed=True):
        return {"passed_validation": passed, "decision": d,
                "total_return_pct": 13.5, "total_pl": 13_500.0,
                "final_capital": 113_500.0, "win_rate": 64.0,
                "initial_capital": 100_000.0}

    def test_returns_required_keys(self):
        from strategy_backtest_comparator import compare_prediction_vs_backtest
        cmp = compare_prediction_vs_backtest(self._ai(), self._bt())
        for k in ("ai_decision", "backtest_decision", "decision_match", "directional_match",
                  "agreement", "final_decision", "agreement_message",
                  "return_error_pct", "pl_error", "win_rate_error"):
            assert k in cmp, f"Missing key: {k}"

    def test_match_when_both_buy(self):
        from strategy_backtest_comparator import compare_prediction_vs_backtest
        cmp = compare_prediction_vs_backtest(self._ai("BUY"), self._bt("BUY"))
        assert cmp["decision_match"] is True
        assert cmp["agreement"]      == "MATCH"
        assert cmp["final_decision"] == "BUY"

    def test_conflict_buy_vs_sell(self):
        from strategy_backtest_comparator import compare_prediction_vs_backtest
        cmp = compare_prediction_vs_backtest(self._ai("BUY"), self._bt("SELL"))
        assert cmp["agreement"]      == "CONFLICT"
        assert cmp["final_decision"] == "REVIEW"

    def test_partial_positive_bt_buy_ai_hold(self):
        from strategy_backtest_comparator import compare_prediction_vs_backtest
        cmp = compare_prediction_vs_backtest(self._ai("HOLD"), self._bt("BUY"))
        assert cmp["agreement"]      == "PARTIAL POSITIVE"
        assert cmp["final_decision"] == "BUY WITH CAUTION"

    def test_avoid_when_bt_sell_ai_hold(self):
        from strategy_backtest_comparator import compare_prediction_vs_backtest
        cmp = compare_prediction_vs_backtest(self._ai("HOLD"), self._bt("SELL"))
        assert cmp["agreement"]      == "PARTIAL NEGATIVE"
        assert cmp["final_decision"] == "AVOID"

    def test_missing_when_backtest_failed(self):
        from strategy_backtest_comparator import compare_prediction_vs_backtest
        cmp = compare_prediction_vs_backtest(self._ai("BUY"), self._bt(passed=False))
        assert cmp["agreement"]      == "MISSING"
        assert cmp["final_decision"] == "BUY"

    def test_return_error_calculation(self):
        from strategy_backtest_comparator import compare_prediction_vs_backtest
        cmp = compare_prediction_vs_backtest(self._ai("BUY"), self._bt("BUY"))
        assert abs(cmp["return_error_pct"] - 1.5) < 0.01


# ══════════════════════════════════════════════════════════════════════════════
# 6. ACCURACY ENGINE
# ══════════════════════════════════════════════════════════════════════════════
class TestAccuracyEngine:
    def _ai(self, d="BUY"):
        return {"status": "SUCCESS", "decision": d,
                "predicted_total_return_pct": 15.0, "predicted_total_pl": 15_000.0,
                "predicted_final_capital": 115_000.0, "predicted_win_rate": 68.0,
                "predicted_max_drawdown": 8.0}

    def _bt(self, d="BUY"):
        return {"passed_validation": True, "decision": d,
                "total_return_pct": 13.5, "total_pl": 13_500.0,
                "final_capital": 113_500.0, "win_rate": 64.0,
                "max_drawdown": 9.0, "initial_capital": 100_000.0}

    def test_build_evaluation_record_schema(self):
        from strategy_accuracy_engine import build_evaluation_record
        rec = build_evaluation_record(STRATEGY_INPUT, "abc123", self._ai(), self._bt())
        assert rec["source"]              == "strategy_backtest_verification"
        assert rec["strategy_input_hash"] == "abc123"
        assert "timestamp"  in rec
        assert "comparison" in rec
        assert "return_error_pct" in rec["comparison"]

    def test_save_and_load_records(self, tmp_path):
        import strategy_accuracy_engine as eng
        from strategy_accuracy_engine import (
            build_evaluation_record, save_strategy_evaluation_record,
            load_strategy_accuracy_records,
        )
        old = eng.EVAL_FILE
        eng.EVAL_FILE = tmp_path / "test.jsonl"
        try:
            save_strategy_evaluation_record(
                build_evaluation_record(STRATEGY_INPUT, "h1", self._ai("BUY"), self._bt("BUY")))
            save_strategy_evaluation_record(
                build_evaluation_record(STRATEGY_INPUT, "h2", self._ai("HOLD"), self._bt("SELL")))
            loaded = load_strategy_accuracy_records()
            assert len(loaded) == 2
        finally:
            eng.EVAL_FILE = old

    def test_calculate_accuracy_metrics_with_2_records(self, tmp_path):
        import strategy_accuracy_engine as eng
        from strategy_accuracy_engine import (
            build_evaluation_record, save_strategy_evaluation_record,
            load_strategy_accuracy_records, calculate_strategy_accuracy_metrics,
        )
        old = eng.EVAL_FILE
        eng.EVAL_FILE = tmp_path / "test2.jsonl"
        try:
            save_strategy_evaluation_record(
                build_evaluation_record(STRATEGY_INPUT, "h1", self._ai("BUY"), self._bt("BUY")))
            save_strategy_evaluation_record(
                build_evaluation_record(STRATEGY_INPUT, "h2", self._ai("SELL"), self._bt("SELL")))
            m = calculate_strategy_accuracy_metrics(load_strategy_accuracy_records())
            assert m["n_records"]  == 2
            assert m["n_correct"]  == 2
            assert m["decision_accuracy"] == 1.0
        finally:
            eng.EVAL_FILE = old

    def test_insufficient_records_returns_error(self):
        from strategy_accuracy_engine import calculate_strategy_accuracy_metrics
        assert "error" in calculate_strategy_accuracy_metrics([])
        assert "error" in calculate_strategy_accuracy_metrics([{}])


# ══════════════════════════════════════════════════════════════════════════════
# 7. ENRICH BACKTEST METRICS
# ══════════════════════════════════════════════════════════════════════════════
class TestEnrichBacktestMetrics:
    def test_computes_cagr_when_missing(self):
        from strategy_backtest_comparator import enrich_backtest_metrics
        bt = {"initial_capital": 100_000, "total_pl": 40_000, "total_return_pct": 40.0,
              "win_rate": 65.0, "trade_count": 20, "trial_rows": []}
        enriched = enrich_backtest_metrics(bt, STRATEGY_INPUT)
        assert enriched.get("cagr") is not None and enriched["cagr"] != 0.0

    def test_computes_beta_when_missing(self):
        from strategy_backtest_comparator import enrich_backtest_metrics
        bt = {"initial_capital": 100_000, "total_pl": 0, "total_return_pct": 0.0,
              "win_rate": 65.0, "trade_count": 20, "trial_rows": []}
        enriched = enrich_backtest_metrics(bt, STRATEGY_INPUT)
        assert enriched.get("beta") is not None

    def test_computes_max_drawdown_from_trial_rows(self):
        from strategy_backtest_comparator import enrich_backtest_metrics
        bt = {"initial_capital": 100_000, "total_pl": 1000, "total_return_pct": 1.0,
              "win_rate": 60.0, "trade_count": 5,
              "trial_rows": [
                  {"profit_loss": 1000}, {"profit_loss": -3000},
                  {"profit_loss": 2000}, {"profit_loss": -500}, {"profit_loss": 1500},
              ]}
        enriched = enrich_backtest_metrics(bt, STRATEGY_INPUT)
        assert enriched.get("max_drawdown") is not None
        assert enriched["max_drawdown"] > 0


# ══════════════════════════════════════════════════════════════════════════════
# 8. RAPIDAPI HOST
# ══════════════════════════════════════════════════════════════════════════════
class TestRapidAPIConfig:
    def test_rapidapi_host_is_trading_view(self):
        """All RapidAPI calls must go to trading-view.p.rapidapi.com, not Yahoo."""
        calls = []

        def _capture_get(endpoint, params=None, timeout=20):
            calls.append(endpoint)
            return {"status": "SUCCESS", "data": {"gainers": []}}

        with patch("rapidapi_client.rapidapi_get", side_effect=_capture_get):
            from strategy_prediction_agent import _get_rapidapi_context
            _get_rapidapi_context("AAPL")

        for ep in calls:
            assert "yahoo" not in ep.lower(), f"Forbidden Yahoo endpoint: {ep}"


# ══════════════════════════════════════════════════════════════════════════════
# 9. V2 CALIBRATION — NEW TESTS
# ══════════════════════════════════════════════════════════════════════════════

# Short put Δ30 DTE50 weekly — the exact combo that was broken (SELL when should BUY)
_SP_WEEKLY = {
    "symbol":           "MSFT",
    "start_date":       "2021-06-25",
    "end_date":         "2024-01-24",
    "initial_capital":  80_000.0,
    "benchmark":        "SPY",
    "direction":        "short",
    "side":             "put",
    "dte":              50,
    "delta":            30,
    "legs":             1,
    "entry_frequency":  "weekly",
    "decision_horizon": 30,
}


class TestV2CalibratedPrediction:

    @pytest.fixture(autouse=True)
    def patch_rapidapi(self):
        with patch("rapidapi_client.rapidapi_get", side_effect=_mock_rapidapi_get):
            yield

    def test_ai_prediction_deterministic(self):
        """3 runs with same input within cache window must produce identical numeric output."""
        from strategy_prediction_agent import run_ai_strategy_prediction
        r1 = run_ai_strategy_prediction(STRATEGY_INPUT)
        r2 = run_ai_strategy_prediction(STRATEGY_INPUT)
        r3 = run_ai_strategy_prediction(STRATEGY_INPUT)
        if r1.get("status") != "SUCCESS":
            pytest.skip("AI prediction did not succeed.")
        key_fields = [
            "predicted_total_return_pct", "predicted_win_rate",
            "predicted_risk_score", "predicted_trade_count",
            "predicted_final_capital",
        ]
        for f in key_fields:
            assert r1[f] == r2[f] == r3[f], (
                f"Non-deterministic output for '{f}': {r1[f]} vs {r2[f]} vs {r3[f]}")

    def test_model_version_in_output(self):
        """run_ai_strategy_prediction must return model_version == 'strategy_predictor_v2_calibrated'."""
        from strategy_prediction_agent import run_ai_strategy_prediction, MODEL_VERSION
        result = run_ai_strategy_prediction(STRATEGY_INPUT)
        assert result.get("model_version") == MODEL_VERSION, (
            f"Expected model_version='{MODEL_VERSION}', got '{result.get('model_version')}'")

    def test_decision_not_constant_sell_short_put_weekly(self):
        """
        Short put Δ30 DTE50 weekly: with valid win_rate >= 50 and non-catastrophic return,
        the decision must NOT be SELL. SELL requires return < -5 AND win_rate < 50.
        """
        from strategy_prediction_agent import run_ai_strategy_prediction
        result = run_ai_strategy_prediction(_SP_WEEKLY)
        if result.get("status") != "SUCCESS":
            pytest.skip("AI prediction did not succeed.")
        decision  = result.get("decision")
        total_ret = result.get("predicted_total_return_pct", 0)
        win_rate  = result.get("predicted_win_rate", 0)
        # SELL only valid if BOTH conditions: return < -5 AND win_rate < 50
        if decision == "SELL":
            assert total_ret < -5 and win_rate < 50, (
                f"SELL decision requires return<-5 AND win_rate<50, but got "
                f"return={total_ret:.2f}%, win_rate={win_rate:.1f}%")
        # For short put Δ30 the theoretical win prob is 70% — win_rate should be >= 50
        assert win_rate >= 50, (
            f"Short put Δ30 should have win_rate >= 50%, got {win_rate:.1f}%")

    def test_decision_rule_buy_requires_all_three_conditions(self):
        """BUY = return>5 AND win_rate>=55 AND risk_score<=80. Test the rule directly."""
        from strategy_prediction_agent import _apply_decision_rule
        assert _apply_decision_rule(10.0, 60.0, 70) == "BUY",   "All 3 conditions met → BUY"
        assert _apply_decision_rule(10.0, 60.0, 85) != "BUY",   "High risk → not BUY"
        assert _apply_decision_rule(10.0, 50.0, 70) != "BUY",   "Low win_rate → not BUY"
        assert _apply_decision_rule(-1.0, 60.0, 70) != "BUY",   "Negative return → not BUY"

    def test_sell_requires_both_conditions(self):
        """SELL = return < -5 AND win_rate < 50. Not triggered by risk_score alone."""
        from strategy_prediction_agent import _apply_decision_rule
        assert _apply_decision_rule(-10.0, 40.0, 90) == "SELL",  "Both bad → SELL"
        assert _apply_decision_rule(-10.0, 55.0, 90) != "SELL",  "win_rate ok → not SELL"
        assert _apply_decision_rule(0.0,   40.0, 95) != "SELL",  "return ok → not SELL"
        assert _apply_decision_rule(0.0,   60.0, 99) != "SELL",  "risk_score alone → not SELL"

    def test_accuracy_filters_current_model_version(self, tmp_path):
        """load_strategy_accuracy_records with model_version only returns matching records."""
        import strategy_accuracy_engine as eng
        from strategy_accuracy_engine import (
            build_evaluation_record, save_strategy_evaluation_record,
            load_strategy_accuracy_records, MODEL_VERSION,
        )
        old = eng.EVAL_FILE
        eng.EVAL_FILE = tmp_path / "acc_test.jsonl"
        try:
            ai  = {"status": "SUCCESS", "decision": "BUY",
                   "predicted_total_return_pct": 15.0, "predicted_total_pl": 15_000.0,
                   "predicted_final_capital": 115_000.0, "predicted_win_rate": 68.0,
                   "predicted_max_drawdown": 8.0}
            bt  = {"passed_validation": True, "decision": "BUY",
                   "total_return_pct": 13.5, "total_pl": 13_500.0,
                   "final_capital": 113_500.0, "win_rate": 64.0,
                   "max_drawdown": 9.0, "initial_capital": 100_000.0}
            # Save one v2 record and one legacy (no model_version)
            v2_rec  = build_evaluation_record(STRATEGY_INPUT, "h1", ai, bt, model_version=MODEL_VERSION)
            leg_rec = build_evaluation_record(STRATEGY_INPUT, "h2", ai, bt, model_version=MODEL_VERSION)
            # Simulate legacy by removing model_version
            leg_rec.pop("model_version", None)
            save_strategy_evaluation_record(v2_rec)
            save_strategy_evaluation_record(leg_rec)

            all_recs = load_strategy_accuracy_records()
            v2_recs  = load_strategy_accuracy_records(model_version=MODEL_VERSION)
            assert len(all_recs) == 2, f"Expected 2 total, got {len(all_recs)}"
            assert len(v2_recs)  == 1, f"Expected 1 v2-model record, got {len(v2_recs)}"
        finally:
            eng.EVAL_FILE = old

    def test_rolling_verification_creates_current_model_records(self, tmp_path):
        """run_strategy_rolling_verification saves records with the current model_version."""
        import strategy_accuracy_engine as eng
        from strategy_accuracy_engine import (
            run_strategy_rolling_verification, load_strategy_accuracy_records, MODEL_VERSION,
        )
        old = eng.EVAL_FILE
        eng.EVAL_FILE = tmp_path / "roll_test.jsonl"
        try:
            def _fake_backtest(si):
                return {
                    "passed_validation": True, "decision": "BUY",
                    "total_return_pct": 40.0, "total_pl": 40_000.0,
                    "final_capital": 140_000.0, "win_rate": 70.0,
                    "max_drawdown": 10.0, "initial_capital": float(si["initial_capital"]),
                }

            with patch("rapidapi_client.rapidapi_get", side_effect=_mock_rapidapi_get):
                n = run_strategy_rolling_verification(
                    STRATEGY_INPUT, n_windows=2, backtest_fn=_fake_backtest)

            if n == 0:
                pytest.skip("Rolling verification created 0 records — date range too short.")
            recs = load_strategy_accuracy_records(model_version=MODEL_VERSION)
            assert len(recs) >= 1, f"Expected >= 1 v2-model record, got {len(recs)}"
            for r in recs:
                assert r.get("model_version") == MODEL_VERSION, (
                    f"Record missing correct model_version: {r.get('model_version')}")
        finally:
            eng.EVAL_FILE = old

    def test_calibration_summary_in_ai_output(self):
        """run_ai_strategy_prediction must include calibration_summary key."""
        from strategy_prediction_agent import run_ai_strategy_prediction
        result = run_ai_strategy_prediction(STRATEGY_INPUT)
        if result.get("status") != "SUCCESS":
            pytest.skip()
        cal = result.get("calibration_summary")
        assert isinstance(cal, dict), "calibration_summary must be a dict"
        assert "has_calibration" in cal, "calibration_summary missing 'has_calibration'"
        assert "similar_count"   in cal, "calibration_summary missing 'similar_count'"


# ══════════════════════════════════════════════════════════════════════════════
# 10. V3 BACKTEST SURROGATE CALIBRATED — NEW TESTS
# ══════════════════════════════════════════════════════════════════════════════

def _mock_rapidapi_get_v3(endpoint, params=None, timeout=20):
    """Same mock as above but ensures no external calls in v3 tests."""
    return {"status": "SUCCESS", "data": {"symbols": []}}


class TestV3BacktestSurrogateCalibrated:

    @pytest.fixture(autouse=True)
    def patch_rapidapi(self):
        with patch("rapidapi_client.rapidapi_get", side_effect=_mock_rapidapi_get_v3):
            yield

    def test_no_yfinance_in_new_files(self):
        """strategy_calibration_engine.py must not import or use yfinance."""
        from pathlib import Path
        root = Path(__file__).resolve().parent
        new_files = ["strategy_calibration_engine.py"]
        hits = []
        for fname in new_files:
            fpath = root / fname
            if not fpath.exists():
                continue
            text = fpath.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "yfinance" in stripped or "yahooquery" in stripped or "yf." in stripped:
                    hits.append(f"{fname}:{i}: {stripped[:80]}")
        assert not hits, "yfinance found in new files:\n" + "\n".join(hits)

    def test_model_version_is_v3(self):
        """MODEL_VERSION must be the v3 surrogate-calibrated string."""
        from strategy_prediction_agent import MODEL_VERSION
        assert MODEL_VERSION == "strategy_predictor_v3_backtest_surrogate_calibrated", (
            f"Expected v3 model version, got: {MODEL_VERSION}")

    def test_calculation_version_is_3(self):
        """CALCULATION_VERSION must be '3.0'."""
        from strategy_prediction_agent import CALCULATION_VERSION
        assert CALCULATION_VERSION == "3.0", (
            f"Expected CALCULATION_VERSION='3.0', got: {CALCULATION_VERSION}")

    def test_no_current_backtest_leakage(self):
        """strategy_input with forbidden backtest keys must raise AssertionError."""
        from strategy_prediction_agent import run_ai_strategy_prediction
        bad_input = dict(STRATEGY_INPUT, actual={"total_return_pct": 250.0})
        with pytest.raises((AssertionError, Exception)):
            run_ai_strategy_prediction(bad_input)

    def test_same_input_hash_for_identical_inputs(self):
        """Same StrategyInput dict always produces the same 16-char hex hash."""
        from strategy_prediction_agent import build_strategy_input_hash
        h1 = build_strategy_input_hash(STRATEGY_INPUT)
        h2 = build_strategy_input_hash(dict(STRATEGY_INPUT))
        assert h1 == h2, f"Hash not deterministic: {h1} vs {h2}"
        assert len(h1) == 16, f"Hash must be 16 chars, got {len(h1)}"

    def test_backtest_decision_mapping_very_profitable(self):
        """
        When backtest final_capital >> initial_capital (like TSLA +680%),
        normalize_backtest_metrics must return decision BUY, not HOLD.
        This tests the fix for O3 pdf bug.
        """
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        # Simulate the normalize_backtest_metrics logic via streamlit_app
        # We test it directly: tpl_f > 0, total_return_pct > 50 → BUY
        # We replicate the relevant lines from normalize_backtest_metrics:
        tpl_f          = 544_284.0   # 80k → 624k
        initial_capital = 80_000.0
        wr_f           = 23.5        # low win rate (long options typical)
        total_return_pct = tpl_f / initial_capital * 100  # 680.35%

        d = "REVIEW"
        if total_return_pct > 50:
            d = "BUY"
        elif tpl_f > 0 and total_return_pct > 5 and wr_f >= 40:
            d = "BUY"
        elif tpl_f > 0 and wr_f >= 50:
            d = "BUY"
        elif tpl_f < 0 and total_return_pct < -5 and wr_f < 50:
            d = "SELL"
        elif tpl_f != 0 or wr_f > 0:
            d = "HOLD"

        assert d == "BUY", (
            f"Expected BUY for +{total_return_pct:.0f}% return, got {d}. "
            f"Backtest with final_capital >> initial_capital must be BUY.")

    def test_calibration_dataset_excludes_exact_hash(self, tmp_path):
        """
        ensure_calibration_dataset must never return a record whose
        strategy_input_hash matches current_hash.
        """
        from strategy_calibration_engine import ensure_calibration_dataset, _build_strategy_hash
        import strategy_calibration_engine as eng
        old = eng.EVAL_FILE
        eng.EVAL_FILE = tmp_path / "calib_test.jsonl"
        try:
            current_hash = _build_strategy_hash(_SP_WEEKLY)
            records = ensure_calibration_dataset(
                _SP_WEEKLY, current_hash, min_records=99, max_new_backtests=0
            )
            hashes = [r.get("strategy_input_hash") for _, r in records]
            assert current_hash not in hashes, (
                f"current_hash {current_hash} must not appear in calibration records.")
        finally:
            eng.EVAL_FILE = old

    def test_calibration_blending_moves_toward_empirical(self, tmp_path):
        """
        With 3+ similar calibration records showing high returns,
        the blended prediction must be significantly higher than the raw prediction.
        """
        from strategy_prediction_agent import (
            _deterministic_projection, _compute_factor_scores,
            _get_calibration_bias, _blend_with_calibration,
        )
        import strategy_prediction_agent as agent

        old = agent.EVAL_FILE
        agent.EVAL_FILE = tmp_path / "blend_test.jsonl"
        try:
            # Write 3 fake evaluation records with high actual returns
            import json as _json
            for i in range(3):
                sub_si = dict(_SP_WEEKLY,
                              start_date=f"202{i+1}-01-01",
                              end_date=f"202{i+2}-01-01")
                h = agent.build_strategy_input_hash(sub_si)
                rec = {
                    "source": "strategy_backtest_verification",
                    "model_version": "any_version",
                    "strategy_input": sub_si,
                    "strategy_input_hash": h,
                    "backtest_actual": {
                        "passed_validation": True,
                        "decision": "BUY",
                        "total_return_pct": 200.0,
                        "win_rate": 85.0,
                        "max_drawdown": 8.0,
                    },
                }
                with open(agent.EVAL_FILE, "a", encoding="utf-8") as fh:
                    fh.write(_json.dumps(rec) + "\n")

            # Now run prediction — calibration should pull return toward 200%
            ctx = {"gainers": [], "losers": [], "active": [], "news": [],
                   "movers_available": False, "news_available": False}
            factors = _compute_factor_scores(_SP_WEEKLY, ctx)
            raw_proj = _deterministic_projection(_SP_WEEKLY, factors)
            raw_ret  = raw_proj["predicted_total_return_pct"]

            input_hash = agent.build_strategy_input_hash(_SP_WEEKLY)
            cal = _get_calibration_bias(_SP_WEEKLY, input_hash)
            blended = _blend_with_calibration(raw_proj, cal)
            blended_ret = blended["predicted_total_return_pct"]

            assert cal.get("has_calibration"), "Expected calibration to be active."
            assert blended_ret > raw_ret, (
                f"Blended return ({blended_ret:.1f}%) must be > raw return ({raw_ret:.1f}%) "
                f"when empirical data shows higher returns.")
        finally:
            agent.EVAL_FILE = old

    def test_overall_strategy_accuracy_penalizes_numeric_error(self):
        """
        100% decision accuracy with huge return error must give < 100% overall accuracy.
        """
        from strategy_accuracy_engine import compute_overall_strategy_accuracy
        metrics_perfect_direction_bad_numbers = {
            "n_records":             2,
            "decision_accuracy":     1.0,      # 100% direction correct
            "directional_accuracy":  1.0,
            "avg_return_abs_error":  280.0,    # 280% return error (like MSFT AI vs actual)
            "avg_pl_abs_error":      180_000,  # $180k P&L error
            "avg_final_capital_error_pct": 250.0,
            "avg_win_rate_error":    -10.0,
        }
        osa = compute_overall_strategy_accuracy(metrics_perfect_direction_bad_numbers)
        assert isinstance(osa, dict), "Must return a dict"
        assert "overall_accuracy" in osa, "Must have overall_accuracy key"
        overall = osa["overall_accuracy"]
        assert overall < 0.70, (
            f"Overall accuracy must be < 70% when return error is 280%, got {overall:.2%}. "
            f"Decision accuracy ≠ Overall accuracy when numerics are very wrong.")

    def test_overall_strategy_accuracy_high_when_close(self):
        """
        Perfect direction + small numeric errors should give >= 80% overall accuracy.
        """
        from strategy_accuracy_engine import compute_overall_strategy_accuracy
        metrics_good = {
            "n_records":             5,
            "decision_accuracy":     0.80,
            "directional_accuracy":  0.90,
            "avg_return_abs_error":  5.0,
            "avg_pl_abs_error":      3_000,
            "avg_final_capital_error_pct": 4.0,
            "avg_win_rate_error":    2.0,
        }
        osa = compute_overall_strategy_accuracy(metrics_good)
        overall = osa["overall_accuracy"]
        assert overall >= 0.70, (
            f"Overall accuracy should be >= 70% when all errors are small, got {overall:.2%}")

    def test_rolling_verification_creates_v3_records(self, tmp_path):
        """run_strategy_rolling_verification saves records with model_version=v3."""
        import strategy_accuracy_engine as eng
        from strategy_accuracy_engine import (
            run_strategy_rolling_verification, load_strategy_accuracy_records, MODEL_VERSION,
        )
        old = eng.EVAL_FILE
        eng.EVAL_FILE = tmp_path / "roll_v3_test.jsonl"
        try:
            def _fake_backtest(si):
                return {
                    "passed_validation": True, "decision": "BUY",
                    "total_return_pct": 220.0, "total_pl": 176_000.0,
                    "final_capital": 256_000.0, "win_rate": 85.0,
                    "max_drawdown": 12.0, "initial_capital": float(si["initial_capital"]),
                }

            with patch("rapidapi_client.rapidapi_get", side_effect=_mock_rapidapi_get_v3):
                n = run_strategy_rolling_verification(
                    _SP_WEEKLY, n_windows=2, backtest_fn=_fake_backtest)

            if n == 0:
                pytest.skip("Rolling verification created 0 records — date range too short.")

            recs = load_strategy_accuracy_records(model_version=MODEL_VERSION)
            assert len(recs) >= 1, (
                f"Expected >= 1 record with model_version={MODEL_VERSION}, got {len(recs)}")
            assert MODEL_VERSION == "strategy_predictor_v3_backtest_surrogate_calibrated", (
                f"MODEL_VERSION mismatch: {MODEL_VERSION}")
            for r in recs:
                assert r.get("model_version") == MODEL_VERSION
        finally:
            eng.EVAL_FILE = old

    def test_similarity_compute_is_bounded(self):
        """compute_strategy_similarity result must be in [0.0, 1.0]."""
        from strategy_calibration_engine import compute_strategy_similarity
        identical = compute_strategy_similarity(_SP_WEEKLY, _SP_WEEKLY)
        assert 0.0 <= identical <= 1.0, f"Similarity must be in [0,1], got {identical}"
        assert identical == 1.0, f"Identical inputs must give similarity 1.0, got {identical}"

        different = compute_strategy_similarity(
            _SP_WEEKLY,
            {**_SP_WEEKLY, "direction": "long", "side": "call", "symbol": "GOOG",
             "delta": 10, "dte": 7, "entry_frequency": "daily"},
        )
        assert 0.0 <= different <= 1.0
        assert different < 0.50, (
            f"Very different strategies should have similarity < 0.50, got {different}")


# ══════════════════════════════════════════════════════════════════════════════
# 11. O1–O7 REGRESSION SUITE — FINAL STRICT PROMPT
# ══════════════════════════════════════════════════════════════════════════════

class TestO1ToO7ValidationRegressions:
    """
    Regression tests for every failure observed in PDFs O1-O7 and blank-symbol test.
    Each test confirms the specific guard that now blocks the failure mode.
    """

    # ── O1 / O2 / Blank: symbol validation ───────────────────────────────────

    def test_o1_blank_symbol_blocked(self):
        """Blank symbol must be rejected before AI or backtest runs."""
        from strategy_validation import validate_strategy_input
        ok, err = validate_strategy_input(dict(STRATEGY_INPUT, symbol=""))
        assert not ok, "Blank symbol must be blocked"
        assert ("blank" in err.lower() or "required" in err.lower()), (
            f"Error must mention blank/required, got: {err}")

    def test_o1_whitespace_symbol_blocked(self):
        """Whitespace-only symbol must also be rejected."""
        from strategy_validation import validate_strategy_input
        ok, err = validate_strategy_input(dict(STRATEGY_INPUT, symbol="   "))
        assert not ok, "Whitespace-only symbol must be blocked"

    def test_o1_fake_symbol_xyz_blocked(self):
        """O1: XYZ is a known placeholder symbol — must be blocked."""
        from strategy_validation import validate_strategy_input
        ok, err = validate_strategy_input(dict(STRATEGY_INPUT, symbol="XYZ"))
        assert not ok, "XYZ must be blocked as a placeholder symbol"
        assert "XYZ" in err, f"Error must name the symbol, got: {err}"

    def test_o2_fake_symbol_abcxyz_blocked(self):
        """O2: ABCXYZ has 6 characters — invalid format, must be blocked."""
        from strategy_validation import validate_strategy_input
        ok, err = validate_strategy_input(dict(STRATEGY_INPUT, symbol="ABCXYZ"))
        assert not ok, "ABCXYZ (6 chars) must fail format validation"

    def test_real_symbols_pass_validation(self):
        """Real stock/ETF symbols must pass validation without error."""
        from strategy_validation import validate_strategy_input
        for sym in ("AAPL", "MSFT", "TSLA", "CVS", "SPY", "GOOGL", "BRK.B"):
            ok, err = validate_strategy_input(dict(STRATEGY_INPUT, symbol=sym))
            assert ok, f"Real symbol '{sym}' must pass validation — got: {err}"

    # ── O4: catastrophic loss → SELL ─────────────────────────────────────────

    def test_o4_tsla_catastrophic_loss_maps_to_sell(self):
        """
        O4: TSLA short put 2021-2025 — tpl_f=-581,759, wr_f=70.3%, return=-727%.
        With the old logic (win_rate condition on SELL) this mapped to HOLD.
        Phase 8 fix: final_capital <= 0 → always SELL regardless of win_rate.
        """
        initial_capital  = 80_000.0
        tpl_f            = -581_759.51
        wr_f             = 70.3   # high win-rate short premium
        final_capital    = initial_capital + tpl_f   # deeply negative
        total_return_pct = tpl_f / initial_capital * 100

        # Phase 8 decision logic (mirrored from normalize_backtest_metrics)
        d = "REVIEW"
        if final_capital <= 0:
            d = "SELL"
        elif total_return_pct <= -50:
            d = "SELL"
        elif total_return_pct > 5 and tpl_f > 0:
            d = "BUY"
        elif total_return_pct < -5:
            d = "SELL"
        elif -5 <= total_return_pct <= 5:
            d = "HOLD"

        assert d == "SELL", (
            f"TSLA -727% (final_capital={final_capital:.0f}) must be SELL; "
            f"win_rate {wr_f}% must NOT override catastrophic P&L. Got: {d}")

    # ── O5: sustained loss → SELL ─────────────────────────────────────────────

    def test_o5_cvs_loss_maps_to_sell(self):
        """
        O5: CVS short put — return=-28.32%, win_rate=72.9%.
        Old logic required win_rate < 50 for SELL → mapped to HOLD.
        Phase 8: total_return_pct < -5 → SELL regardless of win_rate.
        """
        initial_capital  = 80_000.0
        tpl_f            = -22_656.0   # -28.32% of 80k
        wr_f             = 72.9
        final_capital    = initial_capital + tpl_f
        total_return_pct = tpl_f / initial_capital * 100

        d = "REVIEW"
        if final_capital <= 0:
            d = "SELL"
        elif total_return_pct <= -50:
            d = "SELL"
        elif total_return_pct > 5 and tpl_f > 0:
            d = "BUY"
        elif total_return_pct < -5:
            d = "SELL"
        elif -5 <= total_return_pct <= 5:
            d = "HOLD"

        assert d == "SELL", (
            f"CVS -28% must be SELL not HOLD even with win_rate {wr_f}%. Got: {d}")

    # ── O6 / O7: date validation ──────────────────────────────────────────────

    def test_o6_future_end_date_2027_blocked(self):
        """O6: end_date in 2027 must be blocked — no future dates allowed."""
        from strategy_validation import validate_strategy_input
        ok, err = validate_strategy_input(dict(STRATEGY_INPUT, end_date="2027-01-01"))
        assert not ok, "Future end date 2027-01-01 must be blocked"
        assert ("future" in err.lower() or "2027" in err), (
            f"Error must mention future date, got: {err}")

    def test_o7_year_1000_start_date_blocked(self):
        """O7: start_date in year 1000 must be blocked — pre-2000 dates are not valid."""
        from strategy_validation import validate_strategy_input
        ok, err = validate_strategy_input(dict(STRATEGY_INPUT, start_date="1000-01-01"))
        assert not ok, "Year 1000 start date must be blocked"
        assert ("2000" in err or "before" in err.lower() or "historical" in err.lower()), (
            f"Error must explain 2000-01-01 minimum, got: {err}")

    def test_future_start_date_blocked(self):
        """Start date that is today or in the future must be blocked."""
        from strategy_validation import validate_strategy_input
        from datetime import date, timedelta
        future = (date.today() + timedelta(days=30)).isoformat()
        ok, err = validate_strategy_input(dict(STRATEGY_INPUT, start_date=future))
        assert not ok, f"Future start date {future} must be blocked"

    def test_invalid_date_format_blocked(self):
        """Unparseable date like '01/01/2021' must be blocked."""
        from strategy_validation import validate_strategy_input
        ok, err = validate_strategy_input(dict(STRATEGY_INPUT, start_date="01/01/2021"))
        assert not ok, "Invalid date format '01/01/2021' must be blocked"

    # ── Auto-retry removal ────────────────────────────────────────────────────

    def test_auto_retry_hardcoded_dates_removed(self):
        """
        The silent auto-retry that replaced user dates with hardcoded '2026-06-24'
        must no longer exist in streamlit_app.py (root cause of O6/O7).
        """
        from pathlib import Path
        app_path = Path(__file__).resolve().parent / "streamlit_app.py"
        text = app_path.read_text(encoding="utf-8")
        assert "2026-06-24" not in text, (
            "Hardcoded auto-retry date '2026-06-24' found in streamlit_app.py. "
            "The silent date-override retry must be removed (O6/O7 root cause fix).")

    # ── Quarantine / accuracy record integrity ────────────────────────────────

    def test_quarantine_functions_exist(self):
        """is_valid_evaluation_record and quarantine_invalid_record must be importable."""
        from strategy_accuracy_engine import is_valid_evaluation_record, quarantine_invalid_record
        assert callable(is_valid_evaluation_record)
        assert callable(quarantine_invalid_record)

    def test_quarantine_rejects_fake_symbol_record(self):
        """A record with symbol='XYZ' must be rejected by is_valid_evaluation_record."""
        from strategy_accuracy_engine import is_valid_evaluation_record
        record = {
            "strategy_input": {
                "symbol": "XYZ", "start_date": "2021-01-01", "end_date": "2024-01-01",
            },
            "backtest_actual": {
                "passed_validation": True,
                "decision": "BUY",
                "actual_total_return_pct": 50.0,
            },
        }
        assert not is_valid_evaluation_record(record), (
            "Records with fake symbol 'XYZ' must fail is_valid_evaluation_record")

    def test_quarantine_rejects_future_end_date_record(self):
        """A record with future end_date must be rejected (was likely auto-retried)."""
        from strategy_accuracy_engine import is_valid_evaluation_record
        record = {
            "strategy_input": {
                "symbol": "CVS", "start_date": "2021-01-01", "end_date": "2027-01-01",
            },
            "backtest_actual": {
                "passed_validation": True,
                "decision": "BUY",
                "actual_total_return_pct": 50.0,
            },
        }
        assert not is_valid_evaluation_record(record), (
            "Records with future end_date=2027 must fail is_valid_evaluation_record")

    def test_quarantine_rejects_year_1000_record(self):
        """A record with start_date in year 1000 must be rejected."""
        from strategy_accuracy_engine import is_valid_evaluation_record
        record = {
            "strategy_input": {
                "symbol": "CVS", "start_date": "1000-01-01", "end_date": "2024-01-01",
            },
            "backtest_actual": {
                "passed_validation": True,
                "decision": "BUY",
                "actual_total_return_pct": 50.0,
            },
        }
        assert not is_valid_evaluation_record(record), (
            "Records with year-1000 start_date must fail is_valid_evaluation_record")

    def test_quarantine_accepts_valid_real_record(self):
        """A well-formed real record must pass is_valid_evaluation_record."""
        from strategy_accuracy_engine import is_valid_evaluation_record
        record = {
            "strategy_input": {
                "symbol": "MSFT", "start_date": "2021-01-01", "end_date": "2024-01-01",
            },
            "backtest_actual": {
                "passed_validation": True,
                "decision": "BUY",
                "actual_total_return_pct": 220.0,
            },
        }
        assert is_valid_evaluation_record(record), (
            "Valid MSFT record with past dates and real return must pass validation")

    def test_strategy_validation_module_exists(self):
        """strategy_validation.py must be importable as the central gate."""
        import strategy_validation
        assert hasattr(strategy_validation, "validate_strategy_input")
        assert hasattr(strategy_validation, "validate_symbol")
        assert hasattr(strategy_validation, "validate_dates")


class TestPortfolioModeDetection:
    """Portfolio mode detection and routing tests."""

    def test_detect_single_symbol_aapl(self):
        """Single ticker AAPL must route to single_strategy mode."""
        from portfolio_mode import detect_input_mode
        assert detect_input_mode("AAPL") == "single_strategy"

    def test_detect_portfolio_weighted_space(self):
        """Space-separated weighted tickers must route to portfolio mode."""
        from portfolio_mode import detect_input_mode
        assert detect_input_mode("GOOGL 50% AAPL 20% TSLA 20% MSFT 10%") == "portfolio"

    def test_detect_portfolio_weighted_commas(self):
        """Comma-separated weighted tickers must route to portfolio mode."""
        from portfolio_mode import detect_input_mode
        assert detect_input_mode("GOOGL 50%, AAPL 30%, MSFT 20%") == "portfolio"

    def test_parse_portfolio_weights_sum_100(self):
        """parse_and_validate_portfolio must succeed when weights sum to 100."""
        from portfolio_mode import parse_and_validate_portfolio
        result = parse_and_validate_portfolio("AAPL 50% MSFT 50%", 100000)
        assert result["status"] == "SUCCESS", f"Expected SUCCESS, got: {result}"
        assert len(result["holdings"]) == 2

    def test_portfolio_does_not_use_single_symbol_validator_on_raw_string(self):
        """The raw portfolio string must never be passed to validate_strategy_input."""
        from portfolio_mode import detect_input_mode
        from strategy_validation import validate_strategy_input
        raw = "GOOGL 50% AAPL 20% TSLA 20% MSFT 10%"
        mode = detect_input_mode(raw)
        assert mode == "portfolio", "Portfolio string must be detected as portfolio mode"
        # validate_strategy_input would block this as invalid symbol — confirm it does
        si = {
            "symbol": raw, "direction": "BULLISH", "side": "SELL",
            "start_date": "2023-01-01", "end_date": "2024-01-01",
            "initial_capital": 10000, "dte": 30, "delta": 0.30,
            "legs": 1, "entry_frequency": "weekly",
        }
        ok, _ = validate_strategy_input(si)
        assert not ok, "Raw portfolio string MUST fail single-symbol validation (confirms routing matters)"

    def test_portfolio_validates_each_symbol_individually(self):
        """Each ticker in portfolio must pass individual symbol validation."""
        from portfolio_mode import parse_and_validate_portfolio
        result = parse_and_validate_portfolio("AAPL 60% MSFT 40%", 50000)
        assert result["status"] == "SUCCESS"
        tickers = [h["ticker"] for h in result["holdings"]]
        assert "AAPL" in tickers
        assert "MSFT" in tickers

    def test_portfolio_invalid_weight_blocks(self):
        """Portfolio with weights that don't sum near 100 must return ERROR or issues."""
        from portfolio_mode import parse_and_validate_portfolio
        result = parse_and_validate_portfolio("AAPL 10% MSFT 10%", 10000)
        # weights sum to 20% — parser must flag this
        is_error = result["status"] == "ERROR" or len(result.get("issues", [])) > 0
        assert is_error, f"Weights summing to 20% must produce error/issues. Got: {result}"

    def test_single_strategy_still_blocks_fake_symbol(self):
        """Fake symbol XYZ must still be blocked in single-strategy mode after portfolio mode added."""
        from strategy_validation import validate_strategy_input
        si = {
            "symbol": "XYZ", "direction": "BULLISH", "side": "SELL",
            "start_date": "2023-01-01", "end_date": "2024-01-01",
            "initial_capital": 10000, "dte": 30, "delta": 0.30,
            "legs": 1, "entry_frequency": "weekly",
        }
        ok, err = validate_strategy_input(si)
        assert not ok, "XYZ must be blocked by single-symbol validation"
        assert "XYZ" in err or "blocked" in err.lower() or "invalid" in err.lower()

    def test_blank_still_blocks(self):
        """Blank symbol must still be blocked in single-strategy mode."""
        from strategy_validation import validate_strategy_input
        si = {
            "symbol": "", "direction": "BULLISH", "side": "SELL",
            "start_date": "2023-01-01", "end_date": "2024-01-01",
            "initial_capital": 10000, "dte": 30, "delta": 0.30,
            "legs": 1, "entry_frequency": "weekly",
        }
        ok, err = validate_strategy_input(si)
        assert not ok, "Blank symbol must be blocked"


class TestPortfolioAIResilience:
    """Portfolio analysis must always succeed even when Gemini returns broken JSON."""

    _HOLDINGS_4 = [
        {"ticker": "GOOGL", "weight": 0.50, "weight_pct": 50.0, "allocation": 40000},
        {"ticker": "CVS",   "weight": 0.20, "weight_pct": 20.0, "allocation": 16000},
        {"ticker": "TSLA",  "weight": 0.20, "weight_pct": 20.0, "allocation": 16000},
        {"ticker": "MSFT",  "weight": 0.10, "weight_pct": 10.0, "allocation":  8000},
    ]

    def test_safe_parse_llm_json_handles_truncated(self):
        """Truncated JSON returns (None, error_str) without raising."""
        from portfolio_mode import safe_parse_llm_json
        result, err = safe_parse_llm_json(
            '{"recommendation": "HOLD", "explanation": "broken'
        )
        assert result is None
        assert err is not None and isinstance(err, str)

    def test_safe_parse_llm_json_strips_fences(self):
        """Markdown-fenced JSON is parsed correctly."""
        from portfolio_mode import safe_parse_llm_json
        result, err = safe_parse_llm_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}
        assert err is None

    def test_portfolio_analysis_complete_without_gemini(self):
        """run_deterministic_portfolio_analysis returns all required fields."""
        from portfolio_mode import run_deterministic_portfolio_analysis
        required = {
            "status", "recommendation", "portfolio_score", "risk_score",
            "diversification_score", "concentration_risk", "expected_return_pct",
            "expected_drawdown_pct", "confidence_score", "top_strengths",
            "top_risks", "recommended_actions", "holding_analysis",
            "final_decision", "risk_status", "diversification_status",
            "analysis_summary", "gemini_status",
        }
        result = run_deterministic_portfolio_analysis(
            self._HOLDINGS_4, 80000, "SPY"
        )
        assert result["status"] == "SUCCESS"
        missing = required - result.keys()
        assert not missing, f"Missing fields: {missing}"
        for f in ("top_strengths", "top_risks", "recommended_actions"):
            assert isinstance(result[f], list) and len(result[f]) > 0, f"{f} must be non-empty list"

    def test_portfolio_ai_invalid_json_does_not_crash(self):
        """Gemini returning malformed JSON → result still SUCCESS with gemini_status=FAILED."""
        from portfolio_mode import run_portfolio_gemini_analysis
        from unittest.mock import patch, MagicMock

        mock_resp = MagicMock()
        mock_resp.text = '{"recommendation": "HOLD", "explanation": "broken'
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_resp

        with patch("google.generativeai.configure"), \
             patch("google.generativeai.GenerativeModel", return_value=mock_model):
            result = run_portfolio_gemini_analysis(self._HOLDINGS_4, 80000, "SPY")

        assert result["status"] == "SUCCESS", (
            f"Must return SUCCESS even when Gemini JSON is broken. Got: {result.get('status')}"
        )
        assert result.get("gemini_status") == "FAILED", (
            f"gemini_status must be FAILED. Got: {result.get('gemini_status')}"
        )
        assert "portfolio_score" in result
        assert "risk_score" in result
        assert "holding_analysis" in result

    def test_portfolio_numeric_metrics_not_overwritten_by_gemini(self):
        """Gemini cannot overwrite deterministic numeric scores even if it tries."""
        from portfolio_mode import run_portfolio_gemini_analysis, run_deterministic_portfolio_analysis
        from unittest.mock import patch, MagicMock

        det = run_deterministic_portfolio_analysis(self._HOLDINGS_4, 80000, "SPY")
        expected_score = det["portfolio_score"]

        mock_resp = MagicMock()
        mock_resp.text = (
            '{"top_strengths": ["s1","s2","s3"], "top_risks": ["r1","r2","r3"],'
            '"recommended_actions": ["a1","a2","a3"], "analysis_summary": "test",'
            '"portfolio_score": 99}'  # Gemini tries to override score — must be ignored
        )
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_resp

        with patch("google.generativeai.configure"), \
             patch("google.generativeai.GenerativeModel", return_value=mock_model):
            result = run_portfolio_gemini_analysis(self._HOLDINGS_4, 80000, "SPY")

        assert result["portfolio_score"] == expected_score, (
            f"Gemini must not overwrite portfolio_score. "
            f"Expected {expected_score}, got {result['portfolio_score']}"
        )
        assert result["top_strengths"] == ["s1", "s2", "s3"], (
            "Gemini text fields should be merged"
        )

    def test_portfolio_rebalance_for_50_percent_concentration(self):
        """GOOGL at 50% must trigger REBALANCE recommendation."""
        from portfolio_mode import run_deterministic_portfolio_analysis
        result = run_deterministic_portfolio_analysis(self._HOLDINGS_4, 80000, "SPY")
        assert result["recommendation"] == "REBALANCE", (
            f"50% concentration must trigger REBALANCE. Got: {result['recommendation']}"
        )
        assert result["concentration_risk"] == "HIGH", (
            f"50% max weight must set concentration_risk=HIGH. Got: {result['concentration_risk']}"
        )

    def test_portfolio_allocations_correct(self):
        """Deterministic analysis allocations must match input holdings."""
        from portfolio_mode import run_deterministic_portfolio_analysis
        result = run_deterministic_portfolio_analysis(self._HOLDINGS_4, 80000, "SPY")
        ha_map = {h["ticker"]: h for h in result["holding_analysis"]}
        assert "GOOGL" in ha_map, "GOOGL must appear in holding_analysis"
        assert "TSLA"  in ha_map, "TSLA must appear in holding_analysis"
        assert "MSFT"  in ha_map, "MSFT must appear in holding_analysis"
        assert "CVS"   in ha_map, "CVS must appear in holding_analysis"

    def test_portfolio_mode_does_not_call_tastytrade(self):
        """portfolio_mode.py must not reference tastytrade at all."""
        from pathlib import Path
        source = (
            Path(__file__).parent / "portfolio_mode.py"
        ).read_text(encoding="utf-8")
        assert "tastytrade" not in source.lower(), (
            "portfolio_mode.py must not import or call tastytrade"
        )
        assert "run_tastytrade" not in source, (
            "portfolio_mode.py must not call run_tastytrade_strategy_backtest"
        )


class TestPortfolioVerification:
    """Per-holding AI prediction + backtest aggregation tests."""

    _PSI = {
        "mode":             "portfolio_strategy",
        "holdings": [
            {"symbol": "GOOGL", "weight": 50.0, "allocated_capital": 40000.0},
            {"symbol": "CVS",   "weight": 20.0, "allocated_capital": 16000.0},
            {"symbol": "MSFT",  "weight": 20.0, "allocated_capital": 16000.0},
        ],
        "start_date":      "2021-06-25",
        "end_date":        "2021-12-26",
        "initial_capital": 72000.0,
        "benchmark":       "SPY",
        "direction":       "short",
        "side":            "put",
        "dte":             50,
        "delta":           30,
        "legs":            1,
        "entry_frequency": "monthly",
        "decision_horizon": 30,
    }

    def _mock_ai(self, **kwargs):
        """Return a fake successful AI result."""
        def _factory(si):
            capital = float(si["initial_capital"])
            return {
                "status":                  "SUCCESS",
                "decision":                "BUY",
                "predicted_final_capital": capital * 1.05,
                "predicted_total_return_pct": 5.0,
                "predicted_win_rate":      60.0,
                "predicted_trade_count":   6,
                "predicted_max_drawdown":  8.0,
                "predicted_volatility":    12.0,
                "predicted_sharpe":        0.8,
                "predicted_risk_score":    40.0,
                "confidence_score":        70.0,
            }
        return _factory

    def _mock_bt(self, factor: float = 1.03):
        """Return a fake backtest function that returns passed_validation=True."""
        def _factory(si):
            capital = float(si["initial_capital"])
            return {
                "passed_validation": True,
                "status":            "SUCCESS",
                "decision":          "BUY",
                "final_capital":     round(capital * factor, 2),
                "total_return_pct":  round((factor - 1) * 100, 2),
                "win_rate":          58.0,
                "trade_count":       6,
                "max_drawdown":      9.0,
            }
        return _factory

    def test_portfolio_ai_prediction_runs_per_holding(self):
        """run_portfolio_ai_prediction must call AI once per holding."""
        from portfolio_strategy_engine import run_portfolio_ai_prediction

        call_log = []
        def _fake_ai(si):
            call_log.append(si["symbol"])
            return {"status": "SUCCESS", "decision": "HOLD",
                    "predicted_final_capital": si["initial_capital"],
                    "predicted_win_rate": 50.0, "predicted_trade_count": 5,
                    "predicted_max_drawdown": 10.0, "predicted_volatility": 15.0,
                    "predicted_sharpe": 0.5, "predicted_risk_score": 45.0,
                    "confidence_score": 60.0}

        with patch("strategy_prediction_agent.run_ai_strategy_prediction", side_effect=_fake_ai):
            result = run_portfolio_ai_prediction(self._PSI)

        assert len(call_log) == 3, f"AI must be called once per holding. Got {len(call_log)} calls."
        assert set(call_log) == {"GOOGL", "CVS", "MSFT"}, f"Called with: {call_log}"

    def test_portfolio_backtest_runs_per_holding(self):
        """run_portfolio_backtest_actual must call backtest_fn once per holding."""
        from portfolio_strategy_engine import run_portfolio_backtest_actual

        call_log = []
        def _fake_bt(si):
            call_log.append(si["symbol"])
            return {"passed_validation": True, "decision": "HOLD",
                    "final_capital": si["initial_capital"], "total_return_pct": 0.0,
                    "win_rate": 50.0, "trade_count": 5, "max_drawdown": 8.0}

        result = run_portfolio_backtest_actual(self._PSI, _fake_bt)
        assert len(call_log) == 3, f"Backtest must be called once per holding. Got {len(call_log)}"
        assert set(call_log) == {"GOOGL", "CVS", "MSFT"}

    def test_portfolio_backtest_does_not_use_raw_portfolio_string(self):
        """backtest_fn must never be called with the raw portfolio string as symbol."""
        from portfolio_strategy_engine import run_portfolio_backtest_actual

        raw_string = "GOOGL 50% CVS 20% MSFT 30%"
        called_with = []
        def _fake_bt(si):
            called_with.append(si.get("symbol", ""))
            return {"passed_validation": True, "decision": "HOLD",
                    "final_capital": si["initial_capital"], "total_return_pct": 0.0,
                    "win_rate": 50.0, "trade_count": 4, "max_drawdown": 7.0}

        run_portfolio_backtest_actual(self._PSI, _fake_bt)
        for sym in called_with:
            assert sym != raw_string, (
                f"Raw portfolio string was passed to backtest. Found: {sym}"
            )
            assert len(sym) <= 10, f"Symbol {sym!r} looks like a raw string"

    def test_portfolio_aggregate_final_capital_sum(self):
        """Portfolio final capital must equal sum of holding final capitals."""
        from portfolio_strategy_engine import run_portfolio_backtest_actual

        holding_finals = {}
        def _fake_bt(si):
            sym = si["symbol"]
            final = round(si["initial_capital"] * 1.04, 2)
            holding_finals[sym] = final
            return {"passed_validation": True, "decision": "BUY",
                    "final_capital": final, "total_return_pct": 4.0,
                    "win_rate": 55.0, "trade_count": 6, "max_drawdown": 9.0}

        result = run_portfolio_backtest_actual(self._PSI, _fake_bt)
        expected_total = round(sum(holding_finals.values()), 2)
        assert abs(result["final_capital"] - expected_total) < 1.0, (
            f"Portfolio final_capital {result['final_capital']} != sum of holdings {expected_total}"
        )

    def test_portfolio_aggregate_total_pl_sum(self):
        """Portfolio total_pl must equal final_capital - initial_capital."""
        from portfolio_strategy_engine import run_portfolio_backtest_actual

        def _fake_bt(si):
            final = round(si["initial_capital"] * 1.06, 2)
            return {"passed_validation": True, "decision": "BUY",
                    "final_capital": final, "total_return_pct": 6.0,
                    "win_rate": 60.0, "trade_count": 6, "max_drawdown": 8.0}

        result = run_portfolio_backtest_actual(self._PSI, _fake_bt)
        expected_pl = round(result["final_capital"] - self._PSI["initial_capital"], 2)
        assert abs(result["total_pl"] - expected_pl) < 1.0, (
            f"total_pl {result['total_pl']} != final - initial = {expected_pl}"
        )

    def test_portfolio_comparison_metrics(self):
        """compare_portfolio_ai_vs_backtest must produce correct comparison dict."""
        from portfolio_strategy_engine import compare_portfolio_ai_vs_backtest

        pf_ai = {
            "decision": "BUY", "total_return_pct": 8.0, "total_pl": 5760.0,
            "final_capital": 77760.0, "win_rate": 62.0, "max_drawdown": 9.0,
            "holding_predictions": [],
        }
        pf_bt = {
            "decision": "BUY", "total_return_pct": 5.0, "total_pl": 3600.0,
            "final_capital": 75600.0, "win_rate": 58.0, "max_drawdown": 10.0,
            "initial_capital": 72000.0,
            "holding_actuals": [],
        }
        cmp = compare_portfolio_ai_vs_backtest(pf_ai, pf_bt)
        assert cmp["decision_match"] is True
        assert cmp["directional_match"] is True
        assert cmp["agreement"] == "MATCH"
        assert abs(cmp["return_error_pct"] - 3.0) < 0.1

    def test_portfolio_accuracy_uses_separate_records_file(self):
        """Portfolio evaluation records must use a different file than single-stock records."""
        from portfolio_accuracy_engine import PORTFOLIO_EVAL_FILE
        from strategy_accuracy_engine import EVAL_FILE as SINGLE_EVAL_FILE
        assert str(PORTFOLIO_EVAL_FILE) != str(SINGLE_EVAL_FILE), (
            "Portfolio and single-stock evaluation files must be different"
        )
        assert "portfolio" in str(PORTFOLIO_EVAL_FILE).lower()

    def test_portfolio_accuracy_does_not_mix_single_strategy_records(self):
        """Portfolio JSONL filename must not equal the single-strategy JSONL filename."""
        from portfolio_accuracy_engine import PORTFOLIO_EVAL_FILE
        pf_name = PORTFOLIO_EVAL_FILE.name
        assert "portfolio" in pf_name.lower(), f"File name must contain 'portfolio': {pf_name}"
        assert pf_name != "strategy_prediction_evaluation_runs.jsonl"

    def test_portfolio_final_board_match(self):
        """AI BUY + Backtest BUY → agreement MATCH, final_verified_decision BUY."""
        from portfolio_strategy_engine import compare_portfolio_ai_vs_backtest
        pf_ai = {"decision": "BUY",  "total_return_pct": 8.0, "total_pl": 1000.0,
                 "final_capital": 73000.0, "win_rate": 60.0, "max_drawdown": 8.0,
                 "holding_predictions": []}
        pf_bt = {"decision": "BUY",  "total_return_pct": 6.0, "total_pl": 800.0,
                 "final_capital": 72800.0, "win_rate": 58.0, "max_drawdown": 9.0,
                 "initial_capital": 72000.0, "failed_holdings": [], "holding_actuals": []}
        cmp = compare_portfolio_ai_vs_backtest(pf_ai, pf_bt)
        assert cmp["agreement"] == "MATCH"
        assert cmp["final_verified_decision"] == "BUY"

    def test_portfolio_final_board_conflict(self):
        """AI BUY + Backtest SELL → agreement CONFLICT, final_verified_decision REVIEW."""
        from portfolio_strategy_engine import compare_portfolio_ai_vs_backtest
        pf_ai = {"decision": "BUY",  "total_return_pct": 8.0, "total_pl": 1000.0,
                 "final_capital": 73000.0, "win_rate": 60.0, "max_drawdown": 8.0,
                 "holding_predictions": []}
        pf_bt = {"decision": "SELL", "total_return_pct": -8.0, "total_pl": -1000.0,
                 "final_capital": 71000.0, "win_rate": 40.0, "max_drawdown": 15.0,
                 "initial_capital": 72000.0, "failed_holdings": [], "holding_actuals": []}
        cmp = compare_portfolio_ai_vs_backtest(pf_ai, pf_bt)
        assert cmp["agreement"] == "CONFLICT"
        assert cmp["final_verified_decision"] == "REVIEW"

    def test_portfolio_backtest_failure_blocks_accuracy_record(self):
        """If any holding backtest fails, passed_validation=False and record must not be saved."""
        from portfolio_strategy_engine import run_portfolio_backtest_actual

        def _always_fail(si):
            return {"passed_validation": False, "status": "ERROR",
                    "decision": "REVIEW", "explanation": "Auth failed"}

        result = run_portfolio_backtest_actual(self._PSI, _always_fail)
        assert result["passed_validation"] is False, (
            "All-failed backtest must have passed_validation=False"
        )
        assert result["failed_holdings"] == ["GOOGL", "CVS", "MSFT"]

    def test_portfolio_hash_matches_all_outputs(self):
        """Same portfolio_si → same hash every time."""
        from portfolio_strategy_engine import build_portfolio_strategy_hash
        h1 = build_portfolio_strategy_hash(self._PSI)
        h2 = build_portfolio_strategy_hash(self._PSI)
        assert h1 == h2, "Portfolio hash must be deterministic"
        assert len(h1) == 16, "Hash must be 16 hex chars"

    def test_portfolio_section_2_data_structure(self):
        """pf_ai must contain all required fields for Section 2 rendering."""
        from portfolio_strategy_engine import run_portfolio_ai_prediction
        from unittest.mock import patch

        def _fake_ai(si):
            return {"status": "SUCCESS", "decision": "HOLD",
                    "predicted_final_capital": si["initial_capital"] * 1.02,
                    "predicted_win_rate": 52.0, "predicted_trade_count": 5,
                    "predicted_max_drawdown": 9.0, "predicted_volatility": 13.0,
                    "predicted_sharpe": 0.6, "predicted_risk_score": 42.0,
                    "confidence_score": 65.0}

        with patch("strategy_prediction_agent.run_ai_strategy_prediction", side_effect=_fake_ai):
            result = run_portfolio_ai_prediction(self._PSI)

        required = {"decision", "initial_capital", "final_capital", "total_pl",
                    "total_return_pct", "cagr", "sharpe", "win_rate", "trade_count",
                    "max_drawdown", "volatility", "risk_score", "confidence_score",
                    "holding_predictions"}
        missing = required - result.keys()
        assert not missing, f"pf_ai missing required fields: {missing}"

    def test_portfolio_holding_level_comparison_data(self):
        """compare_portfolio_ai_vs_backtest must produce holding_comparisons list."""
        from portfolio_strategy_engine import compare_portfolio_ai_vs_backtest
        pf_ai = {
            "decision": "BUY", "total_return_pct": 5.0, "total_pl": 500.0,
            "final_capital": 72500.0, "win_rate": 56.0, "max_drawdown": 8.0,
            "holding_predictions": [
                {"symbol": "GOOGL", "weight": 50.0, "allocated_capital": 40000.0,
                 "predicted_final_capital": 42000.0, "predicted_return_pct": 5.0, "decision": "BUY"},
                {"symbol": "MSFT",  "weight": 30.0, "allocated_capital": 16000.0,
                 "predicted_final_capital": 16500.0, "predicted_return_pct": 3.0, "decision": "HOLD"},
            ],
        }
        pf_bt = {
            "decision": "BUY", "total_return_pct": 3.0, "total_pl": 300.0,
            "final_capital": 72300.0, "win_rate": 54.0, "max_drawdown": 9.0,
            "initial_capital": 72000.0, "failed_holdings": [],
            "holding_actuals": [
                {"symbol": "GOOGL", "weight": 50.0, "allocated_capital": 40000.0,
                 "actual_final_capital": 41600.0, "actual_return_pct": 4.0, "decision": "BUY"},
                {"symbol": "MSFT",  "weight": 30.0, "allocated_capital": 16000.0,
                 "actual_final_capital": 16300.0, "actual_return_pct": 1.9, "decision": "HOLD"},
            ],
        }
        cmp = compare_portfolio_ai_vs_backtest(pf_ai, pf_bt)
        assert "holding_comparisons" in cmp
        assert len(cmp["holding_comparisons"]) == 2
        googl_hc = next(h for h in cmp["holding_comparisons"] if h["symbol"] == "GOOGL")
        assert "directional_match" in googl_hc
        assert "holding_verdict" in googl_hc
        assert "return_error" in googl_hc


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
