"""
Gemini Stock Prediction Agent — Walk-Forward (No Leakage)

Uses Google Gemini as the AI reasoning engine.
- Builds rich feature packet: RSI, MACD, Bollinger Bands, ATR, SMA, volume
- Enforces strict leakage prevention (no target price in Gemini context)
- Applies calibration from past validated records
- Validates and recalculates Gemini numeric output
- Applies deterministic decision guardrails

Environment variables:
    GEMINI_API_KEY or GOOGLE_API_KEY  — required for Gemini
    GEMINI_MODEL                      — default: gemini-3.7-flash
    AI_PROVIDER                       — "gemini" or "baseline" (default: gemini)
    ALLOW_BASELINE_FALLBACK           — "true" / "false" (default: false)
    ENABLE_CHART_VISION               — "true" / "false" (default: false) — attach
                                         chart images (wide + detail) to every
                                         consensus call; see chart_rendering.py
    CHART_VISION_WIDE_LOOKBACK_DAYS   — default: 240
    CHART_VISION_DETAIL_LOOKBACK_DAYS — default: 90
    CHART_VISION_REQUEST_TIMEOUT_MS   — default: 150000 (chart-vision calls need
                                         more headroom than text-only; see 503/504
                                         failures observed in the initial pilot)
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import math
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

from record_dedup import dedup_records, sort_by_target_date

# ─── Config ───────────────────────────────────────────────────────────────────
AI_PROVIDER             = os.getenv("AI_PROVIDER", "gemini").lower()
ALLOW_BASELINE_FALLBACK = os.getenv("ALLOW_BASELINE_FALLBACK", "false").lower() == "true"
GEMINI_MODEL            = os.getenv("GEMINI_MODEL", os.getenv("AGENT_MODEL", "gemini-3.7-flash"))
_GEMINI_KEY             = os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")

# Chart-vision input (default OFF): attaches two chart images (wide structural +
# short detail -- a single timeframe was validated to underperform sending both,
# see chart_rendering.py) to every consensus call. Off by default until an A/B
# validation run (batch_validation_runner.py, matching symbols/horizons/months-back
# with only this flag differing) justifies enabling it broadly.
ENABLE_CHART_VISION               = os.getenv("ENABLE_CHART_VISION", "false").lower() == "true"
CHART_VISION_WIDE_LOOKBACK_DAYS   = int(os.getenv("CHART_VISION_WIDE_LOOKBACK_DAYS", "240"))
CHART_VISION_DETAIL_LOOKBACK_DAYS = int(os.getenv("CHART_VISION_DETAIL_LOOKBACK_DAYS", "90"))
# Research Expansion Program, Component 5 -- bull/bear debate consensus
# (_call_gemini_debate_consensus). OPT-IN, default off: this session already
# found more LLM sophistication (the existing triple-consensus) scored WORSE
# than an older, simpler baseline; this must prove itself via the Phase 5
# batch harness before ever being made the default. 5 Gemini calls instead
# of 3 -- real latency cost (~2.5-4 min/prediction at this model's speed).
ENABLE_DEBATE_CONSENSUS = os.getenv("ENABLE_DEBATE_CONSENSUS", "false").lower() == "true"
# Research Expansion Program -- judge-based aggregation, replacing majority
# vote (_call_gemini_judge_consensus). Evidence: "When Agents Disagree: The
# Selection Bottleneck" (arXiv 2603.20324) found judge-based selection beats
# majority voting by a huge margin (Bradley-Terry 0.810 vs 0.496), while
# majority voting itself is statistically indistinguishable from a single
# model (p=0.669) -- and this project's OWN data shows the same pattern: the
# 3 consensus calls agree 72% of the time, but agreement doesn't predict
# accuracy (52.5% vs 53.3%). OPT-IN, default off: the study's own disclosed
# caveat is same-family judge/generator self-evaluation bias, so JUDGE_MODEL
# below defaults to a DIFFERENT model than GEMINI_MODEL, and this must clear
# the same Phase 5 batch-harness bar as Component 5 before ever defaulting on.
ENABLE_JUDGE_AGGREGATION = os.getenv("ENABLE_JUDGE_AGGREGATION", "false").lower() == "true"
# Named GEMINI_JUDGE_MODEL (not the generic "JUDGE_MODEL") -- confirmed live
# this session that a bare "JUDGE_MODEL" name collides with an unrelated
# pre-existing environment variable already set on this machine (pointing
# at a non-Gemini model id), which would have silently broken every judge
# call. This project-specific name avoids that collision.
JUDGE_MODEL = os.getenv("GEMINI_JUDGE_MODEL", "gemini-3.1-pro-preview")
# Research Expansion Program -- per-prediction LAP-style leakage probe
# (core/lap_leakage_probe.py). OPT-IN, default off: costs one extra Gemini
# call per prediction. Confirmed live this session: a stripped ticker+date
# probe shows 92.5% avg confidence on well-known historical dates vs 0% on
# genuinely future dates -- this flag runs that same check against THIS
# prediction's own target_date, surfacing a `leakage_probe` field in the
# result (never blocks or alters the prediction itself on failure).
ENABLE_LAP_PROBE_PER_PREDICTION = os.getenv("ENABLE_LAP_PROBE_PER_PREDICTION", "false").lower() == "true"
# Research Expansion Program -- genuinely diverse 3-call consensus (masked
# feature packets: technicals-only / news-only / regime-only), replacing
# the existing 3 calls' identical-evidence-different-framing design. See
# _call_gemini_diverse_consensus docstring. OPT-IN, default off -- needs the
# same Phase 5 batch-harness validation as every other opt-in consensus mode
# before ever becoming default. Composes with ENABLE_JUDGE_AGGREGATION.
ENABLE_DIVERSE_CONSENSUS = os.getenv("ENABLE_DIVERSE_CONSENSUS", "false").lower() == "true"
# Research Expansion Program -- conformal-prediction-style range widening
# (core/conformal_range_calibrator.py). Real, live-measured baseline: the
# deterministic range predictor's raw band contained the actual price swing
# 79.9% of the time (n=304); this applies a calibrated widening multiplier,
# fit from that same real data, to target a chosen coverage level instead of
# whatever the raw band happens to achieve. OPT-IN, default off -- changes
# the reported low/high band width, a real behavior change that needs
# explicit opt-in like every other experimental component here.
ENABLE_CONFORMAL_RANGE = os.getenv("ENABLE_CONFORMAL_RANGE", "false").lower() == "true"
# Must match a key in data/conformal_range_calibration.json's
# "by_target_coverage" dict -- Python's str(0.90) == "0.9", not "0.90", so
# this default is "0.9", not "0.90" (confirmed live against the real file).
CONFORMAL_TARGET_COVERAGE = os.getenv("CONFORMAL_TARGET_COVERAGE", "0.9")
# Research Expansion Program -- per-headline news scoring
# (core/per_headline_news_scorer.py), the actual mechanism behind
# Lopez-Lira & Tang's real edge (per-headline YES/NO, not one aggregate
# sentiment score). OPT-IN, default off -- one extra Gemini call per
# prediction, live-only (same gate as the Yahoo headlines it reuses).
ENABLE_PER_HEADLINE_NEWS_SCORING = os.getenv("ENABLE_PER_HEADLINE_NEWS_SCORING", "false").lower() == "true"
# Research Expansion Program, Component 6 follow-up -- promotes the shadow ML
# model (see "ML signal cross-check, SHADOW MODE ONLY" below) from logged-only
# to an active decision override, but ONLY on segments with their own
# dedicated trained model (never the generic default_model, which was never
# shown to help -- see SegmentedModel). OPT-IN, default off: real head-to-head
# evidence exists for exactly 5 segments (a 20-case probe found the shadow
# model correct 64.3% of the time vs Gemini's 35.7%, n=14 -- see
# scratchpad/ml_shadow_ev_probe_results.json), but that's still a small
# sample: this must be validated at larger scale before ever defaulting on.
ENABLE_ML_SEGMENT_OVERRIDE = os.getenv("ENABLE_ML_SEGMENT_OVERRIDE", "false").lower() == "true"
# Self-learning case retrieval (core/case_retrieval.py). Default ON -- unlike
# debate consensus this adds zero extra Gemini calls (one DB query + a prompt
# section using data already fetched), so it carries none of the latency/cost
# risk that justified defaulting debate consensus off. Still flagged so a
# controlled A/B (same symbols/horizons/origin-dates, only this toggled) can
# cleanly isolate its real effect instead of being confounded with whatever
# else changed between two runs -- exactly the mistake the first same-day
# attempt at this comparison made (different date ranges between arms).
ENABLE_CASE_RETRIEVAL = os.getenv("ENABLE_CASE_RETRIEVAL", "true").lower() == "true"
# Every other network call in this project (Alpaca, historical price fetch) has an
# explicit timeout; this one didn't. A hung connection under real-world network
# flakiness (observed directly: DNS reconnect blips, failed sends) would then block
# its asyncio.to_thread worker forever -- the caller's own outer scan timeout only
# stops *waiting* on stragglers, it doesn't cancel them, so stuck Gemini calls could
# accumulate across cycles and eventually starve the whole thread pool that every
# other network call (including unrelated Alpaca calls) also depends on. 60s is
# generous enough for a real deep-thinking response, bounded enough to guarantee the
# call eventually fails cleanly instead of hanging indefinitely.
GEMINI_REQUEST_TIMEOUT_MS = int(os.getenv("GEMINI_REQUEST_TIMEOUT_MS", "60000"))
# Hard, ACTUALLY-enforced wall-clock cap per consensus call, applied with
# concurrent.futures' own .result(timeout=...) in _call_gemini_consensus --
# unlike GEMINI_REQUEST_TIMEOUT_MS above (an httpx per-read-chunk timeout
# that does NOT bound a streaming "thinking" response's total duration,
# confirmed live this session: genuine successful calls took 92-191s past
# that 60s setting, and some calls hung 45+ minutes with no response at
# all). Set well above the real observed 92-191s range for a genuinely
# successful deep-thinking call on this project's configured GEMINI_MODEL,
# so this only ever discards a true runaway hang, never a good, just-slow
# answer.
_CONSENSUS_CALL_HARD_TIMEOUT_S = float(os.getenv("GEMINI_CONSENSUS_CALL_HARD_TIMEOUT_S", "240"))
# Chart-vision pilot run (20 predictions, ENABLE_CHART_VISION=true) hit an 8/20
# outright-failure rate on 503 UNAVAILABLE / 504 DEADLINE_EXCEEDED / ReadTimeout
# -- zero such failures occurred on the identical symbol/horizon/origin set with
# vision off. Two images per call (6 per prediction across the 3 consensus
# calls) evidently pushes some requests past the 60s budget. Use a longer
# timeout specifically when images are attached rather than raising it globally,
# since the text-only path has never shown this failure mode.
CHART_VISION_REQUEST_TIMEOUT_MS = int(os.getenv("CHART_VISION_REQUEST_TIMEOUT_MS", "150000"))
# A follow-up pilot after the timeout bump above and the chart-image size cut
# (see chart_rendering.py) still saw 503/504s concentrated on vision-on calls
# -- the longer per-call time with images attached raises exposure to Gemini's
# transient overload, it doesn't just risk a hard timeout. _generate_content_with_retry
# (below) retries those specific transient errors with backoff instead of failing
# the call outright on the first one.

STOCK_EVAL_FILE = ROOT / "stock_prediction_evaluation_runs.jsonl"

_HIGH_RISK_CUTOFF  = 80
_RETURN_CLAMP_MAX  = 20.0
_RETURN_CLAMP_MIN  = -20.0


def _get_horizon_thresholds(horizon_days: int, symbol: str = "", expected_range_pct: Optional[float] = None) -> Tuple[float, float]:
    """Return (buy_threshold, sell_threshold) -- shown to Gemini in the prompt as the
    bar for a decisive BUY/SELL call.

    MUST match stock_comparison_engine.decision_thresholds_for_horizon exactly: that
    function is the REAL guardrail _apply_guardrails enforces after Gemini responds,
    and is also what grades the ground-truth actual_decision. Before this fix, this
    function independently returned a flat +/-0.1% ("HOLD-elimination mode") -- so
    Gemini was told "any nonzero return is decisive" while actually being graded
    against a properly horizon-scaled +/-2% (at 7d) band. That mismatch (not a lack of
    skill) is the direct, confirmed cause of exact decision-match (34.4%) sitting far
    below directional match (54.0%) across this project's own 475-prediction dataset:
    Gemini had no way to know what threshold it was actually being held to.

    expected_range_pct is accepted for backward compatibility with existing call
    sites but intentionally unused -- the single source of truth for this threshold
    is decision_thresholds_for_horizon, not a second, independently-tuned formula.
    """
    from stock_comparison_engine import decision_thresholds_for_horizon
    return decision_thresholds_for_horizon(horizon_days)


# ═══════════════════════════════════════════════════════════════════════════════
# TECHNICAL INDICATORS
# ═══════════════════════════════════════════════════════════════════════════════

def _calc_sma(closes: List[float], period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 4)


def _calc_ema(closes: List[float], period: int) -> List[float]:
    if not closes:
        return []
    k = 2.0 / (period + 1)
    emas = [closes[0]]
    for p in closes[1:]:
        emas.append(p * k + emas[-1] * (1 - k))
    return emas


def _calc_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        if delta > 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(delta))
    if len(gains) < period:
        return None
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def _calc_macd(
    closes: List[float], fast: int = 12, slow: int = 26, signal_period: int = 9
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if len(closes) < slow + signal_period:
        return None, None, None
    fast_ema  = _calc_ema(closes, fast)
    slow_ema  = _calc_ema(closes, slow)
    macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
    if len(macd_line) < signal_period:
        return None, None, None
    sig_ema  = _calc_ema(macd_line, signal_period)
    macd_v   = round(macd_line[-1], 4)
    signal_v = round(sig_ema[-1], 4)
    hist_v   = round(macd_v - signal_v, 4)
    return macd_v, signal_v, hist_v


def _calc_bollinger_bands(
    closes: List[float], period: int = 20
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if len(closes) < period:
        return None, None, None
    window = closes[-period:]
    sma = sum(window) / period
    std = math.sqrt(sum((c - sma) ** 2 for c in window) / period)
    return round(sma + 2 * std, 4), round(sma, 4), round(sma - 2 * std, 4)


def _calc_atr(bars: List[dict], period: int = 14) -> Optional[float]:
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        high = float(bars[i].get("high") or bars[i].get("close") or 0)
        low  = float(bars[i].get("low")  or bars[i].get("close") or 0)
        prev = float(bars[i - 1].get("close") or 0)
        if prev <= 0:
            continue
        trs.append(max(high - low, abs(high - prev), abs(low - prev)))
    if len(trs) < period:
        return None
    return round(sum(trs[-period:]) / period, 4)


# ── PHASE 8: ADX (Average Directional Index) ──────────────────────────────────
def _calc_adx(bars: List[dict], period: int = 14) -> Optional[float]:
    """Compute ADX to measure trend strength. >25 = strong trend, <20 = choppy."""
    if len(bars) < period * 2 + 1:
        return None
    try:
        plus_dm, minus_dm, trs = [], [], []
        for i in range(1, len(bars)):
            h  = float(bars[i].get("high")  or bars[i].get("close") or 0)
            l  = float(bars[i].get("low")   or bars[i].get("close") or 0)
            ph = float(bars[i-1].get("high") or bars[i-1].get("close") or 0)
            pl = float(bars[i-1].get("low")  or bars[i-1].get("close") or 0)
            pc = float(bars[i-1].get("close") or 0)
            if pc <= 0:
                continue
            up   = h - ph
            down = pl - l
            plus_dm.append(up   if up > down and up > 0   else 0.0)
            minus_dm.append(down if down > up and down > 0 else 0.0)
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        if len(trs) < period:
            return None
        def _smooth(vals, p):
            s = sum(vals[:p])
            result = [s]
            for v in vals[p:]:
                s = s - s / p + v
                result.append(s)
            return result
        str_ = _smooth(trs, period)
        spdm = _smooth(plus_dm, period)
        smdm = _smooth(minus_dm, period)
        dx_vals = []
        for i in range(len(str_)):
            if str_[i] == 0:
                continue
            pdi = 100 * spdm[i] / str_[i]
            mdi = 100 * smdm[i] / str_[i]
            denom = pdi + mdi
            if denom == 0:
                continue
            dx_vals.append(100 * abs(pdi - mdi) / denom)
        if len(dx_vals) < period:
            return None
        return round(sum(dx_vals[-period:]) / period, 2)
    except Exception:
        return None


# ── Research Expansion Program Component -- indicator completeness pass:
# CCI, Williams %R, CMF, Stochastic. Zhong & Hitchcock (arXiv 2108.10826) used
# all four alongside RSI/MACD; we had RSI/MACD/ADX/ATR/Bollinger but not
# these. Same free OHLCV bars already fetched for everything else -- no new
# data source, no new API key, pure arithmetic.
def _calc_cci(bars: List[dict], period: int = 20) -> Optional[float]:
    """Commodity Channel Index. >100 = strong uptrend/overbought,
    <-100 = strong downtrend/oversold."""
    if len(bars) < period:
        return None
    try:
        tps = []
        for b in bars[-period:]:
            h = float(b.get("high") or b.get("close") or 0)
            l = float(b.get("low") or b.get("close") or 0)
            c = float(b.get("close") or 0)
            tps.append((h + l + c) / 3.0)
        sma_tp = sum(tps) / period
        mean_dev = sum(abs(tp - sma_tp) for tp in tps) / period
        if mean_dev == 0:
            return 0.0
        return round((tps[-1] - sma_tp) / (0.015 * mean_dev), 2)
    except Exception:
        return None


def _calc_williams_r(bars: List[dict], period: int = 14) -> Optional[float]:
    """Williams %R. Ranges -100..0; below -80 = oversold, above -20 = overbought."""
    if len(bars) < period:
        return None
    try:
        window = bars[-period:]
        highs = [float(b.get("high") or b.get("close") or 0) for b in window]
        lows  = [float(b.get("low")  or b.get("close") or 0) for b in window]
        close = float(window[-1].get("close") or 0)
        hh, ll = max(highs), min(lows)
        if hh == ll:
            return -50.0
        return round((hh - close) / (hh - ll) * -100.0, 2)
    except Exception:
        return None


def _calc_cmf(bars: List[dict], period: int = 20) -> Optional[float]:
    """Chaikin Money Flow. Ranges roughly -1..1; positive = buying pressure."""
    if len(bars) < period:
        return None
    try:
        window = bars[-period:]
        mfv_sum, vol_sum = 0.0, 0.0
        for b in window:
            h = float(b.get("high") or b.get("close") or 0)
            l = float(b.get("low") or b.get("close") or 0)
            c = float(b.get("close") or 0)
            v = float(b.get("volume") or 0)
            mfm = ((c - l) - (h - c)) / (h - l) if (h - l) != 0 else 0.0
            mfv_sum += mfm * v
            vol_sum += v
        if vol_sum == 0:
            return None
        return round(mfv_sum / vol_sum, 4)
    except Exception:
        return None


def _calc_stochastic(bars: List[dict], period: int = 14, d_period: int = 3) -> Tuple[Optional[float], Optional[float]]:
    """Stochastic %K / %D. Above 80 = overbought, below 20 = oversold."""
    if len(bars) < period + d_period - 1:
        return None, None
    try:
        k_vals = []
        for i in range(period - 1, len(bars)):
            window = bars[i - period + 1:i + 1]
            highs = [float(b.get("high") or b.get("close") or 0) for b in window]
            lows  = [float(b.get("low")  or b.get("close") or 0) for b in window]
            close = float(window[-1].get("close") or 0)
            hh, ll = max(highs), min(lows)
            k_vals.append(50.0 if hh == ll else (close - ll) / (hh - ll) * 100.0)
        if len(k_vals) < d_period:
            return round(k_vals[-1], 2) if k_vals else None, None
        k = round(k_vals[-1], 2)
        d = round(sum(k_vals[-d_period:]) / d_period, 2)
        return k, d
    except Exception:
        return None, None


# ── PHASE 10: RSI Divergence Detector ─────────────────────────────────────────
def _detect_rsi_divergence(bars: List[dict], lookback: int = 20) -> str:
    """
    Detect bullish or bearish RSI-price divergence over the last `lookback` bars.
    Bullish divergence: price lower low + RSI higher low = BULLISH_DIVERGENCE
    Bearish divergence: price higher high + RSI lower high = BEARISH_DIVERGENCE
    Returns: 'BULLISH_DIVERGENCE' | 'BEARISH_DIVERGENCE' | 'NONE'
    """
    if len(bars) < lookback + 15:
        return "NONE"
    try:
        window = bars[-(lookback + 14):]
        closes = [float(b.get("close") or 0) for b in window if float(b.get("close") or 0) > 0]
        if len(closes) < lookback:
            return "NONE"
        rsi_series = []
        for i in range(14, len(closes)):
            rsi_series.append(_calc_rsi(closes[:i+1], 14))
        if len(rsi_series) < 4 or any(r is None for r in rsi_series):
            return "NONE"
        price_recent  = closes[-1]
        price_mid     = closes[len(closes) // 2]
        rsi_recent    = rsi_series[-1]
        rsi_mid       = rsi_series[len(rsi_series) // 2]
        # Bullish divergence: price fell but RSI rose
        if price_recent < price_mid * 0.98 and rsi_recent > rsi_mid + 3:
            return "BULLISH_DIVERGENCE"
        # Bearish divergence: price rose but RSI fell
        if price_recent > price_mid * 1.02 and rsi_recent < rsi_mid - 3:
            return "BEARISH_DIVERGENCE"
        return "NONE"
    except Exception:
        return "NONE"


def _period_return(closes: List[float], lookback: int) -> Optional[float]:
    if len(closes) < lookback + 1:
        return None
    p_now, p_then = closes[-1], closes[-lookback]
    if p_then <= 0:
        return None
    return round((p_now - p_then) / p_then * 100.0, 4)


def _annualized_volatility(closes: List[float], window: int = 60) -> Optional[float]:
    if len(closes) < window + 1:
        return None
    rets = []
    for i in range(max(1, len(closes) - window), len(closes)):
        prev, curr = closes[i - 1], closes[i]
        if prev > 0:
            rets.append(math.log(curr / prev))
    if len(rets) < 10:
        return None
    mean = sum(rets) / len(rets)
    var  = sum((r - mean) ** 2 for r in rets) / len(rets)
    return round(math.sqrt(var) * math.sqrt(252) * 100.0, 2)


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE PACKET
# ═══════════════════════════════════════════════════════════════════════════════

def build_stock_feature_packet(
    normalized_input: dict,
    ai_visible_bars: List[dict],
    benchmark_bars: Optional[List[dict]] = None,
) -> dict:
    """
    Build deterministic feature packet from real bars only.
    Leakage prevention: caller must pass only bars up to effective_origin_date.
    """
    if not ai_visible_bars:
        return {"status": "INSUFFICIENT", "n_bars": 0, "error": "No bars provided"}

    price_basis = str(normalized_input.get("price_basis", "close") or "close")

    def _price(bar: dict) -> float:
        return float(bar.get(price_basis) or bar.get("close") or 0)

    closes = [_price(b) for b in ai_visible_bars if _price(b) > 0]
    n = len(closes)
    if n < 5:
        return {"status": "INSUFFICIENT", "n_bars": n, "error": "Too few valid price bars"}

    origin_price = closes[-1]
    ctx_start    = str(normalized_input.get("historical_context_start_date", "") or "")
    origin_str   = str(normalized_input.get("prediction_origin_date", "") or "")

    # Effective context start = first bar actually present (may be later than requested)
    _first_bar_date = ""
    for _b in ai_visible_bars:
        _bd = str(_b.get("date") or _b.get("datetime") or "")
        if _bd:
            _first_bar_date = _bd[:10]
            break

    # Returns
    r1d   = _period_return(closes, 1)
    r5d   = _period_return(closes, 5)
    r10d  = _period_return(closes, 10)
    r20d  = _period_return(closes, 20)
    r60d  = _period_return(closes, 60)
    r120d = _period_return(closes, 120)
    r_full = round((closes[-1] - closes[0]) / closes[0] * 100.0, 4) if closes[0] > 0 else None

    # Trend / SMA
    sma10  = _calc_sma(closes, 10)
    sma20  = _calc_sma(closes, 20)
    sma50  = _calc_sma(closes, 50)
    sma100 = _calc_sma(closes, 100)

    def _pct_diff(price, ref):
        if price and ref and ref > 0:
            return round((price - ref) / ref * 100.0, 4)
        return None

    pvs20 = _pct_diff(origin_price, sma20)
    pvs50 = _pct_diff(origin_price, sma50)
    trend_regime = (
        "bullish" if pvs20 and pvs50 and pvs20 > 2 and pvs50 > 2
        else "bearish" if pvs20 and pvs50 and pvs20 < -2 and pvs50 < -2
        else "sideways"
    )

    # Momentum
    rsi14 = _calc_rsi(closes, 14)
    macd, macd_signal, macd_hist = _calc_macd(closes)

    # Volatility
    ann_vol = _annualized_volatility(closes)
    atr14   = _calc_atr(ai_visible_bars, 14)
    bb_upper, bb_mid, bb_lower = _calc_bollinger_bands(closes, 20)
    vol_regime = (
        "low" if ann_vol and ann_vol < 20
        else "high" if ann_vol and ann_vol > 50
        else "medium"
    )
    bb_position = None
    if bb_upper and bb_lower and (bb_upper - bb_lower) > 0:
        bb_position = round((origin_price - bb_lower) / (bb_upper - bb_lower), 4)

    peak = max(closes)
    max_dd = round((origin_price - peak) / peak * 100.0, 4) if peak > 0 else None
    low_   = min(closes)
    dist_from_low = round((origin_price - low_) / low_ * 100.0, 4) if low_ > 0 else None

    # Volume
    vols = [float(b.get("volume") or 0) for b in ai_visible_bars]
    avg_vol20 = round(sum(vols[-20:]) / 20, 0) if len(vols) >= 20 else None
    avg_vol60 = round(sum(vols[-60:]) / 60, 0) if len(vols) >= 60 else None
    latest_vol = vols[-1] if vols else None
    vol_ratio20 = round(latest_vol / avg_vol20, 4) if avg_vol20 and avg_vol20 > 0 and latest_vol else None

    # Indicator-completeness pass -- CCI, Williams %R, CMF, Stochastic
    cci20       = _calc_cci(ai_visible_bars, 20)
    williams_r14 = _calc_williams_r(ai_visible_bars, 14)
    cmf20       = _calc_cmf(ai_visible_bars, 20)
    stoch_k14, stoch_d3 = _calc_stochastic(ai_visible_bars, 14, 3)

    # Phase 8 — ADX trend strength
    adx14 = _calc_adx(ai_visible_bars, 14)
    adx_regime = (
        "strong_trend"  if adx14 and adx14 > 25
        else "weak_trend"    if adx14 and adx14 > 20
        else "choppy_market" if adx14 is not None
        else "unknown"
    )

    # Phase 10 — RSI divergence
    rsi_divergence = _detect_rsi_divergence(ai_visible_bars, lookback=20)

    # Support / Resistance
    window20         = closes[-20:] if n >= 20 else closes
    recent_support   = round(min(window20), 4)
    recent_resistance = round(max(window20), 4)
    dist_to_sup  = round((origin_price - recent_support) / origin_price * 100.0, 4) if origin_price > 0 else None
    dist_to_res  = round((recent_resistance - origin_price) / origin_price * 100.0, 4) if origin_price > 0 else None

    # Benchmark relative strength
    bm_r20 = bm_r60 = rel20 = rel60 = None
    if benchmark_bars:
        bm_closes = [float(b.get("close") or 0) for b in benchmark_bars if b.get("close")]
        if bm_closes:
            bm_r20 = _period_return(bm_closes, 20)
            bm_r60 = _period_return(bm_closes, 60)
            if bm_r20 is not None and r20d is not None:
                rel20 = round(r20d - bm_r20, 4)
            if bm_r60 is not None and r60d is not None:
                rel60 = round(r60d - bm_r60, 4)

    # Reversal detection
    oversold_signal   = rsi14 is not None and rsi14 < 30
    overbought_signal = rsi14 is not None and rsi14 > 70
    near_support      = dist_to_sup is not None and dist_to_sup < 3.0
    near_resistance   = dist_to_res is not None and dist_to_res < 3.0
    momentum_divergence = (
        r5d is not None and r20d is not None and r60d is not None
        and r5d > 0 and r20d < 0 and r60d < 0
    )
    reversal_risk = "low"
    if oversold_signal and near_support and r60d is not None and r60d < -20:
        reversal_risk = "high"
    elif overbought_signal and near_resistance and r20d is not None and r20d > 10:
        reversal_risk = "high"   # extreme overbought surge near resistance → high reversal risk
    elif oversold_signal or (near_support and r20d is not None and r20d < -10):
        reversal_risk = "medium"
    elif overbought_signal and near_resistance:
        reversal_risk = "medium"  # overbought + at resistance → medium reversal risk

    dq = 100
    if n < 20:   dq -= 40
    elif n < 60: dq -= 20
    elif n < 120: dq -= 10

    return {
        "status":              "OK",
        "n_bars":              n,
        "data_quality_score":  max(0, min(100, dq)),
        "symbol":              normalized_input.get("symbol", ""),
        "benchmark":           normalized_input.get("benchmark", ""),
        "price_basis":         price_basis,
        "origin_price":        round(origin_price, 4),
        "requested_ctx_start": ctx_start,
        "effective_ctx_start": _first_bar_date or ctx_start,
        "ctx_start":           _first_bar_date or ctx_start,
        "origin_date":         origin_str,
        "horizon_days":        normalized_input.get("decision_horizon_days", 30),
        "returns": {
            "return_1d":            r1d,
            "return_5d":            r5d,
            "return_10d":           r10d,
            "return_20d":           r20d,
            "return_60d":           r60d,
            "return_120d":          r120d,
            "full_context_return":  r_full,
        },
        "trend": {
            "sma_10":               sma10,
            "sma_20":               sma20,
            "sma_50":               sma50,
            "sma_100":              sma100,
            "price_vs_sma_20_pct":  pvs20,
            "price_vs_sma_50_pct":  pvs50,
            "trend_regime":         trend_regime,
            "ADX_14":               adx14,
            "adx_regime":           adx_regime,
            "rsi_divergence":       rsi_divergence,
        },
        "momentum": {
            "RSI_14":               rsi14,
            "MACD":                 macd,
            "MACD_signal":          macd_signal,
            "MACD_histogram":       macd_hist,
            "rate_of_change_20":    r20d,
            "CCI_20":               cci20,
            "Williams_R_14":        williams_r14,
            "STOCH_K_14":           stoch_k14,
            "STOCH_D_3":            stoch_d3,
        },
        "volatility": {
            "annualized_volatility": ann_vol,
            "ATR_14":               atr14,
            "ATR_daily_pct":        round(atr14 / origin_price * 100.0, 4) if atr14 and origin_price > 0 else None,
            "BB_upper":             bb_upper,
            "BB_mid":               bb_mid,
            "BB_lower":             bb_lower,
            "BB_position":          bb_position,
            "max_drawdown_context": max_dd,
            "dist_from_low_pct":    dist_from_low,
            "volatility_regime":    vol_regime,
        },
        "return_magnitude_formula": {
            "ATR_daily_pct":        round(atr14 / origin_price * 100.0, 4) if atr14 and origin_price > 0 else None,
            "horizon_days":         normalized_input.get("decision_horizon_days", 30),
            "sqrt_horizon":         round(math.sqrt(int(normalized_input.get("decision_horizon_days") or 30)), 4),
            "expected_range_pct":   round((atr14 / origin_price * 100.0) * math.sqrt(int(normalized_input.get("decision_horizon_days") or 30)), 4) if atr14 and origin_price > 0 else None,
            "note": "Use expected_range_pct × direction_factor (0.10-0.75) to get |predicted_return|. Add sign from direction.",
        },
        "volume": {
            "avg_volume_20":  avg_vol20,
            "avg_volume_60":  avg_vol60,
            "latest_volume":  latest_vol,
            "volume_ratio_20": vol_ratio20,
            "CMF_20":          cmf20,
        },
        "support_resistance": {
            "recent_support":           recent_support,
            "recent_resistance":        recent_resistance,
            "dist_to_support_pct":      dist_to_sup,
            "dist_to_resistance_pct":   dist_to_res,
        },
        "benchmark_comparison": {
            "benchmark_return_20d":  bm_r20,
            "benchmark_return_60d":  bm_r60,
            "relative_strength_20d": rel20,
            "relative_strength_60d": rel60,
        },
        "reversal_signals": {
            "oversold_signal":      oversold_signal,
            "overbought_signal":    overbought_signal,
            "near_support":         near_support,
            "near_resistance":      near_resistance,
            "momentum_divergence":  momentum_divergence,
            "reversal_risk":        reversal_risk,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CALIBRATION SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

def _load_calibration_source_records() -> List[dict]:
    """Load the records build_calibration_summary() should calibrate from.

    Central database (Supabase) is the source of truth -- see
    db/stock_prediction_repository.py -- falling back to the local JSONL file
    only if the DB is unreachable, so a transient connection hiccup degrades
    calibration quality instead of crashing the whole prediction.

    This is its own function (rather than inlined) so tests can monkeypatch
    it directly instead of pointing STOCK_EVAL_FILE at a fixture file --
    the real source of truth moved to the DB, so that's the correct seam now.
    """
    try:
        from db.stock_prediction_repository import load_stock_prediction_records
        return load_stock_prediction_records(limit=100000)
    except Exception:
        records: List[dict] = []
        if STOCK_EVAL_FILE.exists():
            try:
                with open(STOCK_EVAL_FILE, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            try:
                                records.append(json.loads(line))
                            except Exception:
                                pass
            except Exception:
                pass
        return records


def build_calibration_summary(
    symbol: str = "", horizon_days: int = 0, as_of_date: str = "",
    feature_packet: Optional[dict] = None,
) -> dict:
    """Read past validated records and build a calibration summary for Gemini.

    as_of_date: when set (e.g. to a historical prediction's origin date), records
    whose target_date is not strictly before as_of_date are excluded. This keeps
    a historical replay from seeing outcomes that hadn't resolved yet as of the
    origin being replayed. Empty (the default, used for live predictions where
    the cutoff is effectively "now") preserves prior unfiltered behavior.

    feature_packet: when provided, also retrieves the nearest historical
    precedents (core/case_retrieval.py) from this same leakage-safe record
    set -- concrete past cases, not just aggregate percentages.
    """
    records = _load_calibration_source_records()

    # Retried/re-run predictions share the same (symbol, origin, horizon, target)
    # key — dedup so a single retried period doesn't outweigh normal ones.
    # (load_stock_prediction_records already dedups DB-sourced records; this is
    # a no-op in that case and only matters for the local-file fallback path.)
    records = dedup_records(records)

    if as_of_date:
        records = [
            r for r in records
            if str(r.get("stock_prediction_input", {}).get("target_date") or "") < as_of_date
        ]

    if not records:
        return {
            "total_validated_records": 0,
            "note": "No calibration records yet — this is a fresh model with no history.",
        }

    total  = len(records)
    dec_ok = sum(1 for r in records if r.get("comparison", {}).get("decision_match") is True)
    dir_ok = sum(1 for r in records if r.get("comparison", {}).get("directional_match") is True)

    ret_errors = [
        abs(float(r["comparison"]["abs_return_error_pct"]))
        for r in records
        if r.get("comparison", {}).get("abs_return_error_pct") is not None
    ]
    avg_ret_err = round(sum(ret_errors) / len(ret_errors), 2) if ret_errors else None

    raw_errors = [
        float(r["comparison"]["return_error_pct"])
        for r in records
        if r.get("comparison", {}).get("return_error_pct") is not None
    ]
    overpred  = sum(1 for e in raw_errors if e < 0)   # AI predicted too high
    underpred = sum(1 for e in raw_errors if e > 0)   # AI predicted too low

    sym_records = [
        r for r in records
        if r.get("stock_prediction_input", {}).get("symbol") == symbol
    ] if symbol else []

    recent_conflicts = [
        {
            "symbol":   r.get("stock_prediction_input", {}).get("symbol", ""),
            "ai_dec":   r.get("ai_prediction", {}).get("decision", ""),
            "act_dec":  r.get("actual_validation", {}).get("actual_decision", ""),
            "ret_err":  r.get("comparison", {}).get("return_error_pct"),
        }
        for r in records
        if r.get("comparison", {}).get("decision_match") is False
    ][-5:]

    # Compute decision-level directional bias FIRST (more reliable than return magnitude)
    _pre_false_sell = sum(1 for r in records
                         if (r.get("ai_prediction", {}).get("decision") or "").upper() == "SELL"
                         and (r.get("actual_validation", {}).get("actual_decision") or "").upper() == "BUY")
    _pre_false_buy  = sum(1 for r in records
                         if (r.get("ai_prediction", {}).get("decision") or "").upper() == "BUY"
                         and (r.get("actual_validation", {}).get("actual_decision") or "").upper() == "SELL")
    if _pre_false_sell > _pre_false_buy * 2:
        _dir_bias = (
            f"SELL BIAS DETECTED: {_pre_false_sell} false-SELL errors (predicted SELL but market rose) "
            f"vs only {_pre_false_buy} false-BUY errors. "
            "You are systematically too bearish. When signals are MIXED or NEUTRAL, lean BUY — especially for SPY/SPX/QQQ."
        )
    elif _pre_false_buy > _pre_false_sell * 2:
        _dir_bias = (
            f"BUY BIAS DETECTED: {_pre_false_buy} false-BUY errors vs {_pre_false_sell} false-SELL errors. "
            "You are systematically too bullish."
        )
    elif overpred > underpred * 1.5:
        _dir_bias = "Model tends to underpredict returns (bearish tilt). Consider adjusting toward neutral/BUY."
    elif underpred > overpred * 1.5:
        _dir_bias = "Model tends to overpredict returns (bullish tilt)."
    else:
        _dir_bias = "No strong directional bias in return errors."

    # ── Failure category analysis ─────────────────────────────────────────
    hold_count  = sum(1 for r in records
                      if (r.get("ai_prediction", {}).get("decision") or "").upper() == "HOLD")
    hold_rate   = round(hold_count / total * 100, 1)

    # bias_note now includes HOLD bias if applicable
    if hold_rate > 55:
        bias_note = f"{_dir_bias} HOLD bias CRITICAL: {hold_rate}% HOLD rate — model over-selects neutral."
    elif hold_rate > 45:
        bias_note = f"{_dir_bias} HOLD bias WARNING: {hold_rate}% HOLD rate — above ideal range."
    else:
        bias_note = _dir_bias

    false_buy_count  = 0
    false_sell_count = 0
    over_hold_count  = 0
    wrong_magnitude  = 0
    trend_reversal   = 0

    for r in records:
        ai_dec  = (r.get("ai_prediction", {}).get("decision") or "").upper()
        act_dec = (r.get("actual_validation", {}).get("actual_decision") or "").upper()
        if ai_dec == act_dec:
            continue
        if ai_dec == "HOLD" and act_dec in ("BUY", "SELL"):
            over_hold_count += 1
        elif ai_dec == "BUY" and act_dec == "SELL":
            actual_ret = r.get("actual_validation", {}).get("actual_return_pct")
            if actual_ret is not None and float(actual_ret) < -5:
                trend_reversal += 1
            else:
                false_buy_count += 1
        elif ai_dec == "SELL" and act_dec == "BUY":
            false_sell_count += 1

    # Recent failures (last 30 records) get priority for top_failure — avoids stale old patterns dominating.
    # Sort by target_date first: append order isn't guaranteed chronological (backfills, retries).
    _recent = sort_by_target_date(records)[-30:]
    _recent_false_sell = sum(1 for r in _recent
                             if (r.get("ai_prediction", {}).get("decision") or "").upper() == "SELL"
                             and (r.get("actual_validation", {}).get("actual_decision") or "").upper() == "BUY")
    _recent_false_buy  = sum(1 for r in _recent
                             if (r.get("ai_prediction", {}).get("decision") or "").upper() == "BUY"
                             and (r.get("actual_validation", {}).get("actual_decision") or "").upper() == "SELL")
    _recent_over_hold  = sum(1 for r in _recent
                             if (r.get("ai_prediction", {}).get("decision") or "").upper() == "HOLD"
                             and (r.get("actual_validation", {}).get("actual_decision") or "").upper() in ("BUY", "SELL"))
    recent_failure_counts = {
        "FALSE_SELL": _recent_false_sell,
        "FALSE_BUY":  _recent_false_buy,
        "OVER_HOLD":  _recent_over_hold,
    }
    top_failure = "NONE"
    failure_counts = {
        "OVER_HOLD":             over_hold_count,
        "FALSE_BUY":             false_buy_count,
        "FALSE_SELL":            false_sell_count,
        "WRONG_MAGNITUDE":       wrong_magnitude,
        "TREND_REVERSAL_MISSED": trend_reversal,
    }
    # Use recent failure counts if they clearly indicate a pattern; fall back to all-time
    if any(v > 2 for v in recent_failure_counts.values()):
        top_failure = max(recent_failure_counts, key=recent_failure_counts.get)
    elif any(v > 0 for v in failure_counts.values()):
        top_failure = max(failure_counts, key=failure_counts.get)

    hold_warning = ""
    if hold_rate > 55:
        hold_warning = (
            f"CRITICAL: HOLD rate is {hold_rate}% — you are severely over-selecting HOLD. "
            "Commit to BUY or SELL when indicators clearly agree."
        )
    elif hold_rate > 45:
        hold_warning = (
            f"CAUTION: HOLD rate is {hold_rate}% — you are over-selecting HOLD. "
            "Commit to BUY or SELL when indicators clearly agree."
        )

    cal_summary = {
        "total_validated_records":    total,
        "decision_match_pct":         round(dec_ok / total * 100, 1),
        "direction_match_pct":        round(dir_ok / total * 100, 1),
        "avg_return_error_pp":        avg_ret_err,
        "overprediction_rate":        round(overpred / total * 100, 1),
        "underprediction_rate":       round(underpred / total * 100, 1),
        "hold_rate_pct":              hold_rate,
        "false_buy_count":            false_buy_count,
        "false_sell_count":           false_sell_count,
        "over_hold_count":            over_hold_count,
        "trend_reversal_missed":      trend_reversal,
        "top_failure_reason":         top_failure,
        "recent_30_false_sell":       _recent_false_sell,
        "recent_30_false_buy":        _recent_false_buy,
        "recent_30_over_hold":        _recent_over_hold,
        "recent_top_failure":         max(recent_failure_counts, key=recent_failure_counts.get) if any(v > 0 for v in recent_failure_counts.values()) else "NONE",
        "symbol_record_count":        len(sym_records),
        "recent_conflicts":           recent_conflicts,
        "bias_note":                  bias_note,
        "hold_rate_warning":          hold_warning,
    }
    # Build per-symbol calibration inline from all historical runs (always fresh, not just static JSON)
    _sym_inline_cal = None
    if symbol and len(sym_records) >= 3:
        _s_total = len(sym_records)
        _s_match = sum(1 for r in sym_records if r.get("comparison", {}).get("decision_match"))
        _s_dir   = sum(1 for r in sym_records if r.get("comparison", {}).get("directional_match"))
        _s_hold  = sum(1 for r in sym_records if (r.get("ai_prediction", {}).get("decision") or "").upper() == "HOLD")
        _s_fbuy  = sum(1 for r in sym_records if
                       (r.get("ai_prediction", {}).get("decision") or "").upper() == "BUY" and
                       (r.get("actual_validation", {}).get("actual_decision") or "").upper() == "SELL")
        _s_fsell = sum(1 for r in sym_records if
                       (r.get("ai_prediction", {}).get("decision") or "").upper() == "SELL" and
                       (r.get("actual_validation", {}).get("actual_decision") or "").upper() == "BUY")
        _s_ohold = sum(1 for r in sym_records if
                       (r.get("ai_prediction", {}).get("decision") or "").upper() == "HOLD" and
                       (r.get("actual_validation", {}).get("actual_decision") or "").upper() in ("BUY", "SELL"))
        _s_errs  = [abs(float(r.get("comparison", {}).get("return_error_pct", 0) or 0)) for r in sym_records
                    if r.get("comparison", {}).get("return_error_pct") is not None]
        _s_match_pct  = round(_s_match / _s_total * 100, 1)
        _s_hold_pct   = round(_s_hold  / _s_total * 100, 1)
        _s_fbuy_pct   = round(_s_fbuy  / _s_total * 100, 1)
        _s_fsell_pct  = round(_s_fsell / _s_total * 100, 1)
        _s_avg_err    = round(sum(_s_errs) / len(_s_errs), 2) if _s_errs else None
        # Top failure for this symbol
        _s_failures = {"OVER_HOLD": _s_ohold, "FALSE_BUY": _s_fbuy, "FALSE_SELL": _s_fsell}
        _s_top_fail = max(_s_failures, key=_s_failures.get) if any(v > 0 for v in _s_failures.values()) else "NONE"
        # Volatility warning: AI errors correlate with high-vol symbols
        _s_vol_warn = _s_avg_err is not None and _s_avg_err > 15
        _s_cal_summary = (
            f"{symbol} has {_s_total} historical runs with {_s_match_pct}% decision match. "
            f"Top failure: {_s_top_fail} ({_s_failures[_s_top_fail] if _s_top_fail != 'NONE' else 0}/{_s_total} runs). "
            f"HOLD rate: {_s_hold_pct}%. False-SELL rate: {_s_fsell_pct}%. False-BUY rate: {_s_fbuy_pct}%. "
            f"Avg return error: {_s_avg_err}pp. "
            + (f"HIGH-ERROR SYMBOL — this stock is hard to predict accurately." if _s_vol_warn else "")
        )
        _sym_inline_cal = {
            "calibration_available": True,
            "match_pct":             _s_match_pct,
            "direction_match_pct":   round(_s_dir / _s_total * 100, 1),
            "hold_rate_pct":         _s_hold_pct,
            "false_buy_rate_pct":    _s_fbuy_pct,
            "false_sell_rate_pct":   _s_fsell_pct,
            "avg_return_error_pp":   _s_avg_err,
            "runs_available":        _s_total,
            "top_failure_categories": [_s_top_fail] if _s_top_fail != "NONE" else [],
            "volatility_warning":    _s_vol_warn,
            "news_earnings_warning": False,
            "calibration_summary":   _s_cal_summary,
        }

    # Try to enhance with static profile (may have richer data) — but prefer inline if both available
    cal_profile_path = ROOT / "data" / "calibration_profiles.json"
    if cal_profile_path.exists() and symbol:
        try:
            cal_profiles = json.loads(cal_profile_path.read_text(encoding="utf-8"))
            sym_profile  = cal_profiles.get("profiles", {}).get(symbol, {})
            if sym_profile.get("calibration_available"):
                # Merge: keep inline freshness, add static profile extras
                _static_cal = {
                    "calibration_available": True,
                    "match_pct":            sym_profile.get("match_pct"),
                    "hold_rate_pct":        sym_profile.get("hold_rate_pct"),
                    "false_buy_rate_pct":   sym_profile.get("false_buy_rate_pct"),
                    "false_sell_rate_pct":  sym_profile.get("false_sell_rate_pct"),
                    "avg_return_error_pp":  sym_profile.get("avg_return_error_pp"),
                    "top_failure_categories": sym_profile.get("top_failure_categories", []),
                    "volatility_warning":   sym_profile.get("volatility_warning"),
                    "news_earnings_warning":sym_profile.get("news_earnings_warning"),
                    "calibration_summary":  sym_profile.get("calibration_summary", ""),
                }
                # Use inline if we have more runs, else use static
                if _sym_inline_cal and _sym_inline_cal.get("runs_available", 0) >= 3:
                    cal_summary["symbol_calibration"] = _sym_inline_cal
                else:
                    cal_summary["symbol_calibration"] = _static_cal
            elif _sym_inline_cal:
                cal_summary["symbol_calibration"] = _sym_inline_cal
        except Exception as exc:
            # Degrade gracefully (a malformed calibration file must never
            # break prediction) but don't hide that this enrichment was
            # skipped -- callers can surface it instead of silently looking
            # complete.
            cal_summary["symbol_calibration_error"] = f"{type(exc).__name__}: {exc}"
            if _sym_inline_cal:
                cal_summary["symbol_calibration"] = _sym_inline_cal
    elif _sym_inline_cal:
        cal_summary["symbol_calibration"] = _sym_inline_cal

    # Phase 1 — confidence calibration curve: informational context so the
    # model can see its own stated confidence has historically NOT tracked
    # correctness (80-100% stated confidence -> 40.0% actual direction match
    # this session's own DB; 40-59% -> 62.1%, i.e. inverted). This cannot make
    # the model magically well-calibrated via prompting alone (more LLM
    # sophistication already made raw accuracy worse elsewhere this session),
    # but it's honest context rather than silence.
    try:
        _conf_map_path = ROOT / "data" / "confidence_calibration_map.json"
        if _conf_map_path.exists():
            _conf_map = json.loads(_conf_map_path.read_text(encoding="utf-8"))
            if _conf_map.get("bins"):
                cal_summary["confidence_calibration_curve"] = _conf_map["bins"]
    except Exception:
        pass

    # Phase 2 — horizon-aware segment reliability: per-symbol calibration above
    # answers "how has this symbol done overall," which hides wildly different
    # reality across horizons (e.g. SPY short-horizon vs. SPY 120-day). This
    # answers the sharper question for THIS specific prediction's horizon.
    if symbol and horizon_days:
        try:
            from segment_reliability import classify_records, segment_label
            cal_summary["segment_reliability"] = {
                "segment": segment_label(symbol, horizon_days),
                **classify_records(records, symbol, horizon_days),
            }
        except Exception as exc:
            # Degrade gracefully -- this is enrichment, not required for a
            # prediction to proceed.
            cal_summary["segment_reliability_error"] = f"{type(exc).__name__}: {exc}"

    # Self-learning retrieval -- the k most similar past validated runs by
    # feature-vector distance, from this SAME leakage-safe `records` list
    # (already filtered to target_date < as_of_date above). Reuses that
    # filtering rather than re-querying, so this can never see a precedent
    # the aggregate stats above couldn't also see.
    if ENABLE_CASE_RETRIEVAL and feature_packet and symbol:
        try:
            from case_retrieval import find_similar_cases
            cal_summary["nearest_cases"] = find_similar_cases(
                feature_packet, symbol, horizon_days, records,
                current_origin_date=as_of_date, k=5,
            )
        except Exception as exc:
            cal_summary["nearest_cases_error"] = f"{type(exc).__name__}: {exc}"

    return cal_summary


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNAL SCORE ENGINE — deterministic bull/bear/uncertainty from feature packet
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_signal_scores(feature_packet: dict) -> dict:
    """
    Compute deterministic bullish/bearish/uncertainty scores (each 0-100) from
    the feature packet. Each indicator casts a vote (bull, bear, uncertain) that
    sums to 1.0 per indicator. Final score = mean vote × 100 across all indicators.
    """
    trend     = feature_packet.get("trend", {}) or {}
    momentum  = feature_packet.get("momentum", {}) or {}
    volatility = feature_packet.get("volatility", {}) or {}
    returns   = feature_packet.get("returns", {}) or {}
    reversal  = feature_packet.get("reversal_signals", {}) or {}

    signals: List[Tuple[float, float, float]] = []  # (bull, bear, uncert) each vote sums to 1.0

    # 1. Trend regime + SMA alignment
    regime = trend.get("trend_regime", "sideways")
    pvs20  = trend.get("price_vs_sma_20_pct") or 0.0
    pvs50  = trend.get("price_vs_sma_50_pct") or 0.0
    if regime == "bullish" and pvs20 > 2 and pvs50 > 2:
        signals.append((1.0, 0.0, 0.0))
    elif regime == "bearish" and pvs20 < -2 and pvs50 < -2:
        signals.append((0.0, 1.0, 0.0))
    elif pvs20 > 1:
        signals.append((0.6, 0.0, 0.4))
    elif pvs20 < -1:
        signals.append((0.0, 0.6, 0.4))
    else:
        signals.append((0.0, 0.0, 1.0))

    # 2. RSI
    rsi = momentum.get("RSI_14")
    if rsi is not None:
        if 55 <= rsi < 70:
            signals.append((1.0, 0.0, 0.0))
        elif 30 < rsi <= 45:
            signals.append((0.0, 1.0, 0.0))
        elif rsi >= 78:
            signals.append((0.0, 0.5, 0.5))   # extreme overbought → bearish lean + high uncertainty
        elif rsi >= 70:
            signals.append((0.3, 0.0, 0.7))   # overbought → mostly uncertain, mild bull caution
        elif rsi <= 22:
            signals.append((0.5, 0.0, 0.5))   # extreme oversold → bullish lean + high uncertainty
        elif rsi <= 30:
            signals.append((0.0, 0.4, 0.6))   # oversold → uncertain (reversal risk)
        else:
            signals.append((0.0, 0.0, 1.0))

    # 3. MACD line + histogram
    macd_v = momentum.get("MACD")
    macd_h = momentum.get("MACD_histogram")
    if macd_v is not None and macd_h is not None:
        if macd_v > 0 and macd_h > 0:
            signals.append((1.0, 0.0, 0.0))
        elif macd_v < 0 and macd_h < 0:
            signals.append((0.0, 1.0, 0.0))
        elif macd_h > 0:
            signals.append((0.6, 0.0, 0.4))
        elif macd_h < 0:
            signals.append((0.0, 0.6, 0.4))
        else:
            signals.append((0.0, 0.0, 1.0))

    # 4. Recent returns (20d + 60d) — stronger conviction when both agree strongly
    r20 = returns.get("return_20d")
    r60 = returns.get("return_60d")
    if r20 is not None and r60 is not None:
        if r20 > 5 and r60 > 8:          # very strong uptrend
            signals.append((1.0, 0.0, 0.0))
            signals.append((1.0, 0.0, 0.0))  # double weight for strong consensus
        elif r20 > 3 and r60 > 5:
            signals.append((1.0, 0.0, 0.0))
        elif r20 < -5 and r60 < -8:      # very strong downtrend
            signals.append((0.0, 1.0, 0.0))
            signals.append((0.0, 1.0, 0.0))  # double weight for strong consensus
        elif r20 < -3 and r60 < -5:
            signals.append((0.0, 1.0, 0.0))
        elif r20 > 1:
            signals.append((0.6, 0.0, 0.4))
        elif r20 < -1:
            signals.append((0.0, 0.6, 0.4))
        else:
            signals.append((0.0, 0.0, 1.0))

    # 5. Bollinger band position
    bb_pos = volatility.get("BB_position")
    if bb_pos is not None:
        if bb_pos > 0.8:
            signals.append((0.0, 0.4, 0.6))   # near upper band → bearish tilt + uncertain
        elif bb_pos < 0.2:
            signals.append((0.4, 0.0, 0.6))   # near lower band → bullish tilt + uncertain
        else:
            signals.append((0.0, 0.0, 1.0))

    # 6. Volatility regime
    vol_regime = volatility.get("volatility_regime", "medium")
    if vol_regime == "high":
        signals.append((0.0, 0.0, 1.0))
    elif vol_regime == "low":
        pass   # no vote — low vol is neutral

    # 7. Reversal risk
    rev_risk = reversal.get("reversal_risk", "low")
    if rev_risk == "high":
        signals.append((0.0, 0.0, 1.0))
    elif rev_risk == "medium":
        signals.append((0.0, 0.0, 0.8))

    if not signals:
        return {"bullish_score": 50, "bearish_score": 50, "uncertainty_score": 50,
                "dominant": "uncertain", "dominant_score": 50}

    n = len(signals)
    bull_s  = round(sum(s[0] for s in signals) / n * 100)
    bear_s  = round(sum(s[1] for s in signals) / n * 100)
    uncert_s = round(sum(s[2] for s in signals) / n * 100)

    if bull_s > bear_s and bull_s > uncert_s:
        dominant, dom_score = "bullish", bull_s
    elif bear_s > bull_s and bear_s > uncert_s:
        dominant, dom_score = "bearish", bear_s
    else:
        dominant, dom_score = "uncertain", uncert_s

    return {
        "bullish_score":    bull_s,
        "bearish_score":    bear_s,
        "uncertainty_score": uncert_s,
        "dominant":          dominant,
        "dominant_score":    dom_score,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — DETERMINISTIC TECHNICAL SCORE OVERRIDE
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_technical_override_score(feature_packet: dict) -> dict:
    """
    Deterministic technical scoring -10 to +10.
    Extreme scores override AI decision entirely.
    Returns: {"score": int, "override": str or None, "breakdown": dict}
    """
    score = 0
    breakdown = {}

    momentum   = feature_packet.get("momentum", {})
    trend      = feature_packet.get("trend", {})
    volatility = feature_packet.get("volatility", {})
    reversal   = feature_packet.get("reversal_signals", {})

    rsi        = momentum.get("RSI_14")
    macd_hist  = momentum.get("MACD_histogram")
    macd_line  = momentum.get("MACD")

    price      = feature_packet.get("price_snapshot", {}).get("last_close") or feature_packet.get("origin_price")
    sma20      = trend.get("sma_20")
    sma50      = trend.get("sma_50")
    bb_upper   = volatility.get("BB_upper") if volatility else None
    bb_lower   = volatility.get("BB_lower") if volatility else None

    # RSI signals (-2 to +2)
    if rsi is not None:
        if rsi > 75:
            score -= 2
            breakdown["RSI"] = f"OVERBOUGHT ({rsi:.1f}) → -2"
        elif rsi > 65:
            score -= 1
            breakdown["RSI"] = f"UPPER NEUTRAL ({rsi:.1f}) → -1"
        elif rsi < 25:
            score += 2
            breakdown["RSI"] = f"OVERSOLD ({rsi:.1f}) → +2"
        elif rsi < 35:
            score += 1
            breakdown["RSI"] = f"LOWER NEUTRAL ({rsi:.1f}) → +1"
        else:
            breakdown["RSI"] = f"NEUTRAL ({rsi:.1f}) → 0"

    # MACD signals (-2 to +2)
    if macd_hist is not None:
        if macd_hist > 0 and macd_line is not None and macd_line > 0:
            score += 2
            breakdown["MACD"] = f"BULLISH histogram+line positive → +2"
        elif macd_hist > 0:
            score += 1
            breakdown["MACD"] = f"BULLISH histogram positive → +1"
        elif macd_hist < 0 and macd_line is not None and macd_line < 0:
            score -= 2
            breakdown["MACD"] = f"BEARISH histogram+line negative → -2"
        elif macd_hist < 0:
            score -= 1
            breakdown["MACD"] = f"BEARISH histogram negative → -1"
        else:
            breakdown["MACD"] = "NEUTRAL → 0"

    # SMA alignment (-2 to +2)
    if price and sma20 and sma50:
        if price > sma20 > sma50:
            score += 2
            breakdown["SMA"] = f"BULLISH price>{sma20:.2f}>{sma50:.2f} → +2"
        elif price > sma20:
            score += 1
            breakdown["SMA"] = f"MILD BULLISH price>SMA20 → +1"
        elif price < sma20 < sma50:
            score -= 2
            breakdown["SMA"] = f"BEARISH price<{sma20:.2f}<{sma50:.2f} → -2"
        elif price < sma20:
            score -= 1
            breakdown["SMA"] = f"MILD BEARISH price<SMA20 → -1"
        else:
            breakdown["SMA"] = "NEUTRAL → 0"

    # Bollinger Band position (-1 to +1)
    if bb_upper and bb_lower and price:
        if price >= bb_upper * 0.99:
            score -= 1
            breakdown["BB"] = f"Near UPPER band → -1"
        elif price <= bb_lower * 1.01:
            score += 1
            breakdown["BB"] = f"Near LOWER band → +1"
        else:
            breakdown["BB"] = "INSIDE bands → 0"

    # 20-day return momentum (-1 to +1)
    ret_20 = feature_packet.get("returns", {}).get("return_20d")
    if ret_20 is not None:
        if ret_20 > 8:
            score -= 1
            breakdown["RET_20D"] = f"Overextended +{ret_20:.1f}% → -1"
        elif ret_20 < -8:
            score += 1
            breakdown["RET_20D"] = f"Oversold {ret_20:.1f}% → +1"
        else:
            breakdown["RET_20D"] = f"Normal {ret_20:.1f}% → 0"

    # Phase 9 — Volume Confirmation (-2 to +2)
    vol_data  = feature_packet.get("volume", {})
    vol_ratio = vol_data.get("volume_ratio_20")
    ret_1d    = feature_packet.get("returns", {}).get("return_1d")
    if vol_ratio is not None and ret_1d is not None:
        if ret_1d > 0 and vol_ratio > 1.2:
            score += 2
            breakdown["VOLUME"] = f"CONFIRMED BULL: price UP + volume {vol_ratio:.2f}x avg → +2"
        elif ret_1d > 0 and vol_ratio < 0.8:
            score -= 1
            breakdown["VOLUME"] = f"SUSPECT BULL: price UP but volume only {vol_ratio:.2f}x avg → -1"
        elif ret_1d < 0 and vol_ratio > 1.2:
            score -= 2
            breakdown["VOLUME"] = f"CONFIRMED BEAR: price DOWN + volume {vol_ratio:.2f}x avg → -2"
        elif ret_1d < 0 and vol_ratio < 0.8:
            score += 1
            breakdown["VOLUME"] = f"WEAK SELL: price DOWN but low volume {vol_ratio:.2f}x avg → +1"
        else:
            breakdown["VOLUME"] = f"NEUTRAL volume ({vol_ratio:.2f}x avg) → 0"

    # Phase 8 — ADX Trend Strength (confidence multiplier, no score change but flag choppy)
    adx_val    = trend.get("ADX_14")
    adx_regime = trend.get("adx_regime", "unknown")
    if adx_val is not None:
        if adx_val < 20:
            breakdown["ADX"] = f"CHOPPY MARKET (ADX={adx_val:.1f} < 20) — signals unreliable, override disabled"
        elif adx_val > 25:
            breakdown["ADX"] = f"STRONG TREND (ADX={adx_val:.1f} > 25) — signals reliable"
        else:
            breakdown["ADX"] = f"WEAK TREND (ADX={adx_val:.1f}) — moderate confidence"

    # Phase 10 — RSI Divergence (-3 to +3, most powerful signal)
    rsi_div = trend.get("rsi_divergence", "NONE")
    if rsi_div == "BULLISH_DIVERGENCE":
        score += 3
        breakdown["RSI_DIVERGENCE"] = "BULLISH DIVERGENCE: price fell but RSI rose → reversal UP likely → +3"
    elif rsi_div == "BEARISH_DIVERGENCE":
        score -= 3
        breakdown["RSI_DIVERGENCE"] = "BEARISH DIVERGENCE: price rose but RSI fell → reversal DOWN likely → -3"
    else:
        breakdown["RSI_DIVERGENCE"] = "No divergence detected → 0"

    # Level signal (0 to +1): oversold AND sitting near a recent support level.
    # Deliberately asymmetric and modest -- reviewing the eval log showed the
    # mirror case (overbought + near resistance) does NOT reverse as reliably,
    # so this only ever nudges toward BUY, never SELL, and by a small amount
    # since near_support/reversal_risk alone didn't perfectly track the
    # validated RSI+ADX+trend pattern either (it's a supporting signal, not
    # the primary one -- see the CAPITULATION GUARD in _apply_guardrails).
    near_support   = bool(reversal.get("near_support"))
    _rev_risk_flag = reversal.get("reversal_risk", "low")
    if rsi is not None and rsi < 30 and near_support and _rev_risk_flag in ("high", "medium"):
        score += 1
        breakdown["LEVEL"] = f"OVERSOLD AT SUPPORT (reversal_risk={_rev_risk_flag}) → +1"
    else:
        breakdown["LEVEL"] = f"reversal_risk={_rev_risk_flag}, near_support={near_support} → 0"

    # In choppy markets (ADX < 20), disable hard overrides — signals are noise
    choppy = adx_val is not None and adx_val < 20
    override = None
    if not choppy:
        if score >= 5:
            override = "BUY"
        elif score <= -5:
            override = "SELL"

    max_possible = 13
    return {
        "score":      score,
        "override":   override,
        "breakdown":  breakdown,
        "adx_regime": adx_regime,
        "choppy_market": choppy,
        "verdict":    f"TECHNICAL SCORE: {score:+d}/{max_possible} → {'CHOPPY — no override' if choppy else ('FORCE ' + override if override else 'Let AI decide')}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — EARNINGS CALENDAR GATE
# ═══════════════════════════════════════════════════════════════════════════════

def _is_recent_origin(origin_str: str, max_days: int = 7) -> bool:
    """True when origin_str is within max_days of today (i.e. a live prediction).

    Any enrichment source that can only report *present-day* real-world state
    (yfinance's live options chain, yfinance's "next upcoming earnings" calendar)
    must be gated behind this before being injected into a prediction — otherwise
    a historical replay leaks knowledge that didn't exist as of the origin date
    being replayed. Unparseable/missing origin dates are treated as NOT recent
    (conservative default: skip the live-only enrichment rather than risk leakage).
    """
    from datetime import date as _date_cls
    from stock_prediction_agent import _parse_ymd
    origin_date_obj = _parse_ymd(origin_str)
    if not origin_date_obj:
        return False
    return (_date_cls.today() - origin_date_obj).days <= max_days


def _get_earnings_warning(symbol: str, prediction_start: str, prediction_end: str) -> str:
    """Check if earnings fall within prediction window using yfinance. Returns warning string or empty."""
    try:
        import yfinance as yf
        from datetime import datetime as _dtm, timedelta as _td
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is None:
            return ""
        # calendar can be a dict or DataFrame depending on yfinance version
        if hasattr(cal, 'to_dict'):
            cal = cal.to_dict()
        earnings_date = None
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date") or cal.get("earnings_date")
            if ed:
                if isinstance(ed, (list, tuple)) and len(ed) > 0:
                    earnings_date = ed[0]
                else:
                    earnings_date = ed
        if earnings_date is None:
            return ""
        if hasattr(earnings_date, 'date'):
            earnings_date = earnings_date.date()
        elif isinstance(earnings_date, str):
            earnings_date = _dtm.strptime(earnings_date[:10], "%Y-%m-%d").date()

        p_start = _dtm.strptime(str(prediction_start)[:10], "%Y-%m-%d").date()
        p_end   = _dtm.strptime(str(prediction_end)[:10],   "%Y-%m-%d").date()

        window_start = p_start - _td(days=7)
        window_end   = p_end   + _td(days=7)

        if window_start <= earnings_date <= window_end:
            days_away = (earnings_date - p_start).days
            return (
                f"EARNINGS WARNING: {symbol} has earnings on {earnings_date} "
                f"({days_away:+d} days from prediction start). "
                f"Options prices will be heavily impacted by earnings volatility. "
                f"Confidence reduced. Consider avoiding options trades spanning earnings."
            )
        return ""
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 5 — PUT/CALL RATIO SIGNAL
# ═══════════════════════════════════════════════════════════════════════════════

def _get_put_call_ratio(symbol: str) -> dict:
    """Fetch put/call ratio from yfinance options chain. Returns sentiment dict."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            return {"available": False}
        # Use nearest expiration
        nearest_exp = expirations[0]
        chain = ticker.option_chain(nearest_exp)
        total_put_oi  = float(chain.puts["openInterest"].sum()  if "openInterest" in chain.puts.columns  else 0)
        total_call_oi = float(chain.calls["openInterest"].sum() if "openInterest" in chain.calls.columns else 0)
        if total_call_oi == 0:
            return {"available": False}
        pc_ratio = round(total_put_oi / total_call_oi, 3)
        if pc_ratio > 1.5:
            sentiment = "BEARISH"
            note = f"P/C ratio {pc_ratio:.2f} > 1.5 — market is heavily positioned for downside"
        elif pc_ratio < 0.5:
            sentiment = "BULLISH"
            note = f"P/C ratio {pc_ratio:.2f} < 0.5 — market is heavily positioned for upside"
        elif pc_ratio < 0.8:
            sentiment = "MILDLY_BULLISH"
            note = f"P/C ratio {pc_ratio:.2f} — slight bullish bias"
        elif pc_ratio > 1.2:
            sentiment = "MILDLY_BEARISH"
            note = f"P/C ratio {pc_ratio:.2f} — slight bearish bias"
        else:
            sentiment = "NEUTRAL"
            note = f"P/C ratio {pc_ratio:.2f} — balanced market positioning"
        return {
            "available":       True,
            "put_call_ratio":  pc_ratio,
            "sentiment":       sentiment,
            "note":            note,
            "expiration_used": nearest_exp,
        }
    except Exception:
        return {"available": False}


# ═══════════════════════════════════════════════════════════════════════════════
# DECISION GUARDRAILS (deterministic — dynamic thresholds by horizon)
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_guardrails(
    predicted_return_pct: float,
    confidence_score: int,
    risk_score: int,
    data_quality_score: int,
    horizon_days: int = 30,
    signal_scores: Optional[dict] = None,
    reversal_risk: str = "low",
    rsi: Optional[float] = None,
    symbol: str = "",
    adx: Optional[float] = None,
    trend_regime: str = "",
) -> Tuple[str, str]:
    """Guardrail: predicted_return_pct vs. the SAME horizon-scaled dead-band used
    to grade the actual outcome (stock_comparison_engine.decision_thresholds_for_horizon).

    Previously this was "decisive" -- any nonzero predicted_return_pct became a
    BUY/SELL with no dead-band, while the ground-truth label used a flat ±2%
    band regardless of horizon. The two definitions of HOLD had nothing to do
    with each other: the AI could only ever reach HOLD via the capitulation
    guard below, while "the market was actually flat" required an actual ±2%
    (now horizon-scaled) move. Using the identical threshold function on both
    sides is what makes decision_match actually measure agreement, not an
    artifact of two unrelated rules.

    Only truly unusable inputs (data quality < 50, confidence < 20) produce REVIEW.

    One exception, added after reviewing the eval log: extreme-oversold-RSI in a
    strong, established downtrend (RSI<25, ADX>25, bearish regime) resolved with
    a POSITIVE actual return in every sampled historical occurrence (4/4; TSLA
    2026-08-01, DELL 2026-01-20, AMZN 2026-06-18 were all misses on this exact
    setup, SPY 2026-03-28 was the one hit) despite the model calling SELL/HOLD
    in 3 of those 4. The mirror case (extreme overbought + strong uptrend) showed
    no such one-sidedness (44% match, mixed outcomes both ways), so this stays
    asymmetric on purpose -- it is not a general "fade the extreme RSI" rule.
    """
    _is_index = symbol.upper() in ("SPY", "SPX", "QQQ", "IWM", "DIA")

    # Only critically bad data → REVIEW (not HOLD)
    if data_quality_score < 50:
        return "REVIEW", f"Data quality critically low ({data_quality_score}/100) — cannot analyse."

    if confidence_score < 20:
        return "REVIEW", f"Confidence critically low ({confidence_score}/100) — model has no signal."

    _capitulation_setup = (
        predicted_return_pct < 0
        and rsi is not None and rsi < 25
        and adx is not None and adx > 25
        and trend_regime == "bearish"
    )
    if _capitulation_setup:
        return "HOLD", (
            f"CAPITULATION GUARD: RSI={rsi:.1f} (extreme oversold) with ADX={adx:.1f} "
            f"(strong downtrend) — this exact setup resolved with a positive actual "
            f"return in every sampled historical occurrence despite the model favoring "
            f"SELL/HOLD; downgrading decisive SELL (predicted {predicted_return_pct:+.2f}%) "
            f"to HOLD rather than compounding the downside bias. "
            f"[conf={confidence_score}, risk={risk_score}, rev_risk={reversal_risk}, "
            f"{'index' if _is_index else 'stock'}, {horizon_days}d horizon]"
        )

    # Horizon-scaled dead-band: same formula used to grade the actual outcome.
    from stock_comparison_engine import decision_thresholds_for_horizon
    buy_th, sell_th = decision_thresholds_for_horizon(horizon_days)

    if predicted_return_pct > buy_th:
        decision = "BUY"
        reason   = (
            f"BUY: predicted return {predicted_return_pct:+.2f}% > horizon-scaled threshold "
            f"+{buy_th:.2f}%. "
            f"[conf={confidence_score}, risk={risk_score}, rev_risk={reversal_risk}, "
            f"{'index' if _is_index else 'stock'}, {horizon_days}d horizon]"
        )
    elif predicted_return_pct < sell_th:
        decision = "SELL"
        reason   = (
            f"SELL: predicted return {predicted_return_pct:+.2f}% < horizon-scaled threshold "
            f"{sell_th:.2f}%. "
            f"[conf={confidence_score}, risk={risk_score}, rev_risk={reversal_risk}, "
            f"{'index' if _is_index else 'stock'}, {horizon_days}d horizon]"
        )
    else:
        decision = "HOLD"
        reason   = (
            f"HOLD: predicted return {predicted_return_pct:+.2f}% is within the horizon-scaled "
            f"dead-band (±{buy_th:.2f}% at {horizon_days}d) — too small a move to call a direction. "
            f"[conf={confidence_score}, risk={risk_score}, rev_risk={reversal_risk}, "
            f"{'index' if _is_index else 'stock'}, {horizon_days}d horizon]"
        )

    return decision, reason


# ═══════════════════════════════════════════════════════════════════════════════
# GEMINI PROMPT BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def _build_symbol_calibration_section(calibration_summary: dict) -> str:
    """Build per-symbol calibration section for Gemini prompt if available."""
    sym_cal = calibration_summary.get("symbol_calibration", {})
    if not sym_cal or not sym_cal.get("calibration_available"):
        return ""

    match_pct  = sym_cal.get("match_pct") or 0
    hold_r     = sym_cal.get("hold_rate_pct") or 0
    fbuy_r     = sym_cal.get("false_buy_rate_pct") or 0
    fsell_r    = sym_cal.get("false_sell_rate_pct") or 0
    avg_err    = sym_cal.get("avg_return_error_pp")
    runs       = sym_cal.get("runs_available", 0)
    top_fails  = sym_cal.get("top_failure_categories", [])
    cal_sum    = sym_cal.get("calibration_summary", "")

    _match_label = "ABOVE TARGET" if match_pct >= 60 else "BELOW 60% TARGET" if match_pct >= 40 else "VERY LOW -- unreliable symbol"
    _hold_label  = "TOO HIGH -- commit more" if hold_r > 40 else "OK"
    _fbuy_label  = "CAUTION: too many wrong BUY calls" if fbuy_r > 30 else "OK"
    _fsell_label = "CAUTION: too many wrong SELL calls -- lean BUY" if fsell_r > 30 else "OK"

    lines = [
        "=" * 70,
        f"SYMBOL-SPECIFIC CALIBRATION PROFILE -- {runs} HISTORICAL RUNS ON THIS EXACT SYMBOL",
        "(Highest priority -- these are THIS symbol's known failure patterns from all past runs)",
        "=" * 70,
        f"  Decision match rate:    {match_pct}%  ({_match_label})",
        f"  HOLD rate:              {hold_r}%   ({_hold_label})",
        f"  False BUY rate:         {fbuy_r}%   ({_fbuy_label})",
        f"  False SELL rate:        {fsell_r}%  ({_fsell_label})",
    ]
    if avg_err is not None:
        _err_label = "(HIGH -- magnitude predictions unreliable)" if avg_err > 15 else "(reasonable)"
        lines.append(f"  Avg return error:       {avg_err} pp  {_err_label}")
    if top_fails:
        lines.append(f"  Top failure categories: {', '.join(top_fails)}")
    if sym_cal.get("volatility_warning"):
        lines.append("  HIGH-ERROR SYMBOL: Volatility shifts frequently missed -- weight ATR/BB heavily.")
    if sym_cal.get("news_earnings_warning"):
        lines.append("  EARNINGS/NEWS RISK: Events caused AI errors on this symbol -- check calendar.")
    if cal_sum:
        lines.append(f"  Summary: {cal_sum}")

    # Specific SELL/BUY guidance from false rates
    if fsell_r > 30:
        lines.append(
            f"  HARD RULE -- FALSE_SELL DOMINANT ({fsell_r}% of runs): "
            "Do NOT issue SELL unless ALL FOUR bearish conditions are met: "
            "trend=bearish AND price below SMA50 AND RSI<42 AND 20d<-3%. "
            "If ANY condition is missing -> BUY."
        )
    if fbuy_r > 30:
        lines.append(
            f"  HARD RULE -- FALSE_BUY DOMINANT ({fbuy_r}% of runs): "
            "Add reversal_risk check before BUY. If RSI>70 AND price near resistance -> reduce return magnitude."
        )
    if hold_r > 40:
        lines.append(
            f"  CRITICAL -- HOLD OVER-USED ({hold_r}%): "
            "Commit to BUY or SELL when any directional signal exists. HOLD is almost always wrong here."
        )

    lines.append("=" * 70)
    lines.append("")
    return "\n".join(lines) + "\n"


def _build_segment_reliability_section(calibration_summary: dict) -> str:
    """Phase 2 — surface this exact (symbol, horizon_bucket) segment's proven/
    unproven status, distinct from the overall per-symbol profile above (which
    blends every horizon together and can hide that e.g. this symbol is fine
    short-horizon but unproven at this specific long horizon, or vice versa).

    Deliberately informational, not a HARD RULE like the sections above --
    this is a trust/calibration signal, not a decision override."""
    seg = calibration_summary.get("segment_reliability")
    if not seg or seg.get("classification") == "INSUFFICIENT_DATA":
        return ""

    cls = seg.get("classification")
    n   = seg.get("n", 0)
    drm = seg.get("direction_match_pct")

    if cls == "PROVEN":
        note = f"This segment has a real track record: {drm}% direction match over {n} runs. Reasonable confidence is warranted."
    else:
        note = (
            f"UNPROVEN SEGMENT: only {drm}% direction match over {n} runs for this exact "
            f"symbol/horizon combination -- historically close to or below a coin flip. "
            "Do not let a confident-sounding rationale overstate how reliable this specific "
            "call is; widen uncertainty and prefer a lower confidence_score."
        )
    return f"SEGMENT RELIABILITY ({seg.get('segment', '')}): {note}\n\n"


def _build_nearest_cases_section(calibration_summary: dict) -> str:
    """Self-learning retrieval — concrete historical precedent, not just
    aggregate percentages: the k most similar past validated runs (by
    standardized feature-vector distance, core/case_retrieval.py) and what
    actually happened to each one. Same spirit as symbol calibration / segment
    reliability above, but grounded in specific comparable cases instead of a
    blended rate, so a run that looks statistically fine in aggregate can
    still surface a handful of very similar precedents that all went wrong."""
    cases = calibration_summary.get("nearest_cases")
    if not cases:
        return ""

    lines = [
        "=" * 70,
        f"NEAREST HISTORICAL PRECEDENTS -- {len(cases)} MOST SIMILAR PAST VALIDATED RUNS",
        "(Concrete comparable cases ranked by feature similarity, not aggregate stats)",
        "=" * 70,
    ]
    wrong_direction_repeat = 0
    for c in cases:
        outcome = "CORRECT" if c["decision_match"] else "WRONG"
        tier = "same symbol" if c["match_tier"] == "SAME_SYMBOL" else "same horizon bucket, different symbol"
        err = c.get("abs_return_error_pct")
        err_s = f"{err}pp error" if err is not None else "error n/a"
        lines.append(
            f"  [{tier}] {c['symbol']} {c['horizon_days']}d (origin {c['origin_date']}): "
            f"AI said {c['ai_decision']}, actual was {c['actual_decision']} -> {outcome} "
            f"({err_s}, similarity dist={c['distance']})"
        )
        if not c["decision_match"]:
            wrong_direction_repeat += 1

    if wrong_direction_repeat >= 3:
        lines.append(
            f"  CAUTION: {wrong_direction_repeat}/{len(cases)} of the closest precedents were WRONG. "
            "Do not mechanically repeat the same call pattern that failed on these similar setups -- "
            "widen uncertainty and weigh this alongside (not instead of) the technical/fundamental signals."
        )
    lines.append("=" * 70)
    lines.append("")
    return "\n".join(lines) + "\n"


def _build_options_context_section(opts: dict, horizon_days: int) -> str:
    """Build the OPTIONS STRATEGY CONTEXT section injected into the Gemini prompt."""
    if not opts:
        return ""
    _dir  = str(opts.get("direction", "") or "").strip().capitalize()
    _type = str(opts.get("opt_type", "") or "").strip().capitalize()
    if not _dir or not _type:
        return ""

    _delta = opts.get("delta") or opts.get("delta_ui")
    _dte   = opts.get("dte")
    _qty   = opts.get("quantity", 1)
    _tp    = opts.get("take_profit_pct")
    _sl    = opts.get("stop_loss_pct")
    _is_buy  = _dir.lower() in ("buy", "long")
    _is_call = _type.lower() == "call"

    # What the strategy needs to profit
    if _is_buy and _is_call:
        _prob_worthless = 100 - (_delta or 12)
        _need = (
            f"Stock must RISE fast enough to push the {_delta}-delta call into profit within {_dte} days. "
            f"A {_delta}-delta call has ~{_prob_worthless}% chance of expiring worthless. "
            f"Gradual drift is NOT enough — you need a significant upward move, not a slow trend."
        )
        _alignment = "BUY direction needed — stock must rise sharply."
    elif _is_buy and not _is_call:
        _prob_worthless = 100 - (_delta or 12)
        _need = (
            f"Stock must FALL fast enough to push the {_delta}-delta put into profit within {_dte} days. "
            f"A {_delta}-delta put has ~{_prob_worthless}% chance of expiring worthless. "
            f"You need a significant downward move quickly."
        )
        _alignment = "SELL direction needed — stock must fall sharply."
    elif not _is_buy and not _is_call:  # Sell Put
        _prob_profit = 100 - (_delta or 30)
        _need = (
            f"Stock must STAY ABOVE the {_delta}-delta put strike for {_dte} days to keep the full premium. "
            f"Short put has ~{_prob_profit}% probability of being profitable at expiry. "
            f"Profits from NEUTRAL to BULLISH conditions — stock must not crash."
        )
        _alignment = "NEUTRAL to BULLISH needed — stock must stay flat or rise."
    else:  # Sell Call
        _prob_profit = 100 - (_delta or 30)
        _need = (
            f"Stock must STAY BELOW the {_delta}-delta call strike for {_dte} days to keep the full premium. "
            f"Short call has ~{_prob_profit}% probability of being profitable at expiry. "
            f"Profits from NEUTRAL to BEARISH conditions — stock must not surge."
        )
        _alignment = "NEUTRAL to BEARISH needed — stock must stay flat or fall."

    # DTE-specific guidance
    if _dte is not None and _dte <= 5:
        _dte_note = (
            f"VERY SHORT DTE ({_dte} days) — this is a VOLATILITY bet, not a direction bet. "
            f"The option expires in {_dte} days. Your {horizon_days}-day horizon prediction is useful for context "
            f"but the option cares only about what happens in the NEXT {_dte} DAYS. "
            f"Assess ATR_14 carefully: is current daily volatility large enough to move a {_delta}-delta strike into profit? "
            f"A quiet, slow-moving stock will NOT profit a {_dte}-DTE {_delta}-delta option regardless of trend. "
            f"In your options_strategy_assessment: explicitly state whether ATR supports a large enough single-day move."
        )
    elif _dte is not None and _dte <= 21:
        _dte_note = (
            f"SHORT DTE ({_dte} days) — short-term momentum is the primary driver. "
            f"RSI direction, MACD histogram momentum, and 5d/10d returns matter most. "
            f"The stock must move in the right direction within {_dte} days, not over the full {horizon_days}-day horizon."
        )
    else:
        _dte_note = (
            f"MEDIUM/LONG DTE ({_dte} days) — your directional BUY/SELL/HOLD prediction maps well to this option. "
            f"The option has enough time to follow the trend. RSI, MACD, and 20-60d returns are all directly useful."
        )

    _timeframe_mismatch = ""
    if _dte is not None and horizon_days > 0 and _dte < horizon_days / 2:
        _timeframe_mismatch = (
            f"\nTIMEFRAME MISMATCH WARNING: Option expires in {_dte} days but prediction horizon is {horizon_days} days. "
            f"These are very different windows. The option is a SHORT-TERM position inside a LONG-TERM prediction. "
            f"Your directional call covers the full {horizon_days} days, but the option only captures the first {_dte} days."
        )

    return (
        f"\nOPTIONS STRATEGY CONTEXT (you are predicting for an options position — factor this into your analysis):\n"
        f"  Strategy:     {_dir} {_type}\n"
        f"  Contracts:    {_qty}\n"
        f"  Delta:        {_delta} (option has ~{_delta}% probability of being in-the-money at expiry)\n"
        f"  DTE:          {_dte} days (option EXPIRES in {_dte} days)\n"
        f"  Take Profit:  {str(_tp) + '% of premium' if _tp else 'None'}\n"
        f"  Stop Loss:    {str(_sl) + '% of premium' if _sl else 'None'}\n"
        f"\nWHAT THIS STRATEGY NEEDS TO PROFIT:\n{_need}\n"
        f"\nDIRECTION ALIGNMENT: {_alignment}\n"
        f"\nDTE GUIDANCE:\n{_dte_note}"
        f"{_timeframe_mismatch}\n"
    )


def _build_tt_context_section(normalized_input: dict) -> str:
    """Build TT Historical Options Intelligence section — real backtest data from context period."""
    ctx_opt = normalized_input.get("tt_context_optimizer") or {}
    results = ctx_opt.get("results") or []
    if not results:
        return ""

    ctx_start    = ctx_opt.get("ctx_start", "")
    origin_date  = ctx_opt.get("origin_date", "")
    direction    = str(ctx_opt.get("direction", "")).upper()
    opt_type     = str(ctx_opt.get("opt_type", "")).upper()
    current_iv   = ctx_opt.get("current_iv")
    valid_n      = ctx_opt.get("valid_combos", 0)
    total_n      = ctx_opt.get("total_combos", 0)
    symbol       = str(normalized_input.get("symbol", ""))

    valid_rows = sorted(
        [r for r in results if not r.get("no_data")],
        key=lambda x: x.get("total_pnl", 0), reverse=True
    )
    if not valid_rows:
        return ""

    best  = valid_rows[0]
    worst = valid_rows[-1]

    lines = [
        "",
        "=" * 70,
        "TT HISTORICAL OPTIONS INTELLIGENCE — REAL TASTYTRADE DATA (not simulation)",
        f"Learning period : {ctx_start}  →  {origin_date}",
        f"Strategy tested : {direction} {opt_type} options on {symbol}",
        f"Combos tested   : {total_n} total  |  {valid_n} returned data",
        "THESE ARE REAL BACKTESTED OPTIONS RESULTS — this is what ACTUALLY worked",
        "on this stock during the historical context window. Weight this heavily.",
        "=" * 70,
        "",
        "RANKED PARAMETER COMBINATIONS (real P&L from TastyTrade API):",
    ]

    for i, r in enumerate(valid_rows[:10]):
        if i == 0:
            tag = "  🥇 #1 BEST →"
        elif i == len(valid_rows) - 1:
            tag = f"  💀 #{i+1} WORST→"
        else:
            tag = f"     #{i+1}      "
        lines.append(
            f"{tag} D{r['delta']} · {r['dte']}DTE · TP{r['tp_pct']}% · SL{r['sl_pct']}%"
            f"  |  P&L ${r['total_pnl']:+,.0f}  |  WinRate {r['win_rate']*100:.0f}%"
            f"  |  {r['trades']} trades  |  avg ${r.get('avg_pnl', 0):+,.0f}/trade"
        )

    best_deltas = sorted(set(r["delta"] for r in valid_rows[:3]))
    best_dtes   = sorted(set(r["dte"]   for r in valid_rows[:3]))
    bad_deltas  = sorted(set(r["delta"] for r in valid_rows[-2:]))

    lines.extend([
        "",
        "PATTERNS LEARNED FROM REAL DATA:",
        f"  ✅ Top-performing delta range: {best_deltas}",
        f"  ✅ Top-performing DTE range  : {best_dtes} days",
        f"  ❌ Underperforming deltas    : {bad_deltas}",
        f"  🥇 Best single combo        : D{best['delta']} · {best['dte']}DTE"
        f" · TP{best['tp_pct']}% · SL{best['sl_pct']}%"
        f" → ${best['total_pnl']:+,.0f} profit, {best['win_rate']*100:.0f}% win rate",
        f"  💀 Worst single combo       : D{worst['delta']} · {worst['dte']}DTE"
        f" · TP{worst['tp_pct']}% · SL{worst['sl_pct']}%"
        f" → ${worst['total_pnl']:+,.0f}, {worst['win_rate']*100:.0f}% win rate",
        "",
        "MANDATORY INSTRUCTION — set your recommended_trade_config FROM THIS DATA:",
        f"  suggested_delta          : {best['delta']}  (historically best for this stock/period)",
        f"  suggested_dte            : {best['dte']}   (historically best for this stock/period)",
        f"  suggested_take_profit_pct: {best['tp_pct']}  (historically best exit target)",
        f"  suggested_stop_loss_pct  : {best['sl_pct']}  (historically best stop)",
        "  Only deviate from these if your directional analysis provides VERY strong",
        "  evidence that a different setup is clearly superior. Default = use the best combo.",
    ])

    if current_iv is not None:
        iv_pct = round(current_iv * 100, 1)
        if current_iv > 0.40:
            iv_label = "VERY HIGH — options are expensive. Buying calls/puts is costly. Consider selling."
        elif current_iv > 0.28:
            iv_label = "ELEVATED — options moderately expensive. Be selective on buying premium."
        elif current_iv > 0.16:
            iv_label = "NORMAL — balanced environment for buying or selling options."
        else:
            iv_label = "LOW — options are cheap. Good environment for buying calls/puts."
        lines.extend([
            "",
            f"CURRENT IMPLIED VOLATILITY: {iv_pct}%  →  {iv_label}",
        ])

    lines.append("=" * 70)
    return "\n".join(lines) + "\n"


def _build_regime_section(feature_packet: dict, calibration_summary: dict) -> str:
    """Build market regime intelligence section for the Gemini prompt."""
    trend    = feature_packet.get("trend", {}) or {}
    momentum = feature_packet.get("momentum", {}) or {}
    vol      = feature_packet.get("volatility", {}) or {}
    returns  = feature_packet.get("returns", {}) or {}

    regime     = trend.get("trend_regime", "sideways")
    rsi        = momentum.get("RSI_14")
    macd_h     = momentum.get("MACD_histogram")
    vol_regime = vol.get("volatility_regime", "medium")
    ann_vol    = vol.get("annualized_volatility_pct")

    lines = [
        "",
        "MARKET REGIME INTELLIGENCE (computed deterministically from price data):",
    ]

    # Trend regime
    if regime == "bullish":
        lines.append("  Trend Regime:     BULLISH — price above key moving averages, upward momentum")
    elif regime == "bearish":
        lines.append("  Trend Regime:     BEARISH — price below key moving averages, downward momentum")
    else:
        lines.append("  Trend Regime:     SIDEWAYS — no clear directional bias")

    # RSI zone
    if rsi is not None:
        if rsi > 75:
            lines.append(f"  RSI Zone:         EXTREME OVERBOUGHT ({rsi:.1f}) — high reversal risk if at 2yr high with MACD diverging")
        elif rsi > 60:
            lines.append(f"  RSI Zone:         OVERBOUGHT-ISH ({rsi:.1f}) — momentum still strong, not exhausted")
        elif rsi < 25:
            lines.append(f"  RSI Zone:         EXTREME OVERSOLD ({rsi:.1f}) — potential bounce but bearish momentum")
        elif rsi < 40:
            lines.append(f"  RSI Zone:         OVERSOLD ({rsi:.1f}) — bearish momentum, SELL is valid")
        else:
            lines.append(f"  RSI Zone:         NEUTRAL ({rsi:.1f}) — no strong momentum signal")

    # MACD momentum
    if macd_h is not None:
        if macd_h > 0:
            lines.append(f"  MACD Momentum:    ACCELERATING UP (histogram={macd_h:+.4f}) — bullish")
        elif macd_h < 0:
            lines.append(f"  MACD Momentum:    DECELERATING / DOWN (histogram={macd_h:+.4f}) — bearish")
        else:
            lines.append(f"  MACD Momentum:    FLAT — no directional momentum signal")

    # Volatility regime
    if vol_regime == "high":
        lines.append(f"  Volatility:       HIGH VOLATILITY REGIME — predictions are less reliable, widen uncertainty")
    elif vol_regime == "low":
        lines.append(f"  Volatility:       LOW VOLATILITY REGIME — trending moves are more reliable when they occur")
    else:
        lines.append(f"  Volatility:       NORMAL VOLATILITY — standard prediction reliability")

    # Annualized vol
    if ann_vol:
        _vol_label = "HIGH-RISK stock" if ann_vol > 50 else "MODERATE stock" if ann_vol > 25 else "LOW-VOLATILITY stock"
        lines.append(f"  Annualized Vol:   {ann_vol:.1f}% — {_vol_label}")

    # Phase 8 — ADX trend strength
    adx_val    = trend.get("ADX_14")
    adx_regime = trend.get("adx_regime", "unknown")
    if adx_val is not None:
        if adx_val < 20:
            lines.append(f"  ADX Trend Strength: CHOPPY MARKET ({adx_val:.1f} < 20) — market is ranging, technical signals are unreliable. Lower confidence.")
        elif adx_val > 25:
            lines.append(f"  ADX Trend Strength: STRONG TREND ({adx_val:.1f} > 25) — trending market, directional signals are reliable.")
        else:
            lines.append(f"  ADX Trend Strength: WEAK TREND ({adx_val:.1f}) — moderate trend, use caution.")

    # Phase 10 — RSI divergence
    rsi_div = trend.get("rsi_divergence", "NONE")
    if rsi_div == "BULLISH_DIVERGENCE":
        lines.append("  RSI Divergence:   BULLISH DIVERGENCE DETECTED — price made lower low but RSI made higher low. Strong reversal UP signal. Weight heavily toward BUY.")
    elif rsi_div == "BEARISH_DIVERGENCE":
        lines.append("  RSI Divergence:   BEARISH DIVERGENCE DETECTED — price made higher high but RSI made lower high. Strong reversal DOWN signal. Weight heavily toward SELL.")
    else:
        lines.append("  RSI Divergence:   None detected — no divergence signal.")

    # Item #6 ("adapt methodology per regime") -- ground the qualitative
    # regime read above in this project's own real, measured track record
    # for that exact regime, not just a generic platitude.
    try:
        from segment_reliability import regime_reliability_note
        _regime_note = regime_reliability_note(regime, adx_regime)
        if _regime_note:
            lines.append(_regime_note.rstrip("\n"))
    except Exception:
        pass

    # Combined regime signal
    if regime == "bullish" and rsi and rsi > 50 and macd_h and macd_h > 0:
        lines.append("  REGIME VERDICT:   STRONG BULL — all 3 regime signals agree -> BUY bias")
    elif regime == "bearish" and rsi and rsi < 50 and macd_h and macd_h < 0:
        lines.append("  REGIME VERDICT:   STRONG BEAR — all 3 regime signals agree -> SELL bias")
    elif regime == "bullish":
        lines.append("  REGIME VERDICT:   MODERATE BULL — trend bullish but momentum mixed -> lean BUY")
    elif regime == "bearish":
        lines.append("  REGIME VERDICT:   MODERATE BEAR — trend bearish but momentum mixed -> lean SELL")
    else:
        lines.append("  REGIME VERDICT:   NEUTRAL — no strong directional bias -> use other signals")

    lines.append("")
    return "\n".join(lines) + "\n"


def _build_gemini_prompt(
    normalized_input: dict,
    feature_packet: dict,
    calibration_summary: dict,
    signal_scores: dict = None,
    earnings_warning: str = "",
    market_movers_context: str = "",
) -> str:
    fp_json  = json.dumps(feature_packet, indent=2, default=str)
    cal_json = json.dumps(calibration_summary, indent=2, default=str)
    signal_scores_for_prompt = signal_scores or {}
    horizon_days = int(normalized_input.get("decision_horizon_days") or 30)

    # Build options strategy context section (injected near top of prompt)
    _opts_section = _build_options_context_section(
        normalized_input.get("options_params") or {}, horizon_days
    )

    # Build TT Historical Options Intelligence section (real backtest data from context period)
    _tt_ctx_section = _build_tt_context_section(normalized_input)

    # Build market regime intelligence section (deterministic from feature packet)
    _regime_section = _build_regime_section(feature_packet, calibration_summary)

    # Build put/call ratio section (Phase 5)
    _pc_data = calibration_summary.get("put_call_data", {}) or {}
    if _pc_data.get("available"):
        _pc_section = (
            "\n═══ PUT/CALL RATIO — MARKET POSITIONING SENTIMENT ═══\n"
            f"{_pc_data['note']}\n"
            f"Sentiment: {_pc_data.get('sentiment', 'UNKNOWN')}\n"
            f"Expiration used: {_pc_data.get('expiration_used', 'N/A')}\n"
            "This reflects real money positioning in the options market.\n"
            "═══════════════════════════════════════════════════════\n"
        )
    else:
        _pc_section = (
            "\n═══ PUT/CALL RATIO — MARKET POSITIONING SENTIMENT ═══\n"
            "Put/Call data unavailable for this symbol\n"
            "Sentiment: UNKNOWN\n"
            "═══════════════════════════════════════════════════════\n"
        )

    # Build index/ETF context section for SPY/SPX/QQQ/IWM
    _sym_upper = str(normalized_input.get("symbol") or "").upper().strip()
    _INDEX_ETF_MAP = {
        "SPY":  ("S&P 500 ETF (SPDR)", "tracks 500 largest US companies by market cap"),
        "SPX":  ("S&P 500 Index",       "the underlying index itself — cash-settled options"),
        "QQQ":  ("NASDAQ-100 ETF",      "tracks 100 largest non-financial NASDAQ companies, tech-heavy"),
        "IWM":  ("Russell 2000 ETF",    "tracks 2000 small-cap US companies"),
        "VIX":  ("CBOE Volatility Index","measures market fear — moves inversely to SPY usually"),
        "GLD":  ("Gold ETF",            "tracks gold price — safe haven asset"),
        "TLT":  ("20+ Year Treasury ETF","tracks long-term US government bonds"),
        "SQQQ": ("3x Short NASDAQ ETF", "inverse leveraged NASDAQ — extremely volatile"),
        "TQQQ": ("3x Long NASDAQ ETF",  "leveraged NASDAQ — extremely volatile"),
    }
    # Compute thresholds BEFORE _idx_section so buy_thr/sell_thr are available in the SPX/SPY block
    _expected_range_pct = (feature_packet.get("return_magnitude_formula") or {}).get("expected_range_pct")
    buy_thr, sell_thr = _get_horizon_thresholds(horizon_days, _sym_upper, _expected_range_pct)

    _is_index = _sym_upper in _INDEX_ETF_MAP
    _idx_section = ""
    if _is_index:
        _idx_name, _idx_desc = _INDEX_ETF_MAP[_sym_upper]
        _spy_spx = _sym_upper in ("SPY", "SPX")
        _idx_section = (
            f"\nSYMBOL CONTEXT — INDEX/ETF (not a single stock):\n"
            f"  Symbol: {_sym_upper} = {_idx_name}\n"
            f"  What it is: {_idx_desc}\n"
        )
        if _spy_spx:
            _idx_section += (
                f"  KEY BEHAVIORS FOR {_sym_upper}:\n"
                f"  - Historically trends UPWARD over 1-year+ horizons (long-run upward bias)\n"
                f"  - For 1-month (30-day) horizon: {_sym_upper} is POSITIVE in ~67-75% of all 30-day windows historically\n"
                f"  - This means: when signals are NEUTRAL or MIXED, the correct call is BUY — not SELL, not HOLD\n"
                f"  - Corrections rarely exceed -10% in a single month without a major macro shock\n"
                f"  - SELL signals must be backed by VERY strong momentum reversal (RSI < 38, MACD negative, trend bearish, r20d < -3%)\n"
                f"  - Neutral RSI (40-60) + flat MACD → BUY — do NOT default to SELL or HOLD\n"
                f"  - Slightly negative MACD histogram alone is NOT sufficient for SELL on a 30-day horizon\n"
                f"  - Price slightly below SMA20 alone is NOT sufficient for SELL — need SMA50 breach too\n"
                f"\n  ABSOLUTE RULE — {_sym_upper} HOLD IS BANNED:\n"
                f"  - HOLD IS FORBIDDEN for {_sym_upper}. Output BUY or SELL ONLY.\n"
                f"  - Any positive predicted_return_pct (even +0.1%) → decision MUST be BUY\n"
                f"  - Any negative predicted_return_pct (even -0.1%) → decision MUST be SELL\n"
                f"  - When uncertain for 30-day horizon → predict small POSITIVE return (e.g., +1.2%) → BUY\n"
                f"  - SELL on 30-day horizon requires: RSI < 38 AND MACD < 0 AND trend = 'bearish' AND r20d < -3%\n"
                f"  - Missing any one of those 4 conditions → predict a small positive return → BUY\n"
                f"  - The system guardrail will override any HOLD to BUY/SELL — so HOLD is wasted output\n"
            )
        _idx_section += "\n"

    # Compute actual data window description from feature packet (never hardcode)
    _n_bars_fp    = int(feature_packet.get("n_bars", 0) or 0)
    _ctx_start_fp = feature_packet.get("effective_ctx_start") or feature_packet.get("ctx_start") or "unknown"
    _years_fp     = round(_n_bars_fp / 252, 1) if _n_bars_fp else 0
    _data_window  = f"{_n_bars_fp} bars (~{_years_fp} years, from {_ctx_start_fp})"
    inp_json = json.dumps({
        "symbol":                        normalized_input.get("symbol"),
        "benchmark":                     normalized_input.get("benchmark"),
        "price_basis":                   normalized_input.get("price_basis"),
        "initial_capital":               normalized_input.get("initial_capital"),
        "requested_ctx_start":           normalized_input.get("historical_context_start_date"),
        "effective_ctx_start":           feature_packet.get("effective_ctx_start") or normalized_input.get("historical_context_start_date"),
        "effective_origin_date":         normalized_input.get("prediction_origin_date"),
        "target_date":                   normalized_input.get("target_date"),
        "horizon_days":                  horizon_days,
        "buy_threshold_pct":             buy_thr,
        "sell_threshold_pct":            sell_thr,
    }, indent=2)

    # Build failure category note for prompt
    hold_rate         = calibration_summary.get("hold_rate_pct", 0) or 0
    top_failure       = calibration_summary.get("top_failure_reason", "NONE") or "NONE"
    recent_top_fail   = calibration_summary.get("recent_top_failure", "NONE") or "NONE"
    hold_warning      = calibration_summary.get("hold_rate_warning", "") or ""
    over_hold_n       = calibration_summary.get("over_hold_count", 0) or 0
    false_buy_n       = calibration_summary.get("false_buy_count", 0) or 0
    false_sell_n      = calibration_summary.get("false_sell_count", 0) or 0
    rec_false_sell_n  = calibration_summary.get("recent_30_false_sell", 0) or 0
    rec_false_buy_n   = calibration_summary.get("recent_30_false_buy", 0) or 0
    rec_over_hold_n   = calibration_summary.get("recent_30_over_hold", 0) or 0
    match_pct         = calibration_summary.get("decision_match_pct", 0) or 0

    # Use recent failure pattern when it diverges from all-time (recent is more actionable)
    _active_failure = recent_top_fail if recent_top_fail not in ("NONE", "") else top_failure

    failure_guidance = ""
    if _active_failure == "FALSE_SELL":
        failure_guidance = (
            f"CRITICAL — FALSE_SELL is the dominant recent failure "
            f"({rec_false_sell_n} of last 30 runs: predicted SELL but market rose). "
            f"All-time: {false_sell_n} false-SELL vs {false_buy_n} false-BUY. "
            "You are SYSTEMATICALLY TOO BEARISH — your SELL threshold is too low. "
            "\n  HARD RULE for SPY/SPX/QQQ on 30-day horizon — SELL requires ALL FOUR: "
            "RSI < 38 AND MACD histogram < 0 AND trend = 'bearish' AND r20d < -3%. "
            "Missing any single condition → output BUY with a small positive return. "
            "\n  HARD RULE for any symbol on ANY horizon: "
            "Neutral RSI (40-60) + flat MACD → BUY. Slightly negative MACD alone → BUY. "
            "Price below SMA20 alone (but above SMA50) → BUY. "
            "\n  When uncertain → BUY. The base rate for 30-day SPY/SPX windows is 67-75% positive. "
            "Your SELL prediction must overcome that base rate with STRONG evidence."
        )
    elif _active_failure == "FALSE_BUY":
        failure_guidance = (
            f"CAUTION — FALSE_BUY occurred {rec_false_buy_n} times recently ({false_buy_n} all-time). "
            "You predicted BUY but market fell. Add reversal_risk check before committing BUY. "
            "If price is near resistance AND RSI > 70, downgrade to a smaller positive return. "
            "Check for bearish divergence (price rises but RSI falls) before finalizing BUY."
        )
    elif _active_failure == "OVER_HOLD":
        _sell_bias_add = ""
        if false_sell_n > false_buy_n * 2:
            _sell_bias_add = (
                f" SECONDARY ISSUE: When you do commit, you skew SELL: {false_sell_n} false-SELL "
                f"vs {false_buy_n} false-BUY all-time. When committing from HOLD, lean BUY for indices "
                "unless ALL FOUR bearish conditions are met (RSI<38, MACD<0, trend=bearish, r20d<-3%)."
            )
        failure_guidance = (
            f"CRITICAL — OVER_HOLD is the top failure ({rec_over_hold_n} recent, {over_hold_n} all-time). "
            "You have been refusing to commit to BUY/SELL when indicators were clear. "
            "When trend + RSI + MACD all agree, COMMIT to BUY or SELL — do not hide in HOLD."
            + _sell_bias_add
        )
    elif top_failure == "TREND_REVERSAL_MISSED":
        failure_guidance = (
            "CAUTION — Trend reversals were missed. When RSI diverges from price trend direction, "
            "this often signals an impending reversal. Weight reversal_signals heavily."
        )

    # Phase 1 — consensus mode prepend block
    _consensus_mode = calibration_summary.get("consensus_mode", "")
    if _consensus_mode == "devils_advocate":
        _consensus_prepend = (
            "CONSENSUS MODE — DEVIL'S ADVOCATE ANALYSIS:\n"
            "Before reaching your conclusion, you MUST first argue the OPPOSITE case as strongly as possible.\n"
            "List every reason the opposite direction could be correct. Only after doing that, weigh both sides and decide.\n\n"
        )
    elif _consensus_mode == "pure_technical":
        _consensus_prepend = (
            "CONSENSUS MODE — PURE TECHNICAL ANALYSIS:\n"
            "Ignore all narrative context and qualitative factors. Base your decision ONLY on the numerical technical indicators: "
            "RSI, MACD, Bollinger Bands, SMA alignment, ATR, volume, and return percentages. No story, just numbers.\n\n"
        )
    elif _consensus_mode == "bull_round1":
        _consensus_prepend = (
            "DEBATE MODE — BULL ANALYST, ROUND 1:\n"
            "You are the Bull analyst in a structured debate (Research Expansion Program Component 5, "
            "inspired by TradingAgents' multi-round researcher debate). Argue ONLY the case for BUY/upside, "
            "as strongly as the real evidence supports. Do not hedge toward SELL or HOLD. A separate Bear "
            "analyst is independently building the opposing case; you will get to respond to their specific "
            "argument in round 2. Still return the required JSON with your honest predicted_return_pct, "
            "confidence_score, etc. -- argue the bull case, but do not fabricate a BUY decision if the "
            "numbers genuinely don't support any upside at all.\n\n"
        )
    elif _consensus_mode == "bear_round1":
        _consensus_prepend = (
            "DEBATE MODE — BEAR ANALYST, ROUND 1:\n"
            "You are the Bear analyst in a structured debate (Research Expansion Program Component 5, "
            "inspired by TradingAgents' multi-round researcher debate). Argue ONLY the case for SELL/downside, "
            "as strongly as the real evidence supports. Do not hedge toward BUY or HOLD. A separate Bull "
            "analyst is independently building the opposing case; you will get to respond to their specific "
            "argument in round 2. Still return the required JSON with your honest predicted_return_pct, "
            "confidence_score, etc. -- argue the bear case, but do not fabricate a SELL decision if the "
            "numbers genuinely don't support any downside at all.\n\n"
        )
    elif _consensus_mode == "bull_round2":
        _consensus_prepend = (
            "DEBATE MODE — BULL ANALYST, ROUND 2 (REBUTTAL):\n"
            "You argued the bull case in round 1. Below is the Bear analyst's round-1 argument. You MUST "
            "respond to their SPECIFIC points, not generic counterarguments -- name which of their claims "
            "you're rebutting and why, using the actual data. If their argument genuinely changes your view, "
            "say so and adjust; conviction without engaging their real points is not a valid rebuttal.\n\n"
            f"BEAR'S ROUND-1 ARGUMENT TO RESPOND TO:\n{calibration_summary.get('opponent_argument', '(not provided)')}\n\n"
        )
    elif _consensus_mode == "bear_round2":
        _consensus_prepend = (
            "DEBATE MODE — BEAR ANALYST, ROUND 2 (REBUTTAL):\n"
            "You argued the bear case in round 1. Below is the Bull analyst's round-1 argument. You MUST "
            "respond to their SPECIFIC points, not generic counterarguments -- name which of their claims "
            "you're rebutting and why, using the actual data. If their argument genuinely changes your view, "
            "say so and adjust; conviction without engaging their real points is not a valid rebuttal.\n\n"
            f"BULL'S ROUND-1 ARGUMENT TO RESPOND TO:\n{calibration_summary.get('opponent_argument', '(not provided)')}\n\n"
        )
    else:
        _consensus_prepend = ""

    # Phase 2 — chain-of-thought block (inserted before JSON output instructions)
    _cot_block = """
MANDATORY CHAIN-OF-THOUGHT REASONING — Answer these 8 questions IN ORDER before giving your JSON:

STEP 1 — TREND: Is the primary trend BULLISH, BEARISH, or NEUTRAL? (SMA20 vs SMA50, price vs both MAs)
STEP 2 — MOMENTUM: Is momentum ACCELERATING or DECELERATING? (MACD histogram direction, RSI slope)
STEP 3 — VOLATILITY: Is volatility EXPANDING (risky, unpredictable) or CONTRACTING (ready to move)?
STEP 4 — MOVING AVERAGES: Is price ABOVE or BELOW SMA20 and SMA50? Are the MAs aligned in same direction?
STEP 5 — CALIBRATION HISTORY: What does this symbol's historical failure pattern tell you to watch out for?
STEP 6 — OPTIONS LEARNING: What did the Context-Period backtests show worked best on this stock historically?
STEP 7 — BULL CASE SCORE: Rate the bull case from 0 to 10 based purely on the data above.
STEP 8 — BEAR CASE SCORE: Rate the bear case from 0 to 10 based purely on the data above.

DECISION RULE: Whichever score (bull or bear) is HIGHER becomes your final decision direction.
If scores are equal, lean BUY (upward market bias).

Now provide your complete JSON response including chain_of_thought field with your answers to the 8 steps above.
"""

    _earnings_block = (
        f"\n{'='*70}\n"
        f"⚠️  {earnings_warning}\n"
        f"{'='*70}\n"
    ) if earnings_warning else ""

    return f"""{_consensus_prepend}{_earnings_block}You are a financial trading agent for a walk-forward backtesting system.

▶▶▶ RULE #0 — HOLD IS BANNED ◀◀◀
You MUST output BUY or SELL. HOLD is FORBIDDEN in almost all cases.
- predicted_return_pct > 0 (even +0.01%)  → decision MUST be BUY
- predicted_return_pct < 0 (even -0.01%)  → decision MUST be SELL
- predicted_return_pct = exactly 0.00%    → output BUY (market has upward long-run bias)
- HOLD is only valid if you genuinely cannot determine whether return will be positive or negative
  AND signals are perfectly 50/50 AND RSI is exactly 50. This is an edge case, not a default.
- The system will automatically override any HOLD based on the sign of your predicted_return_pct.
  So output HOLD only when you truly have zero directional conviction.
- "I am uncertain" → still BUY or SELL. Choose the more likely direction and commit.
- For SPX/SPY/QQQ: historical positive rate is 75%. When uncertain → BUY.

YOUR TWO JOBS:
1. DIRECTIONAL PREDICTION: Predict whether the stock will go UP (BUY) or DOWN (SELL) over the
   next {horizon_days} days, with a specific predicted_return_pct and confidence_score.
   OUTPUT BUY OR SELL — NOT HOLD. HOLD = FAILURE.
2. COMPLETE TRADE CONFIGURATION: When options params are provided, select a COMPLETE trade setup — not just
   direction. In recommended_trade_config, output a SPECIFIC action (Buy Call/Put/Sell Call/Put), a SPECIFIC
   delta integer, a SPECIFIC DTE integer, and a SPECIFIC quantity (1-10 contracts). The backtester will run
   with your exact configuration and show agent P&L vs backtester P&L for comparison.

AGENT SIZING RULES (when options params are provided):
- confidence ≥ 70 AND trend strong → suggest delta 35-50, quantity 4-7 (high conviction)
- confidence 50-69 → suggest delta 20-35, quantity 2-4 (moderate conviction)
- confidence < 50 → suggest delta 10-25, quantity 1-2 (low conviction, OTM lottery)
- DTE must be ≥ 2× the expected move time (don't suggest DTE=5 if you expect the move in 10 days)

STRICT RULES:
1. Analyze ONLY the structured data provided below.
2. Do NOT invent prices, news events, earnings, or external facts not in the data.
3. NOT investment advice — this is a model prediction for validation/research only.
4. Return ONLY valid JSON — no text before or after the JSON.
5. The target_date price is UNKNOWN to you — do NOT reference any price after the origin date.
6. Do NOT use calibration accuracy stats to fake a better prediction. Use them to avoid known failure patterns.
7. HOLD IS BANNED — if your predicted_return_pct is positive, your decision MUST be BUY.

IMPORTANT — REVERSAL CAUTION (NARROW SCOPE):
This applies ONLY when ALL THREE are simultaneously true:
  1. RSI is EXTREME oversold (< 28, not just < 35)
  2. Price is explicitly near a major support level (near_support = true)
  3. reversal_risk = "high"
In that specific case, output REVIEW (not SELL and not HOLD).
In ALL OTHER bearish cases — commit to SELL. Do NOT output HOLD.

STRONG BEARISH MANDATE — when ALL of these are true, you MUST predict SELL with a calculated negative return:
- trend_regime = "bearish"
- price below SMA20 AND SMA50
- MACD < 0 AND MACD_histogram < 0
- 20d return < -3% AND 60d return < -5%
Calculate the magnitude from data (do NOT use a fixed range): use the ATR-based formula below.
Do NOT default to HOLD when all four bearish conditions are met.

STRONG BULLISH MANDATE — when ALL of these are true, you MUST predict BUY with a calculated positive return:
- trend_regime = "bullish"
- price above SMA20 AND SMA50
- MACD > 0 AND MACD_histogram > 0
- 20d return > +3% AND 60d return > +5%
Calculate the magnitude from data (do NOT use a fixed range): use the ATR-based formula below.
Do NOT default to HOLD when all four bullish conditions are met.

LONG HORIZON GUIDANCE — when horizon_days > 60:
- For longer horizons, the expected_range_pct from the ATR formula is larger — use it directly.
- Do NOT floor at ±5% — let the ATR formula determine the magnitude. A low-volatility stock might legitimately predict ±3%.
- Strong directional signals + horizon > 60 days = direction_factor 0.55-0.75. Mixed signals = 0.25-0.40.
- Always use the formula result with full decimals (e.g., +6.83%, not +7.0%).

VERY LONG HORIZON GUIDANCE — when horizon_days > 90 AND symbol is SPY/SPX/QQQ/IWM:
- SPY/SPX/QQQ are positive in ~85% of any random 90-day window and ~90% of 180-day windows.
- Short-term bearish signals (MACD dip, price below SMA20) are NOISE for 90+ day predictions.
- For SPY/SPX/QQQ with horizon > 90 days, default to BUY: apply formula with direction_factor ≥ 0.35.
- SELL for SPY/SPX/QQQ (horizon > 90 days) requires ALL FIVE of these extreme conditions:
    1. trend_regime = "bearish" (not just "sideways")
    2. price BELOW SMA50 (not just SMA20) by > 2%
    3. MACD line < 0 AND histogram < 0
    4. RSI < 38 (deeply bearish momentum, not just < 50)
    5. 60d return < -8% (significant recent decline, not just -3%)
- If ANY of those 5 conditions is missing → predict BUY for SPY/SPX/QQQ at 90+ day horizon.
- Calibration confirmed: FALSE_SELL (predicting negative for indices over long horizons) is the #1 accuracy killer.
- Short-term MACD negative + RSI 45-50 on SPY does NOT justify SELL for a 6-7 month horizon.

DECISION QUALITY — BUY OR SELL ONLY:
The system currently has a {hold_rate:.0f}% HOLD rate — this is a CRITICAL FAILURE.
HOLD IS ELIMINATED. You MUST output BUY or SELL 99%+ of the time.

DECISION RULE — SIMPLE AND ABSOLUTE:
- predicted_return_pct > 0  →  decision = "BUY"   (no exceptions)
- predicted_return_pct < 0  →  decision = "SELL"  (no exceptions)
- predicted_return_pct = 0  →  decision = "BUY"   (upward market bias default)

HOLD IS ONLY VALID when ALL of these are SIMULTANEOUSLY true (extremely rare):
- You genuinely cannot distinguish positive vs negative (perfectly 50/50)
- RSI is exactly 44-56 AND MACD histogram is exactly 0 AND trend = "sideways"
- There are fewer than 30 bars of data (not enough history)
If any directional signal exists at all → commit to BUY or SELL.

OVERBOUGHT/OVERSOLD — TOPPY REVERSAL SELL PATTERN (valid SELL for ALL symbols):
When ALL THREE conditions are SIMULTANEOUSLY present, SELL IS STRONGLY VALID (even for indices):
  Condition 1: RSI > 75  (extreme overbought — momentum exhaustion zone)
  Condition 2: Price is near or above its 2-year historical high (extreme valuation, limited upside)
  Condition 3: MACD_histogram is DECLINING (price making highs but momentum weakening = bearish divergence)
This "toppy reversal" pattern historically predicts reversals. Output SELL with a negative predicted_return_pct.
If only 1 or 2 of these 3 conditions are met → default to BUY (do NOT SELL on partial signals).
If RSI > 75 alone (without conditions 2 and 3) → BUY with MODERATE return (momentum is strong, not exhausted).
RSI < 25 with bearish trend → SELL with moderate return prediction.

USE BUY when predicted_return_pct > 0 (simple rule — commit to a direction):
- Any positive bullish signal: trend up, RSI > 50, MACD > 0, price above SMA20 → BUY
- Even with mixed signals: if more bullish than bearish → positive return → BUY
- For SPX/SPY/QQQ when signals are neutral → BUY (75% historical positive rate)

USE SELL when predicted_return_pct < 0:
- For individual stocks (not SPY/SPX/QQQ): any negative bearish signal → SELL
- For SPY/SPX/QQQ with horizon < 30 days: trend down + RSI < 45 + MACD < 0 → SELL is valid
- For SPY/SPX/QQQ with horizon 30-90 days: need trend bearish + price below SMA50 + RSI < 42 + 20d return < -5%
- For SPY/SPX/QQQ with horizon > 90 days: need ALL FIVE extreme conditions (see VERY LONG HORIZON section above)
- 20d return < -3% AND trend = bearish → SELL for individual stocks (do NOT output HOLD)
- WARNING: Single bearish indicators (MACD < 0 or price below SMA20) do NOT justify SELL for index ETFs over 90+ days

RETURN MAGNITUDE — CALCULATE FROM DATA (never guess a round number):
Use this exact formula to derive your predicted_return_pct:
  Step 1: daily_vol_pct = ATR14 / current_price × 100
  Step 2: expected_range_pct = daily_vol_pct × sqrt(horizon_days)
  Step 3: direction_factor (based on signal strength):
           Strong signals (trend + RSI + MACD all aligned, |r20d| > 3%) → 0.55 to 0.75
           Moderate signals (2 of 3 aligned) → 0.30 to 0.50
           Weak signals (mixed, only 1 aligned) → 0.10 to 0.25
  Step 4: |predicted_return| = expected_range_pct × direction_factor
  Step 5: Apply sign (positive = BUY, negative = SELL)
  Step 6: Add the actual decimal digits from your calculation — do NOT round to .0 or .5

EXAMPLE CALCULATION (SPY, horizon=30):
  ATR14=12.4, price=741 → daily_vol=1.67%, sqrt(30)=5.48, expected_range=9.16%
  Moderate bullish signals → direction_factor=0.38 → |predicted_return|=9.16×0.38=3.48%
  Decision: BUY, predicted_return_pct=+3.48

ANTI-ANCHORING — CRITICAL RULE:
Do NOT output any of these stereotyped round values: ±2.5%, ±3.5%, ±5.5%, ±6.5%, ±8.5%, ±10.0%, ±12.0%.
If your calculation yields one of these, recalculate with the actual decimal output (e.g., 3.48% not 3.5%).
Every run has unique ATR, price, RSI, and momentum values — your output must reflect them.
Round numbers prove you are pattern-matching from the prompt instead of calculating from data.

Do NOT default to HOLD when:
- Trend regime is clearly bullish or bearish
- RSI signals momentum (>58 = bullish, <42 = bearish)
- MACD line AND histogram agree on direction
- 20d and 60d returns consistently agree
- reversal_risk is "low" (no overbought/oversold near S/R)

Decision thresholds for this prediction (NEAR-ZERO — any signal produces BUY or SELL):
- BUY if predicted_return_pct > 0 (even +0.1%)
- SELL if predicted_return_pct < 0 (even -0.1%)
- BUY if predicted_return_pct = exactly 0 (default to bullish)
- HOLD: NOT ALLOWED (the guardrail converts HOLD to BUY/SELL based on your predicted_return_pct anyway)

If ANY positive return is predicted → BUY. If ANY negative return is predicted → SELL. No exceptions.

CALIBRATION FAILURE CONTEXT (learn from these to avoid repeating the same mistakes):
- Current decision match rate: {match_pct}%
- Hold rate: {hold_rate}% {('(TOO HIGH — commit more)' if hold_rate > 45 else '')}
- Top failure reason (all-time): {top_failure} | Recent 30 runs: {recent_top_fail}
- Over-hold cases: {over_hold_n} | False-buy cases: {false_buy_n} | False-sell cases: {false_sell_n}
- Recent 30 runs — False-SELL: {rec_false_sell_n} | False-BUY: {rec_false_buy_n} | Over-HOLD: {rec_over_hold_n}
{f'- {hold_warning}' if hold_warning else ''}
{f'- {failure_guidance}' if failure_guidance else ''}

{_idx_section}{_opts_section}{_tt_ctx_section}{_regime_section}{_pc_section}
{_build_segment_reliability_section(calibration_summary)}{_build_nearest_cases_section(calibration_summary)}NORMALIZED INPUT:
{inp_json}

FEATURE PACKET (computed from real historical bars — no future data):
{fp_json}

CALIBRATION SUMMARY (full past performance — use to avoid known failure patterns):
{cal_json}

{_build_symbol_calibration_section(calibration_summary)}
DATA LIMITATIONS:
- Historical bars come from open-source market data provider (primary) → NASDAQ external → RapidAPI TradingView (plan-dependent)
- {_data_window} of price history available
- No real-time news or macro data
- Options chain live data: NOT available in historical context (would be future leakage for past dates)
{f'EARNINGS ALERT: {earnings_warning}' if earnings_warning else '- Earnings calendar: checked — no events detected in prediction window.'}
{market_movers_context if market_movers_context else '- Market movers: NOT included (historical prediction — live snapshot would be future leakage).'}

SIGNAL SCORES (deterministic, computed from feature packet — these are the objective indicators):
{json.dumps(signal_scores_for_prompt, indent=2)}

{_cot_block}
REQUIRED JSON RESPONSE (return ONLY this JSON, no other text):
{{
  "status": "SUCCESS",
  "chain_of_thought": "<compact, one short phrase per step, e.g. 'T:BULLISH M:ACCEL V:CONTRACT MA:ABOVE Cal:<1 phrase> Opt:<1 phrase> Bull:7 Bear:3' — NOT prose paragraphs>",
  "ai_provider": "gemini",
  "predicted_return_pct": <float, clamped to -20.0 to +20.0>,
  "confidence_score": <integer 0-100>,
  "risk_score": <integer 0-100>,
  "decision_threshold_used": {{"buy_threshold": {buy_thr}, "sell_threshold": {sell_thr}}},
  "bullish_score_assessment": <integer 0-100, your assessment of bullish evidence>,
  "bearish_score_assessment": <integer 0-100, your assessment of bearish evidence>,
  "narrative_dependency_score": <integer 0-100: how much does THIS call depend on narrative/sentiment/news-driven factors rather than pure price-technicals? 0 = purely technical (e.g. a broad index following its trend), 100 = the call hinges on story/sentiment/catalyst factors that technicals alone can't capture (e.g. a single volatile stock driven by news flow)>,
  "primary_signal": "<single most important indicator driving your prediction>",
  "trend_assessment": "<EXACTLY 1 sentence: trend regime + where price sits vs SMA20/50/200>",
  "momentum_assessment": "<EXACTLY 1 sentence: RSI value + MACD direction, building or exhausting>",
  "volatility_assessment": "<EXACTLY 1 sentence: ATR vs average, Bollinger expanding or contracting>",
  "benchmark_assessment": "<EXACTLY 1 sentence: outperforming or underperforming benchmark, by how much>",
  "bull_case": "<EXACTLY 1 sentence: price target + single strongest bullish catalyst>",
  "bear_case": "<EXACTLY 1 sentence: price level + single strongest bearish catalyst>",
  "main_reason": "<2-3 sentences total: the decision, the single strongest supporting reason, and the main risk that could invalidate it.>",
  "why_not_opposite_decision": "<EXACTLY 1 sentence: the single strongest signal that argued for the opposite call and why it was overruled>",
  "key_features_used": ["REQUIRED FIRST ENTRY: your return magnitude calculation — e.g. 'ATR14=12.4, price=741, daily_vol=1.67%, sqrt(30)=5.48, range=9.16%, direction_factor=0.38 → predicted=+3.48%'", "second most important feature with exact value", "third feature"],
  "data_limitations": ["list of 1-3 specific data gaps that could affect accuracy — be specific about what is missing and how it matters"],
  "options_strategy_assessment": "<REQUIRED if OPTIONS STRATEGY CONTEXT was provided above, else null. State: (1) Does current ATR support required move? (2) Is directional alignment FAVORABLE/NEUTRAL/UNFAVORABLE? (3) For short DTE (<=5 days): does ATR support enough single-day move? (4) One-sentence verdict on whether this position makes sense given current market.>",
  "user_strategy_evaluation": {{
    "verdict": "<REQUIRED if options params provided. GOOD / RISKY / NOT_RECOMMENDED / REVIEW. Evaluate the EXACT strategy the user entered (action, delta, DTE, qty, SL%, TP%). Null if no options.>",
    "issues": ["<specific issue with user strategy e.g. Delta 12 is far OTM needs very large fast move>", "<issue 2 if any>"],
    "strengths": ["<strength of user strategy if any e.g. DTE 30 gives adequate time>"],
    "assessment": "<3-4 sentences: Honestly evaluate user strategy. Name specific problematic params. Explain why it works or fails. Compare to what would be better.>"
  }},
  "recommended_trade_config": {{
    "action": "<REQUIRED if options params provided. YOUR best action from market view. Correct user if wrong direction. Exactly one of: Buy Call, Buy Put, Sell Call, Sell Put. Null if no options.>",
    "suggested_delta": "<REQUIRED if options. Your recommended delta integer. High confidence 35-50, medium 25-35, low 15-25. Fix user delta if too far OTM. Null if no options.>",
    "suggested_delta_range": "<Display range e.g. 25-35. Null if no options.>",
    "suggested_dte": "<REQUIRED if options. Your recommended DTE integer. Long enough for expected move. Increase if user DTE too short. Null if no options.>",
    "suggested_dte_range": "<Display range e.g. 25-35. Null if no options.>",
    "suggested_quantity": "<REQUIRED if options. Contracts 1-10 matching confidence and capital. Reduce if user qty too large. Null if no options.>",
    "suggested_take_profit_pct": "<Recommended TP% adjusted for realistic exit. Null if no options.>",
    "suggested_stop_loss_pct": "<Recommended SL% - widen if user SL too tight. Null if no options.>",
    "alignment_with_user_config": "<ALIGNED / PARTIALLY_ALIGNED / NOT_ALIGNED vs user input. Null if no options.>",
    "alignment_notes": "<2-3 sentences: which params agree, which to change and exactly why. If NOT_ALIGNED be very specific about what to fix. Null if no options.>"
  }},
  "needs_human_review": <true if confidence < 60 or strong reversal risk, else false>
}}"""


# ═══════════════════════════════════════════════════════════════════════════════
# JSON EXTRACTION HELPER
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_json(raw_text: str) -> str:
    """
    Extract clean JSON object from Gemini response.
    Handles thinking tags, markdown fences, preamble text.
    """
    import re
    # Remove <think>...</think> or <thinking>...</thinking> blocks
    raw_text = re.sub(r"<think(?:ing)?>\s*.*?\s*</think(?:ing)?>", "", raw_text, flags=re.DOTALL)
    # Find the outermost JSON object
    start = raw_text.find("{")
    end   = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw_text[start:end + 1].strip()
    return raw_text.strip()


def _repair_json(text: str) -> str:
    """
    Repair common Gemini JSON issues before parsing.

    Handles:
    - Truncated JSON (response cut off by token limit) — closes open strings/objects
    - Missing commas between JSON object fields ("Expecting ',' delimiter")
    - Literal newline/tab/control chars inside string values
    - Trailing commas before } or ]
    - Python literals True/False/None
    - Backslash before a literal control char (e.g. backslash+newline → \\n)
    """
    import re
    # Fix Python literals
    text = re.sub(r'\bTrue\b', 'true', text)
    text = re.sub(r'\bFalse\b', 'false', text)
    text = re.sub(r'\bNone\b', 'null', text)

    # Remove trailing commas before } or ]
    text = re.sub(r',(\s*[}\]])', r'\1', text)

    # ── PASS 1: State machine — escape literal control chars inside strings ──────
    # Also fixes \<control-char> sequences (e.g. backslash + literal newline)
    # which are invalid JSON escape sequences.
    result: list = []
    in_string   = False
    escape_next = False

    for ch in text:
        if escape_next:
            # Previous char was a backslash inside a string.
            # If the char after it is a raw control character, convert to valid escape.
            if ch == '\n':
                result.append('n')       # \<newline> → \n
            elif ch == '\r':
                result.append('r')       # \<CR>      → \r
            elif ch == '\t':
                result.append('t')       # \<tab>     → \t
            elif ord(ch) < 0x20:
                result.append(f'u{ord(ch):04x}')  # \<ctrl> → \uXXXX
            else:
                result.append(ch)        # normal escape (\", \\, \/, \n, etc.)
            escape_next = False
        elif ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
        elif ch == '"':
            in_string = not in_string
            result.append(ch)
        elif in_string and ch == '\n':
            result.append('\\n')
        elif in_string and ch == '\r':
            result.append('\\r')
        elif in_string and ch == '\t':
            result.append('\\t')
        elif in_string and ord(ch) < 0x20:
            result.append(f'\\u{ord(ch):04x}')
        else:
            result.append(ch)

    repaired = ''.join(result)

    # ── PASS 2: Fix missing commas between JSON fields ───────────────────────────
    # "Expecting ',' delimiter" most often means Gemini forgot a comma between
    # two key-value pairs, e.g.:
    #   "prediction_rationale": "long text"
    #   "confidence_score": 70          ← missing comma after the string value
    #
    # After Pass 1, all newlines inside strings are escaped (\n), so the regex
    # can safely match string boundaries without confusion.
    # Pattern: a JSON value (string / number / bool / null / } / ]) followed by
    # whitespace (newline) then a double-quote — insert a comma between them.
    repaired = re.sub(
        r'("(?:[^"\\]|\\.)*"'           # "string value"
        r'|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'  # number
        r'|\btrue\b|\bfalse\b|\bnull\b' # boolean / null
        r'|\}|\])'                       # closing brace/bracket
        r'(\s*\n\s*)'                    # whitespace including newline
        r'(?=")',                         # lookahead: next token starts with "
        r'\1,\2',
        repaired,
        flags=re.DOTALL,
    )

    # ── PASS 3: Close truncated JSON (response cut off by token limit) ───────────
    # If the JSON is incomplete (open string, unclosed objects/arrays), attempt
    # to close it so the parser can at least extract the fields that were returned.
    try:
        json.loads(repaired)
        return repaired  # already valid
    except Exception:
        pass

    # Close any open string literal first
    in_str = False
    esc    = False
    for ch in repaired:
        if esc:
            esc = False
        elif ch == '\\' and in_str:
            esc = True
        elif ch == '"':
            in_str = not in_str
    if in_str:
        repaired += '"'

    # Count unmatched { and [ to close them
    depth_brace  = 0
    depth_bracket = 0
    in_str2 = False
    esc2    = False
    for ch in repaired:
        if esc2:
            esc2 = False
        elif ch == '\\' and in_str2:
            esc2 = True
        elif ch == '"':
            in_str2 = not in_str2
        elif not in_str2:
            if ch == '{':
                depth_brace += 1
            elif ch == '}':
                depth_brace = max(0, depth_brace - 1)
            elif ch == '[':
                depth_bracket += 1
            elif ch == ']':
                depth_bracket = max(0, depth_bracket - 1)

    # Remove trailing commas before closing
    repaired = re.sub(r',\s*$', '', repaired.rstrip())
    repaired += ']' * depth_bracket + '}' * depth_brace

    return repaired


# ═══════════════════════════════════════════════════════════════════════════════
# GEMINI API CALL
# ═══════════════════════════════════════════════════════════════════════════════

def _recompute_price_fields(pred_return_pct: float, origin_price: float, initial_capital: float) -> Tuple[float, float, float, float]:
    """Derive (pred_return_pct, target, final_capital, total_pl) from a return %.

    Single source of truth for this formula — used both for a fresh Gemini call
    and to keep the technical-override path's numeric fields consistent with
    whatever decision it lands on (see _call_gemini_consensus).
    """
    pred_return  = max(_RETURN_CLAMP_MIN, min(_RETURN_CLAMP_MAX, pred_return_pct))
    pred_return  = round(pred_return, 4)
    pred_target  = round(origin_price * (1.0 + pred_return / 100.0), 4)
    pred_capital = round(initial_capital * (pred_target / origin_price), 4)
    pred_pl      = round(pred_capital - initial_capital, 4)
    return pred_return, pred_target, pred_capital, pred_pl


_CHART_VISION_PREFACE = (
    "Two chart images are attached before this text: a wide multi-month chart "
    "(long-term structure/pattern) and a shorter detail chart (recent price action, "
    "clearer candles). Use them as an additional, visual source of support/resistance "
    "and pattern context alongside the structured numeric data below; they do not "
    "replace it."
)


def _build_gemini_contents(prompt_content: str, chart_images: Optional[Dict[str, bytes]]):
    """Returns the exact `contents` value to pass to generate_content().

    chart_images=None/empty -> returns prompt_content UNCHANGED (a plain str) --
    this is what guarantees byte-identical behavior to the flag-off path today.
    Otherwise returns [wide_image, detail_image, preface_text, prompt_content],
    images first per Gemini's documented practice of putting image parts before
    the text that references them.
    """
    if not chart_images:
        return prompt_content

    from google.genai import types as genai_types
    return [
        genai_types.Part.from_bytes(data=chart_images["wide"], mime_type="image/png"),
        genai_types.Part.from_bytes(data=chart_images["detail"], mime_type="image/png"),
        _CHART_VISION_PREFACE,
        prompt_content,
    ]


# Chart-vision pilot runs showed 503 UNAVAILABLE / 504 DEADLINE_EXCEEDED failures
# occurring almost exclusively on vision-on calls (zero on an identical vision-off
# run in the same time window) -- these are Gemini's own transient overload
# signals ("high demand"), not request problems, so retrying is the correct
# response, unlike a 4xx ClientError (bad request/auth) which would just fail
# identically again. Two retries (3s, then 8s backoff) adds at most ~11s to a
# call that was already going to wait up to CHART_VISION_REQUEST_TIMEOUT_MS.
_GEMINI_TRANSIENT_RETRY_DELAYS_S = (3, 8)


def _generate_content_with_retry(client, **kwargs):
    """client.models.generate_content() wrapper that retries a transient
    google.genai.errors.ServerError (5xx) with backoff before giving up.

    Re-raises the last ServerError once retries are exhausted -- callers keep
    their existing try/except handling for a persistent outage unchanged.
    """
    from google.genai import errors as genai_errors
    last_exc: Optional[Exception] = None
    for _delay in (0,) + _GEMINI_TRANSIENT_RETRY_DELAYS_S:
        if _delay:
            time.sleep(_delay)
        try:
            return client.models.generate_content(**kwargs)
        except genai_errors.ServerError as exc:
            last_exc = exc
    raise last_exc


def _call_gemini(
    normalized_input: dict,
    feature_packet: dict,
    calibration_summary: dict,
    origin_price: float,
    initial_capital: float,
    earnings_warning: str = "",
    market_movers_context: str = "",
    chart_images: Optional[Dict[str, bytes]] = None,
) -> dict:
    """Call Gemini, validate response, recalculate numerics. Returns result dict."""
    t0 = time.time()

    if not _GEMINI_KEY:
        return {
            "status":            "FAILED",
            "gemini_used":       False,
            "error":             "GEMINI_API_KEY missing. Set GEMINI_API_KEY or GOOGLE_API_KEY in .env",
            "gemini_latency_ms": 0,
        }

    sig_scores     = _compute_signal_scores(feature_packet)
    prompt_content = _build_gemini_prompt(normalized_input, feature_packet, calibration_summary, signal_scores=sig_scores, earnings_warning=earnings_warning, market_movers_context=market_movers_context)
    prompt_hash    = hashlib.sha256(prompt_content.encode()).hexdigest()[:16]

    try:
        from google import genai
        from google.genai import types as genai_types

        _timeout_ms = CHART_VISION_REQUEST_TIMEOUT_MS if chart_images else GEMINI_REQUEST_TIMEOUT_MS
        client = genai.Client(
            api_key=_GEMINI_KEY,
            http_options=genai_types.HttpOptions(timeout=_timeout_ms),
        )

        # Phase 7 — Deep thinking enabled (budget=8000 lets Gemini reason internally
        # before answering, dramatically improving prediction quality). The
        # devils_advocate/pure_technical calls use a smaller budget for speed, but
        # it must stay > 0: some models (e.g. gemini-3.1-pro-preview) hard-reject
        # thinking_budget=0 with "Budget 0 is invalid. This model only works in
        # thinking mode." -- a 400 ClientError, not a disagreement, that was
        # silently killing 2 of the 3 consensus calls on every single request.
        _consensus_mode = (calibration_summary or {}).get("consensus_mode", "")
        _thinking_budget = 1024 if _consensus_mode in ("devils_advocate", "pure_technical") else 8000
        response = _generate_content_with_retry(
            client,
            model=GEMINI_MODEL,
            contents=_build_gemini_contents(prompt_content, chart_images),
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=16000,
                response_mime_type="application/json",
                thinking_config=genai_types.ThinkingConfig(thinking_budget=_thinking_budget),
            ),
        )

        gemini_latency_ms = round((time.time() - t0) * 1000, 0)
        raw_text = (response.text or "").strip()

        # Extract JSON from response (handles thinking tags, markdown fences, plain JSON)
        json_text = _extract_json(raw_text)

        # Try parsing; on failure attempt repair then retry once
        gemini_json = None
        _first_err  = None
        for _attempt, _candidate in enumerate([json_text, _repair_json(json_text)]):
            try:
                gemini_json = json.loads(_candidate)
                break
            except Exception as _e:
                if _attempt == 0:
                    _first_err = _e

        # Both attempts failed — make one automatic Gemini retry at temperature=0.15
        # Using 0.0 would produce the same broken response; 0.15 yields a different sample.
        if gemini_json is None:
            try:
                _retry_resp = _generate_content_with_retry(
                    client,
                    model=GEMINI_MODEL,
                    contents=_build_gemini_contents(prompt_content, chart_images),
                    config=genai_types.GenerateContentConfig(
                        temperature=0.15,
                        max_output_tokens=8192,
                        response_mime_type="application/json",
                        thinking_config=genai_types.ThinkingConfig(thinking_budget=1024),
                    ),
                )
                _retry_raw  = (_retry_resp.text or "").strip()
                _retry_text = _extract_json(_retry_raw)
                for _c2 in [_retry_text, _repair_json(_retry_text)]:
                    try:
                        gemini_json = json.loads(_c2)
                        break
                    except Exception:
                        pass
            except Exception:
                pass

        if gemini_json is None:
            return {
                "status":            "FAILED",
                "gemini_used":       True,
                "error":             f"Gemini JSON parse failed: {_first_err}",
                "gemini_raw_text":   raw_text[:500],
                "gemini_latency_ms": gemini_latency_ms,
            }

        # Recalculate numerics from Gemini's predicted_return_pct
        pred_return, pred_target, pred_capital, pred_pl = _recompute_price_fields(
            float(gemini_json.get("predicted_return_pct") or 0.0), origin_price, initial_capital,
        )

        conf  = max(0, min(100, int(gemini_json.get("confidence_score") or 50)))
        risk  = max(0, min(100, int(gemini_json.get("risk_score") or 50)))
        dq    = min(100, int(feature_packet.get("data_quality_score", 70) or 70))

        # Research Expansion Program, Component 4 -- structured numeric scores
        # (not just the final decision) feeding the ML model as additional
        # features, per the hybrid LLM+quant research finding (LLM-generated
        # "formulaic alpha" signals as model inputs, not only a narrative
        # verdict). bullish/bearish_score_assessment were already in the
        # schema but never parsed before this -- wiring up existing unused
        # output instead of adding prompt complexity for two of the three.
        def _clamped_score(key: str) -> Optional[int]:
            val = gemini_json.get(key)
            if val is None:
                return None
            try:
                return max(0, min(100, int(val)))
            except (TypeError, ValueError):
                return None
        bull_conviction   = _clamped_score("bullish_score_assessment")
        bear_conviction   = _clamped_score("bearish_score_assessment")
        narrative_dep     = _clamped_score("narrative_dependency_score")
        h_days = int(normalized_input.get("decision_horizon_days") or 30)

        _rev_risk      = feature_packet.get("reversal_signals", {}).get("reversal_risk", "low")
        _rsi_val       = feature_packet.get("momentum", {}).get("RSI_14")
        _adx_val       = feature_packet.get("trend", {}).get("ADX_14")
        _trend_regime  = feature_packet.get("trend", {}).get("trend_regime", "")
        decision, decision_reason = _apply_guardrails(
            pred_return, conf, risk, dq,
            horizon_days=h_days,
            signal_scores=sig_scores,
            reversal_risk=_rev_risk,
            rsi=_rsi_val,
            symbol=str(normalized_input.get("symbol") or ""),
            adx=_adx_val,
            trend_regime=_trend_regime,
        )

        output_hash = hashlib.sha256(raw_text.encode()).hexdigest()[:16]

        return {
            "status":                   "SUCCESS",
            "gemini_used":              True,
            "ai_provider":              "gemini",
            "model_name":               GEMINI_MODEL,
            "gemini_latency_ms":        gemini_latency_ms,
            "prompt_hash":              prompt_hash,
            "gemini_output_hash":       output_hash,
            "predicted_return_pct":     pred_return,
            "predicted_target_price":   pred_target,
            "predicted_final_capital":  pred_capital,
            "predicted_total_pl":       pred_pl,
            "decision":                 decision,
            "decision_reason":          decision_reason,
            "confidence_score":         conf,
            "risk_score":               risk,
            "data_quality_score":       dq,
            "signal_scores":            sig_scores,
            "bull_conviction_score":    bull_conviction,
            "bear_conviction_score":    bear_conviction,
            "narrative_dependency_score": narrative_dep,
            "reasoning":                gemini_json.get("main_reason", ""),
            "trend_assessment":         gemini_json.get("trend_assessment", ""),
            "momentum_assessment":      gemini_json.get("momentum_assessment", ""),
            "volatility_assessment":    gemini_json.get("volatility_assessment", ""),
            "benchmark_assessment":     gemini_json.get("benchmark_assessment", ""),
            "bull_case":                gemini_json.get("bull_case", ""),
            "bear_case":                gemini_json.get("bear_case", ""),
            "why_not_opposite":         gemini_json.get("why_not_opposite_decision", ""),
            "key_features_used":            gemini_json.get("key_features_used", []),
            "data_limitations":             gemini_json.get("data_limitations", []),
            "options_strategy_assessment":  gemini_json.get("options_strategy_assessment") or "",
            "recommended_trade_config":     gemini_json.get("recommended_trade_config") or {},
            "needs_human_review":           bool(gemini_json.get("needs_human_review", False)),
            "chain_of_thought":             gemini_json.get("chain_of_thought", ""),
            "gemini_raw_json":              gemini_json,
        }

    except Exception as exc:
        gemini_latency_ms = round((time.time() - t0) * 1000, 0)
        return {
            "status":            "FAILED",
            "gemini_used":       True,
            "error":             f"Gemini API error: {type(exc).__name__}: {exc}",
            "gemini_latency_ms": gemini_latency_ms,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — TRIPLE GEMINI CONSENSUS ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def _tally_consensus_votes(results: List[dict], call_labels: List[str], fallback_fn) -> dict:
    """Shared majority-vote tallying, used by both _call_gemini_consensus
    (3 independent framings) and _call_gemini_debate_consensus (Component 5 --
    the final 3-way tally among bull-round2/bear-round2/pure-technical, after
    the debate rounds have run). Extracted so both consensus mechanisms share
    identical, already-tested voting/confidence semantics rather than two
    subtly-different copies drifting apart.

    fallback_fn() is called (and its result annotated/returned) only if EVERY
    result failed outright -- one direct retry rather than giving up with
    zero information. Takes no arguments; callers close over whatever a
    direct single-call fallback needs.
    """
    # All successful calls, regardless of decision — the true "how many calls
    # actually completed" count. A HOLD/REVIEW result is a real, successful call;
    # it must not vanish from this count just because it can't win the BUY/SELL vote.
    attempted   = [(i, r) for i, r in enumerate(results) if r.get("status") == "SUCCESS"]
    total_attempted = len(attempted)

    # Directional (BUY/SELL) subset only, for the majority vote itself.
    successful  = [(i, r) for i, r in attempted if r.get("decision") in ("BUY", "SELL")]
    hold_count  = total_attempted - len(successful)

    if total_attempted == 0:
        # True failure — every call errored/failed to parse. Fall back to a single
        # direct call (no consensus possible).
        #
        # Hard-timeout-protected, same as the 3 consensus calls themselves
        # (_CONSENSUS_CALL_HARD_TIMEOUT_S) -- confirmed live this session that
        # without this, a fallback call reached only when ALL 3 consensus
        # calls already failed/timed out could itself hang past 9 minutes
        # with no bound at all, since fallback_fn() previously called
        # _call_gemini directly, bypassing the ThreadPoolExecutor wrapper
        # entirely and relying solely on GEMINI_REQUEST_TIMEOUT_MS's broken
        # per-chunk (not total-duration) httpx timeout.
        _fb_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        _fb_future = _fb_executor.submit(fallback_fn)
        try:
            fallback = _fb_future.result(timeout=_CONSENSUS_CALL_HARD_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            fallback = {
                "status": "FAILED", "decision": "REVIEW", "gemini_used": False,
                "error": f"fallback call exceeded the {_CONSENSUS_CALL_HARD_TIMEOUT_S:.0f}s hard timeout -- abandoned",
            }
        except Exception as exc:
            fallback = {"status": "FAILED", "decision": "REVIEW", "gemini_used": False,
                        "error": f"{type(exc).__name__}: {exc}"}
        _fb_executor.shutdown(wait=False)
        fallback["consensus_votes"]      = {"BUY": 0, "SELL": 0, "HOLD": 0}
        fallback["consensus_confidence"] = "LOW"
        fallback["consensus_calls"]      = []
        return fallback

    if not successful:
        # Every successful call landed on HOLD/REVIEW — a real, low-confidence
        # outcome in its own right. Don't burn another Gemini call chasing a
        # BUY/SELL decision none of the attempts actually reached.
        chosen_result = dict(attempted[0][1])
        chosen_result["consensus_votes"]      = {"BUY": 0, "SELL": 0, "HOLD": hold_count}
        chosen_result["consensus_confidence"] = "LOW"
        chosen_result["consensus_calls"]      = [
            {"call": call_labels[i], "decision": r.get("decision", "FAILED"), "status": r.get("status", "FAILED")}
            for i, r in enumerate(results)
        ]
        return chosen_result

    # Count votes
    buy_count  = sum(1 for _, r in successful if r.get("decision") == "BUY")
    sell_count = sum(1 for _, r in successful if r.get("decision") == "SELL")

    n = len(results)

    # Majority-HOLD with a minority directional dissenter (e.g. 2 HOLD + 1 BUY)
    # -- a real majority preference for "don't trade this," not the genuine
    # 3-way noise the skip gate below exists for. This is the pattern that
    # actually fires in production (confirmed from real logged skips this
    # session, e.g. "Votes: {'BUY': 1, 'SELL': 0, 'HOLD': 2}") -- a true,
    # irreducible 1-BUY/1-SELL/1-HOLD split with no majority on anything
    # still falls through to the LOW branch below unaffected (hold_count==1
    # there, not >=2) -- see test_genuinely_mixed_low_confidence_still_skipped.
    if hold_count >= 2:
        hold_calls = [r for _, r in attempted if r.get("decision") not in ("BUY", "SELL")]
        chosen_result = dict(hold_calls[0]) if hold_calls else dict(attempted[0][1])
        chosen_result["decision"] = "HOLD"
        chosen_result["consensus_votes"]      = {"BUY": buy_count, "SELL": sell_count, "HOLD": hold_count}
        chosen_result["consensus_confidence"] = "MEDIUM"
        chosen_result["consensus_calls"]      = [
            {"call": call_labels[i], "decision": r.get("decision", "FAILED"), "status": r.get("status", "FAILED")}
            for i, r in enumerate(results)
        ]
        return chosen_result

    # Confidence reflects how many of the attempted calls actually agreed on a
    # direction — a HOLD/REVIEW among them is weaker evidence than clean
    # directional agreement, even though it can't change which side wins.
    if total_attempted == n and hold_count == 0:
        consensus_confidence = "HIGH" if (buy_count == n or sell_count == n) else "MEDIUM"
    elif total_attempted - hold_count >= 2:
        consensus_confidence = "MEDIUM"
    else:
        consensus_confidence = "LOW"

    majority_decision = "BUY" if buy_count >= sell_count else "SELL"

    # Prefer the earliest call (by index) that matches the majority
    chosen_result = None
    for pref_idx in range(n):
        for suc_idx, suc_r in successful:
            if suc_idx == pref_idx and suc_r.get("decision") == majority_decision:
                chosen_result = suc_r
                break
        if chosen_result:
            break

    # If somehow none match, just take the first successful
    if chosen_result is None:
        chosen_result = successful[0][1]

    # Annotate with consensus metadata
    chosen_result = dict(chosen_result)
    chosen_result["consensus_votes"]      = {"BUY": buy_count, "SELL": sell_count, "HOLD": hold_count}
    chosen_result["consensus_confidence"] = consensus_confidence
    chosen_result["consensus_calls"]      = [
        {"call": call_labels[i], "decision": r.get("decision", "FAILED"), "status": r.get("status", "FAILED")}
        for i, r in enumerate(results)
    ]
    return chosen_result


def _apply_technical_override_and_return(chosen_result: dict, feature_packet: dict,
                                          origin_price: float, initial_capital: float) -> dict:
    """Shared post-processing step (deterministic technical override), used
    by both _call_gemini_consensus and _call_gemini_debate_consensus so the
    two mechanisms apply identical downstream logic after their respective
    (different) voting processes pick a chosen_result."""
    # Phase 3 — apply technical override
    tech_override = _compute_technical_override_score(feature_packet)
    chosen_result["technical_override_score"] = tech_override
    if tech_override["override"] and chosen_result.get("status") == "SUCCESS":
        if tech_override["override"] != chosen_result.get("decision"):
            original_decision = chosen_result.get("decision")
            original_return   = chosen_result.get("predicted_return_pct")
            chosen_result["decision"] = tech_override["override"]

            # Keep the numeric fields consistent with the new decision: flip the
            # return's sign to match the override direction, preserving the
            # model's assessed magnitude, then re-derive target/capital/P&L from
            # that — otherwise the record would end up e.g. decision="SELL" with
            # a positive predicted_return_pct, a directionally self-contradictory
            # record. tech_override["override"] is exhaustively "BUY" or "SELL"
            # here (see _compute_technical_override_score), so the sign mapping
            # below always resolves.
            override_sign = 1.0 if tech_override["override"] == "BUY" else -1.0
            magnitude = abs(float(original_return or 0.0))
            new_return, new_target, new_capital, new_pl = _recompute_price_fields(
                override_sign * magnitude, origin_price, initial_capital,
            )
            chosen_result["predicted_return_pct"]     = new_return
            chosen_result["predicted_target_price"]   = new_target
            chosen_result["predicted_final_capital"]  = new_capital
            chosen_result["predicted_total_pl"]       = new_pl

            chosen_result["decision_reason"] = (
                f"TECHNICAL OVERRIDE (score={tech_override['score']:+d}/10): {tech_override['verdict']}. "
                f"Original AI consensus: {original_decision} ({original_return}% return -> {new_return}% return)"
            )

    # Phase 4's ML signal cross-check used to run here, but feature_packet at
    # this point predates the Component 4 LLM-alpha scores (bull/bear
    # conviction, narrative dependency) -- those are computed from THIS
    # call's own output, so checking the ML model here could never actually
    # see them. Moved to run_gemini_stock_prediction, after those scores are
    # folded into feature_packet, so the shadow model gets the full feature
    # set instead of a permanently-incomplete one. See that function for the
    # real block (search "ML signal cross-check").
    return chosen_result


def _apply_ml_segment_override(
    gemini_result: dict,
    ml_pred: dict,
    has_dedicated_segment_model: bool,
    origin_price: float,
    initial_capital: float,
    enabled: bool,
) -> dict:
    """Research Expansion Program, Component 6 follow-up.

    Promotes the shadow ML model (ml_pred, from ml_signal_model.predict_proba)
    from logged-only to an active decision override -- but ONLY when BOTH:
      - `enabled` (ENABLE_ML_SEGMENT_OVERRIDE) is on, and
      - `has_dedicated_segment_model` is True, i.e. this (symbol, horizon)
        segment has its OWN trained model, not the blended default_model
        fallback (which has no supporting evidence -- see SegmentedModel).

    Mutates and returns gemini_result. No-op (returns unchanged) when either
    gate fails, when ml_pred is falsy, or when ml_pred's decision already
    agrees with gemini_result's -- nothing to override in that case.
    """
    if not (enabled and has_dedicated_segment_model and ml_pred):
        return gemini_result
    if ml_pred.get("decision") == gemini_result.get("decision"):
        return gemini_result

    original_decision = gemini_result.get("decision")
    original_return    = gemini_result.get("predicted_return_pct")
    gemini_result["decision"] = ml_pred["decision"]

    # Same recompute pattern as the technical override above -- keep
    # return/target/capital/P&L fields consistent with the new decision.
    sign      = 1.0 if ml_pred["decision"] == "BUY" else -1.0
    magnitude = abs(float(original_return or 0.0))
    new_return, new_target, new_capital, new_pl = _recompute_price_fields(
        sign * magnitude, origin_price, initial_capital,
    )
    gemini_result["predicted_return_pct"]    = new_return
    gemini_result["predicted_target_price"]  = new_target
    gemini_result["predicted_final_capital"] = new_capital
    gemini_result["predicted_total_pl"]      = new_pl
    gemini_result["decision_reason"] = (
        f"ML SEGMENT OVERRIDE (segment={ml_pred.get('segment')}, "
        f"p_buy={ml_pred.get('p_buy')}, p_sell={ml_pred.get('p_sell')}): "
        f"this segment's dedicated model disagreed with Gemini consensus. "
        f"Original AI consensus: {original_decision} "
        f"({original_return}% return -> {new_return}% return)"
    )
    return gemini_result


def _call_gemini_consensus(
    normalized_input: dict,
    feature_packet: dict,
    calibration_summary: dict,
    origin_price: float,
    initial_capital: float,
    earnings_warning: str = "",
    market_movers_context: str = "",
    chart_images: Optional[Dict[str, bytes]] = None,
) -> dict:
    """
    Call Gemini three times with different reasoning modes and take a majority vote.
    Returns result dict enhanced with consensus metadata.
    Falls back to single call if all three fail.

    chart_images (when provided) is the SAME {"wide": ..., "detail": ...} pair
    attached to all 3 calls -- the underlying visual evidence is identical
    across reasoning modes, only the text prompt's framing differs.

    The 3 calls are INDEPENDENT (same feature_packet, different reasoning-mode
    framing only) and run CONCURRENTLY, not sequentially. Confirmed live this
    session: run sequentially, 3 real deep-thinking calls took up to ~570s
    total (92-191s each); GEMINI_REQUEST_TIMEOUT_MS's own 60s HTTP timeout
    does NOT bound a call's real wall-clock duration here (google-genai's
    httpx-based timeout is a per-read-chunk timeout, not a total-duration
    cap, and a "thinking" model streams tokens throughout, so the timer
    keeps resetting) -- some calls were observed hanging 45+ minutes with
    no response at all. Running the 3 calls concurrently turns the total
    latency from sum(3 calls) into max(3 calls) at zero cost to prediction
    quality (identical calls, just not serialized), and the explicit
    `.result(timeout=...)` below is this project's own enforced hard cap --
    a call that exceeds it is abandoned (its background thread may keep
    running until the underlying connection eventually errors out, but the
    prediction path does not wait on it) and counted as a failed vote for
    that mode, exactly like any other `_call_gemini` failure already is.
    _CONSENSUS_CALL_HARD_TIMEOUT_S is set well above the real 92-191s
    latencies observed for genuinely successful deep-thinking calls with
    this project's configured GEMINI_MODEL (gemini-3.1-pro-preview), so a
    good, just-slow call is never discarded -- only a true runaway hang is.
    """
    call_labels, results, fallback_fn = _run_three_independent_candidates(
        normalized_input, feature_packet, calibration_summary, origin_price, initial_capital,
        earnings_warning=earnings_warning, market_movers_context=market_movers_context,
        chart_images=chart_images,
    )
    chosen_result = _tally_consensus_votes(results, call_labels, fallback_fn)
    return _apply_technical_override_and_return(chosen_result, feature_packet, origin_price, initial_capital)


# ── Research Expansion Program -- genuinely diverse candidate calls ────────
# This project's own data shows the existing 3-call consensus (same full
# feature_packet, only prompt FRAMING differs) agrees 72% of the time, and
# agreement doesn't predict accuracy (52.5% vs 53.3%) -- the calls aren't
# actually diverse, just re-reading the same evidence with different
# rhetoric. The Selection Bottleneck study's judge-beats-vote result assumes
# a genuinely diverse candidate pool; without that, judge-based aggregation
# has little to select BETWEEN. This masks feature_packet itself into 3
# disjoint evidence subsets -- technicals-only, news/fundamentals-only,
# market-regime-only -- so each call reasons from different real evidence,
# not just a different tone on identical evidence.
_TECHNICAL_SECTIONS = {
    "returns", "trend", "momentum", "volatility", "volume",
    "support_resistance", "benchmark_comparison", "reversal_signals",
    "return_magnitude_formula",
}
_NEWS_FUNDAMENTAL_KEYS = {
    "returns", "news_sentiment_score", "news_sentiment_article_count",
    "sec_8k_filing_count", "yahoo_headline_count", "earnings_days_away",
    "insider_buy_count", "insider_sell_count", "insider_net_signal",
    "congress_buy_count", "congress_sell_count", "congress_net_signal",
    "institutional_holder_count", "institutional_flow_score",
    "sec_revenue", "sec_revenue_yoy_pct", "sec_net_income",
    "sec_net_income_yoy_pct", "sec_eps_diluted", "pe_ratio", "pb_ratio", "ps_ratio",
    "pead_composite_score", "earnings_reaction_score", "canslim_composite_score",
    "dividend_growth_score", "dividend_cagr_3yr", "value_dividend_score",
    "reddit_mentions", "reddit_mentions_24h_change",
}
_REGIME_KEYS = {
    "returns", "benchmark_comparison", "macro_regime_composite_score",
    "market_breadth_200ma", "market_breadth_8ma", "market_uptrend_ratio",
    "ftd_dual_confirmation", "ibd_qqq_d25_count", "market_top_risk_score",
    "fed_funds_rate_pct", "treasury_10y_yield_pct",
    "macro_event_days_away", "macro_event_tier",
    "downtrend_median_duration_days", "downtrend_p90_duration_days",
}
_FEATURE_PACKET_METADATA_KEYS = {
    "status", "n_bars", "data_quality_score", "symbol", "benchmark",
    "price_basis", "origin_price", "requested_ctx_start", "effective_ctx_start",
    "ctx_start", "origin_date", "horizon_days",
}


def _mask_feature_packet_for_diversity(feature_packet: dict, mode: str) -> dict:
    """Returns a deep-ish copy of feature_packet containing ONLY metadata +
    the evidence cluster for `mode` ("technicals_only" | "news_only" |
    "regime_only"). Sections/keys outside that cluster are dropped entirely
    (not nulled) so the prompt's JSON dump genuinely doesn't mention them --
    a call can't "see" evidence that isn't in its packet."""
    masked = {k: v for k, v in feature_packet.items() if k in _FEATURE_PACKET_METADATA_KEYS}
    if mode == "technicals_only":
        for section in _TECHNICAL_SECTIONS:
            if section in feature_packet:
                masked[section] = feature_packet[section]
    elif mode == "news_only":
        for key in _NEWS_FUNDAMENTAL_KEYS:
            if key in feature_packet:
                masked[key] = feature_packet[key]
    elif mode == "regime_only":
        for key in _REGIME_KEYS:
            if key in feature_packet:
                masked[key] = feature_packet[key]
    else:
        return dict(feature_packet)
    return masked


def _run_three_diverse_candidates(
    normalized_input: dict,
    feature_packet: dict,
    calibration_summary: dict,
    origin_price: float,
    initial_capital: float,
    earnings_warning: str = "",
    market_movers_context: str = "",
    chart_images: Optional[Dict[str, bytes]] = None,
) -> Tuple[List[str], List[dict], Any]:
    """Same shape/contract as _run_three_independent_candidates, but each
    call gets a DIFFERENT, masked feature_packet (technicals-only /
    news-only / regime-only) instead of the same full packet with a
    different prompt framing."""
    masked_packets = {
        "technicals_only": _mask_feature_packet_for_diversity(feature_packet, "technicals_only"),
        "news_only": _mask_feature_packet_for_diversity(feature_packet, "news_only"),
        "regime_only": _mask_feature_packet_for_diversity(feature_packet, "regime_only"),
    }

    def _make_call(mode: str):
        return _call_gemini(
            normalized_input, masked_packets[mode], calibration_summary, origin_price, initial_capital,
            earnings_warning=earnings_warning, market_movers_context=market_movers_context,
            chart_images=chart_images,
        )

    call_labels = ["technicals_only", "news_only", "regime_only"]
    results: List[dict] = [None, None, None]  # type: ignore[list-item]

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
    future_to_index = {executor.submit(_make_call, mode): i for i, mode in enumerate(call_labels)}
    for future in future_to_index:
        i = future_to_index[future]
        try:
            results[i] = future.result(timeout=_CONSENSUS_CALL_HARD_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            results[i] = {
                "status": "FAILED", "gemini_used": False,
                "error": f"diverse call ({call_labels[i]}) exceeded the "
                         f"{_CONSENSUS_CALL_HARD_TIMEOUT_S:.0f}s hard timeout -- abandoned, not awaited further",
                "gemini_latency_ms": _CONSENSUS_CALL_HARD_TIMEOUT_S * 1000,
            }
        except Exception as exc:
            results[i] = {
                "status": "FAILED", "gemini_used": False,
                "error": f"{type(exc).__name__}: {exc}", "gemini_latency_ms": 0,
            }
    executor.shutdown(wait=False)

    def _fallback():
        return _call_gemini(
            normalized_input, feature_packet, calibration_summary, origin_price, initial_capital,
            earnings_warning=earnings_warning, market_movers_context=market_movers_context,
            chart_images=chart_images,
        )

    return call_labels, results, _fallback


def _call_gemini_diverse_consensus(
    normalized_input: dict,
    feature_packet: dict,
    calibration_summary: dict,
    origin_price: float,
    initial_capital: float,
    earnings_warning: str = "",
    market_movers_context: str = "",
    chart_images: Optional[Dict[str, bytes]] = None,
) -> dict:
    """Research Expansion Program -- genuinely diverse 3-call consensus
    (technicals-only / news-only / regime-only, masked feature packets).
    OPT-IN (ENABLE_DIVERSE_CONSENSUS). Composes with ENABLE_JUDGE_AGGREGATION
    if also set (judge over genuinely diverse candidates is the configuration
    the Selection Bottleneck study's result actually supports); otherwise
    falls back to the same majority-vote tally every other consensus mode
    uses, so this is directly comparable to the standard 3-call baseline via
    the Phase 5 batch harness."""
    call_labels, results, fallback_fn = _run_three_diverse_candidates(
        normalized_input, feature_packet, calibration_summary, origin_price, initial_capital,
        earnings_warning=earnings_warning, market_movers_context=market_movers_context,
        chart_images=chart_images,
    )

    if ENABLE_JUDGE_AGGREGATION:
        judge_outcome = _judge_select_candidate(results, call_labels)
        if judge_outcome is not None:
            chosen_result = dict(results[judge_outcome["chosen_index"]])
            buy_count = sum(1 for r in results if r.get("decision") == "BUY")
            sell_count = sum(1 for r in results if r.get("decision") == "SELL")
            hold_count = sum(1 for r in results if r.get("status") == "SUCCESS" and r.get("decision") not in ("BUY", "SELL"))
            chosen_result["consensus_votes"] = {"BUY": buy_count, "SELL": sell_count, "HOLD": hold_count}
            chosen_result["consensus_calls"] = [
                {"call": call_labels[i], "decision": r.get("decision", "FAILED"), "status": r.get("status", "FAILED")}
                for i, r in enumerate(results)
            ]
            conf = judge_outcome.get("judge_confidence")
            chosen_result["consensus_confidence"] = (
                "HIGH" if isinstance(conf, (int, float)) and conf >= 70
                else "MEDIUM" if isinstance(conf, (int, float)) and conf >= 40
                else "LOW"
            )
            chosen_result["aggregation_method"] = "judge_over_diverse_candidates"
            chosen_result["judge_chosen_call"] = call_labels[judge_outcome["chosen_index"]]
            chosen_result["judge_reasoning"] = judge_outcome["judge_reasoning"]
            chosen_result["judge_confidence"] = conf
            chosen_result["judge_model"] = judge_outcome["judge_model"]
            return _apply_technical_override_and_return(chosen_result, feature_packet, origin_price, initial_capital)

    chosen_result = _tally_consensus_votes(results, call_labels, fallback_fn)
    chosen_result["aggregation_method"] = "majority_vote_over_diverse_candidates"
    return _apply_technical_override_and_return(chosen_result, feature_packet, origin_price, initial_capital)


def _run_three_independent_candidates(
    normalized_input: dict,
    feature_packet: dict,
    calibration_summary: dict,
    origin_price: float,
    initial_capital: float,
    earnings_warning: str = "",
    market_movers_context: str = "",
    chart_images: Optional[Dict[str, bytes]] = None,
) -> Tuple[List[str], List[dict], Any]:
    """Shared candidate-generation step for _call_gemini_consensus (majority
    vote) and _call_gemini_judge_consensus (judge-based selection) -- the 3
    independent calls themselves are identical either way; only how their
    outputs get aggregated into one final decision differs. Extracted so
    both aggregation mechanisms share identical, already-tested call/timeout
    semantics instead of two copies drifting apart (same reasoning
    _tally_consensus_votes was already extracted for).

    Returns (call_labels, results, fallback_fn) -- fallback_fn takes no
    arguments and makes one direct single call, for callers to use only if
    every candidate failed outright.
    """
    def _make_call(mode: Optional[str]):
        cal = dict(calibration_summary)
        if mode:
            cal["consensus_mode"] = mode
        else:
            cal.pop("consensus_mode", None)
        return _call_gemini(
            normalized_input, feature_packet, cal, origin_price, initial_capital,
            earnings_warning=earnings_warning, market_movers_context=market_movers_context,
            chart_images=chart_images,
        )

    call_labels = ["standard", "devils_advocate", "pure_technical"]
    modes: List[Optional[str]] = [None, "devils_advocate", "pure_technical"]
    results: List[dict] = [None, None, None]  # type: ignore[list-item]

    # Deliberately NOT a `with ThreadPoolExecutor() as executor:` block --
    # the context manager's __exit__ calls shutdown(wait=True), which blocks
    # until every submitted thread finishes, including one we've already
    # given up on below via .result(timeout=...). That would silently
    # reintroduce the exact hang this fix exists to prevent. The executor
    # (and any thread still stuck inside a true runaway call) is abandoned
    # without a blocking shutdown; Python reclaims it once those threads
    # eventually finish or the process exits.
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
    future_to_index = {executor.submit(_make_call, mode): i for i, mode in enumerate(modes)}
    for future in future_to_index:
        i = future_to_index[future]
        try:
            results[i] = future.result(timeout=_CONSENSUS_CALL_HARD_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            results[i] = {
                "status": "FAILED", "gemini_used": False,
                "error": f"consensus call ({call_labels[i]}) exceeded the "
                         f"{_CONSENSUS_CALL_HARD_TIMEOUT_S:.0f}s hard timeout -- abandoned, not awaited further",
                "gemini_latency_ms": _CONSENSUS_CALL_HARD_TIMEOUT_S * 1000,
            }
        except Exception as exc:
            results[i] = {
                "status": "FAILED", "gemini_used": False,
                "error": f"{type(exc).__name__}: {exc}", "gemini_latency_ms": 0,
            }
    executor.shutdown(wait=False)

    def _fallback():
        return _call_gemini(
            normalized_input, feature_packet, calibration_summary, origin_price, initial_capital,
            earnings_warning=earnings_warning, market_movers_context=market_movers_context,
            chart_images=chart_images,
        )

    return call_labels, results, _fallback


def _judge_select_candidate(results: List[dict], call_labels: List[str]) -> Optional[dict]:
    """Research Expansion Program -- judge-based aggregation (see
    ENABLE_JUDGE_AGGREGATION docstring near the top of this file). Shows a
    DIFFERENT model (JUDGE_MODEL, not GEMINI_MODEL -- the research's own
    disclosed same-family-bias caveat) the 3 candidate decisions + their
    reasoning, and asks it to pick which one to adopt.

    Returns a dict with keys {"chosen_index": int, "judge_reasoning": str,
    "judge_confidence": int} on success, or None on any failure (caller
    must fall back to majority voting -- this is an experimental, opt-in
    path and must never be the reason a prediction fails outright).
    """
    if not _GEMINI_KEY:
        return None

    candidates_desc = []
    for i, (label, r) in enumerate(zip(call_labels, results)):
        if r.get("status") != "SUCCESS":
            candidates_desc.append(f"Candidate {i} ({label}): FAILED -- {r.get('error', 'unknown error')}")
            continue
        candidates_desc.append(
            f"Candidate {i} ({label}): decision={r.get('decision')}, "
            f"confidence_score={r.get('confidence_score')}, risk_score={r.get('risk_score')}, "
            f"predicted_return_pct={r.get('predicted_return_pct')}, "
            f"reasoning=\"{str(r.get('reasoning', ''))[:400]}\""
        )

    judge_prompt = (
        "You are a neutral judge reviewing 3 independent stock-prediction calls made by "
        "another AI model about the SAME stock/time period, each using a different "
        "reasoning framing (standard, devil's-advocate/contrarian, pure-technical-only). "
        "They may disagree. Your job is NOT to average them or default to the majority -- "
        "pick whichever ONE candidate has the strongest, most internally consistent "
        "reasoning given its own stated evidence, even if it is the minority view.\n\n"
        + "\n".join(candidates_desc) +
        "\n\nRespond with ONLY a JSON object, no other text:\n"
        '{"chosen_index": <0, 1, or 2 -- a FAILED candidate can never be chosen>, '
        '"judge_reasoning": "<1-2 sentences: why this one over the others>", '
        '"judge_confidence_0_100": <integer>}'
    )

    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=_GEMINI_KEY, http_options=genai_types.HttpOptions(timeout=30000))
        response = _generate_content_with_retry(
            client,
            model=JUDGE_MODEL,
            contents=judge_prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=500,
                response_mime_type="application/json",
                thinking_config=genai_types.ThinkingConfig(thinking_budget=1024),
            ),
        )
        raw = (response.text or "").strip()
        json_text = _extract_json(raw)
        parsed = json.loads(json_text)
        chosen_index = int(parsed.get("chosen_index"))
        if chosen_index not in (0, 1, 2) or results[chosen_index].get("status") != "SUCCESS":
            return None
        return {
            "chosen_index": chosen_index,
            "judge_reasoning": str(parsed.get("judge_reasoning", "")),
            "judge_confidence": parsed.get("judge_confidence_0_100"),
            "judge_model": JUDGE_MODEL,
        }
    except Exception:
        return None


def _call_gemini_judge_consensus(
    normalized_input: dict,
    feature_packet: dict,
    calibration_summary: dict,
    origin_price: float,
    initial_capital: float,
    earnings_warning: str = "",
    market_movers_context: str = "",
    chart_images: Optional[Dict[str, bytes]] = None,
) -> dict:
    """Research Expansion Program -- judge-based aggregation. Runs the SAME
    3 independent candidate calls as _call_gemini_consensus, but instead of
    a majority vote, a 4th call (a different model, JUDGE_MODEL) picks which
    ONE candidate to adopt. Falls back to majority voting if the judge call
    itself fails for any reason (network, parsing, bad index) -- this is an
    experimental, opt-in path (ENABLE_JUDGE_AGGREGATION) and must degrade
    gracefully, never block a prediction.

    4 Gemini calls total (3 candidates + 1 judge) -- one more than the
    standard 3-call consensus, cheaper than the 5-call debate consensus.
    """
    call_labels, results, fallback_fn = _run_three_independent_candidates(
        normalized_input, feature_packet, calibration_summary, origin_price, initial_capital,
        earnings_warning=earnings_warning, market_movers_context=market_movers_context,
        chart_images=chart_images,
    )

    judge_outcome = _judge_select_candidate(results, call_labels)
    if judge_outcome is None:
        # Judge failed/declined -- fall back to the proven majority-vote path.
        chosen_result = _tally_consensus_votes(results, call_labels, fallback_fn)
        chosen_result["aggregation_method"] = "majority_vote_fallback_judge_unavailable"
        return _apply_technical_override_and_return(chosen_result, feature_packet, origin_price, initial_capital)

    chosen_result = dict(results[judge_outcome["chosen_index"]])
    buy_count  = sum(1 for r in results if r.get("decision") == "BUY")
    sell_count = sum(1 for r in results if r.get("decision") == "SELL")
    hold_count = sum(1 for r in results if r.get("status") == "SUCCESS" and r.get("decision") not in ("BUY", "SELL"))
    chosen_result["consensus_votes"]      = {"BUY": buy_count, "SELL": sell_count, "HOLD": hold_count}
    chosen_result["consensus_calls"]      = [
        {"call": call_labels[i], "decision": r.get("decision", "FAILED"), "status": r.get("status", "FAILED")}
        for i, r in enumerate(results)
    ]
    conf = judge_outcome.get("judge_confidence")
    chosen_result["consensus_confidence"] = (
        "HIGH" if isinstance(conf, (int, float)) and conf >= 70
        else "MEDIUM" if isinstance(conf, (int, float)) and conf >= 40
        else "LOW"
    )
    chosen_result["aggregation_method"] = "judge"
    chosen_result["judge_chosen_call"]  = call_labels[judge_outcome["chosen_index"]]
    chosen_result["judge_reasoning"]    = judge_outcome["judge_reasoning"]
    chosen_result["judge_confidence"]   = conf
    chosen_result["judge_model"]        = judge_outcome["judge_model"]
    return _apply_technical_override_and_return(chosen_result, feature_packet, origin_price, initial_capital)


def _call_gemini_debate_consensus(
    normalized_input: dict,
    feature_packet: dict,
    calibration_summary: dict,
    origin_price: float,
    initial_capital: float,
    earnings_warning: str = "",
    market_movers_context: str = "",
    chart_images: Optional[Dict[str, bytes]] = None,
) -> dict:
    """
    Research Expansion Program, Component 5 -- Bull/Bear debate consensus,
    inspired by TradingAgents' multi-round researcher debate (see this
    session's own research: a respected, 110k-star open framework uses
    actual multi-round debate rather than independent parallel framings).

    OPT-IN ONLY (ENABLE_DEBATE_CONSENSUS env var) and NOT a default
    replacement for _call_gemini_consensus -- this session already found,
    concretely, that MORE LLM sophistication (the existing triple-consensus)
    scored WORSE than an older, simpler baseline. "Credible idea from a
    respected project" is exactly the standard that already failed once this
    session when applied uncritically; this must earn its way into the live
    path through the Phase 5 batch harness before ever being made default.

    5 Gemini calls (vs. 3 for the standard consensus): Bull round 1, Bear
    round 1, Bull round 2 (rebuts Bear's round-1 argument), Bear round 2
    (rebuts Bull's round-1 argument), Pure Technical (reused as a 3rd
    independent voice). Only the 3 FINAL positions (bull round 2, bear round
    2, pure technical) are tallied for the majority vote -- round 1 calls are
    intermediate debate turns, not votes in their own right. Real latency
    cost: at ~30-46s/call for this model, this is 2.5-4 minutes per
    prediction end to end.
    """
    def _call(mode: str, opponent_argument: str = ""):
        cal = dict(calibration_summary)
        cal["consensus_mode"] = mode
        if opponent_argument:
            cal["opponent_argument"] = opponent_argument
        return _call_gemini(
            normalized_input, feature_packet, cal, origin_price, initial_capital,
            earnings_warning=earnings_warning, market_movers_context=market_movers_context,
            chart_images=chart_images,
        )

    bull_r1 = _call("bull_round1")
    bear_r1 = _call("bear_round1")

    bull_r1_argument = bull_r1.get("reasoning") or bull_r1.get("decision_reason") or ""
    bear_r1_argument = bear_r1.get("reasoning") or bear_r1.get("decision_reason") or ""

    bull_r2 = _call("bull_round2", opponent_argument=bear_r1_argument)
    bear_r2 = _call("bear_round2", opponent_argument=bull_r1_argument)
    pure_technical = _call("pure_technical")

    results = [bull_r2, bear_r2, pure_technical]
    call_labels = ["bull_round2", "bear_round2", "pure_technical"]

    def _fallback():
        return _call_gemini(
            normalized_input, feature_packet, calibration_summary, origin_price, initial_capital,
            earnings_warning=earnings_warning, market_movers_context=market_movers_context,
            chart_images=chart_images,
        )

    chosen_result = _tally_consensus_votes(results, call_labels, _fallback)
    chosen_result["debate_transcript"] = {
        "bull_round1": bull_r1_argument, "bear_round1": bear_r1_argument,
        "bull_round2_decision": bull_r2.get("decision"), "bear_round2_decision": bear_r2.get("decision"),
    }
    return _apply_technical_override_and_return(chosen_result, feature_packet, origin_price, initial_capital)


# ═══════════════════════════════════════════════════════════════════════════════
# LEAKAGE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_no_leakage(ai_visible_bars: List[dict], origin_date: str, ctx_start: str) -> dict:
    if not ai_visible_bars:
        return {"status": "NO_BARS", "note": "No bars to check"}
    dates = [b["date"] for b in ai_visible_bars]
    min_d, max_d = min(dates), max(dates)
    if max_d > origin_date:
        return {"status": "LEAKAGE_DETECTED", "max_date": max_d, "origin": origin_date}
    if min_d < ctx_start:
        return {"status": "LEAKAGE_DETECTED", "min_date": min_d, "ctx_start": ctx_start}
    return {"status": "CLEAN", "min_date": min_d, "max_date": max_d}


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def run_gemini_stock_prediction(spi: dict, price_history_context: List[dict]) -> dict:
    """
    Walk-forward stock prediction using Gemini.

    Parameters:
    - spi                   : StockPredictionInput dict
    - price_history_context : bars filtered to [ctx_start, origin_date] by caller

    Returns a result dict compatible with the existing app's ai_result schema,
    plus additional Gemini-specific fields (ai_provider, gemini_used, etc.).
    """
    from stock_prediction_agent import (
        validate_stock_prediction_input,
        build_stock_prediction_hash,
        _parse_ymd,
    )
    from historical_price_service import get_price_on_date

    origin_str  = str(spi.get("prediction_origin_date", "") or "")
    ctx_start   = str(spi.get("historical_context_start_date", "") or "")
    target_str  = str(spi.get("target_date", "") or "")
    symbol      = str(spi.get("symbol", "") or "").upper()
    horizon_days = int(spi.get("decision_horizon_days", 30) or 30)
    initial_cap  = float(spi.get("initial_capital", 50000) or 50000)
    input_hash   = build_stock_prediction_hash(spi)

    # Double guard: strip future bars
    history = [b for b in (price_history_context or []) if b["date"] <= origin_str]

    valid, err = validate_stock_prediction_input(spi)
    if not valid:
        return _error_result(spi, input_hash, err)

    if not history:
        return _error_result(spi, input_hash, f"No price bars available up to {origin_str}")

    # Leakage check
    leakage = _validate_no_leakage(history, origin_str, ctx_start)
    if leakage["status"] == "LEAKAGE_DETECTED":
        return _error_result(spi, input_hash, f"Leakage detected: {leakage}")

    # Pre-flight assertion: block if any bar date is after origin date
    _target_in_history = any(b["date"] > origin_str for b in history)
    if _target_in_history:
        return _error_result(spi, input_hash, "LEAKAGE_BLOCKED: bars after origin date detected in history.")

    # Origin price — respect price_basis setting (high/low/open/close)
    _price_basis = str(spi.get("price_basis", "close") or "close")
    origin_price, eff_origin_date, price_err = get_price_on_date(history, origin_str, price_basis=_price_basis)
    if origin_price is None:
        return _error_result(spi, input_hash, f"Cannot get origin price on {origin_str}: {price_err}")

    # Failures below are recorded here instead of silently swallowed -- a
    # transient fetch error must not look identical to "this symbol genuinely
    # has no earnings/benchmark/movers data." Returned in the final result
    # under context_enrichment_warnings.
    _context_enrichment_warnings: dict = {}

    # Fetch benchmark bars so relative strength is computed for Gemini
    benchmark_sym = str(spi.get("benchmark", "") or "").strip().upper()
    _benchmark_bars: Optional[List[dict]] = None
    if benchmark_sym and benchmark_sym != symbol:
        try:
            from historical_price_service import fetch_price_history_for_range as _fpr
            _bm_bars, _bm_err, _bm_cov = _fpr(benchmark_sym, ctx_start, origin_str)
            if _bm_bars:
                _benchmark_bars = [b for b in _bm_bars if b["date"] <= origin_str]
            else:
                _context_enrichment_warnings["benchmark_bars"] = _bm_err or "No benchmark bars returned."
        except Exception as exc:
            _benchmark_bars = None
            _context_enrichment_warnings["benchmark_bars"] = f"{type(exc).__name__}: {exc}"

    # Build feature packet
    feature_packet = build_stock_feature_packet(spi, history, benchmark_bars=_benchmark_bars)
    if feature_packet.get("status") != "OK":
        return _error_result(spi, input_hash, f"Feature packet failed: {feature_packet.get('error')}")

    # Phase 3 — earnings proximity + news sentiment (Alpha Vantage), scoped to
    # single-name symbols only -- this session's own data showed broad-index
    # symbols (SPY/QQQ/etc.) already perform acceptably on technical
    # indicators alone at short horizons; this targets the specific weak spot
    # (narrative-driven single names) instead of adding cost/complexity
    # everywhere. Unlike the RapidAPI market-movers snapshot (which has no
    # historical capability and is gated to live-only predictions), these
    # fetchers filter by as_of_date themselves, so they're safe for historical
    # replay too -- no _is_recent_origin gate needed here. Degrades to
    # unavailable, never blocks a prediction, if ALPHA_VANTAGE_API_KEY isn't
    # set or the free tier is rate-limited.
    _is_index_symbol = symbol.upper() in ("SPY", "SPX", "QQQ", "IWM", "DIA")
    if not _is_index_symbol:
        try:
            from news_sentiment_service import fetch_earnings_calendar, earnings_days_away, fetch_news_sentiment_score
            _earn_data, _earn_err = fetch_earnings_calendar(symbol)
            if _earn_data:
                feature_packet["earnings_days_away"] = earnings_days_away(_earn_data, origin_str, target_str or origin_str)
            elif _earn_err:
                _context_enrichment_warnings["alpha_vantage_earnings"] = _earn_err

            _sent_data, _sent_err = fetch_news_sentiment_score(symbol, origin_str)
            if _sent_data:
                feature_packet["news_sentiment_score"] = _sent_data.get("avg_sentiment_score")
                feature_packet["news_sentiment_article_count"] = _sent_data.get("article_count")
            elif _sent_err:
                _context_enrichment_warnings["alpha_vantage_news_sentiment"] = _sent_err
        except Exception as exc:
            _context_enrichment_warnings["alpha_vantage"] = f"{type(exc).__name__}: {exc}"

    # Calibration summary — as_of_date=origin_str keeps a historical replay from
    # seeing outcomes that hadn't resolved yet as of the origin being replayed;
    # for live predictions (origin_str ~= today) this is effectively unfiltered.
    # feature_packet is passed through so build_calibration_summary can also
    # retrieve nearest historical precedents (case_retrieval.py) from the same
    # leakage-safe record set.
    calibration_summary = build_calibration_summary(
        symbol=symbol, horizon_days=horizon_days, as_of_date=origin_str,
        feature_packet=feature_packet,
    )
    if calibration_summary.get("symbol_calibration_error"):
        _context_enrichment_warnings["symbol_calibration"] = calibration_summary["symbol_calibration_error"]

    _origin_is_recent = _is_recent_origin(origin_str)

    # Per-prediction leakage probe -- OPT-IN (ENABLE_LAP_PROBE_PER_PREDICTION),
    # one extra Gemini call, never blocks the main prediction on failure.
    _leakage_probe_result: Optional[dict] = None
    if ENABLE_LAP_PROBE_PER_PREDICTION and target_str:
        try:
            from lap_leakage_probe import check_leakage_for_prediction
            _leakage_probe_result = check_leakage_for_prediction(symbol, target_str)
        except Exception as exc:
            _leakage_probe_result = {"checked": False, "error": f"{type(exc).__name__}: {exc}"}

    # ---- Context-enrichment data fetches, run CONCURRENTLY -----------------
    # Each of the ~28 free/alt-data providers below (SEC EDGAR, ApeWisdom,
    # macro/regime/breadth/FTD/IBD/market-top, the CANSLIM/VCP/Stockbee/PEAD/
    # dividend screens, put/call ratio, market movers, chart vision, etc.) is
    # an independent, read-only lookup keyed only on (symbol, origin_str) --
    # none of them reads another's output or feeds the next one. Running them
    # sequentially (as before) meant their latencies simply added up on top of
    # the Gemini call itself -- this was the actual, honest reason a single
    # prediction could take far longer than the Gemini call alone would
    # suggest. Firing them concurrently (same ThreadPoolExecutor pattern
    # already used for the 3 Gemini consensus calls) collapses that sum down
    # to roughly the slowest single provider. This changes nothing about WHAT
    # data is fetched, how it's parsed, or what Gemini ultimately sees --
    # every feature_packet key/warning ends up identical to the sequential
    # version, just collected faster. The whole batch is bounded by one
    # ceiling (default 25s) so a single slow/dead free provider -- or all of
    # them, e.g. during a DNS outage -- can never stall a prediction the way
    # the unbounded Gemini calls used to; tasks still running past the
    # deadline are abandoned (not waited on) and simply recorded as a warning.
    _ENRICHMENT_BATCH_TIMEOUT_S = float(os.getenv("CONTEXT_ENRICHMENT_BATCH_TIMEOUT_S", "25"))

    def _task_insider():
        if _is_index_symbol:
            return {}
        try:
            from insider_activity_service import fetch_insider_activity
            _data, _err = fetch_insider_activity(symbol, origin_str)
            if _data:
                return {"feature": {
                    "insider_buy_count": _data.get("buy_count"),
                    "insider_sell_count": _data.get("sell_count"),
                    "insider_net_signal": _data.get("net_signal"),
                }}
            if _err:
                return {"warning": ("sec_edgar_insider", _err)}
            return {}
        except Exception as exc:
            return {"warning": ("sec_edgar_insider", f"{type(exc).__name__}: {exc}")}

    def _task_reddit():
        if _is_index_symbol or not _origin_is_recent:
            return {}
        try:
            from social_attention_service import fetch_reddit_attention
            _data, _err = fetch_reddit_attention(symbol)
            if _data:
                return {"feature": {
                    "reddit_mentions": _data.get("mentions"),
                    "reddit_mentions_24h_change": _data.get("mentions_24h_change"),
                }}
            if _err:
                return {"warning": ("apewisdom_reddit", _err)}
            return {}
        except Exception as exc:
            return {"warning": ("apewisdom_reddit", f"{type(exc).__name__}: {exc}")}

    def _task_macro_data():
        try:
            from macro_data_service import fetch_macro_snapshot
            _data, _err = fetch_macro_snapshot(origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "fed_funds_rate_pct": _data.get("fed_funds_rate_pct"),
                    "treasury_10y_yield_pct": _data.get("treasury_10y_yield_pct"),
                }
            if _err:
                out["warning"] = ("macro_data", _err)
            return out
        except Exception as exc:
            return {"warning": ("macro_data", f"{type(exc).__name__}: {exc}")}

    def _task_congress():
        if _is_index_symbol:
            return {}
        try:
            from congress_trade_service import fetch_congress_trades
            _data, _err = fetch_congress_trades(symbol, origin_str)
            if _data:
                return {"feature": {
                    "congress_buy_count": _data.get("buy_count"),
                    "congress_sell_count": _data.get("sell_count"),
                    "congress_net_signal": _data.get("net_signal"),
                }}
            if _err:
                return {"warning": ("congress_trades", _err)}
            return {}
        except Exception as exc:
            return {"warning": ("congress_trades", f"{type(exc).__name__}: {exc}")}

    def _task_institutional_holdings():
        if _is_index_symbol:
            return {}
        try:
            from institutional_holdings_service import fetch_institutional_holders
            _data, _err = fetch_institutional_holders(symbol, origin_str)
            if _data:
                return {"feature": {"institutional_holder_count": _data.get("holder_count")}}
            if _err:
                return {"warning": ("institutional_holdings", _err)}
            return {}
        except Exception as exc:
            return {"warning": ("institutional_holdings", f"{type(exc).__name__}: {exc}")}

    def _task_market_breadth():
        try:
            from market_breadth_service import fetch_market_breadth_snapshot
            _data, _err = fetch_market_breadth_snapshot(origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "market_breadth_200ma": _data.get("breadth_200ma"),
                    "market_breadth_8ma": _data.get("breadth_8ma"),
                    "market_uptrend_ratio": _data.get("uptrend_ratio"),
                }
            if _err:
                out["warning"] = ("market_breadth", _err)
            return out
        except Exception as exc:
            return {"warning": ("market_breadth", f"{type(exc).__name__}: {exc}")}

    def _task_macro_regime():
        try:
            from macro_regime_service import compute_macro_regime
            _data, _err = compute_macro_regime(origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "macro_regime_composite_score": _data.get("composite_score"),
                    "macro_regime_current": _data.get("current_regime"),
                    "macro_regime_confidence": _data.get("confidence"),
                }
            if _err:
                out["warning"] = ("macro_regime", _err)
            return out
        except Exception as exc:
            return {"warning": ("macro_regime", f"{type(exc).__name__}: {exc}")}

    def _task_ftd_status():
        try:
            from ftd_status_service import compute_ftd_status
            _data, _err = compute_ftd_status(origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "ftd_combined_state": _data.get("combined_state"),
                    "ftd_dual_confirmation": _data.get("dual_confirmation"),
                }
            if _err:
                out["warning"] = ("ftd_status", _err)
            return out
        except Exception as exc:
            return {"warning": ("ftd_status", f"{type(exc).__name__}: {exc}")}

    def _task_ibd_distribution_day():
        try:
            from ibd_distribution_day_service import compute_ibd_distribution_day_status
            _data, _err = compute_ibd_distribution_day_status(origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "ibd_overall_risk_level": _data.get("overall_risk_level"),
                    "ibd_qqq_d25_count": _data.get("qqq_d25_count"),
                }
            if _err:
                out["warning"] = ("ibd_distribution_day", _err)
            return out
        except Exception as exc:
            return {"warning": ("ibd_distribution_day", f"{type(exc).__name__}: {exc}")}

    def _task_market_top_detector():
        try:
            from market_top_detector_service import compute_market_top_risk
            _data, _err = compute_market_top_risk(origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "market_top_risk_score": _data.get("composite_score"),
                    "market_top_risk_zone": _data.get("zone"),
                }
            if _err:
                out["warning"] = ("market_top_detector", _err)
            return out
        except Exception as exc:
            return {"warning": ("market_top_detector", f"{type(exc).__name__}: {exc}")}

    def _task_sec_8k():
        if _is_index_symbol:
            return {}
        try:
            from free_news_service import fetch_sec_8k_count
            _data, _err = fetch_sec_8k_count(symbol, origin_str)
            if _data:
                return {"feature": {"sec_8k_filing_count": _data.get("filing_count")}}
            if _err:
                return {"warning": ("sec_8k_filings", _err)}
            return {}
        except Exception as exc:
            return {"warning": ("sec_8k_filings", f"{type(exc).__name__}: {exc}")}

    def _task_yahoo_headlines():
        if _is_index_symbol or not _origin_is_recent:
            return {}
        try:
            from free_news_service import fetch_yahoo_headline_tags
            _data, _err = fetch_yahoo_headline_tags(symbol)
            if _data:
                feature = {
                    "yahoo_headline_count": _data.get("headline_count"),
                    "yahoo_headline_tags": _data.get("tags"),
                }
                # Research Expansion Program -- per-headline scoring (Lopez-Lira
                # & Tang's actual mechanism). OPT-IN: one extra Gemini call,
                # only when there are real titles to classify.
                if ENABLE_PER_HEADLINE_NEWS_SCORING and _data.get("titles"):
                    try:
                        from per_headline_news_scorer import score_headlines
                        _hl_data, _hl_err = score_headlines(symbol, _data["titles"])
                        if _hl_data:
                            feature.update(_hl_data)
                        elif _hl_err:
                            return {"feature": feature, "warning": ("per_headline_news_scoring", _hl_err)}
                    except Exception as _hl_exc:
                        return {"feature": feature, "warning": ("per_headline_news_scoring", f"{type(_hl_exc).__name__}: {_hl_exc}")}
                return {"feature": feature}
            if _err:
                return {"warning": ("yahoo_headlines", _err)}
            return {}
        except Exception as exc:
            return {"warning": ("yahoo_headlines", f"{type(exc).__name__}: {exc}")}

    def _task_sec_financials():
        if _is_index_symbol:
            return {}
        try:
            from sec_financials_service import fetch_key_financials, compute_valuation_ratios
            _data, _err = fetch_key_financials(symbol, origin_str)
            out: dict = {}
            feature: dict = {}
            if _data:
                feature.update({
                    "sec_revenue": _data.get("revenue"),
                    "sec_revenue_yoy_pct": _data.get("revenue_yoy_pct"),
                    "sec_net_income": _data.get("net_income"),
                    "sec_net_income_yoy_pct": _data.get("net_income_yoy_pct"),
                    "sec_eps_diluted": _data.get("eps_diluted"),
                })
            elif _err:
                out["warning"] = ("sec_financials", _err)

            # P/E, P/B, P/S -- uses the SAME origin_price already used for
            # every other feature in this packet, never a live quote.
            _ratio_data, _ratio_err = compute_valuation_ratios(symbol, origin_str, origin_price)
            if _ratio_data:
                feature.update(_ratio_data)
            elif _ratio_err and "warning" not in out:
                out["warning"] = ("sec_valuation_ratios", _ratio_err)

            if feature:
                out["feature"] = feature
            return out
        except Exception as exc:
            return {"warning": ("sec_financials", f"{type(exc).__name__}: {exc}")}

    def _task_downtrend_duration():
        try:
            from downtrend_duration_service import fetch_downtrend_stats
            _data, _err = fetch_downtrend_stats(symbol, origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "downtrend_median_duration_days": _data.get("median_duration_days"),
                    "downtrend_p90_duration_days": _data.get("p90_duration_days"),
                }
            if _err:
                out["warning"] = ("downtrend_duration", _err)
            return out
        except Exception as exc:
            return {"warning": ("downtrend_duration", f"{type(exc).__name__}: {exc}")}

    def _task_pead_screener():
        if _is_index_symbol:
            return {}
        try:
            from pead_screener_service import fetch_pead_analysis
            _data, _err = fetch_pead_analysis(symbol, origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "pead_composite_score": _data.get("composite_score"),
                    "pead_stage": _data.get("stage"),
                }
            if _err:
                out["warning"] = ("pead_screener", _err)
            return out
        except Exception as exc:
            return {"warning": ("pead_screener", f"{type(exc).__name__}: {exc}")}

    def _task_earnings_trade_analyzer():
        if _is_index_symbol:
            return {}
        try:
            from earnings_trade_analyzer_service import fetch_earnings_trade_analysis
            _data, _err = fetch_earnings_trade_analysis(symbol, origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "earnings_reaction_score": _data["composite"].get("composite_score"),
                    "earnings_reaction_grade": _data["composite"].get("grade"),
                }
            if _err:
                out["warning"] = ("earnings_trade_analyzer", _err)
            return out
        except Exception as exc:
            return {"warning": ("earnings_trade_analyzer", f"{type(exc).__name__}: {exc}")}

    def _task_exhaustion_hammer():
        if _is_index_symbol:
            return {}
        try:
            from stockbee_exhaustion_hammer_service import fetch_exhaustion_hammer_analysis
            _data, _err = fetch_exhaustion_hammer_analysis(symbol, origin_str)
            if _data:
                return {"feature": {
                    "hammer_setup_score": _data.get("setup_score"),
                    "hammer_state": _data.get("state"),
                }}
            if _err:
                return {"warning": ("stockbee_exhaustion_hammer", _err)}
            return {}
        except Exception as exc:
            return {"warning": ("stockbee_exhaustion_hammer", f"{type(exc).__name__}: {exc}")}

    def _task_momentum_burst():
        if _is_index_symbol:
            return {}
        try:
            from stockbee_momentum_burst_service import fetch_momentum_burst_analysis
            _data, _err = fetch_momentum_burst_analysis(symbol, origin_str)
            if _data:
                return {"feature": {
                    "momentum_burst_score": _data.get("setup_score"),
                    "momentum_burst_state": _data.get("state"),
                }}
            if _err:
                return {"warning": ("stockbee_momentum_burst", _err)}
            return {}
        except Exception as exc:
            return {"warning": ("stockbee_momentum_burst", f"{type(exc).__name__}: {exc}")}

    def _task_episodic_pivot():
        if _is_index_symbol:
            return {}
        try:
            from stockbee_episodic_pivot_analyzer_service import fetch_episodic_pivot_analysis
            _data, _err = fetch_episodic_pivot_analysis(symbol, origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "episodic_pivot_score": _data.get("composite_score"),
                    "episodic_pivot_state": _data.get("state"),
                }
            if _err:
                out["warning"] = ("stockbee_episodic_pivot", _err)
            return out
        except Exception as exc:
            return {"warning": ("stockbee_episodic_pivot", f"{type(exc).__name__}: {exc}")}

    def _task_vcp_screener():
        if _is_index_symbol:
            return {}
        try:
            from vcp_screener_service import fetch_vcp_analysis
            _data, _err = fetch_vcp_analysis(symbol, origin_str)
            if _data:
                return {"feature": {
                    "vcp_composite_score": _data.get("composite_score"),
                    "vcp_execution_state": _data.get("execution_state"),
                }}
            if _err:
                return {"warning": ("vcp_screener", _err)}
            return {}
        except Exception as exc:
            return {"warning": ("vcp_screener", f"{type(exc).__name__}: {exc}")}

    def _task_canslim():
        if _is_index_symbol:
            return {}
        try:
            from canslim_screener_service import fetch_canslim_analysis
            _data, _err = fetch_canslim_analysis(symbol, origin_str)
            if _data:
                return {"feature": {
                    "canslim_composite_score": _data.get("composite_score"),
                    "canslim_rating": _data.get("rating"),
                }}
            if _err:
                return {"warning": ("canslim_screener", _err)}
            return {}
        except Exception as exc:
            return {"warning": ("canslim_screener", f"{type(exc).__name__}: {exc}")}

    def _task_dividend_growth_pullback():
        if _is_index_symbol:
            return {}
        try:
            from dividend_growth_pullback_screener_service import fetch_dividend_growth_pullback_analysis
            _data, _err = fetch_dividend_growth_pullback_analysis(symbol, origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "dividend_growth_score": _data.get("composite_score"),
                    "dividend_cagr_3yr": _data.get("dividend_cagr_3yr"),
                }
            if _err:
                out["warning"] = ("dividend_growth_pullback", _err)
            return out
        except Exception as exc:
            return {"warning": ("dividend_growth_pullback", f"{type(exc).__name__}: {exc}")}

    def _task_value_dividend():
        if _is_index_symbol:
            return {}
        try:
            from value_dividend_screener_service import fetch_value_dividend_analysis
            _data, _err = fetch_value_dividend_analysis(symbol, origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "value_dividend_score": _data.get("composite_score"),
                    "dividend_stable": _data.get("dividend_stable"),
                }
            if _err:
                out["warning"] = ("value_dividend_screener", _err)
            return out
        except Exception as exc:
            return {"warning": ("value_dividend_screener", f"{type(exc).__name__}: {exc}")}

    def _task_20pct_study():
        if _is_index_symbol:
            return {}
        try:
            from stockbee_20pct_study_service import fetch_20pct_study
            _data, _err = fetch_20pct_study(symbol, origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "twenty_pct_study_score": _data["scores"].get("continuation_quality_score"),
                    "twenty_pct_study_direction": _data.get("direction"),
                }
            if _err:
                out["warning"] = ("stockbee_20pct_study", _err)
            return out
        except Exception as exc:
            return {"warning": ("stockbee_20pct_study", f"{type(exc).__name__}: {exc}")}

    def _task_macro_calendar():
        if not _origin_is_recent:
            return {}
        try:
            from macro_calendar_service import fetch_macro_event_risk
            _data, _err = fetch_macro_event_risk(origin_str, lookahead_days=horizon_days)
            out = {}
            if _data:
                out["feature"] = {
                    "macro_event_days_away": _data.get("days_to_nearest_event"),
                    "macro_event_tier": _data.get("nearest_event_tier"),
                }
            if _err:
                out["warning"] = ("macro_calendar", _err)
            return out
        except Exception as exc:
            return {"warning": ("macro_calendar", f"{type(exc).__name__}: {exc}")}

    def _task_institutional_flow():
        if _is_index_symbol:
            return {}
        try:
            from institutional_flow_tracker_service import fetch_institutional_flow
            _data, _err = fetch_institutional_flow(symbol, origin_str)
            out = {}
            if _data:
                out["feature"] = {
                    "institutional_flow_score": _data.get("flow_score"),
                    "institutional_flow_classification": _data.get("classification"),
                }
            if _err:
                out["warning"] = ("institutional_flow_tracker", _err)
            return out
        except Exception as exc:
            return {"warning": ("institutional_flow_tracker", f"{type(exc).__name__}: {exc}")}

    def _task_put_call_ratio():
        if not _origin_is_recent:
            return {}
        try:
            return {"put_call_data": _get_put_call_ratio(symbol)}
        except Exception:
            return {"put_call_data": {"available": False}}

    def _task_market_movers():
        if not _origin_is_recent:
            return {}
        try:
            from rapidapi_market_service import fetch_top_movers_for_gemini
            _result = fetch_top_movers_for_gemini()
            if _result.get("status") == "SUCCESS":
                return {"market_movers_context": _result.get("context_text", "")}
            return {"warning": ("market_movers", str(_result.get("message") or _result.get("status") or "unavailable"))}
        except Exception as exc:
            return {"warning": ("market_movers", f"{type(exc).__name__}: {exc}")}

    def _task_chart_vision():
        if not ENABLE_CHART_VISION:
            return {}
        try:
            from chart_rendering import render_chart_pair
            _images = render_chart_pair(
                history, symbol, origin_str,
                wide_lookback_days=CHART_VISION_WIDE_LOOKBACK_DAYS,
                detail_lookback_days=CHART_VISION_DETAIL_LOOKBACK_DAYS,
            )
            return {"chart_images": _images}
        except Exception as exc:
            return {"warning": ("chart_vision", f"{type(exc).__name__}: {exc}")}

    _enrichment_tasks = [
        _task_insider, _task_reddit, _task_macro_data, _task_congress,
        _task_institutional_holdings, _task_market_breadth, _task_macro_regime,
        _task_ftd_status, _task_ibd_distribution_day, _task_market_top_detector,
        _task_sec_8k, _task_yahoo_headlines, _task_sec_financials,
        _task_downtrend_duration, _task_pead_screener, _task_earnings_trade_analyzer,
        _task_exhaustion_hammer, _task_momentum_burst, _task_episodic_pivot,
        _task_vcp_screener, _task_canslim, _task_dividend_growth_pullback,
        _task_value_dividend, _task_20pct_study, _task_macro_calendar,
        _task_institutional_flow, _task_put_call_ratio, _task_market_movers,
        _task_chart_vision,
    ]

    _market_movers_context = ""
    _chart_images: Optional[Dict[str, bytes]] = None
    if not _origin_is_recent:
        calibration_summary["put_call_data"] = {"available": False, "reason": "historical_replay"}

    _enrichment_executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(_enrichment_tasks))
    _enrichment_futures = {_enrichment_executor.submit(_task): _task for _task in _enrichment_tasks}
    _enrichment_done, _enrichment_not_done = concurrent.futures.wait(
        _enrichment_futures.keys(), timeout=_ENRICHMENT_BATCH_TIMEOUT_S
    )
    for _future in _enrichment_done:
        _task = _enrichment_futures[_future]
        try:
            _task_result = _future.result() or {}
        except Exception as exc:
            _task_result = {"warning": (_task.__name__.replace("_task_", ""), f"{type(exc).__name__}: {exc}")}
        if _task_result.get("feature"):
            feature_packet.update(_task_result["feature"])
        if _task_result.get("warning"):
            _w_key, _w_val = _task_result["warning"]
            _context_enrichment_warnings[_w_key] = _w_val
        if "put_call_data" in _task_result:
            calibration_summary["put_call_data"] = _task_result["put_call_data"]
        if "market_movers_context" in _task_result:
            _market_movers_context = _task_result["market_movers_context"]
        if "chart_images" in _task_result:
            _chart_images = _task_result["chart_images"]
    for _future in _enrichment_not_done:
        _task = _enrichment_futures[_future]
        _context_enrichment_warnings[_task.__name__.replace("_task_", "")] = (
            f"Did not complete within {_ENRICHMENT_BATCH_TIMEOUT_S}s enrichment budget."
        )
    _enrichment_executor.shutdown(wait=False)

    # Earnings-window warning for the prompt. Previously called the RapidAPI
    # tradingview_calendar endpoint here, confirmed dead this session (404,
    # not a valid path on the subscribed product) -- removed rather than left
    # as silent-failing dead weight. Phase 3's Alpha Vantage earnings_days_away
    # (feature_packet, set above) already covers this same underlying need
    # for non-index symbols via a working, verified source.
    _earnings_warning = ""
    _earn_days = feature_packet.get("earnings_days_away")
    if _earn_days is not None and 0 <= _earn_days <= horizon_days:
        _earnings_warning = (
            f"EARNINGS WARNING: {symbol} has earnings {_earn_days} day(s) into the prediction window "
            "(source: Alpha Vantage EARNINGS, verified historical reported dates). Earnings events cause "
            "high volatility and often invalidate technical predictions. Raise risk_score by 15-20 and "
            "lower confidence_score accordingly."
        )

    # Phase 4 — yfinance earnings gate (supplement tradingview calendar). yfinance's
    # `.calendar` always reports the real-world upcoming earnings date relative to
    # TODAY, not to origin_str, so it must not run for a historical replay.
    if not _earnings_warning and _origin_is_recent:
        try:
            _yf_earn_warn = _get_earnings_warning(symbol, origin_str, target_str or origin_str)
            if _yf_earn_warn:
                _earnings_warning = _yf_earn_warn
        except Exception:
            pass

    # Call Gemini consensus engine -- Phase 1 (triple call, majority vote) by
    # default, or an opt-in alternative aggregation: Component 5's bull/bear
    # debate consensus (ENABLE_DEBATE_CONSENSUS) or judge-based selection
    # (ENABLE_JUDGE_AGGREGATION, see that function's docstring). Both are
    # experimental; debate takes precedence if a caller somehow sets both,
    # since it was the earlier-validated of the two opt-in paths.
    if ENABLE_DEBATE_CONSENSUS:
        _consensus_fn = _call_gemini_debate_consensus
    elif ENABLE_DIVERSE_CONSENSUS:
        # Handles ENABLE_JUDGE_AGGREGATION internally too (judge over
        # genuinely diverse candidates, if both flags are set).
        _consensus_fn = _call_gemini_diverse_consensus
    elif ENABLE_JUDGE_AGGREGATION:
        _consensus_fn = _call_gemini_judge_consensus
    else:
        _consensus_fn = _call_gemini_consensus
    gemini_result = _consensus_fn(
        spi, feature_packet, calibration_summary, origin_price, initial_cap,
        earnings_warning=_earnings_warning,
        market_movers_context=_market_movers_context,
        chart_images=_chart_images,
    )

    if gemini_result.get("status") != "SUCCESS":
        return _error_result(
            spi, input_hash,
            f"Gemini prediction unavailable. {gemini_result.get('error', 'Unknown error')}",
            extra={
                "gemini_used":       gemini_result.get("gemini_used", False),
                "ai_provider":       "gemini",
                "gemini_latency_ms": gemini_result.get("gemini_latency_ms", 0),
            },
        )

    # Research Expansion Program, Component 4 -- fold the LLM-generated
    # structured scores into feature_packet (the one place ML feature
    # extraction already reads from, feature_packet_to_vector/FEATURE_SPEC in
    # ml_feature_extractor.py) rather than inventing a second feature source.
    # These are only available post-prediction (they're Gemini's OUTPUT, not
    # a pre-prediction input), which is fine -- the stored _feature_packet
    # snapshot happens after this point, at the end of this function.
    feature_packet["bull_conviction_score"] = gemini_result.get("bull_conviction_score")
    feature_packet["bear_conviction_score"] = gemini_result.get("bear_conviction_score")
    feature_packet["narrative_dependency_score"] = gemini_result.get("narrative_dependency_score")

    # Phase 4 — ML signal cross-check. Logged alongside every prediction for
    # comparison (ml_signal_shadow), and -- ONLY on segments with their own
    # dedicated trained model, and ONLY when ENABLE_ML_SEGMENT_OVERRIDE is on
    # -- allowed to override decision/return/price fields. Motivated by this
    # session's own repeated finding that a simpler, older baseline model
    # beats the newer triple-consensus architecture (most recently: 64.3% vs
    # 35.7% direction match on the 5 segments with dedicated models, n=14).
    # Every other segment stays shadow-only (logged, never acted on) since
    # there's no supporting evidence there. Absent model (not yet trained --
    # see ml_training_runner.py) is the normal, expected state, not an error.
    # Runs here (not inside _call_gemini_consensus) so feature_packet already
    # includes Component 4's LLM-alpha scores above.
    try:
        from ml_signal_model import load_model, predict_proba, SegmentedModel
        from ml_feature_extractor import feature_packet_to_vector
        from segment_reliability import segment_label as _segment_label_fn
        _ml_model = load_model()
        if _ml_model is not None:
            _ml_vec = feature_packet_to_vector(feature_packet)
            if _ml_vec is not None:
                _seg = _segment_label_fn(symbol, horizon_days)
                _ml_pred = predict_proba(_ml_model, _ml_vec, segment_label=_seg)
                if _ml_pred is not None:
                    _ml_pred["agrees_with_final_decision"] = (_ml_pred["decision"] == gemini_result.get("decision"))
                    _ml_pred["segment"] = _seg
                    gemini_result["ml_signal_shadow"] = _ml_pred

                    _has_dedicated_segment_model = (
                        isinstance(_ml_model, SegmentedModel) and _seg in _ml_model.models
                    )
                    gemini_result = _apply_ml_segment_override(
                        gemini_result, _ml_pred, _has_dedicated_segment_model,
                        origin_price, initial_cap, ENABLE_ML_SEGMENT_OVERRIDE,
                    )
    except Exception as _ml_exc:
        gemini_result["ml_signal_shadow_error"] = f"{type(_ml_exc).__name__}: {_ml_exc}"

    # Phase 11 — Low Confidence Skip Gate
    # If all 3 consensus calls disagree, the signal is noise — do not generate a trade.
    # Exception: every attempted call landing on HOLD (0 BUY, 0 SELL votes) is
    # UNANIMOUS agreement, not a conflict -- e.g. the CAPITULATION GUARD in
    # _apply_guardrails deterministically downgrades all 3 calls together
    # whenever the same feature packet triggers it. That's a coherent "don't
    # trade this" signal and should surface as a real HOLD decision, not be
    # mislabeled as ambiguous noise and skipped.
    _votes = gemini_result.get("consensus_votes", {})
    _unanimous_hold = _votes.get("BUY", 0) == 0 and _votes.get("SELL", 0) == 0 and _votes.get("HOLD", 0) > 0
    if gemini_result.get("consensus_confidence") == "LOW" and not _unanimous_hold:
        return _error_result(
            spi, input_hash,
            (
                "SKIP — INSUFFICIENT SIGNAL QUALITY: All 3 Gemini consensus calls produced "
                "conflicting directions. This means the market data is ambiguous and no reliable "
                "prediction can be made. Skipping this trade to avoid a coin-flip prediction. "
                f"Votes: {gemini_result.get('consensus_votes', {})}. "
                "Try a different date range or symbol."
            ),
            extra={
                "gemini_used":        True,
                "ai_provider":        "gemini",
                "skip_reason":        "LOW_CONSENSUS_CONFIDENCE",
                "consensus_votes":    gemini_result.get("consensus_votes", {}),
                "consensus_calls":    gemini_result.get("consensus_calls", []),
                "gemini_latency_ms":  gemini_result.get("gemini_latency_ms", 0),
            },
        )

    pred_return  = gemini_result["predicted_return_pct"]
    pred_target  = gemini_result["predicted_target_price"]
    pred_capital = gemini_result["predicted_final_capital"]
    pred_pl      = gemini_result["predicted_total_pl"]

    from stock_comparison_engine import validate_no_leakage as _ck
    leakage_check = _ck(history, origin_str).get("status", "UNKNOWN")

    # Phase 1 — calibrated confidence: self-reported confidence_score is
    # inversely correlated with correctness (confirmed this session: 80-100%
    # stated confidence -> 40.0% actual direction match, n=25; 40-59% stated
    # confidence -> 62.1% actual). Map the raw score to what predictions at
    # that confidence level have ACTUALLY been right, from the static
    # snapshot built by confidence_calibration_builder.py -- same
    # staleness caveat as data/calibration_profiles.json, re-run periodically.
    _calibrated_confidence = None
    try:
        _cal_map_path = ROOT / "data" / "confidence_calibration_map.json"
        if _cal_map_path.exists():
            from confidence_calibrator import calibrate as _calibrate_confidence
            _cal_map = json.loads(_cal_map_path.read_text(encoding="utf-8"))
            _calibrated_confidence = _calibrate_confidence(gemini_result["confidence_score"], _cal_map)
    except Exception:
        _calibrated_confidence = None

    # Signal-quality layer -- this project's own live DB shows predicted-move
    # SIZE is inversely related to correctness too (<2% predicted move: 73.6%
    # direction-match, n=129; 2-5%: 48.9%, n=350; >5%: 48.3%, n=265), the same
    # inverted pattern already fixed for stated confidence above. Combines
    # both calibrated hit rates into one display-only tier -- never changes
    # decision/predicted_return_pct/target_price, purely additive, exactly
    # the "sit on top of each raw prediction, never replace it" requirement.
    _magnitude_calibrated_hit_rate = None
    try:
        _mag_map_path = ROOT / "data" / "magnitude_calibration_map.json"
        if _mag_map_path.exists():
            from magnitude_calibrator import calibrate_magnitude as _calibrate_magnitude
            _mag_map = json.loads(_mag_map_path.read_text(encoding="utf-8"))
            _magnitude_calibrated_hit_rate = _calibrate_magnitude(gemini_result.get("predicted_return_pct"), _mag_map)
    except Exception:
        _magnitude_calibrated_hit_rate = None

    try:
        from magnitude_calibrator import signal_quality_tier as _signal_quality_tier
        _signal_quality = _signal_quality_tier(_calibrated_confidence, _magnitude_calibrated_hit_rate)
    except Exception:
        _signal_quality = {"signal_quality_score": None, "signal_quality_tier": "UNKNOWN"}

    # Position sizing -- see core/position_sizing.py for why this exists and
    # why it insists on calibrated_confidence over the raw, confirmed-
    # inversely-correlated confidence_score whenever a calibration map is
    # available.
    try:
        from position_sizing import compute_position_size
        _recommended_position = compute_position_size(
            decision=gemini_result["decision"],
            initial_capital=initial_cap,
            confidence_score=gemini_result.get("confidence_score"),
            calibrated_confidence_score=_calibrated_confidence,
            risk_score=gemini_result.get("risk_score"),
            trend_regime=(feature_packet.get("trend") or {}).get("trend_regime"),
            signal_quality_tier=_signal_quality.get("signal_quality_tier"),
        )
    except Exception as _pos_exc:
        _recommended_position = {"status": "ERROR", "reason": f"{type(_pos_exc).__name__}: {_pos_exc}"}

    # Gemini reasoning (combine assessments)
    reasoning_parts = [
        gemini_result.get("reasoning") or "",
        gemini_result.get("trend_assessment") or "",
        gemini_result.get("momentum_assessment") or "",
    ]
    reasoning = " | ".join(p for p in reasoning_parts if p)[:800] or "Gemini prediction completed."

    # Price range + which-day-within-the-window prediction (range_timing_predictor.py).
    # Deterministic -- no extra Gemini call. The range half is backtested at
    # 77% band-containment and generalizes to any horizon (ATR x sqrt(horizon)
    # scaling). The day-offset half is only swapped to the KNN precedent model
    # (measured ~52%/~48% within-+/-1-day hit rate) for horizons close to the
    # 7d window it was actually validated on -- outside that range its day
    # guesses would be silently miscalibrated, so they're left unconfident
    # (None) rather than implying a backtested number that doesn't apply.
    _range_timing: dict = {}
    try:
        from range_timing_predictor import (
            predict_price_range_and_timing, predict_day_offset_knn, load_range_timing_training_set,
        )
        _rt_pred = predict_price_range_and_timing(feature_packet)
        if _rt_pred.get("status") == "OK":
            _range_timing = {
                "predicted_low_price":       _rt_pred["predicted_low_price"],
                "predicted_high_price":      _rt_pred["predicted_high_price"],
                "predicted_low_day_offset":  _rt_pred["predicted_low_day_offset"],
                "predicted_high_day_offset": _rt_pred["predicted_high_day_offset"],
                "range_basis":               _rt_pred["range_basis"],
                "day_timing_source":         "rule_based",
                "low_day_within_1_confidence_pct":  None,
                "high_day_within_1_confidence_pct": None,
            }
            if 3 <= horizon_days <= 10:
                _training_cases = load_range_timing_training_set()
                if _training_cases:
                    from ml_feature_extractor import feature_packet_to_vector
                    _vec = feature_packet_to_vector(feature_packet)
                    _knn = predict_day_offset_knn(_vec, _training_cases) if _vec else {"status": "INSUFFICIENT"}
                    if _knn.get("status") == "OK":
                        _range_timing["predicted_low_day_offset"]  = _knn["predicted_low_day_offset"]
                        _range_timing["predicted_high_day_offset"] = _knn["predicted_high_day_offset"]
                        _range_timing["day_timing_source"] = "knn_precedent"
                        _range_timing["low_day_within_1_confidence_pct"]  = _knn["low_day_within_1_confidence_pct"]
                        _range_timing["high_day_within_1_confidence_pct"] = _knn["high_day_within_1_confidence_pct"]
                        _range_timing["day_timing_basis"] = _knn["basis"]

            # Conformal widening -- OPT-IN, see ENABLE_CONFORMAL_RANGE docstring.
            # Never replaces the raw predicted_low/high_price fields; adds
            # conformal_low/high_price alongside them.
            if ENABLE_CONFORMAL_RANGE and _range_timing.get("predicted_low_price") is not None:
                try:
                    from conformal_range_calibrator import apply_conformal_widening
                    _conf_path = ROOT / "data" / "conformal_range_calibration.json"
                    if _conf_path.exists():
                        _conf_data = json.loads(_conf_path.read_text(encoding="utf-8"))
                        _conf_fit = (_conf_data.get("by_target_coverage") or {}).get(CONFORMAL_TARGET_COVERAGE)
                        if _conf_fit and _conf_fit.get("multiplier"):
                            _conf_out = apply_conformal_widening(
                                _range_timing["predicted_low_price"],
                                _range_timing["predicted_high_price"],
                                _conf_fit["multiplier"],
                            )
                            _range_timing.update(_conf_out)
                            _range_timing["conformal_target_coverage"] = CONFORMAL_TARGET_COVERAGE
                except Exception as _conf_exc:
                    _context_enrichment_warnings["conformal_range"] = f"{type(_conf_exc).__name__}: {_conf_exc}"
    except Exception as exc:
        _context_enrichment_warnings["range_timing"] = f"{type(exc).__name__}: {exc}"

    # Day-by-day predicted price path -- ALWAYS computed, for EVERY
    # prediction (not opt-in): extends the already-live ATR-sqrt(time) range
    # math (range_timing above) to every day in the horizon, not just the
    # terminal low/high. See day_by_day_path_predictor.py's own
    # methodology_note for the honest disclosure of what this is (a real
    # formula interpolation between two real endpoints) and isn't (a fresh
    # AI forecast per day).
    _daily_price_path: dict = {"path": [], "methodology_note": ""}
    _stock_entry_exit: dict = {}
    try:
        from day_by_day_path_predictor import predict_daily_path, best_entry_exit_days
        _atr_daily_pct = (feature_packet.get("volatility") or {}).get("ATR_daily_pct")
        _daily_price_path = predict_daily_path(
            origin_price, pred_return, horizon_days, atr_daily_pct=_atr_daily_pct,
        )
        if _daily_price_path.get("path"):
            _stock_entry_exit = best_entry_exit_days(
                _daily_price_path["path"], bullish=(pred_return is not None and pred_return >= 0),
            )
    except Exception as exc:
        _context_enrichment_warnings["daily_price_path"] = f"{type(exc).__name__}: {exc}"

    # Day-by-day options valuation -- only when the caller passes an
    # explicit options_evaluation spec on spi (strike/option_type/dte/
    # contracts, optionally premium_paid_per_share for an already-owned
    # position). Separate from the existing TT-integrated strike-selection
    # options_params (which resolves a strike via delta/premium targeting
    # against a real or Black-Scholes-fallback chain for a different,
    # heavier backtest flow) -- this is the simple, explicit-parameter path
    # for "I already know my strike/DTE/premium, show me the daily path."
    _options_daily_path: Optional[dict] = None
    _opts_eval = spi.get("options_evaluation") or {}
    if _opts_eval.get("strike") and _opts_eval.get("option_type") and _opts_eval.get("dte") and _daily_price_path.get("path"):
        try:
            from options_path_evaluator import evaluate_options_path
            _annual_vol = (feature_packet.get("volatility") or {}).get("annualized_volatility")
            _rfr = feature_packet.get("treasury_10y_yield_pct")
            _options_daily_path = evaluate_options_path(
                _daily_price_path["path"],
                strike=float(_opts_eval["strike"]),
                option_type=str(_opts_eval["option_type"]),
                dte_at_day0=int(_opts_eval["dte"]),
                contracts=int(_opts_eval.get("contracts", 1)),
                annual_volatility_pct=_annual_vol or 30.0,
                premium_paid_per_share=_opts_eval.get("premium_paid_per_share"),
                risk_free_rate_pct=_rfr or 4.0,
            )
        except Exception as exc:
            _context_enrichment_warnings["options_daily_path"] = f"{type(exc).__name__}: {exc}"

    return {
        "status":                       "SUCCESS",
        "source":                       "gemini_stock_prediction_agent",
        "model_version":                "gemini_stock_prediction_agent_v1",
        "ai_provider":                  "gemini",
        "gemini_used":                  True,
        "model_name":                   GEMINI_MODEL,
        "gemini_latency_ms":            gemini_result.get("gemini_latency_ms", 0),
        "prompt_hash":                  gemini_result.get("prompt_hash", ""),
        "gemini_output_hash":           gemini_result.get("gemini_output_hash", ""),
        "stock_prediction_input_hash":  input_hash,
        "symbol":                       symbol,
        "requested_ctx_start":          spi.get("historical_context_start_date"),
        "effective_ctx_start":          feature_packet.get("effective_ctx_start") or spi.get("historical_context_start_date"),
        "historical_context_start_date": feature_packet.get("effective_ctx_start") or spi.get("historical_context_start_date"),
        "prediction_origin_date":       origin_str,
        "effective_origin_date":        eff_origin_date,
        "target_date":                  target_str,
        "decision_horizon_days":        horizon_days,
        "price_basis":                  str(spi.get("price_basis", "close") or "close"),
        "origin_price_used":            round(origin_price, 4),
        "predicted_target_price":       pred_target,
        "predicted_return_pct":         pred_return,
        "initial_capital":              initial_cap,
        "predicted_final_capital":      pred_capital,
        "predicted_total_pl":           pred_pl,
        "decision":                     gemini_result["decision"],
        "decision_reason":              gemini_result["decision_reason"],
        "confidence_score":             gemini_result["confidence_score"],
        "calibrated_confidence_score":  _calibrated_confidence,
        "magnitude_calibrated_hit_rate": _magnitude_calibrated_hit_rate,
        "signal_quality_score":         _signal_quality.get("signal_quality_score"),
        "signal_quality_tier":          _signal_quality.get("signal_quality_tier"),
        "leakage_probe":                _leakage_probe_result,
        "daily_price_path":             _daily_price_path.get("path", []),
        "daily_price_path_methodology_note": _daily_price_path.get("methodology_note", ""),
        "stock_entry_exit_recommendation": _stock_entry_exit,
        "options_daily_path":           _options_daily_path,
        "recommended_position":         _recommended_position,
        "risk_score":                   gemini_result["risk_score"],
        "data_quality_score":           gemini_result["data_quality_score"],
        "signal_scores":                gemini_result.get("signal_scores", {}),
        "bull_conviction_score":        gemini_result.get("bull_conviction_score"),
        "bear_conviction_score":        gemini_result.get("bear_conviction_score"),
        "narrative_dependency_score":   gemini_result.get("narrative_dependency_score"),
        "latest_date_seen_by_ai":       history[-1]["date"] if history else origin_str,
        "target_price_hidden_from_ai":  True,
        "leakage_check":                leakage_check,
        "reasoning":                    reasoning,
        "trend_assessment":             gemini_result.get("trend_assessment", ""),
        "momentum_assessment":          gemini_result.get("momentum_assessment", ""),
        "volatility_assessment":        gemini_result.get("volatility_assessment", ""),
        "benchmark_assessment":         gemini_result.get("benchmark_assessment", ""),
        "bull_case":                    gemini_result.get("bull_case", ""),
        "bear_case":                    gemini_result.get("bear_case", ""),
        "why_not_opposite":             gemini_result.get("why_not_opposite", ""),
        "key_features_used":                gemini_result.get("key_features_used", []),
        "data_limitations":                 gemini_result.get("data_limitations", []),
        "options_strategy_assessment":      gemini_result.get("options_strategy_assessment", ""),
        "recommended_trade_config":         gemini_result.get("recommended_trade_config", {}),
        "needs_human_review":               gemini_result.get("needs_human_review", False),
        "chain_of_thought":                 gemini_result.get("chain_of_thought", ""),
        "consensus_votes":                  gemini_result.get("consensus_votes", {}),
        "consensus_confidence":             gemini_result.get("consensus_confidence", ""),
        "consensus_calls":                  gemini_result.get("consensus_calls", []),
        "aggregation_method":               gemini_result.get("aggregation_method", "majority_vote"),
        "judge_chosen_call":                gemini_result.get("judge_chosen_call"),
        "judge_reasoning":                  gemini_result.get("judge_reasoning"),
        "judge_confidence":                 gemini_result.get("judge_confidence"),
        "judge_model":                      gemini_result.get("judge_model"),
        "technical_override_score":         gemini_result.get("technical_override_score", {}),
        "ml_signal_shadow":                 gemini_result.get("ml_signal_shadow"),
        "debate_transcript":                gemini_result.get("debate_transcript"),
        "market_movers_used":           bool(_market_movers_context),
        "chart_vision_used":            bool(_chart_images),
        "context_enrichment_warnings":  _context_enrichment_warnings,
        "predicted_low_price":              _range_timing.get("predicted_low_price"),
        "predicted_high_price":             _range_timing.get("predicted_high_price"),
        "predicted_low_day_offset":         _range_timing.get("predicted_low_day_offset"),
        "predicted_high_day_offset":        _range_timing.get("predicted_high_day_offset"),
        "range_timing":                     _range_timing,
        "_feature_packet":              feature_packet,
        "_calibration_summary":         calibration_summary,
        "_gemini_raw_json":             gemini_result.get("gemini_raw_json", {}),
        "features_used": {
            "RSI_14":           feature_packet["momentum"]["RSI_14"],
            "MACD":             feature_packet["momentum"]["MACD"],
            "return_5d":        feature_packet["returns"]["return_5d"],
            "return_20d":       feature_packet["returns"]["return_20d"],
            "return_60d":       feature_packet["returns"]["return_60d"],
            "annualized_vol":   feature_packet["volatility"]["annualized_volatility"],
            "trend_regime":     feature_packet["trend"]["trend_regime"],
            "reversal_risk":    feature_packet["reversal_signals"]["reversal_risk"],
            "bars_used":        feature_packet["n_bars"],
            "last_ai_bar_date": history[-1]["date"] if history else origin_str,
        },
    }


def _error_result(spi: dict, input_hash: str, error_msg: str, extra: dict = None) -> dict:
    result = {
        "status":                       "FAILED",
        "source":                       "gemini_stock_prediction_agent",
        "model_version":                "gemini_stock_prediction_agent_v1",
        "ai_provider":                  "gemini",
        "gemini_used":                  False,
        "stock_prediction_input_hash":  input_hash,
        "symbol":                       str(spi.get("symbol", "") or ""),
        "prediction_origin_date":       str(spi.get("prediction_origin_date", "") or ""),
        "target_date":                  str(spi.get("target_date", "") or ""),
        "decision":                     "REVIEW",
        "confidence_score":             0,
        "data_quality_score":           0,
        "risk_score":                   0,
        "target_price_hidden_from_ai":  True,
        "error":                        error_msg,
        "predicted_target_price":       None,
        "predicted_return_pct":         None,
        "predicted_final_capital":      None,
        "predicted_total_pl":           None,
    }
    if extra:
        result.update(extra)
    return result
