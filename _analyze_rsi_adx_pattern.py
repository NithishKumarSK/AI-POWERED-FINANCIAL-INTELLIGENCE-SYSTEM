"""
One-off analysis (not part of the app): for every deduped eval-log record,
reconstruct the RSI_14 / ADX_14 / trend_regime the model actually saw at
prediction time (deterministic feature packet, no Gemini calls), and check
how often "extreme RSI + strong-trend" setups occurred and how they resolved.

This is read-only research to decide whether the July 31 TSLA miss (RSI=18.08,
ADX=34.88, decisive SELL, actual +18.23%) reflects a real recurring pattern
or a one-off. Nothing here is wired into the app.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from stock_accuracy_engine import load_stock_prediction_records
from historical_price_service import fetch_price_history
from gemini_stock_prediction_agent import build_stock_feature_packet

recs = load_stock_prediction_records(limit=1000)
by_symbol: dict = {}
for r in recs:
    spi = r.get("stock_prediction_input", {})
    sym = spi.get("symbol")
    if sym:
        by_symbol.setdefault(sym, []).append(r)

_price_cache: dict = {}


def get_bars(symbol: str):
    if symbol not in _price_cache:
        bars, err = fetch_price_history(symbol, min_days=1200)
        _price_cache[symbol] = bars if not err else []
    return _price_cache[symbol]


rows = []
skipped = 0
for sym, sym_recs in by_symbol.items():
    bars = get_bars(sym)
    if not bars:
        skipped += len(sym_recs)
        continue
    for r in sym_recs:
        spi = r.get("stock_prediction_input", {})
        origin = spi.get("prediction_origin_date")
        if not origin:
            skipped += 1
            continue
        ctx_bars = [b for b in bars if b["date"] <= origin]
        if len(ctx_bars) < 60:
            skipped += 1
            continue
        packet = build_stock_feature_packet(spi, ctx_bars)
        if packet.get("status") != "OK":
            skipped += 1
            continue
        rsi = packet["momentum"].get("RSI_14")
        adx = packet["trend"].get("ADX_14")
        trend_regime = packet["trend"].get("trend_regime")
        if rsi is None or adx is None:
            skipped += 1
            continue

        ai_dec  = r.get("ai_prediction", {}).get("decision")
        act_dec = r.get("actual_validation", {}).get("actual_decision")
        match   = r.get("comparison", {}).get("decision_match")
        actual_ret = r.get("actual_validation", {}).get("actual_return_pct")

        rows.append({
            "symbol": sym, "origin": origin, "rsi": rsi, "adx": adx,
            "trend_regime": trend_regime, "ai_decision": ai_dec,
            "actual_decision": act_dec, "match": match, "actual_return_pct": actual_ret,
        })

print(f"Analyzed {len(rows)} records ({skipped} skipped: no price data / insufficient bars).\n")

# Pattern 1: extreme oversold + strong downtrend (the July 31 TSLA setup)
oversold_strong_down = [r for r in rows if r["rsi"] < 25 and r["adx"] > 25 and r["trend_regime"] == "bearish"]
# Pattern 2 (mirror): extreme overbought + strong uptrend
overbought_strong_up = [r for r in rows if r["rsi"] > 75 and r["adx"] > 25 and r["trend_regime"] == "bullish"]
# Looser version: just RSI<25 or RSI>75 in ANY strong trend, regardless of regime label match
extreme_rsi_strong_trend = [r for r in rows if (r["rsi"] < 25 or r["rsi"] > 75) and r["adx"] > 25]

def summarize(label, subset):
    print(f"=== {label}: {len(subset)} occurrences ===")
    if not subset:
        print()
        return
    misses = [r for r in subset if r["match"] is False]
    matches = [r for r in subset if r["match"] is True]
    print(f"  decision_match: {len(matches)}/{len(subset)} ({100*len(matches)/len(subset):.0f}%)  |  misses: {len(misses)}")
    for r in subset:
        print(f"    {r['symbol']:6s} {r['origin']}  RSI={r['rsi']:.1f}  ADX={r['adx']:.1f}  "
              f"AI={r['ai_decision']:5s} actual={r['actual_decision']:5s} "
              f"match={r['match']}  actual_ret={r['actual_return_pct']}")
    print()

summarize("Extreme oversold (RSI<25) + strong downtrend (ADX>25, bearish regime)", oversold_strong_down)
summarize("Extreme overbought (RSI>75) + strong uptrend (ADX>25, bullish regime)", overbought_strong_up)
summarize("Any extreme RSI (<25 or >75) + strong trend (ADX>25), any regime label", extreme_rsi_strong_trend)

# Baseline: overall decision-match rate for comparison
all_with_match = [r for r in rows if r["match"] is not None]
overall_match = sum(1 for r in all_with_match if r["match"]) / len(all_with_match) if all_with_match else None
print(f"Overall decision-match rate across all {len(all_with_match)} scored records: "
      f"{100*overall_match:.1f}%" if overall_match is not None else "N/A")
