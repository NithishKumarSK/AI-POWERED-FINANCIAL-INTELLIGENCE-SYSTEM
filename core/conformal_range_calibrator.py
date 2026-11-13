"""
conformal_range_calibrator.py -- split-conformal-style calibration for the
deterministic price-range predictor (range_timing_predictor.py).

Real, live-measured baseline this session (304 validated predictions with
both a predicted and actual price range): the raw predicted [low, high] band
fully contained the actual price swing 79.9% of the time -- a real, strong
number, but not a GUARANTEED coverage level. This module computes, from that
same real calibration data, how much the band needs to widen (a single
multiplicative factor on the half-width around the band's center) to reach a
chosen target coverage (e.g. 90%), using the standard split-conformal
construction: take the ceil((n+1)*target_coverage)/n -quantile of each
case's own "how far would this band have needed to stretch to contain the
actual swing" ratio.

This is a REAL statistical guarantee only insofar as future cases are
exchangeable with the calibration set (same symbol mix, same market regime)
-- a disclosed assumption, not a universal promise. Re-run periodically as
the ledger grows, same staleness caveat as every other calibration snapshot
in this project (confidence_calibration_map.json, magnitude_calibration_map.json).

Pure functions only -- no API calls, no Streamlit, importable anywhere.
"""
from __future__ import annotations

import math
from typing import List, Optional


def _nonconformity_ratio(predicted_low: float, predicted_high: float,
                          actual_low: float, actual_high: float) -> Optional[float]:
    """How much the [predicted_low, predicted_high] band's half-width would
    need to multiply by (expanding symmetrically around its own center) to
    fully contain [actual_low, actual_high]. Returns 1.0 if already covered
    (never shrinks below the original band) -- None if the predicted band is
    degenerate (zero or negative width, can't be scaled)."""
    if predicted_high <= predicted_low:
        return None
    center = (predicted_low + predicted_high) / 2.0
    half_width = (predicted_high - predicted_low) / 2.0
    if half_width <= 0:
        return None
    required_half_width = max(half_width, center - actual_low, actual_high - center)
    return required_half_width / half_width


def fit_conformal_multiplier(cases: List[dict], target_coverage: float = 0.90) -> dict:
    """
    cases: list of dicts each with predicted_low_price, predicted_high_price,
    actual_low_price, actual_high_price (same shape as
    scratchpad's price_range_results_fixed.json "cases" list -- the real,
    live-measured calibration set this project already built).

    Returns:
        {"multiplier": float, "target_coverage": float,
         "raw_coverage_pct": float, "n": int,
         "calibrated_coverage_on_calibration_set_pct": float}
    multiplier is the single number to apply to future predicted ranges.
    Returns multiplier=1.0 (no-op) with n=0 if no usable cases.
    """
    ratios = []
    raw_hits = 0
    for c in cases:
        pl, ph = c.get("predicted_low_price"), c.get("predicted_high_price")
        al, ah = c.get("actual_low_price"), c.get("actual_high_price")
        if None in (pl, ph, al, ah):
            continue
        ratio = _nonconformity_ratio(float(pl), float(ph), float(al), float(ah))
        if ratio is None:
            continue
        ratios.append(ratio)
        if ratio <= 1.0 + 1e-9:
            raw_hits += 1

    n = len(ratios)
    if n == 0:
        return {"multiplier": 1.0, "target_coverage": target_coverage,
                "raw_coverage_pct": None, "n": 0,
                "calibrated_coverage_on_calibration_set_pct": None}

    ratios.sort()
    # Standard split-conformal quantile index: ceil((n+1) * target_coverage),
    # clamped to the last available order statistic (can't exceed n).
    q_idx = min(n, math.ceil((n + 1) * target_coverage))
    multiplier = ratios[q_idx - 1] if q_idx >= 1 else ratios[0]

    calibrated_hits = sum(1 for r in ratios if r <= multiplier + 1e-9)

    return {
        "multiplier": round(multiplier, 4),
        "target_coverage": target_coverage,
        "raw_coverage_pct": round(raw_hits / n * 100, 1),
        "n": n,
        "calibrated_coverage_on_calibration_set_pct": round(calibrated_hits / n * 100, 1),
    }


def apply_conformal_widening(predicted_low: float, predicted_high: float, multiplier: float) -> dict:
    """Widen [predicted_low, predicted_high] symmetrically around its own
    center by `multiplier`. multiplier < 1 is clamped to 1 (this calibration
    only ever widens a band to improve coverage, never narrows one -- a
    narrower band is a different, unvalidated claim)."""
    m = max(1.0, float(multiplier))
    center = (predicted_low + predicted_high) / 2.0
    half_width = (predicted_high - predicted_low) / 2.0 * m
    return {
        "conformal_low_price": round(center - half_width, 4),
        "conformal_high_price": round(center + half_width, 4),
        "conformal_multiplier_applied": round(m, 4),
    }
