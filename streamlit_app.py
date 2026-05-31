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
import streamlit as st
from datetime import datetime

# Add paths - main directory first, then subdirectories
sys.path.insert(0, os.path.dirname(__file__))  # Main directory first
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'tools'))
sys.path.insert(2, os.path.join(os.path.dirname(__file__), 'config'))
sys.path.insert(3, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
from stock_analysis_agent import StockAnalysisAgent
from portfolio_manager import PortfolioManager

load_dotenv()

# Page configuration
st.set_page_config(
    page_title="AI Financial Analyst System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .afi-hero, .xeltrix-hero {
        padding: 1.25rem 1.25rem;
        border-radius: 16px;
        background: #FFFFFF;
        border: 1px solid rgba(15, 23, 42, 0.10);
        box-shadow: 0 10px 30px rgba(2, 8, 23, 0.06);
        margin-bottom: 0.75rem;
    }
    .afi-title, .xeltrix-title {
        font-size: 2.1rem;
        font-weight: 760;
        line-height: 1.15;
        margin-bottom: 0.25rem;
    }
    .afi-subtitle, .xeltrix-subtitle {
        opacity: 0.92;
        font-size: 1.0rem;
        margin-bottom: 0.25rem;
    }
    .tiny-muted {
        color: rgba(15, 23, 42, 0.70);
        font-size: 0.9rem;
    }
    .report-box {
        border-radius: 14px;
        border: 1px solid rgba(15, 23, 42, 0.10);
        padding: 0.85rem 0.95rem;
        background: #FFFFFF;
        box-shadow: 0 8px 20px rgba(2, 8, 23, 0.05);
    }
    .kpi-label {
        color: rgba(15, 23, 42, 0.68);
        font-size: 0.85rem;
        margin-bottom: 0.25rem;
        font-weight: 600;
        letter-spacing: 0.01em;
    }
    .kpi-value {
        font-size: 1.35rem;
        font-weight: 760;
        line-height: 1.2;
    }
    .pill {
        display: inline-block;
        padding: 0.20rem 0.55rem;
        border-radius: 999px;
        border: 1px solid rgba(15, 23, 42, 0.10);
        background: rgba(15, 23, 42, 0.03);
        font-size: 0.85rem;
        font-weight: 650;
        margin-left: 0.4rem;
        vertical-align: middle;
    }
</style>
""", unsafe_allow_html=True)


def _get_api_status() -> dict:
    google_ok = bool(os.getenv("GOOGLE_API_KEY"))
    rapidapi_ok = bool(os.getenv("RAPIDAPI_KEY")) and os.getenv("RAPIDAPI_KEY") != "mock-key-for-testing"
    return {"google_ok": google_ok, "rapidapi_ok": rapidapi_ok}


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
    st.markdown(
        """
        <div class="xeltrix-hero">
            <div class="xeltrix-title">AI FINANCIAL ANALYST SYSTEM</div>
            <div class="xeltrix-subtitle">Evaluation‑First Portfolio Research & Investment Intelligence</div>
            <div class="tiny-muted">Real‑Time Market Analysis • AI Reasoning • Portfolio Evaluation • Risk Intelligence</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    api_status = _get_api_status()
    model_name = os.getenv("AGENT_MODEL") or "-"

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("System", "Financial Intelligence", "evaluation‑first")
    with col2:
        st.metric("Model", model_name, "configured")
    with col3:
        status = "OK" if (api_status["google_ok"] and api_status["rapidapi_ok"]) else "Needs keys"
        st.metric("API Status", status, "paid APIs")
    with col4:
        st.metric("Evaluation", "Backtesting", "operational")

    with st.expander("Active AI Agents"):
        st.markdown(
            """
✅ Market Research Agent  
✅ Sentiment Analysis Agent  
✅ Risk Intelligence Agent  
✅ Portfolio Optimization Agent  
✅ Recommendation Critic Agent  
            """.strip()
        )


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
            return "-"
        return f"{float(value) * 100:.{digits}f}%"
    except Exception:
        return "-"


def _num(value, digits: int = 2) -> str:
    try:
        if value is None:
            return "-"
        return f"{float(value):.{digits}f}"
    except Exception:
        return "-"


def render_portfolio_intelligence_summary(output: dict):
    portfolio = output.get("portfolio", {}) or {}
    st.markdown("### Portfolio Intelligence")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Decision", portfolio.get("decision", "-"), f"{portfolio.get('composite_score', '-')}/100")
    with c2:
        st.metric("Confidence", f"{portfolio.get('confidence', '-')}/100")
    with c3:
        st.metric("Risk", f"{portfolio.get('risk_score', '-')}/100", portfolio.get("concentration_risk", "-"))
    with c4:
        st.metric("Diversification", f"{portfolio.get('diversification_score', '-')}/100")
    with c5:
        st.metric("Sharpe", f"{float(portfolio.get('sharpe_ratio', 0) or 0):.2f}")
    c6, c7, c8 = st.columns(3)
    with c6:
        st.metric("Portfolio Beta", f"{float(portfolio.get('portfolio_beta', 0) or 0):.2f}")
    with c7:
        st.metric("VaR 95%", _pct(portfolio.get("value_at_risk_95"), 2))
    with c8:
        st.metric("Max Drawdown", _pct(portfolio.get("max_drawdown"), 2))

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
    config = output.get("config", {}) or {}

    st.markdown("### Institutional Backtest Results")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Final Value", f"${float(metrics.get('final_value', 0) or 0):,.0f}", _pct(metrics.get("total_return"), 2))
    with c2:
        st.metric("CAGR", _pct(metrics.get("cagr"), 2))
    with c3:
        st.metric("Sharpe", f"{float(metrics.get('sharpe_ratio', 0) or 0):.2f}")
    with c4:
        st.metric("Max Drawdown", _pct(metrics.get("max_drawdown"), 2))
    with c5:
        st.metric("Win Rate", _pct(decision_metrics.get("win_rate")))

    c6, c7, c8, c9, c10 = st.columns(5)
    with c6:
        st.metric("Alpha", _pct(metrics.get("alpha"), 2))
    with c7:
        st.metric("Beta", _num(metrics.get("beta")))
    with c8:
        st.metric("Sortino", f"{float(metrics.get('sortino_ratio', 0) or 0):.2f}")
    with c9:
        st.metric("Info Ratio", _num(metrics.get("information_ratio")))
    with c10:
        st.metric("Trades", len(output.get("trade_log") or []))
    readiness = output.get("institutional_readiness") or {}
    if readiness:
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
            st.json(config)
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
                st.json(data_quality)
    except Exception as e:
        st.error(f"Could not render institutional backtest: {e}")


def institutional_backtesting_interface():
    st.subheader("Institutional Backtesting")
    st.caption("Capital simulation, deterministic decisions, benchmark comparison, trade logs, calibration, and regime-segmented evaluation.")

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
        st.dataframe(parsed.get("holdings", []), use_container_width=True, hide_index=True)
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
            status_box.success("Institutional backtest complete.")
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


def main():
    """Main application"""
    # Initialize agent
    initialize_agent()
    render_hero()

    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Select Module",
        [
            "Institutional Backtesting",
            "Portfolio Analysis",
            "Stock Research",
            "Evaluation Lab",
            "Strategy Lab",
            "Factor Research Lab",
            "Calibration Center",
            "Historical Replay",
            "Agent Debate Center",
            "Market Sentiment",
            "AI Recommendation",
            "Risk Intelligence",
        ],
        index=0,
    )

    if page == "Institutional Backtesting":
        institutional_backtesting_interface()
    elif page == "Stock Research":
        stock_analysis_interface()
    elif page == "Portfolio Analysis":
        portfolio_analysis_interface()
    elif page == "Evaluation Lab":
        evaluation_lab_interface()
    elif page in {"Strategy Lab", "Calibration Center", "Historical Replay", "Factor Research Lab"}:
        evaluation_lab_interface()
    elif page == "Agent Debate Center":
        st.subheader("Agent Debate Center")
        st.info("Run Stock Research or Historical Replay to view Bull, Bear, Risk, Macro, Technical, Critic, and Final agents with validated signals.")
    elif page == "Legacy Evaluation Lab":
        st.subheader("Evaluation Lab")
        st.caption("Evaluation-first infrastructure: temporal cutoff testing + stored runs + calibration.")

        st.info(
            "Cutoff mode currently uses **price-only** engines (Technical + Risk) to avoid future leakage. "
            "Other engines are marked Unavailable in this mode."
        )

        tickers_raw = st.text_input("Tickers (comma separated)", value="", placeholder="Enter ticker symbols")
        as_of_date = st.text_input("As-of date (YYYY-MM-DD)", value="", placeholder="YYYY-MM-DD")
        horizon_days = st.number_input("Horizon days", min_value=1, max_value=365, value=1)

        run_btn = st.button("Run Cutoff Backtest (price-only)", type="primary", use_container_width=True)

        results = []
        if run_btn:
            tickers = [t.strip().upper() for t in (tickers_raw or "").split(",") if t.strip()]
            if not tickers:
                st.warning("Enter at least one ticker.")
            else:
                with st.spinner("Running cutoff evaluations (price-only)…"):
                    for t in tickers[:25]:
                        out = st.session_state.agent.evaluate_price_only_cutoff(t, as_of_date=as_of_date, horizon_days=int(horizon_days))
                        if out.get("status") != "SUCCESS":
                            results.append(
                                {
                                    "Ticker": t,
                                    "Status": "ERROR",
                                    "Message": out.get("message", "Unknown error"),
                                }
                            )
                            continue
                        intel = out.get("intelligence") or {}
                        verdict = (intel.get("verdict") or {}).get("value")
                        comp = (intel.get("verdict") or {}).get("score")
                        conf = (intel.get("confidence") or {}).get("score")
                        outcome = out.get("outcome") or {}
                        results.append(
                            {
                                "Ticker": t,
                                "Status": "OK",
                                "Verdict": verdict,
                                "Composite": comp,
                                "Confidence": conf,
                                "Evaluated": bool(outcome.get("evaluated")),
                                "Actual Return": outcome.get("actual_return"),
                                "Correct": outcome.get("correct"),
                            }
                        )

        if results:
            st.markdown("### Run Results")
            st.dataframe(results, use_container_width=True, hide_index=True)

            evaluated = [r for r in results if r.get("Evaluated") is True and isinstance(r.get("Correct"), bool)]
            if evaluated:
                win_rate = sum(1 for r in evaluated if r.get("Correct") is True) / len(evaluated)
                st.metric("Win Rate", f"{win_rate*100:.1f}%", f"{len(evaluated)} evaluated")

                # Simple bar chart of returns
                try:
                    import plotly.express as px

                    chart_rows = [r for r in evaluated if isinstance(r.get("Actual Return"), (int, float))]
                    if chart_rows:
                        fig = px.bar(
                            chart_rows,
                            x="Ticker",
                            y="Actual Return",
                            title="Realized Return (cutoff → horizon)",
                        )
                        fig.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10))
                        st.plotly_chart(fig, use_container_width=True)
                except Exception:
                    pass

        # Historical stored runs (local)
        st.divider()
        st.markdown("### Stored Evaluation Runs (local)")
        runs_path = os.path.join(os.path.dirname(__file__), "evaluation_runs.jsonl")
        if os.path.exists(runs_path):
            loaded = []
            try:
                import json

                with open(runs_path, "r", encoding="utf-8") as f_in:
                    for line in f_in:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            loaded.append(json.loads(line))
                        except Exception:
                            continue
            except Exception:
                loaded = []

            if loaded:
                # Show recent
                recent = list(reversed(loaded[-200:]))
                st.dataframe(recent, use_container_width=True, hide_index=True)

                evaluated2 = [x for x in loaded if x.get("evaluated") is True and isinstance(x.get("correct"), bool)]
                if len(evaluated2) >= 20:
                    # Calibration table
                    buckets = {b: [] for b in range(0, 10)}
                    for x in evaluated2:
                        try:
                            b = int(min(9, max(0, int(x.get("confidence", 0)) // 10)))
                        except Exception:
                            continue
                        buckets[b].append(x)
                    cal_rows = []
                    for b, xs in buckets.items():
                        if not xs:
                            continue
                        acc = sum(1 for it in xs if bool(it.get("correct")) is True) / len(xs)
                        cal_rows.append({"Confidence Bucket": f"{b*10}-{b*10+9}", "N": len(xs), "Accuracy": round(acc * 100, 1)})
                    st.markdown("**Confidence Calibration (from evaluated runs)**")
                    st.dataframe(cal_rows, use_container_width=True, hide_index=True)
            else:
                st.caption("No runs parsed from file yet.")
        else:
            st.caption("No local evaluation file yet. Run at least one evaluation above to create it.")
    else:
        st.subheader(page)
        st.info("Evaluation Engine — Operational")

    # Sidebar
    with st.sidebar:
        st.header("Settings")

        st.subheader("User Session")

        # User ID input for session logging
        user_id = st.text_input("User ID", value=st.session_state.get('user_id', ''), placeholder="Enter user ID", help="Enter your user ID for session logging")
        if user_id and user_id != st.session_state.get('user_id', ''):
            st.session_state.user_id = user_id
            # Reinitialize agents with new user ID
            if 'agent' in st.session_state:
                st.session_state.agent = StockAnalysisAgent(user_id=user_id)
            if 'portfolio_manager' in st.session_state:
                st.session_state.portfolio_manager = PortfolioManager(user_id=user_id)
            st.success("Session updated with new user ID")

        st.divider()

        st.subheader("Quick Actions")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Clear Stock History"):
                st.session_state.analysis_history = []
                st.success("Stock history cleared")
        with col2:
            if st.button("Clear Portfolio History"):
                st.session_state.portfolio_history = []
                st.success("Portfolio history cleared")

        st.divider()

        st.subheader("About")
        st.info("""
        **AI Financial Analyst System** helps you:
        - Analyze individual stocks
        - Analyze entire portfolios
        - Generate structured reports

        Note: API calls may be paid. Start small.
        """)

        st.divider()

        st.subheader("System Status")

        # Check API keys
        google_api_key = os.getenv('GOOGLE_API_KEY')
        if google_api_key:
            st.success("Google AI configured")
        else:
            st.warning("Google AI not configured")

        rapidapi_key = os.getenv('RAPIDAPI_KEY')
        if rapidapi_key and rapidapi_key != 'mock-key-for-testing':
            st.success("RapidAPI configured")
        else:
            st.warning("RapidAPI not configured")


if __name__ == "__main__":
    main()
