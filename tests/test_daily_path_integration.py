"""Integration tests: core/gemini_stock_prediction_agent.py's
run_gemini_stock_prediction must ALWAYS attach a day-by-day price path to
every prediction, and must attach a day-by-day options valuation whenever
the caller passes an explicit options_evaluation spec on spi -- the
"wire it into every prediction, not a one-off script" requirement."""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _make_bars(n: int = 300, start_price: float = 100.0) -> list:
    bars = []
    for i in range(n):
        close = round(start_price * (1 + 0.002 * math.sin(i / 10.0)), 4)
        bars.append({
            "date":   f"2025-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}",
            "open":   round(close * 0.999, 4),
            "high":   round(close * 1.005, 4),
            "low":    round(close * 0.995, 4),
            "close":  close,
            "volume": 1_000_000 + i * 1000,
        })
    return bars


def _fake_consensus_result(decision="BUY", return_pct=5.0):
    return {
        "status": "SUCCESS", "decision": decision,
        "decision_reason": "...", "predicted_return_pct": return_pct,
        "predicted_target_price": 100.0 * (1 + return_pct / 100.0),
        "predicted_final_capital": 10000.0 * (1 + return_pct / 100.0),
        "predicted_total_pl": 10000.0 * (return_pct / 100.0),
        "confidence_score": 60, "risk_score": 50, "data_quality_score": 90,
        "signal_scores": {}, "consensus_confidence": "HIGH",
        "consensus_votes": {"BUY": 3, "SELL": 0, "HOLD": 0},
        "consensus_calls": [], "gemini_latency_ms": 0,
        "prompt_hash": "", "gemini_output_hash": "",
    }


def _base_spi(horizon_days=7, **extra):
    spi = {
        "symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
        "historical_context_start_date": "2025-01-01",
        "prediction_origin_date": "2025-06-01",
        "target_date": "2025-06-08",
        "decision_horizon_days": horizon_days, "initial_capital": 10000,
    }
    spi.update(extra)
    return spi


def test_daily_price_path_always_present_no_options_requested(monkeypatch):
    import gemini_stock_prediction_agent as gsp_mod
    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", lambda *a, **k: _fake_consensus_result("BUY", 5.0))

    result = gsp_mod.run_gemini_stock_prediction(_base_spi(), _make_bars())

    assert result["status"] == "SUCCESS"
    assert len(result["daily_price_path"]) == 7
    assert result["daily_price_path"][-1]["day_offset"] == 7
    assert result["daily_price_path_methodology_note"]
    assert result["options_daily_path"] is None  # no options_evaluation was passed


def test_daily_price_path_terminal_day_matches_prediction(monkeypatch):
    import gemini_stock_prediction_agent as gsp_mod
    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", lambda *a, **k: _fake_consensus_result("SELL", -6.0))

    result = gsp_mod.run_gemini_stock_prediction(_base_spi(horizon_days=10), _make_bars())

    terminal = result["daily_price_path"][-1]
    assert terminal["day_offset"] == 10
    assert abs(terminal["predicted_return_pct"] - result["predicted_return_pct"]) < 0.5


def test_stock_entry_exit_recommendation_present(monkeypatch):
    import gemini_stock_prediction_agent as gsp_mod
    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", lambda *a, **k: _fake_consensus_result("BUY", 5.0))

    result = gsp_mod.run_gemini_stock_prediction(_base_spi(), _make_bars())

    rec = result["stock_entry_exit_recommendation"]
    assert rec.get("entry_day") is not None


def test_options_daily_path_computed_when_evaluation_spec_given(monkeypatch):
    """The core ask: passing an explicit options_evaluation spec must make
    run_gemini_stock_prediction automatically compute the day-by-day
    options valuation -- no separate script needed."""
    import gemini_stock_prediction_agent as gsp_mod
    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", lambda *a, **k: _fake_consensus_result("BUY", 5.0))

    spi = _base_spi(horizon_days=7, options_evaluation={
        "strike": 105.0, "option_type": "call", "dte": 7,
        "contracts": 10, "premium_paid_per_share": 2.0,
    })
    result = gsp_mod.run_gemini_stock_prediction(spi, _make_bars())

    opt = result["options_daily_path"]
    assert opt is not None
    assert opt["status"] == "OK"
    assert opt["strike"] == 105.0
    assert opt["option_type"] == "call"
    assert opt["contracts"] == 10
    assert opt["existing_position_recommendation"] is not None
    assert opt["existing_position_recommendation"]["total_cost"] == 2.0 * 100 * 10


def test_options_daily_path_without_premium_has_no_existing_position_rec(monkeypatch):
    import gemini_stock_prediction_agent as gsp_mod
    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", lambda *a, **k: _fake_consensus_result("SELL", -4.0))

    spi = _base_spi(horizon_days=7, options_evaluation={
        "strike": 95.0, "option_type": "put", "dte": 7, "contracts": 5,
    })
    result = gsp_mod.run_gemini_stock_prediction(spi, _make_bars())

    opt = result["options_daily_path"]
    assert opt is not None
    assert opt["status"] == "OK"
    assert opt["existing_position_recommendation"] is None
    assert opt["new_position_recommendation"] is not None


def test_options_daily_path_absent_fields_results_in_none(monkeypatch):
    """An incomplete options_evaluation (missing strike) must not crash --
    just no options path, same degrade-gracefully contract as every other
    optional enrichment in this project."""
    import gemini_stock_prediction_agent as gsp_mod
    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", lambda *a, **k: _fake_consensus_result("BUY", 5.0))

    spi = _base_spi(horizon_days=7, options_evaluation={"option_type": "call", "dte": 7})
    result = gsp_mod.run_gemini_stock_prediction(spi, _make_bars())

    assert result["status"] == "SUCCESS"
    assert result["options_daily_path"] is None


def test_daily_price_path_never_breaks_prediction_on_internal_error(monkeypatch):
    """Even if the path predictor itself throws, the main prediction must
    still succeed -- same try/except-degrade-gracefully contract as every
    other enrichment source. Patches the function object directly (not
    builtins.__import__, which risks destabilizing every other import in
    the same process) -- gemini_stock_prediction_agent's `from
    day_by_day_path_predictor import predict_daily_path` inside the try
    block does a fresh attribute lookup on the already-imported module each
    call, so patching the module's own attribute is sufficient and safe."""
    import gemini_stock_prediction_agent as gsp_mod
    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", lambda *a, **k: _fake_consensus_result("BUY", 5.0))

    import day_by_day_path_predictor as path_mod
    def _boom(*a, **k):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(path_mod, "predict_daily_path", _boom)

    result = gsp_mod.run_gemini_stock_prediction(_base_spi(), _make_bars())
    assert result["status"] == "SUCCESS"
    assert "daily_price_path" in result.get("context_enrichment_warnings", {})
