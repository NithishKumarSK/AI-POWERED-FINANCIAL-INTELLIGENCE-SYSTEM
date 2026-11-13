"""
build_range_timing_training_set.py — generates data/range_timing_training_set.json:
a deterministic, no-Gemini-needed dataset of (feature vector -> real day-of-low,
real day-of-high) cases, used by range_timing_predictor.predict_day_offset_knn()
as the precedent pool for its k-nearest-neighbor day-timing estimate.

Why a static file instead of querying the live DB (like case_retrieval.py does):
the DB stores each prediction's final decision/outcome, not the full day-by-day
price trace within the validation window, so there's nothing to compute a real
low-day/high-day offset from there. This script computes it directly from real
historical price bars instead -- same leakage-safe walk-forward discipline as
every other backtest in this project (only bars strictly after the origin are
used to determine the real low/high day).

Run from the repo root:
    python scripts/adhoc/build_range_timing_training_set.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_paths  # noqa: E402
bootstrap_paths.add_module_paths()

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env", override=True)

from historical_price_service import fetch_price_history, filter_history_up_to  # noqa: E402
from gemini_stock_prediction_agent import build_stock_feature_packet  # noqa: E402
from range_timing_predictor import evaluate_range_and_timing, predict_price_range_and_timing  # noqa: E402
from ml_feature_extractor import feature_packet_to_vector  # noqa: E402

SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "UNH", "SPY", "QQQ"]
HORIZON_DAYS = 7
N_ORIGINS_PER_SYMBOL = 110  # up from 40 -- denser, deterministic, no Gemini cost
ORIGIN_STEP_DAYS = 4        # up from a fixed 7d weekly step -- more real cases per
                             # symbol within the same history window, still enough
                             # spacing that consecutive windows aren't near-duplicates
OUT_PATH = ROOT / "data" / "range_timing_training_set.json"


def main() -> None:
    today = date.today()
    cases: list[dict] = []
    hist_cache: dict[str, list] = {}

    def get_hist(sym: str) -> list:
        if sym not in hist_cache:
            h, _err = fetch_price_history(sym, min_days=600)
            hist_cache[sym] = h or []
        return hist_cache[sym]

    print(f"Building range-timing training set: {len(SYMBOLS)} symbols x "
          f"{N_ORIGINS_PER_SYMBOL} origins, horizon={HORIZON_DAYS}d", flush=True)

    for symbol in SYMBOLS:
        hist = get_hist(symbol)
        if not hist:
            print(f"  [WARN] {symbol}: no history", flush=True)
            continue
        for i in range(N_ORIGINS_PER_SYMBOL):
            origin = today - timedelta(days=HORIZON_DAYS + 7 + i * ORIGIN_STEP_DAYS)
            ctx_start = origin - timedelta(days=200)
            origin_s = origin.isoformat()
            target = origin + timedelta(days=HORIZON_DAYS)
            if target >= today:
                continue
            ctx_bars = [b for b in filter_history_up_to(hist, origin_s)
                        if b.get("date", "") >= ctx_start.isoformat()]
            if len(ctx_bars) < 20:
                continue
            spi = {"symbol": symbol, "historical_context_start_date": ctx_start.isoformat(),
                   "prediction_origin_date": origin_s, "decision_horizon_days": HORIZON_DAYS,
                   "price_basis": "close"}
            fp = build_stock_feature_packet(spi, ctx_bars)
            if fp.get("status") != "OK":
                continue
            vec = feature_packet_to_vector(fp)
            if vec is None:
                continue
            predicted_rule = predict_price_range_and_timing(fp)
            if predicted_rule.get("status") != "OK":
                continue
            window_bars = [b for b in hist if origin_s < b.get("date", "") <= target.isoformat()]
            if len(window_bars) < HORIZON_DAYS - 2:
                continue
            ev = evaluate_range_and_timing(predicted_rule, window_bars)
            if ev.get("status") != "OK":
                continue
            cases.append({
                "symbol": symbol, "origin": origin_s, "horizon_days": HORIZON_DAYS,
                "vec": vec,
                "actual_low_day": ev["actual_low_day_offset"],
                "actual_high_day": ev["actual_high_day_offset"],
            })

    print(f"Built {len(cases)} cases", flush=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "generated_at": date.today().isoformat(),
        "horizon_days": HORIZON_DAYS,
        "n_cases": len(cases),
        "cases": cases,
    }, indent=2), encoding="utf-8")
    print(f"Saved to {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
