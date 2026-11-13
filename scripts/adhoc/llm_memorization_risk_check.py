"""
llm_memorization_risk_check.py — to-do item #7: test for LLM memorization
risk (per the "Profit Mirage" paper methodology), finally executable.

Earlier attempts this session could not responsibly run this test: no
reliable, authoritative source gave Gemini 3.7 Flash's actual training
knowledge cutoff (conflicting third-party blog claims, no primary source).
That changed -- Google DeepMind's own model card (fetched and read directly
from the PDF, not a secondary summary) states on page 6:

    "The knowledge cutoff date for Gemini 3.7 Flash is March 2026 -- users
    can expect updated information for some domains while in others they
    may experience the model's knowledge is limited to January 2025 (in
    line with the Gemini 3 Model Family)."
    Source: https://storage.googleapis.com/deepmind-media/Model-Cards/Gemini-3-7-Flash-Model-Card.pdf

That gives two real, citable bounds:
  - January 2025: the CONSERVATIVE cutoff. A prediction target_date before
    this is the only group where memorization is even plausible across
    every domain.
  - March 2026: the GENEROUS upper bound. A prediction target_date on/after
    this is GUARANTEED genuinely unseen by the model at training time,
    regardless of domain -- the real outcome hadn't happened yet.

METHODOLOGY (same spirit as the "Profit Mirage" paper): bucket this
project's own real, resolved DB predictions by where their target_date
falls relative to those two bounds, and compare decision_match /
direction_match / return-error rates across buckets. If memorization were
meaningfully inflating this project's reported accuracy, the
pre-January-2025 bucket (plausibly memorized) should show materially better
results than the post-March-2026 bucket (genuinely unseen) -- a real,
testable, falsifiable prediction, not a hand-wave.

STATISTICAL HONESTY: a two-proportion z-test is run between the
pre-cutoff and post-cutoff buckets for both decision_match and
direction_match. The pre-cutoff bucket is typically small (this project's
real-world test data skews toward recent dates), so the test explicitly
reports whether any observed gap clears conventional significance
(|z| >= 1.96, p < 0.05) rather than treating a raw percentage-point
difference as proof either way -- a small-sample gap that looks dramatic
in isolation is not evidence without this check.

This script is read-only (never modifies the DB) and safe to re-run as the
DB grows -- each re-run gets more statistical power as more genuinely-
unseen (post-cutoff) predictions resolve, since real-world dates keep
advancing past the cutoff while the cutoff itself is fixed.

Usage:
    python scripts/adhoc/llm_memorization_risk_check.py
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "db"))

import bootstrap_paths  # noqa: E402
bootstrap_paths.add_module_paths()

OUT_PATH = ROOT / "data" / "llm_memorization_risk_report.json"

CONSERVATIVE_CUTOFF = "2025-01-01"  # before this: plausibly memorized, every domain
GENEROUS_CUTOFF      = "2026-03-01"  # on/after this: guaranteed genuinely unseen

MODEL_CARD_SOURCE = (
    "https://storage.googleapis.com/deepmind-media/Model-Cards/Gemini-3-7-Flash-Model-Card.pdf"
)
MODEL_CARD_QUOTE = (
    "The knowledge cutoff date for Gemini 3.7 Flash is March 2026 -- users can expect "
    "updated information for some domains while in others they may experience the "
    "model's knowledge is limited to January 2025 (in line with the Gemini 3 Model Family)."
)


def _bucket_of(target_date: str) -> str:
    if target_date < CONSERVATIVE_CUTOFF:
        return "pre_jan2025_plausibly_memorized"
    elif target_date < GENEROUS_CUTOFF:
        return "jan2025_to_mar2026_ambiguous"
    else:
        return "post_mar2026_genuinely_unseen"


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _two_proportion_z_test(p1: float, n1: int, p2: float, n2: int):
    """Returns (z, two_tailed_p_value). None if either n is 0."""
    if n1 == 0 or n2 == 0:
        return None, None
    p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (p1 - p2) / se
    p_value = 2 * (1 - _norm_cdf(abs(z)))
    return round(z, 3), round(p_value, 4)


def _bucket_stats(comps: list) -> dict:
    n = len(comps)
    if n == 0:
        return {"n": 0}
    dm = sum(1 for c in comps if c.get("decision_match") is True)
    dirm = sum(1 for c in comps if c.get("directional_match") is True)
    errs = [abs(c["return_error_pct"]) for c in comps if c.get("return_error_pct") is not None]
    return {
        "n": n,
        "decision_match_pct": round(dm / n * 100, 1),
        "direction_match_pct": round(dirm / n * 100, 1),
        "avg_abs_return_error_pp": round(sum(errs) / len(errs), 2) if errs else None,
        "_dm_rate": dm / n,
        "_dirm_rate": dirm / n,
    }


def run() -> dict:
    from stock_prediction_repository import load_stock_prediction_records

    records = load_stock_prediction_records(limit=5000)
    groups = defaultdict(list)
    skipped_no_date = 0

    for r in records:
        spi = r.get("stock_prediction_input") or {}
        av = r.get("actual_validation") or {}
        comp = r.get("comparison") or {}
        target_date = av.get("effective_target_date") or spi.get("target_date")
        if not target_date:
            skipped_no_date += 1
            continue
        groups[_bucket_of(target_date)].append(comp)

    buckets = {name: _bucket_stats(comps) for name, comps in groups.items()}

    pre = buckets.get("pre_jan2025_plausibly_memorized", {"n": 0})
    post = buckets.get("post_mar2026_genuinely_unseen", {"n": 0})

    dm_z, dm_p = (None, None)
    dir_z, dir_p = (None, None)
    if pre.get("n", 0) > 0 and post.get("n", 0) > 0:
        dm_z, dm_p = _two_proportion_z_test(pre["_dm_rate"], pre["n"], post["_dm_rate"], post["n"])
        dir_z, dir_p = _two_proportion_z_test(pre["_dirm_rate"], pre["n"], post["_dirm_rate"], post["n"])

    significant = (dm_z is not None and abs(dm_z) >= 1.96) or (dir_z is not None and abs(dir_z) >= 1.96)

    if pre.get("n", 0) < 20:
        verdict = (
            f"INCONCLUSIVE-BY-SAMPLE-SIZE: only {pre.get('n', 0)} predictions fall in the "
            "plausibly-memorized bucket (target_date before 2025-01-01) -- too few for a "
            "reliable statistical read either way. Re-run this script periodically; it will "
            "not gain power for THIS bucket (its date range is fixed in the past), but the "
            "genuinely-unseen bucket will keep growing, which is itself reassuring context."
        )
    elif significant and pre.get("decision_match_pct", 0) > post.get("decision_match_pct", 0):
        verdict = (
            "SIGNIFICANT GAP FOUND, consistent with memorization risk: the plausibly-memorized "
            "bucket shows materially and statistically significantly higher match rates than the "
            "genuinely-unseen bucket. This project's headline accuracy numbers should be reported "
            "with this caveat until investigated further."
        )
    else:
        verdict = (
            "NO STATISTICALLY SIGNIFICANT MEMORIZATION SIGNAL: any gap between the "
            "plausibly-memorized and genuinely-unseen buckets is within the range expected from "
            "sampling noise at this sample size (|z| < 1.96 for both decision_match and "
            "direction_match). This project's real, measured accuracy on the large "
            "genuinely-unseen bucket is not meaningfully different from the small "
            "plausibly-memorized bucket, which is evidence AGAINST memorization being a "
            "material driver of this project's reported numbers -- not proof of its absence, "
            "since the plausibly-memorized sample is small."
        )

    # Drop internal helper keys before reporting/saving.
    for b in buckets.values():
        b.pop("_dm_rate", None)
        b.pop("_dirm_rate", None)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_card_source": MODEL_CARD_SOURCE,
        "model_card_quote": MODEL_CARD_QUOTE,
        "conservative_cutoff": CONSERVATIVE_CUTOFF,
        "generous_cutoff": GENEROUS_CUTOFF,
        "records_considered": len(records),
        "records_skipped_no_target_date": skipped_no_date,
        "buckets": buckets,
        "two_proportion_z_test": {
            "decision_match":  {"z": dm_z, "p_value": dm_p},
            "direction_match": {"z": dir_z, "p_value": dir_p},
            "significance_threshold": "|z| >= 1.96 (p < 0.05)",
        },
        "verdict": verdict,
    }
    return report


def _print_report(report: dict) -> None:
    print("-- LLM Memorization Risk Check (to-do item #7) -------------------------")
    print(f"  Source: {report['model_card_source']}")
    print(f"  Quote:  \"{report['model_card_quote']}\"")
    print(f"  Records considered: {report['records_considered']} "
          f"(skipped {report['records_skipped_no_target_date']} with no target_date)")
    print()
    for name, stats in report["buckets"].items():
        if stats.get("n", 0) == 0:
            print(f"  {name}: n=0")
            continue
        print(f"  {name}: n={stats['n']}  decision_match={stats['decision_match_pct']}%  "
              f"direction_match={stats['direction_match_pct']}%  "
              f"avg_abs_return_err={stats['avg_abs_return_error_pp']}pp")
    print()
    zt = report["two_proportion_z_test"]
    print(f"  decision_match z={zt['decision_match']['z']}  p={zt['decision_match']['p_value']}")
    print(f"  direction_match z={zt['direction_match']['z']}  p={zt['direction_match']['p_value']}")
    print()
    print(f"  VERDICT: {report['verdict']}")
    print("-------------------------------------------------------------------------")


if __name__ == "__main__":
    rep = run()
    _print_report(rep)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(f"\nWritten to {OUT_PATH}")
