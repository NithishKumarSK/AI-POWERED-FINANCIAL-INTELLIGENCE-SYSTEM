"""One-off analysis: classify every completed stock-prediction run into a
failure category, using the same taxonomy as failure_analyzer.py but reading
directly from stock_prediction_evaluation_runs.jsonl (the real accumulated
corpus) instead of the near-empty batch_validation_results.csv.
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
records = []
with open(ROOT / "stock_prediction_evaluation_runs.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except Exception:
                pass

def classify(rec):
    cmp = rec.get("comparison", {})
    ai = rec.get("ai_prediction", {})
    act = rec.get("actual_validation", {})
    if cmp.get("status") != "SUCCESS":
        return "DATA_QUALITY_ISSUE"
    if cmp.get("agreement") == "MATCH" or cmp.get("decision_match"):
        return "NONE"
    ai_dec = (ai.get("decision") or "").upper()
    act_dec = (act.get("actual_decision") or "").upper()
    abs_err = abs(cmp.get("abs_return_error_pct") or cmp.get("return_error_pct") or 0)
    if ai_dec == "HOLD" and act_dec in ("BUY", "SELL"):
        return "OVER_HOLD"
    if ai_dec == "BUY" and act_dec == "SELL":
        return "FALSE_BUY"
    if ai_dec == "SELL" and act_dec == "BUY":
        return "FALSE_SELL"
    if cmp.get("directional_match") and not cmp.get("decision_match"):
        return "WRONG_MAGNITUDE"
    if ai_dec in ("BUY", "SELL") and act_dec == "HOLD":
        return "PREMATURE_CALL"
    return "UNKNOWN_FAILURE"

cat_counts = defaultdict(int)
symbol_stats = defaultdict(lambda: {"n": 0, "match": 0, "abs_err_sum": 0.0, "misses": []})
worst = []
overall_abs_err = []
confidence_by_outcome = defaultdict(list)

for rec in records:
    cmp = rec.get("comparison", {})
    ai = rec.get("ai_prediction", {})
    act = rec.get("actual_validation", {})
    spi = rec.get("stock_prediction_input", {})
    sym = spi.get("symbol", "?")
    cat = classify(rec)
    cat_counts[cat] += 1

    is_match = cat == "NONE"
    abs_err = abs(cmp.get("abs_return_error_pct") or cmp.get("return_error_pct") or 0)
    overall_abs_err.append(abs_err)

    s = symbol_stats[sym]
    s["n"] += 1
    if is_match:
        s["match"] += 1
    s["abs_err_sum"] += abs_err

    conf = ai.get("confidence_score")
    if conf is not None:
        confidence_by_outcome["match" if is_match else "miss"].append(conf)

    if not is_match:
        s["misses"].append({
            "run_id": rec.get("run_id"),
            "category": cat,
            "ai_decision": ai.get("decision"),
            "actual_decision": act.get("actual_decision"),
            "predicted_return_pct": ai.get("predicted_return_pct"),
            "actual_return_pct": act.get("actual_return_pct"),
            "abs_return_error_pct": round(abs_err, 2),
            "confidence": conf,
            "origin_date": spi.get("prediction_origin_date"),
            "target_date": spi.get("target_date"),
        })
        worst.append({
            "symbol": sym,
            "run_id": rec.get("run_id"),
            "category": cat,
            "ai_decision": ai.get("decision"),
            "actual_decision": act.get("actual_decision"),
            "abs_return_error_pct": round(abs_err, 2),
            "predicted_return_pct": ai.get("predicted_return_pct"),
            "actual_return_pct": act.get("actual_return_pct"),
            "origin_date": spi.get("prediction_origin_date"),
            "target_date": spi.get("target_date"),
            "confidence": conf,
        })

total = len(records)
matches = cat_counts.get("NONE", 0)

print("=== OVERALL ===")
print(f"total_records: {total}")
print(f"matches: {matches}  ({round(100*matches/total,1)}%)")
print(f"avg_abs_return_error_pct: {round(sum(overall_abs_err)/len(overall_abs_err),2)}")
print()
print("=== FAILURE CATEGORY BREAKDOWN ===")
for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
    print(f"{cat:28s} {n:4d}  ({round(100*n/total,1)}%)")
print()
print("=== PER-SYMBOL (n>=3) sorted by miss rate desc ===")
sym_rows = []
for sym, s in symbol_stats.items():
    if s["n"] >= 3:
        miss_rate = 100 * (s["n"] - s["match"]) / s["n"]
        avg_err = s["abs_err_sum"] / s["n"]
        sym_rows.append((sym, s["n"], s["match"], miss_rate, avg_err))
sym_rows.sort(key=lambda r: -r[3])
for sym, n, match, miss_rate, avg_err in sym_rows:
    print(f"{sym:8s} n={n:3d}  match={match:3d}  miss_rate={round(miss_rate,1):5.1f}%  avg_abs_err={round(avg_err,1):5.1f}pp")
print()
print("=== CONFIDENCE: matched vs missed ===")
for k, v in confidence_by_outcome.items():
    if v:
        print(f"{k}: n={len(v)}  avg_confidence={round(sum(v)/len(v),1)}")
print()
print("=== TOP 10 WORST MISSES (by abs return error) ===")
worst_sorted = sorted(worst, key=lambda x: -(x["abs_return_error_pct"] or 0))[:10]
for w in worst_sorted:
    print(json.dumps(w))

# dump full structured output for artifact-building
out = {
    "total": total,
    "matches": matches,
    "match_rate_pct": round(100*matches/total, 1),
    "avg_abs_return_error_pct": round(sum(overall_abs_err)/len(overall_abs_err), 2),
    "category_counts": dict(cat_counts),
    "symbol_stats": [
        {"symbol": r[0], "n": r[1], "match": r[2], "miss_rate_pct": round(r[3],1), "avg_abs_err_pp": round(r[4],1)}
        for r in sym_rows
    ],
    "confidence_by_outcome": {k: round(sum(v)/len(v),1) for k, v in confidence_by_outcome.items() if v},
    "worst_misses": worst_sorted,
}
with open(ROOT / "data" / "_failure_analysis_live.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print()
print("Wrote data/_failure_analysis_live.json")
