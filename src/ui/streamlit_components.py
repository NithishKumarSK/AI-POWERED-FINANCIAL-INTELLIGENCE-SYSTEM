"""Reusable Streamlit UI components shared across pages."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _pct(v: Any, decimals: int = 2) -> str:
    try:
        return f"{float(v) * 100:.{decimals}f}%"
    except Exception:
        return str(v) if v is not None else "-"


def _num(v: Any, decimals: int = 2) -> str:
    try:
        return f"{float(v):.{decimals}f}"
    except Exception:
        return str(v) if v is not None else "-"


def _dollar(v: Any) -> str:
    try:
        return f"${float(v):,.2f}"
    except Exception:
        return str(v) if v is not None else "-"


def render_verdict_card(verdict: str, score: float, confidence: float, risk_label: str) -> None:
    """Render the top-level decision card."""
    import streamlit as st

    color = {"BUY": "#00c896", "SELL": "#ff4b4b", "HOLD": "#ffd700"}.get(verdict, "#888")
    st.markdown(
        f"""<div style="border-left:5px solid {color}; padding:12px 16px; border-radius:6px;
        background:#1a1a2e; margin-bottom:12px;">
        <span style="font-size:28px; font-weight:700; color:{color};">{verdict}</span>
        &nbsp;<span style="color:#aaa;">Score {score:.0f}/100 · Confidence {confidence:.0f}% · Risk {risk_label}</span>
        </div>""",
        unsafe_allow_html=True,
    )


def render_kpi_row(metrics: List[Dict[str, Any]]) -> None:
    """Render a row of KPI metric cards.

    Each metric dict: {"label": str, "value": str, "delta": str (optional)}
    """
    import streamlit as st

    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            st.metric(label=m["label"], value=m["value"], delta=m.get("delta"))


def render_equity_curve(equity_curve: List[Dict[str, Any]], title: str = "Equity Curve") -> None:
    """Render equity curve line chart."""
    import streamlit as st
    import plotly.express as px
    import pandas as pd

    if not equity_curve:
        st.info("No equity curve data.")
        return

    df = pd.DataFrame(equity_curve)
    if df.empty or "date" not in df.columns or "value" not in df.columns:
        st.info("Equity curve data missing required columns.")
        return

    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    fig = px.line(df, x="date", y="value", title=title)
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def render_profit_loss_histogram(trial_rows: List[Dict[str, Any]], title: str = "P&L Distribution") -> None:
    """Histogram of trade P&L values."""
    import streamlit as st
    import plotly.express as px
    import pandas as pd

    if not trial_rows:
        st.info("No trial data to plot.")
        return

    df = pd.DataFrame(trial_rows)
    if "profit_loss" not in df.columns:
        st.info("Trial rows missing profit_loss column.")
        return

    df["profit_loss"] = pd.to_numeric(df["profit_loss"], errors="coerce").dropna()
    fig = px.histogram(df, x="profit_loss", nbins=40, title=title,
                       color_discrete_sequence=["#00c896"])
    fig.add_vline(x=0, line_dash="dash", line_color="red", opacity=0.6)
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def render_trial_table(trial_rows: List[Dict[str, Any]], max_rows: int = 200) -> None:
    """Render trial data table."""
    import streamlit as st
    import pandas as pd

    if not trial_rows:
        st.info("No trial data.")
        return

    df = pd.DataFrame(trial_rows[:max_rows])
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_validation_badge(passed: bool, reasons: List[str]) -> None:
    """Show green/red validation badge."""
    import streamlit as st

    if passed:
        st.success("Validation PASSED — real backtest data confirmed.")
    else:
        st.error("Validation FAILED — result not shown to prevent misleading data.")
        for r in reasons:
            st.warning(f"• {r}")


def render_backtest_summary_metrics(summary: Dict[str, Any]) -> None:
    """Render the main backtest KPI row."""
    import streamlit as st

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.metric("Total P&L", _dollar(summary.get("total_profit_loss")))
    with c2:
        st.metric("Win Rate", _pct(summary.get("win_rate")))
    with c3:
        st.metric("Avg P&L / Trade", _dollar(summary.get("average_profit_loss")))
    with c4:
        st.metric("Num Trades", str(summary.get("num_trades", "-")))
    with c5:
        st.metric("Max Profit", _dollar(summary.get("max_profit")))
    with c6:
        st.metric("Max Loss", _dollar(summary.get("max_loss")))


def render_internal_backtest_metrics(result: Dict[str, Any]) -> None:
    """KPI row for internal equity backtester."""
    import streamlit as st

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Total Return", _pct(result.get("total_return")))
    with c2:
        st.metric("CAGR", _pct(result.get("cagr")))
    with c3:
        st.metric("Max Drawdown", _pct(result.get("max_drawdown")))
    with c4:
        sharpe = result.get("sharpe")
        st.metric("Sharpe", _num(sharpe) if sharpe is not None else "N/A")
    with c5:
        final = result.get("final_value")
        st.metric("Final Value", _dollar(final) if final else "-")
