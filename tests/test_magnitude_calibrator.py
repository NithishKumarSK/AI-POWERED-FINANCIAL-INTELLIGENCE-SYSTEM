"""Tests for core/magnitude_calibrator.py -- the signal-quality layer:
this session's own live DB (744 validated predictions) found predicted-move
SIZE inversely related to correctness (<2% predicted move -> 73.6% direction
match, n=129; 2-5% -> 48.9%, n=350; >5% -> 48.3%, n=265), mirroring the
already-fixed inverted-confidence pattern."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _rec(predicted_return_pct, directional_match):
    return {
        "ai_prediction": {"predicted_return_pct": predicted_return_pct},
        "comparison": {"directional_match": directional_match},
    }


# ── fit_magnitude_calibration_map ───────────────────────────────────────────

def test_fit_magnitude_calibration_map_empty_records():
    from magnitude_calibrator import fit_magnitude_calibration_map
    result = fit_magnitude_calibration_map([])
    assert result == {"bins": [], "overall_hit_rate": None, "n_total": 0}


def test_fit_magnitude_calibration_map_skips_records_missing_fields():
    from magnitude_calibrator import fit_magnitude_calibration_map
    records = [
        {"ai_prediction": {}, "comparison": {"directional_match": True}},
        {"ai_prediction": {"predicted_return_pct": 3.0}, "comparison": {}},
        _rec(3.0, True),
    ]
    result = fit_magnitude_calibration_map(records)
    assert result["n_total"] == 1


def test_fit_magnitude_calibration_map_bins_by_absolute_value():
    """A negative predicted_return_pct must bin on its magnitude, not sign."""
    from magnitude_calibrator import fit_magnitude_calibration_map
    records = [_rec(-1.0, True)] * 6
    result = fit_magnitude_calibration_map(records, min_n=5)
    bin0 = next(b for b in result["bins"] if b["lo"] == 0)
    assert bin0["n"] == 6
    assert bin0["hit_rate"] == 100.0


def test_fit_magnitude_calibration_map_proves_inverted_magnitude():
    """Reproduce this session's real finding structurally: small predicted
    moves more often right than large predicted moves."""
    from magnitude_calibrator import fit_magnitude_calibration_map
    records = (
        [_rec(1.0, True)] * 7 + [_rec(1.0, False)] * 3     # small move: 70% hit
        + [_rec(8.0, True)] * 3 + [_rec(8.0, False)] * 7    # big move: 30% hit
    )
    result = fit_magnitude_calibration_map(records, min_n=5)
    small_bin = next(b for b in result["bins"] if b["lo"] <= 1.0 < b["hi"])
    big_bin = next(b for b in result["bins"] if b["lo"] <= 8.0 < b["hi"])
    assert small_bin["hit_rate"] > big_bin["hit_rate"]


def test_fit_magnitude_calibration_map_sparse_bins_merge():
    from magnitude_calibrator import fit_magnitude_calibration_map
    records = [_rec(1.0, True)] + [_rec(3.0, True)] * 10
    result = fit_magnitude_calibration_map(records, min_n=5)
    assert len(result["bins"]) == 1
    assert result["bins"][0]["n"] == 11


# ── calibrate_magnitude ─────────────────────────────────────────────────────

def test_calibrate_magnitude_returns_bin_hit_rate():
    from magnitude_calibrator import fit_magnitude_calibration_map, calibrate_magnitude
    records = [_rec(8.0, True)] * 2 + [_rec(8.0, False)] * 8
    cal_map = fit_magnitude_calibration_map(records, min_n=5)
    assert calibrate_magnitude(8.0, cal_map) == 20.0


def test_calibrate_magnitude_uses_absolute_value():
    from magnitude_calibrator import fit_magnitude_calibration_map, calibrate_magnitude
    records = [_rec(8.0, True)] * 2 + [_rec(8.0, False)] * 8
    cal_map = fit_magnitude_calibration_map(records, min_n=5)
    assert calibrate_magnitude(-8.0, cal_map) == calibrate_magnitude(8.0, cal_map)


def test_calibrate_magnitude_none_falls_back_to_overall():
    from magnitude_calibrator import fit_magnitude_calibration_map, calibrate_magnitude
    records = [_rec(3.0, True)] * 7 + [_rec(3.0, False)] * 3
    cal_map = fit_magnitude_calibration_map(records, min_n=5)
    assert calibrate_magnitude(None, cal_map) == cal_map["overall_hit_rate"]


def test_calibrate_magnitude_no_map_returns_none():
    from magnitude_calibrator import calibrate_magnitude
    assert calibrate_magnitude(3.0, None) is None
    assert calibrate_magnitude(3.0, {}) is None


# ── signal_quality_tier ──────────────────────────────────────────────────────

def test_signal_quality_tier_both_missing():
    from magnitude_calibrator import signal_quality_tier
    result = signal_quality_tier(None, None)
    assert result == {"signal_quality_score": None, "signal_quality_tier": "UNKNOWN"}


def test_signal_quality_tier_strong():
    from magnitude_calibrator import signal_quality_tier, STRONG_THRESHOLD_PCT
    result = signal_quality_tier(STRONG_THRESHOLD_PCT, STRONG_THRESHOLD_PCT + 5)
    assert result["signal_quality_tier"] == "STRONG"


def test_signal_quality_tier_weak():
    from magnitude_calibrator import signal_quality_tier, WEAK_THRESHOLD_PCT
    result = signal_quality_tier(WEAK_THRESHOLD_PCT - 1, 90.0)
    assert result["signal_quality_tier"] == "WEAK"


def test_signal_quality_tier_takes_the_weaker_input_not_average():
    """A strong confidence calibration must NOT mask a weak magnitude
    calibration (or vice versa) -- the tier reflects the weakest link."""
    from magnitude_calibrator import signal_quality_tier
    result = signal_quality_tier(95.0, 20.0)
    assert result["signal_quality_score"] == 20.0
    assert result["signal_quality_tier"] == "WEAK"


def test_signal_quality_tier_one_input_missing_uses_the_other():
    from magnitude_calibrator import signal_quality_tier
    result = signal_quality_tier(None, 70.0)
    assert result["signal_quality_score"] == 70.0
    assert result["signal_quality_tier"] == "STRONG"
