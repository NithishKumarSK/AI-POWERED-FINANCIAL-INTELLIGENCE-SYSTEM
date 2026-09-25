"""
Strategy Backtest Comparator
Compares AI strategy prediction output vs tastytrade backtest actual output.
Computes numeric error metrics and agreement classification.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


def _safe(val, default=0.0):
    """Return float or default for None/invalid."""
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def compare_prediction_vs_backtest(
    ai_prediction: dict,
    backtest_actual: dict,
) -> dict:
    """
    Compare AI strategy prediction vs tastytrade backtest actual.

    Returns ComparisonOutput with:
    - decision_match: bool
    - directional_match: bool
    - numeric error metrics
    - agreement classification
    - final verified decision
    """
    ai_d  = str(ai_prediction.get("decision",  "REVIEW")).upper()
    bt_d  = str(backtest_actual.get("decision", "REVIEW")).upper()
    ai_ok = ai_prediction.get("status") == "SUCCESS"
    bt_ok = backtest_actual.get("passed_validation", False)

    # ── Decision agreement ────────────────────────────────────────────────
    decision_match = ai_d == bt_d

    # Directional match: both positive (BUY) or both negative (SELL) or both neutral (HOLD)
    def _dir(d: str) -> str:
        if d == "BUY":   return "positive"
        if d == "SELL":  return "negative"
        return "neutral"
    directional_match = _dir(ai_d) == _dir(bt_d)

    # ── Numeric error metrics ─────────────────────────────────────────────
    ai_ret  = _safe(ai_prediction.get("predicted_total_return_pct"))
    bt_ret  = _safe(backtest_actual.get("total_return_pct"))
    ai_pl   = _safe(ai_prediction.get("predicted_total_pl"))
    bt_pl   = _safe(backtest_actual.get("total_pl"))
    ai_fc   = _safe(ai_prediction.get("predicted_final_capital"))
    bt_fc   = _safe(backtest_actual.get("final_capital"))
    ai_wr   = _safe(ai_prediction.get("predicted_win_rate"))
    bt_wr   = _safe(backtest_actual.get("win_rate"))

    # Signed and absolute errors
    return_error_pct     = round(ai_ret - bt_ret, 2)
    pl_error             = round(ai_pl - bt_pl, 2)
    final_capital_error  = round(ai_fc - bt_fc, 2)
    win_rate_error       = round(ai_wr - bt_wr, 2)

    # As % of actual (relative error)
    bt_cap = _safe(backtest_actual.get("initial_capital"), 100_000)
    final_capital_error_pct = round(final_capital_error / bt_cap * 100, 2) if bt_cap else 0.0

    # ── Agreement classification ──────────────────────────────────────────
    if not ai_ok and not bt_ok:
        agreement    = "MISSING"
        final_dec    = "REVIEW"
        agreement_msg = "Neither engine produced a valid result."
    elif not bt_ok:
        agreement    = "MISSING"
        final_dec    = ai_d
        agreement_msg = "Backtesting failed — using AI prediction only."
    elif not ai_ok:
        agreement    = "MISSING"
        final_dec    = bt_d
        agreement_msg = "AI prediction failed — using backtest decision only."
    elif ai_d == bt_d:
        agreement    = "MATCH"
        final_dec    = bt_d
        agreement_msg = f"Both engines agree: {bt_d}. Ground-truth verified."
    elif {ai_d, bt_d} == {"BUY", "SELL"}:
        agreement    = "CONFLICT"
        final_dec    = "REVIEW"
        agreement_msg = f"Engines conflict ({ai_d} vs {bt_d}). Manual review required."
    elif bt_d == "BUY" and ai_d == "HOLD":
        agreement    = "PARTIAL POSITIVE"
        final_dec    = "BUY WITH CAUTION"
        agreement_msg = (f"Backtest validates BUY; AI predicted HOLD (conservative). "
                         f"Cautious entry suggested — consider reduced position size.")
    elif ai_d == "BUY" and bt_d == "HOLD":
        agreement    = "PARTIAL"
        final_dec    = "HOLD WITH WATCHLIST"
        agreement_msg = "AI predicted BUY but backtest validates HOLD. Monitor closely."
    elif bt_d == "SELL" and ai_d == "HOLD":
        agreement    = "PARTIAL NEGATIVE"
        final_dec    = "AVOID"
        agreement_msg = "Backtest signals SELL; AI was conservative with HOLD. Avoid strategy."
    elif ai_d == "SELL" and bt_d == "HOLD":
        agreement    = "PARTIAL NEGATIVE"
        final_dec    = "HOLD"
        agreement_msg = "AI predicted SELL but backtest validates HOLD. Stay cautious."
    else:
        agreement    = "PARTIAL"
        final_dec    = "HOLD"
        agreement_msg = f"Partial: AI={ai_d}, backtest={bt_d}. Proceed with caution."

    return {
        "ai_decision":               ai_d,
        "backtest_decision":         bt_d,
        "decision_match":            decision_match,
        "directional_match":         directional_match,
        "agreement":                 agreement,
        "final_decision":            final_dec,
        "agreement_message":         agreement_msg,
        # Numeric differences
        "return_error_pct":          return_error_pct,
        "pl_error":                  pl_error,
        "final_capital_error":       final_capital_error,
        "final_capital_error_pct":   final_capital_error_pct,
        "win_rate_error":            win_rate_error,
        # Raw values for display
        "ai_return_pct":             ai_ret,
        "bt_return_pct":             bt_ret,
        "ai_pl":                     ai_pl,
        "bt_pl":                     bt_pl,
        "ai_final_capital":          ai_fc,
        "bt_final_capital":          bt_fc,
        "ai_win_rate":               ai_wr,
        "bt_win_rate":               bt_wr,
    }


def enrich_backtest_metrics(bt_m: dict, strategy_input: dict) -> dict:
    """
    Compute missing backtest metrics (CAGR, drawdown, volatility, etc.)
    from trial data and strategy input when tastytrade API doesn't return them.
    Returns enriched copy.
    """
    import math

    m = dict(bt_m)
    trial_rows  = m.get("trial_rows", []) or []
    initial_cap = _safe(m.get("initial_capital"), 100_000)
    total_ret   = _safe(m.get("total_return_pct"))
    total_pl    = _safe(m.get("total_pl"))
    win_rate    = _safe(m.get("win_rate"))  # already in %
    trade_count = m.get("trade_count") or len(trial_rows)

    # Years from strategy_input
    try:
        from strategy_prediction_agent import _get_years, _get_trade_count
        years = _get_years(strategy_input["start_date"], strategy_input["end_date"])
        freq  = strategy_input.get("entry_frequency", "monthly")
    except Exception:
        years = 3.5
        freq  = "monthly"

    # ── CAGR ──────────────────────────────────────────────────────────────
    if m.get("cagr") is None and initial_cap > 0 and years > 0:
        final_cap = initial_cap + total_pl
        if final_cap > 0:
            m["cagr"] = round(((final_cap / initial_cap) ** (1.0 / years) - 1.0) * 100, 2)

    # ── Final capital ─────────────────────────────────────────────────────
    if m.get("final_capital") is None:
        m["final_capital"] = round(initial_cap + total_pl, 2)

    # ── Max drawdown from equity curve ────────────────────────────────────
    if m.get("max_drawdown") is None and trial_rows:
        equity = initial_cap
        peak   = initial_cap
        max_dd = 0.0
        for t in trial_rows:
            pl = _safe(t.get("profit_loss"))
            equity += pl
            if equity > peak:
                peak = equity
            if peak > 0:
                dd = (peak - equity) / peak
                if dd > max_dd:
                    max_dd = dd
        m["max_drawdown"] = round(max_dd * 100, 2)

    # ── Volatility from trade returns ─────────────────────────────────────
    if m.get("volatility") is None and len(trial_rows) > 1:
        rets = [_safe(t.get("profit_loss")) / initial_cap * 100 for t in trial_rows]
        mean = sum(rets) / len(rets)
        var  = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        period_std = var ** 0.5
        periods_per_year = 12 if "month" in freq else 52 if "week" in freq else 252
        ann_vol = period_std * (periods_per_year ** 0.5)
        m["volatility"] = round(ann_vol, 2)

    # ── Sharpe from CAGR + volatility ─────────────────────────────────────
    if m.get("sharpe") is None and m.get("cagr") is not None and m.get("volatility"):
        rfr = 4.5
        m["sharpe"] = round((m["cagr"] - rfr) / m["volatility"], 2)

    # ── Sortino ───────────────────────────────────────────────────────────
    if m.get("sortino") is None and m.get("cagr") is not None and m.get("volatility"):
        downside_vol = m["volatility"] * 0.65
        if downside_vol > 0:
            m["sortino"] = round((m["cagr"] - 4.5) / downside_vol, 2)

    # ── Beta from strategy type ───────────────────────────────────────────
    if m.get("beta") is None:
        direction = strategy_input.get("direction", "short")
        side      = strategy_input.get("side", "put")
        delta_val = int(strategy_input.get("delta", 30))
        legs_val  = int(strategy_input.get("legs", 1))
        if direction == "short" and side == "put":
            sign = 1
        elif direction == "short" and side == "call":
            sign = -1
        else:
            sign = 1
        m["beta"] = round((delta_val / 100) * min(legs_val, 2) * 0.5 * sign, 3)

    # ── Max profit / max loss from trial rows ────────────────────────────
    if m.get("max_profit") is None and trial_rows:
        profits = [_safe(t.get("profit_loss")) for t in trial_rows]
        m["max_profit"] = round(max(profits), 2) if profits else None
    if m.get("max_loss") is None and trial_rows:
        profits = [_safe(t.get("profit_loss")) for t in trial_rows]
        m["max_loss"] = round(min(profits), 2) if profits else None

    # ── Alpha = strategy CAGR - SPY approx (12% ann) ─────────────────────
    if m.get("alpha") is None and m.get("cagr") is not None:
        m["alpha"] = round(m["cagr"] - 12.0, 2)

    # ── Risk score ────────────────────────────────────────────────────────
    if m.get("risk_score") is None:
        dd = _safe(m.get("max_drawdown"), 0) / 50
        vv = _safe(m.get("volatility"),   0) / 45
        lr = (100 - _safe(win_rate, 50)) / 100
        m["risk_score"] = max(0, min(100, round(min(1, dd)*40 + min(1, vv)*30 + lr*30)))

    # ── Confidence score ──────────────────────────────────────────────────
    if m.get("confidence_score") is None:
        n = trade_count or 1
        m["confidence_score"] = min(100, max(30, round(40 + min(30, n * 0.6) + (_safe(win_rate)/100) * 30)))

    return m
