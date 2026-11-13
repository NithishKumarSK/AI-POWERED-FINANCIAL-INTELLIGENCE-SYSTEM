"""
conformal_range_builder.py -- CLI to (re)fit the conformal range-widening
multiplier from data/price_range_calibration_source.json (the real,
live-measured predicted-vs-actual low/high price dataset built this
session: 304 validated predictions with both a predicted range and a
resolvable real outcome), and write the static snapshot the live prediction
path reads (same "static JSON snapshot" convention as
confidence_calibration_builder.py / magnitude_calibration_builder.py).

The source file is a one-off export (re-fetching real price history for
every symbol is the expensive part, ~85 provider calls) -- regenerating it
requires re-running the price-range fetch, not just this builder. This
builder re-derives the MULTIPLIER from whatever source data currently
exists, cheaply (pure arithmetic).

Usage:
    python core/conformal_range_builder.py
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

SOURCE_PATH = ROOT / "data" / "price_range_calibration_source.json"
OUT_PATH = ROOT / "data" / "conformal_range_calibration.json"

TARGET_COVERAGES = (0.80, 0.90, 0.95)


def build_and_save(source_path: Path = SOURCE_PATH, out_path: Path = OUT_PATH) -> dict:
    from conformal_range_calibrator import fit_conformal_multiplier

    if not source_path.exists():
        raise FileNotFoundError(
            f"{source_path} not found -- run the price-range fetch "
            "(build_price_range_data.py + fix_price_range_merge.py) first."
        )
    data = json.loads(source_path.read_text(encoding="utf-8"))
    cases = data.get("cases", [])

    by_coverage = {}
    for target in TARGET_COVERAGES:
        by_coverage[str(target)] = fit_conformal_multiplier(cases, target_coverage=target)

    out = {
        "by_target_coverage": by_coverage,
        "generated_at": datetime.utcnow().isoformat(),
        "source_case_count": len(cases),
        "source_file": str(source_path.name),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _print_summary(result: dict) -> None:
    print("-- Conformal Range Calibration ------------------------------------------")
    print(f"  Source cases:  {result.get('source_case_count')}")
    for target, fit in result["by_target_coverage"].items():
        print(f"  target={target}  n={fit['n']:3d}  raw_coverage={fit['raw_coverage_pct']}%  "
              f"multiplier={fit['multiplier']}  calibrated_coverage={fit['calibrated_coverage_on_calibration_set_pct']}%")
    print("--------------------------------------------------------------------------")


if __name__ == "__main__":
    result = build_and_save()
    _print_summary(result)
    print(f"\nWritten to {OUT_PATH}")
