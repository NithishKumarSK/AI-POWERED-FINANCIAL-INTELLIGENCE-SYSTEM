"""
AI Financial Analyst System
Single-page institutional terminal. Options Backtesting vs AI Agent Intelligence.
No sidebar. No navigation. No fake data. No personal names. No live trades.
"""
from __future__ import annotations

import os, sys, json, time, math
from pathlib import Path
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))
sys.path.insert(2, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

import requests
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

RUNS_FILE        = ROOT / "ai_agent_evaluation_runs.jsonl"
_TT_BACK_URL     = os.getenv("TASTYTRADE_BACKTESTER_BASE_URL", "https://backtester.vast.tastyworks.com")
_TT_API_URL      = os.getenv("TASTYTRADE_API_BASE_URL",        "https://api.tastyworks.com")
_TT_USER_AGENT   = os.getenv("TASTYTRADE_USER_AGENT",          "ajay-ai-finance/1.0")

# ══════════════════════════════════════════════════════════════════════════════
# CSS — institutional terminal style
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""<style>
.stApp{background:#F6F9FC;}
.block-container{padding-top:.8rem!important;padding-bottom:2rem!important;max-width:1340px;}
/* Header */
.sys-hdr{background:#fff;border:1px solid #E3E8EE;border-radius:8px;
         padding:.7rem 1rem .6rem;margin-bottom:.8rem;
         box-shadow:0 1px 4px rgba(10,37,64,.06);}
.sys-title{font-size:1.3rem;font-weight:800;color:#0A2540;letter-spacing:-.02em;}
.sys-sub{font-size:.72rem;color:#425466;margin-top:.1rem;}
/* Status pills */
.pill{display:inline-block;font-size:.64rem;font-weight:700;
      padding:.16rem .55rem;border-radius:20px;margin:.15rem .2rem 0 0;}
.pill-ok{background:#D1FAE5;color:#065F46;}
.pill-err{background:#FEE2E2;color:#991B1B;}
.pill-warn{background:#FEF3C7;color:#92400E;}
/* Section headers */
.sec-hd{font-size:.8rem;font-weight:700;color:#0A2540;
        border-left:3px solid #635BFF;padding:.1rem .55rem;
        margin:.9rem 0 .5rem;letter-spacing:.01em;}
/* Column header card */
.col-hdr{background:#fff;border:1px solid #E3E8EE;border-radius:6px;
         padding:.6rem .85rem .5rem;margin-bottom:.5rem;
         box-shadow:0 1px 3px rgba(10,37,64,.04);}
.col-hdr-t{font-size:.68rem;font-weight:700;color:#0A2540;
           text-transform:uppercase;letter-spacing:.08em;}
.col-hdr-s{font-size:.61rem;color:#94A3B8;margin-top:.07rem;}
/* Decision badge */
.dv-buy {font-size:2.1rem;font-weight:900;color:#00875A;line-height:1.1;}
.dv-sell{font-size:2.1rem;font-weight:900;color:#DF1B41;line-height:1.1;}
.dv-hold{font-size:2.1rem;font-weight:900;color:#F59E0B;line-height:1.1;}
.dv-rev {font-size:2.1rem;font-weight:900;color:#6B7280;line-height:1.1;}
/* Final decision board cards */
.fdb-card{text-align:center;padding:.85rem .4rem;background:#fff;
          border:1px solid #E3E8EE;border-radius:8px;
          box-shadow:0 1px 3px rgba(10,37,64,.04);}
.fdb-lbl{font-size:.6rem;font-weight:700;color:#425466;
         text-transform:uppercase;letter-spacing:.07em;}
.fdb-val{font-size:1.8rem;font-weight:900;margin-top:.18rem;}
/* Badges */
.vbadge-ok {font-size:.65rem;color:#00875A;font-weight:600;}
.vbadge-err{font-size:.65rem;color:#DF1B41;font-weight:600;}
.vbadge-warn{font-size:.65rem;color:#F59E0B;font-weight:600;}
/* HR */
.af-hr{border:none;border-top:1px solid #E3E8EE;margin:.85rem 0;}
</style>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# RUNTIME STATUS
# ══════════════════════════════════════════════════════════════════════════════
def _status() -> dict:
    google = bool(os.getenv("GOOGLE_API_KEY","").strip() or os.getenv("GEMINI_API_KEY","").strip())
    rapid  = bool(os.getenv("RAPIDAPI_KEY","").strip()) and os.getenv("RAPIDAPI_KEY","") != "mock-key-for-testing"
    tt_cs  = bool(os.getenv("TASTYTRADE_CLIENT_SECRET","").strip())
    tt_rt  = bool(os.getenv("TASTYTRADE_REFRESH_TOKEN","").strip())
    tt     = tt_cs and tt_rt
    return dict(google=google, rapidapi=rapid, tastytrade=tt, backtesting=tt)


def _pill(label: str, ok: bool, warn: bool = False) -> str:
    cls = "pill-warn" if warn else ("pill-ok" if ok else "pill-err")
    sym = "⚠" if warn else ("✔" if ok else "✘")
    return f'<span class="pill {cls}">{sym} {label}</span>'


# ══════════════════════════════════════════════════════════════════════════════
# DIRECT TASTYTRADE API — bypass wrapper for better response extraction
# ══════════════════════════════════════════════════════════════════════════════
def _fmt_bearer(token: str) -> str:
    """Ensure 'Bearer ' prefix. Never logged. Time O(1)."""
    if not token: return ""
    t = token.strip()
    return t if t.startswith("Bearer ") else f"Bearer {t}"


def _tt_refresh() -> Tuple[str, str]:
    """Exchange refresh token for new access token via form-encoded OAuth."""
    rt = os.getenv("TASTYTRADE_REFRESH_TOKEN","").strip()
    cs = os.getenv("TASTYTRADE_CLIENT_SECRET","").strip()
    if not rt: return "", "TASTYTRADE_REFRESH_TOKEN not set in .env"
    if not cs: return "", "TASTYTRADE_CLIENT_SECRET not set in .env"
    url     = f"{_TT_API_URL}/oauth/token"
    payload = {"grant_type": "refresh_token", "refresh_token": rt, "client_secret": cs}
    headers = {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": _TT_USER_AGENT}
    try:
        resp = requests.post(url, data=payload, headers=headers, timeout=20)
        if resp.status_code == 200:
            data  = resp.json()
            token = data.get("access_token") or (data.get("data") or {}).get("access-token","")
            if token: return token.strip(), ""
            return "", "OAuth OK but access_token missing from response."
        return "", f"OAuth failed: HTTP {resp.status_code}"
    except Exception as exc:
        return "", f"OAuth error: {type(exc).__name__}"


def _tt_token() -> Tuple[str, str]:
    """Get valid access token: env first, then refresh. Returns (token, error)."""
    at = os.getenv("TASTYTRADE_ACCESS_TOKEN","").strip()
    if at: return at, ""
    return _tt_refresh()


def _tt_headers(token: str) -> dict:
    return {"Authorization": _fmt_bearer(token),
            "Content-Type": "application/json",
            "User-Agent": _TT_USER_AGENT}


def _tt_build_payload(sym: str, start: str, end: str,
                      direction: str, side: str,
                      dte: int, delta: int, num_legs: int,
                      frequency: str = "every day") -> dict:
    """Verified equity-option payload. Time O(k), Space O(k). k=num_legs.
    Same-side legs MUST have different expirations (>=5 day gap) or API returns 400.
    Fix: offset each leg DTE by +5 days.
    """
    end_iso = end if "T" in str(end) else f"{end}T00:00:00Z"
    legs = []
    for i in range(int(num_legs)):
        legs.append({
            "type": "equity-option",        # MUST be equity-option
            "direction": direction,          # MUST be short or long
            "quantity": 1,
            "side": side,
            "daysUntilExpiration": int(dte) + (i * 5),  # +5 per leg avoids same-expiry 400
            "strikeSelection": "delta",
            "delta": int(delta),
        })
    return {
        "startDate": start,
        "endDate":   end_iso,
        "symbol":    sym.upper(),
        "status":    "pending",
        "entryConditions": {"frequency": frequency},
        "exitConditions":  {},
        "legs": legs,
    }


def _tt_create(payload: dict, token: str) -> Tuple[str, str]:
    """POST /backtests. Returns (backtest_id, error)."""
    url = f"{_TT_BACK_URL}/backtests"
    try:
        resp = requests.post(url, json=payload, headers=_tt_headers(token), timeout=30)
        if resp.status_code in (200, 201):
            data = resp.json()
            bid  = (data.get("id") or data.get("backtestId") or
                    (data.get("data") or {}).get("id",""))
            if bid: return str(bid), ""
            return "", "Backtest created but no ID in response."
        return "", f"Create failed: HTTP {resp.status_code} — {resp.text[:200]}"
    except Exception as exc:
        return "", f"Create error: {type(exc).__name__}"


def _tt_poll(bid: str, token: str, timeout: int = 180, interval: int = 5) -> Tuple[dict, str]:
    """Poll GET /backtests/{id} until complete or timeout. Time O(timeout/interval)."""
    url      = f"{_TT_BACK_URL}/backtests/{bid}"
    deadline = time.time() + timeout
    last_status = ""
    while time.time() < deadline:
        try:
            resp = requests.get(url, headers=_tt_headers(token), timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                st_  = str(data.get("status","")).lower()
                last_status = st_
                if st_ in ("complete","completed","success","done","finished"):
                    return data, ""
                if st_ in ("error","failed","failure","cancelled"):
                    return {}, f"Backtest ended with status='{st_}'."
        except Exception:
            pass
        time.sleep(interval)
    return {}, f"Timed out after {timeout}s (last status='{last_status}')."


def _tt_extract(data: dict) -> dict:
    """
    Extract statistics/trials from raw response.
    Tries multiple key paths because API nesting varies. Time O(1).
    """
    result = data.get("results") or data.get("result") or data.get("data") or {}
    if not isinstance(result, dict): result = {}

    stats = (result.get("statistics") or result.get("stats") or
             data.get("statistics")   or data.get("stats"))

    trials = (result.get("trials")      or result.get("snapshots")    or
              result.get("tradeHistory") or result.get("trades")       or
              data.get("trials")        or data.get("snapshots")       or [])
    if not isinstance(trials, list): trials = []

    legs     = result.get("legs") or data.get("legs") or []
    leg_type = "unknown"
    if legs and isinstance(legs, list) and isinstance(legs[0], dict):
        leg_type = legs[0].get("type","unknown")

    return {
        "statistics": stats,
        "trials":     trials,
        "leg_type":   leg_type,
        "symbol":     data.get("symbol","") or result.get("symbol",""),
        "status":     data.get("status",""),
    }


def _tt_validate(ex: dict) -> Tuple[bool, List[str]]:
    """Strict validation — never pass on fake/incomplete data."""
    reasons = []
    if ex["leg_type"] == "unknown":
        reasons.append("leg_type='unknown' — payload must use type='equity-option'.")
    if not ex["statistics"]:
        reasons.append("statistics=null — backtester returned no statistics.")
    if not ex["trials"]:
        reasons.append("trials=null/empty — no trial data returned.")
    else:
        pls = []
        for t in ex["trials"]:
            if isinstance(t, dict):
                pl = t.get("profitLoss") or t.get("profit_loss") or t.get("pl") or 0
                try: pls.append(float(pl))
                except: pass
        if pls and all(abs(p) < 0.0001 for p in pls):
            reasons.append("All profitLoss=0 — misconfigured payload or API error.")
    return len(reasons) == 0, reasons


def _tt_normalize(bid: str, ex: dict, initial_capital: float) -> dict:
    """Compute final metric dict from extracted data. Time O(m). m=num_trials."""
    stats  = ex["statistics"] or {}
    trials = ex["trials"]

    # Total P/L
    tpl = (stats.get("totalProfitLoss") or stats.get("total_profit_loss") or
           stats.get("netProfitLoss")   or stats.get("totalReturn"))
    if tpl is None and trials:
        pls = []
        for t in trials:
            if isinstance(t, dict):
                pl = t.get("profitLoss") or t.get("profit_loss") or t.get("pl") or 0
                try: pls.append(float(pl))
                except: pass
        if pls: tpl = sum(pls)
    tpl_f = float(tpl) if tpl is not None else 0.0

    # Win rate
    wr = stats.get("winRate") or stats.get("win_rate")
    if wr is None and trials:
        pls2 = []
        for t in trials:
            if isinstance(t, dict):
                pl = t.get("profitLoss") or t.get("profit_loss") or 0
                try: pls2.append(float(pl))
                except: pass
        if pls2: wr = sum(1 for p in pls2 if p > 0) / len(pls2)

    # Counts
    num_trades = len(trials)
    nt2 = stats.get("numTrades") or stats.get("num_trades") or stats.get("tradeCount")
    if nt2: num_trades = int(nt2)

    num_wins   = stats.get("numWins")   or stats.get("num_wins")
    num_losses = stats.get("numLosses") or stats.get("num_losses")

    avg_pl = (stats.get("averageProfitLoss") or stats.get("average_profit_loss") or
              stats.get("avgProfitLoss"))
    if avg_pl is None and tpl_f and num_trades:
        avg_pl = tpl_f / num_trades

    sharpe     = stats.get("sharpeRatio")  or stats.get("sharpe_ratio")
    max_profit = stats.get("maxProfit")    or stats.get("max_profit")
    max_loss   = stats.get("maxLoss")      or stats.get("max_loss")

    trial_rows = []
    for t in trials[:500]:
        if isinstance(t, dict):
            trial_rows.append({
                "entry_date": t.get("entryDate") or t.get("entry_date",""),
                "exit_date":  t.get("exitDate")  or t.get("exit_date",""),
                "profit_loss": float(t.get("profitLoss") or t.get("profit_loss") or 0),
            })

    fc  = initial_capital + tpl_f
    ret = (tpl_f / initial_capital * 100) if initial_capital else 0.0

    return {
        "backtest_id":        bid,
        "symbol":             ex["symbol"],
        "status":             "SUCCESS",
        "leg_type":           ex["leg_type"],
        "passed_validation":  True,
        "total_profit_loss":  tpl_f,
        "final_capital":      fc,
        "total_return_pct":   ret,
        "win_rate":           float(wr)  if wr  is not None else None,
        "num_trades":         num_trades,
        "num_wins":           int(num_wins)   if num_wins   is not None else None,
        "num_losses":         int(num_losses) if num_losses is not None else None,
        "average_profit_loss":float(avg_pl)   if avg_pl     is not None else None,
        "sharpe_ratio":       float(sharpe)   if sharpe     is not None else None,
        "max_profit":         float(max_profit) if max_profit is not None else None,
        "max_loss":           float(max_loss)   if max_loss   is not None else None,
        "trial_rows":         trial_rows,
    }


def run_tastytrade_backtest(sym: str, start: str, end: str,
                             direction: str, side: str,
                             dte: int, delta: int, num_legs: int,
                             frequency: str, initial_capital: float) -> dict:
    """
    Full flow: token → payload → create → poll → extract → validate → normalize.
    Retries once with verified dates if statistics/trials null.
    Time O(poll_time), Space O(m).
    """
    token, err = _tt_token()
    if not token:
        return {"status": "ERROR", "message": f"Authentication failed: {err}",
                "passed_validation": False}

    def _once(s: str, e: str) -> dict:
        payload     = _tt_build_payload(sym, s, e, direction, side, dte, delta, num_legs, frequency)
        bid, err2   = _tt_create(payload, token)
        if not bid:
            return {"status": "ERROR", "message": err2, "passed_validation": False}
        data, err3  = _tt_poll(bid, token, timeout=180, interval=5)
        if not data:
            return {"status": "ERROR", "message": err3,
                    "backtest_id": bid, "passed_validation": False}
        ex              = _tt_extract(data)
        passed, reasons = _tt_validate(ex)
        if not passed:
            return {"status": "VALIDATION_FAILED",
                    "message": "; ".join(reasons),
                    "backtest_id": bid, "passed_validation": False,
                    "leg_type": ex["leg_type"],
                    "_raw": data, "_extracted": ex}
        result = _tt_normalize(bid, ex, initial_capital)
        return result

    result = _once(start, end)

    # Retry once with verified dates if statistics/trials null
    if not result.get("passed_validation"):
        msg = result.get("message","").lower()
        if "statistics=null" in msg or "trials=null" in msg:
            retry = _once("2021-06-25", "2026-06-24")
            if retry.get("passed_validation"):
                retry["_retried"] = True
                return retry

    return result


# ══════════════════════════════════════════════════════════════════════════════
# AI AGENT ENGINE
# ══════════════════════════════════════════════════════════════════════════════
def _ai_has_data(ai_res: dict) -> bool:
    """True when at least one engine produced a non-zero score."""
    if not ai_res or ai_res.get("status") != "SUCCESS": return False
    scores = (ai_res.get("intelligence") or {}).get("scores") or {}
    return any((scores.get(e) or {}).get("score", 0) != 0
               for e in ["fundamental","technical","valuation","risk","macro","sentiment"])


def run_ai_agents(sym: str) -> dict:
    """Run StockAnalysisAgent independently. Time O(engine_time)."""
    if not _AGENT_OK:
        return {"status": "ERROR", "message": "stock_analysis_agent module not found."}
    try:
        if "agent" not in st.session_state:
            st.session_state["agent"] = StockAnalysisAgent()
        return st.session_state["agent"].analyze_stock(sym)
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


def _ai_decision(ai_res: dict) -> str:
    """BUY/SELL/HOLD/REVIEW from agent result. Uses verdict first, then score composite."""
    if not ai_res or ai_res.get("status") != "SUCCESS": return "REVIEW"
    intel = ai_res.get("intelligence") or {}
    verd  = intel.get("verdict") or {}
    # Use verdict.value directly — Gemini may return HOLD even when market data is unavailable
    val = (verd.get("value") or verd.get("decision") or "").upper()
    if val in ("BUY","SELL","HOLD"): return val
    # Fallback: composite from engine scores if any are non-zero
    scores = intel.get("scores") or {}
    eng_sc = [(scores.get(e) or {}).get("score", 0)
              for e in ["fundamental","technical","valuation","sentiment","macro"]]
    risk   = (scores.get("risk") or {}).get("score", 0)
    valid  = [s for s in eng_sc if s != 0]
    if not valid: return "REVIEW"
    composite = sum(valid) / len(valid) - risk * 0.10
    if composite >= 67: return "BUY"
    if composite <= 33: return "SELL"
    return "HOLD"


def _bt_decision(bt_res: dict) -> str:
    """BUY/SELL/HOLD/REVIEW from backtest result. Time O(1)."""
    if not bt_res or not bt_res.get("passed_validation"): return "REVIEW"
    wr  = float(bt_res.get("win_rate") or 0)
    tpl = float(bt_res.get("total_profit_loss") or 0)
    if tpl > 0 and wr >= 0.50: return "BUY"
    if tpl < 0 and wr < 0.40:  return "SELL"
    return "HOLD"


# ══════════════════════════════════════════════════════════════════════════════
# COMPARISON LOGIC
# ══════════════════════════════════════════════════════════════════════════════
def _compare(bt_d: str, ai_d: str, bt_res: dict, ai_res: dict) -> dict:
    """Agreement + final combined decision. Time O(1)."""
    bt_ok = bool(bt_res and bt_res.get("passed_validation"))
    ai_ok = bool(ai_res and ai_res.get("status") == "SUCCESS" and _ai_has_data(ai_res))
    if not bt_ok and not ai_ok:
        return {"agreement":"MISSING","final":"REVIEW",
                "msg":"Neither engine produced a valid result."}
    if not bt_ok:
        return {"agreement":"MISSING","final":ai_d,
                "msg":"Backtesting failed — showing AI decision only."}
    if not ai_ok:
        return {"agreement":"MISSING","final":bt_d,
                "msg":"AI agents had no data — showing backtest decision only."}
    if bt_d == ai_d:
        return {"agreement":"MATCH","final":bt_d,
                "msg":f"Both engines agree on {bt_d}. High-confidence signal."}
    if {bt_d,ai_d} == {"BUY","SELL"}:
        return {"agreement":"CONFLICT","final":"REVIEW",
                "msg":f"Engines conflict ({bt_d} vs {ai_d}). Manual review required."}
    final = "HOLD" if "HOLD" in {bt_d,ai_d} else "REVIEW"
    return {"agreement":"PARTIAL","final":final,
            "msg":f"Partial disagreement: backtest={bt_d}, AI={ai_d}. Proceed with caution."}


# ══════════════════════════════════════════════════════════════════════════════
# ACCURACY METRICS  Time O(N*C), Space O(C^2)
# ══════════════════════════════════════════════════════════════════════════════
def _load_runs() -> List[dict]:
    records: List[dict] = []
    if not RUNS_FILE.exists(): return records
    try:
        with open(RUNS_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try: records.append(json.loads(line))
                    except: pass
    except: pass
    return records


def _compute_accuracy(y_true: list, y_pred: list) -> dict:
    """Manual accuracy/precision/recall/F1/confusion matrix. No sklearn."""
    if not y_true or len(y_true) != len(y_pred) or len(y_true) < 2:
        return {"error": f"Need >= 2 samples, got {len(y_true)}"}
    labels  = sorted(set(y_true + y_pred))
    n       = len(y_true)
    correct = sum(t == p for t,p in zip(y_true, y_pred))
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
    for t,p in zip(y_true, y_pred):
        if t in idx and p in idx: mat[idx[t]][idx[p]] += 1
    return {"accuracy":round(correct/n,4),"macro_p":round(mp,4),
            "macro_r":round(mr,4),"macro_f1":round(mf,4),
            "per_class":per,"cm_labels":labels,"cm_matrix":mat,
            "n_samples":n,"n_correct":correct}


def _seed_demo(sym: str = "SPY") -> None:
    """Write 3 demo self-check records. NOT production accuracy."""
    demo = [
        {"symbol":sym,"ai_decision":"BUY", "actual_label":"BUY", "correct":True,
         "ai_confidence":72,"actual_return_pct":4.2,"source":"demo_self_check","timestamp":"2024-01-15"},
        {"symbol":sym,"ai_decision":"HOLD","actual_label":"HOLD","correct":True,
         "ai_confidence":58,"actual_return_pct":0.8,"source":"demo_self_check","timestamp":"2024-02-12"},
        {"symbol":sym,"ai_decision":"BUY", "actual_label":"HOLD","correct":False,
         "ai_confidence":61,"actual_return_pct":1.1,"source":"demo_self_check","timestamp":"2024-03-08"},
    ]
    try:
        with open(RUNS_FILE,"w",encoding="utf-8") as fh:
            for r in demo: fh.write(json.dumps(r)+"\n")
    except: pass


# ══════════════════════════════════════════════════════════════════════════════
# RENDER HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _dv_cls(d: str) -> str:
    return {"BUY":"dv-buy","SELL":"dv-sell","HOLD":"dv-hold"}.get(d,"dv-rev")

def _dv_color(d: str) -> str:
    return {"BUY":"#00875A","SELL":"#DF1B41","HOLD":"#F59E0B",
            "MATCH":"#00875A","CONFLICT":"#DF1B41","PARTIAL":"#F59E0B"}.get(d,"#6B7280")

def _hr():
    st.markdown("<hr class='af-hr'>", unsafe_allow_html=True)

def _sec(t: str):
    st.markdown(f'<div class="sec-hd">{t}</div>', unsafe_allow_html=True)

def _na(val) -> str:
    """Return formatted value or 'Not available'."""
    return str(val) if val not in (None,"") else "Not available"

def _ne(val) -> str:
    """Return formatted value or 'Not estimated'."""
    return str(val) if val not in (None,"") else "Not estimated"

def _mrow3(c1_lbl, c1_val, c2_lbl, c2_val, c3_lbl, c3_val):
    """3-column metric row."""
    cols = st.columns(3)
    cols[0].metric(c1_lbl, c1_val)
    cols[1].metric(c2_lbl, c2_val)
    cols[2].metric(c3_lbl, c3_val)

def _mrow2(c1_lbl, c1_val, c2_lbl, c2_val):
    cols = st.columns(2)
    cols[0].metric(c1_lbl, c1_val)
    cols[1].metric(c2_lbl, c2_val)


# ══════════════════════════════════════════════════════════════════════════════
# BACKTEST COLUMN
# ══════════════════════════════════════════════════════════════════════════════
def _render_bt_col(bt_res: dict, capital: float) -> None:
    """Render tastytrade backtest results. Time O(1)."""
    st.markdown(
        '<div class="col-hdr">'
        '<div class="col-hdr-t">BACKTESTING RESULTS</div>'
        '<div class="col-hdr-s">tastytrade Backtester API · equity-option · direct API</div>'
        '</div>', unsafe_allow_html=True)

    if not bt_res:
        st.info("Click the run button to start the backtest.")
        return

    if not bt_res.get("passed_validation"):
        code = bt_res.get("status","ERROR")
        msg  = bt_res.get("message","Validation failed.")
        if code == "ERROR" and "Auth" in msg:
            st.error(f"Authentication error: {msg}")
        else:
            st.error(f"Backtest failed ({code}): {msg}")
        lt = bt_res.get("leg_type")
        if lt: st.caption(f"Leg type returned by API: {lt}")
        return

    d    = _bt_decision(bt_res)
    tpl  = float(bt_res.get("total_profit_loss") or 0)
    fc   = float(bt_res.get("final_capital") or (capital + tpl))
    ret  = float(bt_res.get("total_return_pct") or (tpl/capital*100 if capital else 0))
    wr   = bt_res.get("win_rate")
    nt   = bt_res.get("num_trades")
    nw   = bt_res.get("num_wins")
    nl   = bt_res.get("num_losses")
    avg  = bt_res.get("average_profit_loss")
    sr   = bt_res.get("sharpe_ratio")
    mp   = bt_res.get("max_profit")
    ml   = bt_res.get("max_loss")
    bid  = str(bt_res.get("backtest_id",""))
    num_trials = bt_res.get("num_trials", len(bt_res.get("trial_rows",[])))

    retry_note = " · auto-retry" if bt_res.get("_retried") else ""
    st.markdown(
        f'<div class="{_dv_cls(d)}">{d}</div>'
        f'<span class="vbadge-ok">✓ Validation PASSED{retry_note}</span>'
        + (f'<br><span style="font-size:.6rem;color:#94A3B8">ID: {bid[:28]}</span>' if bid else ""),
        unsafe_allow_html=True)
    st.markdown("")

    # Row 1 — capital
    _mrow3("Initial Capital", f"${capital:,.0f}",
           "Final Capital",   f"${fc:,.0f}",
           "Total P&L",       f"${tpl:,.2f}")
    # Row 2 — performance
    _mrow3("Total Return",    f"{ret:.2f}%",
           "Win Rate",        f"{wr*100:.1f}%" if wr is not None else "Not available",
           "Trade Count",     str(nt) if nt is not None else "Not available")
    # Row 3 — trade stats
    _mrow3("Wins",            str(nw) if nw is not None else "Not available",
           "Losses",          str(nl) if nl is not None else "Not available",
           "Avg P&L / Trade", f"${float(avg):,.2f}" if avg is not None else "Not available")
    # Row 4 — risk
    _mrow3("Sharpe Ratio",    f"{float(sr):.2f}" if sr is not None else "Not available",
           "Max Profit",      f"${float(mp):,.2f}" if mp is not None else "Not available",
           "Max Loss",        f"${float(ml):,.2f}" if ml is not None else "Not available")
    # Row 5 — API limitations note
    _mrow2("Trials Used",     str(num_trials),
           "CAGR / Alpha / Beta / Drawdown", "Not returned by tastytrade API")


# ══════════════════════════════════════════════════════════════════════════════
# AI AGENTS COLUMN
# ══════════════════════════════════════════════════════════════════════════════
def _render_ai_col(ai_res: dict, capital: float) -> None:
    """Render AI agent prediction results. Shows all available scores. Time O(1)."""
    st.markdown(
        '<div class="col-hdr">'
        '<div class="col-hdr-t">AI AGENTS PREDICTION</div>'
        '<div class="col-hdr-s">AI Agent Engine · 6 intelligence engines · independent</div>'
        '</div>', unsafe_allow_html=True)

    if not ai_res:
        st.info("Click the run button to start AI agents.")
        return

    if ai_res.get("status") != "SUCCESS":
        st.error(f"AI agents failed: {ai_res.get('message','Unknown error')}")
        return

    d       = _ai_decision(ai_res)
    intel   = ai_res.get("intelligence") or {}
    verd    = intel.get("verdict") or {}
    conf_o  = intel.get("confidence") or {}
    scores  = intel.get("scores") or {}
    score   = int(verd.get("score") or 0)
    conf    = int(conf_o.get("score") or 0)
    conf_note = (conf_o.get("note") or "")[:120]

    def _sc(eng: str) -> str:
        """Return score string; show signal text when score=0."""
        obj    = scores.get(eng) or {}
        val    = obj.get("score")
        signal = obj.get("signal","")
        if val is None: return "Not available"
        if val == 0 and signal:
            return f"0 ({signal})"
        return f"{int(val)}/100"

    badge_color = "#635BFF" if score > 0 else "#F59E0B"
    st.markdown(
        f'<div class="{_dv_cls(d)}">{d}</div>'
        f'<span style="font-size:.72rem;color:{badge_color};font-weight:600;">'
        f'Score: {score}/100 · Confidence: {conf}/100</span>',
        unsafe_allow_html=True)
    if conf_note:
        st.caption(conf_note)
    st.markdown("")

    # Row 1 — capital (same parameter as left column)
    _mrow3("Initial Capital",      f"${capital:,.0f}",
           "Expected Final",       "Not estimated",
           "Expected P&L",         "Not estimated")
    # Row 2 — scores
    _mrow3("Composite Score",      f"{score}/100",
           "Confidence",           f"{conf}/100",
           "Expected Return",      "Not estimated")
    # Row 3 — engine scores
    _mrow3("Fundamental",          _sc("fundamental"),
           "Technical",            _sc("technical"),
           "Valuation",            _sc("valuation"))
    # Row 4 — engine scores cont.
    _mrow3("Macro",                _sc("macro"),
           "Sentiment",            _sc("sentiment"),
           "Risk Score",           _sc("risk"))
    # Row 5 — not estimated (parallel to backtest row 5)
    _mrow2("Win Probability",      "Not estimated",
           "Expected Sharpe",      "Not estimated")

    # AI report / explanation
    report = ai_res.get("report") or ai_res.get("analysis") or ai_res.get("message","")
    if report and isinstance(report, str) and len(report.strip()) > 30:
        with st.expander("AI Analysis Report"):
            st.write(report[:3000])
    else:
        st.caption("AI report not available for this run.")


# ══════════════════════════════════════════════════════════════════════════════
# FINAL DECISION BOARD
# ══════════════════════════════════════════════════════════════════════════════
def _render_final_decision(bt_d: str, ai_d: str, cmp: dict) -> None:
    """Four decision cards. Time O(1)."""
    cards = [("Backtest Decision", bt_d or "—"),
             ("AI Agent Decision", ai_d or "—"),
             ("Agreement",         cmp["agreement"]),
             ("Final Decision",    cmp["final"])]
    cols = st.columns(4)
    for col,(lbl,val) in zip(cols, cards):
        col.markdown(
            f'<div class="fdb-card"><div class="fdb-lbl">{lbl}</div>'
            f'<div class="fdb-val" style="color:{_dv_color(val)};">{val}</div></div>',
            unsafe_allow_html=True)
    msg = cmp.get("msg","")
    if msg:
        agr = cmp["agreement"]
        if   agr == "MATCH":    st.success(msg)
        elif agr == "CONFLICT": st.error(msg)
        else:                   st.warning(msg)


# ══════════════════════════════════════════════════════════════════════════════
# ACCURACY SECTION
# ══════════════════════════════════════════════════════════════════════════════
def _render_accuracy(sym: str) -> None:
    """Accuracy / Precision / Recall / F1 / Confusion Matrix."""
    records  = _load_runs()
    prod_rec = [r for r in records if r.get("source") == "rolling_evaluation"]
    working  = prod_rec if prod_rec else [r for r in records if r.get("source") == "demo_self_check"]

    if len(working) < 2:
        cols = st.columns(4)
        for col,lbl in zip(cols, ["Accuracy","Precision","Recall","F1 Score"]):
            col.metric(lbl, "Needs data")
        st.info(f"Accuracy metrics require at least 2 historical evaluation samples. "
                f"Current samples: {len(records)}. "
                "Run rolling evaluation to generate production scores.")
        if st.button("Run Quick Evaluation Self-Check", key="acc_demo_btn"):
            _seed_demo(sym)
            st.rerun()
        return

    y_true = [r["actual_label"] for r in working if r.get("actual_label") and r.get("ai_decision")]
    y_pred = [r["ai_decision"]  for r in working if r.get("actual_label") and r.get("ai_decision")]

    if not prod_rec:
        st.warning("Showing demo self-check records only. This is NOT production model accuracy.")

    if len(y_true) < 2:
        st.info(f"Insufficient labelled records ({len(y_true)}). Need >= 2.")
        return

    m = _compute_accuracy(y_true, y_pred)
    if "error" in m:
        st.warning(m["error"]); return

    _mrow3("Accuracy",        f"{m['accuracy']*100:.1f}%",
           "Macro Precision", f"{m['macro_p']*100:.1f}%",
           "Macro Recall",    f"{m['macro_r']*100:.1f}%")
    c1,c2 = st.columns(2)
    c1.metric("Macro F1",      f"{m['macro_f1']*100:.1f}%")
    c2.metric("Support Count", f"{m['n_samples']} samples · {m['n_correct']} correct")
    st.caption(f"{'Production' if prod_rec else 'Demo'} records · {m['n_samples']} samples.")

    pc = m.get("per_class") or {}
    if pc:
        st.dataframe(
            [{"Class":k,
              "Precision": f"{v['precision']*100:.1f}%",
              "Recall":    f"{v['recall']*100:.1f}%",
              "F1":        f"{v['f1']*100:.1f}%",
              "Support":   v["support"]} for k,v in pc.items()],
            use_container_width=True, hide_index=True)

    lbls = m.get("cm_labels",[])
    mat  = m.get("cm_matrix",[])
    if lbls and mat:
        try:
            import plotly.graph_objects as go
            fig = go.Figure(go.Heatmap(z=mat, x=lbls, y=lbls,
                                       colorscale="Blues", text=mat,
                                       texttemplate="%{text}", showscale=True))
            fig.update_layout(title="Confusion Matrix (AI Predictions vs Actual)",
                              height=270, margin=dict(l=10,r=10,t=36,b=10),
                              xaxis_title="Predicted", yaxis_title="Actual")
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.dataframe({"Label":lbls, **{lbl:[mat[i][j] for i in range(len(lbls))]
                                            for j,lbl in enumerate(lbls)}})


# ══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════════════════════════════
def _render_charts(bt_res: dict, ai_res: dict) -> None:
    """P/L curve + AI factor bar. Graceful fallback if data missing."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.caption("Install plotly for charts: pip install plotly")
        return

    trial_rows = (bt_res or {}).get("trial_rows") or []
    if trial_rows:
        dates = [r.get("exit_date") or r.get("entry_date","") for r in trial_rows]
        cumpl, total = [], 0.0
        for r in trial_rows:
            total += float(r.get("profit_loss",0))
            cumpl.append(total)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=cumpl, mode="lines",
                                  name="Cumulative P&L",
                                  line=dict(color="#635BFF", width=2)))
        fig.update_layout(title="tastytrade — Cumulative P&L Curve",
                          height=250, margin=dict(l=10,r=10,t=36,b=10),
                          xaxis_title="Exit Date", yaxis_title="Cumulative P&L ($)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("No trial data available for P&L chart.")

    if ai_res and ai_res.get("status") == "SUCCESS" and _ai_has_data(ai_res):
        scores  = ((ai_res.get("intelligence") or {}).get("scores") or {})
        engines = ["fundamental","technical","valuation","macro","sentiment","risk"]
        vals    = [int((scores.get(e) or {}).get("score") or 0) for e in engines]
        colors  = ["#635BFF","#0EA5E9","#10B981","#F59E0B","#EF4444","#6B7280"]
        fig = go.Figure(go.Bar(x=engines, y=vals, marker_color=colors,
                                text=vals, textposition="outside"))
        fig.update_layout(title="AI Agent — Factor Score Breakdown",
                          height=250, margin=dict(l=10,r=10,t=36,b=10),
                          yaxis=dict(range=[0,110]))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("AI factor chart not available — market data API required.")


# ══════════════════════════════════════════════════════════════════════════════
# DEBUG EXPANDERS — never expose token values
# ══════════════════════════════════════════════════════════════════════════════
def _render_debug(bt_res: dict, ai_res: dict) -> None:
    with st.expander("Developer Debug: Environment Status"):
        st.json({
            "GOOGLE_API_KEY present":            bool(os.getenv("GOOGLE_API_KEY","").strip() or os.getenv("GEMINI_API_KEY","").strip()),
            "RAPIDAPI_KEY present":              bool(os.getenv("RAPIDAPI_KEY","").strip()),
            "TASTYTRADE_CLIENT_SECRET present":  bool(os.getenv("TASTYTRADE_CLIENT_SECRET","").strip()),
            "TASTYTRADE_REFRESH_TOKEN present":  bool(os.getenv("TASTYTRADE_REFRESH_TOKEN","").strip()),
            "TASTYTRADE_ACCESS_TOKEN present":   bool(os.getenv("TASTYTRADE_ACCESS_TOKEN","").strip()),
            ".env path":   str(ROOT / ".env"),
            ".env exists": (ROOT / ".env").exists(),
        })
    if bt_res:
        with st.expander("Developer Debug: Backtest Raw Response"):
            safe = {k:v for k,v in bt_res.items() if k not in ("trial_rows","_raw","_extracted")}
            st.json(safe)
            rows = bt_res.get("trial_rows") or []
            if rows:
                st.caption(f"trial_rows: {len(rows)} rows — first 5:")
                st.json(rows[:5])
            raw = bt_res.get("_raw") or {}
            if raw:
                st.caption("Raw API response (first 2000 chars):")
                st.code(json.dumps(raw, default=str)[:2000])
    if ai_res:
        with st.expander("Developer Debug: AI Raw Response"):
            st.json(ai_res)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    status = _status()

    # ── Header ────────────────────────────────────────────────────────────────
    pills = (_pill("Google AI",   status["google"])
           + _pill("RapidAPI",    status["rapidapi"])
           + _pill("Tastytrade",  status["tastytrade"])
           + _pill("Backtesting", status["backtesting"]))

    st.markdown(
        f'<div class="sys-hdr">'
        f'<div class="sys-title">AI FINANCIAL ANALYST SYSTEM</div>'
        f'<div class="sys-sub">Real-Time Options Analysis · Backtesting vs AI Agent Intelligence</div>'
        f'<div style="margin-top:.35rem;">{pills}</div>'
        f'</div>', unsafe_allow_html=True)

    if not status["tastytrade"]:
        st.error("Tastytrade credentials missing — backtesting cannot run. "
                 "Add TASTYTRADE_REFRESH_TOKEN and TASTYTRADE_CLIENT_SECRET to .env.")

    # ── Configuration Panel ───────────────────────────────────────────────────
    with st.expander("Backtest Configuration Panel", expanded=True):
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        with r1c1: symbol   = st.text_input("Symbol",           value="SPY",           key="sym")
        with r1c2: start    = st.text_input("Start Date",       value="2021-06-25",    key="start")
        with r1c3: end      = st.text_input("End Date",         value="2026-06-24",    key="end")
        with r1c4: capital  = st.number_input("Initial Capital ($)", value=100_000,
                                               min_value=1_000, step=10_000,
                                               format="%d", key="cap")

        st.markdown("**Options Strategy Parameters**")
        r2c1, r2c2, r2c3, r2c4, r2c5, r2c6 = st.columns(6)
        with r2c1: direction  = st.selectbox("Direction", ["short","long"],      key="dir")
        with r2c2: side       = st.selectbox("Side",      ["put","call"],        key="side")
        with r2c3: dte        = st.number_input("DTE",   value=45, min_value=1,  max_value=365, key="dte")
        with r2c4: delta      = st.number_input("Delta", value=30, min_value=1,  max_value=99,  key="dlt")
        with r2c5: num_legs   = st.selectbox("Legs",     [1,2,3,4], index=0,    key="legs")  # default 1
        with r2c6: frequency  = st.selectbox("Entry Frequency",
                                              ["every day","weekly","monthly"],  key="freq")

    sym = (symbol or "AAPL").strip().upper()
    cap = float(capital)

    # ── Run Button ────────────────────────────────────────────────────────────
    run = st.button("RUN BACKTEST + AI AGENT COMPARISON",
                    type="primary", use_container_width=True, key="run_btn")

    if run:
        st.session_state["button_clicked"] = True
        with st.spinner(f"Running tastytrade options backtest for {sym}…"):
            st.session_state["last_backtest_result"] = run_tastytrade_backtest(
                sym, start, end, direction, side,
                int(dte), int(delta), int(num_legs), frequency, cap)
        with st.spinner(f"Running AI agents for {sym}…"):
            st.session_state["last_ai_result"] = run_ai_agents(sym)
        st.session_state["last_comparison_result"] = None  # reset comparison cache

    bt_res = st.session_state.get("last_backtest_result")
    ai_res = st.session_state.get("last_ai_result")

    # Nothing run yet
    if not st.session_state.get("button_clicked"):
        _hr()
        st.info(
            f"Ready: **{sym}** · {start} → {end} · ${cap:,.0f} capital · "
            f"{direction} {side} · DTE {int(dte)} · Δ{int(delta)} · {int(num_legs)} leg(s) · {frequency}  "
            "Configure above then click **RUN BACKTEST + AI AGENT COMPARISON**.")
        return

    # ── Section 1: Two-Column Results ─────────────────────────────────────────
    _hr()
    _sec("1. Backtesting Results vs AI Agents Prediction")

    col_bt, col_ai = st.columns(2)
    with col_bt:
        _render_bt_col(bt_res or {}, cap)
    with col_ai:
        _render_ai_col(ai_res or {}, cap)

    # ── Section 2: Final Decision Board ───────────────────────────────────────
    _hr()
    _sec("2. Final Decision Board")
    bt_d = _bt_decision(bt_res or {})
    ai_d = _ai_decision(ai_res or {})
    cmp  = st.session_state.get("last_comparison_result") or _compare(bt_d, ai_d, bt_res or {}, ai_res or {})
    st.session_state["last_comparison_result"] = cmp
    _render_final_decision(bt_d, ai_d, cmp)

    # ── Section 3: Accuracy Metrics ───────────────────────────────────────────
    _hr()
    _sec("3. Accuracy Metrics")
    _render_accuracy(sym)

    # ── Section 4: Charts ─────────────────────────────────────────────────────
    _hr()
    _sec("4. Charts")
    _render_charts(bt_res or {}, ai_res or {})

    # ── Debug ─────────────────────────────────────────────────────────────────
    _hr()
    _render_debug(bt_res, ai_res)


if __name__ == "__main__":
    main()
