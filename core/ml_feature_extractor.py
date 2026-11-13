"""
ml_feature_extractor.py — Phase 4 of the accuracy improvement program.

Builds a flat, numeric feature matrix + binary direction label (BUY=1/SELL=0,
HOLD rows excluded -- see decision_thresholds_for_horizon) from feature
packets, for training core/ml_signal_model.py.

Two data sources, because the DB alone currently has almost no usable data:

1. extract_from_db_records() -- pulls `_feature_packet` out of the DB's
   `ai_prediction_raw` column for already-validated predictions. This is the
   "real" source of truth going forward (every live prediction now stores its
   feature_packet), but as of this session's own check: only 2 of 138
   historical rows actually have it (the field was added to the result dict
   after most existing rows were saved). It will keep growing from here.

2. generate_bulk_training_data() -- computes feature_packet + ground-truth
   label directly from real historical price bars across many symbols/
   horizons/origin dates, the same way batch_validation_runner's use_llm=False
   path does, WITHOUT needing a live prediction or Gemini call. This is how
   you get a trainable dataset TODAY instead of waiting months for #1 to
   accumulate -- same real, free, cross-verified price data already proven
   this session (NASDAQ/yfinance), same leakage-safe windowing.

Both return the same (X, y, feature_names, meta) shape so ml_signal_model.py
doesn't need to care which source produced a given row. meta carries
symbol/origin_date/horizon_days per row -- required for walk-forward
(time-ordered) train/test splitting; a random split on this data would leak
the future into training, exactly the mistake stock_comparison_engine's
leakage checks exist to prevent elsewhere.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_paths
bootstrap_paths.add_module_paths()

# Numeric feature paths into feature_packet: (name, section, key).
FEATURE_SPEC: List[Tuple[str, str, str]] = [
    ("return_1d",              "returns",             "return_1d"),
    ("return_5d",               "returns",             "return_5d"),
    ("return_10d",               "returns",             "return_10d"),
    ("return_20d",                "returns",             "return_20d"),
    ("return_60d",                 "returns",             "return_60d"),
    ("price_vs_sma_20_pct",         "trend",               "price_vs_sma_20_pct"),
    ("price_vs_sma_50_pct",          "trend",               "price_vs_sma_50_pct"),
    ("ADX_14",                        "trend",               "ADX_14"),
    ("RSI_14",                         "momentum",            "RSI_14"),
    ("MACD_histogram",                  "momentum",            "MACD_histogram"),
    # Indicator-completeness pass (Zhong & Hitchcock, arXiv 2108.10826, used
    # all four) -- same free OHLCV bars already fetched for everything else.
    ("CCI_20",                          "momentum",            "CCI_20"),
    ("Williams_R_14",                   "momentum",            "Williams_R_14"),
    ("STOCH_K_14",                       "momentum",            "STOCH_K_14"),
    ("STOCH_D_3",                        "momentum",            "STOCH_D_3"),
    ("CMF_20",                           "volume",              "CMF_20"),
    ("annualized_volatility",            "volatility",          "annualized_volatility"),
    ("ATR_daily_pct",                     "volatility",          "ATR_daily_pct"),
    ("BB_position",                        "volatility",          "BB_position"),
    ("max_drawdown_context",                "volatility",          "max_drawdown_context"),
    ("dist_from_low_pct",                    "volatility",          "dist_from_low_pct"),
    ("volume_ratio_20",                       "volume",              "volume_ratio_20"),
    ("dist_to_support_pct",                    "support_resistance", "dist_to_support_pct"),
    ("dist_to_resistance_pct",                  "support_resistance", "dist_to_resistance_pct"),
    ("benchmark_return_20d",                     "benchmark_comparison", "benchmark_return_20d"),
    ("relative_strength_20d",                     "benchmark_comparison", "relative_strength_20d"),
    ("relative_strength_60d",                      "benchmark_comparison", "relative_strength_60d"),
    # Phase 3 (Alpha Vantage) + Research Expansion Program Components 1/2 --
    # all top-level feature_packet keys (section="" -- see _lookup below),
    # not nested under a sub-dict. Missing/unavailable (no API key, index
    # symbol, rate-limited, etc.) becomes NaN, same as any other feature.
    ("earnings_days_away",         "", "earnings_days_away"),
    ("news_sentiment_score",       "", "news_sentiment_score"),
    ("news_sentiment_article_count", "", "news_sentiment_article_count"),
    ("insider_buy_count",          "", "insider_buy_count"),
    ("insider_sell_count",         "", "insider_sell_count"),
    ("insider_net_signal",         "", "insider_net_signal"),
    ("reddit_mentions",            "", "reddit_mentions"),
    ("reddit_mentions_24h_change", "", "reddit_mentions_24h_change"),
    # Component 4 -- LLM-generated structured scores (Gemini's OUTPUT, folded
    # into feature_packet post-prediction). Only present for real Gemini-
    # sourced rows; generate_bulk_training_data's deterministic path never
    # calls Gemini, so these stay NaN there -- a disclosed, inherent limit.
    ("bull_conviction_score",      "", "bull_conviction_score"),
    ("bear_conviction_score",      "", "bear_conviction_score"),
    ("narrative_dependency_score", "", "narrative_dependency_score"),
    # To-do item #9 remainder -- macro/rate data (core/macro_data_service.py).
    # Market-wide, not symbol-specific; NaN wherever ALPHA_VANTAGE_API_KEY
    # isn't configured, same degrade-gracefully contract as every field above.
    ("fed_funds_rate_pct",         "", "fed_funds_rate_pct"),
    ("treasury_10y_yield_pct",     "", "treasury_10y_yield_pct"),
    # Congress trade disclosures (core/congress_trade_service.py) + 13F
    # institutional holdings (core/institutional_holdings_service.py) --
    # same degrade-gracefully contract as every field above.
    ("congress_buy_count",         "", "congress_buy_count"),
    ("congress_sell_count",        "", "congress_sell_count"),
    ("congress_net_signal",        "", "congress_net_signal"),
    ("institutional_holder_count", "", "institutional_holder_count"),
    ("market_breadth_200ma",       "", "market_breadth_200ma"),
    ("market_breadth_8ma",         "", "market_breadth_8ma"),
    ("market_uptrend_ratio",       "", "market_uptrend_ratio"),
    # core/free_news_service.py -- yahoo_headline_tags is a dict (prompt-only
    # context, not a scalar) and intentionally excluded from the numeric vector.
    ("sec_8k_filing_count",        "", "sec_8k_filing_count"),
    ("yahoo_headline_count",       "", "yahoo_headline_count"),
    ("sec_revenue",                "", "sec_revenue"),
    ("sec_revenue_yoy_pct",        "", "sec_revenue_yoy_pct"),
    ("sec_net_income",             "", "sec_net_income"),
    ("sec_net_income_yoy_pct",     "", "sec_net_income_yoy_pct"),
    ("sec_eps_diluted",            "", "sec_eps_diluted"),
    # P/E, P/B, P/S -- derived from the SEC XBRL fundamentals above plus the
    # prediction's own origin_price (core/sec_financials_service.py
    # compute_valuation_ratios). Missing for loss-making companies (no
    # meaningful P/E) or filers with no resolvable equity/shares data.
    ("pe_ratio",                    "", "pe_ratio"),
    ("pb_ratio",                    "", "pb_ratio"),
    ("ps_ratio",                    "", "ps_ratio"),
    # Per-headline news scoring (core/per_headline_news_scorer.py) --
    # Lopez-Lira & Tang's actual mechanism (per-headline YES/NO), opt-in and
    # live-only, so NaN for historical replay and whenever the flag is off.
    ("per_headline_news_score",        "", "per_headline_news_score"),
    ("per_headline_news_up_count",     "", "per_headline_news_up_count"),
    ("per_headline_news_down_count",   "", "per_headline_news_down_count"),
    # macro_regime_current/confidence are categorical strings (prompt-only
    # context, not scalars) and intentionally excluded from the numeric vector.
    ("macro_regime_composite_score", "", "macro_regime_composite_score"),
    # core/ibd_distribution_day_service.py -- ibd_overall_risk_level is a
    # categorical string (prompt-only context, not a scalar) and
    # intentionally excluded from the numeric vector.
    ("ibd_qqq_d25_count", "", "ibd_qqq_d25_count"),
    # core/market_top_detector_service.py -- market_top_risk_zone is a
    # categorical string (prompt-only context, not a scalar) and
    # intentionally excluded from the numeric vector.
    ("market_top_risk_score", "", "market_top_risk_score"),
    # core/downtrend_duration_service.py -- per-symbol historical downtrend
    # duration statistics.
    ("downtrend_median_duration_days", "", "downtrend_median_duration_days"),
    ("downtrend_p90_duration_days", "", "downtrend_p90_duration_days"),
    # core/pead_screener_service.py -- pead_stage is a categorical string
    # (prompt-only context, not a scalar) and intentionally excluded from
    # the numeric vector.
    ("pead_composite_score", "", "pead_composite_score"),
    # core/earnings_trade_analyzer_service.py -- earnings_reaction_grade is
    # a categorical string (prompt-only context, not a scalar) and
    # intentionally excluded from the numeric vector.
    ("earnings_reaction_score", "", "earnings_reaction_score"),
    # core/stockbee_exhaustion_hammer_service.py -- hammer_state is a
    # categorical string (prompt-only context, not a scalar) and
    # intentionally excluded from the numeric vector.
    ("hammer_setup_score", "", "hammer_setup_score"),
    # core/stockbee_momentum_burst_service.py -- momentum_burst_state is a
    # categorical string (prompt-only context, not a scalar) and
    # intentionally excluded from the numeric vector.
    ("momentum_burst_score", "", "momentum_burst_score"),
    # core/stockbee_episodic_pivot_analyzer_service.py -- episodic_pivot_state
    # is a categorical string (prompt-only context, not a scalar) and
    # intentionally excluded from the numeric vector.
    ("episodic_pivot_score", "", "episodic_pivot_score"),
    # core/vcp_screener_service.py -- vcp_execution_state is a categorical
    # string (prompt-only context, not a scalar) and intentionally
    # excluded from the numeric vector.
    ("vcp_composite_score", "", "vcp_composite_score"),
    # core/canslim_screener_service.py -- canslim_rating is a categorical
    # string (prompt-only context, not a scalar) and intentionally
    # excluded from the numeric vector.
    ("canslim_composite_score", "", "canslim_composite_score"),
    # core/dividend_growth_pullback_screener_service.py -- dividend_cagr_3yr
    # is a secondary numeric alongside the composite score (both kept,
    # unlike the categorical-string exclusions elsewhere in this file).
    ("dividend_growth_score", "", "dividend_growth_score"),
    ("dividend_cagr_3yr", "", "dividend_cagr_3yr"),
    # core/value_dividend_screener_service.py -- dividend_stable (bool) is
    # in BOOL_FEATURE_SPEC below, not here.
    ("value_dividend_score", "", "value_dividend_score"),
    # core/stockbee_20pct_study_service.py -- twenty_pct_study_direction is
    # a categorical string (prompt-only context, not a scalar) and
    # intentionally excluded from the numeric vector.
    ("twenty_pct_study_score", "", "twenty_pct_study_score"),
    # core/macro_calendar_service.py -- live-only (gated to recent-origin
    # predictions at the call site), so historical replay rows never have
    # this key; feature_packet_to_vector already treats a missing key as NaN.
    ("macro_event_days_away", "", "macro_event_days_away"),
    ("macro_event_tier", "", "macro_event_tier"),
    # core/institutional_flow_tracker_service.py -- institutional_flow_classification
    # is a categorical string (prompt-only context, not a scalar) and
    # intentionally excluded from the numeric vector.
    ("institutional_flow_score", "", "institutional_flow_score"),
]

# Boolean feature paths -- encoded 1.0/0.0, missing treated as 0.0 (false).
BOOL_FEATURE_SPEC: List[Tuple[str, str, str]] = [
    ("oversold_signal",     "reversal_signals", "oversold_signal"),
    ("overbought_signal",   "reversal_signals", "overbought_signal"),
    ("near_support",        "reversal_signals", "near_support"),
    ("near_resistance",     "reversal_signals", "near_resistance"),
    ("momentum_divergence", "reversal_signals", "momentum_divergence"),
    # core/ftd_status_service.py -- ftd_combined_state is a categorical string
    # (prompt-only context, not a scalar) and intentionally excluded here.
    ("ftd_dual_confirmation", "", "ftd_dual_confirmation"),
    ("dividend_stable", "", "dividend_stable"),
]

FEATURE_NAMES: List[str] = [n for n, _, _ in FEATURE_SPEC] + [n for n, _, _ in BOOL_FEATURE_SPEC]


def _lookup(feature_packet: dict, section: str, key: str):
    """section="" means key lives directly on feature_packet (e.g. the
    earnings/insider/reddit enrichment fields, which are written as top-level
    keys, not nested under a sub-dict like "returns"/"trend")."""
    if not section:
        return feature_packet.get(key)
    return (feature_packet.get(section) or {}).get(key)


def feature_packet_to_vector(feature_packet: dict) -> Optional[List[float]]:
    """Flatten a feature_packet dict into a fixed-order numeric vector.
    Returns None if the packet is missing/failed (status != "OK")."""
    if not feature_packet or feature_packet.get("status") != "OK":
        return None
    vec: List[float] = []
    for _name, section, key in FEATURE_SPEC:
        val = _lookup(feature_packet, section, key)
        try:
            vec.append(float(val) if val is not None else float("nan"))
        except (TypeError, ValueError):
            vec.append(float("nan"))
    for _name, section, key in BOOL_FEATURE_SPEC:
        val = _lookup(feature_packet, section, key)
        vec.append(1.0 if val else 0.0)
    return vec


def _label_from_actual_return(actual_return_pct: float, horizon_days: int) -> Optional[int]:
    """1=BUY, 0=SELL, None=HOLD (excluded -- this is a direction model, not a
    magnitude/HOLD model). Reuses the same horizon-scaled threshold as the
    live product's own ground truth (Phase 0) -- the ML label and the
    product's "did the AI get it right" label must agree on what a real move is."""
    from stock_comparison_engine import decision_from_return
    dec = decision_from_return(actual_return_pct, horizon_days=horizon_days)
    if dec == "BUY":
        return 1
    if dec == "SELL":
        return 0
    return None


def extract_from_db_records(records: List[dict]) -> Tuple[List[List[float]], List[int], List[str], List[dict]]:
    """Pull (X, y) from DB records that have a stored _feature_packet (see
    module docstring -- currently sparse, grows from live use going forward)."""
    X: List[List[float]] = []
    y: List[int] = []
    meta: List[dict] = []
    for r in records or []:
        ai_raw = r.get("ai_prediction") or {}
        fp = ai_raw.get("_feature_packet")
        if not fp:
            continue
        vec = feature_packet_to_vector(fp)
        if vec is None:
            continue
        spi = r.get("stock_prediction_input") or {}
        av = r.get("actual_validation") or {}
        actual_ret = av.get("actual_return_pct")
        horizon = spi.get("decision_horizon_days")
        if actual_ret is None or horizon is None:
            continue
        label = _label_from_actual_return(float(actual_ret), int(horizon))
        if label is None:
            continue
        X.append(vec)
        y.append(label)
        meta.append({
            "symbol": spi.get("symbol"),
            "origin_date": spi.get("prediction_origin_date"),
            "horizon_days": horizon,
            "source": "db_record",
        })
    return X, y, list(FEATURE_NAMES), meta


def generate_bulk_training_data(
    symbols: List[str],
    horizons: List[int],
    months_back: int = 24,
    sample_freq: str = "monthly",
    max_samples: int = 2000,
    benchmark: str = "SPY",
    verbose: bool = False,
) -> Tuple[List[List[float]], List[int], List[str], List[dict]]:
    """Generate (X, y) directly from real historical price bars -- no Gemini
    call, no live prediction required. Deterministic feature_packet +
    deterministic ground-truth label, same free/verified price providers
    (NASDAQ/yfinance) already proven this session. This is how a trainable
    dataset exists TODAY instead of waiting on the DB to slowly accumulate
    _feature_packet-bearing live predictions.
    """
    from datetime import date, timedelta
    from historical_price_service import fetch_price_history, filter_history_up_to
    from gemini_stock_prediction_agent import build_stock_feature_packet
    from batch_validation_runner import _build_origin_dates, DEFAULT_CTX_DAYS

    today = date.today()
    origins = _build_origin_dates(months_back, today, freq=sample_freq)

    X: List[List[float]] = []
    y: List[int] = []
    meta: List[dict] = []

    # Fetch each symbol's (and the benchmark's) full history ONCE, outside the
    # origin/horizon loops, and slice per-origin below -- the live prediction
    # path fetches a benchmark too (relative-strength features), and without
    # it those feature columns are silently all-NaN for every single row
    # (confirmed during development: sklearn's imputer warned "Skipping
    # features without any observed values" for exactly the 3
    # benchmark_comparison columns on a real training run).
    _hist_cache: Dict[str, List[dict]] = {}

    def _get_hist(sym: str) -> List[dict]:
        if sym not in _hist_cache:
            h, _err = fetch_price_history(sym, min_days=max(400, DEFAULT_CTX_DAYS + 90))
            _hist_cache[sym] = h or []
        return _hist_cache[sym]

    bm_hist = _get_hist(benchmark) if benchmark else []

    for origin in origins:
        for symbol in symbols:
            for horizon in horizons:
                if len(X) >= max_samples:
                    return X, y, list(FEATURE_NAMES), meta
                target = origin + timedelta(days=horizon)
                if target >= today:
                    continue
                try:
                    hist = _get_hist(symbol)
                    if not hist:
                        continue
                    origin_s = origin.strftime("%Y-%m-%d")
                    target_s = target.strftime("%Y-%m-%d")
                    ctx_start = (origin - timedelta(days=DEFAULT_CTX_DAYS)).strftime("%Y-%m-%d")
                    ctx_bars = [b for b in filter_history_up_to(hist, origin_s) if b.get("date", "") >= ctx_start]
                    if not ctx_bars:
                        continue

                    bm_bars = None
                    if bm_hist and benchmark != symbol:
                        bm_bars = [b for b in filter_history_up_to(bm_hist, origin_s) if b.get("date", "") >= ctx_start]

                    spi = {
                        "symbol": symbol, "historical_context_start_date": ctx_start,
                        "prediction_origin_date": origin_s, "target_date": target_s,
                        "decision_horizon_days": horizon, "price_basis": "close",
                    }
                    fp = build_stock_feature_packet(spi, ctx_bars, benchmark_bars=bm_bars)
                    vec = feature_packet_to_vector(fp)
                    if vec is None:
                        continue

                    origin_bar = ctx_bars[-1]
                    target_bars = [b for b in hist if b.get("date", "") <= target_s]
                    if not target_bars:
                        continue
                    target_bar = target_bars[-1]
                    origin_price = float(origin_bar.get("close") or 0)
                    target_price = float(target_bar.get("close") or 0)
                    if origin_price <= 0 or target_price <= 0:
                        continue
                    actual_return_pct = (target_price - origin_price) / origin_price * 100.0

                    label = _label_from_actual_return(actual_return_pct, horizon)
                    if label is None:
                        continue  # HOLD -- excluded from this direction-only model

                    X.append(vec)
                    y.append(label)
                    meta.append({
                        "symbol": symbol, "origin_date": origin_s,
                        "horizon_days": horizon, "source": "bulk_generated",
                    })
                    if verbose:
                        print(f"[{len(X):4d}] {symbol} {origin_s} {horizon}d -> label={label}")
                except Exception as exc:
                    if verbose:
                        print(f"skip {symbol} {origin}: {type(exc).__name__}: {exc}")
                    continue

    return X, y, list(FEATURE_NAMES), meta
