"""
Portfolio Mode — Detection, Parsing, AI Analysis, and Streamlit Rendering.

Handles multi-symbol weighted inputs like:
  GOOGL 50% AAPL 20% TSLA 20% MSFT 10%
  AAPL 40%, MSFT 30%, NVDA 30%
  AAPL MSFT TSLA  (equal weights auto-assigned)

Completely separate from single-symbol strategy backtest mode.
Single-symbol validation is never called on the raw portfolio string.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)


# ══════════════════════════════════════════════════════════════════════════════
# MODE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def detect_input_mode(raw: str) -> str:
    """
    Returns "portfolio" for multi-symbol / weighted inputs.
    Returns "single_strategy" for everything else (blank included — the
    single-symbol validator handles blank and fake-symbol blocking).

    Examples:
      "AAPL"                                    → single_strategy
      "MSFT"                                    → single_strategy
      "GOOGL 50% AAPL 20% TSLA 20% MSFT 10%"  → portfolio
      "AAPL 40%, MSFT 30%, NVDA 30%"           → portfolio
      "AAPL MSFT NVDA"                          → portfolio (3 tickers)
      ""                                        → single_strategy
    """
    if not raw or not raw.strip():
        return "single_strategy"

    text = raw.strip()

    # Explicit % sign → portfolio weight syntax
    if "%" in text:
        return "portfolio"

    # Colon or equals weight syntax: AAPL:40 or AAPL=40
    if re.search(r"\b[A-Za-z]{1,5}\s*[:=]\s*\d", text):
        return "portfolio"

    # Multiple space/comma-separated ticker-like tokens → portfolio
    tokens = re.split(r"[\s,;]+", text)
    ticker_tokens = [
        t for t in tokens
        if t and re.match(r"^[A-Z]{1,5}([.\-][A-Z])?$", t.upper())
    ]
    if len(ticker_tokens) >= 2:
        return "portfolio"

    return "single_strategy"


# ══════════════════════════════════════════════════════════════════════════════
# PARSING + PER-SYMBOL VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def parse_and_validate_portfolio(raw: str, initial_capital: float) -> dict:
    """
    Parse portfolio string using existing portfolio_parser, then validate
    EACH ticker individually using strategy_validation.validate_symbol().

    Returns:
      {"status": "SUCCESS", "holdings": [...], "total_weight": float, "issues": [...]}
      {"status": "ERROR",   "errors": [...]}
    """
    from portfolio_parser import parse_portfolio_input
    from strategy_validation import validate_symbol

    parsed = parse_portfolio_input(raw)
    if parsed.get("status") != "SUCCESS":
        return {
            "status": "ERROR",
            "errors": parsed.get("issues", ["Could not parse portfolio input."]),
        }

    raw_holdings = parsed.get("holdings", [])
    if not raw_holdings:
        return {"status": "ERROR", "errors": ["No valid portfolio holdings found."]}

    errors: List[str] = []
    validated = []
    for h in raw_holdings:
        ticker = h["ticker"]
        ok, sym_err = validate_symbol(ticker)
        if not ok:
            errors.append(sym_err)
        else:
            weight = float(h["weight"])
            validated.append({
                "ticker":     ticker,
                "weight":     weight,
                "weight_pct": round(weight * 100, 1),
                "allocation": round(weight * initial_capital, 2),
            })

    if errors:
        return {"status": "ERROR", "errors": errors}

    if not validated:
        return {"status": "ERROR", "errors": ["No holdings remained after symbol validation."]}

    total_w = sum(h["weight"] for h in validated)
    if not (0.995 <= total_w <= 1.005):
        return {
            "status": "ERROR",
            "errors": [
                f"Weight total must equal 100%. "
                f"Current total: {total_w * 100:.1f}%. "
                f"Adjust weights or ensure they sum to 100."
            ],
        }

    return {
        "status":       "SUCCESS",
        "holdings":     validated,
        "total_weight": total_w,
        "issues":       parsed.get("issues", []),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO ANALYSIS ENGINE — Deterministic first, Gemini for narrative only
# ══════════════════════════════════════════════════════════════════════════════

_HIGH_VOL_SYMBOLS: frozenset = frozenset({
    "TSLA", "GME", "AMC", "NVDA", "COIN", "MSTR", "PLTR", "RIVN", "LCID",
    "SOFI", "SPCE", "CLOV", "WISH", "HOOD", "CRWD", "RBLX", "BYND", "NIO",
})


def safe_parse_llm_json(text: str):
    """
    Returns (parsed_dict, None) on success or (None, error_str) on failure.
    Strips markdown fences; on failure tries to extract the first balanced JSON object.
    """
    if not text:
        return None, "Empty response from LLM"
    cleaned = re.sub(r"```(?:json)?\n?", "", text).strip("`").strip()
    try:
        return json.loads(cleaned), None
    except json.JSONDecodeError:
        pass
    try:
        start = cleaned.index("{")
        depth = 0
        for i, ch in enumerate(cleaned[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(cleaned[start: i + 1]), None
    except (ValueError, json.JSONDecodeError):
        pass
    return None, f"Malformed JSON (length={len(text)})"


def run_deterministic_portfolio_analysis(
    holdings: list,
    initial_capital: float,
    benchmark: str,
) -> dict:
    """
    Compute all portfolio metrics deterministically — no Gemini, no external APIs.
    Always returns a complete dict with status=SUCCESS.
    """
    n = len(holdings)
    weights = [h["weight"] for h in holdings]
    tickers = [h["ticker"] for h in holdings]

    max_weight = max(weights)
    max_ticker = tickers[weights.index(max_weight)]
    hhi = sum(w ** 2 for w in weights)

    diversification_score = round(max(0, min(100, (1 - hhi) * 100)))

    high_vol_tickers = [t for t in tickers if t in _HIGH_VOL_SYMBOLS]
    high_vol_weight = sum(
        h["weight"] for h in holdings if h["ticker"] in _HIGH_VOL_SYMBOLS
    )

    concentration_penalty = round(max_weight * 60)
    hhi_penalty = round(hhi * 40)
    vol_penalty = round(high_vol_weight * 30)
    small_n_penalty = max(0, (3 - n) * 5)
    risk_score = min(
        100, max(0, concentration_penalty + hhi_penalty + vol_penalty + small_n_penalty)
    )

    if max_weight >= 0.50:
        concentration_risk = "HIGH"
    elif max_weight >= 0.35:
        concentration_risk = "MODERATE"
    else:
        concentration_risk = "LOW"

    portfolio_score = round(min(100, max(0,
        diversification_score * 0.40
        + (100 - risk_score) * 0.35
        + min(n * 10, 40) * 0.25
    )))
    confidence_score = round(max(40, min(85, 80 - (100 - portfolio_score) * 0.3)))

    if max_weight >= 0.50:
        recommendation = "REBALANCE"
    elif risk_score >= 75:
        recommendation = "REDUCE_RISK"
    elif diversification_score >= 65 and risk_score < 55:
        recommendation = "HOLD"
    else:
        recommendation = "HOLD"

    expected_return_pct = round(
        max(2.0, min(20.0, 9.0 - (risk_score - 50) * 0.12)), 1
    )
    expected_drawdown_pct = round(
        max(8.0, min(55.0, 15 + hhi * 30 + high_vol_weight * 20)), 1
    )

    big_caps = {"GOOGL", "MSFT", "AAPL", "AMZN", "META", "BRK.B", "JPM"}
    strengths = []
    if n >= 4:
        strengths.append(f"{n}-holding portfolio provides basic diversification")
    if any(t in big_caps for t in tickers):
        strengths.append("Exposure to large-cap, liquid equities")
    if diversification_score >= 60:
        strengths.append(f"Reasonable diversification score ({diversification_score}/100)")
    if not strengths:
        strengths = [
            "Portfolio has defined weights for all positions",
            "No invalid symbols detected",
        ]
    strengths = strengths[:3]

    risks = []
    if max_weight >= 0.50:
        risks.append(
            f"Over-concentration in {max_ticker} ({max_weight * 100:.0f}% of portfolio)"
        )
    if high_vol_tickers:
        risks.append(f"High-volatility holdings: {', '.join(high_vol_tickers)}")
    if hhi > 0.30:
        risks.append(f"HHI index {hhi:.2f} indicates above-average concentration")
    if not risks:
        risks = [
            "Standard market risk applies to all equity holdings",
            "Monitor positions against benchmark",
        ]
    risks = risks[:3]

    actions = []
    if max_weight >= 0.50:
        actions.append(
            f"Reduce {max_ticker} to ≤35% — currently {max_weight * 100:.0f}%"
        )
    if high_vol_tickers:
        actions.append(f"Review position sizing for: {', '.join(high_vol_tickers)}")
    if n < 5:
        actions.append("Consider adding 1-2 defensive or dividend positions")
    if not actions:
        actions = [
            "Maintain allocation and review quarterly",
            "Monitor benchmark relative performance",
        ]
    actions = actions[:3]

    risk_status = (
        "HIGH" if risk_score >= 70 else
        "MODERATE" if risk_score >= 50 else "LOW"
    )
    div_status = (
        "WELL_DIVERSIFIED" if diversification_score >= 70 else
        "MODERATELY_DIVERSIFIED" if diversification_score >= 50 else "CONCENTRATED"
    )

    explanation = (
        f"Portfolio of {n} holdings totalling ${initial_capital:,.0f} "
        f"benchmarked against {benchmark}. "
        f"Largest position: {max_ticker} at {max_weight * 100:.0f}%. "
        f"HHI={hhi:.2f}. Recommendation: {recommendation}."
    )

    holding_analysis = []
    for h in holdings:
        ticker = h["ticker"]
        w = h["weight"]
        if w >= 0.40:
            decision = "REBALANCE"
        elif ticker in _HIGH_VOL_SYMBOLS and w >= 0.20:
            decision = "REDUCE"
        else:
            decision = "HOLD"
        rl = (
            "HIGH" if ticker in _HIGH_VOL_SYMBOLS else
            "MODERATE" if w >= 0.35 else "LOW"
        )
        rc = round(w * risk_score, 1)
        if decision == "REBALANCE":
            action = f"Trim {ticker} from {w*100:.0f}% to ~30-35%"
        elif decision == "REDUCE":
            action = f"Reduce {ticker} — high volatility at {w*100:.0f}%"
        else:
            action = f"Hold {ticker} at {w*100:.0f}%; review on earnings"
        holding_analysis.append({
            "ticker":                          ticker,
            "ai_decision":                     decision,
            "risk_level":                      rl,
            "portfolio_risk_contribution_pct": rc,
            "suggested_action":                action,
        })

    return {
        "status":                     "SUCCESS",
        "source":                     "deterministic_portfolio_engine",
        "gemini_status":              "NOT_USED",
        "recommendation":             recommendation,
        "portfolio_recommendation":   recommendation,
        "portfolio_score":            portfolio_score,
        "risk_score":                 risk_score,
        "diversification_score":      diversification_score,
        "concentration_risk":         concentration_risk,
        "expected_return_pct":        expected_return_pct,
        "expected_annual_return_pct": expected_return_pct,
        "expected_drawdown_pct":      expected_drawdown_pct,
        "expected_max_drawdown_pct":  expected_drawdown_pct,
        "confidence_score":           confidence_score,
        "confidence":                 confidence_score,
        "top_strengths":              strengths,
        "top_risks":                  risks,
        "recommended_actions":        actions,
        "holding_analysis":           holding_analysis,
        "final_decision":             recommendation,
        "risk_status":                risk_status,
        "diversification_status":     div_status,
        "analysis_summary":           explanation,
        "explanation":                explanation,
        "developer_debug":            {},
    }


def _get_market_context_for_portfolio() -> dict:
    """Fetch gainers/losers from RapidAPI. Returns empty on any failure."""
    try:
        from rapidapi_client import rapidapi_get

        def _syms(r: dict) -> list:
            data = r.get("data", {})
            if isinstance(data, dict):
                return [
                    s.get("s", "").split(":")[-1]
                    for s in data.get("symbols", [])
                    if isinstance(s, dict) and s.get("s")
                ]
            return []

        g = rapidapi_get(
            "/market/get-movers",
            params={"exchange": "US", "name": "percent_change_gainers", "locale": "en"},
            timeout=15,
        )
        l = rapidapi_get(
            "/market/get-movers",
            params={"exchange": "US", "name": "percent_change_losers", "locale": "en"},
            timeout=15,
        )
        return {"gainers": _syms(g)[:5], "losers": _syms(l)[:5]}
    except Exception:
        return {"gainers": [], "losers": []}


def run_portfolio_gemini_analysis(
    holdings: list,
    initial_capital: float,
    benchmark: str,
) -> dict:
    """
    Portfolio analysis: deterministic engine first, Gemini for narrative polish only.
    Returns a complete dict with status=SUCCESS regardless of Gemini outcome.
    Gemini failure is recorded in developer_debug and gemini_status — never shown as main error.
    """
    # Step 1: Always build deterministic result — this is the authoritative output
    result = run_deterministic_portfolio_analysis(holdings, initial_capital, benchmark)

    # Step 2: Try Gemini for narrative enrichment only (text fields, never numeric metrics)
    try:
        import google.generativeai as genai

        api_key = os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            result["developer_debug"]["gemini_note"] = "GOOGLE_API_KEY not configured"
            return result

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("AGENT_MODEL", "gemini-2.5-flash"))

        ctx = _get_market_context_for_portfolio()
        gainers_txt = ", ".join(ctx.get("gainers", [])) or "unavailable"
        losers_txt  = ", ".join(ctx.get("losers",  [])) or "unavailable"

        holdings_txt = "\n".join(
            f"  {h['ticker']}: {h['weight_pct']:.1f}% = ${h['allocation']:,.0f}"
            for h in holdings
        )

        prompt = f"""You are a portfolio analyst. For this portfolio:

{holdings_txt}
Total Capital: ${initial_capital:,.0f} | Benchmark: {benchmark}
Market context — Gainers: {gainers_txt} | Losers: {losers_txt}
Deterministic recommendation: {result['recommendation']}
Risk score: {result['risk_score']}/100 | Diversification: {result['diversification_score']}/100

Return ONLY a JSON object with these exact fields, no markdown fences, no prose outside JSON:
{{
  "top_strengths": ["<str>", "<str>", "<str>"],
  "top_risks": ["<str>", "<str>", "<str>"],
  "recommended_actions": ["<str>", "<str>", "<str>"],
  "analysis_summary": "<2-3 sentence portfolio outlook>"
}}"""

        resp = model.generate_content(
            prompt,
            generation_config={"temperature": 0.1, "max_output_tokens": 600},
        )
        text = (resp.text or "").strip()
        parsed, parse_err = safe_parse_llm_json(text)

        if parsed and isinstance(parsed, dict):
            # Merge ONLY safe text fields — numeric metrics are NEVER overwritten by Gemini
            for field in ("top_strengths", "top_risks", "recommended_actions"):
                val = parsed.get(field)
                if isinstance(val, list) and val:
                    result[field] = val
            summary = parsed.get("analysis_summary", "")
            if summary and isinstance(summary, str) and summary.strip():
                result["analysis_summary"] = summary
                result["explanation"] = summary
            result["gemini_status"] = "USED"
        else:
            result["gemini_status"] = "FAILED"
            result["developer_debug"]["gemini_raw"]   = text[:2000]
            result["developer_debug"]["gemini_error"] = parse_err or "Unknown parse error"

    except Exception as exc:
        result["gemini_status"] = "FAILED"
        result["developer_debug"]["gemini_error"] = str(exc)

    return result


# ══════════════════════════════════════════════════════════════════════════════
# RENDERING — reuses the same CSS classes as streamlit_app.py
# ══════════════════════════════════════════════════════════════════════════════

def _psec(title: str) -> None:
    import streamlit as st
    st.markdown(f'<div class="sec-head">{title}</div>', unsafe_allow_html=True)


def _phr() -> None:
    import streamlit as st
    st.markdown("<hr class='af-hr'>", unsafe_allow_html=True)


def _score_bar(label: str, score: int, color: str = "#2563EB") -> None:
    import streamlit as st
    pct = max(0, min(100, int(score or 0)))
    st.markdown(
        f'<div style="margin-bottom:.6rem">'
        f'<span style="font-size:.85rem;font-weight:600;color:#374151">{label}</span>'
        f'<div style="background:#E5E7EB;border-radius:4px;height:10px;margin-top:4px">'
        f'<div style="background:{color};width:{pct}%;height:10px;border-radius:4px"></div>'
        f'</div>'
        f'<span style="font-size:.8rem;color:#6B7280">{pct} / 100</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


_DEC_BADGE_CFG = {
    "BUY_MORE":    ("#16A34A", "BUY MORE"),
    "HOLD":        ("#2563EB", "HOLD"),
    "REBALANCE":   ("#D97706", "REBALANCE"),
    "REDUCE":      ("#DC2626", "REDUCE"),
    "RESTRUCTURE": ("#7C3AED", "RESTRUCTURE"),
    "BUY":         ("#16A34A", "BUY"),
    "SELL":        ("#DC2626", "SELL"),
}


def _badge(decision: str) -> str:
    col, label = _DEC_BADGE_CFG.get(decision, ("#6B7280", decision))
    return (
        f'<span style="background:{col};color:#fff;font-weight:700;'
        f'font-size:.95rem;padding:.25rem .85rem;border-radius:6px;'
        f'letter-spacing:.05em">{label}</span>'
    )


def _metric_row(label: str, ai_val, bt_val, fmt: str = "{}") -> None:
    """Render one comparison row: label | AI value | BT value."""
    import streamlit as st
    c1, c2, c3 = st.columns([2, 1.5, 1.5])
    c1.markdown(f"<small style='color:#6B7280'>{label}</small>", unsafe_allow_html=True)
    c2.markdown(f"**{fmt.format(ai_val) if ai_val is not None else '—'}**")
    c3.markdown(f"**{fmt.format(bt_val) if bt_val is not None else '—'}**")


def _dec_col(d: str) -> str:
    return {
        "BUY": "#16A34A", "SELL": "#DC2626", "HOLD": "#2563EB",
        "REVIEW": "#6B7280", "REBALANCE": "#D97706", "REDUCE": "#D97706",
    }.get(str(d).upper(), "#374151")


def render_portfolio_sections(portfolio_state: dict) -> None:
    """
    Render 7 portfolio sections from stored session state.
    Called from streamlit_app.py main() after the button-click block.
    Sections:
      1 · Portfolio Inputs Used
      2 · Portfolio AI Prediction vs Portfolio Backtest Actual
      3 · Holding-Level AI vs Backtest
      4 · Portfolio Factor Intelligence
      5 · Final Portfolio Decision Board
      6 · Portfolio Accuracy Metrics
      7 · Portfolio Charts
    """
    import streamlit as st
    import pandas as pd

    holdings  = portfolio_state.get("holdings", [])    # parsed holdings (ticker, weight_pct, allocation)
    issues    = portfolio_state.get("issues",   [])
    si        = portfolio_state.get("si",        {})
    pf_ai     = portfolio_state.get("pf_ai",    {})    # portfolio AI prediction
    pf_bt     = portfolio_state.get("pf_bt",    {})    # portfolio backtest actual
    pf_cmp    = portfolio_state.get("pf_cmp",   {})    # comparison
    det       = portfolio_state.get("deterministic", {})  # factor intelligence
    pf_hash   = portfolio_state.get("portfolio_hash", "—")
    cap       = float(si.get("initial_capital", 100_000))
    bench     = si.get("benchmark", "SPY")

    # ── Section 1: Portfolio Inputs ───────────────────────────────────────────
    _phr()
    _psec("Section 1 · Portfolio Inputs Used")

    if issues:
        for msg in issues:
            st.info(msg)

    cols = st.columns(min(len(holdings), 6))
    for col, h in zip(cols, holdings):
        with col:
            st.metric(
                label=h["ticker"],
                value=f"${h['allocation']:,.0f}",
                delta=f"{h['weight_pct']:.1f}%",
            )

    with st.expander("Full Allocation Table & Strategy Params"):
        df = pd.DataFrame([
            {
                "Ticker":            h["ticker"],
                "Weight":            f"{h['weight_pct']:.1f}%",
                "Capital Allocated": f"${h['allocation']:,.0f}",
                "Validation":        "PASSED",
            }
            for h in holdings
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.markdown(
            f"**Strategy params:** {si.get('direction','').upper()} {si.get('side','').upper()} "
            f"DTE={si.get('dte','')} Δ{si.get('delta','')} legs={si.get('legs','')} "
            f"{si.get('entry_frequency','')} | "
            f"Period: {si.get('start_date','')} → {si.get('end_date','')} | "
            f"Benchmark: {bench} | Hash: `{pf_hash}`"
        )

    # ── Section 2: Portfolio AI vs Backtest ───────────────────────────────────
    _phr()
    _psec("Section 2 · Portfolio AI Prediction vs Portfolio Backtest Actual")

    if not pf_ai and not pf_bt:
        st.info("Portfolio AI prediction and backtest will appear here after running.")
    else:
        # Column headers
        hd0, hd1, hd2 = st.columns([2, 1.5, 1.5])
        hd0.markdown("<small style='color:#6B7280;font-weight:700'>METRIC</small>", unsafe_allow_html=True)
        hd1.markdown(
            "<div style='font-weight:700;color:#2563EB;font-size:.85rem'>AI PREDICTION</div>",
            unsafe_allow_html=True,
        )
        hd2.markdown(
            "<div style='font-weight:700;color:#16A34A;font-size:.85rem'>BACKTEST ACTUAL</div>",
            unsafe_allow_html=True,
        )

        # Decision row
        ai_dec = pf_ai.get("decision", "—")
        bt_dec = pf_bt.get("decision", "—")
        c1, c2, c3 = st.columns([2, 1.5, 1.5])
        c1.markdown("<small style='color:#6B7280'>Decision</small>", unsafe_allow_html=True)
        c2.markdown(
            f'<span style="color:{_dec_col(ai_dec)};font-weight:700">{ai_dec}</span>',
            unsafe_allow_html=True,
        )
        c3.markdown(
            f'<span style="color:{_dec_col(bt_dec)};font-weight:700">{bt_dec}</span>',
            unsafe_allow_html=True,
        )

        ic = pf_ai.get("initial_capital") or pf_bt.get("initial_capital") or cap
        _metric_row("Initial Capital",     f"${ic:,.0f}",                  f"${ic:,.0f}")
        _metric_row("Final Capital",       f"${pf_ai.get('final_capital', 0):,.0f}", f"${pf_bt.get('final_capital', 0):,.0f}")
        _metric_row("Total P&L",           f"${pf_ai.get('total_pl', 0):,.0f}",     f"${pf_bt.get('total_pl', 0):,.0f}")
        _metric_row("Total Return %",      f"{pf_ai.get('total_return_pct', 0):.2f}%", f"{pf_bt.get('total_return_pct', 0):.2f}%")
        _metric_row("CAGR",                f"{pf_ai.get('cagr', 0):.2f}%",          f"{pf_bt.get('cagr', 0):.2f}%")
        _metric_row("Sharpe",              f"{pf_ai.get('sharpe', 0):.2f}",          f"{pf_bt.get('sharpe', 0):.2f}")
        _metric_row("Sortino",             f"{pf_ai.get('sortino', 0):.2f}",         f"{pf_bt.get('sortino', 0):.2f}")
        _metric_row("Max Drawdown",        f"{pf_ai.get('max_drawdown', 0):.2f}%",   f"{pf_bt.get('max_drawdown', 0):.2f}%")
        _metric_row("Win Rate",            f"{pf_ai.get('win_rate', 0):.1f}%",       f"{pf_bt.get('win_rate', 0):.1f}%")
        _metric_row("Trade Count",         str(pf_ai.get("trade_count", 0)),          str(pf_bt.get("trade_count", 0)))
        _metric_row("Alpha",               f"{pf_ai.get('alpha', 0):.2f}%",          f"{pf_bt.get('alpha', 0):.2f}%")
        _metric_row("Beta",                f"{pf_ai.get('beta', 0):.2f}",            f"{pf_bt.get('beta', 0):.2f}")
        _metric_row("Volatility",          f"{pf_ai.get('volatility', 0):.2f}%",     f"{pf_bt.get('volatility', 0):.2f}%")
        _metric_row("Risk Score",          f"{pf_ai.get('risk_score', 0):.0f}/100",  f"{pf_bt.get('risk_score', 0):.0f}/100")
        _metric_row("Confidence Score",    f"{pf_ai.get('confidence_score', 0):.0f}/100", f"{pf_bt.get('confidence_score', 0):.0f}/100")

        # Prediction closeness
        if pf_cmp:
            _phr()
            st.markdown("**Numeric Prediction Closeness**")
            nc1, nc2, nc3, nc4, nc5 = st.columns(5)
            nc1.metric("Return Error",     f"{pf_cmp.get('return_error_pct', 0):.2f}%")
            nc2.metric("P&L Error",        f"${pf_cmp.get('pl_error', 0):,.0f}")
            nc3.metric("Capital Error",    f"{pf_cmp.get('final_capital_error_pct', 0):.2f}%")
            nc4.metric("Win Rate Error",   f"{pf_cmp.get('win_rate_error', 0):.1f}%")
            nc5.metric("Directional Match", "YES" if pf_cmp.get("directional_match") else "NO")

        if pf_bt.get("failed_holdings"):
            st.warning(
                f"Backtest failed for: {', '.join(pf_bt['failed_holdings'])}. "
                "Portfolio result is partial."
            )

    # ── Section 3: Holding-Level AI vs Backtest ───────────────────────────────
    _phr()
    _psec("Section 3 · Holding-Level AI vs Backtest")

    hc_list = pf_cmp.get("holding_comparisons", []) if pf_cmp else []
    if hc_list:
        verdict_colors = {
            "ACCURATE":            "#16A34A",
            "DIRECTION CORRECT":   "#2563EB",
            "LARGE ERROR":         "#DC2626",
            "DIRECTIONAL MISMATCH":"#D97706",
        }
        cols_h = [1.5, 1, 1.2, 1, 1, 1.2, 1.2, 1, 1, 1, 1, 2]
        labels = ["Symbol","Weight","Capital","AI Dec","BT Dec",
                  "AI Final","BT Final","AI Ret%","BT Ret%","Ret Err","Dir","Verdict"]
        hdr_cols = st.columns(cols_h)
        for hdr, lbl in zip(hdr_cols, labels):
            hdr.markdown(
                f"<small style='color:#6B7280;font-weight:600'>{lbl}</small>",
                unsafe_allow_html=True,
            )
        for hc in hc_list:
            row = st.columns(cols_h)
            row[0].markdown(f"**{hc['symbol']}**")
            row[1].markdown(f"{hc.get('weight', 0):.1f}%")
            row[2].markdown(f"${hc.get('allocated_capital', 0):,.0f}")
            ai_d = hc.get("ai_decision", "—")
            bt_d = hc.get("bt_decision", "—")
            row[3].markdown(f'<span style="color:{_dec_col(ai_d)};font-weight:700">{ai_d}</span>',
                            unsafe_allow_html=True)
            row[4].markdown(f'<span style="color:{_dec_col(bt_d)};font-weight:700">{bt_d}</span>',
                            unsafe_allow_html=True)
            row[5].markdown(f"${hc.get('ai_final_capital', 0):,.0f}")
            row[6].markdown(f"${hc.get('bt_final_capital', 0):,.0f}")
            row[7].markdown(f"{hc.get('ai_return_pct', 0):.1f}%")
            row[8].markdown(f"{hc.get('bt_return_pct', 0):.1f}%")
            row[9].markdown(f"{hc.get('return_error', 0):.1f}%")
            row[10].markdown("✔" if hc.get("directional_match") else "✗")
            v = hc.get("holding_verdict", "—")
            row[11].markdown(
                f'<span style="color:{verdict_colors.get(v, "#374151")};font-weight:600">{v}</span>',
                unsafe_allow_html=True,
            )
    else:
        # Fallback: show deterministic holding intelligence when no AI vs BT data yet
        ha_map = {h.get("ticker", ""): h for h in det.get("holding_analysis", [])}
        for holding in holdings:
            t  = holding["ticker"]
            ha = ha_map.get(t, {})
            st.markdown(
                f"**{t}** — {holding['weight_pct']:.1f}% | ${holding['allocation']:,.0f} | "
                f"Decision: {ha.get('ai_decision','—')} | Risk: {ha.get('risk_level','—')} | "
                f"{ha.get('suggested_action','—')}"
            )

    # ── Section 4: Portfolio Factor Intelligence ──────────────────────────────
    _phr()
    _psec("Section 4 · Portfolio Factor Intelligence")

    ai_det = det  # deterministic analysis result
    gemini_status = ai_det.get("gemini_status", "NOT_USED") if ai_det else "NOT_USED"
    if gemini_status == "FAILED":
        st.caption("Gemini narrative unavailable — deterministic portfolio analysis used.")

    if ai_det and ai_det.get("status") == "SUCCESS":
        r1c1, r1c2, r1c3 = st.columns(3)
        with r1c1: _score_bar("Portfolio Score",       ai_det.get("portfolio_score", 0),       "#2563EB")
        with r1c2: _score_bar("Risk Score",            ai_det.get("risk_score", 0),            "#DC2626")
        with r1c3: _score_bar("Diversification Score", ai_det.get("diversification_score", 0), "#16A34A")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Concentration Risk",    ai_det.get("concentration_risk", "—"))
        m2.metric("Expected Annual Return", f"{ai_det.get('expected_annual_return_pct', 0):.1f}%")
        m3.metric("Expected Max Drawdown",  f"{ai_det.get('expected_max_drawdown_pct', 0):.1f}%")
        m4.metric("Factor Confidence",      f"{ai_det.get('confidence', 0)}/100")

        sa1, sa2, sa3 = st.columns(3)
        with sa1:
            st.markdown("**Top Strengths**")
            for s in ai_det.get("top_strengths", []):
                st.markdown(f"&nbsp;&nbsp;+ {s}")
        with sa2:
            st.markdown("**Top Risks**")
            for r in ai_det.get("top_risks", []):
                st.markdown(f"&nbsp;&nbsp;! {r}")
        with sa3:
            st.markdown("**Recommended Actions**")
            for a in ai_det.get("recommended_actions", []):
                st.markdown(f"&nbsp;&nbsp;> {a}")

        if ai_det.get("analysis_summary"):
            st.info(ai_det["analysis_summary"])

        dev_debug = ai_det.get("developer_debug", {})
        if dev_debug or gemini_status == "FAILED":
            with st.expander("Developer Debug — Factor Intelligence"):
                st.json({
                    "gemini_status": gemini_status,
                    "source":        ai_det.get("source", "deterministic_portfolio_engine"),
                    **{k: v for k, v in dev_debug.items()},
                })

    # ── Section 5: Final Portfolio Decision Board ─────────────────────────────
    _phr()
    _psec("Section 5 · Final Portfolio Decision Board")

    ai_fin_dec = pf_ai.get("decision", det.get("portfolio_recommendation", "HOLD"))
    bt_fin_dec = pf_bt.get("decision", "—")
    agreement  = pf_cmp.get("agreement", "—") if pf_cmp else "—"
    final_dec  = pf_cmp.get("final_verified_decision", bt_fin_dec) if pf_cmp else bt_fin_dec
    agr_msg    = pf_cmp.get("agreement_message", "") if pf_cmp else ""

    fd1, fd2, fd3, fd4 = st.columns(4)
    with fd1:
        st.markdown(
            f'<div style="text-align:center">'
            f'<div style="font-size:.75rem;color:#6B7280;font-weight:700;letter-spacing:.08em">'
            f'AI PREDICTED</div>'
            f'<div style="margin-top:.5rem">{_badge(ai_fin_dec)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with fd2:
        st.markdown(
            f'<div style="text-align:center">'
            f'<div style="font-size:.75rem;color:#6B7280;font-weight:700;letter-spacing:.08em">'
            f'BACKTEST ACTUAL</div>'
            f'<div style="margin-top:.5rem">{_badge(bt_fin_dec)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with fd3:
        agr_col = {"MATCH": "#16A34A", "PARTIAL": "#2563EB",
                   "CONFLICT": "#DC2626", "UNVERIFIED": "#6B7280"}.get(agreement, "#374151")
        st.markdown(
            f'<div style="text-align:center">'
            f'<div style="font-size:.75rem;color:#6B7280;font-weight:700;letter-spacing:.08em">'
            f'AGREEMENT</div>'
            f'<div style="margin-top:.5rem;font-size:1rem;font-weight:700;color:{agr_col}">'
            f'{agreement}</div></div>',
            unsafe_allow_html=True,
        )
    with fd4:
        st.markdown(
            f'<div style="text-align:center">'
            f'<div style="font-size:.75rem;color:#6B7280;font-weight:700;letter-spacing:.08em">'
            f'FINAL VERIFIED</div>'
            f'<div style="margin-top:.5rem">{_badge(final_dec)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if agr_msg:
        st.info(agr_msg)

    # ── Section 6: Portfolio Accuracy Metrics ─────────────────────────────────
    _phr()
    _psec("Section 6 · Portfolio Accuracy Metrics")

    try:
        from portfolio_accuracy_engine import (
            load_portfolio_evaluation_records,
            calculate_portfolio_accuracy_metrics,
        )
        records = load_portfolio_evaluation_records()
        acc = calculate_portfolio_accuracy_metrics(records)

        if acc.get("status") == "SUCCESS":
            st.caption(
                "Portfolio accuracy measures AI portfolio prediction closeness against "
                "aggregated per-holding backtest actuals."
            )
            a1, a2, a3, a4 = st.columns(4)
            a1.metric("Overall Portfolio Accuracy", f"{acc['overall_accuracy_pct']}%")
            a2.metric("Decision Accuracy",          f"{acc['decision_accuracy_pct']}%")
            a3.metric("Directional Accuracy",       f"{acc['directional_accuracy_pct']}%")
            a4.metric("Records",                    str(acc["count"]))

            b1, b2, b3, b4 = st.columns(4)
            b1.metric("Return Accuracy",        f"{acc['return_accuracy_pct']}%")
            b2.metric("P&L Accuracy",           f"{acc['pl_accuracy_pct']}%")
            b3.metric("Capital Accuracy",       f"{acc['final_capital_accuracy_pct']}%")
            b4.metric("Win Rate Accuracy",      f"{acc['win_rate_accuracy_pct']}%")

            with st.expander("Error Breakdown"):
                st.json({
                    "avg_return_error":     acc["avg_return_error"],
                    "avg_pl_error":         acc["avg_pl_error"],
                    "avg_capital_error_pct": acc["avg_capital_error_pct"],
                    "avg_win_rate_error":   acc["avg_win_rate_error"],
                })
        else:
            st.info(f"Portfolio accuracy: {acc.get('count', 0)} records — run more portfolio backtests to build history.")
    except Exception as _acc_e:
        st.caption(f"Portfolio accuracy metrics unavailable: {_acc_e}")

    # ── Section 7: Portfolio Charts ───────────────────────────────────────────
    _phr()
    _psec("Section 7 · Portfolio Charts")

    try:
        chart_cols = st.columns(2)

        # Chart A: AI vs BT Final Capital by holding
        with chart_cols[0]:
            st.markdown("**Holding-Level: AI vs Backtest Final Capital**")
            hc_list2 = pf_cmp.get("holding_comparisons", []) if pf_cmp else []
            if hc_list2:
                chart_data = pd.DataFrame([
                    {
                        "Symbol":      hc["symbol"],
                        "AI Capital":  hc["ai_final_capital"],
                        "BT Capital":  hc["bt_final_capital"],
                    }
                    for hc in hc_list2
                ]).set_index("Symbol")
                st.bar_chart(chart_data, color=["#2563EB", "#16A34A"])
            else:
                st.caption("No holding comparison data yet.")

        # Chart B: Portfolio Allocation
        with chart_cols[1]:
            st.markdown("**Portfolio Allocation by Weight**")
            if holdings:
                alloc_data = pd.DataFrame([
                    {"Symbol": h["ticker"], "Weight %": h["weight_pct"]}
                    for h in holdings
                ]).set_index("Symbol")
                st.bar_chart(alloc_data, color="#6366F1")
    except Exception:
        st.caption("Charts unavailable.")
