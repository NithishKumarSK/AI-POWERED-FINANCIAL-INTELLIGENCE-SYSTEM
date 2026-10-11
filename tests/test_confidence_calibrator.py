"""Tests for core/confidence_calibrator.py -- Phase 1 of the accuracy
improvement program: mapping the AI's self-reported confidence_score to what
predictions at that stated confidence have ACTUALLY been right, since this
session's own live DB query found raw confidence inversely correlated with
correctness (80-100% stated -> 40.0% actual direction match, n=25;
40-59% stated -> 62.1% actual, n=29)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _rec(confidence, directional_match):
    return {
        "ai_prediction": {"confidence_score": confidence},
        "comparison": {"directional_match": directional_match},
    }


# ── fit_calibration_map ───────────────────────────────────────────────────────

def test_fit_calibration_map_empty_records():
    from confidence_calibrator import fit_calibration_map
    result = fit_calibration_map([])
    assert result == {"bins": [], "overall_hit_rate": None, "n_total": 0}


def test_fit_calibration_map_skips_records_missing_fields():
    from confidence_calibrator import fit_calibration_map
    records = [
        {"ai_prediction": {}, "comparison": {"directional_match": True}},   # missing confidence
        {"ai_prediction": {"confidence_score": 70}, "comparison": {}},       # missing directional_match
        _rec(70, True),
    ]
    result = fit_calibration_map(records)
    assert result["n_total"] == 1


def test_fit_calibration_map_overall_hit_rate():
    from confidence_calibrator import fit_calibration_map
    records = [_rec(70, True)] * 3 + [_rec(70, False)] * 1
    result = fit_calibration_map(records)
    assert result["overall_hit_rate"] == 75.0
    assert result["n_total"] == 4


def test_fit_calibration_map_sparse_bins_merge():
    """A bin with fewer than min_n samples must merge into a neighbor rather
    than report a noisy rate from e.g. n=1."""
    from confidence_calibrator import fit_calibration_map
    records = (
        [_rec(10, True)]            # 1 record in [0,40) -- too sparse alone
        + [_rec(50, True)] * 10     # plenty in [40,60)
    )
    result = fit_calibration_map(records, min_n=5)
    # The sparse [0,40) bin must have merged forward into [40,60) -- so there
    # should be exactly one bin covering [0,60), not two separate ones.
    assert len(result["bins"]) == 1
    assert result["bins"][0]["lo"] == 0
    assert result["bins"][0]["n"] == 11


def test_fit_calibration_map_bin_boundaries_half_open():
    from confidence_calibrator import fit_calibration_map, DEFAULT_BIN_EDGES
    # exactly 40 must land in the [40,60) bin, not [0,40)
    records = [_rec(40, True)] * 6 + [_rec(39, False)] * 6
    result = fit_calibration_map(records, min_n=5)
    bin_40 = next(b for b in result["bins"] if b["lo"] == 40)
    assert bin_40["n"] == 6
    assert bin_40["hit_rate"] == 100.0


def test_fit_calibration_map_handles_confidence_100():
    """A raw confidence of exactly 100 must fall inside the last bin, not be dropped."""
    from confidence_calibrator import fit_calibration_map
    records = [_rec(100, True)] * 6
    result = fit_calibration_map(records, min_n=5)
    assert result["n_total"] == 6
    assert sum(b["n"] for b in result["bins"]) == 6


def test_fit_calibration_map_proves_inverted_confidence():
    """Reproduce this session's real finding structurally: a mid-confidence
    bucket that's MORE often right than a high-confidence bucket."""
    from confidence_calibrator import fit_calibration_map
    records = (
        [_rec(50, True)] * 6 + [_rec(50, False)] * 4    # mid: 60% hit rate
        + [_rec(90, True)] * 4 + [_rec(90, False)] * 6   # high: 40% hit rate
    )
    result = fit_calibration_map(records, min_n=5)
    mid_bin = next(b for b in result["bins"] if b["lo"] <= 50 < b["hi"])
    high_bin = next(b for b in result["bins"] if b["lo"] <= 90 < b["hi"])
    assert mid_bin["hit_rate"] > high_bin["hit_rate"]


# ── calibrate ──────────────────────────────────────────────────────────────

def test_calibrate_returns_bin_hit_rate():
    from confidence_calibrator import fit_calibration_map, calibrate
    records = [_rec(90, True)] * 2 + [_rec(90, False)] * 8  # 20% hit rate at high confidence
    cal_map = fit_calibration_map(records, min_n=5)
    assert calibrate(90, cal_map) == 20.0


def test_calibrate_none_confidence_falls_back_to_overall():
    from confidence_calibrator import fit_calibration_map, calibrate
    records = [_rec(70, True)] * 7 + [_rec(70, False)] * 3
    cal_map = fit_calibration_map(records, min_n=5)
    assert calibrate(None, cal_map) == cal_map["overall_hit_rate"]


def test_calibrate_no_map_returns_none():
    from confidence_calibrator import calibrate
    assert calibrate(70, None) is None
    assert calibrate(70, {}) is None


def test_calibrate_out_of_range_low_clamps_to_first_bin():
    from confidence_calibrator import fit_calibration_map, calibrate
    records = [_rec(50, True)] * 6
    cal_map = fit_calibration_map(records, min_n=5)
    # -5 isn't a valid confidence but must degrade gracefully, not crash
    assert calibrate(-5, cal_map) == cal_map["bins"][0]["hit_rate"]
