"""Streamlit-free Stock Price Validation orchestrator for the API.

Mirrors _run_all() in stock_prediction_app.py (the live Streamlit app's
orchestrator) -- same input validation, context-window leakage checks, AI
dispatch, and pending-vs-validated branching -- but returns a plain dict
instead of writing into st.session_state, and saves through the central DB
repository (db.stock_prediction_repository) instead of local files.

Reuses the exact same building blocks the UI uses, so behavior stays
identical between the Streamlit app and the API:
  stock_prediction_agent.validate_stock_prediction_input / build_stock_prediction_hash
  historical_price_service.fetch_price_history_for_range
  stock_prediction_app._dispatch_prediction   (Gemini/baseline routing)
  stock_walkforward_validator.run_stock_validation
  db.stock_prediction_repository.save_stock_prediction_record / save_pending_prediction
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict

from historical_price_service import fetch_price_history_for_range, get_context_summary
from stock_prediction_agent import build_stock_prediction_hash, validate_stock_prediction_input
from stock_walkforward_validator import run_stock_validation
from db.stock_prediction_repository import save_pending_prediction, save_stock_prediction_record


def _build_spi(input_dict: dict) -> dict:
    spi = {
        "symbol": str(input_dict.get("symbol", "")).upper().strip(),
        "historical_context_start_date": str(input_dict.get("historical_context_start_date", "")),
        "prediction_origin_date": str(input_dict.get("prediction_origin_date", "")),
        "decision_horizon_days": int(input_dict.get("decision_horizon_days", 30) or 30),
        "target_date": str(input_dict.get("target_date", "") or ""),
        "initial_capital": float(input_dict.get("initial_capital", 50000) or 50000),
        "benchmark": str(input_dict.get("benchmark", "SPY") or "SPY").upper(),
        "validation_mode": str(input_dict.get("validation_mode", "horizon_days") or "horizon_days"),
        "price_basis": str(input_dict.get("price_basis", "close") or "close"),
    }
    if not spi["target_date"]:
        try:
            origin_dt = datetime.strptime(spi["prediction_origin_date"], "%Y-%m-%d")
            from datetime import timedelta
            spi["target_date"] = (origin_dt + timedelta(days=spi["decision_horizon_days"])).strftime("%Y-%m-%d")
        except Exception:
            pass
    return spi


def run_stock_price_validation(input_dict: dict) -> Dict[str, Any]:
    """Run one walk-forward stock price validation and persist the outcome
    to the central DB. Returns a result dict with a top-level `status` of
    SUCCESS / PENDING / FAILED."""
    spi = _build_spi(input_dict)

    today = date.today()
    try:
        target_dt = datetime.strptime(spi["target_date"], "%Y-%m-%d").date()
    except Exception:
        return {"status": "FAILED", "error": "target_date / decision_horizon_days could not be resolved", "spi": spi}
    run_type = "live_future_prediction" if target_dt > today else "historical_validation"

    valid, err = validate_stock_prediction_input(spi)
    if not valid:
        return {"status": "FAILED", "error": f"Input validation failed: {err}", "spi": spi}

    input_hash = build_stock_prediction_hash(spi)

    hist, hist_err, hist_cov = fetch_price_history_for_range(
        spi["symbol"], spi["historical_context_start_date"], today.strftime("%Y-%m-%d")
    )
    if not hist:
        return {"status": "FAILED", "error": hist_err or "Historical price data unavailable", "spi": spi, "stock_prediction_input_hash": input_hash}

    ctx_start = spi["historical_context_start_date"]
    origin = spi["prediction_origin_date"]
    ctx_bars = [b for b in hist if ctx_start <= b["date"] <= origin]
    if not ctx_bars:
        return {
            "status": "FAILED",
            "error": f"No price bars between {ctx_start} and {origin}.",
            "spi": spi,
            "stock_prediction_input_hash": input_hash,
        }

    first_bar, last_bar = ctx_bars[0]["date"], ctx_bars[-1]["date"]
    if first_bar < ctx_start:
        return {"status": "FAILED", "error": f"Context leakage: first bar {first_bar} before {ctx_start}.", "spi": spi}
    if last_bar > origin:
        return {"status": "FAILED", "error": f"Future leakage: last bar {last_bar} after {origin}.", "spi": spi}

    # Reuse the live app's exact Gemini/baseline dispatch logic.
    from stock_prediction_app import _dispatch_prediction
    ai_result = _dispatch_prediction(spi, ctx_bars)

    if ai_result.get("status") != "SUCCESS":
        return {
            "status": "FAILED",
            "error": ai_result.get("error", "AI prediction failed"),
            "ai_prediction": ai_result,
            "spi": spi,
            "stock_prediction_input_hash": input_hash,
        }

    ai_hash = ai_result.get("stock_prediction_input_hash", "")
    if ai_hash and ai_hash != input_hash:
        return {"status": "FAILED", "error": "Input hash mismatch between request and AI prediction.", "spi": spi}

    if run_type == "live_future_prediction":
        val_result = {
            "status": "PENDING",
            "reason": "Target date is in the future. Actual validation will be available after the target date.",
            "validation_available_after": spi["target_date"],
        }
        saved, save_msg = save_pending_prediction(spi, ai_result)
        return {
            "status": "PENDING",
            "run_type": run_type,
            "stock_prediction_input_hash": input_hash,
            "spi": spi,
            "ai_prediction": ai_result,
            "actual_validation": val_result,
            "saved": saved,
            "save_message": save_msg,
            "ctx_summary": get_context_summary(hist, ctx_start, origin),
        }

    val_result = run_stock_validation(spi, ai_result, hist)
    if val_result.get("status") == "SUCCESS":
        saved, save_msg = save_stock_prediction_record(spi, ai_result, val_result)
    else:
        saved, save_msg = False, f"Validation failed -- not saved: {val_result.get('error', '')}"

    return {
        "status": val_result.get("status", "FAILED"),
        "run_type": run_type,
        "stock_prediction_input_hash": input_hash,
        "spi": spi,
        "ai_prediction": ai_result,
        "actual_validation": val_result,
        "comparison": val_result.get("comparison", {}),
        "saved": saved,
        "save_message": save_msg,
        "ctx_summary": get_context_summary(hist, ctx_start, origin),
    }
