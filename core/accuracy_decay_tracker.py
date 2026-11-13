"""
accuracy_decay_tracker.py -- Research Expansion Program: decaying-edge
tracking, grounded in Lopez-Lira & Tang (arXiv 2304.07619 v6), whose own
headline finding is not "high accuracy" but that their strategy's Sharpe
ratio fell from 6.54 (2021 Q4) to 1.22 (Jan-May 2024) as the edge eroded
with adoption. If our system has any edge, it should be measured the same
honest way -- over time, not as one static number.

No new data source: this reads the SAME validated prediction records
already sitting in the central DB (db/stock_prediction_repository.py) that
every other accuracy report in this project uses. Pure arithmetic, zero
Gemini calls, zero cost.

Buckets by calendar month of prediction_origin_date. For each month:
  - decision_match_rate, direction_match_rate (same definitions as every
    other accuracy report in this project)
  - a "strategy return" per prediction: actual_return_pct if decision was
    BUY, -actual_return_pct if SELL, 0.0 if HOLD (this is what you'd have
    actually earned by following the AI's calls, before any cost model)
  - a RAW (non-annualized) Sharpe-like ratio = mean(strategy_return) /
    stdev(strategy_return) for that month's predictions. Deliberately NOT
    annualized -- horizons in our data range from 7 to 45+ days, so a single
    annualization factor would be misleading across mixed-horizon months.
    Report the raw ratio and let the reader judge trend direction, exactly
    the discipline the deep-dive research applies to every paper it reviewed.

Usage: python core/accuracy_decay_tracker.py [--limit N] [--out path.json]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_paths
bootstrap_paths.add_module_paths()


# Lopez-Lira & Tang (arXiv 2304.07619 v6) disclose a 20-basis-point round-
# trip transaction cost as the threshold at which their own strategy's edge
# disappeared entirely -- the same real, citable assumption used here rather
# than an invented number. Applied once per BUY/SELL prediction (one round
# trip: enter + exit); HOLD has no cost since no trade is placed.
ROUND_TRIP_COST_PCT = 0.20


def _strategy_return(decision: Optional[str], actual_return_pct: Optional[float],
                      apply_cost: bool = False) -> Optional[float]:
    if decision not in ("BUY", "SELL", "HOLD") or actual_return_pct is None:
        return None
    cost = ROUND_TRIP_COST_PCT if (apply_cost and decision in ("BUY", "SELL")) else 0.0
    if decision == "BUY":
        return float(actual_return_pct) - cost
    if decision == "SELL":
        return -float(actual_return_pct) - cost
    return 0.0


def build_decay_report(records: List[dict]) -> dict:
    """records: the standard (timestamp, stock_prediction_input, ai_prediction,
    actual_validation, comparison) dict shape returned by
    load_stock_prediction_records (either the JSONL or DB-backed version --
    same shape, see db/stock_prediction_repository.py's _row_to_jsonl_record)."""
    buckets: Dict[str, List[dict]] = defaultdict(list)
    skipped_no_date = 0

    for r in records:
        spi = r.get("stock_prediction_input") or {}
        origin = str(spi.get("prediction_origin_date", "") or "")[:7]  # YYYY-MM
        if not origin or len(origin) != 7:
            skipped_no_date += 1
            continue
        buckets[origin].append(r)

    months = sorted(buckets.keys())
    monthly: List[dict] = []
    for month in months:
        recs = buckets[month]
        n = len(recs)
        dm = sum(1 for r in recs if (r.get("comparison") or {}).get("decision_match") is True)
        dirm = sum(1 for r in recs if (r.get("comparison") or {}).get("directional_match") is True)
        strat_returns, strat_returns_cost_adj = [], []
        for r in recs:
            ai = r.get("ai_prediction") or {}
            av = r.get("actual_validation") or {}
            decision, actual = ai.get("decision"), av.get("actual_return_pct")
            sret = _strategy_return(decision, actual, apply_cost=False)
            sret_cost = _strategy_return(decision, actual, apply_cost=True)
            if sret is not None:
                strat_returns.append(sret)
            if sret_cost is not None:
                strat_returns_cost_adj.append(sret_cost)

        def _mean_and_sharpe(returns):
            if len(returns) < 2:
                return None, None
            mean_ret = round(statistics.mean(returns), 4)
            stdev_ret = statistics.stdev(returns)
            sharpe = round(mean_ret / stdev_ret, 4) if stdev_ret > 1e-9 else None
            return mean_ret, sharpe

        mean_ret, sharpe_raw = _mean_and_sharpe(strat_returns)
        mean_ret_cost, sharpe_cost = _mean_and_sharpe(strat_returns_cost_adj)

        monthly.append({
            "month": month,
            "n": n,
            "decision_match_rate_pct": round(dm / n * 100, 1) if n else None,
            "direction_match_rate_pct": round(dirm / n * 100, 1) if n else None,
            "mean_strategy_return_pct": mean_ret,
            "strategy_sharpe_raw_nonannualized": sharpe_raw,
            "mean_strategy_return_pct_after_costs": mean_ret_cost,
            "strategy_sharpe_after_costs_nonannualized": sharpe_cost,
        })

    # Simple trend signal: compare first half vs second half of months with
    # enough data, exactly the kind of before/after split the deep-dive
    # research applies (e.g. Lopez-Lira's 2021-Q4-vs-2024 comparison), scaled
    # down to however much real history we actually have.
    usable = [m for m in monthly if m["n"] >= 3]
    trend_note = "Not enough months with >=3 predictions each to assess a trend yet."
    if len(usable) >= 2:
        first, last = usable[0], usable[-1]
        trend_note = (
            f"First usable month ({first['month']}, n={first['n']}): "
            f"direction_match={first['direction_match_rate_pct']}%, "
            f"sharpe_raw={first['strategy_sharpe_raw_nonannualized']}. "
            f"Most recent usable month ({last['month']}, n={last['n']}): "
            f"direction_match={last['direction_match_rate_pct']}%, "
            f"sharpe_raw={last['strategy_sharpe_raw_nonannualized']}. "
            "This is a trend SIGNAL only (small-n months are noisy) -- not a "
            "claim of statistical significance, unlike Lopez-Lira & Tang's "
            "multi-year, large-n decay finding."
        )

    return {
        "total_records": len(records),
        "skipped_no_origin_date": skipped_no_date,
        "monthly": monthly,
        "trend_note": trend_note,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--out", type=str, default=str(ROOT / "data" / "accuracy_decay_report.json"))
    args = parser.parse_args()

    from db.stock_prediction_repository import load_stock_prediction_records
    records = load_stock_prediction_records(limit=args.limit)
    report = build_decay_report(records)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Loaded {report['total_records']} validated records "
          f"({report['skipped_no_origin_date']} skipped, no origin date).")
    print(f"Months with data: {len(report['monthly'])}")
    for m in report["monthly"]:
        print(f"  {m['month']}: n={m['n']:3d}  decision_match={m['decision_match_rate_pct']}%  "
              f"direction_match={m['direction_match_rate_pct']}%  "
              f"sharpe_raw={m['strategy_sharpe_raw_nonannualized']}  "
              f"sharpe_after_{ROUND_TRIP_COST_PCT}pct_cost={m['strategy_sharpe_after_costs_nonannualized']}")
    print()
    print(report["trend_note"])
    print(f"\nTransaction-cost assumption: {ROUND_TRIP_COST_PCT}% round-trip per BUY/SELL "
          f"(Lopez-Lira & Tang, arXiv 2304.07619 v6 -- the level at which their own strategy's edge disappeared).")
    print(f"\nFull report written to {out_path}")


if __name__ == "__main__":
    main()
