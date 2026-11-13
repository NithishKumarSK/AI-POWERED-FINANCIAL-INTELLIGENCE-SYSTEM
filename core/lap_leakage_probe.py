"""
lap_leakage_probe.py -- Research Expansion Program Component: a Lookahead
Propensity-style probe (CUHK, Zhenyu Gao / Wenxi Jiang / Yutong Yan, arXiv
2512.23847), adapted to what this project's Gemini API access actually
exposes.

The original LAP method reads the model's raw first-token log-probabilities
for "up"/"down" given only a stripped ticker+date (no news, no price data).
The Gemini API used in this project does not expose token-level logprobs for
this call shape, so this adaptation uses the model's own SELF-REPORTED
confidence (0-100) instead of true token log-probs. That is a materially
weaker signal than the original paper's mechanism (self-reported confidence
can be miscalibrated in ways log-probs aren't) -- this is disclosed here and
in every output, not glossed over. What it still tests, honestly: does the
model behave differently (lower stated confidence, more "UNKNOWN" answers)
when asked about a date it cannot possibly know (a genuine FUTURE date, past
today) versus a well-known, heavily-reported historical date it has almost
certainly memorized from training data?

Two probe categories, deliberately NOT requiring knowledge of the exact
training cutoff (which we don't have for the configured Gemini model):
  - "memorization" dates: historical dates that were front-page financial
    news (2020 COVID crash bottom, 2022 rate-hike selloffs, etc.) -- if the
    model is confident and correct here, that's evidence of memorized
    specific-day market moves, not forecasting skill.
  - "future" dates: dates strictly after today -- by definition the model
    cannot know these. Any confident UP/DOWN answer here is proof of
    fabrication/overconfidence, independent of memorization.

The prompt explicitly forbids search/tool use and asks for ONLY
ticker+date -- no price, no news, no feature packet -- exactly the
"stripped" input the original method requires.

Usage: python core/lap_leakage_probe.py [--symbols TSLA,SPY,AAPL] [--out path.json]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_paths
bootstrap_paths.add_module_paths()

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=False)

_GEMINI_KEY = os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", os.getenv("AGENT_MODEL", "gemini-3.7-flash"))

_PROBE_PROMPT = """You are being asked a single, isolated factual-recall question. \
Do not use any search tool, web browsing, or external data access -- answer \
ONLY from what you already know from training.

Ticker: {symbol}
Date: {date}

Question: Did {symbol}'s stock closing price go UP or DOWN on {date} compared \
to the previous trading day's close?

Respond with ONLY a JSON object, no other text:
{{"answer": "UP" | "DOWN" | "UNKNOWN", "confidence_0_to_100": <integer>}}

If you do not know, or the date has not occurred yet, or you are not \
confident, answer "UNKNOWN" with low confidence. Do not guess to seem helpful."""


def _memorization_dates() -> List[str]:
    """Historical dates that were major, heavily-reported financial news
    events -- plausible candidates for memorization independent of any
    specific symbol's price history."""
    return ["2020-03-23", "2022-01-03", "2022-06-13", "2024-08-05"]


def _future_dates(n: int = 4) -> List[str]:
    """Strictly-future dates relative to actual today -- the model cannot
    know these by construction, regardless of training cutoff."""
    today = _dt.date.today()
    return [(today + _dt.timedelta(days=30 * (i + 1))).isoformat() for i in range(n)]


def _call_probe(symbol: str, date: str) -> dict:
    if not _GEMINI_KEY:
        return {"symbol": symbol, "date": date, "error": "GEMINI_API_KEY/GOOGLE_API_KEY not set"}

    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=_GEMINI_KEY, http_options=genai_types.HttpOptions(timeout=30000))
    prompt = _PROBE_PROMPT.format(symbol=symbol, date=date)

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=200,
                response_mime_type="application/json",
                thinking_config=genai_types.ThinkingConfig(thinking_budget=512),
            ),
        )
        raw = (response.text or "").strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        parsed = json.loads(match.group(0)) if match else {}
        return {
            "symbol": symbol, "date": date,
            "answer": parsed.get("answer"),
            "confidence": parsed.get("confidence_0_to_100"),
            "raw": raw[:300],
        }
    except Exception as exc:
        return {"symbol": symbol, "date": date, "error": f"{type(exc).__name__}: {exc}"}


def check_leakage_for_prediction(symbol: str, target_date: str) -> dict:
    """Per-prediction leakage check (not the full memorization-vs-future
    survey above) -- probes the model about THIS specific prediction's own
    target_date, stripped of all price/news context, asking only
    ticker+date. A confident UP/DOWN answer here means the model may already
    "know" this specific outcome (training-data memorization, if target_date
    predates its cutoff) or is fabricating confidence (if target_date is
    still in the future relative to real-world today) -- either way, a
    signal this specific prediction's narrative shouldn't be taken as proof
    of forecasting skill. Wired into the live pipeline as OPT-IN
    (ENABLE_LAP_PROBE_PER_PREDICTION, default false) since it costs one
    extra Gemini call per prediction.

    Returns {"checked": bool, "answer": str|None, "confidence": int|None,
    "flag": bool} -- flag=True means "confident non-UNKNOWN answer," the
    condition worth surfacing to a user/report; never raises, never blocks
    the caller's main prediction on failure."""
    result = _call_probe(symbol, target_date)
    if result.get("error"):
        return {"checked": False, "answer": None, "confidence": None, "flag": False, "error": result["error"]}
    answer = result.get("answer")
    confidence = result.get("confidence")
    flag = answer in ("UP", "DOWN") and isinstance(confidence, (int, float)) and confidence >= 50
    return {"checked": True, "answer": answer, "confidence": confidence, "flag": flag}


def run_probe(symbols: List[str]) -> dict:
    memo_dates = _memorization_dates()
    future_dates = _future_dates()

    results_memo, results_future = [], []
    for sym in symbols:
        for d in memo_dates:
            results_memo.append(_call_probe(sym, d))
            time.sleep(0.5)  # gentle on the free-tier rate limit
        for d in future_dates:
            results_future.append(_call_probe(sym, d))
            time.sleep(0.5)

    def _summarize(results: List[dict]) -> dict:
        valid = [r for r in results if r.get("confidence") is not None]
        confident_nonunknown = [r for r in valid if r.get("answer") in ("UP", "DOWN")]
        avg_conf = round(sum(r["confidence"] for r in valid) / len(valid), 1) if valid else None
        return {
            "n": len(results),
            "n_errors": sum(1 for r in results if r.get("error")),
            "n_answered_up_or_down": len(confident_nonunknown),
            "n_answered_unknown": sum(1 for r in valid if r.get("answer") == "UNKNOWN"),
            "avg_stated_confidence": avg_conf,
        }

    memo_summary = _summarize(results_memo)
    future_summary = _summarize(results_future)

    verdict = (
        "EXPECTED PATTERN (consistent with the LAP finding, via the weaker "
        "self-reported-confidence proxy used here): confidence collapses for "
        "future/unknowable dates relative to well-known historical dates."
        if (memo_summary["avg_stated_confidence"] or 0) > (future_summary["avg_stated_confidence"] or 0) + 10
        else "NOT the expected pattern -- confidence did not clearly drop for "
             "future dates. Either the model is well-calibrated (correctly "
             "saying UNKNOWN for BOTH categories), or it is overconfident even "
             "on dates that have not occurred, which would itself be a real "
             "finding worth reporting (fabrication, not memorization)."
    )

    return {
        "model": GEMINI_MODEL,
        "symbols": symbols,
        "memorization_dates_probed": memo_dates,
        "future_dates_probed": future_dates,
        "memorization_summary": memo_summary,
        "future_summary": future_summary,
        "raw_results_memorization": results_memo,
        "raw_results_future": results_future,
        "verdict": verdict,
        "methodology_caveat": (
            "This uses SELF-REPORTED confidence, not the original LAP paper's "
            "token-level log-probabilities (not exposed by this project's "
            "Gemini API access for this call shape). Treat as a weaker, "
            "directional signal -- not a replication of arXiv 2512.23847's "
            "exact method."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=str, default="TSLA,SPY,AAPL")
    parser.add_argument("--out", type=str, default=str(ROOT / "data" / "lap_leakage_probe_report.json"))
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    report = run_probe(symbols)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Model: {report['model']}")
    print(f"Memorization-date probes: {report['memorization_summary']}")
    print(f"Future-date probes:       {report['future_summary']}")
    print()
    print(report["verdict"])
    print()
    print(report["methodology_caveat"])
    print(f"\nFull report written to {out_path}")


if __name__ == "__main__":
    main()
