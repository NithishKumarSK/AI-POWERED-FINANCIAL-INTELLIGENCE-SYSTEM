"""
Tests for scripts/adhoc/llm_memorization_risk_check.py -- to-do item #7's
now-executable LLM memorization risk test, bucketed against the real,
primary-source Gemini 3.7 Flash knowledge cutoff bounds (Google DeepMind's
own model card, fetched and read directly this session).

Pure-function tests only (bucketing, z-test math, stats, verdict wording) --
no DB access, no real records required.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "adhoc"))

import llm_memorization_risk_check as mrc  # noqa: E402


def _comp(decision_match: bool, directional_match: bool, return_error_pct: float = 1.0) -> dict:
    return {
        "decision_match": decision_match,
        "directional_match": directional_match,
        "return_error_pct": return_error_pct,
    }


# ── _bucket_of: boundary correctness ─────────────────────────────────────────

def test_bucket_before_conservative_cutoff():
    assert mrc._bucket_of("2024-12-31") == "pre_jan2025_plausibly_memorized"


def test_bucket_on_conservative_cutoff_is_ambiguous_not_pre():
    """On-the-boundary date belongs to the AMBIGUOUS zone, not pre-cutoff --
    the pre-cutoff bucket is strictly BEFORE 2025-01-01."""
    assert mrc._bucket_of("2025-01-01") == "jan2025_to_mar2026_ambiguous"


def test_bucket_just_before_generous_cutoff():
    assert mrc._bucket_of("2026-02-28") == "jan2025_to_mar2026_ambiguous"


def test_bucket_on_generous_cutoff_is_genuinely_unseen():
    assert mrc._bucket_of("2026-03-01") == "post_mar2026_genuinely_unseen"


def test_bucket_far_future():
    assert mrc._bucket_of("2027-01-01") == "post_mar2026_genuinely_unseen"


# ── _two_proportion_z_test ────────────────────────────────────────────────────

def test_z_test_identical_proportions_gives_zero():
    z, p = mrc._two_proportion_z_test(0.5, 100, 0.5, 100)
    assert z == 0.0
    assert p == 1.0


def test_z_test_large_gap_large_samples_is_significant():
    z, p = mrc._two_proportion_z_test(0.80, 500, 0.40, 500)
    assert abs(z) >= 1.96
    assert p < 0.05


def test_z_test_small_gap_small_samples_not_significant():
    # Mirrors this project's real finding: ~9pp gap, n=23 vs n=389.
    z, p = mrc._two_proportion_z_test(0.435, 23, 0.344, 389)
    assert abs(z) < 1.96
    assert p > 0.05


def test_z_test_zero_n_returns_none():
    z, p = mrc._two_proportion_z_test(0.5, 0, 0.5, 100)
    assert z is None and p is None


# ── _bucket_stats ─────────────────────────────────────────────────────────────

def test_bucket_stats_empty():
    assert mrc._bucket_stats([]) == {"n": 0}


def test_bucket_stats_basic_rates():
    comps = [
        _comp(True, True, 2.0),
        _comp(True, True, 4.0),
        _comp(False, True, 6.0),
        _comp(False, False, 8.0),
    ]
    stats = mrc._bucket_stats(comps)
    assert stats["n"] == 4
    assert stats["decision_match_pct"] == 50.0
    assert stats["direction_match_pct"] == 75.0
    assert stats["avg_abs_return_error_pp"] == 5.0


def test_bucket_stats_missing_return_error_excluded_from_avg():
    comps = [_comp(True, True, None), _comp(True, True, 10.0)]
    stats = mrc._bucket_stats(comps)
    assert stats["avg_abs_return_error_pp"] == 10.0


# ── run(): end-to-end with a monkeypatched record source ────────────────────

def test_run_reports_inconclusive_when_pre_cutoff_bucket_too_small(monkeypatch):
    def fake_load(limit=5000):
        records = []
        # Only 3 pre-cutoff records -- below the n>=20 threshold.
        for _ in range(3):
            records.append({
                "stock_prediction_input": {"target_date": "2024-06-01"},
                "actual_validation": {},
                "comparison": _comp(True, True, 1.0),
            })
        for _ in range(50):
            records.append({
                "stock_prediction_input": {"target_date": "2026-06-01"},
                "actual_validation": {},
                "comparison": _comp(True, True, 1.0),
            })
        return records

    import stock_prediction_repository as spr
    monkeypatch.setattr(spr, "load_stock_prediction_records", fake_load)

    report = mrc.run()
    assert "INCONCLUSIVE-BY-SAMPLE-SIZE" in report["verdict"]
    assert report["buckets"]["pre_jan2025_plausibly_memorized"]["n"] == 3
    assert report["buckets"]["post_mar2026_genuinely_unseen"]["n"] == 50


def test_run_skips_records_with_no_target_date(monkeypatch):
    def fake_load(limit=5000):
        return [
            {"stock_prediction_input": {}, "actual_validation": {}, "comparison": _comp(True, True)},
            {"stock_prediction_input": {"target_date": "2026-06-01"}, "actual_validation": {}, "comparison": _comp(True, True)},
        ]

    import stock_prediction_repository as spr
    monkeypatch.setattr(spr, "load_stock_prediction_records", fake_load)

    report = mrc.run()
    assert report["records_skipped_no_target_date"] == 1
    assert report["records_considered"] == 2


def test_run_uses_effective_target_date_over_raw_target_date(monkeypatch):
    """actual_validation.effective_target_date must take priority over
    stock_prediction_input.target_date when both are present (the former
    is the real resolved date; the latter can be the originally-requested
    date before any trading-day adjustment)."""
    def fake_load(limit=5000):
        return [{
            "stock_prediction_input": {"target_date": "2024-01-01"},
            "actual_validation": {"effective_target_date": "2026-06-01"},
            "comparison": _comp(True, True),
        }]

    import stock_prediction_repository as spr
    monkeypatch.setattr(spr, "load_stock_prediction_records", fake_load)

    report = mrc.run()
    assert report["buckets"]["post_mar2026_genuinely_unseen"]["n"] == 1
    assert "pre_jan2025_plausibly_memorized" not in report["buckets"]
