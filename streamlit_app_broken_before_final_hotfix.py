"""
AI Financial Analyst System (Streamlit)

UI intent:
- Look like a credible product in <30 seconds
- Guided workflow + strong hierarchy
- Structured outputs (tabs) instead of walls of text
"""

import os
import sys
import re
import json
import math
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

# Add paths - main directory first, then subdirectories
sys.path.insert(0, os.path.dirname(__file__))  # Main directory first
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'tools'))
sys.path.insert(2, os.path.join(os.path.dirname(__file__), 'config'))
sys.path.insert(3, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
from stock_analysis_agent import StockAnalysisAgent
from portfolio_manager import PortfolioManager

load_dotenv()

# Page configuration — must be the first Streamlit call
st.set_page_config(
    page_title="AI Financial Analyst System",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Stripe-Inspired Design System ─────────────────────────────────────────────
# Palette: #0A2540 navy | #635BFF purple | #00875A success | #DF1B41 danger
st.markdown("""
<style>
/* ── Stripe-Inspired Design System ─────────────────────────────────────── */
/* Palette: navy #0A2540 | purple #635BFF | success #00875A | danger #DF1B41 */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }

/* ── Sidebar ──────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] { background: #0A2540 !important; border-right: 1px solid #0d2d4a; }
section[data-testid="stSidebar"] * { color: #c0d4e8 !important; }
section[data-testid="stSidebar"] label { color: #8ba9c4 !important; font-size: 0.78rem !important; }
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 { color: #e2e8f0 !important; }
section[data-testid="stSidebar"] p { color: #8ba9c4 !important; font-size: 0.8rem !important; }

/* ── Console page header ─────────────────────────────────────────────── */
.console-hdr { background:#0A2540; padding:0.85rem 1.5rem; border-radius:8px; display:flex; align-items:center; justify-content:space-between; margin-bottom:1.5rem; border:1px solid #1a3a55; }
.console-title { font-size:1.1rem; font-weight:700; color:#f1f5f9; }
.console-sub   { font-size:0.78rem; color:#8ba9c4; margin-top:0.12rem; }
.console-badge-wrap { display:flex; gap:0.45rem; flex-wrap:wrap; align-items:center; }
.badge { padding:0.18rem 0.55rem; border-radius:4px; font-size:0.65rem; font-weight:700; letter-spacing:0.05em; }
.badge-purple { background:#635BFF; color:white; }
.badge-ok   { background:rgba(0,135,90,0.18); color:#00875A; border:1px solid rgba(0,135,90,0.3); }
.badge-warn { background:rgba(245,158,11,0.15); color:#d97706; border:1px solid rgba(245,158,11,0.3); }

/* ── Decision board cards ────────────────────────────────────────────── */
.dc-wrap { display:grid; grid-template-columns:repeat(4,1fr); gap:0.8rem; margin:0.75rem 0 1.5rem; }
.dc-card { padding:1rem 1.2rem; border-radius:10px; border:1px solid; }
.dc-buy    { background:#F0FDF4; border-color:#059669; }
.dc-sell   { background:#FFF1F2; border-color:#F43F5E; }
.dc-hold   { background:#FFFBEB; border-color:#F59E0B; }
.dc-review { background:#F0F9FF; border-color:#0EA5E9; }
.dc-lbl { font-size:0.62rem; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; color:#425466; margin-bottom:0.3rem; }
.dc-val { font-size:2.1rem; font-weight:800; line-height:1.15; }
.dc-buy  .dc-val { color:#065F46; }
.dc-sell .dc-val { color:#9F1239; }
.dc-hold .dc-val { color:#92400E; }
.dc-review .dc-val { color:#075985; }
.dc-sub { font-size:0.75rem; color:#425466; margin-top:0.3rem; }
.dc-src { font-size:0.65rem; color:#94A3B8; margin-top:0.45rem; border-top:1px solid rgba(0,0,0,0.06); padding-top:0.35rem; }

/* ── Comparison table ────────────────────────────────────────────────── */
.cmp-tbl { width:100%; border-collapse:collapse; font-size:0.875rem; margin:0.75rem 0; }
.cmp-tbl th { background:#F6F9FC; color:#425466; padding:0.5rem 0.9rem; text-align:left; border-bottom:2px solid #E3E8EE; font-size:0.65rem; font-weight:700; letter-spacing:0.07em; text-transform:uppercase; }
.cmp-tbl td { padding:0.48rem 0.9rem; border-bottom:1px solid #E3E8EE; color:#0A2540; vertical-align:middle; }
.cmp-tbl tr:last-child td { border-bottom:none; }
.cmp-tbl tr:hover td { background:#F9FAFB; }
.cmp-match    { color:#059669; font-weight:700; }
.cmp-conflict { color:#DC2626; font-weight:700; }
.cmp-na       { color:#94A3B8; font-style:italic; }
.cmp-positive { color:#059669; }
.cmp-negative { color:#DC2626; }

/* ── Accuracy metric cards ───────────────────────────────────────────── */
.acc-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:0.7rem; margin:0.75rem 0; }
.acc-card { background:#F6F9FC; border:1px solid #E3E8EE; border-radius:8px; padding:0.9rem; text-align:center; }
.acc-lbl  { font-size:0.62rem; font-weight:700; color:#425466; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.25rem; }
.acc-val  { font-size:1.55rem; font-weight:800; color:#0A2540; }
.acc-sub  { font-size:0.7rem; color:#94A3B8; margin-top:0.15rem; }

/* ── Section heading ─────────────────────────────────────────────────── */
.sec-head { font-size:0.68rem; font-weight:700; color:#635BFF; text-transform:uppercase; letter-spacing:0.1em; border-left:3px solid #635BFF; padding-left:0.6rem; margin:1.6rem 0 0.8rem; }

/* ── Stripe-style status pills ───────────────────────────────────────── */
.status-row { display:flex; gap:0.6rem; flex-wrap:wrap; margin-top:0.75rem; }
.status-pill { display:inline-flex; align-items:center; gap:0.35rem; padding:0.22rem 0.7rem; border-radius:999px; font-size:0.72rem; font-weight:600; }
.status-dot  { width:5px; height:5px; border-radius:50%; background:currentColor; display:inline-block; }
.status-ok   { background:rgba(0,135,90,0.1);   color:#00875A; border:1px solid rgba(0,135,90,0.25); }
.status-warn { background:rgba(245,158,11,0.1);  color:#d97706; border:1px solid rgba(245,158,11,0.25); }
.status-err  { background:rgba(223,27,65,0.1);   color:#DF1B41; border:1px solid rgba(223,27,65,0.25); }

/* ── Metric card ─────────────────────────────────────────────────────── */
.af-metric { background:#F6F9FC; border:1px solid #E3E8EE; border-radius:8px; padding:0.85rem 1rem; text-align:center; }
.af-metric-label { font-size:0.62rem; font-weight:700; color:#425466; letter-spacing:0.07em; text-transform:uppercase; margin-bottom:0.25rem; }
.af-metric-value { font-size:1.35rem; font-weight:800; color:#0A2540; line-height:1.15; }
.af-metric-sub   { font-size:0.7rem; color:#94A3B8; margin-top:0.18rem; }

/* ── Score bar ───────────────────────────────────────────────────────── */
.score-bar-wrap  { margin:0.25rem 0 0.7rem; }
.score-bar-label { font-size:0.75rem; font-weight:600; color:#425466; display:flex; justify-content:space-between; margin-bottom:0.22rem; }
.score-bar-track { background:#E3E8EE; border-radius:999px; height:7px; overflow:hidden; }
.score-bar-fill  { height:100%; border-radius:999px; }
.score-high { background:linear-gradient(90deg,#059669,#34D399); }
.score-mid  { background:linear-gradient(90deg,#F59E0B,#FBbf24); }
.score-low  { background:linear-gradient(90deg,#DC2626,#F87171); }

/* ── Verdict cards ───────────────────────────────────────────────────── */
.verdict-card { border-radius:10px; padding:1.1rem 1.35rem; display:flex; flex-direction:column; gap:0.45rem; }
.verdict-buy  { background:#F0FDF4; border:1px solid #059669; }
.verdict-hold { background:#FFFBEB; border:1px solid #F59E0B; }
.verdict-sell { background:#FFF1F2; border:1px solid #DC2626; }
.verdict-label { font-size:0.62rem; font-weight:700; letter-spacing:0.12em; text-transform:uppercase; }
.verdict-buy  .verdict-label { color:#065F46; }
.verdict-hold .verdict-label { color:#92400E; }
.verdict-sell .verdict-label { color:#9F1239; }
.verdict-value { font-size:2.5rem; font-weight:800; line-height:1; }
.verdict-buy  .verdict-value { color:#059669; }
.verdict-hold .verdict-value { color:#F59E0B; }
.verdict-sell .verdict-value { color:#DC2626; }
.verdict-sub  { font-size:0.85rem; color:#425466; }

/* ── Interpretation boxes ────────────────────────────────────────────── */
.interp-box      { background:#F0FDF4; border-left:4px solid #059669; border-radius:0 8px 8px 0; padding:0.85rem 1rem; margin:0.6rem 0; }
.interp-box-warn { background:#FFFBEB; border-left:4px solid #F59E0B; border-radius:0 8px 8px 0; padding:0.85rem 1rem; margin:0.6rem 0; }
.interp-box-risk { background:#FFF1F2; border-left:4px solid #DC2626; border-radius:0 8px 8px 0; padding:0.85rem 1rem; margin:0.6rem 0; }
.interp-title { font-size:0.62rem; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.28rem; opacity:0.75; }
.interp-text  { font-size:0.875rem; color:#0A2540; line-height:1.5; }

/* ── Legacy KPI / report boxes ───────────────────────────────────────── */
.af-hero { background:#0A2540; border:1px solid #1a3a55; border-radius:10px; padding:1rem 1.5rem 0.85rem; margin-bottom:1.25rem; }
.af-hero-title { font-size:1.5rem; font-weight:800; color:#F1F5F9; letter-spacing:-0.02em; }
.af-hero-title span { color:#635BFF; }
.af-hero-sub  { font-size:0.85rem; color:#8BA9C4; margin-bottom:0.2rem; }
.af-section   { margin-top:1.5rem; margin-bottom:0.6rem; }
.af-section-title { font-size:0.62rem; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; color:#635BFF; margin-bottom:0.45rem; }
.af-section-heading { font-size:1.05rem; font-weight:700; color:#0A2540; border-left:3px solid #635BFF; padding-left:0.65rem; margin-bottom:0.8rem; }
.af-card { background:white; border:1px solid #E3E8EE; border-radius:10px; padding:1rem 1.25rem; margin-bottom:0.8rem; }
.report-box { border-radius:8px; border:1px solid #E3E8EE; padding:0.8rem 1rem; background:white; }
.kpi-label  { color:#425466; font-size:0.75rem; font-weight:600; margin-bottom:0.18rem; }
.kpi-value  { font-size:1.25rem; font-weight:800; line-height:1.2; color:#0A2540; }
.tiny-muted { color:#64748B; font-size:0.82rem; }
.pill { display:inline-block; padding:0.15rem 0.5rem; border-radius:999px; border:1px solid #E3E8EE; background:#F6F9FC; font-size:0.8rem; font-weight:600; margin-left:0.3rem; vertical-align:middle; }
.af-divider { border:none; border-top:1px solid #E3E8EE; margin:1.25rem 0; }
</style>
""", unsafe_allow_html=True)


def _get_api_status() -> dict:
    google_ok   = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
    rapidapi_ok = bool(os.getenv("RAPIDAPI_KEY")) and os.getenv("RAPIDAPI_KEY") != "mock-key-for-testing"
    tt_ok       = bool(os.getenv("TASTYTRADE_REFRESH_TOKEN") or os.getenv("TASTYTRADE_CLIENT_SECRET"))
    return {"google_ok": google_ok, "rapidapi_ok": rapidapi_ok, "tastytrade_ok": tt_ok}


def _status_badge(status: str | None) -> tuple[str, str]:
    if not status:
        return "•", "Unavailable"
    status_upper = str(status).upper()
    if status_upper == "SUCCESS":
        return "✅", "Online"
    if status_upper in {"ERROR", "FAILED", "FAIL"}:
        return "⚠️", "Temporarily unavailable"
    return "•", status_upper


def _first_percent(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"([0-9]{1,3}(?:\\.[0-9]+)?)\\s*%", text)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    if 0 <= val <= 100:
        return val
    return None


def _extract_section(report_text: str, header: str) -> str:
    """
    Extract a section starting at `header` (e.g., "PROBABILITY ANALYSIS:")
    and ending at the next all-caps heading line or end-of-text.
    """
    if not report_text:
        return ""
    start = report_text.find(header)
    if start < 0:
        return ""
    after = report_text[start + len(header) :]

    # Next header: line that looks like "SOME HEADING:" in ALL CAPS.
    m = re.search(r"\n[A-Z0-9][A-Z0-9 /_()-]{3,}:\n", after)
    if not m:
        return after.strip()
    return after[: m.start()].strip()


def render_hero():
    """Kept for backward compatibility — new pages use _console_page_header()."""
    pass


def render_text_report_tabs(report_text: str, *, filename_prefix: str, execution_steps: list | None = None):
    tab1, tab2, tab3, tab4 = st.tabs(["Summary", "Technical Analysis", "AI Reasoning", "Risk Analysis"])

    with tab1:
        prob_text = _extract_section(report_text, "PROBABILITY ANALYSIS:")
        confidence = _first_percent(prob_text) if prob_text else None

        left, right = st.columns([2, 1])
        with left:
            st.markdown("**Intelligence Snapshot**")
            tech_text = _extract_section(report_text, "TECHNICAL ANALYSIS SUMMARY:")
            tech_rec = None
            tech_sig = None
            if tech_text:
                m1 = re.search(r"Recommendation:\\s*(.+)", tech_text)
                m2 = re.search(r"Signal:\\s*(.+)", tech_text)
                tech_rec = m1.group(1).strip() if m1 else None
                tech_sig = m2.group(1).strip() if m2 else None

            colA, colB, colC, colD = st.columns(4)
            with colA:
                st.metric("Technical", tech_rec or "Unavailable")
            with colB:
                st.metric("Signal", tech_sig or "Unavailable")
            with colC:
                st.metric("AI Confidence", f"{confidence:.0f}%" if confidence is not None else "Unavailable")
            with colD:
                st.metric("Coverage", "Tools", "see pipeline monitor")

        with right:
            st.markdown("**AI Confidence Engine**")
            if confidence is None:
                st.caption("No explicit confidence percentage found in the report.")
            else:
                st.progress(min(max(confidence / 100.0, 0.0), 1.0))
                st.caption(f"{confidence:.0f}% confidence (extracted from report text)")

        st.markdown("**Report preview (top ~60 lines):**")
        preview = "\n".join((report_text or "").splitlines()[:60])
        st.code(preview, language="text")

    with tab2:
        tech = _extract_section(report_text, "TECHNICAL ANALYSIS SUMMARY:")
        if tech:
            st.markdown('<div class="report-box">', unsafe_allow_html=True)
            st.code(tech, language="text")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("No dedicated technical section found in this report.")

    with tab3:
        prob = _extract_section(report_text, "PROBABILITY ANALYSIS:")
        if prob:
            st.markdown('<div class="report-box">', unsafe_allow_html=True)
            st.code(prob, language="text")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("No probability/AI reasoning section found in this report.")

    with tab4:
        risk = _extract_section(report_text, "RISK ANALYSIS:")
        if risk:
            st.markdown('<div class="report-box">', unsafe_allow_html=True)
            st.code(risk, language="text")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Risk section not present in this report (more common in scenario reports).")

    st.download_button(
        "Download report (.txt)",
        data=report_text or "",
        file_name=f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        mime="text/plain",
        use_container_width=True,
    )

    if execution_steps:
        with st.expander("AI Pipeline Monitor"):
            for step in execution_steps:
                icon, label = _status_badge(step.get("status"))
                action = step.get("action") or "Step"
                duration = step.get("duration") or "-"
                st.write(f"{icon} **{action}** - {label} ({duration})")


def render_stock_intelligence(result: dict, *, filename_prefix: str):
    """
    Phase 1 UI: computed intelligence scores/signals are primary.
    Raw LLM report remains available only under a debug expander.
    """
    intelligence = (result or {}).get("intelligence") or {}
    scores = intelligence.get("scores") or {}

    verdict = intelligence.get("verdict") or {}
    verdict_value = (verdict.get("value") or "HOLD").upper()
    verdict_score = verdict.get("score")

    confidence = intelligence.get("confidence") or {}
    conf_score = confidence.get("score")
    conf_note = confidence.get("note") or "Computed from engine availability (data completeness proxy)."
    conf_penalties = confidence.get("penalties") or []
    conf_breakdown = confidence.get("breakdown") or {}

    risk = scores.get("risk") or {}
    risk_score = risk.get("score")
    risk_label = risk.get("signal") or "Unavailable"

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f"""
            <div class="report-box">
                <div class="kpi-label">Decision</div>
                <div class="kpi-value">{verdict_value}<span class="pill">{verdict_score if verdict_score is not None else "-"}/100</span></div>
                <div class="tiny-muted">Composite score (risk-adjusted)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="report-box">
                <div class="kpi-label">Confidence</div>
                <div class="kpi-value">{conf_score if conf_score is not None else "-"}/100</div>
                <div class="tiny-muted">{conf_note}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="report-box">
                <div class="kpi-label">Risk</div>
                <div class="kpi-value">{risk_label}<span class="pill">{risk_score if risk_score is not None else "-"}/100</span></div>
                <div class="tiny-muted">Higher score = higher risk</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.caption("Decision source of truth: deterministic scoring engine. LLM narrative is audit-only and cannot override BUY/HOLD/SELL.")

    st.markdown("### Intelligence Snapshot")

    engine_order = [
        ("fundamental", "Fundamental"),
        ("technical", "Technical"),
        ("valuation", "Valuation"),
        ("macro", "Macro"),
        ("sentiment", "Sentiment"),
        ("risk", "Risk"),
    ]

    rows = []
    for key, label in engine_order:
        eng = scores.get(key) or {}
        factors = eng.get("factors") or []
        top = []
        for f in factors[:2]:
            if isinstance(f, dict) and f.get("factor") is not None:
                impact = f.get("impact")
                if impact is None:
                    top.append(str(f.get("factor")))
                else:
                    try:
                        impact_i = int(impact)
                        top.append(f"{f.get('factor')} ({impact_i:+})")
                    except Exception:
                        top.append(str(f.get("factor")))
        missing_fields = eng.get("missing_fields") or []
        rows.append(
            {
                "Engine": label,
                "Score": eng.get("score", 0),
                "Signal": eng.get("signal", "Unavailable"),
                "Top factors": "; ".join(top) if top else "-",
                "Missing": len(missing_fields),
            }
        )

    st.dataframe(rows, use_container_width=True, hide_index=True)

    # Decision trace + factor attribution (compact, auditable)
    top_pos = intelligence.get("alpha_positive_drivers") or []
    top_neg = intelligence.get("alpha_negative_drivers") or []
    risk_contrib = intelligence.get("risk_contributors") or []
    decision_trace = intelligence.get("decision_trace") or {}
    source_rel = intelligence.get("source_reliability") or {}
    agents = intelligence.get("agents") or {}

    with st.expander("Decision Trace & Attribution"):
        left, right = st.columns([1, 1])
        with left:
            st.markdown("**Decision Trace**")
            base_score = decision_trace.get("base_score")
            comp_score = decision_trace.get("composite_score")
            risk_pen = decision_trace.get("risk_penalty_score")
            st.write(f"- Base score: {base_score if base_score is not None else '-'}")
            st.write(f"- Risk score: {risk_pen if risk_pen is not None else '-'}")
            st.write(f"- Composite: {comp_score if comp_score is not None else '-'}")

            comps = decision_trace.get("base_components") or []
            if comps:
                st.markdown("**Engine contributions (weighted)**")
                st.dataframe(
                    [
                        {
                            "Engine": c.get("engine"),
                            "Score": c.get("score"),
                            "Weight": c.get("weight"),
                            "Weighted": c.get("weighted"),
                        }
                        for c in comps
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

        with right:
            st.markdown("**Positive Alpha Drivers**")
            if top_pos:
                for item in top_pos[:6]:
                    st.write(f"- {item.get('engine')}: {item.get('factor')} ({item.get('impact'):+})")
            else:
                st.caption("No positive drivers available.")

            st.markdown("**Negative Drivers**")
            if top_neg:
                for item in top_neg[:6]:
                    st.write(f"- {item.get('engine')}: {item.get('factor')} ({item.get('impact'):+})")
            else:
                st.caption("No negative drivers available.")

            st.markdown("**Risk Contributors**")
            if risk_contrib:
                for item in risk_contrib[:6]:
                    st.write(f"- {item.get('factor')} ({item.get('impact'):+})")
            else:
                st.caption("No risk contributors available.")

        if conf_penalties:
            st.markdown("**Confidence penalties (missing engines)**")
            for p in conf_penalties[:12]:
                st.write(f"- {p.get('engine')}: -{p.get('penalty')} ({p.get('reason')})")

        if conf_breakdown:
            with st.expander("Confidence breakdown"):
                st.write(f"- Completeness score: {conf_breakdown.get('completeness_score', '-')}")
                st.write(f"- Agreement penalty: {conf_breakdown.get('agreement_penalty', '-')}")
                st.write(f"- Contradiction penalty: {conf_breakdown.get('contradiction_penalty', '-')}")
                st.write(f"- Risk regime penalty: {conf_breakdown.get('risk_regime_penalty', '-')}")
                cal = conf_breakdown.get("calibration") or {}
                if isinstance(cal, dict) and cal.get("available"):
                    st.write(f"- Calibration expected accuracy: {cal.get('expected_accuracy', '-')}/100")
                    st.caption(str(cal.get("note") or ""))
                else:
                    st.caption(str((cal or {}).get("note") or "Calibration unavailable (no evaluated history yet)."))

        if source_rel:
            st.markdown("**Source reliability (heuristic)**")
            st.dataframe(
                [{"Engine": k, "Reliability": v} for k, v in source_rel.items()],
                use_container_width=True,
                hide_index=True,
            )

    if agents:
        with st.expander("Agent Consensus"):
            def _agent_row(name: str, obj: dict) -> dict:
                if not isinstance(obj, dict):
                    return {"Agent": name, "Verdict": "-", "Confidence": "-", "Notes": "-"}
                return {
                    "Agent": name,
                    "Verdict": obj.get("verdict") or obj.get("risk_level") or obj.get("verdict") or "-",
                    "Confidence": obj.get("confidence", "-"),
                    "Notes": "; ".join((obj.get("thesis") or obj.get("flags") or obj.get("overrides") or [])[:3]) if isinstance((obj.get("thesis") or obj.get("flags") or obj.get("overrides") or []), list) else "-",
                }

            table = []
            for key in ["bull", "bear", "risk", "critic", "final"]:
                table.append(_agent_row(key, agents.get(key) or {}))
            st.dataframe(table, use_container_width=True, hide_index=True)

            # Detail panes
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Bull Agent**")
                st.write(agents.get("bull") or {})
                st.markdown("**Bear Agent**")
                st.write(agents.get("bear") or {})
            with c2:
                st.markdown("**Risk Agent**")
                st.write(agents.get("risk") or {})
                st.markdown("**Critic Agent**")
                st.write(agents.get("critic") or {})
                st.markdown("**Final Agent**")
                st.write(agents.get("final") or {})

    if (result or {}).get("execution_steps"):
        with st.expander("AI Pipeline Monitor"):
            for step in (result.get("execution_steps") or []):
                icon, label = _status_badge(step.get("status"))
                action = step.get("action") or "Step"
                duration = step.get("duration") or "-"
                st.write(f"{icon} **{action}** - {label} ({duration})")

    with st.expander("Factors & missing fields (per engine)"):
        for key, label in engine_order:
            eng = scores.get(key) or {}
            st.markdown(f"**{label}** - {eng.get('score', 0)}/100 ({eng.get('signal', 'Unavailable')})")
            missing_fields = eng.get("missing_fields") or []
            factors = eng.get("factors") or []
            if factors:
                st.write("Contributing factors:")
                for f in factors[:8]:
                    if isinstance(f, dict):
                        factor = f.get("factor")
                        impact = f.get("impact")
                        value = f.get("value")
                        st.write(f"- {factor}: impact={impact}, value={value}")
                    else:
                        st.write(f"- {f}")
            else:
                st.caption("No contributing factors available.")
            if missing_fields:
                st.write("Missing fields:")
                for m in missing_fields[:20]:
                    st.write(f"- {m}")
            else:
                st.caption("No missing fields detected for this engine.")
            st.divider()

    report_text = (result or {}).get("report") or ""
    with st.expander("Audit only: Raw LLM narrative (not a decision source)"):
        st.caption("Primary UI uses computed scores/signals. This narrative is not allowed to override deterministic decisions.")
        st.code(report_text, language="text")
        st.download_button(
            "Download report (.txt)",
            data=report_text or "",
            file_name=f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    # Visual intelligence layer (compact, institutional)
    with st.expander("Visual Intelligence"):
        try:
            import plotly.graph_objects as go

            f_sc = (scores.get("fundamental") or {}).get("score", 0)
            t_sc = (scores.get("technical") or {}).get("score", 0)
            v_sc = (scores.get("valuation") or {}).get("score", 0)
            m_sc = (scores.get("macro") or {}).get("score", 0)
            s_sc = (scores.get("sentiment") or {}).get("score", 0)
            r_sc = (scores.get("risk") or {}).get("score", 0)
            risk_good = 0 if not isinstance(r_sc, (int, float)) else max(0, min(100, 100 - int(r_sc)))

            categories = ["Fundamental", "Technical", "Valuation", "Macro", "Sentiment", "Risk (low=good)"]
            values = [f_sc, t_sc, v_sc, m_sc, s_sc, risk_good]
            fig = go.Figure()
            fig.add_trace(
                go.Scatterpolar(r=values + [values[0]], theta=categories + [categories[0]], fill="toself", name="Scores")
            )
            fig.update_layout(
                height=360,
                margin=dict(l=10, r=10, t=40, b=10),
                title="Score Radar",
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

            # Attribution bars (alpha drivers + risk contributors)
            bars = []
            for it in (intelligence.get("alpha_positive_drivers") or [])[:6]:
                bars.append({"label": f"{it.get('engine')}:{it.get('factor')}", "impact": int(it.get("impact", 0))})
            for it in (intelligence.get("alpha_negative_drivers") or [])[:6]:
                bars.append({"label": f"{it.get('engine')}:{it.get('factor')}", "impact": int(it.get("impact", 0))})
            for it in (intelligence.get("risk_contributors") or [])[:6]:
                # risk contributors shown as negative contribution to decision quality
                bars.append({"label": f"risk:{it.get('factor')}", "impact": -abs(int(it.get("impact", 0)))})
            if bars:
                bars = sorted(bars, key=lambda x: x["impact"])
                fig2 = go.Figure(
                    data=[
                        go.Bar(
                            x=[b["impact"] for b in bars],
                            y=[b["label"] for b in bars],
                            orientation="h",
                        )
                    ]
                )
                fig2.update_layout(
                    height=360,
                    margin=dict(l=10, r=10, t=40, b=10),
                    title="Attribution (impact)",
                    xaxis_title="Impact",
                    yaxis_title="",
                )
                st.plotly_chart(fig2, use_container_width=True)

            # Confidence gauge
            if isinstance(conf_score, (int, float)):
                fig3 = go.Figure(
                    go.Indicator(
                        mode="gauge+number",
                        value=float(conf_score),
                        title={"text": "Decision Confidence"},
                        gauge={"axis": {"range": [0, 100]}},
                    )
                )
                fig3.update_layout(height=260, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig3, use_container_width=True)

            # Bull vs Bear vs Hold inclination
            probs = intelligence.get("probabilities") or {}
            if probs:
                fig4 = go.Figure(
                    data=[
                        go.Bar(
                            x=["BUY", "HOLD", "SELL"],
                            y=[probs.get("buy", 0), probs.get("hold", 0), probs.get("sell", 0)],
                        )
                    ]
                )
                fig4.update_layout(height=260, margin=dict(l=10, r=10, t=40, b=10), title="Inclination (derived, not predictive)")
                st.plotly_chart(fig4, use_container_width=True)
                if probs.get("note"):
                    st.caption(str(probs.get("note")))

        except Exception as e:
            st.caption(f"Visuals unavailable: {e}")


def _extract_between(report_text: str, start_header: str, end_header: str) -> str:
    if not report_text:
        return ""
    start = report_text.find(start_header)
    if start < 0:
        return ""
    after = report_text[start + len(start_header) :]
    end = after.find(end_header)
    if end < 0:
        return after.strip()
    return after[:end].strip()


def render_portfolio_report_tabs(
    report_text: str,
    *,
    filename_prefix: str,
    execution_log: list | None = None,
    conversion_log: list | None = None,
):
    tab1, tab2, tab3, tab4 = st.tabs(["Summary", "Technical Analysis", "AI Reasoning", "Risk Analysis"])

    with tab1:
        # Quick metrics if present
        total_value = None
        holdings_n = None
        m_val = re.search(r"- Total Value:\\s*\\$([0-9,]+\\.?[0-9]*)", report_text or "")
        if m_val:
            total_value = m_val.group(1)
        m_n = re.search(r"- Number of Holdings:\\s*(\\d+)", report_text or "")
        if m_n:
            holdings_n = m_n.group(1)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Total Value", f"${total_value}" if total_value else "-")
        with c2:
            st.metric("Holdings", holdings_n or "-")
        with c3:
            st.metric("Analysis", "Portfolio", "Agentic")

        st.markdown("**Report preview (top ~70 lines):**")
        preview = "\n".join((report_text or "").splitlines()[:70])
        st.code(preview, language="text")

        if conversion_log:
            try:
                labels = []
                values = []
                for log in conversion_log:
                    if isinstance(log, dict) and "ticker" in log and "amount" in log:
                        labels.append(str(log["ticker"]))
                        values.append(float(log["amount"]))
                if labels and values:
                    import plotly.graph_objects as go

                    fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.55)])
                    fig.update_layout(
                        height=320,
                        margin=dict(l=10, r=10, t=30, b=10),
                        title="Portfolio Allocation (by invested amount)",
                        legend=dict(orientation="h"),
                    )
                    st.plotly_chart(fig, use_container_width=True)
            except Exception:
                # Charts are optional; don't break the report rendering if Plotly fails.
                pass

    with tab2:
        # "Position breakdown" is the closest to a technical section here
        pos = _extract_between(report_text or "", "POSITION BREAKDOWN:", "\n" + "=" * 80)
        if pos:
            st.markdown('<div class="report-box">', unsafe_allow_html=True)
            st.code(pos, language="text")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("No position breakdown section found in this report.")

    with tab3:
        recs = _extract_between(report_text or "", "PORTFOLIO RECOMMENDATIONS:", "INDIVIDUAL STOCK REPORTS:")
        if recs:
            st.markdown('<div class="report-box">', unsafe_allow_html=True)
            st.code(recs, language="text")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("No portfolio recommendations section found in this report.")

    with tab4:
        recs = _extract_between(report_text or "", "PORTFOLIO RECOMMENDATIONS:", "INDIVIDUAL STOCK REPORTS:")
        risk = _extract_section(recs or "", "RISK ANALYSIS:")
        if risk:
            st.markdown('<div class="report-box">', unsafe_allow_html=True)
            st.code(risk, language="text")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Risk section not found inside recommendations (depends on model output).")

    st.download_button(
        "Download report (.txt)",
        data=report_text or "",
        file_name=f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        mime="text/plain",
        use_container_width=True,
    )

    if execution_log:
        with st.expander("AI Pipeline Monitor"):
            for step in execution_log:
                icon, label = _status_badge(step.get("status"))
                agent = step.get("agent") or "Engine"
                action = step.get("action") or "Step"
                duration = step.get("duration") or "-"
                st.write(f"{icon} **{agent}** - {action} - {label} ({duration})")

    if conversion_log:
        with st.expander("Conversion Log"):
            for log in conversion_log:
                if isinstance(log, dict) and "name" in log and "ticker" in log:
                    st.write(f"{log['name']} → {log['ticker']}: ${log['amount']:,.2f} invested")
                    if "current_price" in log and "calculated_shares" in log:
                        st.write(f"  Current Price: ${log['current_price']:.2f}, Shares: {log['calculated_shares']:.2f}")
                elif isinstance(log, dict) and "warning" in log:
                    st.warning(str(log["warning"]))
                else:
                    st.write(str(log))


def render_portfolio_compact(
    report_text: str,
    *,
    filename_prefix: str,
    execution_log: list | None = None,
    conversion_log: list | None = None,
):
    """
    Phase 1 UI: keep portfolio output compact in the main screen.
    Raw LLM report is available only under a debug expander.
    """
    total_value = None
    holdings_n = None
    m_val = re.search(r"- Total Value:\\s*\\$([0-9,]+\\.?[0-9]*)", report_text or "")
    if m_val:
        total_value = m_val.group(1)
    m_n = re.search(r"- Number of Holdings:\\s*(\\d+)", report_text or "")
    if m_n:
        holdings_n = m_n.group(1)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total Value", f"${total_value}" if total_value else "-")
    with c2:
        st.metric("Holdings", holdings_n or "-")
    with c3:
        st.metric("Module", "Portfolio", "analysis")

    # Portfolio intelligence (deterministic, based on allocation log)
    alloc = []
    if conversion_log:
        for log in conversion_log:
            if isinstance(log, dict) and "ticker" in log and "amount" in log:
                try:
                    alloc.append({"ticker": str(log["ticker"]).upper(), "amount": float(log["amount"])})
                except Exception:
                    continue

    if alloc:
        total_amt = sum(x["amount"] for x in alloc if x["amount"] > 0)
        weights = []
        if total_amt > 0:
            weights = [{"ticker": x["ticker"], "weight": x["amount"] / total_amt, "amount": x["amount"]} for x in alloc]

        if weights:
            top = sorted(weights, key=lambda x: x["weight"], reverse=True)[0]
            hhi = sum(x["weight"] ** 2 for x in weights)
            diversification = max(0, min(100, int(round((1.0 - hhi) * 140))))  # heuristic
            concentration = int(round(top["weight"] * 100))

            cA, cB, cC = st.columns(3)
            with cA:
                st.metric("Diversification Score", f"{diversification}/100")
            with cB:
                st.metric("Top Holding", top["ticker"], f"{concentration}%")
            with cC:
                st.metric("Concentration (HHI)", f"{hhi:.3f}")

            st.markdown("**Allocation table**")
            st.dataframe(
                [{"Ticker": x["ticker"], "Weight %": round(x["weight"] * 100, 2), "Amount": round(x["amount"], 2)} for x in sorted(weights, key=lambda x: x["weight"], reverse=True)],
                use_container_width=True,
                hide_index=True,
            )

            # Optional correlation + stress test (explicit opt-in due to extra API calls)
            with st.expander("Portfolio Risk Lab (optional)"):
                st.caption("Computes correlations using 1Y price history. May trigger extra API calls; keep holdings small.")
                do_corr = st.checkbox("Compute correlation matrix (last ~90 points)", value=False, key=f"corr_{filename_prefix}")
                if do_corr:
                    try:
                        import numpy as np
                        import pandas as pd
                        from stock_historical_data import get_year_historical_data

                        series = {}
                        for x in sorted(weights, key=lambda z: z["weight"], reverse=True)[:12]:
                            hr = get_year_historical_data(x["ticker"])
                            hist_payload = hr.get("data", {}).get("data", {})
                            history = hist_payload.get("history", []) or []
                            closes = []
                            for pt in history[-120:]:
                                if isinstance(pt, dict):
                                    c = pt.get("close", pt.get("c"))
                                    try:
                                        closes.append(float(c))
                                    except Exception:
                                        pass
                            if len(closes) >= 90:
                                rets = np.diff(np.array(closes)) / np.array(closes[:-1])
                                series[x["ticker"]] = rets[-90:]

                        if len(series) >= 2:
                            df = pd.DataFrame(series)
                            corr = df.corr()
                            st.markdown("**Correlation matrix (returns)**")
                            st.dataframe(corr.round(2), use_container_width=True)

                            # Simple stress test: market down X% and correlate weights with avg corr
                            shock = st.slider("Market shock (%)", min_value=1, max_value=25, value=8)
                            avg_corr = float(corr.mean().mean())
                            est_dd = -abs(shock) / 100.0 * (0.8 + 0.4 * min(1.0, max(0.0, avg_corr)))
                            st.metric("Estimated drawdown (rough)", f"{est_dd*100:.1f}%")
                        else:
                            st.info("Not enough history series to compute correlation (need >=2 tickers with >=90 points).")
                    except Exception as e:
                        st.error(f"Correlation/stress computation failed: {e}")

    if conversion_log:
        try:
            labels = []
            values = []
            for log in conversion_log:
                if isinstance(log, dict) and "ticker" in log and "amount" in log:
                    labels.append(str(log["ticker"]))
                    values.append(float(log["amount"]))
            if labels and values:
                import plotly.graph_objects as go

                fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.55)])
                fig.update_layout(
                    height=320,
                    margin=dict(l=10, r=10, t=30, b=10),
                    title="Portfolio Allocation (by invested amount)",
                    legend=dict(orientation="h"),
                )
                st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass

    if execution_log:
        with st.expander("AI Pipeline Monitor"):
            for step in execution_log:
                icon, label = _status_badge(step.get("status"))
                agent = step.get("agent") or "Engine"
                action = step.get("action") or "Step"
                duration = step.get("duration") or "-"
                st.write(f"{icon} **{agent}** - {action} - {label} ({duration})")

    if conversion_log:
        with st.expander("Conversion Log"):
            for log in conversion_log:
                if isinstance(log, dict) and "name" in log and "ticker" in log:
                    st.write(f"{log['name']} -> {log['ticker']}: ${log['amount']:,.2f} invested")
                    if "current_price" in log and "calculated_shares" in log:
                        st.write(f"  Current Price: ${log['current_price']:.2f}, Shares: {log['calculated_shares']:.2f}")
                elif isinstance(log, dict) and "warning" in log:
                    st.warning(str(log["warning"]))
                else:
                    st.write(str(log))

    with st.expander("Debug: raw portfolio report (audit only)"):
        st.code(report_text or "", language="text")
        st.download_button(
            "Download report (.txt)",
            data=report_text or "",
            file_name=f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            use_container_width=True,
        )


def initialize_agent():
    """Initialize the stock analysis agent and portfolio manager"""
    if 'agent' not in st.session_state:
        # Get or create user ID
        if 'user_id' not in st.session_state:
            st.session_state.user_id = ""

        with st.spinner("Initializing Stock Analysis Agent..."):
            st.session_state.agent = StockAnalysisAgent(user_id=st.session_state.user_id)
            st.session_state.analysis_history = []

    if 'portfolio_manager' not in st.session_state:
        with st.spinner("Initializing Portfolio Manager..."):
            st.session_state.portfolio_manager = PortfolioManager(user_id=st.session_state.user_id)
            st.session_state.portfolio_history = []


def stock_analysis_interface():
    """Main stock analysis interface"""
    st.subheader("Stock Research")
    st.caption("Start with one ticker to control cost.")
    
    # Stock symbol input
    col1, col2 = st.columns([3, 1])
    with col1:
        stock_symbol = st.text_input(
            "Enter Stock Symbol",
            placeholder="Enter ticker symbol",
            key="stock_symbol_input"
        ).upper()
    
    with col2:
        analyze_button = st.button("Analyze Stock", type="primary", use_container_width=True)
    
    if analyze_button and stock_symbol:
        try:
            from portfolio_parser import parse_portfolio_input

            parsed_portfolio = parse_portfolio_input(stock_symbol)
            parsed_holdings = parsed_portfolio.get("holdings", []) if parsed_portfolio.get("status") == "SUCCESS" else []
            has_portfolio_syntax = len(parsed_holdings) > 1 or any(ch in stock_symbol for ch in "%:=,\n")
            if has_portfolio_syntax and len(parsed_holdings) > 1:
                st.warning("Portfolio-style input detected. Routing to portfolio intelligence instead of treating it as one ticker.")
                st.dataframe(parsed_holdings, use_container_width=True, hide_index=True)
                try:
                    from evaluation_engine import build_portfolio_intelligence, load_dataset

                    dataset = load_dataset()
                    portfolio_intel = build_portfolio_intelligence(parsed_holdings, dataset=dataset)
                    render_portfolio_intelligence_summary(portfolio_intel)
                except Exception as e:
                    st.error(f"Portfolio intelligence route failed: {e}")
                return
        except Exception:
            pass

        # Perform analysis
        with st.spinner("AI Agents Analyzing Market Data..."):
            result = st.session_state.agent.analyze_stock(stock_symbol)
        
        # Display results
        if result.get('status') == 'SUCCESS':
            st.success(f"Analysis completed for `{stock_symbol}`")
            render_stock_intelligence(result, filename_prefix=f"{stock_symbol}_analysis")

            with st.expander("Charts (optional, may trigger extra API calls)"):
                st.caption("Enable only if you’re OK with additional market-data API usage.")
                fetch_chart = st.checkbox("Fetch 1Y price history for chart", value=False, key="fetch_stock_chart")
                if fetch_chart:
                    try:
                        from stock_historical_data import get_year_historical_data
                        hist = get_year_historical_data(stock_symbol)
                        if hist.get("status") != "SUCCESS":
                            st.error(f"Chart data fetch failed: {hist.get('message', 'Unknown error')}")
                        else:
                            payload = hist.get("data", {}).get("data", {})
                            history = payload.get("history", []) or []
                            closes = []
                            xs = []
                            for idx, pt in enumerate(history):
                                if not isinstance(pt, dict):
                                    continue
                                close = pt.get("close", pt.get("c"))
                                t = pt.get("time", pt.get("t", idx))
                                if close is None:
                                    continue
                                xs.append(t)
                                closes.append(close)

                            if not closes:
                                st.warning("No usable historical points found for chart.")
                            else:
                                import plotly.graph_objects as go

                                fig = go.Figure()
                                fig.add_trace(go.Scatter(x=xs, y=closes, mode="lines", name=stock_symbol))
                                fig.update_layout(
                                    height=320,
                                    margin=dict(l=10, r=10, t=30, b=10),
                                    title=f"{stock_symbol} - 1Y Price Trend (raw timeline)",
                                    xaxis_title="Time",
                                    yaxis_title="Close",
                                )
                                st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.error(f"Chart rendering failed: {e}")
            
            # Add to history
            st.session_state.analysis_history.append({
                "symbol": stock_symbol,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "result": result
            })
            
        else:
            st.error(f"Analysis failed: {result.get('message', 'Unknown error')}")
    
    # Display analysis history
    if st.session_state.analysis_history:
        st.divider()
        st.subheader("Recent Stock Runs")
        
        for i, analysis in enumerate(reversed(st.session_state.analysis_history[-5:]), 1):
            with st.expander(f"{i}. {analysis['symbol']} - {analysis['timestamp']}"):
                st.write(f"Status: {analysis['result'].get('status')}")
                if analysis['result'].get('status') == 'SUCCESS':
                    intel = (analysis["result"] or {}).get("intelligence") or {}
                    scores = intel.get("scores") or {}
                    verdict = intel.get("verdict") or {}
                    confidence = intel.get("confidence") or {}
                    risk = scores.get("risk") or {}

                    st.write(
                        f"Decision: **{(verdict.get('value') or 'HOLD').upper()}** ({verdict.get('score', '-')}/100) | "
                        f"Confidence: **{confidence.get('score', '-')}/100** | "
                        f"Risk: **{risk.get('signal', 'Unavailable')}** ({risk.get('score', '-')}/100)"
                    )

                    engine_rows = []
                    for key, label in [
                        ("fundamental", "Fundamental"),
                        ("technical", "Technical"),
                        ("valuation", "Valuation"),
                        ("macro", "Macro"),
                        ("sentiment", "Sentiment"),
                        ("risk", "Risk"),
                    ]:
                        eng = scores.get(key) or {}
                        engine_rows.append(
                            {
                                "Engine": label,
                                "Score": eng.get("score", 0),
                                "Signal": eng.get("signal", "Unavailable"),
                                "Missing": len(eng.get("missing_fields") or []),
                            }
                        )
                    st.dataframe(engine_rows, use_container_width=True, hide_index=True)

                    with st.expander("Debug: raw report (audit only)"):
                        st.code((analysis["result"] or {}).get("report") or "", language="text")


def parse_portfolio_text(text_input: str) -> list:
    """Parse free-text portfolio input into structured holdings.

    Args:
        text_input: Free text portfolio (e.g., "Apple - 22000, Microsoft - 477700")

    Returns:
        list: List of holdings with name and amount
    """
    holdings = []
    lines = text_input.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try different separators
        separators = ['-', '—', '–', ':', ',', '|', ' ']

        for sep in separators:
            if sep in line:
                parts = line.split(sep)
                if len(parts) >= 2:
                    # Try to identify which part is the name and which is the amount
                    # The name is usually first, amount is usually last
                    name_part = parts[0].strip()
                    amount_part = parts[-1].strip()

                    # Skip if name is empty or looks like a number
                    if not name_part or name_part.replace('.', '').isdigit():
                        continue

                    # Extract amount from second part
                    amount_str = amount_part

                    # Handle 'k' suffix (multiply by 1000)
                    # But be smart about it - if number before 'k' is > 1000, it might already be the full amount
                    if 'k' in amount_str.lower():
                        # Remove 'k'
                        amount_before_k = amount_str.lower().replace('k', '')
                        try:
                            base_amount = float(amount_before_k)
                            # If base amount is very large (>10000), don't multiply by 1000
                            # This handles cases like "26496k" where user probably meant 26496, not 26M
                            if base_amount > 10000:
                                amount = base_amount
                            else:
                                amount = base_amount * 1000
                        except ValueError:
                            continue
                    else:
                        # Remove non-numeric characters (except decimal point)
                        amount_str = ''.join(c for c in amount_str if c.isdigit() or c == '.')
                        try:
                            amount = float(amount_str)
                        except ValueError:
                            continue

                    if amount > 0:
                        holdings.append({"name": name_part, "amount": amount})
                    break  # Successfully parsed, move to next line

    return holdings


def portfolio_analysis_interface():
    """Portfolio analysis interface"""
    st.subheader("Portfolio Analysis")
    st.caption("Ajay demo mode: portfolio recommendation, confidence, risk, diversification, and allocation guidance only.")

    weighted_raw = st.text_area(
        "Portfolio Weights",
        value="",
        placeholder="Enter portfolio weights: AAPL 40%, MSFT 30%",
        height=110,
    )
    as_of_raw = st.text_input("As-Of Date", value="", placeholder="YYYY-MM-DD")
    if st.button("RUN PORTFOLIO INTELLIGENCE", type="primary", use_container_width=True):
        if not weighted_raw.strip():
            st.error("Enter portfolio weights before running portfolio intelligence.")
            return
        try:
            from evaluation_engine import build_portfolio_intelligence, load_dataset
            from portfolio_parser import parse_portfolio_input

            parsed = parse_portfolio_input(weighted_raw)
            if parsed.get("status") != "SUCCESS":
                st.error("; ".join(parsed.get("issues") or ["Portfolio input could not be parsed."]))
                return
            as_of_date = datetime.strptime(as_of_raw, "%Y-%m-%d").date() if as_of_raw else None
            result = build_portfolio_intelligence(parsed.get("holdings", []), as_of_date=as_of_date, dataset=load_dataset())
            st.session_state["last_clean_portfolio_intelligence"] = result
        except Exception as exc:
            st.error(f"Portfolio intelligence failed: {exc}")
            return

    if st.session_state.get("last_clean_portfolio_intelligence"):
        render_portfolio_intelligence_summary(st.session_state["last_clean_portfolio_intelligence"])
    else:
        st.info("No portfolio intelligence run yet. Enter weights and run analysis.")
    return
    st.caption("Start small (3–5 holdings) to control cost. This module runs multiple stock analyses under the hood.")

    # Input format selection
    input_format = st.radio(
        "Input Format",
        ["Paste as Text (easiest)", "Weighted Tickers (dataset intelligence)", "Dollar Amounts (table)", "Shares & Avg Cost"],
        help="Choose how you want to enter your holdings"
    )

    # Portfolio input
    st.subheader("Enter Your Holdings")
    holdings = []
    holdings_shares = []
    weighted_holdings = []

    if input_format == "Paste as Text (easiest)":
        st.info("Paste one holding per line using company/ticker and amount.")

        text_input = st.text_area(
            "Paste your portfolio here",
            height=200,
            placeholder="Enter holdings: Company/Ticker - Amount",
            help="One stock per line: Name - Amount"
        )

        holdings = []
        if text_input:
            try:
                holdings = parse_portfolio_text(text_input)
                if holdings:
                    st.success(f"Parsed {len(holdings)} holdings")
                    st.write("**Parsed Holdings (you can edit below if needed):**")

                    # Allow user to edit parsed holdings
                    edited_holdings = []
                    for i, h in enumerate(holdings):
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            edited_name = st.text_input(f"Stock {i+1} Name", value=h.get('name', ''), key=f"edit_name_{i}")
                        with col2:
                            edited_amount = st.number_input(f"Amount ${i+1}", value=h.get('amount', 0.0), key=f"edit_amount_{i}")
                        if edited_name and edited_amount > 0:
                            edited_holdings.append({"name": edited_name, "amount": float(edited_amount)})
                        else:
                            # Keep original if editing failed, but ensure structure is correct
                            if isinstance(h, dict) and 'name' in h and 'amount' in h:
                                edited_holdings.append({"name": h['name'], "amount": float(h['amount'])})
                            else:
                                # Skip this holding if structure is invalid
                                st.warning(f"Skipping invalid holding at position {i+1}")

                    holdings = edited_holdings
                else:
                    st.warning("Could not parse holdings. Check the company/ticker and amount format.")
            except Exception as e:
                st.error(f"Error parsing portfolio: {str(e)}")

    elif input_format == "Weighted Tickers (dataset intelligence)":
        st.info("Enter weighted tickers using text, JSON, comma-separated, or newline-separated formats.")
        weighted_raw = st.text_area(
            "Weighted portfolio",
            value="",
            placeholder="Enter portfolio weights: AAPL 40%, MSFT 30%",
            height=140,
        )
        try:
            from portfolio_parser import parse_portfolio_input

            parsed = parse_portfolio_input(weighted_raw)
            if parsed.get("status") == "SUCCESS":
                weighted_holdings = parsed.get("holdings", [])
                st.success(f"Parsed {len(weighted_holdings)} weighted holdings")
                st.dataframe(weighted_holdings, use_container_width=True, hide_index=True)
                for issue in parsed.get("issues", []):
                    st.caption(f"Parser note: {issue}")
            else:
                st.error("; ".join(parsed.get("issues") or ["Could not parse weighted portfolio."]))
        except Exception as e:
            st.error(f"Portfolio parser unavailable: {e}")

    elif input_format == "Dollar Amounts (table)":
        st.info("Enter company name or ticker and the dollar amount invested")

        # Dynamic input for holdings
        holdings = []
        num_holdings = st.number_input("Number of holdings", min_value=1, max_value=50, value=1)

        for i in range(num_holdings):
            col1, col2 = st.columns([2, 1])
            with col1:
                name = st.text_input(f"Stock {i+1} Name/Ticker", placeholder="Enter company or ticker", key=f"name_{i}")
            with col2:
                amount = st.number_input(f"Amount ${i+1}", min_value=0.0, value=0.0, key=f"amount_{i}")

            if name and amount > 0:
                holdings.append({"name": name, "amount": amount})

    else:  # Shares & Avg Cost
        st.info("Enter company name, number of shares, and average cost per share")

        num_holdings = st.number_input("Number of holdings", min_value=1, max_value=50, value=1)

        for i in range(num_holdings):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                symbol = st.text_input(f"Stock {i+1} Symbol", placeholder="Enter ticker symbol", key=f"symbol_{i}")
            with col2:
                shares = st.number_input(f"Shares {i+1}", min_value=0.0, value=0.0, key=f"shares_{i}")
            with col3:
                avg_cost = st.number_input(f"Avg Cost ${i+1}", min_value=0.0, value=0.0, key=f"cost_{i}")

            if symbol and shares > 0 and avg_cost > 0:
                holdings_shares.append({
                    "symbol": symbol,
                    "shares": shares,
                    "avg_cost": avg_cost
                })

    # Cash input
    cash = st.number_input("Cash in Portfolio ($)", min_value=0.0, value=0.0)

    # Analysis type selection
    st.divider()
    st.subheader("Analysis Type")
    analysis_type = st.selectbox(
        "Choose analysis depth",
        ["1-Month Prediction (faster, ~16s per stock)", "Investment Scenario (~40s per stock)", "Comprehensive (~45s per stock)"],
        help="Faster options for quick analysis, comprehensive for deep analysis"
    )

    # Map selection to actual type
    if analysis_type == "1-Month Prediction (faster, ~16s per stock)":
        actual_type = "one_month"
    elif analysis_type == "Investment Scenario (~40s per stock)":
        actual_type = "scenario"
    else:
        actual_type = "comprehensive"

    # Analyze button
    analyze_button = st.button("Analyze Portfolio", type="primary", use_container_width=True)

    if analyze_button:
        if input_format == "Weighted Tickers (dataset intelligence)" and weighted_holdings:
            with st.spinner("Computing portfolio intelligence from historical dataset..."):
                try:
                    from evaluation_engine import build_portfolio_intelligence, load_dataset

                    dataset = load_dataset()
                    output = build_portfolio_intelligence(weighted_holdings, dataset=dataset)
                    render_portfolio_intelligence_summary(output)
                    st.session_state.portfolio_history.append({
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "result": {"status": output.get("status"), "final_report": "Dataset portfolio intelligence run"},
                        "holdings_count": len(weighted_holdings)
                    })
                except Exception as e:
                    st.error(f"Portfolio intelligence failed: {e}")

        elif input_format == "Paste as Text (easiest)" and holdings:
            # Estimate time
            est_time = len(holdings) * (16 if actual_type == "one_month" else 40 if actual_type == "scenario" else 45)
            st.info(f"⏱️ Estimated time: ~{est_time} seconds ({est_time/60:.1f} minutes) for {len(holdings)} stocks")

            with st.spinner("AI Agents Analyzing Portfolio..."):
                try:
                    result = st.session_state.portfolio_manager.analyze_portfolio_from_dollar_amounts(
                        holdings,
                        analysis_type=actual_type
                    )

                    if result.get('status') == 'SUCCESS':
                        st.success("Portfolio analysis completed")

                        report_text = result.get("final_report", "") or ""
                        render_portfolio_compact(
                            report_text,
                            filename_prefix="portfolio_analysis",
                            execution_log=result.get("execution_log", []),
                            conversion_log=result.get("conversion_log", []),
                        )

                        # Add to history
                        st.session_state.portfolio_history.append({
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "result": result,
                            "holdings_count": len(holdings)
                        })

                    else:
                        st.error(f"Analysis failed: {result.get('message', 'Unknown error')}")

                except Exception as e:
                    st.error(f"Error during analysis: {str(e)}")

        elif input_format == "Dollar Amounts (table)" and holdings:
            # Estimate time
            est_time = len(holdings) * (16 if actual_type == "one_month" else 40 if actual_type == "scenario" else 45)
            st.info(f"⏱️ Estimated time: ~{est_time} seconds ({est_time/60:.1f} minutes) for {len(holdings)} stocks")

            with st.spinner("AI Agents Analyzing Portfolio..."):
                try:
                    result = st.session_state.portfolio_manager.analyze_portfolio_from_dollar_amounts(
                        holdings,
                        analysis_type=actual_type
                    )

                    if result.get('status') == 'SUCCESS':
                        st.success("Portfolio analysis completed")

                        report_text = result.get("final_report", "") or ""
                        render_portfolio_compact(
                            report_text,
                            filename_prefix="portfolio_analysis",
                            execution_log=result.get("execution_log", []),
                            conversion_log=result.get("conversion_log", []),
                        )

                        # Add to history
                        st.session_state.portfolio_history.append({
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "result": result,
                            "holdings_count": len(holdings)
                        })

                    else:
                        st.error(f"Analysis failed: {result.get('message', 'Unknown error')}")

                except Exception as e:
                    st.error(f"Error during analysis: {str(e)}")

        elif input_format == "Shares & Avg Cost" and holdings_shares:
            portfolio_data = {
                "holdings": holdings_shares,
                "cash": cash
            }

            # Estimate time
            est_time = len(holdings_shares) * (16 if actual_type == "one_month" else 40 if actual_type == "scenario" else 45)
            st.info(f"⏱️ Estimated time: ~{est_time} seconds ({est_time/60:.1f} minutes) for {len(holdings_shares)} stocks")

            with st.spinner("AI Agents Analyzing Portfolio..."):
                try:
                    result = st.session_state.portfolio_manager.analyze_portfolio_complete(
                        portfolio_data,
                        analysis_type=actual_type
                    )

                    if result.get('status') == 'SUCCESS':
                        st.success("Portfolio analysis completed")

                        report_text = result.get("final_report", "") or ""
                        render_portfolio_compact(
                            report_text,
                            filename_prefix="portfolio_analysis",
                            execution_log=result.get("execution_log", []),
                            conversion_log=result.get("conversion_log", []),
                        )

                        # Add to history
                        st.session_state.portfolio_history.append({
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "result": result,
                            "holdings_count": len(holdings_shares)
                        })

                    else:
                        st.error(f"Analysis failed: {result.get('message', 'Unknown error')}")

                except Exception as e:
                    st.error(f"Error during analysis: {str(e)}")
        else:
            st.warning("Please enter at least one holding")

    # Display portfolio history
    if st.session_state.portfolio_history:
        st.divider()
        st.subheader("Recent Portfolio Runs")

        for i, analysis in enumerate(reversed(st.session_state.portfolio_history[-3:]), 1):
            with st.expander(f"{i}. {analysis['holdings_count']} holdings - {analysis['timestamp']}"):
                st.write(f"Status: {analysis['result'].get('status')}")
                if analysis['result'].get('status') == 'SUCCESS':
                    st.text(analysis['result'].get('final_report', '')[:500] + "...")





def _pct(value, digits: int = 1) -> str:
    try:
        if value is None:
            return "UNAVAILABLE"
        return f"{float(value) * 100:.{digits}f}%"
    except Exception:
        return "UNAVAILABLE"


def _num(value, digits: int = 2) -> str:
    try:
        if value is None:
            return "UNAVAILABLE"
        return f"{float(value):.{digits}f}"
    except Exception:
        return "UNAVAILABLE"


def _developer_mode_enabled() -> bool:
    return os.getenv("DEVELOPER_MODE", os.getenv("XELTRIX_DEVELOPER_MODE", "0")).strip() == "1"


def _metric_suffix(value, suffix: str = "/100") -> str:
    if value in (None, "", "UNAVAILABLE", "-"):
        return "UNAVAILABLE"
    return f"{value}{suffix}"


def _grade_from_score(score) -> str:
    try:
        value = float(score)
    except Exception:
        return "UNAVAILABLE"
    if value >= 85:
        return "A"
    if value >= 70:
        return "B"
    if value >= 55:
        return "C"
    if value >= 40:
        return "D"
    return "F"


def _display_metric(label: str, value, *, percent: bool = False, digits: int = 2):
    formatted = _pct(value, digits) if percent else _num(value, digits) if isinstance(value, (int, float)) else (value if value not in (None, "") else "UNAVAILABLE")
    st.metric(label, formatted)


def _portfolio_strengths_risks_actions(output: dict) -> tuple[list[str], list[str], list[str]]:
    portfolio = output.get("portfolio", {}) or {}
    strengths: list[str] = []
    risks: list[str] = []
    actions: list[str] = []

    expected_return = portfolio.get("expected_return")
    max_drawdown = portfolio.get("max_drawdown")
    sharpe = portfolio.get("sharpe_ratio")
    diversification = portfolio.get("diversification_score")
    risk_score = portfolio.get("risk_score")
    concentration = portfolio.get("concentration")

    if isinstance(expected_return, (int, float)) and expected_return > 0:
        strengths.append("Positive expected return profile.")
    if isinstance(sharpe, (int, float)) and sharpe >= 1:
        strengths.append("Acceptable risk-adjusted return.")
    if isinstance(diversification, (int, float)) and diversification >= 65:
        strengths.append("Diversification is supportive.")
    if not strengths:
        strengths.append("No strong portfolio strength is proven by current evidence.")

    if isinstance(concentration, (int, float)) and concentration >= 0.40:
        risks.append("Single-name concentration is elevated.")
    if isinstance(risk_score, (int, float)) and risk_score >= 70:
        risks.append("Portfolio risk score is elevated.")
    if isinstance(max_drawdown, (int, float)) and max_drawdown >= 0.15:
        risks.append("Expected drawdown requires monitoring.")
    if not risks:
        risks.append("No major portfolio risk flag triggered.")

    allocator_actions = ((output.get("allocator") or {}).get("suggestions") or [])[:3]
    actions.extend(str(item) for item in allocator_actions if item)
    if not actions:
        actions.append("Maintain allocation discipline and rerun after new evidence.")
    return strengths[:3], risks[:3], actions[:3]


def _render_bullets(title: str, items: list[str]) -> None:
    st.markdown(f"**{title}**")
    for item in items:
        st.write(f"- {item}")


def _backtest_verdict(output: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    status = "PASS"
    metrics = output.get("metrics", {}) or {}
    decision_metrics = output.get("decision_metrics", {}) or {}
    recommendation_accuracy = output.get("recommendation_accuracy") or {}
    consistency = output.get("consistency_audit") or {}
    hard_failure = output.get("hard_failure_audit") or {}
    beta_audit = output.get("beta_alpha_audit") or {}

    if hard_failure.get("status") == "REVIEW":
        status = "REVIEW"
        reasons.extend(hard_failure.get("failures") or hard_failure.get("issues") or [])
    if consistency.get("status") == "REVIEW":
        status = "REVIEW"
        reasons.extend(consistency.get("issues") or [])
    if beta_audit.get("status") not in {"PASSED", "PROXY_USED"}:
        status = "REVIEW"
        reasons.extend(beta_audit.get("issues") or ["Benchmark audit requires review."])
    if recommendation_accuracy.get("status") != "SUCCESS":
        status = "REVIEW"
        reasons.append("External ground truth is not configured, so recommendation accuracy is unavailable.")
    win_rate = decision_metrics.get("win_rate")
    if isinstance(win_rate, (int, float)) and win_rate < 0.45:
        status = "REVIEW"
        reasons.append("Decision win rate is below institutional target.")
    if metrics.get("alpha") is not None and isinstance(metrics.get("alpha"), (int, float)) and float(metrics.get("alpha")) > 0:
        reasons.append("Benchmark outperformance is positive.")
    if not reasons:
        reasons.append("Core backtest metrics, benchmark linkage, and consistency checks passed.")
    if hard_failure.get("status") == "FAIL":
        status = "FAIL"
    return status, list(dict.fromkeys(str(reason) for reason in reasons if reason))[:5]


def _render_audit_card(title: str, status: str, reasons: list[str]) -> None:
    st.markdown(f"**{title}: {status or 'UNAVAILABLE'}**")
    for reason in reasons[:3]:
        st.write(f"- {reason}")


def render_portfolio_intelligence_summary(output: dict):
    portfolio = output.get("portfolio", {}) or {}
    st.markdown("## 3. Portfolio Intelligence")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Recommendation", portfolio.get("decision", "UNAVAILABLE"))
    with c2:
        st.metric("Confidence", _metric_suffix(portfolio.get("confidence")))
    with c3:
        st.metric("Portfolio Score", _metric_suffix(portfolio.get("composite_score")))
    with c4:
        st.metric("Diversification", _metric_suffix(portfolio.get("diversification_score")))
    with c5:
        st.metric("Quality Grade", _grade_from_score(portfolio.get("composite_score")))
    c6, c7, c8, c9, c10 = st.columns(5)
    with c6:
        st.metric("Risk", _metric_suffix(portfolio.get("risk_score")))
    with c7:
        st.metric("Expected Return", _pct(portfolio.get("expected_return"), 2))
    with c8:
        st.metric("Expected Drawdown", _pct(portfolio.get("max_drawdown"), 2))
    with c9:
        reward = portfolio.get("expected_return")
        risk = portfolio.get("max_drawdown")
        ratio = (float(reward) / abs(float(risk))) if isinstance(reward, (int, float)) and isinstance(risk, (int, float)) and risk else None
        st.metric("Risk/Reward", _num(ratio))
    with c10:
        allocation_hint = (((output.get("allocator") or {}).get("suggestions") or ["UNAVAILABLE"])[0])
        st.metric("Suggested Allocation", allocation_hint)

    strengths, risks, actions = _portfolio_strengths_risks_actions(output)
    s_col, r_col, a_col = st.columns(3)
    with s_col:
        _render_bullets("Top Strengths", strengths)
    with r_col:
        _render_bullets("Top Risks", risks)
    with a_col:
        _render_bullets("Recommended Actions", actions)
    return

    try:
        import pandas as pd
        import plotly.express as px

        stocks = output.get("stocks") or []
        if stocks:
            st.markdown("**Stock-Level Intelligence**")
            st.dataframe(
                pd.DataFrame(stocks)[["ticker", "weight", "sector", "decision", "composite", "confidence", "risk", "regime"]],
                use_container_width=True,
                hide_index=True,
            )

        left, right = st.columns(2)
        with left:
            sector_rows = output.get("sector_exposure") or []
            if sector_rows:
                fig = px.bar(sector_rows, x="sector", y="weight", title="Sector Exposure")
                fig.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10), yaxis_tickformat=".0%")
                st.plotly_chart(fig, use_container_width=True)
        with right:
            stress = output.get("stress_tests") or []
            if stress:
                fig = px.bar(stress, x="scenario", y="estimated_impact", title="Stress Test Impact")
                fig.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10), yaxis_tickformat=".0%")
                st.plotly_chart(fig, use_container_width=True)

        corr = output.get("correlation_matrix") or []
        if corr:
            st.markdown("**Correlation Matrix**")
            st.dataframe(corr, use_container_width=True, hide_index=True)

        industry_rows = output.get("industry_exposure") or []
        if industry_rows:
            with st.expander("Industry Exposure"):
                st.dataframe(industry_rows, use_container_width=True, hide_index=True)

        allocator = output.get("allocator") or {}
        suggestions = allocator.get("suggestions") or []
        if suggestions:
            st.markdown("**Portfolio Allocator Agent**")
            for suggestion in suggestions:
                st.write(f"- {suggestion}")

        if output.get("errors"):
            with st.expander("Portfolio Failure Transparency"):
                st.dataframe(output.get("errors"), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Could not render portfolio intelligence: {e}")


def render_institutional_backtest(output: dict):
    metrics = output.get("metrics", {}) or {}
    decision_metrics = output.get("decision_metrics", {}) or {}
    portfolio_intel = output.get("portfolio_intelligence") or {}
    portfolio = portfolio_intel.get("portfolio", {}) or {}
    recommendation_accuracy = output.get("recommendation_accuracy") or {}
    performance = output.get("performance_audit") or {}
    beta_audit = output.get("beta_alpha_audit") or metrics.get("beta_alpha_audit") or {}
    consistency = output.get("consistency_audit") or {}
    accuracy_value = recommendation_accuracy.get("accuracy")
    reliability_basis = accuracy_value if isinstance(accuracy_value, (int, float)) else decision_metrics.get("win_rate")
    verdict, verdict_reasons = _backtest_verdict(output)

    st.markdown("## 1. Institutional Backtesting")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Backtest Verdict", verdict)
    with c2:
        st.metric("Final Portfolio Value", _num(metrics.get("final_value")))
    with c3:
        st.metric("Total Return", _pct(metrics.get("total_return"), 2))
    with c4:
        st.metric("Runtime", f"{performance.get('optimized_runtime_seconds', 'UNAVAILABLE')}s")

    b1, b2, b3, b4, b5, b6 = st.columns(6)
    with b1:
        st.metric("CAGR", _pct(metrics.get("cagr"), 2))
    with b2:
        st.metric("Sharpe", _num(metrics.get("sharpe_ratio")))
    with b3:
        st.metric("Sortino", _num(metrics.get("sortino_ratio")))
    with b4:
        st.metric("Max Drawdown", _pct(metrics.get("max_drawdown"), 2))
    with b5:
        st.metric("Win Rate", _pct(decision_metrics.get("win_rate"), 2))
    with b6:
        st.metric("Trade Count", len(output.get("trade_log") or []))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Alpha", _pct(metrics.get("alpha"), 2))
    with c2:
        st.metric("Beta", _num(metrics.get("beta")))
    with c3:
        st.metric("Information Ratio", _num(metrics.get("information_ratio")))
    with c4:
        st.metric("Benchmark Outperformance", _pct(metrics.get("alpha"), 2))

    audit_1, audit_2, audit_3, audit_4 = st.columns(4)
    with audit_1:
        _render_audit_card("Backtest Verdict", verdict, verdict_reasons)
    with audit_2:
        benchmark_status = ((output.get("config") or {}).get("benchmark_resolution") or {}).get("status") or beta_audit.get("status")
        benchmark_reason = ((output.get("config") or {}).get("benchmark_resolution") or {}).get("issues") or beta_audit.get("issues") or ["Benchmark linked successfully."]
        _render_audit_card("Benchmark Audit", benchmark_status, benchmark_reason)
    with audit_3:
        decision_reasons = [
            f"{decision_metrics.get('evaluated_decisions', decision_metrics.get('total_decisions', 0))} decisions evaluated.",
            f"Win rate: {_pct(decision_metrics.get('win_rate'), 2)}.",
        ]
        _render_audit_card("Decision Audit", "PASSED" if decision_metrics.get("total_decisions", 0) else "UNAVAILABLE", decision_reasons)
    with audit_4:
        _render_audit_card("Consistency Audit", consistency.get("status", "PASSED"), consistency.get("issues") or ["No material contradiction surfaced."])

    st.markdown("## 2. Recommendation Accuracy")
    if recommendation_accuracy.get("status") != "SUCCESS":
        st.warning("Status: UNAVAILABLE — Reason: External Ground Truth Not Configured.")
    else:
        a1, a2, a3, a4, a5, a6 = st.columns(6)
        coverage = recommendation_accuracy.get("coverage")
        if coverage is None:
            total_predictions = recommendation_accuracy.get("total_predictions") or 0
            evaluated_predictions = recommendation_accuracy.get("evaluated_predictions") or 0
            coverage = evaluated_predictions / total_predictions if total_predictions else None
        with a1:
            st.metric("Accuracy", _pct(recommendation_accuracy.get("accuracy"), 2))
        with a2:
            st.metric("Precision", _pct(recommendation_accuracy.get("precision"), 2))
        with a3:
            st.metric("Recall", _pct(recommendation_accuracy.get("recall"), 2))
        with a4:
            st.metric("F1 Score", _pct(recommendation_accuracy.get("f1"), 2))
        with a5:
            st.metric("Coverage", _pct(coverage, 2))
        with a6:
            st.metric("Labels", recommendation_accuracy.get("evaluated_predictions", 0))
        version_comparison = recommendation_accuracy.get("version_comparison") or {}
        v1, v2, v3, v4 = st.columns(4)
        with v1:
            st.metric("Current Agent Accuracy", _pct(version_comparison.get("current_agent_accuracy"), 2))
        with v2:
            st.metric("Previous Agent Accuracy", _pct(version_comparison.get("previous_agent_accuracy"), 2))
        with v3:
            st.metric("Improvement", _pct(version_comparison.get("accuracy_delta"), 2))
        with v4:
            st.metric("Improved?", version_comparison.get("improved", "UNAVAILABLE"))

    portfolio_intel = output.get("portfolio_intelligence") or {}
    if portfolio_intel:
        render_portfolio_intelligence_summary(portfolio_intel)
    return

    readiness = output.get("institutional_readiness") or {}
    if readiness and developer_mode:
        st.metric("Institutional Readiness", f"{readiness.get('score', '-')}/100", "audited result")
        with st.expander("Institutional Readiness Breakdown"):
            st.dataframe([readiness.get("components", {})], use_container_width=True, hide_index=True)

    try:
        import pandas as pd
        import plotly.express as px

        pipeline = output.get("pipeline") or []
        if pipeline:
            with st.expander("Execution Pipeline", expanded=True):
                st.dataframe(pipeline, use_container_width=True, hide_index=True)

        performance_audit = output.get("performance_audit") or {}
        if performance_audit:
            st.markdown("**Performance Audit Report**")
            perf_summary = {
                "optimized_runtime_seconds": performance_audit.get("optimized_runtime_seconds"),
                "previous_runtime_seconds": performance_audit.get("previous_runtime_seconds"),
                "decisions_per_second": performance_audit.get("decisions_per_second"),
                "equity_points": performance_audit.get("equity_points"),
                "decisions": performance_audit.get("decisions"),
                "complexity_notes": performance_audit.get("complexity_notes"),
            }
            st.dataframe(pd.DataFrame([perf_summary]), use_container_width=True, hide_index=True)
            timings = pd.DataFrame(performance_audit.get("stage_timings") or [])
            if not timings.empty:
                st.dataframe(timings, use_container_width=True, hide_index=True)
            with st.expander("Bottlenecks Removed"):
                for item in performance_audit.get("bottlenecks_removed") or []:
                    st.write(f"- {item}")

        equity = pd.DataFrame(output.get("equity_curve") or [])
        if not equity.empty:
            equity["date"] = pd.to_datetime(equity["date"])
            for col in ["portfolio_value", "benchmark_value", "daily_return"]:
                if col in equity.columns:
                    equity[col] = pd.to_numeric(equity[col], errors="coerce")
            try:
                curve_cols = [col for col in ["portfolio_value", "benchmark_value"] if col in equity.columns and equity[col].notna().any()]
                curve_df = equity[["date"] + curve_cols].melt("date", var_name="series", value_name="value").dropna(subset=["value"])
                if curve_df.empty:
                    st.warning("Chart diagnostics: equity curve has no numeric portfolio/benchmark values.")
                else:
                    fig = px.line(curve_df, x="date", y="value", color="series", title="Portfolio Value vs Benchmark")
                    fig.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10))
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as chart_error:
                st.warning(f"Chart diagnostics: equity curve render failed — {chart_error}")

            equity["peak"] = equity["portfolio_value"].cummax()
            equity["drawdown"] = (equity["peak"] - equity["portfolio_value"]) / equity["peak"]
            try:
                fig_dd = px.area(equity.dropna(subset=["drawdown"]), x="date", y="drawdown", title="Drawdown")
                fig_dd.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10), yaxis_tickformat=".0%")
                st.plotly_chart(fig_dd, use_container_width=True)
            except Exception as chart_error:
                st.warning(f"Chart diagnostics: drawdown render failed — {chart_error}")

            if not developer_mode:
                recommendation_accuracy = output.get("recommendation_accuracy") or {}
                st.markdown("### Recommendation Accuracy")
                acc_cols = st.columns(7)
                with acc_cols[0]:
                    st.metric("Total Predictions", recommendation_accuracy.get("total_predictions", len(output.get("decision_log") or [])))
                with acc_cols[1]:
                    st.metric("Evaluated", recommendation_accuracy.get("evaluated_predictions", recommendation_accuracy.get("historical_recommendations_evaluated", 0)))
                with acc_cols[2]:
                    st.metric("Correct", recommendation_accuracy.get("correct_recommendations", 0))
                with acc_cols[3]:
                    st.metric("Accuracy", _pct(recommendation_accuracy.get("accuracy"), 2))
                with acc_cols[4]:
                    st.metric("BUY", _pct(recommendation_accuracy.get("buy_accuracy"), 2))
                with acc_cols[5]:
                    st.metric("HOLD", _pct(recommendation_accuracy.get("hold_accuracy"), 2))
                with acc_cols[6]:
                    st.metric("SELL", _pct(recommendation_accuracy.get("sell_accuracy"), 2))
                pr_cols = st.columns(3)
                with pr_cols[0]:
                    st.metric("Precision", _pct(recommendation_accuracy.get("precision"), 2))
                with pr_cols[1]:
                    st.metric("Recall", _pct(recommendation_accuracy.get("recall"), 2))
                with pr_cols[2]:
                    st.metric("F1", _pct(recommendation_accuracy.get("f1"), 2))
                if recommendation_accuracy.get("status") != "SUCCESS":
                    st.warning("Recommendation Accuracy: UNAVAILABLE - External ground truth is not configured.")
                else:
                    class_rows = recommendation_accuracy.get("per_class_metrics") or []
                    if class_rows:
                        st.dataframe(class_rows, use_container_width=True, hide_index=True)
                    confusion = recommendation_accuracy.get("confusion_matrix") or []
                    if confusion:
                        with st.expander("Confusion Matrix"):
                            st.dataframe(confusion, use_container_width=True, hide_index=True)

                st.markdown("### Strategy Comparison")
                strategy_comparison = output.get("strategy_comparison") or {}
                if strategy_comparison.get("status") == "SUCCESS":
                    rows = strategy_comparison.get("summary") or []
                    if rows:
                        visible = ["strategy", "status", "cagr", "sharpe", "max_drawdown", "win_rate"]
                        strategy_df = pd.DataFrame(rows)
                        st.dataframe(strategy_df[[c for c in visible if c in strategy_df.columns]], use_container_width=True, hide_index=True)
                    competition = strategy_comparison.get("competition") or {}
                    champion = (competition.get("champion_strategy") or {}).get("strategy")
                    if champion:
                        st.success(f"Winning Strategy: {champion}")
                else:
                    st.info("Run a backtest to compare Agentic Strategy against Buy & Hold, Momentum, Technical, Mean Reversion, Factor, and Hybrid strategies.")

                st.markdown("### Feature Evaluation")
                feature_evaluation = output.get("feature_evaluation") or {}
                feature_rows = feature_evaluation.get("rows") or []
                if feature_rows:
                    st.dataframe(feature_rows, use_container_width=True, hide_index=True)
                if feature_evaluation.get("status") != "SUCCESS":
                    st.info("Feature accuracy comparison requires external ground truth. No synthetic feature improvement is shown.")

                portfolio_intel = output.get("portfolio_intelligence") or {}
                if portfolio_intel:
                    render_portfolio_intelligence_summary(portfolio_intel)
                return

            equity["rolling_volatility"] = equity["daily_return"].rolling(21, min_periods=5).std() * (252 ** 0.5)
            try:
                fig_vol = px.line(equity.dropna(subset=["rolling_volatility"]), x="date", y="rolling_volatility", title="Rolling Volatility")
                fig_vol.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10), yaxis_tickformat=".0%")
                st.plotly_chart(fig_vol, use_container_width=True)
            except Exception as chart_error:
                st.warning(f"Chart diagnostics: rolling volatility render failed — {chart_error}")

        audit = output.get("win_rate_audit") or {}
        if audit:
            st.markdown("**Win Rate Audit**")
            st.dataframe(pd.DataFrame([audit]), use_container_width=True, hide_index=True)

        beta_audit = output.get("beta_alpha_audit") or metrics.get("beta_alpha_audit") or {}
        if beta_audit:
            st.markdown("**Beta / Alpha Audit**")
            beta_cols = [
                "benchmark_observations",
                "portfolio_observations",
                "covariance",
                "benchmark_variance",
                "computed_beta",
                "computed_alpha",
                "status",
                "issues",
            ]
            st.dataframe(pd.DataFrame([{k: beta_audit.get(k) for k in beta_cols}]), use_container_width=True, hide_index=True)
            with st.expander("Beta / Alpha Formulas"):
                st.write(beta_audit.get("beta_formula"))
                st.write(beta_audit.get("alpha_formula"))

        consistency = output.get("consistency_audit") or {}
        if consistency:
            st.markdown("**Consistency Audit**")
            st.dataframe(pd.DataFrame([consistency]), use_container_width=True, hide_index=True)

        hard_failure = output.get("hard_failure_audit") or {}
        if hard_failure:
            st.markdown("**Hard Failure Conditions**")
            st.dataframe(pd.DataFrame([hard_failure]), use_container_width=True, hide_index=True)

        metric_value = output.get("metric_decision_value_audit") or []
        if metric_value:
            with st.expander("Metric Decision-Value Audit"):
                st.dataframe(metric_value, use_container_width=True, hide_index=True)

        decisions = pd.DataFrame(output.get("decision_log") or [])
        if not decisions.empty:
            left, right = st.columns(2)
            with left:
                dist = decisions["decision"].value_counts().reset_index()
                dist.columns = ["decision", "count"]
                fig_dist = px.bar(dist, x="decision", y="count", title="Decision Distribution")
                fig_dist.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig_dist, use_container_width=True)
            with right:
                regime_perf = decision_metrics.get("regime_performance") or {}
                if regime_perf:
                    regime_df = pd.DataFrame([{"regime": k, **v} for k, v in regime_perf.items()])
                    fig_regime = px.bar(regime_df, x="regime", y="win_rate", title="Regime-Segmented Accuracy")
                    fig_regime.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10), yaxis_tickformat=".0%")
                    st.plotly_chart(fig_regime, use_container_width=True)

            calibration = pd.DataFrame(decision_metrics.get("calibration") or [])
            if not calibration.empty:
                if "accuracy" in calibration.columns and "bucket" in calibration.columns:
                    calibration["expected_accuracy"] = calibration["bucket"].astype(str).str.split("-").apply(
                        lambda parts: ((float(parts[0]) + float(parts[-1])) / 2.0) / 100.0 if len(parts) >= 2 else None
                    )
                    calibration["calibration_gap"] = calibration["expected_accuracy"] - pd.to_numeric(calibration["accuracy"], errors="coerce")
                st.markdown("**Calibration Validation**")
                cc1, cc2, cc3, cc4 = st.columns(4)
                with cc1:
                    st.metric("Brier Score", _num(decision_metrics.get("brier_score"), 4))
                with cc2:
                    st.metric("ECE", _num(decision_metrics.get("expected_calibration_error"), 4))
                with cc3:
                    st.metric("Overconfidence", _num(decision_metrics.get("overconfidence"), 4))
                with cc4:
                    st.metric("Underconfidence", _num(decision_metrics.get("underconfidence"), 4))
                st.dataframe(calibration, use_container_width=True, hide_index=True)
                chart_df = calibration.dropna(subset=["accuracy"]) if "accuracy" in calibration.columns else calibration
                if not chart_df.empty:
                    try:
                        plot_cols = ["accuracy"] + (["expected_accuracy"] if "expected_accuracy" in chart_df.columns else [])
                        cal_plot = chart_df[["bucket"] + plot_cols].melt("bucket", var_name="series", value_name="value").dropna(subset=["value"])
                        fig_cal = px.line(cal_plot, x="bucket", y="value", color="series", markers=True, title="Confidence Reliability Diagram")
                        fig_cal.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10), yaxis_tickformat=".0%")
                        st.plotly_chart(fig_cal, use_container_width=True)
                    except Exception as chart_error:
                        st.warning(f"Chart diagnostics: calibration render failed — {chart_error}")

            validation = pd.DataFrame(output.get("decision_validation") or [])
            st.markdown("**Decision Validation Report**")
            if not validation.empty:
                visible_validation = [
                    "date",
                    "ticker",
                    "decision",
                    "engine_decision",
                    "confidence",
                    "price_at_decision",
                    "return_7d",
                    "return_30d",
                    "return_60d",
                    "return_90d",
                    "return_180d",
                    "return_365d",
                    "expected_return",
                    "actual_return",
                    "prediction_error",
                    "direction_accuracy",
                    "max_gain_30d",
                    "max_loss_30d",
                    "risk_adjusted_outcome_30d",
                    "outcome",
                    "correct",
                    "top_positive_contributors",
                    "top_negative_contributors",
                    "top_risk_contributors",
                ]
                st.dataframe(validation[[c for c in visible_validation if c in validation.columns]], use_container_width=True, hide_index=True)
                with st.expander("Decision Attribution Detail"):
                    attribution_cols = ["date", "ticker", "decision", "decision_attribution"]
                    st.dataframe(validation[[c for c in attribution_cols if c in validation.columns]], use_container_width=True, hide_index=True)
            else:
                st.warning("Decision validation report unavailable for this run.")

            prediction_quality = output.get("prediction_quality_report") or {}
            if prediction_quality:
                st.markdown("**Prediction Accuracy Report**")
                st.dataframe(pd.DataFrame([prediction_quality]), use_container_width=True, hide_index=True)

            agent_scoreboard = output.get("agent_scoreboard") or {}
            if agent_scoreboard:
                st.markdown("**Builder / Critic / Judge Scoreboard**")
                st.dataframe(pd.DataFrame([agent_scoreboard.get("summary") or {}]), use_container_width=True, hide_index=True)
                agent_rows = pd.DataFrame(agent_scoreboard.get("rows") or [])
                if not agent_rows.empty:
                    with st.expander("Agent Evaluation Rows"):
                        st.dataframe(agent_rows, use_container_width=True, hide_index=True)

            recommendation_accuracy = output.get("recommendation_accuracy") or {}
            if recommendation_accuracy:
                st.markdown("**Recommendation Accuracy vs External Ground Truth**")
                acc_cols = st.columns(5)
                with acc_cols[0]:
                    st.metric("Ground Truth", recommendation_accuracy.get("ground_truth_source", recommendation_accuracy.get("status", "UNAVAILABLE")))
                with acc_cols[1]:
                    st.metric("Evaluated", recommendation_accuracy.get("historical_recommendations_evaluated", 0))
                with acc_cols[2]:
                    st.metric("Correct", recommendation_accuracy.get("correct_recommendations", 0))
                with acc_cols[3]:
                    st.metric("Incorrect", recommendation_accuracy.get("incorrect_recommendations", 0))
                with acc_cols[4]:
                    st.metric("Accuracy", _pct(recommendation_accuracy.get("accuracy"), 2))
                if recommendation_accuracy.get("status") == "UNAVAILABLE":
                    st.warning(recommendation_accuracy.get("message", "External recommendation ground truth unavailable."))
                    with st.expander("Ground Truth Source Research"):
                        st.dataframe(recommendation_accuracy.get("source_research") or [], use_container_width=True, hide_index=True)
                        config = recommendation_accuracy.get("configuration") or {}
                        if config:
                            st.dataframe(pd.DataFrame([config]), use_container_width=True, hide_index=True)
                else:
                    accuracy_rows = pd.DataFrame(recommendation_accuracy.get("evaluated_rows") or [])
                    if not accuracy_rows.empty:
                        st.dataframe(accuracy_rows.head(300), use_container_width=True, hide_index=True)
                    for label, key in [
                        ("Ticker Accuracy", "ticker_accuracy"),
                        ("Monthly Accuracy", "rolling_monthly_accuracy"),
                        ("Regime Accuracy", "regime_accuracy"),
                    ]:
                        rows = recommendation_accuracy.get(key) or []
                        if rows:
                            with st.expander(label):
                                st.dataframe(rows, use_container_width=True, hide_index=True)

            with st.expander("Raw Decision Log"):
                visible_cols = ["as_of_date", "ticker", "decision", "confidence", "target_weight", "future_return", "outcome", "regime"]
                st.dataframe(decisions[[c for c in visible_cols if c in decisions.columns]], use_container_width=True, hide_index=True)

        trades = pd.DataFrame(output.get("trade_log") or [])
        if not trades.empty:
            with st.expander("Trade Log"):
                st.dataframe(trades, use_container_width=True, hide_index=True)

        lifecycle = pd.DataFrame(output.get("trade_lifecycle") or [])
        if not lifecycle.empty:
            st.markdown("**Trade Validation Report**")
            lifecycle_cols = [
                "entry_date",
                "exit_date",
                "ticker",
                "entry_price",
                "exit_price",
                "position_size",
                "gross_exposure",
                "net_exposure",
                "transaction_cost",
                "slippage",
                "pnl",
                "return_pct",
                "holding_period_days",
                "outcome",
            ]
            st.dataframe(lifecycle[[c for c in lifecycle_cols if c in lifecycle.columns]], use_container_width=True, hide_index=True)

        portfolio_intel = output.get("portfolio_intelligence") or {}
        if portfolio_intel:
            with st.expander("Terminal Portfolio Intelligence Snapshot"):
                render_portfolio_intelligence_summary(portfolio_intel)

        with st.expander("Backtest Configuration"):
            st.dataframe(pd.DataFrame([config]), use_container_width=True, hide_index=True)
        report = output.get("institutional_report") or {}
        if report:
            with st.expander("Institutional Report"):
                sections = [
                    ("Executive Summary", "executive_summary"),
                    ("Performance Summary", "unified_evaluation_object"),
                    ("Risk Summary", "risk_analysis"),
                    ("Benchmark Comparison", "benchmark_comparison"),
                    ("Calibration Analysis", "calibration_analysis"),
                    ("Decision Analysis", "decision_summary"),
                    ("Trade Analysis", "trade_summary"),
                    ("Learning Summary", "learning_summary"),
                    ("Data Quality / Leakage", "data_quality_analysis"),
                    ("Consistency Audit", "consistency_audit"),
                    ("Hard Failure Conditions", "hard_failure_audit"),
                    ("Performance Audit", "performance_audit"),
                    ("Metric Decision-Value Audit", "metric_decision_value_audit"),
                    ("Institutional Readiness", "institutional_readiness"),
                ]
                for title, key in sections:
                    payload = report.get(key)
                    if payload:
                        st.markdown(f"**{title}**")
                        if isinstance(payload, dict):
                            st.dataframe(pd.DataFrame([payload]), use_container_width=True, hide_index=True)
                        else:
                            st.write(payload)
                if report.get("weaknesses"):
                    st.markdown("**Weaknesses**")
                    for item in report.get("weaknesses", []):
                        st.write(f"- {item}")
                if report.get("limitations"):
                    st.markdown("**Limitations**")
                    for item in report.get("limitations", []):
                        st.write(f"- {item}")
                if report.get("recommendations"):
                    st.markdown("**Recommendations**")
                    for item in report.get("recommendations", []):
                        st.write(f"- {item}")
        data_quality = output.get("data_quality_audit") or {}
        if data_quality:
            with st.expander("Data Quality / Leakage Audit"):
                flat_quality = {k: v for k, v in data_quality.items() if not isinstance(v, (dict, list))}
                if flat_quality:
                    st.dataframe(pd.DataFrame([flat_quality]), use_container_width=True, hide_index=True)
                for key in ["benchmark_resolution", "dataset_audit"]:
                    payload = data_quality.get(key)
                    if payload:
                        st.markdown(f"**{key.replace('_', ' ').title()}**")
                        st.dataframe(pd.DataFrame([payload]), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Could not render institutional backtest: {e}")


def institutional_backtesting_interface():
    st.subheader("Institutional Backtesting")
    st.caption("Accuracy-first backtesting: recommendation, trust, benchmark edge, and portfolio intelligence only.")

    try:
        from evaluation_engine import load_dataset, run_institutional_backtest
        from portfolio_parser import parse_portfolio_input

        dataset = load_dataset()
        min_date = dataset["Date"].min().date()
        max_date = dataset["Date"].max().date()
    except Exception as e:
        st.error(f"Institutional backtesting unavailable: {e}")
        return

    st.markdown("#### Backtest Configuration Panel")
    portfolio_raw = st.text_area(
        "Ticker(s) / Portfolio Weights",
        value="",
        placeholder="Enter portfolio weights: AAPL 40%, MSFT 30%",
        height=90,
        help="Supports weighted text, comma/newline formats, and JSON.",
    )
    parsed = parse_portfolio_input(portfolio_raw)
    if portfolio_raw and parsed.get("status") == "SUCCESS":
        st.success(f"Parsed {len(parsed.get('holdings', []))} holding(s).")
        for issue in parsed.get("issues", []):
            st.caption(f"Parser note: {issue}")
    elif portfolio_raw:
        st.warning("; ".join(parsed.get("issues") or ["Portfolio input not parsed."]))
    else:
        st.info("No backtest executed. Awaiting portfolio configuration.")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        start_date_raw = st.text_input("Start Date", value="", placeholder="YYYY-MM-DD", key="inst_start")
    with c2:
        end_date_raw = st.text_input("End Date", value="", placeholder="YYYY-MM-DD", key="inst_end")
    with c3:
        initial_capital_raw = st.text_input("Initial Capital", value="", placeholder="Enter starting capital")
    with c4:
        horizon = st.selectbox("Decision Horizon", ["", 7, 30, 60, 90, 180, 365], index=0, placeholder="Select horizon")

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        rebalance = st.selectbox("Rebalance Frequency", ["", "daily", "weekly", "monthly", "quarterly"], index=0, placeholder="Select rebalance")
    with c6:
        benchmark = st.selectbox("Benchmark", ["", "SPY", "QQQ"], index=0, placeholder="Select benchmark")
    with c7:
        strategy = st.selectbox("Strategy Selection", ["", "Composite Agent Strategy", "Risk-Off Composite", "Buy & Hold Benchmark Portfolio"], index=0, placeholder="Select strategy")
    with c8:
        sizing = st.selectbox("Position Sizing Logic", ["", "Confidence Weighted", "Risk Adjusted", "Equal Weight"], index=0, placeholder="Select sizing")

    c9, c10, c11, c12 = st.columns(4)
    with c9:
        transaction_cost_raw = st.text_input("Transaction Cost (bps)", value="", placeholder="Enter bps")
    with c10:
        slippage_raw = st.text_input("Slippage (bps)", value="", placeholder="Enter bps")
    with c11:
        max_position_raw = st.text_input("Max Position", value="", placeholder="0.40 = 40%")
    with c12:
        max_exposure_raw = st.text_input("Max Gross Exposure", value="", placeholder="1.00 = 100%")

    run_button = st.button("RUN INSTITUTIONAL BACKTEST", type="primary", use_container_width=True)
    if run_button:
        if not portfolio_raw or parsed.get("status") != "SUCCESS":
            st.error("Fix portfolio input before running backtest.")
            return
        required = {
            "start date": start_date_raw,
            "end date": end_date_raw,
            "initial capital": initial_capital_raw,
            "decision horizon": horizon,
            "rebalance frequency": rebalance,
            "strategy": strategy,
            "position sizing": sizing,
            "transaction cost": transaction_cost_raw,
            "slippage": slippage_raw,
            "max position": max_position_raw,
            "max gross exposure": max_exposure_raw,
        }
        missing = [name for name, value in required.items() if value in ("", None)]
        if missing:
            st.error("Complete required configuration fields: " + ", ".join(missing))
            return
        try:
            start_date = datetime.strptime(start_date_raw, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_raw, "%Y-%m-%d").date()
            initial_capital = float(initial_capital_raw)
            transaction_cost = float(transaction_cost_raw)
            slippage = float(slippage_raw)
            max_position = float(max_position_raw)
            max_exposure = float(max_exposure_raw)
        except Exception as e:
            st.error(f"Invalid configuration value: {e}")
            return
        if not (min_date <= start_date <= max_date and min_date <= end_date <= max_date):
            st.error(f"Dates must be within dataset range: {min_date} to {max_date}.")
            return

        stages = [
            "Loading historical data",
            "Computing indicators",
            "Computing regime state",
            "Running rolling simulation",
            "Executing strategy logic",
            "Evaluating outcomes",
            "Calculating metrics",
            "Generating calibration curves",
            "Benchmark comparison",
            "Finalizing report",
        ]
        progress = st.progress(0)
        status_box = st.empty()
        for idx, stage in enumerate(stages[:3], 1):
            status_box.info(f"{stage}...")
            progress.progress(idx / len(stages))

        try:
            with st.spinner("Institutional backtest running..."):
                output = run_institutional_backtest(
                    parsed.get("holdings", []),
                    start_date,
                    end_date,
                    initial_capital=float(initial_capital),
                    rebalance_frequency=rebalance,
                    benchmark=benchmark,
                    transaction_cost_bps=float(transaction_cost),
                    slippage_bps=float(slippage),
                    horizon_days=int(horizon),
                    strategy=strategy,
                    position_sizing=sizing,
                    max_position=float(max_position),
                    max_gross_exposure=float(max_exposure),
                    dataset=dataset,
                )
                st.session_state["last_institutional_backtest"] = output
            progress.progress(1.0)
            if str(output.get("status")) == "SUCCESS":
                status_box.success("Institutional backtest complete.")
            else:
                status_box.warning("Backtest completed with audit review items.")
        except Exception as e:
            status_box.error(f"Backtest failed: {e}")

    if st.session_state.get("last_institutional_backtest"):
        render_institutional_backtest(st.session_state["last_institutional_backtest"])
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.info("No backtest executed")
        with c2:
            st.info("Awaiting portfolio configuration")
        with c3:
            st.info("Configure strategy and run evaluation")


def _render_backtest_outputs(output: dict, *, label: str):
    metrics = output.get("metrics", {}) or {}
    results = output.get("results") or output.get("portfolio_results") or []
    errors = output.get("errors") or []

    st.markdown(f"### {label} Results")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Win Rate", _pct(metrics.get("win_rate")))
    with c2:
        st.metric("Avg Return", _pct(metrics.get("average_return"), 2))
    with c3:
        st.metric("Total Runs", metrics.get("total_runs", 0))
    with c4:
        st.metric("Coverage", _pct(metrics.get("coverage")))
    with c5:
        try:
            st.metric("Avg Confidence", f"{float(metrics.get('average_confidence', 0)):.1f}/100")
        except Exception:
            st.metric("Avg Confidence", "-")

    c6, c7, c8, c9 = st.columns(4)
    with c6:
        st.metric("Median Return", _pct(metrics.get("median_return"), 2))
    with c7:
        st.metric("Sharpe", f"{float(metrics.get('sharpe_ratio', 0) or 0):.2f}")
    with c8:
        st.metric("Volatility", _pct(metrics.get("volatility"), 2))
    with c9:
        st.metric("Max Drawdown", _pct(metrics.get("max_drawdown"), 2))

    c10, c11, c12, c13 = st.columns(4)
    with c10:
        st.metric("CAGR", _pct(metrics.get("cagr"), 2))
    with c11:
        st.metric("Sortino", f"{float(metrics.get('sortino_ratio', 0) or 0):.2f}")
    with c12:
        st.metric("Alpha", _pct(metrics.get("alpha"), 2))
    with c13:
        st.metric("Beta", _num(metrics.get("beta")))

    try:
        import pandas as pd
        import plotly.express as px
        from evaluation_engine import compute_returns

        result_df = pd.DataFrame(results)
        if not result_df.empty:
            display_cols = ["as_of_date", "decision", "confidence", "future_return", "strategy_return", "outcome", "valid"]
            visible = [c for c in display_cols if c in result_df.columns]
            st.markdown("**Backtest Table**")
            st.dataframe(result_df[visible], use_container_width=True, hide_index=True)

            returns_df = compute_returns(results)
            if not returns_df.empty:
                try:
                    fig = px.line(returns_df, x="as_of_date", y="cumulative_return", title="Cumulative Strategy Return")
                    fig.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10))
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as chart_error:
                    st.warning(f"Chart diagnostics: cumulative return render failed — {chart_error}")

                returns_df = returns_df.copy()
                returns_df["rolling_return"] = returns_df["strategy_return"].rolling(20, min_periods=5).mean()
                try:
                    fig_roll = px.line(returns_df, x="as_of_date", y="rolling_return", title="Rolling Performance (20-run average)")
                    fig_roll.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
                    st.plotly_chart(fig_roll, use_container_width=True)
                except Exception as chart_error:
                    st.warning(f"Chart diagnostics: rolling return render failed — {chart_error}")

                equity = returns_df.copy()
                equity["equity"] = 1.0 + equity["cumulative_return"]
                equity["peak"] = equity["equity"].cummax()
                equity["drawdown"] = (equity["peak"] - equity["equity"]) / equity["peak"]
                try:
                    fig_dd = px.area(equity, x="as_of_date", y="drawdown", title="Drawdown Curve")
                    fig_dd.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10), yaxis_tickformat=".0%")
                    st.plotly_chart(fig_dd, use_container_width=True)
                except Exception as chart_error:
                    st.warning(f"Chart diagnostics: drawdown render failed — {chart_error}")

            if "outcome" in result_df.columns:
                dist = result_df["outcome"].value_counts().reset_index()
                dist.columns = ["Outcome", "Count"]
                fig_dist = px.bar(dist, x="Outcome", y="Count", title="Win/Loss Distribution")
                fig_dist.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig_dist, use_container_width=True)

            rolling = metrics.get("rolling_metrics") or []
            if rolling:
                roll_df = pd.DataFrame(rolling)
                left, right = st.columns(2)
                with left:
                    fig_wr = px.line(roll_df, x="as_of_date", y="rolling_win_rate", title="Rolling Win Rate")
                    fig_wr.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10), yaxis_tickformat=".0%")
                    st.plotly_chart(fig_wr, use_container_width=True)
                with right:
                    fig_sh = px.line(roll_df, x="as_of_date", y="rolling_sharpe", title="Rolling Sharpe")
                    fig_sh.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10))
                    st.plotly_chart(fig_sh, use_container_width=True)

            sector_accuracy = metrics.get("sector_accuracy") or {}
            if sector_accuracy:
                sector_df = pd.DataFrame([{"sector": k, **v} for k, v in sector_accuracy.items()])
                fig_sector = px.density_heatmap(sector_df, x="sector", y="accuracy", z="count", title="Sector Accuracy Heatmap")
                fig_sector.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig_sector, use_container_width=True)

        calibration = metrics.get("calibration") or []
        if calibration:
            cal_df = pd.DataFrame(calibration)
            st.markdown("**Confidence Calibration**")
            st.dataframe(cal_df, use_container_width=True, hide_index=True)
            chart_df = cal_df.dropna(subset=["accuracy"]) if "accuracy" in cal_df.columns else cal_df
            if not chart_df.empty:
                fig_cal = px.bar(chart_df, x="bucket", y="accuracy", title="Confidence Bucket vs Actual Accuracy")
                fig_cal.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10), yaxis_tickformat=".0%")
                st.plotly_chart(fig_cal, use_container_width=True)

        if errors:
            with st.expander("Failure Transparency"):
                st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)

        if results:
            with st.expander("Missing Fields Audit"):
                audit_rows = []
                for row in results[:300]:
                    audit_rows.append(
                        {
                            "date": row.get("as_of_date"),
                            "missing_engines": ", ".join(row.get("missing_engines") or []),
                            "missing_fields": ", ".join((row.get("missing_fields") or [])[:8]),
                        }
                    )
                st.dataframe(pd.DataFrame(audit_rows), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Could not render backtest outputs: {e}")


def evaluation_lab_interface():
    st.subheader("Evaluation Lab")
    st.caption("Leakage-safe historical backtesting using data/stock_prices_daily.csv as the source of truth.")

    try:
        from evaluation_engine import (
            build_portfolio_intelligence,
            load_dataset,
            load_evaluation_runs,
            run_backtest,
            run_historical_replay,
            run_multi_horizon_backtest,
            run_factor_research,
            rank_predictive_factors,
            run_portfolio_backtest,
            run_strategy_backtest,
            run_strategy_comparison,
        )

        dataset = load_dataset()
        tickers = sorted(dataset["Ticker"].dropna().unique().tolist())
        min_date = dataset["Date"].min().date()
        max_date = dataset["Date"].max().date()
    except Exception as e:
        st.error(f"Evaluation engine unavailable: {e}")
        return

    st.info(
        "Indicators are computed dynamically from rows where Date <= cutoff. "
        "Dataset-unsupported engines are marked unavailable instead of inferred."
    )

    tab_stock, tab_portfolio, tab_replay, tab_strategy, tab_factor, tab_calibration, tab_stored = st.tabs(
        ["Stock Backtest", "Portfolio Backtest", "Historical Replay", "Strategy Lab", "Factor Research Lab", "Calibration Center", "Stored Runs"]
    )

    with tab_stock:
        c1, c2, c3, c4 = st.columns([1.2, 1, 1, 0.8])
        with c1:
            ticker = st.selectbox("Ticker", [""] + tickers, index=0, placeholder="Select ticker")
        with c2:
            start_date_raw = st.text_input("Start Date", value="", placeholder="YYYY-MM-DD", key="eval_stock_start")
        with c3:
            end_date_raw = st.text_input("End Date", value="", placeholder="YYYY-MM-DD", key="eval_stock_end")
        with c4:
            horizon_days = st.selectbox("Horizon", ["", 7, 30, 60, 90, 180, 365], index=0, placeholder="Select horizon")
        c5, c6 = st.columns([1, 1])
        with c5:
            step = st.selectbox("Rolling Frequency", ["", "daily", "weekly", "monthly"], index=0, placeholder="Select frequency")
        with c6:
            benchmark = st.selectbox("Benchmark", ["", "SPY", "QQQ", "None"], index=0, placeholder="Select benchmark")

        if st.button("Run Stock Backtest", type="primary", use_container_width=True):
            if not all([ticker, start_date_raw, end_date_raw, horizon_days, step]):
                st.error("Complete ticker, dates, horizon, and rolling frequency before running.")
                return
            try:
                start_date = datetime.strptime(start_date_raw, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date_raw, "%Y-%m-%d").date()
            except Exception as e:
                st.error(f"Invalid date format: {e}")
                return
            with st.spinner("Running leakage-safe rolling backtest..."):
                try:
                    st.session_state["last_stock_backtest"] = run_backtest(
                        ticker,
                        start_date,
                        end_date,
                        int(horizon_days),
                        step=step,
                        benchmark="" if benchmark == "None" else benchmark,
                        dataset=dataset,
                        log_results=True,
                    )
                except Exception as e:
                    st.error(f"Backtest failed: {e}")

        if st.session_state.get("last_stock_backtest"):
            last = st.session_state["last_stock_backtest"]
            _render_backtest_outputs(last, label=last.get("ticker", "Stock"))

        if st.button("Run Multi-Horizon Scan (7/30/60/90/180)", use_container_width=True):
            if not all([ticker, start_date_raw, end_date_raw, step]):
                st.error("Complete ticker, dates, and rolling frequency before running.")
                return
            try:
                start_date = datetime.strptime(start_date_raw, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date_raw, "%Y-%m-%d").date()
            except Exception as e:
                st.error(f"Invalid date format: {e}")
                return
            with st.spinner("Running multi-horizon evaluation scan..."):
                try:
                    st.session_state["last_multi_horizon"] = run_multi_horizon_backtest(
                        ticker,
                        start_date,
                        end_date,
                        step=step,
                        benchmark="" if benchmark == "None" else benchmark,
                        dataset=dataset,
                    )
                except Exception as e:
                    st.error(f"Multi-horizon scan failed: {e}")
        if st.session_state.get("last_multi_horizon"):
            import pandas as pd
            import plotly.express as px

            mh = st.session_state["last_multi_horizon"]
            summary_df = pd.DataFrame(mh.get("summary") or [])
            if not summary_df.empty:
                st.markdown("**Multi-Horizon Summary**")
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
                fig_mh = px.line(summary_df, x="horizon", y=["win_rate", "sharpe", "cagr"], markers=True, title="Multi-Horizon Evaluation")
                fig_mh.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig_mh, use_container_width=True)

    with tab_portfolio:
        raw = st.text_input("Portfolio Input", value="", placeholder="Enter portfolio weights: AAPL 40%, MSFT 30%")
        parsed_holdings = []
        if raw:
            try:
                from portfolio_parser import parse_portfolio_input

                parsed = parse_portfolio_input(raw)
                if parsed.get("status") == "SUCCESS":
                    parsed_holdings = parsed.get("holdings", [])
                    st.dataframe(parsed_holdings, use_container_width=True, hide_index=True)
                    for issue in parsed.get("issues", []):
                        st.caption(f"Parser note: {issue}")
                else:
                    st.warning("; ".join(parsed.get("issues") or ["Could not parse portfolio."]))
            except Exception as e:
                st.warning(f"Portfolio parser unavailable: {e}")
        else:
            st.info("No portfolio backtest executed. Awaiting portfolio configuration.")
        c1, c2, c3 = st.columns([1, 1, 0.8])
        with c1:
            p_start_raw = st.text_input("Portfolio Start", value="", placeholder="YYYY-MM-DD")
        with c2:
            p_end_raw = st.text_input("Portfolio End", value="", placeholder="YYYY-MM-DD")
        with c3:
            p_horizon = st.selectbox("Portfolio Horizon", ["", 7, 30, 60, 90, 180, 365], index=0, placeholder="Select horizon")

        if st.button("Run Portfolio Backtest", type="primary", use_container_width=True):
            if not all([raw, p_start_raw, p_end_raw, p_horizon]):
                st.error("Complete portfolio, dates, and horizon before running.")
                return
            try:
                p_start = datetime.strptime(p_start_raw, "%Y-%m-%d").date()
                p_end = datetime.strptime(p_end_raw, "%Y-%m-%d").date()
            except Exception as e:
                st.error(f"Invalid date format: {e}")
                return
            with st.spinner("Running equal-weight portfolio backtest..."):
                try:
                    st.session_state["last_portfolio_backtest"] = run_portfolio_backtest(
                        parsed_holdings or raw,
                        p_start,
                        p_end,
                        int(p_horizon),
                        dataset=dataset,
                    )
                except Exception as e:
                    st.error(f"Portfolio backtest failed: {e}")

        if st.session_state.get("last_portfolio_backtest"):
            output = st.session_state["last_portfolio_backtest"]
            _render_backtest_outputs(output, label="Equal-Weight Portfolio")
            div = output.get("diversification", {})
            if div:
                st.markdown("**Diversification Tracking**")
                st.dataframe(div.get("components", []), use_container_width=True, hide_index=True)
            try:
                portfolio_intel = build_portfolio_intelligence(output.get("holdings", parsed_holdings), dataset=dataset)
                render_portfolio_intelligence_summary(portfolio_intel)
            except Exception:
                pass

    with tab_replay:
        st.caption("Replay a decision as if the system were standing on a past date. No future rows are visible to the engines.")
        c1, c2, c3 = st.columns([1.2, 1, 0.8])
        with c1:
            replay_ticker = st.selectbox("Replay Ticker", [""] + tickers, index=0, key="replay_ticker", placeholder="Select ticker")
        with c2:
            replay_date_raw = st.text_input("Replay Date", value="", placeholder="YYYY-MM-DD")
        with c3:
            replay_horizon = st.selectbox("Replay Horizon", ["", 7, 30, 60, 90, 180, 365], index=0, placeholder="Select horizon")
        if st.button("Run Historical Replay", type="primary", use_container_width=True):
            if not all([replay_ticker, replay_date_raw, replay_horizon]):
                st.error("Complete ticker, replay date, and horizon before running.")
                return
            try:
                replay_date = datetime.strptime(replay_date_raw, "%Y-%m-%d").date()
            except Exception as e:
                st.error(f"Invalid date format: {e}")
                return
            with st.spinner("Replaying historical decision..."):
                try:
                    st.session_state["last_replay"] = run_historical_replay(replay_ticker, replay_date, int(replay_horizon), dataset=dataset)
                except Exception as e:
                    st.error(f"Historical replay failed: {e}")
        if st.session_state.get("last_replay"):
            replay = st.session_state["last_replay"]
            intel = replay.get("intelligence", {}) or {}
            verdict = intel.get("verdict", {}) or {}
            confidence = intel.get("confidence", {}) or {}
            outcome = replay.get("outcome", {}) or {}
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Decision", verdict.get("value", "-"), f"{verdict.get('score', '-')}/100")
            with c2:
                st.metric("Confidence", f"{confidence.get('score', '-')}/100")
            with c3:
                st.metric("Future Return", _pct(outcome.get("future_return"), 2))
            with c4:
                st.metric("Outcome", outcome.get("outcome", "Pending"))
            leakage = replay.get("no_leakage_audit") or {}
            if leakage:
                st.markdown("**No-Leakage Audit**")
                st.dataframe([leakage], use_container_width=True, hide_index=True)
            outcomes = replay.get("outcomes_by_horizon") or {}
            if outcomes:
                st.markdown("**Future Outcome Validation**")
                rows = [{"horizon_days": key, **value} for key, value in outcomes.items()]
                st.dataframe(rows, use_container_width=True, hide_index=True)
            render_stock_intelligence({"status": "SUCCESS", "intelligence": intel, "report": ""}, filename_prefix="historical_replay")

    with tab_strategy:
        st.caption("Compare deterministic rules against the same future-return evaluator used by the AI engine.")
        c1, c2, c3, c4 = st.columns([1.2, 1, 1, 0.8])
        with c1:
            strategy_ticker = st.selectbox("Strategy Ticker", [""] + tickers, index=0, key="strategy_ticker", placeholder="Select ticker")
        with c2:
            strategy_name = st.selectbox("Strategy", ["", "RSI", "MA_Crossover", "Volatility_Filter", "Custom_Score"], index=0, placeholder="Select strategy")
        with c3:
            strategy_start_raw = st.text_input("Strategy Start", value="", placeholder="YYYY-MM-DD")
        with c4:
            strategy_horizon = st.selectbox("Strategy Horizon", ["", 7, 30, 60, 90, 180, 365], index=0, placeholder="Select horizon")
        strategy_end_raw = st.text_input("Strategy End", value="", placeholder="YYYY-MM-DD")
        if st.button("Run Strategy Test", type="primary", use_container_width=True):
            if not all([strategy_ticker, strategy_name, strategy_start_raw, strategy_end_raw, strategy_horizon]):
                st.error("Complete ticker, strategy, dates, and horizon before running.")
                return
            try:
                strategy_start = datetime.strptime(strategy_start_raw, "%Y-%m-%d").date()
                strategy_end = datetime.strptime(strategy_end_raw, "%Y-%m-%d").date()
            except Exception as e:
                st.error(f"Invalid date format: {e}")
                return
            with st.spinner("Running strategy lab evaluation..."):
                try:
                    st.session_state["last_strategy_backtest"] = run_strategy_backtest(
                        strategy_ticker,
                        strategy_start,
                        strategy_end,
                        int(strategy_horizon),
                        strategy=strategy_name,
                        dataset=dataset,
                    )
                except Exception as e:
                    st.error(f"Strategy test failed: {e}")
        if st.session_state.get("last_strategy_backtest"):
            out = st.session_state["last_strategy_backtest"]
            _render_backtest_outputs(out, label=f"{out.get('ticker')} {out.get('strategy')} Strategy")
        if st.button("Compare Core Strategies", use_container_width=True):
            if not all([strategy_ticker, strategy_start_raw, strategy_end_raw, strategy_horizon]):
                st.error("Complete ticker, dates, and horizon before comparing strategies.")
                return
            try:
                strategy_start = datetime.strptime(strategy_start_raw, "%Y-%m-%d").date()
                strategy_end = datetime.strptime(strategy_end_raw, "%Y-%m-%d").date()
                st.session_state["last_strategy_comparison"] = run_strategy_comparison(
                    strategy_ticker,
                    strategy_start,
                    strategy_end,
                    int(strategy_horizon),
                    dataset=dataset,
                )
            except Exception as e:
                st.error(f"Strategy comparison failed: {e}")
        if st.session_state.get("last_strategy_comparison"):
            comparison = st.session_state["last_strategy_comparison"]
            rows = comparison.get("summary") or []
            if rows:
                st.markdown("**Strategy Comparison Framework**")
                st.dataframe(rows, use_container_width=True, hide_index=True)
                competition = comparison.get("competition") or {}
                if competition:
                    st.markdown("**Strategy Arena Verdict**")
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "champion": (competition.get("champion_strategy") or {}).get("strategy"),
                                    "runner_up": (competition.get("runner_up_strategy") or {}).get("strategy"),
                                    "worst": (competition.get("worst_strategy") or {}).get("strategy"),
                                    "scoring_rule": competition.get("scoring_rule"),
                                }
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

    with tab_factor:
        st.caption("Evaluate whether a deterministic factor had historical forward-return signal quality.")
        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1, 0.8])
        with c1:
            factor_ticker = st.selectbox("Factor Ticker", [""] + tickers, index=0, key="factor_ticker", placeholder="Select ticker")
        with c2:
            factor_name = st.selectbox(
                "Factor",
                ["", "rsi_14", "rsi_percentile", "momentum_20d", "momentum_60d", "trend_persistence_60d", "volatility_20d", "downside_deviation_60d", "tail_risk_252d", "volume_anomaly_60d"],
                index=0,
                placeholder="Select factor",
            )
        with c3:
            factor_start_raw = st.text_input("Factor Start", value="", placeholder="YYYY-MM-DD")
        with c4:
            factor_horizon = st.selectbox("Factor Horizon", ["", 7, 30, 60, 90, 180, 365], index=0, placeholder="Select horizon")
        factor_end_raw = st.text_input("Factor End", value="", placeholder="YYYY-MM-DD")
        if st.button("Run Factor Research", type="primary", use_container_width=True):
            if not all([factor_ticker, factor_name, factor_start_raw, factor_end_raw, factor_horizon]):
                st.error("Complete ticker, factor, dates, and horizon before running.")
                return
            try:
                factor_start = datetime.strptime(factor_start_raw, "%Y-%m-%d").date()
                factor_end = datetime.strptime(factor_end_raw, "%Y-%m-%d").date()
                st.session_state["last_factor_research"] = run_factor_research(
                    factor_ticker,
                    factor_name,
                    factor_start,
                    factor_end,
                    int(factor_horizon),
                    dataset=dataset,
                )
            except Exception as e:
                st.error(f"Factor research failed: {e}")
        if st.button("Rank Predictive Factors", use_container_width=True):
            if not all([factor_ticker, factor_start_raw, factor_end_raw, factor_horizon]):
                st.error("Complete ticker, dates, and horizon before ranking factors.")
                return
            try:
                factor_start = datetime.strptime(factor_start_raw, "%Y-%m-%d").date()
                factor_end = datetime.strptime(factor_end_raw, "%Y-%m-%d").date()
                st.session_state["last_factor_ranking"] = rank_predictive_factors(
                    factor_ticker,
                    factor_start,
                    factor_end,
                    int(factor_horizon),
                    dataset=dataset,
                )
            except Exception as e:
                st.error(f"Factor ranking failed: {e}")
        if st.session_state.get("last_factor_research"):
            import pandas as pd
            import plotly.express as px

            fr = st.session_state["last_factor_research"]
            if fr.get("status") != "SUCCESS":
                st.warning(fr.get("message", "Factor research unavailable."))
            else:
                c1, c2, c3, c4, c5 = st.columns(5)
                with c1:
                    st.metric("Observations", fr.get("observations", 0))
                with c2:
                    st.metric("IC", f"{float(fr.get('ic', fr.get('predictive_correlation', 0)) or 0):.3f}")
                with c3:
                    st.metric("Rank IC", f"{float(fr.get('rank_ic', 0) or 0):.3f}")
                with c4:
                    st.metric("Hit Rate", _pct(fr.get("hit_rate")))
                with c5:
                    st.metric("Avg Return", _pct(fr.get("average_return"), 2))
                st.markdown("**Factor Evidence Summary**")
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "factor": fr.get("factor"),
                                "observations": fr.get("observations"),
                                "correlation": fr.get("predictive_correlation"),
                                "ic": fr.get("ic"),
                                "rank_ic": fr.get("rank_ic"),
                                "predictive_power": fr.get("predictive_power"),
                                "hit_rate": fr.get("hit_rate"),
                                "average_return": fr.get("average_return"),
                                "median_return": fr.get("median_return"),
                                "best_return": fr.get("best_return"),
                                "worst_return": fr.get("worst_return"),
                                "best_decile": fr.get("best_decile"),
                                "worst_decile": fr.get("worst_decile"),
                            }
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
                summary = pd.DataFrame(fr.get("bucket_analysis") or fr.get("decile_summary") or [])
                if not summary.empty:
                    st.dataframe(summary, use_container_width=True, hide_index=True)
                    try:
                        fig = px.bar(summary, x="bucket", y="average_return", title="Forward Return by Factor Bucket")
                        fig.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10), yaxis_tickformat=".2%")
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception as chart_error:
                        st.warning(f"Chart diagnostics: factor bucket render failed — {chart_error}")

        if st.session_state.get("last_factor_ranking"):
            ranking = st.session_state["last_factor_ranking"]
            st.markdown("**Top Predictive / Worst Factors**")
            if ranking.get("status") != "SUCCESS":
                reasons = [str(item.get("reason")) for item in ranking.get("errors", [])[:3]]
                st.warning("Factor ranking unavailable: " + ("; ".join(reasons) if reasons else "insufficient observations"))
            else:
                st.dataframe(pd.DataFrame(ranking.get("ranking") or []), use_container_width=True, hide_index=True)

    with tab_calibration:
        runs = load_evaluation_runs(limit=5000)
        if not runs:
            st.caption("No stored runs yet. Run backtests to build calibration history.")
        else:
            import pandas as pd
            import plotly.express as px
            from evaluation_engine import compute_calibration, compute_metrics

            stored_metrics = compute_metrics(runs, [])
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Stored Runs", stored_metrics.get("total_runs", 0))
            with c2:
                st.metric("Stored Win Rate", _pct(stored_metrics.get("win_rate")))
            with c3:
                st.metric("Stored Sharpe", f"{stored_metrics.get('sharpe_ratio', 0):.2f}")
            with c4:
                st.metric("Stored Coverage", _pct(stored_metrics.get("coverage")))
            cal = pd.DataFrame(compute_calibration(runs))
            st.dataframe(cal, use_container_width=True, hide_index=True)
            chart_df = cal.dropna(subset=["accuracy"]) if "accuracy" in cal.columns else cal
            if not chart_df.empty:
                fig = px.line(chart_df, x="bucket", y="accuracy", markers=True, title="Confidence Calibration Curve")
                fig.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10), yaxis_tickformat=".0%")
                st.plotly_chart(fig, use_container_width=True)

    with tab_stored:
        runs = load_evaluation_runs(limit=500)
        if not runs:
            st.caption("No stored evaluation runs yet.")
        else:
            try:
                import pandas as pd

                df = pd.DataFrame(runs)
                st.dataframe(df.tail(300).iloc[::-1], use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Could not load stored runs: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SHARED UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _verdict_color(v: str) -> str:
    return {"BUY": "#10b981", "SELL": "#ef4444", "HOLD": "#f59e0b"}.get(str(v).upper(), "#6366f1")

def _verdict_class(v: str) -> str:
    return {"BUY": "verdict-buy", "SELL": "verdict-sell", "HOLD": "verdict-hold"}.get(str(v).upper(), "verdict-hold")

def _score_class(s) -> str:
    try:
        n = float(s)
        if n >= 60: return "score-high"
        if n >= 40: return "score-mid"
        return "score-low"
    except Exception:
        return "score-mid"

def _render_verdict_card(verdict: str, score, confidence, risk_label: str, one_liner: str = ""):
    css = _verdict_class(verdict)
    color = _verdict_color(verdict)
    st.markdown(f"""
    <div class="verdict-card {css}" style="margin-bottom:1.5rem;">
        <div class="verdict-label">Final Recommendation</div>
        <div class="verdict-value">{verdict}</div>
        <div style="display:flex;gap:2rem;margin-top:0.75rem;">
            <div><span style="font-size:0.72rem;color:#94a3b8;display:block;">COMPOSITE SCORE</span>
                 <span style="font-size:1.4rem;font-weight:800;color:{color};">{score if score is not None else '—'}/100</span></div>
            <div><span style="font-size:0.72rem;color:#94a3b8;display:block;">CONFIDENCE</span>
                 <span style="font-size:1.4rem;font-weight:800;color:#e2e8f0;">{confidence if confidence is not None else '—'}/100</span></div>
            <div><span style="font-size:0.72rem;color:#94a3b8;display:block;">RISK LEVEL</span>
                 <span style="font-size:1.4rem;font-weight:800;color:#e2e8f0;">{risk_label or '—'}</span></div>
        </div>
        {f'<div class="verdict-sub" style="margin-top:0.75rem;font-style:italic;">"{one_liner}"</div>' if one_liner else ''}
    </div>
    """, unsafe_allow_html=True)

def _render_score_bar(label: str, score, signal: str = ""):
    try:
        pct = min(max(float(score), 0), 100)
    except Exception:
        pct = 0
    css = _score_class(pct)
    sig_html = f'<span style="color:#64748b;font-size:0.72rem;font-weight:600;">{signal}</span>' if signal else ""
    st.markdown(f"""
    <div class="score-bar-wrap">
        <div class="score-bar-label"><span>{label}</span>{sig_html}</div>
        <div style="display:flex;align-items:center;gap:0.75rem;">
            <div class="score-bar-track" style="flex:1">
                <div class="score-bar-fill {css}" style="width:{pct}%;"></div>
            </div>
            <span style="font-size:0.9rem;font-weight:700;color:#0f172a;min-width:2.5rem;text-align:right;">{pct:.0f}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

def _render_interp(text: str, kind: str = "ok", title: str = "Interpretation"):
    cls = {"ok": "interp-box", "warn": "interp-box-warn", "risk": "interp-box-risk"}.get(kind, "interp-box")
    st.markdown(f"""
    <div class="{cls}">
        <div class="interp-title">{title}</div>
        <div class="interp-text">{text}</div>
    </div>
    """, unsafe_allow_html=True)

def _render_metric_card(label: str, value: str, sub: str = ""):
    st.markdown(f"""
    <div class="af-metric">
        <div class="af-metric-label">{label}</div>
        <div class="af-metric-value">{value}</div>
        {f'<div class="af-metric-sub">{sub}</div>' if sub else ''}
    </div>
    """, unsafe_allow_html=True)

def _section(title: str):
    st.markdown(f'<div class="af-section"><div class="af-section-heading">{title}</div></div>', unsafe_allow_html=True)

def _sub(label: str):
    st.markdown(f'<div class="af-section-title">{label}</div>', unsafe_allow_html=True)

def _generate_stock_one_liner(verdict: str, symbol: str, scores: dict) -> str:
    v = verdict.upper()
    fund = (scores.get("fundamental") or {}).get("score", 50)
    tech  = (scores.get("technical") or {}).get("score", 50)
    risk  = (scores.get("risk") or {}).get("score", 50)
    try:
        fund, tech, risk = float(fund), float(tech), float(risk)
    except Exception:
        return f"{symbol} rated {v} by the intelligence engine."
    if v == "BUY":
        if fund > 65 and tech > 65:
            return f"{symbol} shows strong fundamentals and positive technical momentum, supporting a BUY."
        if risk < 35:
            return f"{symbol} presents a low-risk entry with sufficient upside signals to merit a BUY."
        return f"{symbol} scores above threshold across key engines, yielding a BUY recommendation."
    if v == "SELL":
        if risk > 65:
            return f"{symbol} carries elevated risk and weakening signals — reduce or exit position."
        return f"{symbol} scores below investment threshold — SELL or avoid at current levels."
    if fund > 55:
        return f"{symbol} has solid fundamentals but lacks clear directional conviction — HOLD and monitor."
    return f"{symbol} presents a mixed picture with insufficient edge to commit — HOLD."

def _generate_portfolio_one_liner(signal: str, score, hhi: float, n: int) -> str:
    s = (signal or "HOLD").upper()
    try: hhi = float(hhi)
    except Exception: hhi = 0.2
    conc = "concentrated" if hhi > 0.25 else ("moderately concentrated" if hhi > 0.15 else "diversified")
    if s == "BUY":
        return f"This {n}-stock portfolio is {conc} with an overall bullish tilt — suitable for growth-oriented investors."
    if s == "SELL":
        return f"Portfolio signals are broadly negative — review positions and consider reducing exposure."
    return f"Portfolio of {n} holdings appears {conc}. No immediate action required but monitor concentration."



# ══════════════════════════════════════════════════════════════════════
# NORMALIZED DATA MODELS
# ══════════════════════════════════════════════════════════════════════

@dataclass
class BacktestResultNormalized:
    source: str = "tastytrade"
    symbol: str = ""
    strategy: str = ""
    initial_capital: float = 100_000.0
    final_capital: Optional[float] = None
    total_pl: float = 0.0
    total_return_pct: float = 0.0
    win_rate_pct: Optional[float] = None
    trades_count: int = 0
    sharpe: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    risk_score: Optional[float] = None
    confidence_score: Optional[float] = None
    decision: str = "REVIEW"
    backtest_id: str = ""
    validation_passed: bool = False


@dataclass
class AIAgentResultNormalized:
    source: str = "ai_agents"
    symbol: str = ""
    initial_capital: float = 100_000.0
    expected_pl: Optional[float] = None
    expected_return_pct: Optional[float] = None
    expected_win_rate_pct: Optional[float] = None
    expected_max_drawdown_pct: Optional[float] = None
    risk_score: float = 50.0
    confidence_score: float = 50.0
    decision: str = "HOLD"
    agent_votes: Dict[str, Any] = field(default_factory=dict)
    reasoning: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComparisonResult:
    backtest_decision: str = ""
    ai_decision: str = ""
    agreement: str = "MISSING"
    final_decision: str = "REVIEW"
    metric_gaps: Dict[str, Any] = field(default_factory=dict)
    explanation: str = ""


# ══════════════════════════════════════════════════════════════════════
# ACCURACY METRICS  (manual — no sklearn dependency)
# ══════════════════════════════════════════════════════════════════════

def compute_classification_metrics(y_true: List[str], y_pred: List[str]) -> Dict[str, Any]:
    if not y_true or not y_pred or len(y_true) != len(y_pred):
        return {"error": "Invalid or mismatched label lists"}
    if len(y_true) < 2:
        return {"error": "Need at least 2 evaluated windows for accuracy metrics"}
    labels = sorted(set(y_true + y_pred))
    n = len(y_true)
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    accuracy = correct / n
    per_class: Dict[str, Any] = {}
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        prec   = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1     = 2 * prec * recall / (prec + recall) if (prec + recall) > 0 else 0.0
        per_class[label] = {
            "precision": round(prec, 4), "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": sum(1 for t in y_true if t == label),
        }
    macro_p = sum(v["precision"] for v in per_class.values()) / len(per_class) if per_class else 0.0
    macro_r = sum(v["recall"]    for v in per_class.values()) / len(per_class) if per_class else 0.0
    macro_f = sum(v["f1"]        for v in per_class.values()) / len(per_class) if per_class else 0.0
    idx = {lbl: i for i, lbl in enumerate(labels)}
    matrix = [[0] * len(labels) for _ in range(len(labels))]
    for t, p in zip(y_true, y_pred):
        if t in idx and p in idx:
            matrix[idx[t]][idx[p]] += 1
    return {
        "accuracy": round(accuracy, 4),
        "macro_precision": round(macro_p, 4),
        "macro_recall": round(macro_r, 4),
        "macro_f1": round(macro_f, 4),
        "per_class": per_class,
        "confusion_matrix": {"labels": labels, "matrix": matrix},
        "n_samples": n,
        "n_correct": correct,
    }


# ══════════════════════════════════════════════════════════════════════
# DECISION LOGIC
# ══════════════════════════════════════════════════════════════════════

def backtest_to_decision(result: dict) -> str:
    if not result or not result.get("passed_validation"):
        return "REVIEW"
    wr  = float(result.get("win_rate") or 0)
    tpl = float(result.get("total_profit_loss") or 0)
    if tpl > 0 and wr > 0.50:
        return "BUY"
    if tpl < 0 and wr < 0.40:
        return "SELL"
    return "HOLD"


def ai_result_to_normalized(
    result: dict, symbol: str = "", initial_capital: float = 100_000.0
) -> AIAgentResultNormalized:
    intel    = (result or {}).get("intelligence") or {}
    scores   = intel.get("scores") or {}
    verdict  = intel.get("verdict") or {}
    conf_obj = intel.get("confidence") or {}
    risk_obj = (scores.get("risk") or {})
    return AIAgentResultNormalized(
        symbol=symbol.upper(),
        initial_capital=initial_capital,
        risk_score=float(risk_obj.get("score") or 50),
        confidence_score=float(conf_obj.get("score") or 50),
        decision=(verdict.get("value") or "HOLD").upper(),
        agent_votes={
            k: (scores.get(k) or {}).get("signal", "Unavailable")
            for k in ("fundamental", "technical", "valuation", "macro", "sentiment", "risk")
        },
        reasoning={
            k: int((scores.get(k) or {}).get("score", 0))
            for k in ("fundamental", "technical", "valuation", "macro", "sentiment", "risk")
        },
    )


def normalize_backtest(result: dict, initial_capital: float = 100_000.0) -> BacktestResultNormalized:
    wr = float(result.get("win_rate") or 0)
    return BacktestResultNormalized(
        symbol=(result.get("symbol") or "").upper(),
        initial_capital=initial_capital,
        total_pl=float(result.get("total_profit_loss") or 0),
        win_rate_pct=wr * 100 if wr else None,
        trades_count=int(result.get("num_trades") or 0),
        decision=backtest_to_decision(result),
        backtest_id=str(result.get("backtest_id") or ""),
        validation_passed=bool(result.get("passed_validation")),
    )


def compare_results(
    bt: Optional[BacktestResultNormalized],
    ai: Optional[AIAgentResultNormalized],
) -> ComparisonResult:
    if bt is None and ai is None:
        return ComparisonResult(agreement="MISSING", final_decision="REVIEW",
                                explanation="Neither engine has run yet.")
    if bt is None:
        return ComparisonResult(ai_decision=ai.decision, agreement="MISSING",
                                final_decision=ai.decision,
                                explanation="AI agents ran but tastytrade backtest has not been executed.")
    if ai is None:
        return ComparisonResult(backtest_decision=bt.decision, agreement="MISSING",
                                final_decision=bt.decision,
                                explanation="Tastytrade backtest ran but AI agents have not been executed.")
    bd, ad = bt.decision, ai.decision
    if bd == ad:
        agr, final = "MATCH", bd
        exp = f"High-confidence alignment — both engines agree on {bd}."
    elif {bd, ad} == {"BUY", "SELL"}:
        agr, final = "CONFLICT", "REVIEW"
        exp = f"Engines contradict each other ({bd} vs {ad}). Manual review required."
    else:
        agr  = "PARTIAL"
        final = "REVIEW" if "REVIEW" in {bd, ad} else "HOLD"
        exp  = (f"Partial disagreement: backtest says {bd}, AI says {ad}. "
                "Hold and gather more evidence.")
    gaps: Dict[str, Any] = {}
    if bt.win_rate_pct is not None:
        gaps["win_rate"] = {"backtest": f"{bt.win_rate_pct:.1f}%", "ai_agent": "Not estimated"}
    if bt.total_pl != 0:
        gaps["total_pl"] = {"backtest": f"${bt.total_pl:,.0f}", "ai_agent": "Not estimated"}
    return ComparisonResult(
        backtest_decision=bd, ai_decision=ad,
        agreement=agr, final_decision=final,
        metric_gaps=gaps, explanation=exp,
    )


# ══════════════════════════════════════════════════════════════════════
# UI HELPERS
# ══════════════════════════════════════════════════════════════════════

def _console_page_header(title: str, subtitle: str = "") -> None:
    api = _get_api_status()
    try:
        from src.config.settings import settings as _s
        tt = _s.has_tastytrade_auth
    except Exception:
        tt = False
    g_cls  = "badge badge-ok"   if api["google_ok"]   else "badge badge-warn"
    r_cls  = "badge badge-ok"   if api["rapidapi_ok"] else "badge badge-warn"
    tt_cls = "badge badge-ok"   if tt                  else "badge badge-warn"
    g_t    = "+ Google AI"  if api["google_ok"]   else "- Google AI"
    r_t    = "+ RapidAPI"   if api["rapidapi_ok"] else "- RapidAPI"
    tt_t   = "+ Tastytrade" if tt                  else "- Tastytrade"
    sub_html = f'<div class="console-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(f"""
    <div class="console-hdr">
        <div>
            <div class="console-title">{title}</div>
            {sub_html}
        </div>
        <div class="console-badge-wrap">
            <span class="{g_cls}">{g_t}</span>
            <span class="{r_cls}">{r_t}</span>
            <span class="{tt_cls}">{tt_t}</span>
            <span class="badge badge-purple">AI FINANCE</span>
        </div>
    </div>""", unsafe_allow_html=True)


def _sec(title: str) -> None:
    st.markdown(f'<div class="sec-head">{title}</div>', unsafe_allow_html=True)


def _decision_card_html(label: str, decision: str, sub: str, source: str) -> str:
    _map = {
        "BUY": "dc-buy", "SELL": "dc-sell", "HOLD": "dc-hold",
        "REVIEW": "dc-review", "MATCH": "dc-buy", "CONFLICT": "dc-sell",
        "PARTIAL": "dc-hold", "MISSING": "dc-review",
    }
    cls = _map.get(str(decision).upper(), "dc-review")
    return (
        f'<div class="dc-card {cls}">'
        f'<div class="dc-lbl">{label}</div>'
        f'<div class="dc-val">{decision}</div>'
        f'<div class="dc-sub">{sub}</div>'
        f'<div class="dc-src">{source}</div></div>'
    )


# ══════════════════════════════════════════════════════════════════════
# PAGE 1: AJAY DECISION CONSOLE
# ══════════════════════════════════════════════════════════════════════

def _run_tastytrade_backtest_console(
    sym: str, start: str, end: str,
    direction: str, side: str, dte: int, delta: int, num_legs: int,
) -> None:
    try:
        from src.services.tastytrade_backtester_service import run_options_backtest
        from src.config.settings import settings as _s
    except ImportError as e:
        st.error(f"Tastytrade service unavailable: {e}")
        return
    if not _s.has_tastytrade_auth:
        st.warning("Tastytrade credentials not configured — skipping options backtest.")
        return
    legs = [
        {
            "type": "equity-option",
            "direction": direction,
            "quantity": 1,
            "side": side,
            "daysUntilExpiration": int(dte),
            "strikeSelection": "delta",
            "delta": int(delta),
        }
        for _ in range(int(num_legs))
    ]
    with st.spinner(f"Running tastytrade backtest for {sym}… (30–90 sec)"):
        try:
            r = run_options_backtest(symbol=sym, start_date=start, end_date=end, custom_legs=legs)
            st.session_state["last_tt_backtest"] = r
            if r.get("passed_validation"):
                st.success(
                    f"Backtest complete — ID: {r.get('backtest_id', '')} "
                    f"| Trials: {r.get('num_trials', 0)}"
                )
            else:
                st.error(f"Backtest failed validation: {r.get('message', 'See checklist')}")
        except Exception as exc:
            st.error(f"Backtest error: {exc}")


def _run_ai_agents_console(sym: str, initial_capital: float) -> None:
    initialize_agent()
    with st.spinner(f"Running AI agents for {sym}…"):
        try:
            r = st.session_state.agent.analyze_stock(sym)
            st.session_state["last_ai_agent_prediction"] = r
            if r.get("status") == "SUCCESS":
                intel = r.get("intelligence") or {}
                v  = (intel.get("verdict") or {}).get("value", "HOLD")
                sc = (intel.get("verdict") or {}).get("score", "—")
                st.success(f"AI agents complete — Decision: **{v}** ({sc}/100)")
            else:
                st.error(f"AI agents failed: {r.get('message', 'Unknown error')}")
        except Exception as exc:
            st.error(f"AI agent error: {exc}")


# ══════════════════════════════════════════════════════════════════════
# INSTITUTIONAL COLUMN RENDERERS
# ══════════════════════════════════════════════════════════════════════

def _metric_row(pairs: list) -> None:
    """Render a row of metric columns. pairs = [(label, value), ...]"""
    cols = st.columns(len(pairs))
    for col, (lbl, val) in zip(cols, pairs):
        col.metric(lbl, str(val))


def _decision_badge(decision: str) -> str:
    """Return HTML badge for a decision string."""
    _c = {"BUY": "#00875A", "SELL": "#DF1B41", "HOLD": "#F59E0B",
          "REVIEW": "#6b7280", "—": "#94a3b8"}
    color = _c.get(str(decision).upper(), "#6b7280")
    return (
        f'<span style="font-size:2rem;font-weight:900;color:{color};">'
        f'{decision}</span>'
    )


def _card_header(title: str, source: str) -> str:
    return (
        f'<div style="background:#f8fafc;border:1px solid #e3e8ee;border-radius:8px;'
        f'padding:0.9rem 1.1rem;margin-bottom:0.75rem;">'
        f'<div style="font-size:0.72rem;font-weight:700;color:#0A2540;text-transform:uppercase;'
        f'letter-spacing:0.08em;">{title}</div>'
        f'<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.15rem;">{source}</div>'
        f'</div>'
    )


def _render_backtest_column(bt_res: dict) -> None:
    """Tastytrade backtest results — institutional card format.
    Time O(1), Space O(1)
    """
    st.markdown(_card_header("BACKTESTING RESULTS", "tastytrade Backtester API"), unsafe_allow_html=True)

    if not bt_res:
        st.markdown(
            '<div style="border:2px dashed #e3e8ee;border-radius:8px;padding:1.5rem;'
            'text-align:center;color:#94a3b8;">No result — run the comparison first.</div>',
            unsafe_allow_html=True,
        )
        return

    passed   = bt_res.get("passed_validation", False)
    decision = backtest_to_decision(bt_res)
    _c       = {"BUY": "#00875A", "SELL": "#DF1B41", "HOLD": "#F59E0B"}.get(decision, "#6b7280")

    st.markdown(
        f'<div style="margin-bottom:0.6rem;">'
        f'{_decision_badge(decision)}'
        f'<span style="font-size:0.72rem;margin-left:0.8rem;'
        f'color:{"#00875A" if passed else "#DF1B41"};">'
        f'{"✓ Validation PASSED" if passed else "✗ Validation FAILED"}'
        f'</span></div>',
        unsafe_allow_html=True,
    )

    bt_id = str(bt_res.get("backtest_id") or "")
    if bt_id:
        st.caption(f"Backtest ID: {bt_id[:22]}")

    if not passed:
        st.error(bt_res.get("message", "Validation failed."))
        st.caption(f"Leg type returned: {bt_res.get('leg_type', 'unknown')}")
        return

    wr   = float(bt_res.get("win_rate")          or 0)
    tpl  = float(bt_res.get("total_profit_loss")  or 0)
    avpl = bt_res.get("average_profit_loss")
    sr   = bt_res.get("sharpe_ratio")
    mp   = bt_res.get("max_profit")
    ml   = bt_res.get("max_loss")

    _metric_row([
        ("Total P&L",   f"${tpl:,.0f}"),
        ("Win Rate",    f"{wr*100:.1f}%"),
        ("Trade Count", str(bt_res.get("num_trades") or "—")),
    ])
    _metric_row([
        ("Wins",     str(bt_res.get("num_wins")   or "—")),
        ("Losses",   str(bt_res.get("num_losses") or "—")),
        ("Avg P&L",  f"${float(avpl):,.0f}" if avpl else "—"),
    ])
    _metric_row([
        ("Sharpe Ratio", f"{float(sr):.2f}" if sr else "—"),
        ("Max Profit",   f"${float(mp):,.0f}" if mp else "—"),
        ("Max Loss",     f"${float(ml):,.0f}" if ml else "—"),
    ])

    st.caption(
        f"Initial Capital: $100,000 (default)  |  "
        f"Trials: {bt_res.get('num_trials', 0)}  |  "
        "CAGR / Alpha / Beta / Drawdown not returned by tastytrade API."
    )


def _render_ai_agents_column(ai_res: dict, initial_capital: float = 100_000.0) -> None:
    """AI agent prediction results — institutional card format.
    Time O(1), Space O(1)
    """
    st.markdown(_card_header("AI AGENTS PREDICTION", "AI Agent Engine · 6 intelligence engines"), unsafe_allow_html=True)

    if not ai_res or ai_res.get("status") != "SUCCESS":
        msg = (ai_res or {}).get("message", "")
        st.markdown(
            f'<div style="border:2px dashed #e3e8ee;border-radius:8px;padding:1.5rem;'
            f'text-align:center;color:#94a3b8;">'
            f'{"Error: " + msg if msg else "No result — run the comparison first."}</div>',
            unsafe_allow_html=True,
        )
        return

    intel   = ai_res.get("intelligence") or {}
    verdict = intel.get("verdict") or {}
    conf_o  = intel.get("confidence") or {}
    scores  = intel.get("scores") or {}

    decision = (verdict.get("value") or "HOLD").upper()
    score    = int(verdict.get("score") or 0)
    conf     = int(conf_o.get("score") or 0)

    st.markdown(
        f'<div style="margin-bottom:0.6rem;">'
        f'{_decision_badge(decision)}'
        f'<span style="font-size:0.72rem;margin-left:0.8rem;color:#635BFF;">'
        f'Score: {score}/100 · Confidence: {conf}/100'
        f'</span></div>',
        unsafe_allow_html=True,
    )

    def _s(eng: str) -> int:
        return int((scores.get(eng) or {}).get("score") or 0)

    _metric_row([
        ("Composite Score", f"{score}/100"),
        ("Confidence",      f"{conf}/100"),
        ("Risk Score",      f"{_s('risk')}/100"),
    ])
    _metric_row([
        ("Fundamental", f"{_s('fundamental')}/100"),
        ("Technical",   f"{_s('technical')}/100"),
        ("Valuation",   f"{_s('valuation')}/100"),
    ])
    _metric_row([
        ("Macro",      f"{_s('macro')}/100"),
        ("Sentiment",  f"{_s('sentiment')}/100"),
        ("P&L Est.",   "Not estimated"),
    ])

    st.caption(
        f"Initial Capital: ${initial_capital:,.0f}  |  "
        "Final Capital / CAGR / Win Rate / Drawdown: not estimated by AI agents."
    )


def _render_final_decision_board(cmp: "ComparisonResult") -> None:
    """Four-card final decision board: BT | AI | Agreement | Final."""
    _cc = {
        "BUY": "#00875A", "SELL": "#DF1B41", "HOLD": "#F59E0B",
        "REVIEW": "#6b7280", "MATCH": "#00875A", "CONFLICT": "#DF1B41",
        "PARTIAL": "#F59E0B", "MISSING": "#6b7280", "—": "#94a3b8",
    }

    cards = [
        ("Backtest Decision", cmp.backtest_decision or "—"),
        ("AI Agent Decision", cmp.ai_decision       or "—"),
        ("Agreement",         cmp.agreement          or "—"),
        ("Final Decision",    cmp.final_decision     or "—"),
    ]
    cols = st.columns(4)
    for col, (lbl, val) in zip(cols, cards):
        color = _cc.get(str(val).upper(), "#6b7280")
        col.markdown(
            f'<div style="text-align:center;padding:1rem 0.5rem;background:#f8fafc;'
            f'border:1px solid #e3e8ee;border-radius:8px;">'
            f'<div style="font-size:0.68rem;font-weight:700;color:#425466;'
            f'text-transform:uppercase;letter-spacing:0.06em;">{lbl}</div>'
            f'<div style="font-size:2rem;font-weight:900;color:{color};margin:0.3rem 0;">'
            f'{val}</div></div>',
            unsafe_allow_html=True,
        )

    if cmp.explanation:
        if cmp.agreement == "MATCH":
            st.success(cmp.explanation)
        elif cmp.agreement == "CONFLICT":
            st.error(cmp.explanation)
        else:
            st.warning(cmp.explanation)


def _render_accuracy_section() -> None:
    """Accuracy metrics from historical rolling evaluation runs.
    Time O(N*C), Space O(C^2).  N=samples, C=classes.
    """
    runs_path = os.path.join(os.path.dirname(__file__), "ai_agent_evaluation_runs.jsonl")
    records: List[dict] = []
    if os.path.exists(runs_path):
        try:
            with open(runs_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            pass

    if len(records) < 2:
        st.info(
            "Accuracy metrics require at least 2 historical evaluation samples. "
            "Use the **Accuracy Evaluation Lab** → Run Rolling Evaluation to generate scores. "
            "Minimum 2 samples required; 10+ recommended for reliable metrics."
        )
        if st.button("Open Accuracy Evaluation Lab", key="dc_goto_acc"):
            st.session_state["active_module"] = "Accuracy Evaluation Lab"
            st.rerun()
        return

    y_true = [r["actual_label"] for r in records if r.get("actual_label") and r.get("ai_decision")]
    y_pred = [r["ai_decision"]  for r in records if r.get("actual_label") and r.get("ai_decision")]
    m = compute_classification_metrics(y_true, y_pred)

    if "error" in m:
        st.warning(m["error"])
        return

    _metric_row([
        ("Accuracy",         f"{m['accuracy']*100:.1f}%"),
        ("Macro Precision",  f"{m['macro_precision']*100:.1f}%"),
        ("Macro Recall",     f"{m['macro_recall']*100:.1f}%"),
        ("Macro F1",         f"{m['macro_f1']*100:.1f}%"),
    ])
    st.caption(f"Based on {m['n_samples']} evaluated samples — {m['n_correct']} correct.")

    # Per-class table
    pc = m.get("per_class") or {}
    if pc:
        rows = [
            {"Class": k, "Precision": f"{v['precision']*100:.1f}%",
             "Recall": f"{v['recall']*100:.1f}%",
             "F1": f"{v['f1']*100:.1f}%",
             "Support": v["support"]}
            for k, v in pc.items()
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

    # Confusion matrix heatmap
    cm = m.get("confusion_matrix") or {}
    if cm.get("matrix"):
        lbls = cm["labels"]
        mat  = cm["matrix"]
        try:
            import plotly.graph_objects as go
            fig = go.Figure(go.Heatmap(
                z=mat, x=lbls, y=lbls,
                colorscale="Blues", text=mat, texttemplate="%{text}", showscale=True,
            ))
            fig.update_layout(
                title="Confusion Matrix (AI Predictions vs Actual)",
                height=280, margin=dict(l=10, r=10, t=40, b=10),
                xaxis_title="Predicted", yaxis_title="Actual",
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.dataframe(
                {"Label": lbls,
                 **{lbl: [mat[i][j] for i in range(len(lbls))] for j, lbl in enumerate(lbls)}}
            )


# ══════════════════════════════════════════════════════════════════════
# PAGE 1: DECISION CONSOLE
# ══════════════════════════════════════════════════════════════════════

def page_ajay_decision_console() -> None:
    """Main institutional comparison page: backtesting vs AI agents.
    Time O(engine_time), Space O(1)
    """
    # ── Compact header ──────────────────────────────────────────────
    api = _get_api_status()
    try:
        from src.config.settings import settings as _s
        tt_ok = _s.has_tastytrade_auth
    except Exception:
        tt_ok = api.get("tastytrade_ok", False)

    g_ok  = api["google_ok"]
    r_ok  = api["rapidapi_ok"]

    def _pill(label: str, ok: bool) -> str:
        bg  = "#e6f4ee" if ok else "#fef3c7"
        clr = "#00875A" if ok else "#92400e"
        sym = "✔" if ok else "✘"
        return (f'<span style="font-size:0.7rem;font-weight:600;padding:0.2rem 0.6rem;'
                f'border-radius:12px;background:{bg};color:{clr};margin-right:0.4rem;">'
                f'{sym} {label}</span>')

    st.markdown(
        f'<div style="padding:0.8rem 0 0.4rem;">'
        f'<div style="font-size:1.25rem;font-weight:800;color:#0A2540;letter-spacing:-0.02em;">'
        f'AI FINANCIAL ANALYST SYSTEM</div>'
        f'<div style="font-size:0.8rem;color:#425466;margin-top:0.15rem;margin-bottom:0.6rem;">'
        f'Backtesting vs AI Agent Intelligence</div>'
        f'{_pill("Google AI", g_ok)}'
        f'{_pill("RapidAPI", r_ok)}'
        f'{_pill("Tastytrade", tt_ok)}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Tastytrade warning ──────────────────────────────────────────
    if not tt_ok:
        st.error(
            "Tastytrade credentials are missing — backtesting cannot run.  "
            "Add TASTYTRADE_REFRESH_TOKEN and TASTYTRADE_CLIENT_SECRET to your .env file.  "
            "See Settings for guidance."
        )

    # ── Configuration ────────────────────────────────────────────────
    with st.expander("Backtest Configuration", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1: symbol  = st.text_input("Symbol",           value="SPY", key="dc_symbol")
        with c2: start   = st.text_input("Start Date",       value="2021-06-25", key="dc_start")
        with c3: end     = st.text_input("End Date",         value=str(date.today()), key="dc_end")
        with c4: capital = st.number_input("Initial Capital ($)", value=100_000,
                                           step=10_000, min_value=1_000,
                                           key="dc_capital", format="%d")

        st.markdown("**Options Strategy Parameters**")
        oc1, oc2, oc3, oc4, oc5 = st.columns(5)
        with oc1: direction = st.selectbox("Direction", ["short", "long"],  key="dc_dir")
        with oc2: side      = st.selectbox("Side",      ["put", "call"],    key="dc_side")
        with oc3: dte       = st.number_input("DTE",    value=45, min_value=1, max_value=365, key="dc_dte")
        with oc4: delta     = st.number_input("Delta",  value=30, min_value=1, max_value=99,  key="dc_delta")
        with oc5: num_legs  = st.selectbox("Legs",      [1, 2, 3, 4], index=1, key="dc_legs")

    sym  = (symbol or "SPY").strip().upper()
    cap  = float(capital)
    nleg = int(num_legs) if isinstance(num_legs, int) else 2

    run_all = st.button(
        "RUN BACKTEST + AI AGENT COMPARISON",
        type="primary", use_container_width=True, key="dc_btn_all",
    )

    if run_all:
        _run_tastytrade_backtest_console(
            sym, start, end, direction, side, int(dte), int(delta), nleg,
        )
        _run_ai_agents_console(sym, cap)

    bt_res = st.session_state.get("last_tt_backtest")
    ai_res = st.session_state.get("last_ai_agent_prediction")

    if not bt_res and not ai_res:
        st.markdown("---")
        st.info(
            "Configure symbol and parameters above, then click  "
            "**RUN BACKTEST + AI AGENT COMPARISON**."
        )
        return

    # ── Section 1: Two-column comparison ─────────────────────────────
    st.markdown("---")
    st.markdown("### 1. Backtesting Results vs AI Agents Prediction")
    col_bt, col_ai = st.columns(2)
    with col_bt:
        _render_backtest_column(bt_res or {})
    with col_ai:
        _render_ai_agents_column(ai_res or {}, cap)

    # ── Section 2: Final decision board ──────────────────────────────
    st.markdown("---")
    st.markdown("### 2. Final Decision")
    bt_norm = normalize_backtest(bt_res) if bt_res else None
    ai_norm = (
        ai_result_to_normalized(ai_res)
        if (ai_res and ai_res.get("status") == "SUCCESS")
        else None
    )
    cmp = compare_results(bt_norm, ai_norm)
    _render_final_decision_board(cmp)

    # ── Section 3: Accuracy metrics ──────────────────────────────────
    st.markdown("---")
    st.markdown("### 3. Accuracy Metrics")
    _render_accuracy_section()

    # ── Raw evidence (collapsed) ──────────────────────────────────────
    if bt_res:
        with st.expander("Backtesting Raw Data (tastytrade)"):
            _render_tt_result_pro(bt_res)
    if ai_res and ai_res.get("status") == "SUCCESS":
        with st.expander("AI Agent Raw Data"):
            render_stock_intelligence(ai_res, filename_prefix=f"{sym}_prediction")


# ══════════════════════════════════════════════════════════════════════
# PAGE 2: TASTYTRADE BACKTEST LAB
# ══════════════════════════════════════════════════════════════════════

def page_tastytrade_backtest_lab() -> None:
    _console_page_header(
        "Tastytrade Backtest Lab",
        "Options strategy backtesting — verified equity-option payload",
    )
    tastytrade_options_backtesting_interface()


# ══════════════════════════════════════════════════════════════════════
# PAGE 3: AI AGENT PREDICTION LAB
# ══════════════════════════════════════════════════════════════════════

def page_ai_agent_prediction_lab() -> None:
    _console_page_header(
        "AI Agent Prediction Lab",
        "6-engine deterministic intelligence — BUY/SELL/HOLD from agent consensus",
    )
    initialize_agent()
    _sec("Input")
    c1, c2 = st.columns([3, 1])
    with c1:
        sym = st.text_input("Symbol", placeholder="AAPL, SPY, MSFT…", key="ai_lab_sym").upper()
    with c2:
        run = st.button("Run AI Agents", type="primary", use_container_width=True, key="ai_lab_run")
    if run and sym:
        with st.spinner(f"Running AI agents for {sym}…"):
            try:
                r = st.session_state.agent.analyze_stock(sym)
                st.session_state["last_ai_agent_prediction"] = r
            except Exception as e:
                st.error(f"Agent error: {e}")
                return
        if r.get("status") == "SUCCESS":
            intel = r.get("intelligence") or {}
            v  = (intel.get("verdict") or {}).get("value", "HOLD")
            sc = (intel.get("verdict") or {}).get("score", "—")
            st.success(f"Decision: **{v}** ({sc}/100)")
        else:
            st.error(f"Analysis failed: {r.get('message')}")
    elif run and not sym:
        st.warning("Enter a ticker symbol.")
    res = st.session_state.get("last_ai_agent_prediction")
    if res and res.get("status") == "SUCCESS":
        render_stock_intelligence(res, filename_prefix=f"{sym or 'stock'}_pred")


# ══════════════════════════════════════════════════════════════════════
# PAGE 4: BACKTEST vs AI COMPARISON
# ══════════════════════════════════════════════════════════════════════

def page_backtest_vs_ai_comparison() -> None:
    _console_page_header(
        "Backtest vs AI Comparison",
        "Side-by-side comparison of tastytrade backtest and AI agent outputs",
    )
    bt_res = st.session_state.get("last_tt_backtest")
    ai_res = st.session_state.get("last_ai_agent_prediction")
    if not bt_res and not ai_res:
        st.info("Run both engines first. Use Ajay Decision Console or the individual Lab pages.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Open Tastytrade Backtest Lab", use_container_width=True, key="cmp_tt"):
                st.session_state["active_module"] = "Tastytrade Backtest Lab"
                st.rerun()
        with c2:
            if st.button("Open AI Agent Prediction Lab", use_container_width=True, key="cmp_ai"):
                st.session_state["active_module"] = "AI Agent Prediction Lab"
                st.rerun()
        return
    _render_decision_board(bt_res or {}, ai_res or {})
    if (bt_res and bt_res.get("passed_validation")
            and ai_res and ai_res.get("status") == "SUCCESS"):
        _render_comparison_table(bt_res, ai_res)
    else:
        _sec("Same-Parameter Comparison")
        if not bt_res or not bt_res.get("passed_validation"):
            st.warning("Tastytrade backtest has not run or did not pass validation.")
        if not ai_res or ai_res.get("status") != "SUCCESS":
            st.warning("AI agents have not run or failed.")
    _sec("Decision Explanation")
    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**Why Backtest decided this**")
        if bt_res and bt_res.get("passed_validation"):
            wr  = float(bt_res.get("win_rate") or 0)
            tpl = float(bt_res.get("total_profit_loss") or 0)
            st.write(f"- Realized P&L: **${tpl:,.0f}**")
            st.write(f"- Win rate: **{wr*100:.1f}%**")
            st.write(f"- Trades: **{bt_res.get('num_trades', 0)}**")
            st.write("- Decision rule: P&L > 0 AND win rate > 50% = BUY")
        else:
            st.caption("No validated backtest result.")
    with col_r:
        st.markdown("**Why AI Agents decided this**")
        if ai_res and ai_res.get("status") == "SUCCESS":
            for eng in ("fundamental", "technical", "valuation", "macro", "sentiment", "risk"):
                obj = ((ai_res.get("intelligence") or {}).get("scores") or {}).get(eng) or {}
                st.write(f"- {eng.title()}: **{obj.get('score', 0)}/100** ({obj.get('signal', '—')})")
        else:
            st.caption("No AI agent result.")
    cmp = compare_results(
        normalize_backtest(bt_res) if bt_res else None,
        ai_result_to_normalized(ai_res) if (ai_res and ai_res.get("status") == "SUCCESS") else None,
    )
    kind = (
        "interp-box"      if cmp.agreement == "MATCH" else
        "interp-box-risk" if cmp.agreement == "CONFLICT" else
        "interp-box-warn"
    )
    st.markdown(
        f'<div class="{kind}"><div class="interp-title">Final Interpretation — {cmp.agreement}</div>'
        f'<div class="interp-text">{cmp.explanation}</div></div>',
        unsafe_allow_html=True,
    )
    _render_accuracy_section()
    _sec("Export")
    report = (
        f"# Backtest vs AI Comparison\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"## Decision Board\n"
        f"Backtest:  {cmp.backtest_decision or 'Not run'}\n"
        f"AI Agent:  {cmp.ai_decision or 'Not run'}\n"
        f"Agreement: {cmp.agreement}\n"
        f"Final:     {cmp.final_decision}\n\n"
        f"## Explanation\n"
        f"{cmp.explanation}\n"
    )
    st.download_button(
        "Download Report (.txt)", data=report,
        file_name=f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        mime="text/plain",
    )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5: TASTYTRADE OPTIONS STRATEGY LAB (enhanced)
# ══════════════════════════════════════════════════════════════════════════════

def tastytrade_options_backtesting_interface():
    """Tastytrade Options Strategy Lab — professional options backtesting."""
    _section("Options Strategy Lab")
    st.caption(
        "Validate options strategies using the tastytrade Backtester API. "
        "Uses verified payload: **type='equity-option'**. "
        "Results are only displayed when all validation checks pass."
    )

    try:
        from src.services.tastytrade_backtester_service import run_options_backtest
        from src.config.settings import settings
    except ImportError as e:
        st.error(f"Could not load tastytrade services: {e}")
        return

    # ── Auth gate ──────────────────────────────────────────────────────────
    if not settings.has_tastytrade_auth:
        st.markdown("""
        <div class="interp-box-warn">
            <div class="interp-title">Configuration Required</div>
            <div class="interp-text">Tastytrade credentials are not configured. Add the following to your <code>.env</code> file to enable options backtesting.</div>
        </div>
        """, unsafe_allow_html=True)
        st.code(
            "TASTYTRADE_API_BASE_URL=https://api.tastyworks.com\n"
            "TASTYTRADE_BACKTESTER_BASE_URL=https://backtester.vast.tastyworks.com\n"
            "TASTYTRADE_REFRESH_TOKEN=<your_refresh_token>\n"
            "TASTYTRADE_USER_AGENT=ajay-ai-finance/1.0",
            language="bash",
        )
        _render_interp(
            "The tastytrade Backtester API is <strong>options-only</strong>. "
            "For stock/equity backtesting, use the <strong>Evaluation Lab → Internal Backtesting</strong> page.",
            kind="ok"
        )
        return

    _render_interp(
        "tastytrade Backtester is <strong>options-only</strong> (SPY, QQQ, AAPL, etc.). "
        "For stock/equity backtesting, use the Evaluation Lab page.",
        kind="ok", title="Note"
    )

    # ── Input form ──────────────────────────────────────────────────────────
    with st.form("tt_backtest_form"):
        st.markdown("**Strategy Configuration**")
        c1, c2, c3 = st.columns(3)
        with c1:
            symbol = st.text_input("Symbol", value="SPY", placeholder="SPY")
        with c2:
            direction = st.selectbox("Direction", ["short", "long"])
        with c3:
            side = st.selectbox("Side", ["put", "call"])

        c4, c5 = st.columns(2)
        with c4:
            start_date = st.text_input("Start Date", value="2021-06-25", placeholder="YYYY-MM-DD")
        with c5:
            import datetime as _dt
            end_date = st.text_input("End Date", value=str(_dt.date.today()), placeholder="YYYY-MM-DD")

        c6, c7, c8, c9 = st.columns(4)
        with c6: dte      = st.number_input("DTE (Days to Exp.)", min_value=1,  max_value=365, value=45)
        with c7: delta    = st.number_input("Delta",              min_value=1,  max_value=99,  value=30)
        with c8: quantity = st.number_input("Quantity / Leg",     min_value=1,  max_value=100, value=1)
        with c9: num_legs = st.selectbox("Num. Legs", [1, 2, 3, 4], index=1)

        st.caption("Payload will use type='equity-option' (required for real results). Any other type returns null statistics.")
        submitted = st.form_submit_button("Run Options Backtest", type="primary", use_container_width=True)

    if not submitted:
        if st.session_state.get("last_tt_backtest"):
            _render_tt_result_pro(st.session_state["last_tt_backtest"])
        return

    sym = symbol.strip().upper()
    if not sym:
        st.error("Symbol is required.")
        return

    from src.utils.validation_utils import validate_date_range
    ok, err = validate_date_range(start_date, end_date)
    if not ok:
        st.error(err)
        return

    with st.spinner(f"Running tastytrade options backtest for {sym}... this may take 30–90 seconds."):
        try:
            from src.services.tastytrade_backtester_service import build_custom_legs_payload
            legs = [{"type": "equity-option", "direction": direction, "quantity": int(quantity),
                     "side": side, "daysUntilExpiration": int(dte), "strikeSelection": "delta", "delta": int(delta)}
                    for _ in range(int(num_legs))]
            result = run_options_backtest(symbol=sym, start_date=start_date, end_date=end_date,
                                          custom_legs=legs)
            st.session_state["last_tt_backtest"] = result
        except Exception as exc:
            st.error(f"Backtest failed: {exc}")
            return

    _render_tt_result_pro(result)


def _render_tt_result_pro(result: dict):
    """Professional tastytrade backtest result renderer."""
    passed  = result.get("passed_validation", False)
    status  = result.get("status", "UNKNOWN")

    # ── Validation checklist ───────────────────────────────────────────────
    _section("Validation Checklist")
    leg_type   = result.get("leg_type", "—")
    stats_ok   = result.get("num_trades") is not None
    trials_ok  = (result.get("num_trials") or 0) > 0
    pl_ok      = passed and stats_ok

    checks = [
        ("Leg type = equity-option", leg_type == "equity-option"),
        ("Statistics returned",      stats_ok),
        ("Trials returned",          trials_ok),
        ("Non-zero P&L present",     pl_ok),
        ("Validation gate passed",   passed),
    ]
    check_cols = st.columns(len(checks))
    for col, (label, ok) in zip(check_cols, checks):
        with col:
            icon  = "✅" if ok else "❌"
            color = "#10b981" if ok else "#ef4444"
            st.markdown(f"""
            <div style="text-align:center;padding:0.75rem;border-radius:10px;background:#f8fafc;border:1px solid #e2e8f0;">
                <div style="font-size:1.5rem;">{icon}</div>
                <div style="font-size:0.7rem;font-weight:600;color:{color};margin-top:0.25rem;">{label}</div>
            </div>""", unsafe_allow_html=True)

    if not passed:
        msg = result.get("message", "Validation failed — see checklist above.")
        _render_interp(
            f"<strong>Backtest result was rejected.</strong> {msg}<br><br>"
            "Common fix: ensure payload uses <code>type='equity-option'</code> (not 'option' or 'equity'). "
            "Also verify that your tastytrade refresh token is valid and the symbol supports options.",
            kind="risk", title="Validation Failed"
        )
        with st.expander("Raw API Response (Debug)"):
            st.json(result.get("raw", result))
        return

    # ── SUCCESS ─────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="interp-box" style="margin-top:1rem;">
        <div class="interp-title">Strategy Validated</div>
        <div class="interp-text">Backtest completed successfully with <strong>{result.get('num_trials',0)}</strong> trials and real non-zero P&L data confirmed.</div>
    </div>""", unsafe_allow_html=True)

    _section("Performance Summary")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    with m1: _render_metric_card("Symbol",     result.get("symbol","—"))
    with m2: _render_metric_card("Leg Type",   result.get("leg_type","—"))
    with m3: _render_metric_card("Num Trials", str(result.get("num_trials","—")))
    with m4:
        wr = result.get("win_rate")
        _render_metric_card("Win Rate", f"{float(wr)*100:.1f}%" if wr is not None else "—")
    with m5: _render_metric_card("Total P&L",  f"${result.get('total_profit_loss',0):,.0f}" if result.get("total_profit_loss") is not None else "—")
    with m6: _render_metric_card("Avg P&L",    f"${result.get('average_profit_loss',0):,.0f}" if result.get("average_profit_loss") is not None else "—")

    m7, m8, m9, m10 = st.columns(4)
    with m7:  _render_metric_card("Max Profit", f"${result.get('max_profit',0):,.0f}" if result.get("max_profit") is not None else "—")
    with m8:  _render_metric_card("Max Loss",   f"${result.get('max_loss',0):,.0f}"   if result.get("max_loss") is not None else "—")
    with m9:  _render_metric_card("Num Wins",   str(result.get("num_wins","—")))
    with m10: _render_metric_card("Num Losses", str(result.get("num_losses","—")))

    # ── P&L interpretation ─────────────────────────────────────────────────
    wr_f = float(result.get("win_rate") or 0)
    tpl  = float(result.get("total_profit_loss") or 0)
    kind = "ok" if tpl > 0 and wr_f > 0.5 else ("warn" if wr_f >= 0.4 else "risk")
    _render_interp(
        f"Strategy produced a total P&L of <strong>${tpl:,.0f}</strong> across {result.get('num_trials',0)} trials "
        f"with a win rate of <strong>{wr_f*100:.1f}%</strong>. "
        + ("Strong risk-adjusted performance." if wr_f > 0.6 and tpl > 0 else
           "Marginal win rate — evaluate risk/reward carefully." if wr_f >= 0.4 else
           "Below 40% win rate — strategy may require parameter adjustment."),
        kind=kind, title="Strategy Interpretation"
    )

    # ── P&L Distribution ──────────────────────────────────────────────────
    trial_rows = result.get("trial_rows", [])
    if trial_rows:
        _section("P&L Distribution")
        tab_hist, tab_trials, tab_raw = st.tabs(["P&L Histogram", "Trial Log", "Raw Summary"])
        import pandas as pd
        df = pd.DataFrame(trial_rows)
        with tab_hist:
            if "profit_loss" in df.columns:
                import plotly.express as px
                fig = px.histogram(df, x="profit_loss", nbins=50, title="Trade P&L Distribution",
                                   color_discrete_sequence=["#6366f1"])
                fig.add_vline(x=0, line_dash="dash", line_color="#ef4444", opacity=0.7, annotation_text="Break-even")
                fig.update_layout(height=340, margin=dict(l=10, r=10, t=40, b=10),
                                  xaxis_title="P&L ($)", yaxis_title="Frequency")
                st.plotly_chart(fig, use_container_width=True)
        with tab_trials:
            st.dataframe(df.head(200), use_container_width=True, hide_index=True)
        with tab_raw:
            st.json({k: v for k, v in result.items() if k not in ("trial_rows","raw")})


def internal_backtesting_interface():
    """Internal Equity Backtesting page (for stocks — tastytrade is options-only)."""
    st.header("Internal Equity Backtesting")
    st.caption(
        "Leakage-safe backtesting using data/stock_prices_daily.csv. "
        "Strategies: Buy & Hold, MA Crossover."
    )

    try:
        from src.services.internal_backtester_service import run_equity_backtest
        from src.ui.streamlit_components import render_equity_curve, render_internal_backtest_metrics
    except ImportError as e:
        st.error(f"Could not load internal backtester: {e}")
        return

    # Check dataset exists
    import os
    dataset_path = "data/stock_prices_daily.csv"
    if not os.path.exists(dataset_path):
        st.warning(
            "data/stock_prices_daily.csv not found. "
            "The internal backtester requires this file with columns: Date, Ticker, Open, High, Low, Close, Volume."
        )
        return

    with st.form("internal_bt_form"):
        c1, c2 = st.columns(2)
        with c1:
            ticker = st.text_input("Ticker", value="", placeholder="e.g. AAPL")
        with c2:
            strategy = st.selectbox("Strategy", ["buy_and_hold", "ma_crossover"])

        c3, c4 = st.columns(2)
        with c3:
            start = st.text_input("Start Date", value="", placeholder="YYYY-MM-DD")
        with c4:
            end = st.text_input("End Date", value="", placeholder="YYYY-MM-DD")

        if strategy == "ma_crossover":
            m1, m2 = st.columns(2)
            with m1:
                fast_ma = st.number_input("Fast MA", min_value=2, max_value=200, value=20)
            with m2:
                slow_ma = st.number_input("Slow MA", min_value=5, max_value=500, value=50)
        else:
            fast_ma = slow_ma = None

        capital = st.number_input("Initial Capital ($)", min_value=100.0, value=10000.0, step=1000.0)
        run_btn = st.form_submit_button("Run Backtest", type="primary", use_container_width=True)

    if not run_btn:
        if st.session_state.get("last_internal_backtest"):
            _render_internal_result(
                st.session_state["last_internal_backtest"],
                render_equity_curve,
                render_internal_backtest_metrics,
            )
        return

    ticker = ticker.strip().upper()
    if not ticker:
        st.error("Ticker is required.")
        return
    if not start or not end:
        st.error("Start and end dates are required.")
        return

    kwargs = {"fast_ma": int(fast_ma), "slow_ma": int(slow_ma)} if fast_ma else {}

    with st.spinner(f"Running {strategy} backtest for {ticker}..."):
        try:
            result = run_equity_backtest(
                ticker=ticker,
                start_date=start,
                end_date=end,
                strategy=strategy,
                initial_capital=float(capital),
                dataset_path=dataset_path,
                **kwargs,
            )
            st.session_state["last_internal_backtest"] = result
        except Exception as exc:
            st.error(f"Backtest error: {exc}")
            return

    _render_internal_result(result, render_equity_curve, render_internal_backtest_metrics)


def _render_internal_result(result, render_equity_curve, render_metrics):
    if result.get("status") != "SUCCESS":
        st.error(result.get("message", "Backtest failed."))
        return

    st.success(f"{result['strategy']} backtest complete for {result['ticker']}")
    render_metrics(result)

    if result.get("equity_curve"):
        render_equity_curve(result["equity_curve"], title=f"{result['ticker']} — {result['strategy']}")

    if result.get("trade_log"):
        with st.expander(f"Trade Log ({len(result['trade_log'])} trades)"):
            st.dataframe(result["trade_log"], use_container_width=True, hide_index=True)


def prediction_validation_interface():
    """Prediction Validator page."""
    st.header("Prediction Validation")
    st.caption(
        "Evaluate past BUY/HOLD/SELL decisions against realised prices. "
        "Reads decision_memory.jsonl and data/stock_prices_daily.csv."
    )

    try:
        from src.services.prediction_validator_service import run_prediction_validation
    except ImportError as e:
        st.error(f"Could not load prediction validator: {e}")
        return

    if st.button("Run Validation", type="primary", use_container_width=True):
        with st.spinner("Evaluating predictions..."):
            try:
                result = run_prediction_validation()
                st.session_state["last_prediction_validation"] = result
            except Exception as exc:
                st.error(f"Validation error: {exc}")
                return

    result = st.session_state.get("last_prediction_validation")
    if not result:
        st.info("Click 'Run Validation' to evaluate stored predictions.")
        return

    if result.get("status") == "UNAVAILABLE":
        st.warning(result.get("message", "No prediction records found."))
        return
    if result.get("status") == "ERROR":
        st.error(result.get("message", "Validation error."))
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Total Evaluated", result.get("total_evaluated", 0))
    with c2:
        st.metric("Correct", result.get("correct", 0))
    with c3:
        acc = result.get("accuracy", 0)
        st.metric("Accuracy", f"{acc*100:.1f}%" if acc else "N/A")
    with c4:
        ba = result.get("buy_accuracy", 0)
        st.metric("BUY Accuracy", f"{ba*100:.1f}%" if ba else "N/A")
    with c5:
        sa = result.get("sell_accuracy", 0)
        st.metric("SELL Accuracy", f"{sa*100:.1f}%" if sa else "N/A")

    rows = result.get("rows", [])
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)



# ══════════════════════════════════════════════════════════════════════
# PAGE 5: ACCURACY EVALUATION LAB
# ══════════════════════════════════════════════════════════════════════

def page_accuracy_evaluation_lab() -> None:
    _console_page_header(
        "Accuracy Evaluation Lab",
        "Rolling historical evaluation — temporal cutoff, AI accuracy metrics",
    )
    evaluation_lab_interface()


# ══════════════════════════════════════════════════════════════════════
# PAGE 6: PORTFOLIO INTELLIGENCE
# ══════════════════════════════════════════════════════════════════════

def page_portfolio_intelligence() -> None:
    _console_page_header(
        "Portfolio Intelligence",
        "Multi-asset portfolio concentration, correlation, and signal analysis",
    )
    portfolio_analysis_interface()


# ══════════════════════════════════════════════════════════════════════
# PAGE 7: STOCK RESEARCH
# ══════════════════════════════════════════════════════════════════════

def page_stock_research() -> None:
    _console_page_header(
        "Stock Research",
        "Deep single-stock analysis — fundamentals, technicals, and AI narrative",
    )
    stock_analysis_interface()


# ══════════════════════════════════════════════════════════════════════
# PAGE 8: SETTINGS
# ══════════════════════════════════════════════════════════════════════

def page_settings() -> None:
    _console_page_header("Settings", "API configuration and session diagnostics")
    _sec("API Status")
    api = _get_api_status()
    try:
        from src.config.settings import settings as _s
        tt_ok = _s.has_tastytrade_auth
    except Exception:
        tt_ok = False
    c1, c2, c3 = st.columns(3)
    with c1:
        if api["google_ok"]:
            st.success("Google AI / Gemini — connected")
        else:
            st.warning("Google AI — not configured")
            st.caption("Set GOOGLE_API_KEY or GEMINI_API_KEY in .env")
    with c2:
        if api["rapidapi_ok"]:
            st.success("RapidAPI TradingView — connected")
        else:
            st.warning("RapidAPI — not configured")
            st.caption("Set RAPIDAPI_KEY in .env")
    with c3:
        if tt_ok:
            st.success("Tastytrade — credentials found")
        else:
            st.warning("Tastytrade — not configured")
            st.caption("Set TASTYTRADE_USERNAME and TASTYTRADE_PASSWORD in .env")
    _sec(".env Configuration Guide")
    st.code("""# Copy .env.example to .env and fill in your keys
GOOGLE_API_KEY=your_gemini_api_key
RAPIDAPI_KEY=your_rapidapi_key
TASTYTRADE_USERNAME=your_tastytrade_username
TASTYTRADE_PASSWORD=your_tastytrade_password""", language="bash")
    st.caption(
        "Never commit .env to git. "
        "The .gitignore already excludes .env files. "
        "See .env.example for the full template."
    )
    _sec("Session State Diagnostics")
    keys = [
        "last_tt_backtest", "last_ai_agent_prediction",
        "last_comparison_result", "last_accuracy_metrics",
        "last_stock_analysis", "last_portfolio_analysis",
        "last_ai_report", "active_module",
    ]
    status_rows = []
    for k in keys:
        val = st.session_state.get(k)
        if val is None:
            status = "Not set"
        elif isinstance(val, dict):
            status = f"dict ({len(val)} keys)"
        else:
            status = type(val).__name__
        status_rows.append({"Key": k, "Status": status})
    st.dataframe(status_rows, use_container_width=True, hide_index=True)
    if st.button("Clear All Session State", key="settings_clear"):
        for k in list(st.session_state.keys()):
            if k != "active_module":
                del st.session_state[k]
        st.success("Session state cleared (active_module preserved).")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════
# NAVIGATION
# ══════════════════════════════════════════════════════════════════════

MODULES = [
    "Decision Console",
    "Tastytrade Backtest Lab",
    "AI Agent Prediction Lab",
    "Backtest vs AI Comparison",
    "Accuracy Evaluation Lab",
    "Portfolio Intelligence",
    "Stock Research",
    "Settings",
]


def navigate_to(module: str) -> None:
    if module in MODULES:
        st.session_state["active_module"] = module
        st.rerun()


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════


def _sync_module() -> None:
    """Callback: copy widget state (module_picker) into routing state (active_module)."""
    st.session_state["active_module"] = st.session_state.get("module_picker", MODULES[0])


def main() -> None:
    initialize_agent()

    # Single source of truth for navigation
    if "active_module" not in st.session_state:
        st.session_state["active_module"] = MODULES[0]

    with st.sidebar:
        st.markdown(
            """<div style="padding:1.4rem 0.5rem 1.2rem;">
                <div style="font-size:1.05rem;font-weight:800;color:#f1f5f9;letter-spacing:-0.01em;">
                    AI Financial Analyst
                </div>
                <div style="font-size:0.72rem;color:#635BFF;font-weight:700;
                            letter-spacing:0.08em;text-transform:uppercase;">
                    Decision Intelligence System
                </div>
            </div>""",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='font-size:0.62rem;color:#475569;font-weight:700;"
            "letter-spacing:0.12em;text-transform:uppercase;"
            "padding:0 0.5rem 0.4rem;'>Modules</div>",
            unsafe_allow_html=True,
        )
        # st.radio is the single navigation control — writes active_module directly
        # Use module_picker as the widget key; active_module is plain state
        if "module_picker" not in st.session_state:
            st.session_state["module_picker"] = st.session_state["active_module"]
        st.radio(
            "",
            MODULES,
            index=MODULES.index(st.session_state["active_module"])
            if st.session_state["active_module"] in MODULES
            else 0,
            key="module_picker",
            on_change=_sync_module,
            label_visibility="collapsed",
        )
        st.markdown("<hr style='border-color:#1e293b;margin:1rem 0;'>", unsafe_allow_html=True)
        # Compact API status
        api = _get_api_status()
        st.markdown(
            f"""<div style="padding:0 0.25rem;">
            <div style="font-size:0.62rem;color:#475569;font-weight:700;
                        letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.5rem;">
                API Status
            </div>
            <div style="font-size:0.78rem;color:{'#10b981' if api['google_ok'] else '#f59e0b'};
                        margin-bottom:0.25rem;">
                {'● Google AI' if api['google_ok'] else '○ Google AI'}
            </div>
            <div style="font-size:0.78rem;
                        color:{'#10b981' if api['rapidapi_ok'] else '#f59e0b'};">
                {'● RapidAPI' if api['rapidapi_ok'] else '○ RapidAPI'}
            </div>
            </div>""",
            unsafe_allow_html=True,
        )
        st.markdown("<hr style='border-color:#1e293b;margin:1rem 0;'>", unsafe_allow_html=True)
        user_id = st.text_input(
            "User ID",
            value=st.session_state.get("user_id", ""),
            placeholder="Your name",
            label_visibility="visible",
        )
        if user_id and user_id != st.session_state.get("user_id", ""):
            st.session_state.user_id = user_id
            if "agent" in st.session_state:
                st.session_state.agent = StockAnalysisAgent(user_id=user_id)

    # Route — active_module is synced from radio via _sync_module callback
    m = st.session_state["active_module"]
    if m == "Decision Console":
        page_ajay_decision_console()
    elif m == "Tastytrade Backtest Lab":
        page_tastytrade_backtest_lab()
    elif m == "AI Agent Prediction Lab":
        page_ai_agent_prediction_lab()
    elif m == "Backtest vs AI Comparison":
        page_backtest_vs_ai_comparison()
    elif m == "Accuracy Evaluation Lab":
        page_accuracy_evaluation_lab()
    elif m == "Portfolio Intelligence":
        page_portfolio_intelligence()
    elif m == "Stock Research":
        page_stock_research()
    elif m == "Settings":
        page_settings()
    else:
        page_ajay_decision_console()


if __name__ == "__main__":
    main()

