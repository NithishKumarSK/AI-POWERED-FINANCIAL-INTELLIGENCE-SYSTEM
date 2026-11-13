"""Tests for core/conformal_range_calibrator.py -- split-conformal widening
for the deterministic price-range predictor. Real session finding: raw band
containment was 79.9% (n=304); this calibrates a widening multiplier to hit
a chosen target coverage (e.g. 90%, 95%) from that same real data."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _case(pl, ph, al, ah):
    return {"predicted_low_price": pl, "predicted_high_price": ph,
            "actual_low_price": al, "actual_high_price": ah}


# ── _nonconformity_ratio ─────────────────────────────────────────────────────

def test_nonconformity_ratio_already_covered_is_one():
    from conformal_range_calibrator import _nonconformity_ratio
    # actual swing fully inside predicted band -> no widening needed
    assert _nonconformity_ratio(90, 110, 95, 105) == 1.0


def test_nonconformity_ratio_actual_low_breaks_below():
    from conformal_range_calibrator import _nonconformity_ratio
    # center=100, half_width=10; actual_low=80 needs half_width>=20 -> ratio=2.0
    ratio = _nonconformity_ratio(90, 110, 80, 105)
    assert ratio == 2.0


def test_nonconformity_ratio_degenerate_band_returns_none():
    from conformal_range_calibrator import _nonconformity_ratio
    assert _nonconformity_ratio(100, 100, 90, 110) is None
    assert _nonconformity_ratio(110, 100, 90, 110) is None


# ── fit_conformal_multiplier ────────────────────────────────────────────────

def test_fit_conformal_multiplier_empty_cases():
    from conformal_range_calibrator import fit_conformal_multiplier
    result = fit_conformal_multiplier([])
    assert result["multiplier"] == 1.0
    assert result["n"] == 0


def test_fit_conformal_multiplier_skips_incomplete_cases():
    from conformal_range_calibrator import fit_conformal_multiplier
    cases = [
        {"predicted_low_price": 90, "predicted_high_price": 110},  # missing actual
        _case(90, 110, 95, 105),
    ]
    result = fit_conformal_multiplier(cases)
    assert result["n"] == 1


def test_fit_conformal_multiplier_all_covered_needs_no_widening():
    from conformal_range_calibrator import fit_conformal_multiplier
    cases = [_case(90, 110, 95, 105)] * 10
    result = fit_conformal_multiplier(cases, target_coverage=0.90)
    assert result["multiplier"] == 1.0
    assert result["raw_coverage_pct"] == 100.0


def test_fit_conformal_multiplier_widens_to_hit_target_coverage():
    """8 of 10 cases covered raw (80%); targeting 90% coverage must produce
    a multiplier that pulls in at least one more case."""
    from conformal_range_calibrator import fit_conformal_multiplier
    covered = [_case(90, 110, 95, 105)] * 8
    uncovered = [_case(90, 110, 80, 105), _case(90, 110, 95, 125)]
    result = fit_conformal_multiplier(covered + uncovered, target_coverage=0.90)
    assert result["raw_coverage_pct"] == 80.0
    assert result["multiplier"] > 1.0
    assert result["calibrated_coverage_on_calibration_set_pct"] >= 90.0


# ── apply_conformal_widening ─────────────────────────────────────────────────

def test_apply_conformal_widening_expands_symmetrically():
    from conformal_range_calibrator import apply_conformal_widening
    out = apply_conformal_widening(90, 110, multiplier=2.0)
    # center=100, half_width=10 -> widened half_width=20
    assert out["conformal_low_price"] == 80.0
    assert out["conformal_high_price"] == 120.0


def test_apply_conformal_widening_never_narrows():
    from conformal_range_calibrator import apply_conformal_widening
    out = apply_conformal_widening(90, 110, multiplier=0.5)
    assert out["conformal_low_price"] == 90.0
    assert out["conformal_high_price"] == 110.0
    assert out["conformal_multiplier_applied"] == 1.0


# ── Integration contract with gemini_stock_prediction_agent.py ─────────────
# Regression test for a real bug caught this session: Python's str(0.90) ==
# "0.9", not "0.90" -- CONFORMAL_TARGET_COVERAGE's default must match an
# actual key in the real calibration file, not a human-formatted string.

def test_default_conformal_target_coverage_matches_real_calibration_file_key():
    import json
    from gemini_stock_prediction_agent import CONFORMAL_TARGET_COVERAGE
    cal_path = ROOT / "data" / "conformal_range_calibration.json"
    if not cal_path.exists():
        return  # calibration file is a generated artifact, not guaranteed in every checkout
    data = json.loads(cal_path.read_text(encoding="utf-8"))
    assert CONFORMAL_TARGET_COVERAGE in data.get("by_target_coverage", {})
