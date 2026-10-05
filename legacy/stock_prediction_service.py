"""
Stock Prediction Service — Clean Backend (No Streamlit)

This module is the single entry point for running stock prediction validation.
It has NO Streamlit dependency and can be called by:
  - Discord agent (Amaan's bot)
  - CLI scripts
  - Pytest tests
  - Any external client

Streamlit app should call this module instead of directly calling submodules.

Main functions:
  run_single_stock_validation(stock_prediction_input) -> dict
  run_rolling_validation(config) -> dict
  get_stock_prediction_summary(result) -> str
  map_legacy_strategy_input(strategy_input) -> dict

Time complexity:
  Single validation: O(n) where n = number of historical bars
  Rolling monthly:   O(n + m) if bars reused, where m = number of months

Space complexity:
  O(n + m)
"""
from __future__ import annotations

import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

from historical_price_service import fetch_price_history, filter_history_up_to
from stock_prediction_agent import (
    run_stock_prediction,
    build_stock_prediction_hash,
    validate_stock_prediction_input,
    build_stock_prediction_input,
    MODEL_VERSION,
)
from stock_walkforward_validator import run_stock_validation
from stock_accuracy_engine import (
    save_stock_prediction_record,
    load_stock_prediction_records,
    get_accuracy_summary,
)


# ══════════════════════════════════════════════════════════════════════════════
# SINGLE VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def run_single_stock_validation(stock_prediction_input: dict) -> dict:
    """
    Complete walk-forward stock prediction validation pipeline.

    No Streamlit. Returns clean JSON usable by Discord, CLI, or any client.

    Steps:
      1. Validate input
      2. Build normalized SPI + hash
      3. Fetch historical bars (covers context + target date)
      4. Split: AI bars <= origin_date (strict leakage prevention)
      5. Run AI prediction
      6. Run actual validation (origin price + target price from history)
      7. Compare AI vs actual
      8. Save record if valid
      9. Return full JSON

    Returns dict with keys:
      status, stock_prediction_input, stock_prediction_input_hash,
      ai_prediction, actual_validation, comparison, record_saved, summary
    """
    spi = stock_prediction_input

    # 1. Validate
    valid, err = validate_stock_prediction_input(spi)
    if not valid:
        return {
            "status":   "FAILED",
            "error":    f"Input validation failed: {err}",
            "decision": "REVIEW",
        }

    # 2. Hash
    input_hash = build_stock_prediction_hash(spi)

    # 3. Fetch history
    today = date.today()
    try:
        ctx_dt   = datetime.strptime(spi["historical_context_start_date"], "%Y-%m-%d").date()
        days_req = max(400, (today - ctx_dt).days + 90)
    except Exception:
        days_req = 500

    hist, hist_err = fetch_price_history(spi["symbol"], min_days=days_req)
    if not hist:
        return {
            "status":              "FAILED",
            "error":               f"Price data unavailable for {spi['symbol']}: {hist_err}",
            "decision":            "REVIEW",
            "stock_prediction_input": spi,
            "stock_prediction_input_hash": input_hash,
        }

    # 4. Split — AI sees only bars up to origin_date
    origin_date = spi["prediction_origin_date"]
    ctx_bars    = filter_history_up_to(hist, origin_date)
    if not ctx_bars:
        return {
            "status":  "FAILED",
            "error":   f"No price bars found on or before {origin_date}.",
            "decision": "REVIEW",
            "stock_prediction_input": spi,
            "stock_prediction_input_hash": input_hash,
        }

    # 5. AI Prediction
    ai_result = run_stock_prediction(spi, ctx_bars)

    if ai_result.get("status") != "SUCCESS":
        return {
            "status":              "FAILED",
            "error":               f"AI prediction failed: {ai_result.get('error', 'Unknown')}",
            "decision":            "REVIEW",
            "stock_prediction_input": spi,
            "stock_prediction_input_hash": input_hash,
            "ai_prediction":       ai_result,
        }

    # Hash integrity
    ai_hash = ai_result.get("stock_prediction_input_hash", "")
    if ai_hash and ai_hash != input_hash:
        return {
            "status":  "FAILED",
            "error":   f"Hash mismatch: input={input_hash}, AI returned={ai_hash}.",
            "decision": "REVIEW",
        }

    # 6. Actual Validation
    val_result = run_stock_validation(spi, ai_result, hist)

    # Hash integrity on validation side
    val_hash = val_result.get("stock_prediction_input_hash", "")
    if val_hash and val_hash != input_hash:
        return {
            "status":  "FAILED",
            "error":   f"Validation hash mismatch: input={input_hash}, validation={val_hash}.",
            "decision": "REVIEW",
        }

    # 7. Comparison (embedded in val_result.comparison)
    comparison = val_result.get("comparison", {})

    # 8. Save record
    record_saved = False
    save_msg     = "Not saved."
    if val_result.get("status") == "SUCCESS":
        record_saved, save_msg = save_stock_prediction_record(spi, ai_result, val_result)

    # 9. Return
    return {
        "status":                      "SUCCESS",
        "stock_prediction_input":      spi,
        "stock_prediction_input_hash": input_hash,
        "ai_prediction":               ai_result,
        "actual_validation":           {k: v for k, v in val_result.items() if k != "comparison"},
        "comparison":                  comparison,
        "record_saved":                record_saved,
        "record_save_msg":             save_msg,
        "summary":                     get_stock_prediction_summary({
            "ai_prediction":    ai_result,
            "actual_validation": val_result,
            "comparison":       comparison,
        }),
    }


# ══════════════════════════════════════════════════════════════════════════════
# ROLLING MONTHLY VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def run_rolling_validation(config: dict) -> dict:
    """
    Run walk-forward validation for multiple past months.

    config keys:
      symbol                     : str
      historical_context_start_date : str (YYYY-MM-DD)
      initial_capital            : float
      benchmark                  : str (default "SPY")
      n_months                   : int (default 6)
      validation_mode            : str (default "calendar_month")
      price_basis                : str (default "close")
      decision_horizon_days      : int (default 30, used when validation_mode=horizon_days)

    Returns dict with:
      status, results (list of per-month dicts), summary
    """
    symbol      = str(config.get("symbol", "")).upper().strip()
    ctx_start   = str(config.get("historical_context_start_date", ""))
    capital     = float(config.get("initial_capital", 50_000) or 50_000)
    benchmark   = str(config.get("benchmark", "SPY") or "SPY").upper()
    n_months    = int(config.get("n_months", 6) or 6)
    val_mode    = str(config.get("validation_mode", "calendar_month"))
    price_basis = str(config.get("price_basis", "close"))
    horizon     = int(config.get("decision_horizon_days", 30) or 30)

    if not symbol:
        return {"status": "FAILED", "error": "symbol is required"}

    today = date.today()

    # Fetch history ONCE — reuse for all months
    try:
        ctx_dt   = datetime.strptime(ctx_start, "%Y-%m-%d").date()
        days_req = max(500, (today - ctx_dt).days + 90)
    except Exception:
        days_req = 750

    hist, hist_err = fetch_price_history(symbol, min_days=days_req)
    if not hist:
        return {
            "status": "FAILED",
            "error":  f"Price data unavailable for {symbol}: {hist_err}",
        }

    results  = []
    n_ok     = 0
    n_match  = 0
    n_dir    = 0
    ret_errs = []

    # Walk backward from last completed month
    current = (today.replace(day=1) - timedelta(days=1)).replace(day=1)

    for _ in range(n_months):
        mo_end   = (current + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        origin_s = current.strftime("%Y-%m-%d")
        target_s = mo_end.strftime("%Y-%m-%d")

        # Skip months before context start
        try:
            ctx_dt2 = datetime.strptime(ctx_start, "%Y-%m-%d").date()
            if current <= ctx_dt2:
                break
        except Exception:
            break

        mo_horizon = (mo_end - current).days if val_mode == "calendar_month" else horizon

        spi = {
            "symbol":                        symbol,
            "historical_context_start_date": ctx_start,
            "prediction_origin_date":        origin_s,
            "decision_horizon_days":         mo_horizon,
            "target_date":                   target_s,
            "initial_capital":               capital,
            "benchmark":                     benchmark,
            "validation_mode":               val_mode,
            "price_basis":                   price_basis,
        }

        ctx_bars  = filter_history_up_to(hist, origin_s)
        ai_result = run_stock_prediction(spi, ctx_bars)
        val_result = run_stock_validation(spi, ai_result, hist)

        if ai_result.get("status") == "SUCCESS" and val_result.get("status") == "SUCCESS":
            save_stock_prediction_record(spi, ai_result, val_result)
            n_ok += 1
            cmp = val_result.get("comparison", {})
            if cmp.get("decision_match"):  n_match += 1
            if cmp.get("directional_match"): n_dir += 1
            rae = cmp.get("absolute_return_error_pct")
            if rae is not None: ret_errs.append(float(rae))

        results.append({
            "month":          origin_s[:7],
            "origin_date":    origin_s,
            "target_date":    target_s,
            "origin_price":   val_result.get("origin_price"),
            "target_price":   val_result.get("target_price"),
            "ai_pred_price":  ai_result.get("predicted_target_price"),
            "ai_capital":     ai_result.get("predicted_final_capital"),
            "actual_capital": val_result.get("actual_final_capital"),
            "return_err_pp":  val_result.get("comparison", {}).get("return_error_pct"),
            "ai_decision":    ai_result.get("decision"),
            "actual_decision":val_result.get("actual_decision"),
            "decision_match": val_result.get("comparison", {}).get("decision_match"),
            "dir_match":      val_result.get("comparison", {}).get("directional_match"),
            "ai_status":      ai_result.get("status"),
            "val_status":     val_result.get("status"),
        })

        current = (current - timedelta(days=1)).replace(day=1)

    return {
        "status":    "SUCCESS",
        "symbol":    symbol,
        "n_months":  len(results),
        "results":   results,
        "aggregate": {
            "n_successful":           n_ok,
            "decision_match_rate":    round(n_match / n_ok * 100, 1) if n_ok else None,
            "direction_match_rate":   round(n_dir   / n_ok * 100, 1) if n_ok else None,
            "avg_abs_return_error":   round(sum(ret_errs) / len(ret_errs), 2) if ret_errs else None,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY STRING (for Discord / CLI)
# ══════════════════════════════════════════════════════════════════════════════

def get_stock_prediction_summary(result: dict) -> str:
    """
    Human-readable one-paragraph summary of a validation result.
    Good for Discord messages or CLI output.
    """
    ai  = result.get("ai_prediction", {}) or {}
    val = result.get("actual_validation", {}) or {}
    cmp = result.get("comparison", {}) or {}

    if ai.get("status") != "SUCCESS":
        return f"AI prediction FAILED: {ai.get('error', 'Unknown error')}"

    sym      = ai.get("symbol", "?")
    origin   = ai.get("prediction_origin_date", "?")
    target   = ai.get("target_date", "?")
    ai_dec   = ai.get("decision", "?")
    ai_ret   = ai.get("predicted_return_pct")
    ai_cap   = ai.get("predicted_final_capital")

    if val.get("status") != "SUCCESS":
        return (
            f"{sym} AI prediction ({origin} → {target}): "
            f"decision={ai_dec}, predicted_return={ai_ret:+.2f}%, "
            f"predicted_capital=${ai_cap:,.2f} | "
            f"Actual validation FAILED: {val.get('error', 'Unknown')}"
        )

    act_ret  = val.get("actual_return_pct")
    act_cap  = val.get("actual_final_capital")
    act_dec  = val.get("actual_decision")
    agreement = cmp.get("agreement", "?")
    cap_err  = cmp.get("capital_error")
    ret_err  = cmp.get("return_error_pct")

    summary = (
        f"{sym} Walk-Forward ({origin} → {target})\n"
        f"AI: {ai_dec} | predicted_return={ai_ret:+.2f}% | predicted_capital=${ai_cap:,.2f}\n"
        f"Actual: {act_dec} | actual_return={act_ret:+.2f}% | actual_capital=${act_cap:,.2f}\n"
        f"Agreement: {agreement}"
        + (f" | capital_error=${cap_err:+,.2f}" if cap_err is not None else "")
        + (f" | return_error={ret_err:+.2f}pp" if ret_err is not None else "")
    )
    return summary


# ══════════════════════════════════════════════════════════════════════════════
# LEGACY INPUT MAPPER
# ══════════════════════════════════════════════════════════════════════════════

def map_legacy_strategy_input(strategy_input: dict) -> dict:
    """
    Map old options strategy input to corrected StockPredictionInput.

    Ignores: direction, side, dte, delta, legs, entry_frequency
    Maps:    symbol, start_date→ctx_start, end_date→origin_date,
             decision_horizon, initial_capital, benchmark
    """
    si = strategy_input.get("strategy_input", strategy_input)

    symbol       = str(si.get("symbol", "") or "").upper().strip()
    ctx_start    = str(si.get("start_date", "") or si.get("historical_context_start_date", ""))
    origin_date  = str(si.get("end_date",   "") or si.get("prediction_origin_date", ""))
    horizon      = int(si.get("decision_horizon", 0) or si.get("decision_horizon_days", 30) or 30)
    capital      = float(si.get("initial_capital", 50_000) or 50_000)
    benchmark    = str(si.get("benchmark", "SPY") or "SPY").upper()

    # Compute target_date
    try:
        origin_dt  = datetime.strptime(origin_date, "%Y-%m-%d")
        target_dt  = origin_dt + timedelta(days=horizon)
        target_str = target_dt.strftime("%Y-%m-%d")
    except Exception:
        target_str = ""

    return {
        "symbol":                        symbol,
        "historical_context_start_date": ctx_start,
        "prediction_origin_date":        origin_date,
        "decision_horizon_days":         horizon,
        "target_date":                   target_str,
        "initial_capital":               capital,
        "benchmark":                     benchmark,
        "validation_mode":               "horizon_days",
        "price_basis":                   "close",
        "_mapped_from_legacy":           True,
        "_ignored_legacy_fields":        ["direction", "side", "dte", "delta",
                                          "legs", "entry_frequency"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# CLI ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json as _json
    print("Stock Prediction Service — CLI test")
    spi = build_stock_prediction_input(
        symbol="TSLA",
        historical_context_start_date="2025-07-01",
        prediction_origin_date="2026-03-01",
        decision_horizon_days=30,
        initial_capital=50_000,
    )
    print("Input:", _json.dumps(spi, indent=2))
    result = run_single_stock_validation(spi)
    print("Summary:", get_stock_prediction_summary(result))
    print("Status:", result.get("status"))
