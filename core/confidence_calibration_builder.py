"""
confidence_calibration_builder.py — CLI to (re)fit the confidence calibration
map from the live, shared DB and write the static snapshot that
build_calibration_summary() reads (same "static JSON snapshot" convention
already used for data/calibration_profiles.json -- must be re-run
periodically as the ledger grows, same staleness caveat as that file).

Usage:
    python core/confidence_calibration_builder.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_paths
bootstrap_paths.add_module_paths()

OUT_PATH = ROOT / "data" / "confidence_calibration_map.json"


def build_and_save(out_path: Path = OUT_PATH) -> dict:
    from gemini_stock_prediction_agent import _load_calibration_source_records
    from confidence_calibrator import fit_calibration_map

    # Same source-of-truth function build_calibration_summary() itself uses
    # (DB first, local-JSONL fallback) -- keeps this builder and the live
    # prediction path reading from the identical record set.
    records = _load_calibration_source_records()
    calibration_map = fit_calibration_map(records)
    calibration_map["generated_at"] = datetime.utcnow().isoformat()
    calibration_map["source_record_count"] = len(records)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(calibration_map, indent=2, ensure_ascii=False), encoding="utf-8")
    return calibration_map


def _print_summary(calibration_map: dict) -> None:
    print("-- Confidence Calibration Map ------------------------------------------")
    print(f"  Source records:     {calibration_map.get('source_record_count')}")
    print(f"  Usable (conf+dm):   {calibration_map.get('n_total')}")
    print(f"  Overall hit rate:   {calibration_map.get('overall_hit_rate')}%")
    for b in calibration_map.get("bins", []):
        print(f"  confidence [{b['lo']:3d}-{b['hi']:3d}) n={b['n']:3d}  hit_rate={b['hit_rate']}%")
    print("-------------------------------------------------------------------------")


if __name__ == "__main__":
    cal = build_and_save()
    _print_summary(cal)
    print(f"\nWritten to {OUT_PATH}")
