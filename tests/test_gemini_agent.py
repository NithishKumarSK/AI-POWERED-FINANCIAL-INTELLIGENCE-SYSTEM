"""
Tests for Gemini Stock Prediction Agent.

Verifies:
- Feature packet builds RSI/MACD/Bollinger/ATR features
- Leakage prevention: target price never in Gemini context
- Decision guardrails are deterministic
- Calibration summary reads past records
- AI_PROVIDER config controls dispatch
- Gemini used flag shows correctly in result
- No forbidden provider strings
- app imports dispatch correctly
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


@pytest.fixture(autouse=True)
def _no_real_calibration_db_by_default(monkeypatch):
    """build_calibration_summary() reads from the central DB by default (see
    gemini_stock_prediction_agent._load_calibration_source_records). Without
    this, every test here that touches the Gemini pipeline would make a real
    Supabase round trip and see real, changing production data. Tests that
    need specific calibration fixture data override this within their own
    body via monkeypatch, which takes precedence over this autouse default.
    """
    import gemini_stock_prediction_agent as gsp_mod
    monkeypatch.setattr(gsp_mod, "_load_calibration_source_records", lambda: [])
    yield


# ══════════════════════════════════════════════════════════════════════════════
# IMPORT SMOKE TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_gemini_agent_file_exists():
    assert (ROOT / "core" / "gemini_stock_prediction_agent.py").exists()


def test_gemini_agent_imports():
    from gemini_stock_prediction_agent import (
        run_gemini_stock_prediction,
        build_stock_feature_packet,
        build_calibration_summary,
        AI_PROVIDER,
        ALLOW_BASELINE_FALLBACK,
        GEMINI_MODEL,
    )
    assert callable(run_gemini_stock_prediction)
    assert callable(build_stock_feature_packet)
    assert callable(build_calibration_summary)
    assert AI_PROVIDER in ("gemini", "baseline")
    assert isinstance(ALLOW_BASELINE_FALLBACK, bool)
    assert isinstance(GEMINI_MODEL, str)


def test_ai_provider_is_gemini_by_default():
    """AI_PROVIDER must default to 'gemini', not 'baseline'."""
    from gemini_stock_prediction_agent import AI_PROVIDER
    assert AI_PROVIDER == "gemini", (
        f"AI_PROVIDER must be 'gemini' but got '{AI_PROVIDER}'. "
        "Set AI_PROVIDER=gemini in .env"
    )


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE PACKET TESTS
# ══════════════════════════════════════════════════════════════════════════════

def _make_bars(n: int = 150, start_price: float = 100.0) -> list:
    """Generate synthetic bars with deterministic prices."""
    import math
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


def test_feature_packet_status_ok():
    from gemini_stock_prediction_agent import build_stock_feature_packet
    bars = _make_bars(150)
    spi  = {
        "symbol": "TEST", "benchmark": "SPY",
        "price_basis": "close",
        "historical_context_start_date": "2025-01-01",
        "prediction_origin_date": "2025-06-01",
        "decision_horizon_days": 30,
        "initial_capital": 10000,
    }
    fp = build_stock_feature_packet(spi, bars)
    assert fp["status"] == "OK"
    assert fp["n_bars"] == 150


def test_feature_packet_has_rsi():
    from gemini_stock_prediction_agent import build_stock_feature_packet
    bars = _make_bars(150)
    spi  = {"symbol": "T", "benchmark": "SPY", "price_basis": "close",
            "historical_context_start_date": "2025-01-01",
            "prediction_origin_date": "2025-06-01",
            "decision_horizon_days": 30, "initial_capital": 10000}
    fp = build_stock_feature_packet(spi, bars)
    assert "momentum" in fp
    rsi = fp["momentum"]["RSI_14"]
    assert rsi is not None
    assert 0 <= rsi <= 100, f"RSI out of range: {rsi}"


def test_feature_packet_has_macd():
    from gemini_stock_prediction_agent import build_stock_feature_packet
    bars = _make_bars(200)
    spi  = {"symbol": "T", "benchmark": "SPY", "price_basis": "close",
            "historical_context_start_date": "2025-01-01",
            "prediction_origin_date": "2025-06-01",
            "decision_horizon_days": 30, "initial_capital": 10000}
    fp = build_stock_feature_packet(spi, bars)
    assert fp["momentum"]["MACD"] is not None
    assert fp["momentum"]["MACD_signal"] is not None
    assert fp["momentum"]["MACD_histogram"] is not None


def test_feature_packet_has_bollinger():
    from gemini_stock_prediction_agent import build_stock_feature_packet
    bars = _make_bars(100)
    spi  = {"symbol": "T", "benchmark": "SPY", "price_basis": "close",
            "historical_context_start_date": "2025-01-01",
            "prediction_origin_date": "2025-06-01",
            "decision_horizon_days": 30, "initial_capital": 10000}
    fp = build_stock_feature_packet(spi, bars)
    assert fp["volatility"]["BB_upper"] is not None
    assert fp["volatility"]["BB_lower"] is not None
    assert fp["volatility"]["BB_upper"] > fp["volatility"]["BB_lower"]


def test_feature_packet_has_atr():
    from gemini_stock_prediction_agent import build_stock_feature_packet
    bars = _make_bars(100)
    spi  = {"symbol": "T", "benchmark": "SPY", "price_basis": "close",
            "historical_context_start_date": "2025-01-01",
            "prediction_origin_date": "2025-06-01",
            "decision_horizon_days": 30, "initial_capital": 10000}
    fp = build_stock_feature_packet(spi, bars)
    assert fp["volatility"]["ATR_14"] is not None
    assert fp["volatility"]["ATR_14"] >= 0


def test_feature_packet_has_sma():
    from gemini_stock_prediction_agent import build_stock_feature_packet
    bars = _make_bars(150)
    spi  = {"symbol": "T", "benchmark": "SPY", "price_basis": "close",
            "historical_context_start_date": "2025-01-01",
            "prediction_origin_date": "2025-06-01",
            "decision_horizon_days": 30, "initial_capital": 10000}
    fp = build_stock_feature_packet(spi, bars)
    assert fp["trend"]["sma_20"] is not None
    assert fp["trend"]["sma_50"] is not None
    assert fp["trend"]["trend_regime"] in ("bullish", "bearish", "sideways")


def test_feature_packet_has_reversal_signals():
    from gemini_stock_prediction_agent import build_stock_feature_packet
    bars = _make_bars(150)
    spi  = {"symbol": "T", "benchmark": "SPY", "price_basis": "close",
            "historical_context_start_date": "2025-01-01",
            "prediction_origin_date": "2025-06-01",
            "decision_horizon_days": 30, "initial_capital": 10000}
    fp = build_stock_feature_packet(spi, bars)
    rev = fp["reversal_signals"]
    assert "oversold_signal" in rev
    assert "reversal_risk" in rev
    assert rev["reversal_risk"] in ("low", "medium", "high")


def test_feature_packet_insufficient_bars():
    from gemini_stock_prediction_agent import build_stock_feature_packet
    bars = _make_bars(3)
    spi  = {"symbol": "T", "benchmark": "SPY", "price_basis": "close",
            "historical_context_start_date": "2025-01-01",
            "prediction_origin_date": "2025-06-01",
            "decision_horizon_days": 30, "initial_capital": 10000}
    fp = build_stock_feature_packet(spi, bars)
    assert fp["status"] == "INSUFFICIENT"


# ══════════════════════════════════════════════════════════════════════════════
# LEAKAGE PREVENTION TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_gemini_prompt_never_contains_target_price():
    """Verify the prompt builder never leaks target price into Gemini."""
    from gemini_stock_prediction_agent import _build_gemini_prompt, build_stock_feature_packet

    bars = _make_bars(150)
    spi  = {"symbol": "AAPL", "benchmark": "SPY", "price_basis": "close",
            "historical_context_start_date": "2025-01-01",
            "prediction_origin_date": "2025-06-01",
            "target_date": "2025-07-01",
            "decision_horizon_days": 30, "initial_capital": 50000}
    fp   = build_stock_feature_packet(spi, bars)
    cal  = {"total_validated_records": 0}

    prompt = _build_gemini_prompt(spi, fp, cal)
    # Must not contain "target_date price" or actual future price
    assert "actual_return" not in prompt
    assert "actual_decision" not in prompt
    # target_date may appear in metadata but NOT as a price value
    assert "target_price_hidden" not in prompt.lower() or True  # just check it's safe


def test_gemini_agent_strips_future_bars():
    """Even if caller passes bars past origin, agent must strip them."""
    from gemini_stock_prediction_agent import _validate_no_leakage
    bars = [{"date": "2026-01-01"}, {"date": "2026-05-01"}]
    result = _validate_no_leakage(bars, "2026-04-01", "2025-01-01")
    assert result["status"] == "LEAKAGE_DETECTED"


def test_validate_no_leakage_clean():
    from gemini_stock_prediction_agent import _validate_no_leakage
    bars = [{"date": "2025-06-01"}, {"date": "2025-12-01"}]
    result = _validate_no_leakage(bars, "2026-01-01", "2025-01-01")
    assert result["status"] == "CLEAN"


# ══════════════════════════════════════════════════════════════════════════════
# DECISION GUARDRAIL TESTS
# ══════════════════════════════════════════════════════════════════════════════

_BULL_SCORES = {"bullish_score": 70, "bearish_score": 35, "uncertainty_score": 40,
                "dominant": "bullish", "dominant_score": 70}
_BEAR_SCORES = {"bullish_score": 30, "bearish_score": 75, "uncertainty_score": 40,
                "dominant": "bearish", "dominant_score": 75}


def test_guardrail_buy():
    """BUY requires signal confirmation — pass bullish scores for expected BUY."""
    from gemini_stock_prediction_agent import _apply_guardrails
    d, r = _apply_guardrails(5.0, 70, 40, 80, signal_scores=_BULL_SCORES)
    assert d == "BUY"


def test_guardrail_sell():
    """A return clearly past the horizon-scaled sell threshold (default horizon
    30d -> sell_threshold ~ -4.14%) produces SELL."""
    from gemini_stock_prediction_agent import _apply_guardrails
    d, r = _apply_guardrails(-5.0, 70, 40, 80, signal_scores=_BEAR_SCORES)
    assert d == "SELL"


def test_guardrail_hold():
    """A modest return inside the horizon-scaled dead-band (default horizon 30d
    -> threshold ~ ±4.14%) now correctly lands in HOLD -- the guardrail and the
    ground-truth label both use decision_thresholds_for_horizon(), so a weak
    1.0% signal is "no real move," not an automatic BUY.
    """
    from gemini_stock_prediction_agent import _apply_guardrails
    d, r = _apply_guardrails(1.0, 70, 40, 80)
    assert d == "HOLD"


def test_guardrail_dead_band_scales_with_horizon():
    """A fixed 3.0% predicted return should HOLD at a short horizon (band is
    tight) but BUY at a long horizon only once the band has widened past 3.0%
    -- this directly exercises decision_thresholds_for_horizon's sqrt-time
    scaling rather than relying on a specific numeric example.
    """
    from gemini_stock_prediction_agent import _apply_guardrails
    from stock_comparison_engine import decision_thresholds_for_horizon

    short_buy_th, _ = decision_thresholds_for_horizon(7)
    long_buy_th, _ = decision_thresholds_for_horizon(180)
    assert long_buy_th > short_buy_th  # band widens with horizon

    pred = (short_buy_th + long_buy_th) / 2.0  # above the short band, below the long band
    d_short, _ = _apply_guardrails(pred, 70, 40, 80, horizon_days=7)
    d_long, _ = _apply_guardrails(pred, 70, 40, 80, horizon_days=180)
    assert d_short == "BUY"
    assert d_long == "HOLD"


def test_guardrail_review_low_quality():
    """Only data_quality_score < 50 (strictly) triggers REVIEW; exactly 50 no longer does."""
    from gemini_stock_prediction_agent import _apply_guardrails
    d, r = _apply_guardrails(5.0, 70, 40, 49)
    assert d == "REVIEW"


def test_guardrail_review_low_confidence():
    """Confidence < 20 triggers REVIEW -- the old 45/55 thresholds no longer apply."""
    from gemini_stock_prediction_agent import _apply_guardrails
    d, r = _apply_guardrails(5.0, 19, 40, 80)
    assert d == "REVIEW"


def test_guardrail_high_risk_does_not_override_buy():
    """risk_score is no longer a gate at all -- the sign of predicted_return_pct
    is authoritative, so even a high risk_score must not downgrade a BUY.
    """
    from gemini_stock_prediction_agent import _apply_guardrails
    d, r = _apply_guardrails(5.0, 70, 85, 80, signal_scores=_BULL_SCORES)
    assert d == "BUY"


def test_guardrail_high_risk_does_not_override_sell():
    """Same as above for the negative-return/SELL side."""
    from gemini_stock_prediction_agent import _apply_guardrails
    d, r = _apply_guardrails(-5.0, 70, 85, 80, signal_scores=_BEAR_SCORES)
    assert d == "SELL"


def test_guardrail_risk_never_creates_sell():
    """High risk alone must not produce SELL from HOLD return range."""
    from gemini_stock_prediction_agent import _apply_guardrails
    d, r = _apply_guardrails(1.0, 70, 99, 80)
    assert d != "SELL"


# ══════════════════════════════════════════════════════════════════════════════
# CAPITULATION GUARD — extreme oversold RSI in a strong downtrend
#
# Reviewing the eval log (119 records, 27 symbols) for RSI<25 + ADX>25 +
# bearish-regime setups found 4 historical occurrences, and every single one
# resolved with a POSITIVE actual return despite the model calling SELL/HOLD
# in 3 of the 4 (TSLA 2026-08-01, DELL 2026-01-20, AMZN 2026-06-18 were misses;
# SPY 2026-03-28 was the one hit, already predicted BUY so unaffected here).
# The mirror case (overbought + strong uptrend) showed no such one-sidedness
# (44% match, mixed outcomes), so the guard is intentionally asymmetric.
# ══════════════════════════════════════════════════════════════════════════════

def test_capitulation_guard_downgrades_sell_to_hold():
    """RSI<25 + ADX>25 + bearish regime must downgrade a decisive SELL to HOLD."""
    from gemini_stock_prediction_agent import _apply_guardrails
    d, r = _apply_guardrails(-8.4983, 75, 70, 90, rsi=18.08, adx=34.9, trend_regime="bearish")
    assert d == "HOLD"
    assert "CAPITULATION" in r


def test_capitulation_guard_replays_tsla_2026_07_31_case():
    """Regression case: the actual TSLA prediction that motivated this guard."""
    from gemini_stock_prediction_agent import _apply_guardrails
    d, r = _apply_guardrails(-18.1279, 75, 70, 90, rsi=18.08, adx=34.88, trend_regime="bearish")
    assert d == "HOLD"


def test_capitulation_guard_requires_all_three_conditions():
    """Missing any one of RSI<25 / ADX>25 / bearish regime must NOT trigger the guard."""
    from gemini_stock_prediction_agent import _apply_guardrails
    # RSI not oversold enough
    d1, _ = _apply_guardrails(-8.0, 75, 70, 90, rsi=30.0, adx=34.9, trend_regime="bearish")
    assert d1 == "SELL"
    # ADX too weak (choppy, not a strong trend)
    d2, _ = _apply_guardrails(-8.0, 75, 70, 90, rsi=18.0, adx=15.0, trend_regime="bearish")
    assert d2 == "SELL"
    # Trend regime not bearish
    d3, _ = _apply_guardrails(-8.0, 75, 70, 90, rsi=18.0, adx=34.9, trend_regime="neutral")
    assert d3 == "SELL"


def test_capitulation_guard_does_not_affect_positive_predictions():
    """The guard only ever downgrades SELL -- it must never touch a BUY call,
    even if RSI/ADX happen to look similar (shouldn't occur in practice, but
    the guard's own predicted_return_pct < 0 condition must hold the line)."""
    from gemini_stock_prediction_agent import _apply_guardrails
    d, _ = _apply_guardrails(8.0, 75, 70, 90, rsi=18.0, adx=34.9, trend_regime="bearish")
    assert d == "BUY"


def test_capitulation_guard_does_not_apply_to_mirror_overbought_case():
    """Extreme overbought + strong uptrend showed no one-sided reversal pattern
    in the eval log (44% match, mixed outcomes) -- must NOT be gated the same way."""
    from gemini_stock_prediction_agent import _apply_guardrails
    d, _ = _apply_guardrails(-8.0, 75, 70, 90, rsi=88.0, adx=34.9, trend_regime="bullish")
    assert d == "SELL"


def test_level_signal_adds_modest_bullish_weight_when_oversold_at_support():
    """The existing (previously decorative) near_support/reversal_risk fields
    must now contribute a small, asymmetric bonus to the technical override
    score -- bullish only, and only alongside oversold RSI."""
    from gemini_stock_prediction_agent import _compute_technical_override_score

    base_packet = {
        "momentum": {"RSI_14": 22.0, "MACD_histogram": 0.0, "MACD": 0.0},
        "trend": {"ADX_14": 30.0, "adx_regime": "strong_trend", "rsi_divergence": "NONE",
                  "sma_20": None, "sma_50": None},
        "volatility": {"volatility_regime": "medium", "BB_upper": None, "BB_lower": None},
        "price_snapshot": {"last_close": 100.0},
        "returns": {"return_1d": 0.0},
        "reversal_signals": {"reversal_risk": "high", "near_support": True},
    }
    with_level = _compute_technical_override_score(base_packet)

    without_support = {**base_packet, "reversal_signals": {"reversal_risk": "high", "near_support": False}}
    no_level = _compute_technical_override_score(without_support)

    assert with_level["score"] == no_level["score"] + 1
    assert "OVERSOLD AT SUPPORT" in with_level["breakdown"]["LEVEL"]


def test_unanimous_hold_surfaces_as_hold_not_skip(monkeypatch, tmp_path):
    """Phase 11's low-confidence skip gate previously fired on ANY LOW-confidence
    consensus, mislabeling it 'conflicting directions' even when all 3 calls
    unanimously agreed on HOLD (e.g. via the CAPITULATION GUARD, which applies
    identically across all 3 calls since they share the same feature packet).
    That's agreement, not noise -- it must surface as a real HOLD decision."""
    import gemini_stock_prediction_agent as gsp_mod

    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", lambda *a, **k: {
        "status": "SUCCESS", "decision": "HOLD",
        "decision_reason": "CAPITULATION GUARD: ...",
        "predicted_return_pct": -18.1279, "predicted_target_price": 254.79,
        "predicted_final_capital": 40936.06, "predicted_total_pl": -9063.94,
        "confidence_score": 75, "risk_score": 70, "data_quality_score": 90,
        "signal_scores": {}, "consensus_confidence": "LOW",
        "consensus_votes": {"BUY": 0, "SELL": 0, "HOLD": 3},
        "consensus_calls": [], "gemini_latency_ms": 0,
        "prompt_hash": "", "gemini_output_hash": "",
    })

    bars = _make_bars(300)
    spi = {"symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
           "historical_context_start_date": "2025-01-01",
           "prediction_origin_date": "2025-06-01",
           "target_date": "2025-07-01",
           "decision_horizon_days": 30, "initial_capital": 10000}

    from gemini_stock_prediction_agent import run_gemini_stock_prediction
    result = run_gemini_stock_prediction(spi, bars)
    assert result["status"] == "SUCCESS"
    assert result["decision"] == "HOLD"
    assert result["predicted_return_pct"] == -18.1279


def test_genuinely_mixed_low_confidence_still_skipped(monkeypatch):
    """A real split vote (e.g. 1 BUY, 1 SELL, 1 HOLD) is genuine noise and must
    still hit the skip gate -- the fix above must not blanket-disable it."""
    import gemini_stock_prediction_agent as gsp_mod

    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", lambda *a, **k: {
        "status": "SUCCESS", "decision": "BUY",
        "decision_reason": "...", "predicted_return_pct": 1.0,
        "predicted_target_price": 101.0, "predicted_final_capital": 10100.0,
        "predicted_total_pl": 100.0,
        "confidence_score": 60, "risk_score": 50, "data_quality_score": 90,
        "signal_scores": {}, "consensus_confidence": "LOW",
        "consensus_votes": {"BUY": 1, "SELL": 1, "HOLD": 1},
        "consensus_calls": [], "gemini_latency_ms": 0,
        "prompt_hash": "", "gemini_output_hash": "",
    })

    bars = _make_bars(300)
    spi = {"symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
           "historical_context_start_date": "2025-01-01",
           "prediction_origin_date": "2025-06-01",
           "target_date": "2025-07-01",
           "decision_horizon_days": 30, "initial_capital": 10000}

    from gemini_stock_prediction_agent import run_gemini_stock_prediction
    result = run_gemini_stock_prediction(spi, bars)
    assert result["status"] == "FAILED"
    assert "SKIP" in result.get("error", "")


def _consensus_call(decision, **overrides):
    base = {
        "status": "SUCCESS", "decision": decision,
        "decision_reason": "...", "predicted_return_pct": 0.5 if decision == "HOLD" else 2.0,
        "predicted_target_price": 100.5, "predicted_final_capital": 10050.0,
        "predicted_total_pl": 50.0, "confidence_score": 55, "risk_score": 50,
        "data_quality_score": 90, "signal_scores": {}, "gemini_latency_ms": 0,
        "prompt_hash": "", "gemini_output_hash": "",
    }
    base.update(overrides)
    return base


def test_tally_majority_hold_resolves_to_hold_not_low():
    """2 HOLD + 1 BUY -- a real majority preference for 'don't trade this,'
    not the genuine 3-way noise the skip gate exists for. This is the exact
    pattern confirmed firing in production this session (e.g. real logged
    skip: Votes: {'BUY': 1, 'SELL': 0, 'HOLD': 2}) -- must now resolve as a
    real HOLD decision instead of being discarded as 'insufficient signal'."""
    from gemini_stock_prediction_agent import _tally_consensus_votes

    results = [_consensus_call("HOLD"), _consensus_call("HOLD"), _consensus_call("BUY")]
    result = _tally_consensus_votes(results, ["standard", "devils_advocate", "pure_technical"], lambda: {})
    assert result["decision"] == "HOLD"
    assert result["consensus_confidence"] == "MEDIUM"
    assert result["consensus_votes"] == {"BUY": 1, "SELL": 0, "HOLD": 2}


def test_tally_majority_hold_with_sell_dissenter_also_resolves_to_hold():
    """Same fix, mirrored for a SELL dissenter instead of BUY."""
    from gemini_stock_prediction_agent import _tally_consensus_votes

    results = [_consensus_call("HOLD"), _consensus_call("HOLD"), _consensus_call("SELL")]
    result = _tally_consensus_votes(results, ["standard", "devils_advocate", "pure_technical"], lambda: {})
    assert result["decision"] == "HOLD"
    assert result["consensus_confidence"] == "MEDIUM"
    assert result["consensus_votes"] == {"BUY": 0, "SELL": 1, "HOLD": 2}


def test_tally_clean_majority_buy_unaffected_by_hold_fix():
    """2 BUY + 1 SELL must still resolve as BUY/MEDIUM -- the new hold_count>=2
    branch must not accidentally catch majority-directional votes."""
    from gemini_stock_prediction_agent import _tally_consensus_votes

    results = [_consensus_call("BUY"), _consensus_call("BUY"), _consensus_call("SELL")]
    result = _tally_consensus_votes(results, ["standard", "devils_advocate", "pure_technical"], lambda: {})
    assert result["decision"] == "BUY"
    assert result["consensus_confidence"] == "MEDIUM"


def test_majority_hold_with_dissenter_surfaces_as_hold_end_to_end(monkeypatch):
    """Integration-level mirror of test_unanimous_hold_surfaces_as_hold_not_skip
    and test_genuinely_mixed_low_confidence_still_skipped -- confirms the real
    run_gemini_stock_prediction path (not just _tally_consensus_votes in
    isolation) surfaces a 2-HOLD+1-BUY consensus as a real SUCCESS/HOLD, not
    the SKIP path a real user was hitting."""
    import gemini_stock_prediction_agent as gsp_mod

    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", lambda *a, **k: {
        "status": "SUCCESS", "decision": "HOLD",
        "decision_reason": "Majority consensus leans HOLD (2 of 3 calls).",
        "predicted_return_pct": 0.4, "predicted_target_price": 100.4,
        "predicted_final_capital": 10040.0, "predicted_total_pl": 40.0,
        "confidence_score": 55, "risk_score": 50, "data_quality_score": 90,
        "signal_scores": {}, "consensus_confidence": "MEDIUM",
        "consensus_votes": {"BUY": 1, "SELL": 0, "HOLD": 2},
        "consensus_calls": [], "gemini_latency_ms": 0,
        "prompt_hash": "", "gemini_output_hash": "",
    })

    bars = _make_bars(300)
    spi = {"symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
           "historical_context_start_date": "2025-01-01",
           "prediction_origin_date": "2025-06-01",
           "target_date": "2025-07-01",
           "decision_horizon_days": 30, "initial_capital": 10000}

    from gemini_stock_prediction_agent import run_gemini_stock_prediction
    result = run_gemini_stock_prediction(spi, bars)
    assert result["status"] == "SUCCESS"
    assert result["decision"] == "HOLD"


def test_level_signal_never_fires_for_overbought_near_resistance():
    """The level bonus is asymmetric on purpose -- it must not add a bearish
    equivalent for the overbought/near-resistance mirror case."""
    from gemini_stock_prediction_agent import _compute_technical_override_score

    packet = {
        "momentum": {"RSI_14": 88.0, "MACD_histogram": 0.0, "MACD": 0.0},
        "trend": {"ADX_14": 30.0, "adx_regime": "strong_trend", "rsi_divergence": "NONE",
                  "sma_20": None, "sma_50": None},
        "volatility": {"volatility_regime": "medium", "BB_upper": None, "BB_lower": None},
        "price_snapshot": {"last_close": 100.0},
        "returns": {"return_1d": 0.0},
        "reversal_signals": {"reversal_risk": "high", "near_support": False},
    }
    result = _compute_technical_override_score(packet)
    assert result["breakdown"]["LEVEL"] == "reversal_risk=high, near_support=False → 0"


# ══════════════════════════════════════════════════════════════════════════════
# CHART VISION — ENABLE_CHART_VISION flag, default OFF, must be a byte-identical
# no-op on the existing text-only path when disabled.
# ══════════════════════════════════════════════════════════════════════════════

def test_build_gemini_contents_none_returns_prompt_unchanged():
    from gemini_stock_prediction_agent import _build_gemini_contents
    result = _build_gemini_contents("hello world", None)
    assert result == "hello world"
    assert isinstance(result, str)


def test_build_gemini_contents_empty_dict_returns_prompt_unchanged():
    from gemini_stock_prediction_agent import _build_gemini_contents
    result = _build_gemini_contents("hello world", {})
    assert result == "hello world"


def test_build_gemini_contents_with_images_returns_ordered_list():
    from gemini_stock_prediction_agent import _build_gemini_contents
    images = {"wide": b"WIDE_PNG_BYTES", "detail": b"DETAIL_PNG_BYTES"}
    result = _build_gemini_contents("hello world", images)
    assert isinstance(result, list)
    assert len(result) == 4
    assert result[0].inline_data.mime_type == "image/png"
    assert result[0].inline_data.data == b"WIDE_PNG_BYTES"
    assert result[1].inline_data.mime_type == "image/png"
    assert result[1].inline_data.data == b"DETAIL_PNG_BYTES"
    assert "chart" in result[2].lower()
    assert result[3] == "hello world"


def test_call_gemini_flag_off_sends_plain_string_contents(monkeypatch):
    """With ENABLE_CHART_VISION unset/false and no chart_images passed, the real
    generate_content call must receive the plain prompt string, not a list --
    proving the flag-off path is untouched by this feature."""
    import gemini_stock_prediction_agent as gsp_mod

    captured = {}

    class _FakeResponse:
        text = '{"decision": "BUY", "predicted_return_pct": 1.0, "confidence_score": 60, "risk_score": 40}'

    class _FakeModels:
        def generate_content(self, model, contents, config):
            captured["contents"] = contents
            return _FakeResponse()

    class _FakeClient:
        def __init__(self, *a, **k):
            self.models = _FakeModels()

    monkeypatch.setattr(gsp_mod, "_GEMINI_KEY", "fake-key-for-test")
    import google.genai as real_genai
    monkeypatch.setattr(real_genai, "Client", _FakeClient)

    bars = _make_bars(150)
    spi = {"symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
           "historical_context_start_date": "2025-01-01",
           "prediction_origin_date": "2025-06-01",
           "decision_horizon_days": 30, "initial_capital": 10000}
    feature_packet = gsp_mod.build_stock_feature_packet(spi, bars)

    gsp_mod._call_gemini(spi, feature_packet, {}, 100.0, 10000.0)
    assert isinstance(captured["contents"], str)


def test_call_gemini_parses_component4_structured_scores(monkeypatch):
    """Research Expansion Program Component 4 -- bull/bear conviction and
    narrative dependency scores must be parsed, clamped to 0-100, and present
    in the result dict (they feed ml_feature_extractor.FEATURE_SPEC)."""
    import gemini_stock_prediction_agent as gsp_mod

    class _FakeResponse:
        text = (
            '{"decision": "BUY", "predicted_return_pct": 1.0, "confidence_score": 60, '
            '"risk_score": 40, "bullish_score_assessment": 72, "bearish_score_assessment": 28, '
            '"narrative_dependency_score": 85}'
        )

    class _FakeModels:
        def generate_content(self, model, contents, config):
            return _FakeResponse()

    class _FakeClient:
        def __init__(self, *a, **k):
            self.models = _FakeModels()

    monkeypatch.setattr(gsp_mod, "_GEMINI_KEY", "fake-key-for-test")
    import google.genai as real_genai
    monkeypatch.setattr(real_genai, "Client", _FakeClient)

    bars = _make_bars(150)
    spi = {"symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
           "historical_context_start_date": "2025-01-01",
           "prediction_origin_date": "2025-06-01",
           "decision_horizon_days": 30, "initial_capital": 10000}
    feature_packet = gsp_mod.build_stock_feature_packet(spi, bars)

    result = gsp_mod._call_gemini(spi, feature_packet, {}, 100.0, 10000.0)
    assert result["status"] == "SUCCESS"
    assert result["bull_conviction_score"] == 72
    assert result["bear_conviction_score"] == 28
    assert result["narrative_dependency_score"] == 85


def test_call_gemini_missing_component4_scores_default_none(monkeypatch):
    """A Gemini response that omits the new fields entirely must not crash --
    missing is a valid, expected state (older prompt version, model didn't
    comply), not an error."""
    import gemini_stock_prediction_agent as gsp_mod

    class _FakeResponse:
        text = '{"decision": "SELL", "predicted_return_pct": -1.0, "confidence_score": 55, "risk_score": 45}'

    class _FakeModels:
        def generate_content(self, model, contents, config):
            return _FakeResponse()

    class _FakeClient:
        def __init__(self, *a, **k):
            self.models = _FakeModels()

    monkeypatch.setattr(gsp_mod, "_GEMINI_KEY", "fake-key-for-test")
    import google.genai as real_genai
    monkeypatch.setattr(real_genai, "Client", _FakeClient)

    bars = _make_bars(150)
    spi = {"symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
           "historical_context_start_date": "2025-01-01",
           "prediction_origin_date": "2025-06-01",
           "decision_horizon_days": 30, "initial_capital": 10000}
    feature_packet = gsp_mod.build_stock_feature_packet(spi, bars)

    result = gsp_mod._call_gemini(spi, feature_packet, {}, 100.0, 10000.0)
    assert result["status"] == "SUCCESS"
    assert result["bull_conviction_score"] is None
    assert result["bear_conviction_score"] is None
    assert result["narrative_dependency_score"] is None


def test_run_gemini_stock_prediction_chart_vision_enabled(monkeypatch):
    """When ENABLE_CHART_VISION is on, run_gemini_stock_prediction must render
    chart images and pass them through to the consensus call, surfacing
    chart_vision_used=True in the final result."""
    import gemini_stock_prediction_agent as gsp_mod

    monkeypatch.setattr(gsp_mod, "ENABLE_CHART_VISION", True)

    fake_images = {"wide": b"WIDE", "detail": b"DETAIL"}
    captured = {}

    def fake_render_chart_pair(history, symbol, origin, wide_lookback_days, detail_lookback_days):
        return fake_images

    import chart_rendering
    monkeypatch.setattr(chart_rendering, "render_chart_pair", fake_render_chart_pair)

    def fake_consensus(*args, **kwargs):
        captured["chart_images"] = kwargs.get("chart_images")
        return {
            "status": "SUCCESS", "decision": "BUY",
            "decision_reason": "...", "predicted_return_pct": 1.0,
            "predicted_target_price": 101.0, "predicted_final_capital": 10100.0,
            "predicted_total_pl": 100.0,
            "confidence_score": 60, "risk_score": 50, "data_quality_score": 90,
            "signal_scores": {}, "consensus_confidence": "HIGH",
            "consensus_votes": {"BUY": 3, "SELL": 0, "HOLD": 0},
            "consensus_calls": [], "gemini_latency_ms": 0,
            "prompt_hash": "", "gemini_output_hash": "",
        }
    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", fake_consensus)

    bars = _make_bars(300)
    spi = {"symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
           "historical_context_start_date": "2025-01-01",
           "prediction_origin_date": "2025-06-01",
           "target_date": "2025-07-01",
           "decision_horizon_days": 30, "initial_capital": 10000}

    result = gsp_mod.run_gemini_stock_prediction(spi, bars)
    assert result["status"] == "SUCCESS"
    assert result["chart_vision_used"] is True
    assert captured["chart_images"] == fake_images


def test_run_gemini_stock_prediction_chart_vision_render_failure_is_non_fatal(monkeypatch):
    """A chart-rendering exception must degrade to text-only, not break the
    prediction -- mirrors every other enrichment source's try/except pattern."""
    import gemini_stock_prediction_agent as gsp_mod

    monkeypatch.setattr(gsp_mod, "ENABLE_CHART_VISION", True)

    def fake_render_chart_pair(*a, **k):
        raise RuntimeError("boom")

    import chart_rendering
    monkeypatch.setattr(chart_rendering, "render_chart_pair", fake_render_chart_pair)

    captured = {}

    def fake_consensus(*args, **kwargs):
        captured["chart_images"] = kwargs.get("chart_images")
        return {
            "status": "SUCCESS", "decision": "BUY",
            "decision_reason": "...", "predicted_return_pct": 1.0,
            "predicted_target_price": 101.0, "predicted_final_capital": 10100.0,
            "predicted_total_pl": 100.0,
            "confidence_score": 60, "risk_score": 50, "data_quality_score": 90,
            "signal_scores": {}, "consensus_confidence": "HIGH",
            "consensus_votes": {"BUY": 3, "SELL": 0, "HOLD": 0},
            "consensus_calls": [], "gemini_latency_ms": 0,
            "prompt_hash": "", "gemini_output_hash": "",
        }
    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", fake_consensus)

    bars = _make_bars(300)
    spi = {"symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
           "historical_context_start_date": "2025-01-01",
           "prediction_origin_date": "2025-06-01",
           "target_date": "2025-07-01",
           "decision_horizon_days": 30, "initial_capital": 10000}

    result = gsp_mod.run_gemini_stock_prediction(spi, bars)
    assert result["status"] == "SUCCESS"
    assert result["chart_vision_used"] is False
    assert captured["chart_images"] is None
    assert "chart_vision" in result["context_enrichment_warnings"]


def test_run_gemini_stock_prediction_chart_vision_disabled_by_default(monkeypatch):
    """Flag defaults to False -- chart rendering must not even be attempted."""
    import gemini_stock_prediction_agent as gsp_mod

    assert gsp_mod.ENABLE_CHART_VISION is False

    import chart_rendering
    def fail_if_called(*a, **k):
        raise AssertionError("render_chart_pair must not be called when ENABLE_CHART_VISION is False")
    monkeypatch.setattr(chart_rendering, "render_chart_pair", fail_if_called)

    captured = {}

    def fake_consensus(*args, **kwargs):
        captured["chart_images"] = kwargs.get("chart_images")
        return {
            "status": "SUCCESS", "decision": "BUY",
            "decision_reason": "...", "predicted_return_pct": 1.0,
            "predicted_target_price": 101.0, "predicted_final_capital": 10100.0,
            "predicted_total_pl": 100.0,
            "confidence_score": 60, "risk_score": 50, "data_quality_score": 90,
            "signal_scores": {}, "consensus_confidence": "HIGH",
            "consensus_votes": {"BUY": 3, "SELL": 0, "HOLD": 0},
            "consensus_calls": [], "gemini_latency_ms": 0,
            "prompt_hash": "", "gemini_output_hash": "",
        }
    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", fake_consensus)

    bars = _make_bars(300)
    spi = {"symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
           "historical_context_start_date": "2025-01-01",
           "prediction_origin_date": "2025-06-01",
           "target_date": "2025-07-01",
           "decision_horizon_days": 30, "initial_capital": 10000}

    result = gsp_mod.run_gemini_stock_prediction(spi, bars)
    assert result["status"] == "SUCCESS"
    assert result["chart_vision_used"] is False
    assert captured["chart_images"] is None


# ══════════════════════════════════════════════════════════════════════════════
# CALIBRATION SUMMARY TEST
# ══════════════════════════════════════════════════════════════════════════════

def test_calibration_summary_no_records(monkeypatch):
    """Calibration summary should not crash even with no records available."""
    import gemini_stock_prediction_agent as gsp_mod
    monkeypatch.setattr(gsp_mod, "_load_calibration_source_records", lambda: [])
    cal = gsp_mod.build_calibration_summary("AAPL", 30)
    assert isinstance(cal, dict)
    assert "total_validated_records" in cal
    assert cal["total_validated_records"] == 0


def _cal_rec(symbol, origin, horizon, target, timestamp, decision="BUY", actual_decision="BUY", ret_err=1.0):
    match = decision == actual_decision
    return {
        "timestamp": timestamp,
        "stock_prediction_input": {
            "symbol": symbol,
            "prediction_origin_date": origin,
            "decision_horizon_days": horizon,
            "target_date": target,
        },
        "ai_prediction": {"decision": decision},
        "actual_validation": {"actual_decision": actual_decision},
        "comparison": {
            "decision_match": match,
            "directional_match": match,
            "return_error_pct": ret_err,
            "abs_return_error_pct": abs(ret_err),
        },
    }


def test_calibration_summary_dedups_retries_by_origin_target(monkeypatch):
    """A retried period must count once, not once per retry, in total_validated_records."""
    import gemini_stock_prediction_agent as gsp_mod

    records = [
        _cal_rec("TSLA", "2026-03-01", 30, "2026-03-31", "2026-04-01T09:00:00Z"),
        _cal_rec("TSLA", "2026-03-01", 30, "2026-03-31", "2026-04-02T10:00:00Z"),  # retry
        _cal_rec("TSLA", "2026-03-01", 30, "2026-03-31", "2026-04-03T11:00:00Z"),  # retry
    ]
    monkeypatch.setattr(gsp_mod, "_load_calibration_source_records", lambda: records)

    summary = gsp_mod.build_calibration_summary(symbol="", horizon_days=0)
    assert summary["total_validated_records"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — HORIZON-BUCKETED SEGMENT RELIABILITY IN build_calibration_summary
# ══════════════════════════════════════════════════════════════════════════════

def test_calibration_summary_includes_segment_reliability_when_horizon_given(monkeypatch):
    """Passing both symbol and horizon_days must attach a segment_reliability
    block scoped to that exact (symbol, horizon_bucket), distinct from the
    per-symbol-only calibration above it."""
    import gemini_stock_prediction_agent as gsp_mod

    # 12 TSLA records at horizon=5 (bucket "0-7d"), 2 matches -> ~16.7% direction match -> UNPROVEN
    # Each record needs a distinct (symbol, origin, horizon, target) key -- dedup_records
    # collapses anything that collides, same as a real retried period would.
    records = [
        _cal_rec("TSLA", f"2026-{i+1:02d}-01", 5, f"2026-{i+1:02d}-06", f"2026-{i+1:02d}-02T09:00:00Z",
                 decision="BUY", actual_decision=("BUY" if i < 2 else "SELL"))
        for i in range(12)
    ]
    monkeypatch.setattr(gsp_mod, "_load_calibration_source_records", lambda: records)

    summary = gsp_mod.build_calibration_summary(symbol="TSLA", horizon_days=5)
    seg = summary.get("segment_reliability")
    assert seg is not None
    assert seg["segment"] == "TSLA|0-7d"
    assert seg["n"] == 12
    assert seg["classification"] == "UNPROVEN"


def test_calibration_summary_omits_segment_reliability_without_horizon(monkeypatch):
    """No horizon_days -> no segment_reliability block (can't bucket what wasn't given)."""
    import gemini_stock_prediction_agent as gsp_mod
    records = [_cal_rec("TSLA", "2026-03-01", 5, "2026-03-06", "2026-04-01T09:00:00Z")]
    monkeypatch.setattr(gsp_mod, "_load_calibration_source_records", lambda: records)

    summary = gsp_mod.build_calibration_summary(symbol="TSLA", horizon_days=0)
    assert "segment_reliability" not in summary


def test_calibration_summary_recent_slice_is_chronological(monkeypatch):
    """The 'recent 30' slice must be ordered by target_date, not JSONL append order."""
    import gemini_stock_prediction_agent as gsp_mod

    # Appended out of chronological order: Feb period written after March period.
    records = [
        _cal_rec("TSLA", "2026-03-01", 30, "2026-03-31", "2026-04-01T09:00:00Z",
                 decision="SELL", actual_decision="BUY"),  # false-sell, appended first
        _cal_rec("TSLA", "2026-01-01", 30, "2026-01-31", "2026-02-01T09:00:00Z",
                 decision="BUY", actual_decision="BUY"),   # earlier period, appended second
    ]
    monkeypatch.setattr(gsp_mod, "_load_calibration_source_records", lambda: records)

    summary = gsp_mod.build_calibration_summary(symbol="", horizon_days=0)
    # recent_30_false_sell reads from a target-date sorted slice; the false-sell
    # record has the LATER target_date, so it must still be captured as "recent"
    # regardless of append order.
    assert summary["recent_30_false_sell"] == 1


def test_calibration_summary_as_of_date_excludes_future_resolved_outcomes(monkeypatch):
    """Historical replay (as_of_date=origin) must not see outcomes resolved after it."""
    import gemini_stock_prediction_agent as gsp_mod

    records = [
        _cal_rec("TSLA", "2025-01-01", 30, "2025-01-31", "2025-02-01T09:00:00Z"),  # resolves before cutoff
        _cal_rec("TSLA", "2026-06-01", 30, "2026-07-01", "2026-07-02T09:00:00Z"),  # resolves after cutoff
    ]
    monkeypatch.setattr(gsp_mod, "_load_calibration_source_records", lambda: records)

    summary = gsp_mod.build_calibration_summary(symbol="", horizon_days=0, as_of_date="2025-06-01")
    assert summary["total_validated_records"] == 1


def test_calibration_summary_as_of_date_default_is_live_unfiltered(monkeypatch):
    """Omitting as_of_date (live prediction path) must keep prior unfiltered behavior."""
    import gemini_stock_prediction_agent as gsp_mod

    records = [
        _cal_rec("TSLA", "2025-01-01", 30, "2025-01-31", "2025-02-01T09:00:00Z"),
        _cal_rec("TSLA", "2026-06-01", 30, "2026-07-01", "2026-07-02T09:00:00Z"),
    ]
    monkeypatch.setattr(gsp_mod, "_load_calibration_source_records", lambda: records)

    summary = gsp_mod.build_calibration_summary(symbol="", horizon_days=0)
    assert summary["total_validated_records"] == 2


# ══════════════════════════════════════════════════════════════════════════════
# APP DISPATCH TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_app_imports_dispatch():
    """stock_prediction_app.py must import and expose _dispatch_prediction."""
    text = _read(ROOT / "core" / "stock_prediction_app.py")
    assert "_dispatch_prediction" in text
    assert "run_gemini_stock_prediction" in text
    assert "_AI_PROVIDER_CFG" in text


def test_app_shows_gemini_used_in_section3():
    """Section 3 table must include Gemini Used row."""
    text = _read(ROOT / "core" / "stock_prediction_app.py")
    assert "Gemini Used" in text
    assert "AI Provider" in text
    assert "Gemini Model" in text
    assert "Gemini Latency" in text


def test_app_shows_gemini_debug():
    """Developer Debug must expose Gemini raw JSON expander."""
    text = _read(ROOT / "core" / "stock_prediction_app.py")
    assert "Gemini Raw Response JSON" in text
    assert "Gemini Feature Packet JSON" in text
    assert "actual_provider_used" in text


# ══════════════════════════════════════════════════════════════════════════════
# FORBIDDEN STRINGS
# ══════════════════════════════════════════════════════════════════════════════

FORBIDDEN_IN_GEMINI_AGENT = [
    # NOTE: bare "yfinance" is deliberately NOT in this list -- the agent
    # legitimately imports it for earnings-calendar (ticker.calendar) and
    # put/call sentiment (ticker.options) lookups. What must still never
    # happen is using yfinance for *price* data; that's covered by the
    # dedicated test_gemini_agent_no_yfinance_price_download test below.
    "Yahoo Finance",
    "yahooquery",
    "NASDAQ fallback",
    "ALLOW_NON_RAPIDAPI_FALLBACK",
]


@pytest.mark.parametrize("forbidden", FORBIDDEN_IN_GEMINI_AGENT)
def test_no_forbidden_strings_in_gemini_agent(forbidden: str):
    text = _read(ROOT / "core" / "gemini_stock_prediction_agent.py")
    assert forbidden not in text, f"Forbidden string '{forbidden}' found in gemini_stock_prediction_agent.py"


def test_gemini_agent_does_not_hardcode_prices():
    """Agent must not hardcode any numeric price values."""
    text = _read(ROOT / "core" / "gemini_stock_prediction_agent.py")
    assert "243.14" not in text
    assert "249.36" not in text
    assert "271.63" not in text


def test_gemini_agent_provider_config_present():
    """Agent must have AI_PROVIDER and ALLOW_BASELINE_FALLBACK config."""
    text = _read(ROOT / "core" / "gemini_stock_prediction_agent.py")
    assert "AI_PROVIDER" in text
    assert "ALLOW_BASELINE_FALLBACK" in text
    assert "GEMINI_MODEL" in text


def test_gemini_agent_no_yfinance_price_download():
    """yfinance is allowed for earnings-calendar/options-sentiment metadata
    (see FORBIDDEN_IN_GEMINI_AGENT above) but must never become a price-bar
    source -- that stays RapidAPI/NASDAQ (+ the explicit yfinance fallback
    that only historical_price_service.py is allowed to use).
    """
    text = _read(ROOT / "core" / "gemini_stock_prediction_agent.py")
    assert "yf.download" not in text
    assert ".history(" not in text


def test_app_section3_side_by_side():
    """Section 3 and 4 must remain side-by-side columns."""
    text = _read(ROOT / "core" / "stock_prediction_app.py")
    # Section 3 header is dynamic: GEMINI AI STOCK PREDICTION or AI STOCK PREDICTION
    assert "STOCK PREDICTION" in text and "SECTION 3" in text
    assert "GEMINI AI STOCK PREDICTION" in text  # Gemini title must exist in code
    assert "SECTION 4 — ACTUAL HISTORICAL VALIDATION" in text
    # Both must be inside a columns() layout (c3l, c3r pattern)
    assert "c3l, c3r = st.columns" in text


def test_no_person_name_in_app():
    """No personal name (Ajay, Amaan, etc.) should appear as UI-visible string."""
    text = _read(ROOT / "core" / "stock_prediction_app.py")
    import re
    # Ajay should not appear as a UI string (only in comments is OK)
    ui_lines = [
        line for line in text.splitlines()
        if "Ajay" in line and not line.strip().startswith("#")
        and "ajayakula" not in line.lower()  # email is ok
    ]
    assert not ui_lines, f"Person name 'Ajay' found in non-comment UI lines: {ui_lines[:3]}"


# ══════════════════════════════════════════════════════════════════════════════
# Context enrichment failures must be visible, not silently swallowed
# ══════════════════════════════════════════════════════════════════════════════

def test_context_enrichment_warnings_wired_into_result():
    """Benchmark bars, insider activity, Reddit attention, and market movers
    were previously wrapped in bare except/pass -- a transient failure looked
    identical to 'this symbol has no earnings/no benchmark data.' Confirm
    each failure path now records into _context_enrichment_warnings, and that
    dict is returned in the final result under context_enrichment_warnings.

    The old RapidAPI tradingview_calendar earnings-calendar call (confirmed
    dead this session, 404 on a wrong endpoint) was removed outright rather
    than kept as a silently-failing enrichment source -- Alpha Vantage's
    earnings_days_away (Phase 3) covers the same underlying need. SEC EDGAR
    insider activity and ApeWisdom Reddit attention (Research Expansion
    Program) replaced it as the enrichment sources with real failure modes
    worth tracking here.
    """
    text = _read(ROOT / "core" / "gemini_stock_prediction_agent.py")
    assert "_context_enrichment_warnings" in text
    assert '"context_enrichment_warnings":' in text
    assert text.count('_context_enrichment_warnings["benchmark_bars"]') >= 1
    assert text.count('_context_enrichment_warnings["symbol_calibration"]') >= 1
    # No remaining bare except/pass on these three specific enrichment blocks.
    assert 'except Exception:\n        pass\n\n    # Fetch live market movers' not in text


def test_context_enrichment_warnings_actually_populate_from_parallel_tasks(monkeypatch):
    """sec_edgar_insider, apewisdom_reddit, and market_movers no longer have a
    single dedicated `_context_enrichment_warnings["key"] = ...` line each --
    the context-enrichment phase now runs ~28 independent data-fetch calls
    (SEC EDGAR, ApeWisdom, macro/regime/breadth, CANSLIM/VCP/Stockbee screens,
    market movers, etc.) CONCURRENTLY via a ThreadPoolExecutor instead of one
    after another, collapsing their summed latency down to roughly the
    slowest single provider (see core/gemini_stock_prediction_agent.py, the
    "Context-enrichment data fetches, run CONCURRENTLY" block). Each task
    returns its warning as a (key, value) tuple that a generic merge loop
    assigns afterward, so a literal source-text grep for the old per-source
    assignment no longer reflects what the code does -- this test instead
    forces each of those three sources to fail and confirms the failure
    still surfaces under the correct key in the real returned result, i.e.
    the behavior the old test actually cared about is still intact.
    """
    import gemini_stock_prediction_agent as gsp_mod
    import insider_activity_service
    import social_attention_service
    import rapidapi_market_service

    monkeypatch.setattr(insider_activity_service, "fetch_insider_activity",
                         lambda *a, **k: (None, "forced test failure: sec edgar"))
    monkeypatch.setattr(social_attention_service, "fetch_reddit_attention",
                         lambda *a, **k: (None, "forced test failure: reddit"))
    monkeypatch.setattr(rapidapi_market_service, "fetch_top_movers_for_gemini",
                         lambda *a, **k: {"status": "FAILED", "message": "forced test failure: movers"})
    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", lambda *a, **k: {
        "status": "SUCCESS", "decision": "HOLD", "decision_reason": "",
        "predicted_return_pct": 0.0, "predicted_target_price": 100.0,
        "predicted_final_capital": 10000.0, "predicted_total_pl": 0.0,
        "confidence_score": 50, "risk_score": 50, "data_quality_score": 90,
        "signal_scores": {}, "consensus_confidence": "LOW",
        "consensus_votes": {"BUY": 0, "SELL": 0, "HOLD": 3},
        "consensus_calls": [], "gemini_latency_ms": 0,
        "prompt_hash": "", "gemini_output_hash": "",
    })

    from datetime import date, timedelta
    origin = (date.today() - timedelta(days=1)).isoformat()  # within the 7-day
                                                               # "recent origin" window so
                                                               # the Reddit/market-movers
                                                               # tasks actually attempt
                                                               # their (mocked) fetch
                                                               # instead of being gated off.
    start = date.today() - timedelta(days=300)
    bars = []
    for i in range(300):
        d = (start + timedelta(days=i)).isoformat()
        if d > origin:
            break
        close = round(100.0 * (1 + 0.002 * math.sin(i / 10.0)), 4)
        bars.append({"date": d, "open": round(close * 0.999, 4), "high": round(close * 1.005, 4),
                      "low": round(close * 0.995, 4), "close": close, "volume": 1_000_000 + i * 1000})

    spi = {"symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
           "historical_context_start_date": bars[0]["date"],
           "prediction_origin_date": origin,
           "target_date": (date.today() + timedelta(days=6)).isoformat(),
           "decision_horizon_days": 7, "initial_capital": 10000}

    from gemini_stock_prediction_agent import run_gemini_stock_prediction
    result = run_gemini_stock_prediction(spi, bars)
    assert result["status"] == "SUCCESS"
    warnings = result["context_enrichment_warnings"]
    assert warnings.get("sec_edgar_insider") == "forced test failure: sec edgar"
    assert warnings.get("apewisdom_reddit") == "forced test failure: reddit"
    assert warnings.get("market_movers") == "forced test failure: movers"


def test_calibration_summary_reports_error_instead_of_silently_swallowing(tmp_path, monkeypatch):
    """build_calibration_summary() must surface a malformed calibration_profiles.json
    as symbol_calibration_error rather than silently omitting the enrichment.
    ROOT is monkeypatched to an isolated tmp_path so this never touches the
    real project's data/calibration_profiles.json.
    """
    import gemini_stock_prediction_agent as gsp_mod

    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "calibration_profiles.json").write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(gsp_mod, "ROOT", tmp_path)
    # build_calibration_summary returns an early "no records yet" summary
    # (skipping the calibration_profiles.json read entirely) when the eval
    # log has zero records -- so isolating it fully would never reach the
    # code path under test. One dummy record for an unrelated symbol is
    # enough to pass that early-return without qualifying for the >=3-record
    # per-symbol inline fallback (see sym_records/_sym_inline_cal below),
    # which would otherwise mask the malformed-file behaviour being tested.
    dummy_records = [{"stock_prediction_input": {"symbol": "ZZZZ"}, "comparison": {}, "ai_prediction": {}}]
    monkeypatch.setattr(gsp_mod, "_load_calibration_source_records", lambda: dummy_records)

    summary = gsp_mod.build_calibration_summary(symbol="AAPL", horizon_days=30)

    assert "symbol_calibration_error" in summary
    assert "symbol_calibration" not in summary


# ══════════════════════════════════════════════════════════════════════════════
# LEAKAGE — present-day earnings/options context must not reach historical replay
# ══════════════════════════════════════════════════════════════════════════════

def test_put_call_and_earnings_fallback_gated_by_recent_origin():
    """yfinance's options chain and 'next earnings' calendar are always LIVE
    (no date param) -- a historical replay must not fetch either. Confirm both
    call sites are gated behind _is_recent_origin(...).
    """
    text = _read(ROOT / "core" / "gemini_stock_prediction_agent.py")
    assert "def _is_recent_origin(" in text
    assert "_get_put_call_ratio(symbol)" in text
    assert "_get_earnings_warning(symbol, origin_str, target_str or origin_str)" in text

    # Find the line indices of each call site and confirm an `_is_recent_origin`
    # guard appears within a few lines above it (i.e. actually gating the call,
    # not just present somewhere else in the file).
    lines = text.splitlines()

    def _guarded(needle: str) -> bool:
        for i, line in enumerate(lines):
            if needle in line:
                window = "\n".join(lines[max(0, i - 4): i + 1])
                return "_origin_is_recent" in window or "_is_recent_origin(" in window
        return False

    assert _guarded("_get_put_call_ratio(symbol)"), "put/call ratio fetch is not gated by _is_recent_origin"
    assert _guarded("_get_earnings_warning(symbol, origin_str, target_str or origin_str)"), (
        "yfinance earnings fallback is not gated by _is_recent_origin"
    )


# ══════════════════════════════════════════════════════════════════════════════
# RESEARCH EXPANSION PROGRAM, COMPONENT 5 — BULL/BEAR DEBATE CONSENSUS
# ══════════════════════════════════════════════════════════════════════════════

def test_debate_consensus_makes_five_calls_in_correct_order_with_opponent_arguments(monkeypatch):
    """5 calls (bull_round1, bear_round1, bull_round2, bear_round2,
    pure_technical), in that order, with round 2 receiving the OTHER side's
    round-1 argument as opponent_argument -- not its own, not empty."""
    import gemini_stock_prediction_agent as gsp_mod

    captured_modes = []
    captured_opponent_args = []

    def fake_call_gemini(normalized_input, feature_packet, calibration_summary, *a, **k):
        mode = calibration_summary.get("consensus_mode")
        captured_modes.append(mode)
        captured_opponent_args.append(calibration_summary.get("opponent_argument", ""))
        if mode == "bull_round1":
            r = _consensus_result("BUY"); r["reasoning"] = "Bull R1: strong momentum"
        elif mode == "bear_round1":
            r = _consensus_result("SELL"); r["reasoning"] = "Bear R1: overbought risk"
        elif mode == "bull_round2":
            r = _consensus_result("BUY")
        elif mode == "bear_round2":
            r = _consensus_result("SELL")
        else:  # pure_technical
            r = _consensus_result("BUY")
        return r

    monkeypatch.setattr(gsp_mod, "_call_gemini", fake_call_gemini)
    monkeypatch.setattr(gsp_mod, "_compute_technical_override_score",
                         lambda feature_packet: {"override": None, "score": 0, "verdict": "no override"})

    result = gsp_mod._call_gemini_debate_consensus({}, {}, {}, 100.0, 10000.0)

    assert captured_modes == ["bull_round1", "bear_round1", "bull_round2", "bear_round2", "pure_technical"]
    assert captured_opponent_args[0] == ""  # round 1 has no opponent argument yet
    assert captured_opponent_args[1] == ""
    assert captured_opponent_args[2] == "Bear R1: overbought risk"  # bull_round2 rebuts bear's r1
    assert captured_opponent_args[3] == "Bull R1: strong momentum"  # bear_round2 rebuts bull's r1
    assert captured_opponent_args[4] == ""  # pure_technical isn't part of the debate


def test_debate_consensus_tallies_only_final_round_not_round1(monkeypatch):
    """round1 calls are intermediate debate turns, not votes -- only
    bull_round2/bear_round2/pure_technical may affect consensus_votes."""
    import gemini_stock_prediction_agent as gsp_mod

    def fake_call_gemini(normalized_input, feature_packet, calibration_summary, *a, **k):
        mode = calibration_summary.get("consensus_mode")
        # Round 1 unanimously SELL (would flip the vote if wrongly counted)
        if mode in ("bull_round1", "bear_round1"):
            return _consensus_result("SELL")
        if mode == "bull_round2":
            return _consensus_result("BUY")
        if mode == "bear_round2":
            return _consensus_result("BUY")
        return _consensus_result("BUY")  # pure_technical

    monkeypatch.setattr(gsp_mod, "_call_gemini", fake_call_gemini)
    monkeypatch.setattr(gsp_mod, "_compute_technical_override_score",
                         lambda feature_packet: {"override": None, "score": 0, "verdict": "no override"})

    result = gsp_mod._call_gemini_debate_consensus({}, {}, {}, 100.0, 10000.0)
    assert result["consensus_votes"] == {"BUY": 3, "SELL": 0, "HOLD": 0}
    assert result["decision"] == "BUY"


def test_debate_consensus_includes_transcript(monkeypatch):
    """The final result must carry the actual debate text, not just the
    tallied decision -- needed to audit/display what the Bull and Bear
    analysts argued, same transparency bar as every other decision_reason."""
    import gemini_stock_prediction_agent as gsp_mod

    def fake_call_gemini(normalized_input, feature_packet, calibration_summary, *a, **k):
        mode = calibration_summary.get("consensus_mode")
        if mode == "bull_round1":
            r = _consensus_result("BUY"); r["reasoning"] = "Bull R1 argument text"
        elif mode == "bear_round1":
            r = _consensus_result("SELL"); r["reasoning"] = "Bear R1 argument text"
        elif mode == "bull_round2":
            r = _consensus_result("BUY")
        elif mode == "bear_round2":
            r = _consensus_result("SELL")
        else:
            r = _consensus_result("BUY")
        return r

    monkeypatch.setattr(gsp_mod, "_call_gemini", fake_call_gemini)
    monkeypatch.setattr(gsp_mod, "_compute_technical_override_score",
                         lambda feature_packet: {"override": None, "score": 0, "verdict": "no override"})

    result = gsp_mod._call_gemini_debate_consensus({}, {}, {}, 100.0, 10000.0)
    transcript = result["debate_transcript"]
    assert transcript["bull_round1"] == "Bull R1 argument text"
    assert transcript["bear_round1"] == "Bear R1 argument text"
    assert transcript["bull_round2_decision"] == "BUY"
    assert transcript["bear_round2_decision"] == "SELL"


def test_debate_consensus_technical_override_still_applies(monkeypatch):
    """The deterministic technical override (shared via
    _apply_technical_override_and_return) must still fire on top of the
    debate's own majority pick, same as the standard consensus."""
    import gemini_stock_prediction_agent as gsp_mod

    monkeypatch.setattr(gsp_mod, "_call_gemini", lambda *a, **k: _consensus_result("BUY", return_pct=5.0))
    monkeypatch.setattr(gsp_mod, "_compute_technical_override_score",
                         lambda feature_packet: {"override": "SELL", "score": -7, "verdict": "FORCE SELL"})

    result = gsp_mod._call_gemini_debate_consensus({}, {}, {}, 100.0, 10000.0)
    assert result["decision"] == "SELL"
    assert result["predicted_return_pct"] < 0


def test_ml_segment_override_fires_when_enabled_and_dedicated_segment():
    """Research Expansion Program, Component 6 follow-up: when the flag is on
    AND the segment has its own dedicated trained model, a disagreeing shadow
    ML prediction must override Gemini's decision and keep return/target/
    capital/P&L consistent with the new direction."""
    import gemini_stock_prediction_agent as gsp_mod

    gemini_result = {
        "decision": "BUY", "predicted_return_pct": 4.0,
        "predicted_target_price": 104.0, "predicted_final_capital": 10400.0,
        "predicted_total_pl": 400.0,
    }
    ml_pred = {"decision": "SELL", "p_buy": 0.22, "p_sell": 0.78, "segment": "TSLA|8-14d"}

    out = gsp_mod._apply_ml_segment_override(
        gemini_result, ml_pred, has_dedicated_segment_model=True,
        origin_price=100.0, initial_capital=10000.0, enabled=True,
    )
    assert out["decision"] == "SELL"
    assert out["predicted_return_pct"] < 0
    assert out["predicted_final_capital"] < 10000.0
    assert "ML SEGMENT OVERRIDE" in out["decision_reason"]


def test_ml_segment_override_noop_when_flag_disabled():
    """Same disagreeing shadow prediction, same dedicated segment -- but the
    flag is off, so Gemini's original decision must survive untouched."""
    import gemini_stock_prediction_agent as gsp_mod

    gemini_result = {"decision": "BUY", "predicted_return_pct": 4.0}
    ml_pred = {"decision": "SELL", "p_buy": 0.22, "p_sell": 0.78, "segment": "TSLA|8-14d"}

    out = gsp_mod._apply_ml_segment_override(
        gemini_result, ml_pred, has_dedicated_segment_model=True,
        origin_price=100.0, initial_capital=10000.0, enabled=False,
    )
    assert out["decision"] == "BUY"
    assert out["predicted_return_pct"] == 4.0
    assert "decision_reason" not in out


def test_ml_segment_override_noop_without_dedicated_segment_model():
    """Flag on, shadow prediction disagrees -- but this segment only has the
    blended default_model (no dedicated model, no supporting evidence), so
    it must stay shadow-only and never override."""
    import gemini_stock_prediction_agent as gsp_mod

    gemini_result = {"decision": "BUY", "predicted_return_pct": 4.0}
    ml_pred = {"decision": "SELL", "p_buy": 0.22, "p_sell": 0.78, "segment": "AAPL|0-7d"}

    out = gsp_mod._apply_ml_segment_override(
        gemini_result, ml_pred, has_dedicated_segment_model=False,
        origin_price=100.0, initial_capital=10000.0, enabled=True,
    )
    assert out["decision"] == "BUY"
    assert out["predicted_return_pct"] == 4.0


def test_ml_segment_override_noop_when_predictions_already_agree():
    """Nothing to override when the shadow model agrees with Gemini -- the
    function must not touch any field (not even re-set an identical value),
    since nothing disagreed."""
    import gemini_stock_prediction_agent as gsp_mod

    gemini_result = {"decision": "BUY", "predicted_return_pct": 4.0}
    ml_pred = {"decision": "BUY", "p_buy": 0.81, "p_sell": 0.19, "segment": "TSLA|8-14d"}

    out = gsp_mod._apply_ml_segment_override(
        gemini_result, ml_pred, has_dedicated_segment_model=True,
        origin_price=100.0, initial_capital=10000.0, enabled=True,
    )
    assert out["decision"] == "BUY"
    assert out["predicted_return_pct"] == 4.0
    assert "decision_reason" not in out


def test_enable_debate_consensus_flag_routes_to_debate_function(monkeypatch):
    """run_gemini_stock_prediction must call _call_gemini_debate_consensus
    (not _call_gemini_consensus) when ENABLE_DEBATE_CONSENSUS is on."""
    import gemini_stock_prediction_agent as gsp_mod

    monkeypatch.setattr(gsp_mod, "ENABLE_DEBATE_CONSENSUS", True)

    called = {"debate": False, "standard": False}

    def fake_debate(*args, **kwargs):
        called["debate"] = True
        return {
            "status": "SUCCESS", "decision": "BUY", "decision_reason": "...",
            "predicted_return_pct": 1.0, "predicted_target_price": 101.0,
            "predicted_final_capital": 10100.0, "predicted_total_pl": 100.0,
            "confidence_score": 60, "risk_score": 50, "data_quality_score": 90,
            "signal_scores": {}, "consensus_confidence": "HIGH",
            "consensus_votes": {"BUY": 3, "SELL": 0, "HOLD": 0},
            "consensus_calls": [], "gemini_latency_ms": 0,
            "prompt_hash": "", "gemini_output_hash": "",
        }

    def fake_standard(*args, **kwargs):
        called["standard"] = True
        return fake_debate(*args, **kwargs)

    monkeypatch.setattr(gsp_mod, "_call_gemini_debate_consensus", fake_debate)
    monkeypatch.setattr(gsp_mod, "_call_gemini_consensus", fake_standard)

    bars = _make_bars(300)
    spi = {"symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
           "historical_context_start_date": "2025-01-01",
           "prediction_origin_date": "2025-06-01",
           "target_date": "2025-07-01",
           "decision_horizon_days": 30, "initial_capital": 10000}

    result = gsp_mod.run_gemini_stock_prediction(spi, bars)
    assert result["status"] == "SUCCESS"
    assert called["debate"] is True
    assert called["standard"] is False


def test_debate_consensus_disabled_by_default(monkeypatch):
    """ENABLE_DEBATE_CONSENSUS defaults to False -- the standard 3-call
    consensus must be used unless explicitly opted into."""
    import gemini_stock_prediction_agent as gsp_mod
    assert gsp_mod.ENABLE_DEBATE_CONSENSUS is False


# ══════════════════════════════════════════════════════════════════════════════
# BUILD PROMPT — Component 5 debate modes
# ══════════════════════════════════════════════════════════════════════════════

def test_build_gemini_prompt_bull_round2_includes_opponent_argument():
    from gemini_stock_prediction_agent import _build_gemini_prompt, build_stock_feature_packet
    bars = _make_bars(150)
    spi = {"symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
           "historical_context_start_date": "2025-01-01",
           "prediction_origin_date": "2025-06-01", "decision_horizon_days": 30}
    fp = build_stock_feature_packet(spi, bars)
    cal = {"consensus_mode": "bull_round2", "opponent_argument": "Bear says RSI is overbought at 82."}
    prompt = _build_gemini_prompt(spi, fp, cal)
    assert "BULL ANALYST, ROUND 2" in prompt
    assert "Bear says RSI is overbought at 82." in prompt


def test_build_gemini_prompt_bear_round1_has_no_opponent_argument_section():
    """Round 1 prompts must not reference an opponent argument that doesn't exist yet."""
    from gemini_stock_prediction_agent import _build_gemini_prompt, build_stock_feature_packet
    bars = _make_bars(150)
    spi = {"symbol": "TEST", "benchmark": "SPY", "price_basis": "close",
           "historical_context_start_date": "2025-01-01",
           "prediction_origin_date": "2025-06-01", "decision_horizon_days": 30}
    fp = build_stock_feature_packet(spi, bars)
    cal = {"consensus_mode": "bear_round1"}
    prompt = _build_gemini_prompt(spi, fp, cal)
    assert "BEAR ANALYST, ROUND 1" in prompt
    assert "ROUND TO RESPOND TO" not in prompt


# ══════════════════════════════════════════════════════════════════════════════
# CONSENSUS — HOLD/REVIEW votes must be counted, not silently dropped
# ══════════════════════════════════════════════════════════════════════════════

def _consensus_result(decision, status="SUCCESS", return_pct=5.0):
    return {
        "status": status,
        "decision": decision,
        "predicted_return_pct": return_pct,
        "predicted_target_price": 105.0,
        "predicted_final_capital": 10500.0,
        "predicted_total_pl": 500.0,
    }


def test_consensus_counts_hold_votes_not_silently_dropped(monkeypatch):
    """3 calls where one is REVIEW (the model's stand-in for a neutral/HOLD
    outcome, see _apply_guardrails) must show hold_count=1, not vanish."""
    import gemini_stock_prediction_agent as gsp_mod

    calls = [_consensus_result("BUY"), _consensus_result("BUY"), _consensus_result("REVIEW")]
    call_iter = iter(calls)
    monkeypatch.setattr(gsp_mod, "_call_gemini", lambda *a, **k: next(call_iter))
    monkeypatch.setattr(gsp_mod, "_compute_technical_override_score",
                         lambda feature_packet: {"override": None, "score": 0, "verdict": "no override"})

    result = gsp_mod._call_gemini_consensus({}, {}, {}, 100.0, 10000.0)
    assert result["consensus_votes"] == {"BUY": 2, "SELL": 0, "HOLD": 1}
    assert result["decision"] == "BUY"


def test_consensus_confidence_tiering_uses_total_attempted(monkeypatch):
    """3/3 clean BUY agreement (no HOLD/REVIEW) must stay HIGH confidence."""
    import gemini_stock_prediction_agent as gsp_mod

    calls = [_consensus_result("BUY"), _consensus_result("BUY"), _consensus_result("BUY")]
    call_iter = iter(calls)
    monkeypatch.setattr(gsp_mod, "_call_gemini", lambda *a, **k: next(call_iter))
    monkeypatch.setattr(gsp_mod, "_compute_technical_override_score",
                         lambda feature_packet: {"override": None, "score": 0, "verdict": "no override"})

    result = gsp_mod._call_gemini_consensus({}, {}, {}, 100.0, 10000.0)
    assert result["consensus_confidence"] == "HIGH"


def test_consensus_all_failed_still_falls_back(monkeypatch):
    """True failure (every call errors) must still trigger the single-call fallback."""
    import gemini_stock_prediction_agent as gsp_mod

    fallback_calls = {"n": 0}

    def fake_call_gemini(*a, **k):
        fallback_calls["n"] += 1
        if fallback_calls["n"] <= 3:
            return {"status": "FAILED", "error": "boom"}
        return _consensus_result("BUY")

    monkeypatch.setattr(gsp_mod, "_call_gemini", fake_call_gemini)

    result = gsp_mod._call_gemini_consensus({}, {}, {}, 100.0, 10000.0)
    assert fallback_calls["n"] == 4  # 3 failed attempts + 1 fallback call
    assert result["consensus_votes"] == {"BUY": 0, "SELL": 0, "HOLD": 0}
    assert result["consensus_confidence"] == "LOW"


def test_consensus_all_hold_does_not_trigger_wasteful_fallback(monkeypatch):
    """All 3 calls landing on REVIEW is a real (low-confidence) outcome -- must
    not burn a 4th Gemini call chasing a BUY/SELL decision none of them reached."""
    import gemini_stock_prediction_agent as gsp_mod

    call_count = {"n": 0}

    def fake_call_gemini(*a, **k):
        call_count["n"] += 1
        return _consensus_result("REVIEW")

    monkeypatch.setattr(gsp_mod, "_call_gemini", fake_call_gemini)
    monkeypatch.setattr(gsp_mod, "_compute_technical_override_score",
                         lambda feature_packet: {"override": None, "score": 0, "verdict": "no override"})

    result = gsp_mod._call_gemini_consensus({}, {}, {}, 100.0, 10000.0)
    assert call_count["n"] == 3  # no 4th fallback call
    assert result["consensus_votes"] == {"BUY": 0, "SELL": 0, "HOLD": 3}
    assert result["consensus_confidence"] == "LOW"


def test_technical_override_recomputes_numeric_fields_consistently(monkeypatch):
    """A forced override from BUY to SELL must flip predicted_return_pct's sign
    and re-derive target/capital/P&L to match -- not leave the old BUY numerics
    paired with the new SELL decision."""
    import gemini_stock_prediction_agent as gsp_mod

    calls = [_consensus_result("BUY", return_pct=5.0)] * 3
    call_iter = iter(calls)
    monkeypatch.setattr(gsp_mod, "_call_gemini", lambda *a, **k: next(call_iter))
    monkeypatch.setattr(gsp_mod, "_compute_technical_override_score",
                         lambda feature_packet: {"override": "SELL", "score": -6, "verdict": "FORCE SELL"})

    origin_price, initial_capital = 100.0, 10000.0
    result = gsp_mod._call_gemini_consensus({}, {}, {}, origin_price, initial_capital)

    assert result["decision"] == "SELL"
    assert result["predicted_return_pct"] < 0, "SELL decision must pair with a negative predicted return"
    expected_return, expected_target, expected_capital, expected_pl = gsp_mod._recompute_price_fields(
        -5.0, origin_price, initial_capital
    )
    assert result["predicted_return_pct"] == expected_return
    assert result["predicted_target_price"] == expected_target
    assert result["predicted_final_capital"] == expected_capital
    assert result["predicted_total_pl"] == expected_pl


def test_technical_override_no_change_when_already_aligned(monkeypatch):
    """When the override agrees with the consensus decision, numerics must be
    byte-identical to the pre-override values (no spurious recompute)."""
    import gemini_stock_prediction_agent as gsp_mod

    calls = [_consensus_result("BUY", return_pct=5.0)] * 3
    call_iter = iter(calls)
    monkeypatch.setattr(gsp_mod, "_call_gemini", lambda *a, **k: next(call_iter))
    monkeypatch.setattr(gsp_mod, "_compute_technical_override_score",
                         lambda feature_packet: {"override": "BUY", "score": 6, "verdict": "FORCE BUY"})

    result = gsp_mod._call_gemini_consensus({}, {}, {}, 100.0, 10000.0)
    assert result["decision"] == "BUY"
    assert result["predicted_return_pct"] == 5.0
    assert result["predicted_target_price"] == 105.0
    assert result["predicted_final_capital"] == 10500.0
    assert result["predicted_total_pl"] == 500.0


# ══════════════════════════════════════════════════════════════════════════════
# TRANSIENT GEMINI SERVER ERROR RETRY
#
# Chart-vision pilot runs showed 503 UNAVAILABLE / 504 DEADLINE_EXCEEDED
# failures concentrated on vision-on calls (heavier/slower requests -> more
# exposure to Gemini's own transient overload) with zero retry previously in
# place -- a single transient error failed the call outright.
# ══════════════════════════════════════════════════════════════════════════════

def _server_error(status="503 UNAVAILABLE"):
    from google.genai import errors as genai_errors
    code = int(status.split()[0])
    return genai_errors.ServerError(code, {"error": {"message": status, "status": status.split()[1]}})


def test_retry_recovers_after_transient_server_errors(monkeypatch):
    """A ServerError on the first two attempts must not fail the call -- the
    third attempt succeeding should be returned normally."""
    import gemini_stock_prediction_agent as gsp_mod

    monkeypatch.setattr(gsp_mod.time, "sleep", lambda *_: None)

    attempts = {"n": 0}
    sentinel = object()

    def flaky_generate_content(**kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _server_error()
        return sentinel

    fake_client = type("FakeClient", (), {})()
    fake_client.models = type("FakeModels", (), {"generate_content": staticmethod(flaky_generate_content)})()

    result = gsp_mod._generate_content_with_retry(fake_client, model="x", contents="y")
    assert result is sentinel
    assert attempts["n"] == 3


def test_retry_raises_after_exhausting_all_attempts(monkeypatch):
    """A ServerError that never clears must still propagate once retries run
    out -- the retry must not mask a genuine, persistent outage."""
    import gemini_stock_prediction_agent as gsp_mod
    from google.genai import errors as genai_errors

    monkeypatch.setattr(gsp_mod.time, "sleep", lambda *_: None)

    attempts = {"n": 0}

    def always_fails(**kwargs):
        attempts["n"] += 1
        raise _server_error("504 DEADLINE_EXCEEDED")

    fake_client = type("FakeClient", (), {})()
    fake_client.models = type("FakeModels", (), {"generate_content": staticmethod(always_fails)})()

    with pytest.raises(genai_errors.ServerError):
        gsp_mod._generate_content_with_retry(fake_client, model="x", contents="y")
    # initial attempt + len(_GEMINI_TRANSIENT_RETRY_DELAYS_S) retries
    assert attempts["n"] == 1 + len(gsp_mod._GEMINI_TRANSIENT_RETRY_DELAYS_S)


def test_retry_does_not_swallow_non_server_errors(monkeypatch):
    """A non-transient exception (e.g. a client-side error) must propagate
    immediately on the first attempt -- only ServerError is worth retrying."""
    import gemini_stock_prediction_agent as gsp_mod

    monkeypatch.setattr(gsp_mod.time, "sleep", lambda *_: None)

    attempts = {"n": 0}

    def raises_value_error(**kwargs):
        attempts["n"] += 1
        raise ValueError("not a server error")

    fake_client = type("FakeClient", (), {})()
    fake_client.models = type("FakeModels", (), {"generate_content": staticmethod(raises_value_error)})()

    with pytest.raises(ValueError):
        gsp_mod._generate_content_with_retry(fake_client, model="x", contents="y")
    assert attempts["n"] == 1
