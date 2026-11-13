"""
daily_top_ideas_ranker.py -- Research Expansion Program: a daily "Top 20
ideas" ranking across a stock universe, inspired by Chen & Pu's agentic
nowcaster (Peking University, arXiv 2601.11958), whose own most robust
finding was that ranking (Top-10/20 vs Bottom-20) can show a real,
statistically cleaner edge even when single up/down calls hover near 50% --
exactly this project's own situation (53.0% overall direction-match).

Deliberately NOT one Gemini call per symbol (377 stocks x a 60-150s deep-
thinking call each is not a "daily" feature, it's an hours-long batch job
burning real API quota). Instead: ranks the SAME deterministic, free,
zero-Gemini-cost technical-override score
(_compute_technical_override_score, already used to override/sanity-check
every live Gemini prediction) across a real universe, using only fresh
price history. Cheap enough to actually run daily.

This is explicitly NOT a claim that the deterministic score alone is a
proven trading edge -- it has never been validated standalone for ranking
(only as an override gate on top of Gemini's own call). It's an honest,
cheap, real product feature: "which of these N symbols currently show the
strongest technical setup," not a backtested ranking strategy.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_paths
bootstrap_paths.add_module_paths()

# A real, liquid, sector-diverse universe -- not exhaustive (377 stocks is
# Chen & Pu's own scope, a much larger live-trading operation), but large
# enough for a genuine "Top 20 of N" ranking rather than "Top 20 of 20."
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD", "NFLX", "CRM",
    "ADBE", "ORCL", "CSCO", "IBM", "INTC", "PYPL", "DIS", "V", "MA", "JPM",
    "BAC", "WMT", "HD", "COST", "PG", "KO", "PEP", "MRK", "JNJ", "ABBV",
    "LLY", "UNH", "CVS", "XOM", "CAT", "MDB", "SNOW", "UBER", "SPY", "QQQ",
]


def rank_universe(
    symbols: Optional[List[str]] = None,
    as_of_date: Optional[str] = None,
    hist_start: Optional[str] = None,
    top_n: int = 20,
) -> dict:
    """Ranks `symbols` (default DEFAULT_UNIVERSE) by the deterministic
    technical-override score, as of `as_of_date` (default: today).

    Returns:
        {"as_of_date": str, "universe_size": int, "scored_count": int,
         "failed_symbols": [{"symbol", "error"}, ...],
         "top_ideas": [{"symbol", "score", "override", "trend_regime",
                        "adx", "rsi", "breakdown"}, ...] (sorted desc by score,
         "bottom_ideas": [...] (sorted asc by score, weakest setups)}
    """
    from historical_price_service import fetch_price_history_for_range
    from gemini_stock_prediction_agent import (
        build_stock_feature_packet, _compute_technical_override_score,
    )

    symbols = symbols or DEFAULT_UNIVERSE
    as_of = as_of_date or date.today().isoformat()
    start = hist_start or (date.fromisoformat(as_of[:10]) - timedelta(days=200)).isoformat()

    scored = []
    failed = []
    for sym in symbols:
        try:
            bars, err, _cov = fetch_price_history_for_range(sym, start, as_of)
            if not bars:
                failed.append({"symbol": sym, "error": err or "No bars returned"})
                continue
            bars = [b for b in bars if b["date"] <= as_of]
            if len(bars) < 20:
                failed.append({"symbol": sym, "error": f"Only {len(bars)} bars available, need >=20"})
                continue

            normalized_input = {
                "symbol": sym,
                "historical_context_start_date": start,
                "prediction_origin_date": as_of,
                "decision_horizon_days": 14,
                "price_basis": "close",
            }
            fp = build_stock_feature_packet(normalized_input, bars)
            if fp.get("status") != "OK":
                failed.append({"symbol": sym, "error": fp.get("error", "Feature packet build failed")})
                continue

            tech = _compute_technical_override_score(fp)
            scored.append({
                "symbol": sym,
                "score": tech["score"],
                "override": tech["override"],
                "breakdown": tech["breakdown"],
                "trend_regime": (fp.get("trend") or {}).get("trend_regime"),
                "adx": (fp.get("trend") or {}).get("ADX_14"),
                "rsi": (fp.get("momentum") or {}).get("RSI_14"),
                "origin_price": fp.get("origin_price"),
            })
        except Exception as exc:
            failed.append({"symbol": sym, "error": f"{type(exc).__name__}: {exc}"})

    scored_sorted_desc = sorted(scored, key=lambda s: s["score"], reverse=True)
    scored_sorted_asc = sorted(scored, key=lambda s: s["score"])

    return {
        "as_of_date": as_of,
        "universe_size": len(symbols),
        "scored_count": len(scored),
        "failed_symbols": failed,
        "top_ideas": scored_sorted_desc[:top_n],
        "bottom_ideas": scored_sorted_asc[:top_n],
    }


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=str, default="")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--out", type=str, default=str(ROOT / "data" / "daily_top_ideas.json"))
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None
    result = rank_universe(symbols=symbols, as_of_date=args.as_of, top_n=args.top_n)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    print(f"As of {result['as_of_date']}: scored {result['scored_count']}/{result['universe_size']} "
          f"({len(result['failed_symbols'])} failed)")
    print(f"\nTop {len(result['top_ideas'])} ideas (strongest technical setups):")
    for r in result["top_ideas"]:
        print(f"  {r['symbol']:6s} score={r['score']:+3d}  trend={r['trend_regime']:10s}  "
              f"RSI={r['rsi']}  ADX={r['adx']}")
    print(f"\nBottom {len(result['bottom_ideas'])} ideas (weakest technical setups):")
    for r in result["bottom_ideas"]:
        print(f"  {r['symbol']:6s} score={r['score']:+3d}  trend={r['trend_regime']:10s}  "
              f"RSI={r['rsi']}  ADX={r['adx']}")
    print(f"\nFull report written to {out_path}")


if __name__ == "__main__":
    main()
