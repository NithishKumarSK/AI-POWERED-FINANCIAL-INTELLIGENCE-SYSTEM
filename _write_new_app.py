"""Write the new clean single-page streamlit_app.py to disk."""
import os

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "streamlit_app.py")

NEW = r'''"""
AI Financial Analyst System
Single-page decision terminal.
Backtesting vs AI Agent Intelligence.
No sidebar. No navigation. One button. Two columns.
No personal names in UI. No live trading. No fake data.
"""
from __future__ import annotations
import os, sys, json
from pathlib import Path
from datetime import date
from typing import Any, Dict, List, Optional

# ── path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))
sys.path.insert(2, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)   # always reads project-root .env

import streamlit as st

st.set_page_config(
    page_title="AI Financial Analyst System",
    page_icon="\U0001f4ca",
    layout="wide",
    initial_sidebar_state="collapsed",
)

try:
    from stock_analysis_agent import StockAnalysisAgent
    _AGENT_OK = True
except ImportError:
    _AGENT_OK = False

RUNS_FILE = ROOT / "ai_agent_evaluation_runs.jsonl"

# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
.stApp{background:#F6F9FC;}
.block-container{padding-top:1rem!important;padding-bottom:2rem!important;max-width:1300px;}
.sys-title{font-size:1.4rem;font-weight:800;color:#0A2540;letter-spacing:-.02em;}
.sys-sub{font-size:.82rem;color:#425466;margin-top:.12rem;}
.spill{display:inline-block;font-size:.68rem;font-weight:700;
       padding:.18rem .65rem;border-radius:20px;margin-right:.35rem;}
.sp-ok{background:#D1FAE5;color:#065F46;}
.sp-warn{background:#FEF3C7;color:#92400E;}
.sp-err{background:#FEE2E2;color:#991B1B;}
.col-hdr{background:#fff;border:1px solid #E3E8EE;border-radius:8px;
         padding:.75rem 1rem .6rem;margin-bottom:.65rem;
         box-shadow:0 1px 3px rgba(10,37,64,.06);}
.col-hdr-t{font-size:.72rem;font-weight:700;color:#0A2540;
           text-transform:uppercase;letter-spacing:.08em;}
.col-hdr-s{font-size:.65rem;color:#94A3B8;margin-top:.1rem;}
.dv-buy{font-size:2.1rem;font-weight:900;color:#00875A;line-height:1;}
.dv-sell{font-size:2.1rem;font-weight:900;color:#DF1B41;line-height:1;}
.dv-hold{font-size:2.1rem;font-weight:900;color:#F59E0B;line-height:1;}
.dv-rev{font-size:2.1rem;font-weight:900;color:#6B7280;line-height:1;}
.fdb-card{text-align:center;padding:.9rem .4rem;background:#fff;
          border:1px solid #E3E8EE;border-radius:8px;
          box-shadow:0 1px 3px rgba(10,37,64,.04);}
.fdb-lbl{font-size:.63rem;font-weight:700;color:#425466;
         text-transform:uppercase;letter-spacing:.07em;}
.fdb-val{font-size:1.85rem;font-weight:900;margin-top:.2rem;}
.sec-hd{font-size:.88rem;font-weight:700;color:#0A2540;
        border-left:3px solid #635BFF;padding-left:.6rem;margin:1rem 0 .6rem;}
.af-hr{border:none;border-top:1px solid #E3E8EE;margin:1rem 0;}
.vbadge-ok{font-size:.72rem;color:#00875A;font-weight:600;}
.vbadge-err{font-size:.72rem;color:#DF1B41;font-weight:600;}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# STATUS
# ══════════════════════════════════════════════════════════════════════════════
def _status() -> dict:
    """Read API availability from environment. Time O(1), Space O(1)."""
    google  = bool(os.getenv("GOOGLE_API_KEY","").strip() or os.getenv("GEMINI_API_KEY","").strip())
    rapid   = bool(os.getenv("RAPIDAPI_KEY","").strip()) and os.getenv("RAPIDAPI_KEY","") != "mock-key-for-testing"
    tt_cs   = bool(os.getenv("TASTYTRADE_CLIENT_SECRET","").strip())
    tt_rt   = bool(os.getenv("TASTYTRADE_REFRESH_TOKEN","").strip())
    tt      = tt_cs and tt_rt
    return dict(google=google, rapidapi=rapid, tastytrade=tt, backtesting=tt)


def _pill(label: str, ok: bool) -> str:
    cls = "sp-ok" if ok else "sp-err"
    sym = "✔" if ok else "✘"
    return f'<span class="spill {cls}">{sym} {label}</span>'


# ══════════════════════════════════════════════════════════════════════════════
# TASTYTRADE BACKTEST ENGINE
# ══════════════════════════════════════════════════════════════════════════════
def _run_tastytrade(sym: str, start: str, end: str,
                    direction: str, side: str,
                    dte: int, delta: int, num_legs: int) -> dict:
    """Build verified equity-option payload and run backtest. Time O(k), Space O(k). k=num_legs."""
    try:
        from src.services.tastytrade_backtester_service import run_options_backtest
        from src.config.settings import settings
    except ImportError as exc:
        return {"status": "ERROR", "message": f"Import failed: {exc}", "passed_validation": False}

    if not settings.has_tastytrade_auth:
        return {
            "status": "MISSING_CREDENTIALS",
            "message": (
                "Tastytrade credentials are missing. "
                "Add TASTYTRADE_REFRESH_TOKEN and TASTYTRADE_CLIENT_SECRET to .env."
            ),
            "passed_validation": False,
        }

    legs = [
        {
            "type": "equity-option",      # MUST be equity-option
            "direction": direction,        # MUST be short or long
            "quantity": 1,
            "side": side,
            "daysUntilExpiration": int(dte),
            "strikeSelection": "delta",
            "delta": int(delta),
        }
        for _ in range(int(num_legs))
    ]
    try:
        return run_options_backtest(symbol=sym, start_date=start, end_date=end, custom_legs=legs)
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc), "passed_validation": False}


def _bt_decision(r: dict) -> str:
    """BUY / SELL / HOLD / REVIEW from backtest result. Time O(1)."""
    if not r or not r.get("passed_validation"):
        return "REVIEW"
    wr  = float(r.get("win_rate") or 0)
    tpl = float(r.get("total_profit_loss") or 0)
    if tpl > 0 and wr >= 0.50: return "BUY"
    if tpl < 0 and wr < 0.40:  return "SELL"
    return "HOLD"


# ══════════════════════════════════════════════════════════════════════════════
# AI AGENT ENGINE
# ══════════════════════════════════════════════════════════════════════════════
def _run_ai(sym: str) -> dict:
    """Run AI stock agent independently. Time O(engine_time), Space O(1)."""
    if not _AGENT_OK:
        return {"status": "ERROR", "message": "stock_analysis_agent module not available."}
    try:
        if "agent" not in st.session_state:
            st.session_state["agent"] = StockAnalysisAgent()
        return st.session_state["agent"].analyze_stock(sym)
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


def _ai_decision(r: dict) -> str:
    """Extract BUY / SELL / HOLD / REVIEW from agent result. Time O(1)."""
    if not r or r.get("status") != "SUCCESS":
        return "REVIEW"
    val = ((r.get("intelligence") or {}).get("verdict") or {}).get("value", "")
    return val.upper() if val.upper() in ("BUY","SELL","HOLD") else "REVIEW"


# ══════════════════════════════════════════════════════════════════════════════
# COMPARISON
# ══════════════════════════════════════════════════════════════════════════════
def _compare(bt_d: str, ai_d: str, bt_res: dict, ai_res: dict) -> dict:
    """Agreement + final combined decision. Time O(1), Space O(1)."""
    bt_ok = bool(bt_res and bt_res.get("passed_validation"))
    ai_ok = bool(ai_res and ai_res.get("status") == "SUCCESS")
    if not bt_ok and not ai_ok:
        return {"agreement":"MISSING","final":"REVIEW","msg":"Neither engine has produced a valid result yet."}
    if not bt_ok:
        return {"agreement":"MISSING","final":ai_d,"msg":"Backtesting did not produce a validated result. Showing AI decision only."}
    if not ai_ok:
        return {"agreement":"MISSING","final":bt_d,"msg":"AI agents did not produce a valid result. Showing backtest decision only."}
    if bt_d == ai_d:
        return {"agreement":"MATCH","final":bt_d,"msg":f"Both engines agree on {bt_d}. High-confidence signal."}
    if {bt_d, ai_d} == {"BUY","SELL"}:
        return {"agreement":"CONFLICT","final":"REVIEW","msg":f"Engines conflict ({bt_d} vs {ai_d}). Manual review required."}
    final = "HOLD" if "HOLD" in {bt_d, ai_d} else "REVIEW"
    return {"agreement":"PARTIAL","final":final,"msg":f"Partial disagreement: backtest={bt_d}, AI={ai_d}. Proceed with caution."}


# ══════════════════════════════════════════════════════════════════════════════
# ACCURACY METRICS  Time O(N*C), Space O(C^2)
# ══════════════════════════════════════════════════════════════════════════════
def _load_runs() -> List[dict]:
    records: List[dict] = []
    if not RUNS_FILE.exists():
        return records
    try:
        with open(RUNS_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try: records.append(json.loads(line))
                    except Exception: pass
    except Exception:
        pass
    return records


def _compute_accuracy(y_true: list, y_pred: list) -> dict:
    """Manual accuracy / precision / recall / F1 / confusion matrix. No sklearn needed."""
    if not y_true or len(y_true) != len(y_pred) or len(y_true) < 2:
        return {"error": f"Need >= 2 samples, got {len(y_true)}"}
    labels  = sorted(set(y_true + y_pred))
    n       = len(y_true)
    correct = sum(t==p for t,p in zip(y_true,y_pred))
    per: Dict[str, Any] = {}
    for lbl in labels:
        tp = sum(t==lbl and p==lbl for t,p in zip(y_true,y_pred))
        fp = sum(t!=lbl and p==lbl for t,p in zip(y_true,y_pred))
        fn = sum(t==lbl and p!=lbl for t,p in zip(y_true,y_pred))
        pr = tp/(tp+fp) if (tp+fp) else 0.0
        rc = tp/(tp+fn) if (tp+fn) else 0.0
        f1 = 2*pr*rc/(pr+rc) if (pr+rc) else 0.0
        per[lbl] = {"precision":round(pr,4),"recall":round(rc,4),"f1":round(f1,4),
                    "support":sum(t==lbl for t in y_true)}
    mp = sum(v["precision"] for v in per.values())/len(per) if per else 0.0
    mr = sum(v["recall"]    for v in per.values())/len(per) if per else 0.0
    mf = sum(v["f1"]        for v in per.values())/len(per) if per else 0.0
    idx = {lbl:i for i,lbl in enumerate(labels)}
    mat = [[0]*len(labels) for _ in range(len(labels))]
    for t,p in zip(y_true,y_pred):
        if t in idx and p in idx: mat[idx[t]][idx[p]] += 1
    return {"accuracy":round(correct/n,4),"macro_p":round(mp,4),"macro_r":round(mr,4),
            "macro_f1":round(mf,4),"per_class":per,"cm_labels":labels,"cm_matrix":mat,
            "n_samples":n,"n_correct":correct}


def _seed_demo_runs(sym: str = "SPY") -> None:
    """Write 3 demo self-check records (source=demo_self_check). NOT production accuracy."""
    demo = [
        {"symbol":sym,"ai_decision":"BUY", "actual_label":"BUY", "correct":True, "ai_confidence":72,"actual_return_pct":4.2, "source":"demo_self_check","timestamp":"2024-01-15"},
        {"symbol":sym,"ai_decision":"HOLD","actual_label":"HOLD","correct":True, "ai_confidence":58,"actual_return_pct":0.8, "source":"demo_self_check","timestamp":"2024-02-12"},
        {"symbol":sym,"ai_decision":"BUY", "actual_label":"HOLD","correct":False,"ai_confidence":61,"actual_return_pct":1.1, "source":"demo_self_check","timestamp":"2024-03-08"},
    ]
    try:
        with open(RUNS_FILE, "w", encoding="utf-8") as fh:
            for r in demo: fh.write(json.dumps(r)+"\n")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# RENDER HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _dv_cls(d: str) -> str:
    return {"BUY":"dv-buy","SELL":"dv-sell","HOLD":"dv-hold"}.get(d,"dv-rev")

def _dv_color(d: str) -> str:
    return {"BUY":"#00875A","SELL":"#DF1B41","HOLD":"#F59E0B",
            "MATCH":"#00875A","CONFLICT":"#DF1B41","PARTIAL":"#F59E0B"}.get(d,"#6B7280")

def _sec(title: str) -> None:
    st.markdown(f'<div class="sec-hd">{title}</div>', unsafe_allow_html=True)

def _mrow(pairs: list) -> None:
    """Row of st.metric() cards. Time O(p), Space O(p)."""
    cols = st.columns(len(pairs))
    for col,(lbl,val) in zip(cols,pairs):
        col.metric(lbl, str(val) if val not in (None,"") else "—")

def _hr() -> None:
    st.markdown("<hr class='af-hr'>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# BACKTEST COLUMN RENDER
# ══════════════════════════════════════════════════════════════════════════════
def _render_bt_col(bt_res: dict, capital: float) -> None:
    """Render tastytrade backtest results. Time O(1), Space O(1)."""
    st.markdown(
        '<div class="col-hdr">'
        '<div class="col-hdr-t">BACKTESTING RESULTS</div>'
        '<div class="col-hdr-s">tastytrade Backtester API · equity-option payload</div>'
        '</div>', unsafe_allow_html=True)

    if not bt_res:
        st.caption("Click the run button to see backtest results.")
        return

    if not bt_res.get("passed_validation"):
        status_code = bt_res.get("status","ERROR")
        msg         = bt_res.get("message","Validation failed.")
        if status_code == "MISSING_CREDENTIALS":
            st.error(msg)
        else:
            st.error(f"Backtest failed ({status_code}): {msg}")
            lt = bt_res.get("leg_type")
            if lt: st.caption(f"Leg type returned by API: {lt}")
        return

    d    = _bt_decision(bt_res)
    wr   = float(bt_res.get("win_rate") or 0)
    tpl  = float(bt_res.get("total_profit_loss") or 0)
    fc   = capital + tpl
    ret  = (tpl/capital*100) if capital else 0
    avpl = bt_res.get("average_profit_loss")
    sr   = bt_res.get("sharpe_ratio")
    mp_  = bt_res.get("max_profit")
    ml_  = bt_res.get("max_loss")
    nt   = bt_res.get("num_trades")
    nw   = bt_res.get("num_wins")
    nl   = bt_res.get("num_losses")
    bid  = str(bt_res.get("backtest_id") or "")

    st.markdown(
        f'<div class="{_dv_cls(d)}">{d}</div>'
        f'<span class="vbadge-ok">✓ Validation PASSED</span>'
        +(f'<br><span style="font-size:.63rem;color:#94A3B8;">ID: {bid[:22]}</span>' if bid else ""),
        unsafe_allow_html=True)
    st.markdown("")

    _mrow([("Initial Capital",f"${capital:,.0f}"),("Final Capital",f"${fc:,.0f}"),("Total P&L",f"${tpl:,.0f}")])
    _mrow([("Total Return",f"{ret:.1f}%"),("Win Rate",f"{wr*100:.1f}%"),("Trade Count",str(nt) if nt else "—")])
    _mrow([("Wins",str(nw) if nw else "—"),("Losses",str(nl) if nl else "—"),("Avg P&L/Trade",f"${float(avpl):,.0f}" if avpl is not None else "—")])
    _mrow([("Sharpe Ratio",f"{float(sr):.2f}" if sr is not None else "—"),("Max Profit",f"${float(mp_):,.0f}" if mp_ is not None else "—"),("Max Loss",f"${float(ml_):,.0f}" if ml_ is not None else "—")])
    _mrow([("CAGR","Not available"),("Alpha","Not available"),("Max Drawdown","Not available")])
    st.caption(f"Trials: {bt_res.get('num_trials',0)}  |  CAGR/Alpha/Beta/Drawdown not returned by tastytrade API.")


# ══════════════════════════════════════════════════════════════════════════════
# AI AGENTS COLUMN RENDER
# ══════════════════════════════════════════════════════════════════════════════
def _render_ai_col(ai_res: dict, capital: float) -> None:
    """Render AI agent prediction results. Time O(1), Space O(1)."""
    st.markdown(
        '<div class="col-hdr">'
        '<div class="col-hdr-t">AI AGENTS PREDICTION</div>'
        '<div class="col-hdr-s">AI Agent Engine · 6 intelligence engines</div>'
        '</div>', unsafe_allow_html=True)

    if not ai_res:
        st.caption("Click the run button to see AI agent results.")
        return

    if ai_res.get("status") != "SUCCESS":
        st.error(f"AI agents failed: {ai_res.get('message','Unknown error')}")
        return

    d      = _ai_decision(ai_res)
    intel  = ai_res.get("intelligence") or {}
    verd   = intel.get("verdict") or {}
    conf_o = intel.get("confidence") or {}
    scores = intel.get("scores") or {}
    score  = int(verd.get("score") or 0)
    conf   = int(conf_o.get("score") or 0)

    def _sc(eng: str) -> str:
        v = (scores.get(eng) or {}).get("score")
        return f"{int(v)}/100" if v is not None else "—"

    st.markdown(
        f'<div class="{_dv_cls(d)}">{d}</div>'
        f'<span style="font-size:.72rem;color:#635BFF;font-weight:600;">Score: {score}/100 · Confidence: {conf}/100</span>',
        unsafe_allow_html=True)
    st.markdown("")

    _mrow([("Initial Capital",f"${capital:,.0f}"),("Expected Final","Not estimated"),("Expected P&L","Not estimated")])
    _mrow([("Expected Return","Not estimated"),("Composite Score",f"{score}/100"),("Confidence",f"{conf}/100")])
    _mrow([("Fundamental",_sc("fundamental")),("Technical",_sc("technical")),("Valuation",_sc("valuation"))])
    _mrow([("Macro",_sc("macro")),("Sentiment",_sc("sentiment")),("Risk Score",_sc("risk"))])
    _mrow([("Win Probability","Not estimated"),("Expected Drawdown","Not estimated"),("Expected Sharpe","Not estimated")])
    st.caption(f"Initial Capital: ${capital:,.0f}  |  AI agents run independently — do not copy backtest P&L into AI estimates.")


# ══════════════════════════════════════════════════════════════════════════════
# FINAL DECISION BOARD
# ══════════════════════════════════════════════════════════════════════════════
def _render_final_decision(bt_d: str, ai_d: str, cmp: dict) -> None:
    """Four decision cards. Time O(1), Space O(1)."""
    cards = [("Backtest Decision",bt_d or "—"),("AI Agent Decision",ai_d or "—"),
             ("Agreement",cmp["agreement"]),("Final Decision",cmp["final"])]
    cols = st.columns(4)
    for col,(lbl,val) in zip(cols,cards):
        col.markdown(
            f'<div class="fdb-card"><div class="fdb-lbl">{lbl}</div>'
            f'<div class="fdb-val" style="color:{_dv_color(val)};">{val}</div></div>',
            unsafe_allow_html=True)
    msg = cmp.get("msg","")
    if msg:
        agr = cmp["agreement"]
        if agr=="MATCH":    st.success(msg)
        elif agr=="CONFLICT": st.error(msg)
        else:               st.warning(msg)


# ══════════════════════════════════════════════════════════════════════════════
# ACCURACY SECTION
# ══════════════════════════════════════════════════════════════════════════════
def _render_accuracy(sym: str) -> None:
    """Accuracy / Precision / Recall / F1 / Confusion Matrix."""
    records  = _load_runs()
    prod_rec = [r for r in records if r.get("source") != "demo_self_check"]
    working  = prod_rec if prod_rec else records

    if len(working) < 2:
        _mrow([("Accuracy","Needs data"),("Precision","Needs data"),("Recall","Needs data"),("F1 Score","Needs data")])
        st.info(
            f"Accuracy metrics require at least 2 historical evaluation samples. "
            f"Current samples: {len(records)}.  "
            "Run rolling evaluation to generate scores.")
        if st.button("Run Quick Evaluation Self-Check", key="acc_demo_btn"):
            _seed_demo_runs(sym)
            st.rerun()
        return

    y_true = [r["actual_label"] for r in working if r.get("actual_label") and r.get("ai_decision")]
    y_pred = [r["ai_decision"]  for r in working if r.get("actual_label") and r.get("ai_decision")]

    if not prod_rec:
        st.warning("Showing demo self-check records only. NOT production model accuracy.")

    if len(y_true) < 2:
        st.info(f"Insufficient labelled records ({len(y_true)}). Need >= 2.")
        return

    m = _compute_accuracy(y_true, y_pred)
    if "error" in m:
        st.warning(m["error"]); return

    _mrow([("Accuracy",f"{m['accuracy']*100:.1f}%"),("Macro Precision",f"{m['macro_p']*100:.1f}%"),
           ("Macro Recall",f"{m['macro_r']*100:.1f}%"),("Macro F1",f"{m['macro_f1']*100:.1f}%")])
    st.caption(f"{'Production' if prod_rec else 'Demo'} · {m['n_samples']} samples · {m['n_correct']}/{m['n_samples']} correct.")

    pc = m.get("per_class") or {}
    if pc:
        st.dataframe(
            [{"Class":k,"Precision":f"{v['precision']*100:.1f}%","Recall":f"{v['recall']*100:.1f}%",
              "F1":f"{v['f1']*100:.1f}%","Support":v["support"]} for k,v in pc.items()],
            use_container_width=True, hide_index=True)

    lbls = m.get("cm_labels",[])
    mat  = m.get("cm_matrix",[])
    if lbls and mat:
        try:
            import plotly.graph_objects as go
            fig = go.Figure(go.Heatmap(z=mat,x=lbls,y=lbls,colorscale="Blues",
                                       text=mat,texttemplate="%{text}",showscale=True))
            fig.update_layout(title="Confusion Matrix (AI Predictions vs Actual)",
                              height=260,margin=dict(l=10,r=10,t=36,b=10),
                              xaxis_title="Predicted",yaxis_title="Actual")
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.dataframe({"Label":lbls,**{lbl:[mat[i][j] for i in range(len(lbls))] for j,lbl in enumerate(lbls)}})


# ══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════════════════════════════
def _render_charts(bt_res: dict, ai_res: dict) -> None:
    """P/L curve + AI factor bar chart. Graceful if data missing."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.caption("Install plotly for charts.")
        return

    trial_rows = (bt_res or {}).get("trial_rows") or []
    if trial_rows:
        dates = [r.get("exit_date") or r.get("entry_date","") for r in trial_rows]
        cumpl = []
        total = 0.0
        for r in trial_rows:
            total += float(r.get("profit_loss",0))
            cumpl.append(total)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates,y=cumpl,mode="lines",name="Cumulative P&L",
                                 line=dict(color="#635BFF",width=2)))
        fig.update_layout(title="tastytrade — Cumulative P&L Curve",height=240,
                          margin=dict(l=10,r=10,t=36,b=10),
                          xaxis_title="Exit Date",yaxis_title="Cumulative P&L ($)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("No trial data for P&L chart.")

    if ai_res and ai_res.get("status") == "SUCCESS":
        scores  = ((ai_res.get("intelligence") or {}).get("scores") or {})
        engines = ["fundamental","technical","valuation","macro","sentiment","risk"]
        vals    = [int((scores.get(e) or {}).get("score") or 0) for e in engines]
        colors  = ["#635BFF","#0EA5E9","#10B981","#F59E0B","#EF4444","#6B7280"]
        fig = go.Figure(go.Bar(x=engines,y=vals,marker_color=colors))
        fig.update_layout(title="AI Agent — Factor Score Breakdown",height=240,
                          margin=dict(l=10,r=10,t=36,b=10),yaxis=dict(range=[0,100]))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("AI factor chart not available.")


# ══════════════════════════════════════════════════════════════════════════════
# DEVELOPER DEBUG EXPANDERS  — never expose token values
# ══════════════════════════════════════════════════════════════════════════════
def _render_debug(bt_res: dict, ai_res: dict) -> None:
    with st.expander("Developer Debug: Environment Status"):
        st.json({
            "GOOGLE_API_KEY present":           bool(os.getenv("GOOGLE_API_KEY","").strip() or os.getenv("GEMINI_API_KEY","").strip()),
            "RAPIDAPI_KEY present":             bool(os.getenv("RAPIDAPI_KEY","").strip()),
            "TASTYTRADE_CLIENT_SECRET present":  bool(os.getenv("TASTYTRADE_CLIENT_SECRET","").strip()),
            "TASTYTRADE_REFRESH_TOKEN present":  bool(os.getenv("TASTYTRADE_REFRESH_TOKEN","").strip()),
            "TASTYTRADE_ACCESS_TOKEN present":   bool(os.getenv("TASTYTRADE_ACCESS_TOKEN","").strip()),
            ".env path": str(ROOT / ".env"),
            ".env exists": (ROOT / ".env").exists(),
        })
    if bt_res:
        with st.expander("Developer Debug: Backtest Raw Response"):
            safe = {k:v for k,v in bt_res.items() if k != "trial_rows"}
            st.json(safe)
            rows = bt_res.get("trial_rows") or []
            if rows: st.caption(f"trial_rows: {len(rows)} rows — first 5:"); st.json(rows[:5])
    if ai_res:
        with st.expander("Developer Debug: AI Raw Response"):
            st.json(ai_res)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    status = _status()

    pills = (_pill("Google AI", status["google"])
             + _pill("RapidAPI",   status["rapidapi"])
             + _pill("Tastytrade", status["tastytrade"])
             + _pill("Backtesting",status["backtesting"]))

    st.markdown(
        f'<div class="sys-title">AI FINANCIAL ANALYST SYSTEM</div>'
        f'<div class="sys-sub">Backtesting vs AI Agent Intelligence</div>'
        f'<div style="margin-top:.45rem;">{pills}</div>',
        unsafe_allow_html=True)
    st.markdown("<hr class='af-hr'>", unsafe_allow_html=True)

    if not status["tastytrade"]:
        st.error(
            "Tastytrade credentials are missing — backtesting cannot run.  "
            "Add TASTYTRADE_REFRESH_TOKEN and TASTYTRADE_CLIENT_SECRET to your .env file.")

    with st.expander("Backtest Configuration", expanded=True):
        c1,c2,c3,c4 = st.columns(4)
        with c1: symbol  = st.text_input("Symbol",           value="SPY",        key="sym")
        with c2: start   = st.text_input("Start Date",       value="2021-06-25", key="start")
        with c3: end     = st.text_input("End Date",         value=str(date.today()), key="end")
        with c4: capital = st.number_input("Initial Capital ($)",value=100_000,
                                           min_value=1_000,step=10_000,format="%d",key="cap")
        st.markdown("**Options Strategy Parameters**")
        oc1,oc2,oc3,oc4,oc5 = st.columns(5)
        with oc1: direction = st.selectbox("Direction",["short","long"],key="dir")
        with oc2: side      = st.selectbox("Side",["put","call"],key="side")
        with oc3: dte       = st.number_input("DTE",  value=45,min_value=1,max_value=365,key="dte")
        with oc4: delta     = st.number_input("Delta",value=30,min_value=1,max_value=99, key="dlt")
        with oc5: num_legs  = st.selectbox("Legs",[1,2,3,4],index=1,key="legs")

    sym = (symbol or "SPY").strip().upper()
    cap = float(capital)

    run = st.button("RUN BACKTEST + AI AGENT COMPARISON",
                    type="primary", use_container_width=True, key="run_btn")

    if run:
        with st.spinner(f"Running tastytrade backtest for {sym}…"):
            st.session_state["last_backtest_result"] = _run_tastytrade(
                sym, start, end, direction, side, int(dte), int(delta), int(num_legs))
        with st.spinner(f"Running AI agents for {sym}…"):
            st.session_state["last_ai_result"] = _run_ai(sym)

    bt_res = st.session_state.get("last_backtest_result")
    ai_res = st.session_state.get("last_ai_result")

    if not bt_res and not ai_res:
        st.markdown("<hr class='af-hr'>", unsafe_allow_html=True)
        st.info("Configure parameters above and click **RUN BACKTEST + AI AGENT COMPARISON**.")
        return

    st.markdown("<hr class='af-hr'>", unsafe_allow_html=True)
    st.markdown('<div class="sec-hd">1. Backtesting Results vs AI Agents Prediction</div>', unsafe_allow_html=True)
    col_bt, col_ai = st.columns(2)
    with col_bt: _render_bt_col(bt_res or {}, cap)
    with col_ai: _render_ai_col(ai_res or {}, cap)

    st.markdown("<hr class='af-hr'>", unsafe_allow_html=True)
    st.markdown('<div class="sec-hd">2. Final Decision Board</div>', unsafe_allow_html=True)
    bt_d = _bt_decision(bt_res or {})
    ai_d = _ai_decision(ai_res or {})
    cmp  = _compare(bt_d, ai_d, bt_res or {}, ai_res or {})
    _render_final_decision(bt_d, ai_d, cmp)

    st.markdown("<hr class='af-hr'>", unsafe_allow_html=True)
    st.markdown('<div class="sec-hd">3. Accuracy Metrics</div>', unsafe_allow_html=True)
    _render_accuracy(sym)

    st.markdown("<hr class='af-hr'>", unsafe_allow_html=True)
    st.markdown('<div class="sec-hd">4. Charts</div>', unsafe_allow_html=True)
    _render_charts(bt_res or {}, ai_res or {})

    st.markdown("<hr class='af-hr'>", unsafe_allow_html=True)
    _render_debug(bt_res, ai_res)


if __name__ == "__main__":
    main()
'''

with open(APP, "w", encoding="utf-8") as fh:
    fh.write(NEW)

print("Written", NEW.count("\n") + 1, "lines to", APP)
