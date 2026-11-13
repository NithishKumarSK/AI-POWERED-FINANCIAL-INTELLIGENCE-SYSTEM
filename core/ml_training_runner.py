"""
ml_training_runner.py — CLI to (re)train the Phase 4 / Research Expansion
Program Component 6 ML signal model(s).

Usage:
    python core/ml_training_runner.py                       # DB records only
    python core/ml_training_runner.py --bulk --symbols SPY,TSLA,AAPL --horizons 7,30 --months-back 24
    python core/ml_training_runner.py --bulk --top-sp500

Trains a global (all-data-blended) model AND, per Component 6, a dedicated
model per (symbol, horizon_bucket) segment wherever a segment has enough
samples -- motivated by a real candidate explanation for the global model's
weak result (69.8% holdout vs 67.7% baseline): mixing SPY's behavior with
TSLA's behavior in one classifier may dilute whatever signal exists in
either. Each model (global AND every segment) is evaluated on its OWN
walk-forward holdout and must independently clear the same beat-baseline-by-
3pp + absolute-floor gate before being included -- a segment that doesn't
clear it simply has no dedicated model and falls back to the global one at
prediction time (see ml_signal_model.SegmentedModel), never a fake result.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_paths
bootstrap_paths.add_module_paths()

# A model must beat this holdout accuracy to be saved -- a coin flip (50%)
# plus a small margin, so a model that's merely noise doesn't get persisted
# and silently treated as a real signal.
MIN_HOLDOUT_ACCURACY_PCT = 52.0

# A holdout test set must have at least this many samples before its accuracy
# number means anything. Confirmed real during this project's own use: a
# 39-sample segment (29 train / 10 test after the 75/25 split) reported
# "100% holdout accuracy" and cleared the gate above -- 10/10 correct is
# easily pure chance, not a real signal, but nothing stopped it from being
# saved and overwriting a previously-validated segment. n=20 is still small,
# but a filtering floor, not a claim of statistical power.
MIN_HOLDOUT_TEST_SAMPLES = 20


def _train_and_gate(X, y, meta, label: str):
    """Train on a walk-forward holdout, evaluate, and apply the non-negotiable
    save gate (beat majority-class baseline by >=3pp AND clear the absolute
    floor). Returns (model_or_none, info_dict) -- info_dict always has
    n_total/accuracy_pct/baseline_pct/saved for honest reporting regardless
    of outcome.
    """
    from ml_signal_model import train, evaluate, walk_forward_split, MIN_TRAINING_SAMPLES

    info = {"label": label, "n_total": len(X), "accuracy_pct": None, "baseline_pct": None, "saved": False}
    if len(X) < MIN_TRAINING_SAMPLES:
        info["reason"] = f"only {len(X)} samples (need >= {MIN_TRAINING_SAMPLES})"
        return None, info

    train_idx, test_idx = walk_forward_split(meta, test_frac=0.25)
    # The outer check above only validates the FULL segment's size -- after
    # the 75/25 walk-forward split, the TRAIN portion can land below
    # MIN_TRAINING_SAMPLES even when the full segment cleared it (e.g. a
    # 38-row segment's 75% split is 28 rows). train() raises ValueError for
    # exactly this case; checking here avoids an unhandled crash mid-sweep --
    # confirmed for real during development: a denser weekly-sampled sweep
    # crashed partway through on exactly this boundary and silently dropped
    # every segment after it in iteration order.
    if len(train_idx) < MIN_TRAINING_SAMPLES:
        info["reason"] = f"{len(X)} total samples, but only {len(train_idx)} after the 75/25 holdout split (need >= {MIN_TRAINING_SAMPLES})"
        return None, info

    X_train = [X[i] for i in train_idx]
    y_train = [y[i] for i in train_idx]
    X_test  = [X[i] for i in test_idx]
    y_test  = [y[i] for i in test_idx]

    model = train(X_train, y_train, meta=[meta[i] for i in train_idx])
    result = evaluate(model, X_test, y_test)
    baseline_pct = round(max(sum(y_test), len(y_test) - sum(y_test)) / len(y_test) * 100, 1) if y_test else None
    info["accuracy_pct"] = result["accuracy_pct"]
    info["baseline_pct"] = baseline_pct
    info["n_test"] = result["n"]

    # The model must beat two separate bars: an absolute floor (not pure
    # noise) AND the naive majority-class baseline by a real margin -- a model
    # that merely matches "always guess the common outcome" has learned
    # nothing from the features and must not be saved as if it were a signal.
    # This caught a real case during development: an earlier, buggy model
    # config scored exactly equal to baseline (67.7% == 67.7%) and would have
    # been saved and silently logged as "ML signal" in shadow mode forever.
    beats_baseline = (
        result["accuracy_pct"] is not None and baseline_pct is not None
        and result["accuracy_pct"] >= baseline_pct + 3.0
    )
    clears_floor = result["accuracy_pct"] is not None and result["accuracy_pct"] >= MIN_HOLDOUT_ACCURACY_PCT
    clears_test_size = result["n"] >= MIN_HOLDOUT_TEST_SAMPLES

    if not (beats_baseline and clears_floor and clears_test_size):
        if not clears_test_size:
            info["reason"] = (
                f"holdout test set too small to trust ({result['n']} samples, "
                f"need >= {MIN_HOLDOUT_TEST_SAMPLES}) -- its {result['accuracy_pct']}% could easily be chance"
            )
        else:
            info["reason"] = (
                f"did not beat the {baseline_pct}% majority-class baseline by a real margin"
                if not beats_baseline else f"did not clear the {MIN_HOLDOUT_ACCURACY_PCT}% absolute floor"
            )
        return None, info

    # Re-fit on ALL data (train+test) before returning -- the holdout split
    # was only to get an honest accuracy number; the saved model should use
    # every available sample.
    final_model = train(X, y, meta=meta)
    info["saved"] = True
    return final_model, info


def main() -> None:
    p = argparse.ArgumentParser(description="Train the Phase 4 / Component 6 ML signal model(s)")
    p.add_argument("--bulk", action="store_true",
                   help="Also generate training data directly from real historical price bars "
                        "(no Gemini call needed) -- see ml_feature_extractor.generate_bulk_training_data")
    p.add_argument("--symbols", default="SPY,TSLA,AAPL,MSFT,NVDA,AMZN,GOOGL,META,QQQ,IWM")
    p.add_argument("--horizons", default="7,14,30,45")
    p.add_argument("--months-back", type=int, default=24)
    p.add_argument("--top-sp500", action="store_true")
    p.add_argument("--max-samples", type=int, default=2000)
    p.add_argument("--sample-freq", default="monthly", choices=["monthly", "weekly"],
                   help="Origin sampling density (default: monthly). Per-segment models need far more "
                        "density than monthly sampling provides -- a 24-month monthly sweep across 10 "
                        "symbols x 4 horizons yields only ~5-14 samples per segment, well under the "
                        "30-sample floor; weekly sampling is ~4x denser for the same months_back.")
    p.add_argument("--no-segments", action="store_true",
                   help="Train only the single global model (pre-Component-6 behavior), skip per-segment models")
    args = p.parse_args()

    from ml_feature_extractor import extract_from_db_records, generate_bulk_training_data
    from ml_signal_model import save_model, SegmentedModel, MIN_TRAINING_SAMPLES
    from segment_reliability import segment_label as _segment_label_fn
    from gemini_stock_prediction_agent import _load_calibration_source_records

    db_records = _load_calibration_source_records()
    X, y, feature_names, meta = extract_from_db_records(db_records)
    print(f"From DB records (ai_prediction_raw._feature_packet): {len(X)} usable rows")

    if args.bulk:
        from batch_validation_runner import TOP_SP500_SYMBOLS
        symbols = TOP_SP500_SYMBOLS if args.top_sp500 else [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        horizons = [int(h.strip()) for h in args.horizons.split(",") if h.strip()]
        print(f"Generating bulk training data: {len(symbols)} symbols x {len(horizons)} horizons x "
              f"{args.months_back} months back ({args.sample_freq} sampling) ...")
        bulk_X, bulk_y, _names, bulk_meta = generate_bulk_training_data(
            symbols, horizons, months_back=args.months_back, sample_freq=args.sample_freq,
            max_samples=args.max_samples, verbose=False,
        )
        print(f"From bulk generation: {len(bulk_X)} usable rows")
        X += bulk_X
        y += bulk_y
        meta += bulk_meta

    print(f"\nTotal training rows: {len(X)} (need >= {MIN_TRAINING_SAMPLES} to train at all)")
    if len(X) < MIN_TRAINING_SAMPLES:
        print("Not enough data to train. Re-run with --bulk and/or a larger --months-back/--symbols.")
        return

    print("\n-- Global model (all data blended) --------------------------------------")
    default_model, global_info = _train_and_gate(X, y, meta, "GLOBAL")
    print(f"  n={global_info['n_total']}  holdout={global_info.get('accuracy_pct')}%  "
          f"baseline={global_info.get('baseline_pct')}%  saved={global_info['saved']}"
          + (f"  ({global_info.get('reason')})" if not global_info["saved"] else ""))

    segment_models: dict = {}
    if not args.no_segments:
        print("\n-- Per-segment models -----------------------------------------------------")
        groups: dict = {}
        for i in range(len(X)):
            sym = meta[i].get("symbol") or ""
            horizon = meta[i].get("horizon_days")
            seg = _segment_label_fn(sym, horizon)
            groups.setdefault(seg, []).append(i)

        for seg, idxs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            seg_X = [X[i] for i in idxs]
            seg_y = [y[i] for i in idxs]
            seg_meta = [meta[i] for i in idxs]
            seg_model, seg_info = _train_and_gate(seg_X, seg_y, seg_meta, seg)
            status = (
                f"saved (holdout={seg_info.get('accuracy_pct')}% vs baseline={seg_info.get('baseline_pct')}%)"
                if seg_info["saved"] else f"not saved -- falls back to global ({seg_info.get('reason')})"
            )
            print(f"  {seg:16s} n={seg_info['n_total']:4d}  {status}")
            if seg_model is not None:
                segment_models[seg] = seg_model

    if default_model is None and not segment_models:
        print("\nNothing cleared the save gate -- no model file written. "
              "This is an honest negative result, not a bug; data/ml_signal_model.pkl is left untouched.")
        return

    # Never let a retrain silently destroy a previously-validated segment just
    # because this run's data composition didn't happen to reproduce it (e.g.
    # the segment's rows got diluted by newer, unrelated DB records, or this
    # run used a different --bulk mix). Confirmed real: an earlier retrain on
    # this exact codebase dropped 4 of 5 live-validated segments this way.
    # A segment is only ever replaced if THIS run's model for it also clears
    # the save gate; segments this run has no data for at all are carried
    # forward untouched. Only an explicit --no-segments run intentionally
    # drops segment models (that's its documented purpose).
    kept_from_previous = 0
    if not args.no_segments:
        try:
            from ml_signal_model import load_model as _load_existing_model
            existing = _load_existing_model()
        except Exception:
            existing = None
        if existing is not None and getattr(existing, "models", None):
            for seg, old_model in existing.models.items():
                if seg not in segment_models:
                    segment_models[seg] = old_model
                    kept_from_previous += 1
    if default_model is None:
        try:
            from ml_signal_model import load_model as _load_existing_model2
            existing2 = _load_existing_model2()
        except Exception:
            existing2 = None
        if existing2 is not None and getattr(existing2, "default_model", None) is not None:
            default_model = existing2.default_model
            print("  (global fallback did not clear the gate this run -- keeping the previously-saved one)")

    combined = SegmentedModel(models=segment_models, default_model=default_model)
    save_model(combined)
    new_this_run = len(segment_models) - kept_from_previous
    print(f"\nSaved to data/ml_signal_model.pkl -- {len(segment_models)} segment-specific model(s) total "
          f"({new_this_run} new/updated this run, {kept_from_previous} carried forward unchanged from the "
          f"previous save since this run had no qualifying replacement for them)"
          + (", plus a global fallback" if default_model is not None else ", no global fallback (it didn't clear the gate either)"))


if __name__ == "__main__":
    main()
