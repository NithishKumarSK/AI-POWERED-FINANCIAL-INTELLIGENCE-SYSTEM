"""
Segment reliability classification — Phase 2 of the accuracy improvement
program (see the plan this session: horizon-scaled thresholds, confidence
calibration, segment labeling, external data, ML signal, backtesting harness).

Classifies a (symbol, horizon_bucket) segment as PROVEN / UNPROVEN /
INSUFFICIENT_DATA from its real historical track record, so the product stops
presenting every segment with equal visual confidence when the data shows
wildly different reality -- e.g. SPY at 0-7d has ~89% direction match while
TSLA at the same horizon bucket is ~33%, and TSLA system-wide is 18% across
17 runs. Averaging these into one blended number hides that some slices
already work passably and others are coin-flip-or-worse.

Reuses batch_validation_runner's horizon bucketing (not duplicated here) so
the live product's segment labels line up with the batch-backtest harness's
own per-segment breakdown.
"""
from __future__ import annotations

from typing import Optional

from batch_validation_runner import horizon_bucket, HORIZON_BUCKETS  # noqa: F401 (re-exported for callers)

# A segment needs at least this many resolved predictions before its
# direction-match rate is trusted either way -- below this, the honest answer
# is "we don't know yet," not "good" or "bad."
MIN_SAMPLE_SIZE = 10

# At or above this direction-match rate (with enough samples), a segment is
# labeled PROVEN. Deliberately modest (not 85%+) -- grounded in the academic
# literature, not just this project's own finding: multiple independent
# sources checked during the Research Expansion Program confirm 50-60%
# directional accuracy is the legitimate range for short-horizon stock
# prediction, and anything a paper reports above ~70-80% is a leakage red
# flag (one paper claiming 87-92% accuracy also showed ~99.9% metrics
# elsewhere -- a textbook overfitting signature, not a real edge). 55% is a
# real, externally-defensible edge over a coin flip, not a token threshold.
PROVEN_THRESHOLD_PCT = 55.0

# These numbers are not inflated by LLM memorization of this project's own
# past outcomes. Checked directly: Google DeepMind's own Gemini 3.7 Flash
# model card (fetched and read as a PDF, not a secondary summary --
# https://storage.googleapis.com/deepmind-media/Model-Cards/Gemini-3-7-Flash-Model-Card.pdf)
# states a knowledge cutoff of January 2025 (conservative, every domain) to
# March 2026 (generous, domain-dependent). Bucketing this project's own 572
# real DB predictions by target_date against those bounds and running a
# two-proportion z-test (scripts/adhoc/llm_memorization_risk_check.py) found
# NO statistically significant gap between the small plausibly-memorized
# bucket (target_date before 2025-01-01, n=23) and the large genuinely-
# unseen bucket (target_date on/after 2026-03-01, n=389): decision_match
# z=0.88 p=0.38, direction_match z=0.81 p=0.42 -- both far short of the
# |z|>=1.96 significance bar. See data/llm_memorization_risk_report.json
# for the full, re-runnable breakdown.



def classify_segment(n: int, direction_match_pct: Optional[float]) -> str:
    """
    Classify a (symbol, horizon_bucket) segment from its historical track record.

    Returns one of:
      "INSUFFICIENT_DATA" -- n < MIN_SAMPLE_SIZE (too few runs to trust either way)
      "UNPROVEN"           -- n >= MIN_SAMPLE_SIZE but direction_match_pct < PROVEN_THRESHOLD_PCT
      "PROVEN"              -- n >= MIN_SAMPLE_SIZE and direction_match_pct >= PROVEN_THRESHOLD_PCT
    """
    if n is None or n < MIN_SAMPLE_SIZE:
        return "INSUFFICIENT_DATA"
    if direction_match_pct is None:
        return "INSUFFICIENT_DATA"
    if direction_match_pct >= PROVEN_THRESHOLD_PCT:
        return "PROVEN"
    return "UNPROVEN"


def segment_label(symbol: str, horizon_days: Optional[int]) -> str:
    """Canonical `(symbol, horizon_bucket)` key, e.g. "TSLA|0-7d"."""
    return f"{(symbol or '').upper()}|{horizon_bucket(horizon_days)}"


# Real, measured regime-conditional direction-match rate -- from 436 DB
# predictions with a known trend_regime (same source position_sizing.py's
# REGIME_FACTOR is normalized from). A genuine ~25pp spread, not noise: this
# project is measurably more reliable in sideways markets than bearish ones.
# Used to adapt methodology per regime (to-do item #6) -- not by changing the
# core decision-threshold guardrail (that stays a single source of truth,
# per the horizon-threshold bug already found and fixed this session), but by
# telling Gemini the real, current-regime-conditional track record directly
# in the prompt, the same evidence-grounded pattern already used for
# per-(symbol,horizon) SEGMENT RELIABILITY above.
REGIME_DIRECTION_MATCH_PCT = {
    "sideways": {"pct": 63.8, "n": 199},
    "bullish":  {"pct": 49.0, "n": 147},
    "bearish":  {"pct": 38.9, "n": 90},
}

# Same finding, independent axis (ADX trend-strength regime rather than
# directional trend regime) -- from the same 436-prediction pool.
ADX_REGIME_DIRECTION_MATCH_PCT = {
    "choppy_market": {"pct": 57.3, "n": 227},
    "weak_trend":    {"pct": 50.9, "n": 55},
    "strong_trend":  {"pct": 49.4, "n": 154},
}


def regime_reliability_note(trend_regime: Optional[str], adx_regime: Optional[str]) -> str:
    """Prompt text grounding the CURRENT regime in this project's own real,
    measured direction-match track record for that regime -- not a generic
    "be careful in volatile markets" platitude. Returns "" if the regime
    isn't one of the known keys (never raises, same degrade-gracefully
    discipline as every other optional signal here)."""
    lines = []
    trend_stat = REGIME_DIRECTION_MATCH_PCT.get(trend_regime)
    if trend_stat:
        lines.append(
            f"  Regime Track Record (trend={trend_regime}): {trend_stat['pct']}% direction "
            f"match over {trend_stat['n']} real past predictions in this exact regime "
            f"(vs {REGIME_DIRECTION_MATCH_PCT['sideways']['pct']}% in sideways regimes -- "
            "the best-performing one measured). Calibrate confidence to this, not just the general case."
        )
    adx_stat = ADX_REGIME_DIRECTION_MATCH_PCT.get(adx_regime)
    if adx_stat:
        lines.append(
            f"  Regime Track Record (adx={adx_regime}): {adx_stat['pct']}% direction match "
            f"over {adx_stat['n']} real past predictions in this exact regime."
        )
    return "\n".join(lines) + ("\n" if lines else "")


def classify_records(records: list, symbol: str, horizon_days: Optional[int]) -> dict:
    """
    Classify a symbol's reliability at a specific horizon from a list of
    validated DB records (the same shape build_calibration_summary() already
    loads: each record has stock_prediction_input/ai_prediction/actual_validation/
    comparison sub-dicts).

    Returns {"n": int, "direction_match_pct": float|None, "classification": str}.
    """
    bucket = horizon_bucket(horizon_days)
    seg_records = [
        r for r in records
        if (r.get("stock_prediction_input", {}).get("symbol") or "").upper() == (symbol or "").upper()
        and horizon_bucket(r.get("stock_prediction_input", {}).get("decision_horizon_days")) == bucket
    ]
    n = len(seg_records)
    if n == 0:
        return {"n": 0, "direction_match_pct": None, "classification": "INSUFFICIENT_DATA"}

    dir_ok = sum(1 for r in seg_records if r.get("comparison", {}).get("directional_match") is True)
    direction_match_pct = round(dir_ok / n * 100, 1)
    return {
        "n": n,
        "direction_match_pct": direction_match_pct,
        "classification": classify_segment(n, direction_match_pct),
    }
