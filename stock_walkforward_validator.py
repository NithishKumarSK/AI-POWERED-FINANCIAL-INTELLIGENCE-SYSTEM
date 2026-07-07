"""
Stock Walk-Forward Validator
Computes actual stock return for the prediction window using real historical prices.

Flow:
1. Receive spi (StockPredictionInput), ai_prediction (from stock_prediction_agent),
   and full_price_history (all bars including target_date).
2. Get actual price on prediction_origin_date.
3. Get actual price on target_date.
4. Compute actual return, final capital, P&L via stock_comparison_engine.compute_actual_metrics.
5. Compare with AI prediction via stock_comparison_engine.compare_ai_vs_actual.
6. Return validation + comparison dict.

Rules:
- MUST be called AFTER AI prediction is complete
- NO yfinance
- NO fake prices
- NO hardcoded fallbacks
- If either origin or target price unavailable: status=FAILED, block comparison
"""
from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional

from historical_price_service import get_price_on_date, fetch_price_history
from stock_comparison_engine import (
    compute_actual_metrics,
    compare_ai_vs_actual,
    validate_no_leakage,
    decision_from_return,
)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN VALIDATOR — requires pre-fetched history
# ══════════════════════════════════════════════════════════════════════════════

def run_stock_validation(
    spi:                dict,
    ai_prediction:      dict,
    full_price_history: List[dict],
) -> dict:
    """
    Validate AI stock prediction against actual historical prices.

    Parameters:
    - spi               : StockPredictionInput dict
    - ai_prediction     : output of run_stock_prediction() — must already be complete
    - full_price_history: all available bars (including dates at/after target_date)

    Returns validation dict with actual prices, actual metrics, and comparison.

    ARCHITECTURE GUARANTEE:
    This function is called AFTER AI prediction. The AI never sees target_date price.
    """
    symbol       = str(spi.get("symbol", "") or "").upper()
    origin_date  = str(spi.get("prediction_origin_date", "") or "")
    target_date  = str(spi.get("target_date", "") or "")
    horizon_days = int(spi.get("decision_horizon_days", 30) or 30)
    initial_cap  = float(spi.get("initial_capital", 50000) or 50000)
    input_hash   = str(ai_prediction.get("stock_prediction_input_hash", "") or "")

    base = {
        "status":                      "FAILED",
        "source":                      "historical_stock_price_validation",
        "stock_prediction_input_hash": input_hash,
        "symbol":                      symbol,
        "requested_prediction_origin_date": origin_date,
        "requested_target_date":       target_date,
        "initial_capital":             initial_cap,
    }

    # AI must have succeeded first
    if ai_prediction.get("status") != "SUCCESS":
        base["error"] = "AI prediction did not succeed — actual validation blocked."
        return base

    if not full_price_history:
        base["error"] = "Price history is empty — cannot validate."
        return base

    # Actual origin price — must match AI's resolved effective origin exactly.
    # AI uses last bar in filtered ctx_bars (always on_or_before origin_date).
    # get_price_on_date on full history would find nearest bar (can be AFTER origin),
    # causing a different date and price. Use AI's already-resolved values instead.
    _ai_orig_price = ai_prediction.get("origin_price_used")
    _ai_eff_origin = ai_prediction.get("effective_origin_date", "")
    if _ai_orig_price and float(_ai_orig_price) > 0 and _ai_eff_origin:
        orig_price    = float(_ai_orig_price)
        eff_orig_date = _ai_eff_origin
        orig_err      = ""
    else:
        orig_price, eff_orig_date, orig_err = get_price_on_date(
            full_price_history, origin_date, max_gap_days=5
        )
    if orig_price is None:
        base["error"] = f"Cannot get actual origin price on {origin_date}: {orig_err}"
        return base

    # Actual target price
    tgt_price, eff_tgt_date, tgt_err = get_price_on_date(
        full_price_history, target_date, max_gap_days=5
    )
    if tgt_price is None:
        base["error"] = (
            f"Cannot get actual target price on {target_date}: {tgt_err}. "
            "Target date may be a weekend, holiday, or outside API data range."
        )
        return base

    # Compute actual metrics via canonical formula
    metrics = compute_actual_metrics(orig_price, tgt_price, initial_cap)
    if metrics["status"] != "SUCCESS":
        base["error"] = metrics.get("error", "compute_actual_metrics failed")
        return base

    actual_validation = {
        "status":                      "SUCCESS",
        "source":                      "historical_stock_price_validation",
        "stock_prediction_input_hash": input_hash,
        "symbol":                      symbol,
        "requested_prediction_origin_date": origin_date,
        "effective_origin_price_date": eff_orig_date,
        "requested_target_date":       target_date,
        "effective_target_price_date": eff_tgt_date,
        "origin_price":                round(orig_price, 4),
        "target_price":                round(tgt_price, 4),
        "initial_capital":             initial_cap,
        "actual_return_pct":           round(metrics["actual_return_pct"], 4),
        "actual_final_capital":        round(metrics["actual_final_capital"], 4),
        "actual_total_pl":             round(metrics["actual_total_pl"], 4),
        "actual_decision":             metrics["actual_decision"],
        "horizon_days":                horizon_days,
    }

    # Compare AI vs actual
    comparison = compare_ai_vs_actual(ai_prediction, actual_validation)
    actual_validation["comparison"] = comparison

    return actual_validation


# ══════════════════════════════════════════════════════════════════════════════
# STANDALONE VALIDATOR — fetches prices internally (no pre-fetched history needed)
# ══════════════════════════════════════════════════════════════════════════════

def run_actual_validation(spi: dict) -> dict:
    """
    Standalone actual validation — fetches price history internally.

    Does NOT require a pre-fetched history or an AI prediction dict.
    Returns actual prices and metrics only (no comparison vs AI).

    Use run_stock_validation() when you already have AI prediction + history.
    """
    from stock_prediction_agent import build_stock_prediction_hash

    symbol       = str(spi.get("symbol", "") or "").upper()
    origin_date  = str(spi.get("prediction_origin_date", "") or "")
    target_date  = str(spi.get("target_date", "") or "")
    initial_cap  = float(spi.get("initial_capital", 50000) or 50000)
    horizon_days = int(spi.get("decision_horizon_days", 30) or 30)

    try:
        input_hash = build_stock_prediction_hash(spi)
    except Exception:
        input_hash = ""

    base = {
        "status":                      "FAILED",
        "source":                      "historical_stock_price_validation",
        "stock_prediction_input_hash": input_hash,
        "symbol":                      symbol,
        "requested_prediction_origin_date": origin_date,
        "requested_target_date":       target_date,
        "initial_capital":             initial_cap,
    }

    if not symbol:
        base["error"] = "Symbol is required"
        return base

    # Determine how many days of history to fetch
    today = date.today()
    try:
        ctx_start = str(spi.get("historical_context_start_date", "") or "")
        if ctx_start:
            ctx_dt   = datetime.strptime(ctx_start, "%Y-%m-%d").date()
            days_req = (today - ctx_dt).days + 60
        else:
            days_req = 500
    except Exception:
        days_req = 500

    hist, hist_err = fetch_price_history(symbol, min_days=max(400, days_req))
    if not hist:
        base["error"] = f"Price history unavailable for {symbol}: {hist_err}"
        return base

    orig_price, eff_orig, orig_err = get_price_on_date(hist, origin_date, max_gap_days=5)
    if orig_price is None:
        base["error"] = f"Cannot get origin price on {origin_date}: {orig_err}"
        return base

    tgt_price, eff_tgt, tgt_err = get_price_on_date(hist, target_date, max_gap_days=5)
    if tgt_price is None:
        base["error"] = (
            f"Cannot get target price on {target_date}: {tgt_err}. "
            "Target date may be a weekend, holiday, or outside API data range."
        )
        return base

    metrics = compute_actual_metrics(orig_price, tgt_price, initial_cap)
    if metrics["status"] != "SUCCESS":
        base["error"] = metrics.get("error", "compute_actual_metrics failed")
        return base

    base.update({
        "status":                      "SUCCESS",
        "effective_origin_price_date": eff_orig,
        "effective_target_price_date": eff_tgt,
        "origin_price":                round(orig_price, 4),
        "target_price":                round(tgt_price, 4),
        "actual_return_pct":           round(metrics["actual_return_pct"], 4),
        "actual_final_capital":        round(metrics["actual_final_capital"], 4),
        "actual_total_pl":             round(metrics["actual_total_pl"], 4),
        "actual_decision":             metrics["actual_decision"],
        "horizon_days":                horizon_days,
        "error":                       "",
    })
    return base
