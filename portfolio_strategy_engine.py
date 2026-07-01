"""
Portfolio Strategy Engine
Per-holding AI prediction + tastytrade backtest, then portfolio-level aggregation.
Raw portfolio string is NEVER passed to AI prediction or backtest functions.
Each holding is backtested separately with its allocated capital.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Callable
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


# ══════════════════════════════════════════════════════════════════════════════
# INPUT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_portfolio_strategy_input(holdings: list, si: dict) -> dict:
    """
    Build canonical portfolio strategy input from parsed holdings + form si dict.
    holdings: list of {ticker, weight, weight_pct, allocation} from parse_and_validate_portfolio.
    si: StrategyInput dict from the form (symbol, start_date, end_date, ...).
    """
    return {
        "mode":             "portfolio_strategy",
        "holdings": [
            {
                "symbol":            h["ticker"],
                "weight":            round(h["weight_pct"], 4),
                "allocated_capital": round(h["allocation"], 2),
            }
            for h in holdings
        ],
        "start_date":       str(si.get("start_date", "")),
        "end_date":         str(si.get("end_date", "")),
        "initial_capital":  float(si.get("initial_capital", 100_000)),
        "benchmark":        si.get("benchmark", "SPY"),
        "direction":        si.get("direction", "short"),
        "side":             si.get("side", "put"),
        "dte":              int(si.get("dte", 50)),
        "delta":            int(si.get("delta", 30)),
        "legs":             int(si.get("legs", 1)),
        "entry_frequency":  si.get("entry_frequency", "monthly"),
        "decision_horizon": int(si.get("decision_horizon", 30)),
    }


def build_portfolio_strategy_hash(portfolio_si: dict) -> str:
    """SHA-256[:16] of canonical JSON — same hash must appear in AI, backtest, and accuracy record."""
    canonical = json.dumps(portfolio_si, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _holding_si(h: dict, portfolio_si: dict) -> dict:
    """Build a single-symbol StrategyInput from one holding + portfolio strategy params."""
    return {
        "symbol":           h["symbol"],
        "start_date":       portfolio_si["start_date"],
        "end_date":         portfolio_si["end_date"],
        "initial_capital":  float(h["allocated_capital"]),
        "benchmark":        portfolio_si["benchmark"],
        "direction":        portfolio_si["direction"],
        "side":             portfolio_si["side"],
        "dte":              portfolio_si["dte"],
        "delta":            portfolio_si["delta"],
        "legs":             portfolio_si["legs"],
        "entry_frequency":  portfolio_si["entry_frequency"],
        "decision_horizon": portfolio_si["decision_horizon"],
    }


def _sf(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _map_decision(total_return_pct: float, final_capital: float, initial_capital: float) -> str:
    """Phase-8 decision — P&L magnitude overrides win_rate (same rule as single-stock mode)."""
    if final_capital <= 0:
        return "SELL"
    if total_return_pct <= -50:
        return "SELL"
    if total_return_pct > 5:
        return "BUY"
    if total_return_pct < -5:
        return "SELL"
    return "HOLD"


def _year_span(start_date: str, end_date: str) -> float:
    try:
        s = datetime.strptime(str(start_date)[:10], "%Y-%m-%d")
        e = datetime.strptime(str(end_date)[:10], "%Y-%m-%d")
        return max(0.01, (e - s).days / 365.25)
    except Exception:
        return 1.0


def _cagr(initial: float, final: float, years: float) -> float:
    if initial <= 0 or final <= 0 or years <= 0:
        return 0.0
    try:
        return ((final / initial) ** (1.0 / years) - 1.0) * 100.0
    except Exception:
        return 0.0


def _sharpe(ann_return: float, vol: float) -> float:
    return round((ann_return - 4.5) / vol, 2) if vol > 0 else 0.0


def _wsum(holding_list: list, key: str, initial_capital: float) -> float:
    """Capital-weight sum of a metric across holdings."""
    return sum(
        _sf(h.get(key)) * (_sf(h.get("allocated_capital")) / max(initial_capital, 1))
        for h in holding_list
    )


# ══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO AI PREDICTION
# ══════════════════════════════════════════════════════════════════════════════

def run_portfolio_ai_prediction(portfolio_si: dict) -> dict:
    """
    Run AI prediction per holding using run_ai_strategy_prediction.
    AI runs BEFORE backtest — no backtest data passed here (no leakage).
    The raw portfolio string is NEVER passed to the AI agent.
    Aggregate per-holding results into portfolio-level prediction.
    """
    from strategy_prediction_agent import run_ai_strategy_prediction

    holdings       = portfolio_si["holdings"]
    initial_capital = portfolio_si["initial_capital"]
    years          = _year_span(portfolio_si["start_date"], portfolio_si["end_date"])

    holding_predictions = []
    failed_symbols: list = []

    for h in holdings:
        h_si = _holding_si(h, portfolio_si)  # single-symbol StrategyInput — NOT the raw string
        try:
            h_ai = run_ai_strategy_prediction(h_si)
        except Exception as exc:
            h_ai = {"status": "ERROR", "error": str(exc), "decision": "REVIEW"}

        h_initial = h["allocated_capital"]
        h_status  = h_ai.get("status", "ERROR")
        h_final   = _sf(h_ai.get("predicted_final_capital"), h_initial)
        h_pl      = h_final - h_initial
        h_ret     = (h_pl / h_initial * 100) if h_initial > 0 else 0.0
        h_trades  = int(_sf(h_ai.get("predicted_trade_count"), 0))
        h_wr      = _sf(h_ai.get("predicted_win_rate"), 50.0)
        h_dd      = _sf(h_ai.get("predicted_max_drawdown"), 10.0)
        h_vol     = _sf(h_ai.get("predicted_volatility"), 15.0)
        h_sharpe  = _sf(h_ai.get("predicted_sharpe"), 0.0)
        h_risk    = _sf(h_ai.get("predicted_risk_score"), 50.0)
        h_conf    = _sf(h_ai.get("confidence_score"), 60.0)
        h_dec     = h_ai.get("decision") or _map_decision(h_ret, h_final, h_initial)

        if h_status == "ERROR":
            failed_symbols.append(h["symbol"])

        holding_predictions.append({
            "symbol":                  h["symbol"],
            "weight":                  h["weight"],
            "allocated_capital":       h_initial,
            "predicted_final_capital": round(h_final, 2),
            "predicted_pl":            round(h_pl, 2),
            "predicted_return_pct":    round(h_ret, 2),
            "predicted_trade_count":   h_trades,
            "predicted_win_rate":      round(h_wr, 2),
            "predicted_max_drawdown":  round(h_dd, 2),
            "predicted_sharpe":        round(h_sharpe, 2),
            "predicted_volatility":    round(h_vol, 2),
            "predicted_risk_score":    round(h_risk, 1),
            "confidence_score":        round(h_conf, 1),
            "decision":                h_dec,
            "status":                  h_status,
        })

    # ── Aggregate ──────────────────────────────────────────────────────────────
    total_final  = sum(p["predicted_final_capital"] for p in holding_predictions)
    total_pl     = total_final - initial_capital
    total_ret    = (total_pl / initial_capital * 100) if initial_capital > 0 else 0.0
    total_trades = sum(p["predicted_trade_count"] for p in holding_predictions)

    if total_trades > 0:
        pf_wr = (
            sum(p["predicted_win_rate"] * p["predicted_trade_count"] for p in holding_predictions)
            / total_trades
        )
    else:
        pf_wr = (
            sum(p["predicted_win_rate"] * p["allocated_capital"] for p in holding_predictions)
            / max(initial_capital, 1)
        )

    pf_dd    = _wsum(holding_predictions, "predicted_max_drawdown", initial_capital)
    pf_vol   = _wsum(holding_predictions, "predicted_volatility",   initial_capital)
    pf_risk  = _wsum(holding_predictions, "predicted_risk_score",   initial_capital)
    pf_conf  = _wsum(holding_predictions, "confidence_score",        initial_capital)
    pf_cagr  = _cagr(initial_capital, total_final, years)
    pf_sharpe = _sharpe(pf_cagr, max(pf_vol, 0.01))

    pf_decision = _map_decision(total_ret, total_final, initial_capital)
    if len(failed_symbols) >= max(1, (len(holdings) + 1) // 2):
        pf_decision = "REVIEW"

    return {
        "status":              "SUCCESS" if not failed_symbols else "PARTIAL",
        "source":              "portfolio_ai_prediction_agent",
        "decision":            pf_decision,
        "initial_capital":     round(initial_capital, 2),
        "final_capital":       round(total_final, 2),
        "total_pl":            round(total_pl, 2),
        "total_return_pct":    round(total_ret, 2),
        "cagr":                round(pf_cagr, 2),
        "sharpe":              round(pf_sharpe, 2),
        "sortino":             round(pf_sharpe * 1.1, 2),
        "max_drawdown":        round(pf_dd, 2),
        "win_rate":            round(pf_wr, 2),
        "trade_count":         total_trades,
        "alpha":               round(pf_cagr - 12.0 * years, 2),
        "beta":                0.85,
        "volatility":          round(pf_vol, 2),
        "risk_score":          round(pf_risk, 1),
        "confidence_score":    round(pf_conf, 1),
        "holding_predictions": holding_predictions,
        "failed_holdings":     failed_symbols,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO BACKTEST ACTUAL
# ══════════════════════════════════════════════════════════════════════════════

def run_portfolio_backtest_actual(portfolio_si: dict, backtest_fn: Callable) -> dict:
    """
    Run tastytrade backtest per holding with its allocated capital.
    backtest_fn is run_tastytrade_strategy_backtest from streamlit_app.
    The raw portfolio string is NEVER passed to backtest_fn.
    Each call uses {symbol: holding.symbol, initial_capital: holding.allocated_capital, ...}.
    """
    holdings        = portfolio_si["holdings"]
    initial_capital = portfolio_si["initial_capital"]
    years           = _year_span(portfolio_si["start_date"], portfolio_si["end_date"])

    holding_actuals = []
    failed_symbols: list = []

    for h in holdings:
        h_si = _holding_si(h, portfolio_si)  # single symbol only — NEVER the raw string
        try:
            h_bt = backtest_fn(h_si)
        except Exception as exc:
            h_bt = {"passed_validation": False, "status": "ERROR", "error": str(exc)}

        h_initial = h["allocated_capital"]
        h_passed  = h_bt.get("passed_validation", False)

        if not h_passed:
            failed_symbols.append(h["symbol"])
            h_final  = h_initial
            h_pl     = 0.0
            h_ret    = 0.0
            h_trades = 0
            h_wr     = 0.0
            h_dd     = 0.0
            h_dec    = "REVIEW"
        else:
            h_final  = _sf(h_bt.get("final_capital"), h_initial)
            h_pl     = h_final - h_initial
            h_ret    = (h_pl / h_initial * 100) if h_initial > 0 else 0.0
            h_trades = int(_sf(h_bt.get("trade_count"), 0))
            h_wr     = _sf(h_bt.get("win_rate"), 0.0)
            h_dd     = _sf(h_bt.get("max_drawdown"), 0.0)
            h_dec    = h_bt.get("decision") or _map_decision(h_ret, h_final, h_initial)

        holding_actuals.append({
            "symbol":               h["symbol"],
            "weight":               h["weight"],
            "allocated_capital":    h_initial,
            "actual_final_capital": round(h_final, 2),
            "actual_pl":            round(h_pl, 2),
            "actual_return_pct":    round(h_ret, 2),
            "actual_trade_count":   h_trades,
            "actual_win_rate":      round(h_wr, 2),
            "actual_max_drawdown":  round(h_dd, 2),
            "decision":             h_dec,
            "status":               "SUCCESS" if h_passed else "FAILED",
            "passed":               h_passed,
        })

    # ── Aggregate ──────────────────────────────────────────────────────────────
    total_final  = sum(a["actual_final_capital"] for a in holding_actuals)
    total_pl     = total_final - initial_capital
    total_ret    = (total_pl / initial_capital * 100) if initial_capital > 0 else 0.0
    total_trades = sum(a["actual_trade_count"] for a in holding_actuals)

    successful = [a for a in holding_actuals if a["passed"]]
    if total_trades > 0:
        pf_wr = (
            sum(a["actual_win_rate"] * a["actual_trade_count"] for a in successful)
            / max(total_trades, 1)
        )
    elif successful:
        pf_wr = (
            sum(a["actual_win_rate"] * a["allocated_capital"] for a in successful)
            / max(initial_capital, 1)
        )
    else:
        pf_wr = 0.0

    pf_dd    = _wsum(holding_actuals, "actual_max_drawdown", initial_capital)
    pf_vol   = 15.0  # approximation — tastytrade doesn't always return per-holding vol
    pf_cagr  = _cagr(initial_capital, total_final, years)
    pf_sharpe = _sharpe(pf_cagr, pf_vol)

    all_passed = len(failed_symbols) == 0
    if failed_symbols:
        bt_status   = "PARTIAL_FAILED"
        pf_decision = (
            "REVIEW" if len(failed_symbols) > len(holdings) // 2
            else _map_decision(total_ret, total_final, initial_capital)
        )
    else:
        bt_status   = "SUCCESS"
        pf_decision = _map_decision(total_ret, total_final, initial_capital)

    return {
        "status":            bt_status,
        "source":            "portfolio_tastytrade_backtester",
        "passed_validation": all_passed,
        "decision":          pf_decision,
        "initial_capital":   round(initial_capital, 2),
        "final_capital":     round(total_final, 2),
        "total_pl":          round(total_pl, 2),
        "total_return_pct":  round(total_ret, 2),
        "cagr":              round(pf_cagr, 2),
        "sharpe":            round(pf_sharpe, 2),
        "sortino":           round(pf_sharpe * 1.05, 2),
        "max_drawdown":      round(pf_dd, 2),
        "win_rate":          round(pf_wr, 2),
        "trade_count":       total_trades,
        "alpha":             round(pf_cagr - 12.0 * years, 2),
        "beta":              0.85,
        "volatility":        pf_vol,
        "risk_score":        round(min(100, pf_dd * 1.2 + (1 - pf_wr / 100) * 20), 1),
        "confidence_score":  max(30.0, 85.0 - len(failed_symbols) * 15.0),
        "holding_actuals":   holding_actuals,
        "failed_holdings":   failed_symbols,
    }


# ══════════════════════════════════════════════════════════════════════════════
# COMPARISON ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def compare_portfolio_ai_vs_backtest(pf_ai: dict, pf_bt: dict) -> dict:
    """Compare portfolio-level AI prediction vs backtest actual."""

    def _sign(v) -> int:
        try:
            f = float(v)
            return 1 if f > 0 else (-1 if f < 0 else 0)
        except (TypeError, ValueError):
            return 0

    ai_dec = str(pf_ai.get("decision", "REVIEW")).upper()
    bt_dec = str(pf_bt.get("decision", "REVIEW")).upper()

    decision_match    = (ai_dec == bt_dec)
    directional_match = (
        _sign(pf_ai.get("total_return_pct", 0)) ==
        _sign(pf_bt.get("total_return_pct", 0))
    )

    ai_ret  = _sf(pf_ai.get("total_return_pct"))
    bt_ret  = _sf(pf_bt.get("total_return_pct"))
    ai_pl   = _sf(pf_ai.get("total_pl"))
    bt_pl   = _sf(pf_bt.get("total_pl"))
    ai_cap  = _sf(pf_ai.get("final_capital"))
    bt_cap  = _sf(pf_bt.get("final_capital"))
    ai_wr   = _sf(pf_ai.get("win_rate"))
    bt_wr   = _sf(pf_bt.get("win_rate"))
    ai_dd   = _sf(pf_ai.get("max_drawdown"))
    bt_dd   = _sf(pf_bt.get("max_drawdown"))
    ic      = _sf(pf_bt.get("initial_capital"), 100_000)

    cap_err_pct = abs(ai_cap - bt_cap) / max(abs(ic), 1) * 100

    # Holding-level comparisons
    preds_map   = {p["symbol"]: p for p in pf_ai.get("holding_predictions", [])}
    actuals_map = {a["symbol"]: a for a in pf_bt.get("holding_actuals", [])}
    all_syms    = sorted(set(list(preds_map.keys()) + list(actuals_map.keys())))

    holding_comparisons = []
    for sym in all_syms:
        pred   = preds_map.get(sym, {})
        actual = actuals_map.get(sym, {})
        ai_h_ret = _sf(pred.get("predicted_return_pct"))
        bt_h_ret = _sf(actual.get("actual_return_pct"))
        ai_h_cap = _sf(pred.get("predicted_final_capital"))
        bt_h_cap = _sf(actual.get("actual_final_capital"))
        h_ret_err   = abs(ai_h_ret - bt_h_ret)
        h_dir_match = (_sign(ai_h_ret) == _sign(bt_h_ret))

        if h_dir_match and h_ret_err < 5:
            verdict = "ACCURATE"
        elif h_dir_match:
            verdict = "DIRECTION CORRECT"
        elif h_ret_err > 20:
            verdict = "LARGE ERROR"
        else:
            verdict = "DIRECTIONAL MISMATCH"

        holding_comparisons.append({
            "symbol":            sym,
            "weight":            pred.get("weight") or actual.get("weight", 0),
            "allocated_capital": pred.get("allocated_capital") or actual.get("allocated_capital", 0),
            "ai_decision":       pred.get("decision", "—"),
            "bt_decision":       actual.get("decision", "—"),
            "ai_final_capital":  round(ai_h_cap, 2),
            "bt_final_capital":  round(bt_h_cap, 2),
            "ai_return_pct":     round(ai_h_ret, 2),
            "bt_return_pct":     round(bt_h_ret, 2),
            "return_error":      round(h_ret_err, 2),
            "directional_match": h_dir_match,
            "holding_verdict":   verdict,
        })

    # Determine final agreement and verified decision
    bt_failed = pf_bt.get("failed_holdings", [])
    n_holdings = len(pf_bt.get("holding_actuals", []))
    if bt_failed and len(bt_failed) >= max(1, n_holdings):
        agreement               = "UNVERIFIED"
        final_verified_decision = "REVIEW"
        agreement_msg           = "Backtest failed for all holdings — unverified."
    elif decision_match:
        agreement               = "MATCH"
        final_verified_decision = bt_dec
        agreement_msg           = f"Both engines agree: {bt_dec}. Ground-truth verified."
    elif directional_match:
        agreement               = "PARTIAL"
        final_verified_decision = bt_dec
        agreement_msg           = f"Directional agreement (AI={ai_dec}, BT={bt_dec}). Use backtest decision."
    elif {ai_dec, bt_dec} == {"BUY", "SELL"}:
        agreement               = "CONFLICT"
        final_verified_decision = "REVIEW"
        agreement_msg           = f"Engines conflict ({ai_dec} vs {bt_dec}). Manual review required."
    else:
        agreement               = "PARTIAL"
        final_verified_decision = bt_dec
        agreement_msg           = f"Partial: AI={ai_dec}, backtest={bt_dec}."

    return {
        "ai_decision":              ai_dec,
        "bt_decision":              bt_dec,
        "decision_match":           decision_match,
        "directional_match":        directional_match,
        "agreement":                agreement,
        "agreement_message":        agreement_msg,
        "final_verified_decision":  final_verified_decision,
        "return_error_pct":         round(abs(ai_ret - bt_ret), 2),
        "pl_error":                 round(abs(ai_pl - bt_pl), 2),
        "final_capital_error_pct":  round(cap_err_pct, 2),
        "win_rate_error":           round(abs(ai_wr - bt_wr), 2),
        "drawdown_error":           round(abs(ai_dd - bt_dd), 2),
        "holding_comparisons":      holding_comparisons,
    }
