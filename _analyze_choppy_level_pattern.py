"""
One-off analysis (not part of the app): for every deduped eval-log record,
reconstruct ADX_14 / near_support / near_resistance at prediction time
(deterministic feature packet, no Gemini calls) and check two hypotheses:

1. Choppy market (ADX<20) overall -- is decisive-call accuracy worse than the
   baseline when the trend itself is weak/undefined?
2. "Bought into resistance" / "sold into support" while choppy -- does issuing
   a directional call AGAINST a nearby level, in a low-ADX market, fail more
   than baseline?

Read-only research triggered by 3 TREND_REVERSAL_MISSED cases in a 12-month
TSLA rolling backtest, 2 of which were near_resistance=True + BUY + choppy.
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
        adx = packet["trend"].get("ADX_14")
        rev = packet["reversal_signals"]
        if adx is None:
            skipped += 1
            continue

        ai_dec  = r.get("ai_prediction", {}).get("decision")
        act_dec = r.get("actual_validation", {}).get("actual_decision")
        match   = r.get("comparison", {}).get("decision_match")

        rows.append({
            "symbol": sym, "origin": origin, "adx": adx,
            "near_support": rev.get("near_support"), "near_resistance": rev.get("near_resistance"),
            "ai_decision": ai_dec, "actual_decision": act_dec, "match": match,
        })

print(f"Analyzed {len(rows)} records ({skipped} skipped).\n")

choppy = [r for r in rows if r["adx"] < 20]
strong = [r for r in rows if r["adx"] > 25]

def summarize(label, subset):
    scored = [r for r in subset if r["match"] is not None]
    if not scored:
        print(f"=== {label}: 0 scored ===\n")
        return
    m = sum(1 for r in scored if r["match"])
    print(f"=== {label}: {len(scored)} scored, match {m}/{len(scored)} ({100*m/len(scored):.0f}%) ===")

summarize("Choppy market (ADX<20), all decisions", choppy)
summarize("Strong trend (ADX>25), all decisions", strong)

buy_into_resistance   = [r for r in choppy if r["ai_decision"] == "BUY"  and r["near_resistance"]]
sell_into_support     = [r for r in choppy if r["ai_decision"] == "SELL" and r["near_support"]]
against_level_choppy  = buy_into_resistance + sell_into_support

summarize("Choppy + BUY into near_resistance", buy_into_resistance)
for r in buy_into_resistance:
    print(f"    {r['symbol']:6s} {r['origin']}  ADX={r['adx']:.1f}  AI=BUY  actual={r['actual_decision']}  match={r['match']}")
print()
summarize("Choppy + SELL into near_support", sell_into_support)
for r in sell_into_support:
    print(f"    {r['symbol']:6s} {r['origin']}  ADX={r['adx']:.1f}  AI=SELL  actual={r['actual_decision']}  match={r['match']}")
print()
summarize("Choppy + decisive call AGAINST a nearby level (combined)", against_level_choppy)

all_with_match = [r for r in rows if r["match"] is not None]
overall_match = sum(1 for r in all_with_match if r["match"]) / len(all_with_match) if all_with_match else None
print(f"\nOverall baseline match rate across all {len(all_with_match)} scored records: "
      f"{100*overall_match:.1f}%" if overall_match is not None else "N/A")
