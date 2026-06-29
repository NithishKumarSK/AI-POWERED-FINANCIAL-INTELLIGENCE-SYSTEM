"""
Strategy Prediction Agent v3 — Backtest Surrogate Calibrated
Predicts the outcome of the SAME options strategy as tastytrade backtesting.
Uses: StrategyInput + RapidAPI market context + calibrated options math +
      empirical calibration from historical similar-strategy backtest records.
Three-stage: (1) Raw Prior Model → (2) Calibration Dataset → (3) Calibrated Output.
NO yfinance. NO backtest result leakage. NO fake data. NO random values.
Model version: strategy_predictor_v3_backtest_surrogate_calibrated
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

MODEL_VERSION       = "strategy_predictor_v3_backtest_surrogate_calibrated"
CALCULATION_VERSION = "3.0"
EVAL_FILE           = ROOT / "strategy_prediction_evaluation_runs.jsonl"

REQUIRED_FIELDS = [
    "symbol", "start_date", "end_date", "initial_capital",
    "benchmark", "direction", "side", "dte", "delta",
    "legs", "entry_frequency", "decision_horizon",
]

# ── In-memory RapidAPI cache (15-min TTL per symbol) ─────────────────────────
_RAPIDAPI_CACHE: Dict[str, Dict] = {}
_CACHE_TTL = 15 * 60  # 15 minutes


# ══════════════════════════════════════════════════════════════════════════════
# IDENTITY / VALIDATION
# ══════════════════════════════════════════════════════════════════════════════
def build_strategy_input_hash(strategy_input: dict) -> str:
    """SHA-256[:16] of canonical sorted-key JSON. Both AI and Backtest show this same hash."""
    subset = {k: strategy_input[k] for k in sorted(REQUIRED_FIELDS) if k in strategy_input}
    return hashlib.sha256(json.dumps(subset, sort_keys=True).encode()).hexdigest()[:16]


def validate_strategy_input(si: dict) -> Tuple[bool, str]:
    for f in REQUIRED_FIELDS:
        if f not in si or si[f] is None or si[f] == "":
            return False, f"Missing required field: {f}"
    try:
        if int(si["delta"]) < 1 or int(si["delta"]) > 99:
            return False, f"delta must be 1-99, got {si['delta']}"
        if int(si["dte"]) < 1 or int(si["dte"]) > 365:
            return False, f"dte must be 1-365, got {si['dte']}"
        if float(si["initial_capital"]) <= 0:
            return False, f"initial_capital must be positive, got {si['initial_capital']}"
        if int(si["legs"]) < 1 or int(si["legs"]) > 10:
            return False, f"legs must be 1-10, got {si['legs']}"
        if si["direction"] not in ("short", "long"):
            return False, f"direction must be 'short' or 'long', got {si['direction']}"
        if si["side"] not in ("put", "call"):
            return False, f"side must be 'put' or 'call', got {si['side']}"
    except (TypeError, ValueError) as e:
        return False, f"Invalid numeric field: {e}"
    return True, ""


# ══════════════════════════════════════════════════════════════════════════════
# DATE UTILITIES
# ══════════════════════════════════════════════════════════════════════════════
def _parse_date(s: str) -> datetime:
    return datetime.strptime(str(s).strip(), "%Y-%m-%d")


def _get_years(start_date: str, end_date: str) -> float:
    return max(0.01, (_parse_date(end_date) - _parse_date(start_date)).days / 365.25)


def _get_trade_count(start_date: str, end_date: str, entry_frequency: str) -> int:
    delta_days = (_parse_date(end_date) - _parse_date(start_date)).days
    freq = str(entry_frequency).lower()
    if "month" in freq:
        return max(1, round(delta_days / 30))
    elif "week" in freq:
        return max(1, round(delta_days / 7))
    elif "day" in freq:
        return max(1, round(delta_days * 252 / 365))
    return max(1, round(delta_days / 30))


# ══════════════════════════════════════════════════════════════════════════════
# RAPIDAPI CONTEXT (cached)
# ══════════════════════════════════════════════════════════════════════════════
def _fetch_rapidapi_context(symbol: str) -> dict:
    """Raw fetch from RapidAPI. Never raises."""
    base_ctx: dict = {
        "gainers": [], "losers": [], "active": [],
        "news": [], "movers_available": False, "news_available": False,
        "endpoint_results": {}
    }
    try:
        from rapidapi_client import rapidapi_get

        def _parse_symbols(result: dict) -> list:
            if result.get("status") != "SUCCESS":
                return []
            data = result.get("data", {})
            if isinstance(data, dict):
                symbols = data.get("symbols", [])
                return [
                    s.get("s", "").split(":")[-1]
                    for s in symbols if isinstance(s, dict) and s.get("s")
                ]
            return []

        gainers_r = rapidapi_get("/market/get-movers",
                                  params={"exchange": "US", "name": "percent_change_gainers", "locale": "en"},
                                  timeout=20)
        losers_r  = rapidapi_get("/market/get-movers",
                                  params={"exchange": "US", "name": "percent_change_losers", "locale": "en"},
                                  timeout=20)
        active_r  = rapidapi_get("/market/get-movers",
                                  params={"exchange": "US", "name": "volume_gainers", "locale": "en"},
                                  timeout=20)
        news_r    = rapidapi_get("/news/list", params={"lang": "en"}, timeout=20)

        gainers = _parse_symbols(gainers_r)
        losers  = _parse_symbols(losers_r)
        active  = _parse_symbols(active_r)
        news    = news_r.get("data", []) if news_r.get("status") == "SUCCESS" else []
        news    = news if isinstance(news, list) else []

        movers_ok = (gainers_r.get("status") == "SUCCESS" or
                     losers_r.get("status") == "SUCCESS" or
                     active_r.get("status") == "SUCCESS")

        base_ctx.update({
            "gainers": gainers,
            "losers": losers,
            "active": active,
            "news": news[:50],
            "movers_available": movers_ok,
            "news_available": news_r.get("status") == "SUCCESS",
            "endpoint_results": {
                "/market/get-movers (gainers)": gainers_r.get("status"),
                "/market/get-movers (losers)":  losers_r.get("status"),
                "/market/get-movers (active)":  active_r.get("status"),
                "/news/list":                   news_r.get("status"),
            }
        })
    except Exception as exc:
        base_ctx["error"] = str(exc)
    return base_ctx


def _get_rapidapi_context(symbol: str, cache_key: str = "") -> dict:
    """
    Return RapidAPI context, using 15-minute in-memory cache.
    Same symbol+cache_key returns identical context within the TTL window
    → deterministic predictions for repeated runs.
    """
    key = f"{symbol.upper()}_{cache_key}"
    cached = _RAPIDAPI_CACHE.get(key)
    if cached and (time.time() - cached["ts"]) < _CACHE_TTL:
        return cached["ctx"]
    ctx = _fetch_rapidapi_context(symbol)
    _RAPIDAPI_CACHE[key] = {"ctx": ctx, "ts": time.time()}
    return ctx


# ══════════════════════════════════════════════════════════════════════════════
# CALIBRATION (historical records)
# ══════════════════════════════════════════════════════════════════════════════
def _load_calibration_records(exclude_hash: Optional[str] = None) -> list:
    """
    Load calibration records from JSONL.
    Accepts BOTH evaluation records (strategy_backtest_verification) and
    calibration probe records (strategy_calibration_backtest).

    For evaluation records: any model_version is OK — backtest_actual is
    always from tastytrade, so the empirical data is valid regardless of
    which AI model version made the original prediction.

    For calibration probes: any model_version is OK — these are also
    from tastytrade (mini backtest runs).

    Excludes:
    - current run's hash (no leakage)
    - records with failed/null backtests (decision=REVIEW, no return data)
    """
    records = []
    if not EVAL_FILE.exists():
        return records
    try:
        with open(EVAL_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    source = r.get("source", "")
                    if source not in ("strategy_backtest_verification",
                                      "strategy_calibration_backtest"):
                        continue
                    if exclude_hash and r.get("strategy_input_hash") == exclude_hash:
                        continue
                    bt = r.get("backtest_actual", {}) or {}
                    if not bt:
                        continue
                    # Require real backtest data: valid decision AND return value
                    has_return   = (bt.get("actual_total_return_pct") is not None or
                                    bt.get("total_return_pct") is not None)
                    has_decision = bt.get("decision") not in (None, "REVIEW", "MISSING", "")
                    has_passed   = bool(bt.get("passed_validation", False))
                    if not (has_passed or (has_return and has_decision)):
                        continue
                    records.append(r)
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return records


def _delta_bucket(d: int) -> int:
    return 0 if d <= 20 else 1 if d <= 35 else 2 if d <= 50 else 3


def _dte_bucket(d: int) -> int:
    return 0 if d <= 20 else 1 if d <= 35 else 2 if d <= 60 else 3


def _freq_bucket(f: str) -> int:
    f = str(f).lower()
    return 0 if "day" in f else 1 if "week" in f else 2


def _compute_similarity(si_a: dict, si_b: dict) -> float:
    """
    Compute strategy similarity score [0.0, 1.0].
    Weights: direction+side (most important) > delta bucket > symbol > DTE+legs+freq.
    """
    score = 0.0
    if str(si_a.get("direction","")).lower() == str(si_b.get("direction","")).lower():
        score += 0.20
    if str(si_a.get("side","")).lower() == str(si_b.get("side","")).lower():
        score += 0.20
    if _delta_bucket(int(si_a.get("delta", 30))) == _delta_bucket(int(si_b.get("delta", 30))):
        score += 0.15
    if str(si_a.get("symbol","")).upper() == str(si_b.get("symbol","")).upper():
        score += 0.15
    if _dte_bucket(int(si_a.get("dte", 45))) == _dte_bucket(int(si_b.get("dte", 45))):
        score += 0.10
    if int(si_a.get("legs", 1)) == int(si_b.get("legs", 1)):
        score += 0.10
    if _freq_bucket(si_a.get("entry_frequency","monthly")) == _freq_bucket(si_b.get("entry_frequency","monthly")):
        score += 0.10
    return round(score, 3)


def _get_calibration_bias(si: dict, input_hash: str) -> dict:
    """
    Find similar past records and compute weighted calibration signal.
    Uses backtest_actual records with similarity >= 0.50 (v3 threshold).
    NEVER reads current run's backtest result.
    """
    records     = _load_calibration_records(exclude_hash=input_hash)
    similar: list = []
    for r in records:
        sim = _compute_similarity(si, r.get("strategy_input", {}))
        if sim >= 0.50:
            bt = r.get("backtest_actual", {})
            similar.append((sim, r, bt))

    n = len(similar)
    if n < 2:
        return {"has_calibration": False, "similar_count": n,
                "calibration_weight": 0.0, "raw_weight": 1.0}

    total_weight = sum(s for s, _, _ in similar)
    if total_weight == 0:
        return {"has_calibration": False, "similar_count": 0,
                "calibration_weight": 0.0, "raw_weight": 1.0}

    def _wavg(extract_fn) -> Optional[float]:
        total = 0.0; tw = 0.0
        for sim, r, bt in similar:
            val = extract_fn(r, bt)
            if val is not None:
                try:
                    total += sim * float(val); tw += sim
                except (TypeError, ValueError):
                    pass
        return round(total / tw, 3) if tw > 0 else None

    empirical_return  = _wavg(lambda r, bt: bt.get("actual_total_return_pct") or bt.get("total_return_pct"))
    empirical_wr      = _wavg(lambda r, bt: bt.get("actual_win_rate") or bt.get("win_rate"))
    empirical_dd      = _wavg(lambda r, bt: bt.get("actual_max_drawdown") or bt.get("max_drawdown"))

    decisions = [str(bt.get("decision", "REVIEW")).upper() for _, _, bt in similar]
    buy_ct  = decisions.count("BUY")
    sell_ct = decisions.count("SELL")
    hold_ct = decisions.count("HOLD")

    # V3 weight schedule: more calibration data → higher calibration weight
    if n >= 8:   w_cal, w_raw = 0.75, 0.25
    elif n >= 5: w_cal, w_raw = 0.60, 0.40
    elif n >= 3: w_cal, w_raw = 0.45, 0.55
    else:        w_cal, w_raw = 0.20, 0.80  # 2 records

    return {
        "has_calibration":       True,
        "similar_count":         n,
        "calibration_weight":    w_cal,
        "raw_weight":            w_raw,
        "empirical_return":      empirical_return,
        "empirical_win_rate":    empirical_wr,
        "empirical_max_drawdown": empirical_dd,
        "empirical_directional": "positive" if buy_ct >= max(sell_ct, hold_ct) else (
                                  "negative" if sell_ct > max(buy_ct, hold_ct) else "neutral"),
        "buy_count":             buy_ct,
        "sell_count":            sell_ct,
        "hold_count":            hold_ct,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 10 STRATEGY FACTOR SCORES
# ══════════════════════════════════════════════════════════════════════════════
def _compute_factor_scores(si: dict, ctx: dict) -> dict:
    """
    10 strategy-specific factor scores. Every score derives from
    strategy inputs or RapidAPI context. No generic stock analysis.
    """
    symbol     = str(si["symbol"]).upper()
    direction  = str(si["direction"]).lower()
    side       = str(si["side"]).lower()
    delta      = int(si["delta"])
    dte        = int(si["dte"])
    legs       = int(si["legs"])
    freq       = str(si["entry_frequency"]).lower()
    capital    = float(si["initial_capital"])
    start_date = si["start_date"]
    end_date   = si["end_date"]

    gainers     = ctx.get("gainers", [])
    losers      = ctx.get("losers",  [])
    active      = ctx.get("active",  [])
    news        = ctx.get("news",    [])
    trade_count = _get_trade_count(start_date, end_date, freq)
    years       = _get_years(start_date, end_date)

    # 1. Underlying Regime Score
    if symbol in gainers:
        u_sc = 74; u_sig = "Bullish"; u_src = "RapidAPI movers"
        u_exp = f"{symbol} in RapidAPI top gainers — bullish regime"
    elif symbol in losers:
        u_sc = 30; u_sig = "Bearish"; u_src = "RapidAPI movers"
        u_exp = f"{symbol} in RapidAPI top losers — bearish regime"
    elif symbol in active:
        u_sc = 58; u_sig = "Active/Neutral"; u_src = "RapidAPI movers"
        u_exp = f"{symbol} in high-volume list — elevated activity"
    else:
        u_sc = 55; u_sig = "Neutral"; u_src = "StrategyInput-derived"
        u_exp = f"{symbol} not in today's movers — neutral regime assumed"

    # 2. Options Strategy Suitability Score
    if direction == "short" and side == "put":
        if delta <= 20:   s_sc = 80; s_sig = "Highly Supportive"
        elif delta <= 30: s_sc = 72; s_sig = "Supportive"
        elif delta <= 40: s_sc = 60; s_sig = "Moderate"
        else:             s_sc = 44; s_sig = "Elevated Risk"
        s_exp = f"Short put Δ{delta}: premium-selling at {100-delta}% theoretical win prob"
    elif direction == "short" and side == "call":
        s_sc  = 68 if delta <= 30 else 52
        s_sig = "Supportive" if delta <= 30 else "Moderate"
        s_exp = f"Short call Δ{delta}: bearish/neutral premium strategy"
    elif direction == "long":
        s_sc  = 52; s_sig = "Neutral (Directional)"
        s_exp = f"Long {side} Δ{delta}: requires directional conviction"
    else:
        s_sc  = 50; s_sig = "Neutral"; s_exp = "Strategy type baseline"
    s_src = "StrategyInput"

    # 3. Delta Risk Score
    if delta <= 15:   d_sc = 85; d_sig = "Very Low Risk (Deep OTM)"
    elif delta <= 25: d_sc = 75; d_sig = "Low Risk (OTM)"
    elif delta <= 35: d_sc = 65; d_sig = "Moderate Risk"
    elif delta <= 45: d_sc = 50; d_sig = "Elevated Risk (Near ATM)"
    else:             d_sc = 35; d_sig = "High Risk (ATM/ITM)"
    if legs >= 2: d_sc = min(100, d_sc + 6); d_sig += " (Spread caps loss)"
    d_src = "StrategyInput"
    d_exp = f"Δ{delta}, {legs}L: P(OTM at exp) ≈ {100-delta}% — {'spread' if legs >= 2 else 'naked'}"

    # 4. DTE Risk Score
    if dte <= 14:   dte_sc = 55; dte_sig = "High Gamma (Very Short)"
    elif dte <= 21: dte_sc = 62; dte_sig = "Short DTE"
    elif dte <= 50: dte_sc = 76; dte_sig = "Standard (45-50 DTE ideal)"
    elif dte <= 90: dte_sc = 65; dte_sig = "Medium Duration"
    else:           dte_sc = 52; dte_sig = "Long Duration"
    dte_src = "StrategyInput"
    dte_exp = f"DTE {dte}: {'within' if 40 <= dte <= 60 else 'outside'} the 45-50 DTE sweet spot"

    # 5. Entry Frequency Score
    if "month" in freq:   f_sc = 72; f_sig = "Balanced — 1x/month"
    elif "week" in freq:  f_sc = 60; f_sig = "Higher Frequency"
    elif "day" in freq:   f_sc = 44; f_sig = "Very High Frequency"
    else:                 f_sc = 62; f_sig = "Standard"
    f_src = "StrategyInput"
    f_exp = f"{freq.title()} entries: ~{trade_count} trades over {years:.1f}yr"

    # 6. Benchmark Regime Score
    g_ct = len(gainers); l_ct = len(losers)
    if g_ct > l_ct * 1.2:   b_sc = 66; b_sig = "Broad Market Bullish"
    elif l_ct > g_ct * 1.2: b_sc = 38; b_sig = "Broad Market Bearish"
    else:                    b_sc = 54; b_sig = "Mixed Market"
    b_src = "RapidAPI movers" if ctx.get("movers_available") else "StrategyInput-derived"
    b_exp = f"RapidAPI today: {g_ct} gainers vs {l_ct} losers — {si.get('benchmark','SPY')} regime proxy"

    # 7. Volatility / Risk Score
    # Short premium strategies benefit from IV > realized vol
    if direction == "short":
        v_sc = 65; v_sig = "Favourable (IV > RV premium)"
        v_exp = f"Short {side}: IV historically exceeds realized vol → premium-seller edge"
    else:
        v_sc = 50; v_sig = "Neutral (directional vol)"
        v_exp = f"Long {side}: vol must move in direction"
    v_src = "Derived (strategy direction)"

    # 8. News / Sentiment Score
    bull_kw = ["beat","beats","gain","gains","upgrade","upgraded","rises","rise",
               "strong","record","rally","growth","bullish","outperform",
               "positive","breakout","jumped","jumps","soars","buying opportunity",
               "surges","surge","top","best","exceeds","raised","record","high"]
    bear_kw = ["miss","misses","fall","falls","downgrade","downgraded","cuts",
               "cut","loss","losses","concern","probe","lawsuit","decline",
               "declines","bearish","sell","weak","warning","drop","drops",
               "layoffs","layoff","fire","fired","crashes","crash","low","worst",
               "disappoints","disappoint","below","hurt","investigation"]

    bull_ct = bear_ct = sym_ct = 0
    for art in news[:30]:
        title   = (art.get("title", "") or "").lower()
        desc    = (art.get("description", "") or "").lower()
        body    = title + " " + desc
        related = art.get("relatedSymbols", []) or []
        if isinstance(related, list) and any(symbol in str(r.get("symbol","")).upper() for r in related):
            sym_ct += 1
        if any(kw in body for kw in bull_kw): bull_ct += 1
        if any(kw in body for kw in bear_kw): bear_ct += 1

    if bull_ct > bear_ct:
        sent_sc = min(80, 55 + (bull_ct - bear_ct) * 3); sent_sig = "Bullish"
    elif bear_ct > bull_ct:
        sent_sc = max(22, 50 - (bear_ct - bull_ct) * 3); sent_sig = "Bearish"
    elif len(news) > 0:
        sent_sc = 50; sent_sig = "Neutral"
    else:
        sent_sc = 50; sent_sig = "No News Data"
    sent_src = "RapidAPI news" if ctx.get("news_available") else "StrategyInput-derived"
    sent_exp = f"{bull_ct} bullish vs {bear_ct} bearish headlines; {sym_ct} mention {symbol}"

    # 9. Capital Exposure Score
    if legs >= 2:   cap_sc = 70; cap_sig = "Defined Risk (Spread)"
    else:           cap_sc = 50; cap_sig = "Managed Risk (Naked)"
    if capital >= 100_000: cap_sc = min(100, cap_sc + 5)
    elif capital < 10_000: cap_sc = max(0,   cap_sc - 12)
    cap_src = "StrategyInput"
    cap_exp = (f"${capital:,.0f} capital, {legs}L "
               f"{'spread → capped loss' if legs >= 2 else 'naked → managed at 2x premium'}")

    # 10. Strategy Confidence Score
    factor_list = [u_sc, s_sc, d_sc, dte_sc, f_sc, b_sc, v_sc, sent_sc, cap_sc]
    avg         = sum(factor_list) / len(factor_list)
    variance    = sum((s - avg) ** 2 for s in factor_list) / len(factor_list)
    std_dev     = variance ** 0.5
    data_bonus  = 8 if ctx.get("movers_available") else 0
    news_bonus  = 5 if ctx.get("news_available") else 0
    trade_bonus = min(10, trade_count * 0.15)
    conf_sc     = min(100, max(20, round(avg - std_dev * 0.2 + data_bonus + news_bonus + trade_bonus)))
    conf_sig    = "High" if conf_sc >= 70 else ("Moderate" if conf_sc >= 50 else "Low")
    conf_src    = "Derived (factor agreement + data completeness)"
    conf_exp    = (f"{len(factor_list)}/9 input factors; avg={avg:.0f}; "
                   f"std={std_dev:.1f}; data: movers={'✓' if ctx.get('movers_available') else '✗'} "
                   f"news={'✓' if ctx.get('news_available') else '✗'}")

    def _mk(name, sc, sig, src, exp):
        return {"score": sc, "signal": sig, "source": src, "factor": name, "explanation": exp}

    return {
        "underlying_regime":    _mk("Underlying Regime Score",            u_sc,    u_sig,    u_src,    u_exp),
        "strategy_suitability": _mk("Options Strategy Suitability Score", s_sc,    s_sig,    s_src,    s_exp),
        "delta_risk":           _mk("Delta Risk Score",                    d_sc,    d_sig,    d_src,    d_exp),
        "dte_risk":             _mk("DTE Risk Score",                      dte_sc,  dte_sig,  dte_src,  dte_exp),
        "entry_frequency":      _mk("Entry Frequency Score",               f_sc,    f_sig,    f_src,    f_exp),
        "benchmark_regime":     _mk("Benchmark Regime Score",              b_sc,    b_sig,    b_src,    b_exp),
        "volatility_risk":      _mk("Volatility / Risk Score",             v_sc,    v_sig,    v_src,    v_exp),
        "news_sentiment":       _mk("News / Sentiment Score",              sent_sc, sent_sig, sent_src, sent_exp),
        "capital_exposure":     _mk("Capital Exposure Score",              cap_sc,  cap_sig,  cap_src,  cap_exp),
        "strategy_confidence":  _mk("Strategy Confidence Score",           conf_sc, conf_sig, conf_src, conf_exp),
    }


# ══════════════════════════════════════════════════════════════════════════════
# DECISION RULE (spec-compliant)
# ══════════════════════════════════════════════════════════════════════════════
def _apply_decision_rule(total_ret: float, win_rate_pct: float, risk_score: float) -> str:
    """
    BUY:    return > 5%  AND win_rate >= 55  AND risk_score <= 80
    HOLD:   return -5..+5, or mixed signals, or elevated risk with positive return
    SELL:   return < -5%  AND win_rate < 50  (requires BOTH conditions)
    REVIEW: should not arise from normal calculation — defensive only
    """
    if total_ret > 5 and win_rate_pct >= 55 and risk_score <= 80:
        return "BUY"
    if total_ret > 5 and win_rate_pct >= 55:
        return "HOLD"   # good return but elevated risk
    if total_ret >= -5 and win_rate_pct >= 45:
        return "HOLD"
    if total_ret > 0:
        return "HOLD"   # still positive, just less conviction
    if total_ret < -5 and win_rate_pct < 50:
        return "SELL"
    return "HOLD"       # negative return but win_rate ok — cautious hold


# ══════════════════════════════════════════════════════════════════════════════
# COLD-START DETERMINISTIC PROJECTION
# ══════════════════════════════════════════════════════════════════════════════
def _deterministic_projection(si: dict, factors: dict) -> dict:
    """
    Compute all prediction metrics using calibrated options-strategy math.
    No yfinance. No backtest data. No random values. Fully deterministic.

    Key fixes vs v1:
    - loss_mult 2.0 (naked) / 1.5 (spread) — realistic managed trade
    - pos_alloc accounts for DTE/frequency overlap (concurrent open positions)
    - Additive market regime bonus instead of multiplicative scale
    - Decision rule per spec (not risk-score-only SELL)
    """
    direction  = str(si["direction"]).lower()
    side       = str(si["side"]).lower()
    delta      = int(si["delta"])
    dte        = int(si["dte"])
    legs       = int(si["legs"])
    freq       = str(si["entry_frequency"]).lower()
    capital    = float(si["initial_capital"])

    trade_count = _get_trade_count(si["start_date"], si["end_date"], freq)
    years       = _get_years(si["start_date"], si["end_date"])

    # ── Win Rate ──────────────────────────────────────────────────────────
    # Base: P(option expires OTM) ≈ (100-delta)% for short, delta% for long
    base_wr    = (100 - delta) if direction == "short" else float(delta)
    regime_avg = (factors["underlying_regime"]["score"] + factors["benchmark_regime"]["score"]) / 2.0
    regime_adj = (regime_avg - 50) * 0.20   # +/- up to 10pp
    sent_adj   = (factors["news_sentiment"]["score"] - 50) * 0.08
    iv_edge    = 3.0 if direction == "short" else -2.0
    win_rate_pct = max(35.0, min(92.0, base_wr + regime_adj + sent_adj + iv_edge))
    win_rate     = win_rate_pct / 100.0

    # ── Per-Trade Premium (calibrated Black-Scholes proxy) ────────────────
    # premium_frac: fraction of stock price received as premium
    assumed_iv      = 0.27
    premium_frac    = (delta / 100.0) ** 0.75 * assumed_iv * (dte / 365.0) ** 0.5 * 0.95

    # Effective position allocation — accounts for DTE/entry-frequency overlap
    # Overlapping positions in portfolio at any time: dte / days_between_entries
    if "week" in freq:   days_between = 7
    elif "month" in freq: days_between = 30
    elif "day" in freq:  days_between = 1
    else:                days_between = 30

    concurrent_positions = max(1.0, dte / float(days_between))

    # Capital allocation % per position (realistic position sizing)
    if legs >= 2:
        total_capital_alloc = 0.55   # spread uses ~55% of capital as collateral
        loss_mult = 1.5              # spread: loss ≤ width - credit received
    else:
        total_capital_alloc = 0.45   # cash-secured put collateral
        loss_mult = 2.0              # managed trade: close at 2× premium (standard stop)

    # Per-position allocation = total_alloc / concurrent_positions
    pos_alloc = max(0.03, min(0.25, total_capital_alloc / concurrent_positions))

    # Premium per trade as % of total portfolio
    prem_pct      = premium_frac * pos_alloc * 100.0
    max_loss_pct  = prem_pct * loss_mult

    # ── Expected Value per Trade ──────────────────────────────────────────
    ev_pct = win_rate * prem_pct - (1.0 - win_rate) * max_loss_pct

    # ── Total Return ──────────────────────────────────────────────────────
    # Accumulate EV across all trades (additive approximation)
    raw_return = ev_pct * trade_count

    # Market regime: ADDITIVE bonus, not multiplicative (avoids amplifying losses)
    regime_bonus = (regime_avg - 50.0) * 0.35  # +/- up to 8.75pp
    total_ret    = max(-80.0, min(350.0, raw_return + regime_bonus))

    # ── Financial Metrics ─────────────────────────────────────────────────
    total_pl      = capital * total_ret / 100.0
    final_capital = capital + total_pl

    # CAGR
    if years > 0 and final_capital > 0 and capital > 0:
        cagr = ((final_capital / capital) ** (1.0 / years) - 1.0) * 100.0
    else:
        cagr = 0.0
    cagr = max(-99.0, min(300.0, cagr))

    # Annualised Volatility
    # Short premium: lower vol than underlying; scaled by risk factors
    base_vol     = 12.0 if legs >= 2 else 20.0
    risk_factor  = max(0.0, (100 - factors["volatility_risk"]["score"]) / 100.0)
    cap_factor   = max(0.0, (100 - factors["capital_exposure"]["score"]) / 100.0)
    volatility   = max(5.0, min(60.0, base_vol + risk_factor * 15.0 + cap_factor * 8.0))

    # Sharpe & Sortino
    rfr     = 4.5
    sharpe  = round((cagr - rfr) / volatility, 2) if volatility > 0 else 0.0
    sortino = round((cagr - rfr) / max(0.01, volatility * 0.65), 2)

    # Max Drawdown
    p_loss   = 1.0 - win_rate
    if p_loss > 0 and trade_count > 1:
        max_streak  = math.ceil(math.log(trade_count + 1) / max(0.0001, math.log(1.0 / p_loss + 1e-9)))
    else:
        max_streak  = 1
    max_drawdown = max(2.0, min(65.0, max_streak * max_loss_pct))

    # Max Profit / Loss (dollar)
    max_profit_usd = round(prem_pct / 100.0 * capital * min(trade_count, 1), 2)
    max_loss_usd   = -round(max_loss_pct / 100.0 * capital * min(trade_count, 1), 2)

    # Beta: delta-equivalent exposure
    if direction == "short" and side == "put":   beta_sign = 1
    elif direction == "short" and side == "call": beta_sign = -1
    else:                                          beta_sign = 1
    beta  = round(max(0.05, min(2.0, (delta / 100.0) * min(legs, 2) * 0.5)) * beta_sign, 3)

    # Alpha vs benchmark (SPY ≈ 12% annualised)
    alpha = round(total_ret - 12.0 * years, 2)

    # Risk Score
    dd_comp    = min(1.0, max_drawdown / 50.0)
    vol_comp   = min(1.0, volatility   / 45.0)
    loss_comp  = 1.0 - win_rate
    risk_score = max(0, min(100, round(dd_comp * 40 + vol_comp * 30 + loss_comp * 30)))

    # Confidence Score (from strategy_confidence factor)
    conf_score = min(100, max(25, factors["strategy_confidence"]["score"]))

    # Decision (spec-compliant rule)
    decision = _apply_decision_rule(total_ret, win_rate_pct, risk_score)

    return {
        "decision":                       decision,
        "predicted_initial_capital":      capital,
        "predicted_final_capital":        round(final_capital, 2),
        "predicted_total_pl":             round(total_pl, 2),
        "predicted_total_return_pct":     round(total_ret, 2),
        "predicted_cagr":                 round(cagr, 2),
        "predicted_sharpe":               sharpe,
        "predicted_sortino":              sortino,
        "predicted_max_drawdown":         round(max_drawdown, 2),
        "predicted_win_rate":             round(win_rate_pct, 1),
        "predicted_trade_count":          trade_count,
        "predicted_alpha":                alpha,
        "predicted_beta":                 beta,
        "predicted_volatility":           round(volatility, 1),
        "predicted_risk_score":           risk_score,
        "predicted_confidence_score":     conf_score,
        "predicted_max_profit":           max_profit_usd,
        "predicted_max_loss":             max_loss_usd,
        # Internal: needed for calibration blending
        "_win_rate":     win_rate,
        "_capital":      capital,
        "_years":        years,
        "_trade_count":  trade_count,
        "_prem_pct":     prem_pct,
        "_max_loss_pct": max_loss_pct,
        "_risk_score":   risk_score,
    }


# ══════════════════════════════════════════════════════════════════════════════
# CALIBRATION BLENDING
# ══════════════════════════════════════════════════════════════════════════════
def _blend_with_calibration(proj: dict, cal: dict) -> dict:
    """
    Blend cold-start projection with calibration records.
    V3 weight schedule (read from cal dict, set by _get_calibration_bias):
    - >= 8 records: 25% raw / 75% calibration
    - 5-7 records:  40% / 60%
    - 3-4 records:  55% / 45%
    - 2 records:    80% / 20%
    Recomputes all derived metrics after blending.
    Never copies backtest values directly.
    """
    if not cal.get("has_calibration") or cal.get("similar_count", 0) < 2:
        return proj

    # Use pre-computed weights from _get_calibration_bias
    w_formula = cal.get("raw_weight",          0.55)
    w_cal     = cal.get("calibration_weight",  0.45)

    empirical_return  = cal.get("empirical_return",   0.0) or 0.0
    empirical_wr      = cal.get("empirical_win_rate", 0.0) or 0.0
    empirical_dd      = cal.get("empirical_max_drawdown") or proj["predicted_max_drawdown"]

    # Blend core metrics — allow higher returns for profitable strategies
    blended_ret = w_formula * proj["predicted_total_return_pct"] + w_cal * empirical_return
    blended_wr  = w_formula * proj["predicted_win_rate"]         + w_cal * empirical_wr
    blended_wr  = max(35.0, min(95.0, blended_wr))
    blended_ret = max(-80.0, min(1000.0, blended_ret))  # allow up to 1000% for long options
    blended_dd  = max(2.0, min(65.0, w_formula * proj["predicted_max_drawdown"] + w_cal * empirical_dd))

    # Recompute derived metrics
    capital = proj["_capital"]
    years   = proj["_years"]

    blended_pl  = capital * blended_ret / 100.0
    blended_fc  = capital + blended_pl

    if years > 0 and blended_fc > 0 and capital > 0:
        blended_cagr = ((blended_fc / capital) ** (1.0 / years) - 1.0) * 100.0
    else:
        blended_cagr = 0.0
    blended_cagr = max(-99.0, min(999.0, blended_cagr))

    vol    = proj["predicted_volatility"]
    rfr    = 4.5
    sharpe = round((blended_cagr - rfr) / vol, 2) if vol > 0 else proj["predicted_sharpe"]
    sort_  = round((blended_cagr - rfr) / max(0.01, vol * 0.65), 2)

    # Risk score after blending
    dd_c   = min(1.0, blended_dd / 50.0)
    vol_c  = min(1.0, vol / 45.0)
    wr_c   = 1.0 - blended_wr / 100.0
    risk_s = max(0, min(100, round(dd_c * 40 + vol_c * 30 + wr_c * 30)))

    alpha = round(blended_ret - 12.0 * years, 2)

    decision = _apply_decision_rule(blended_ret, blended_wr, risk_s)

    blended = dict(proj)
    blended.update({
        "decision":                   decision,
        "predicted_total_return_pct": round(blended_ret, 2),
        "predicted_win_rate":         round(blended_wr, 1),
        "predicted_total_pl":         round(blended_pl, 2),
        "predicted_final_capital":    round(blended_fc, 2),
        "predicted_cagr":             round(blended_cagr, 2),
        "predicted_sharpe":           sharpe,
        "predicted_sortino":          sort_,
        "predicted_max_drawdown":     round(blended_dd, 2),
        "predicted_alpha":            alpha,
        "predicted_risk_score":       risk_s,
    })
    return blended


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI EXPLANATION (optional, temperature=0)
# ══════════════════════════════════════════════════════════════════════════════
def _gemini_explanation(si: dict, factors: dict, proj: dict) -> str:
    """Generate explanation text. Returns '' on failure. Never generates numeric metrics."""
    try:
        import google.generativeai as genai
        api_key = os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            return ""
        genai.configure(api_key=api_key)
        model_name = os.getenv("AGENT_MODEL", "gemini-2.5-flash")
        model      = genai.GenerativeModel(model_name)
        prompt = (
            f"Options strategy analysis context:\n"
            f"Strategy: {si['direction']} {si['side']} on {si['symbol']}, "
            f"delta={si['delta']}, DTE={si['dte']}, legs={si['legs']}, "
            f"entry={si['entry_frequency']}, period={si['start_date']} to {si['end_date']}, "
            f"capital=${si['initial_capital']:,.0f}.\n\n"
            f"Pre-computed AI metrics: decision={proj['decision']}, "
            f"predicted_return={proj['predicted_total_return_pct']:.1f}%, "
            f"win_rate={proj['predicted_win_rate']:.1f}%, "
            f"trade_count={proj['predicted_trade_count']}, "
            f"risk_score={proj['predicted_risk_score']}/100.\n\n"
            f"Factor signals: "
            f"regime={factors['underlying_regime']['signal']}, "
            f"suitability={factors['strategy_suitability']['signal']}, "
            f"sentiment={factors['news_sentiment']['signal']}.\n\n"
            f"Write ONE concise paragraph (3-4 sentences) explaining WHY the strategy "
            f"prediction is {proj['decision']}. Focus on options mechanics and strategy suitability. "
            f"Do NOT generate or suggest any different numeric values — those are already computed."
        )
        resp = model.generate_content(
            prompt,
            generation_config={"temperature": 0, "max_output_tokens": 400},
        )
        return resp.text.strip()[:1500]
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
def run_ai_strategy_prediction(strategy_input: dict) -> dict:
    """
    Full AI strategy prediction pipeline (v2 calibrated).

    Order:
    1. Validate StrategyInput
    2. Fetch RapidAPI context (cached 15 min)
    3. Compute 10 factor scores
    4. Cold-start deterministic projection
    5. Load calibration records (historical only, exclude current hash)
    6. Blend cold-start + calibration
    7. Optional Gemini explanation text
    8. Return complete output with model_version

    NEVER receives or uses the current-run backtest result.
    """
    # Guard: no backtest result leakage
    forbidden_keys = ["actual", "backtest_actual", "tastytrade_result",
                      "backtest_result", "bt_actual", "bt_result"]
    for k in forbidden_keys:
        assert k not in strategy_input, (
            f"Strategy input must not contain backtest result key: '{k}' — "
            f"AI prediction must be independent of backtest")
    # Also guard against stringified leakage
    si_str = json.dumps({k: v for k, v in strategy_input.items() if k != "benchmark"})
    if "backtest" in si_str.lower() and "actual" in si_str.lower():
        raise AssertionError("Strategy input contains backtest result data — forbidden")

    valid, err = validate_strategy_input(strategy_input)
    if not valid:
        return {
            "status":   "ERROR",
            "error":    err,
            "source":   "strategy_prediction_agent",
            "decision": "REVIEW",
            "model_version": MODEL_VERSION,
        }

    si         = strategy_input
    input_hash = build_strategy_input_hash(si)

    # 1. RapidAPI context (cached — same call within 15 min is identical)
    ctx = _get_rapidapi_context(si["symbol"], cache_key=input_hash[:8])

    # 2. 10 factor scores
    factors = _compute_factor_scores(si, ctx)

    # 3. Cold-start deterministic projection
    proj_raw = _deterministic_projection(si, factors)

    # 4. Calibration records (past runs only — no current-run backtest)
    cal = _get_calibration_bias(si, input_hash)

    # 5. Blend cold-start + calibration
    proj = _blend_with_calibration(proj_raw, cal)

    # 6. Optional Gemini explanation (text only, temperature=0)
    explanation = _gemini_explanation(si, factors, proj)
    if not explanation:
        d   = proj["decision"]
        wr  = proj["predicted_win_rate"]
        ret = proj["predicted_total_return_pct"]
        n_sim = cal.get("similar_count", 0)
        w_cal = cal.get("calibration_weight", 0.0)
        cal_note = (
            f" Calibrated against {n_sim} similar historical strategies "
            f"(calibration_weight={w_cal:.0%})."
            if cal.get("has_calibration")
            else " No calibration records yet — cold-start priors only."
        )
        explanation = (
            f"AI strategy prediction (v3 surrogate-calibrated) for {si['direction']} {si['side']} "
            f"Δ{si['delta']} on {si['symbol']}: decision={d}. "
            f"Estimated win rate {wr:.1f}% (base {100 - si['delta']}% OTM probability + "
            f"market regime and IV-premium adjustments). "
            f"Predicted total return {ret:.1f}% over {_get_years(si['start_date'], si['end_date']):.1f}yr "
            f"across {proj['predicted_trade_count']} {si['entry_frequency']} entries."
            f"{cal_note}"
        )

    # Clean internal fields before returning
    out_proj = {k: v for k, v in proj.items() if not k.startswith("_")}

    return {
        "status":                   "SUCCESS",
        "source":                   "strategy_prediction_agent",
        "model_version":            MODEL_VERSION,
        "calculation_version":      CALCULATION_VERSION,
        "strategy_input_hash":      input_hash,
        "prediction_scope":         "same_options_strategy",
        "calibration_summary": {
            "has_calibration":       cal.get("has_calibration", False),
            "similar_count":         cal.get("similar_count", 0),
            "calibration_weight":    cal.get("calibration_weight", 0.0),
            "raw_weight":            cal.get("raw_weight", 1.0),
            "empirical_return":      cal.get("empirical_return"),
            "empirical_win_rate":    cal.get("empirical_win_rate"),
            "empirical_max_drawdown": cal.get("empirical_max_drawdown"),
            "empirical_directional": cal.get("empirical_directional", "neutral"),
        },
        **out_proj,
        "strategy_factor_scores": factors,
        "rapidapi_context_summary": {
            "movers_available":  ctx.get("movers_available"),
            "news_available":    ctx.get("news_available"),
            "gainers_count":     len(ctx.get("gainers", [])),
            "losers_count":      len(ctx.get("losers",  [])),
            "news_count":        len(ctx.get("news",    [])),
            "endpoint_results":  ctx.get("endpoint_results", {}),
        },
        "explanation": explanation,
    }
