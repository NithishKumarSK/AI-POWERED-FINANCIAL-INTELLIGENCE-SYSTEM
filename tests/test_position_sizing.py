"""Tests for core/position_sizing.py -- Research Expansion Program position sizing."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from position_sizing import (
    compute_position_size, kelly_fraction, fixed_fractional_shares, atr_based_shares,
    MAX_POSITION_FRACTION, MIN_POSITION_FRACTION,
)


def test_hold_and_review_get_no_position():
    for dec in ("HOLD", "REVIEW"):
        out = compute_position_size(dec, 10000.0, calibrated_confidence_score=90)
        assert out["status"] == "NO_POSITION"


def test_no_confidence_at_all_returns_no_position():
    out = compute_position_size("BUY", 10000.0)
    assert out["status"] == "NO_POSITION"


def test_weak_signal_quality_overrides_the_floor_to_no_position():
    """Real gate added this session: without this, MIN_POSITION_FRACTION
    means a WEAK-tier prediction (both confidence and move-size historically
    unreliable) still gets sized like any other BUY/SELL -- "no signal" was
    never actually possible. High calibrated confidence must NOT override
    a WEAK tier -- the tier is the whole point."""
    out = compute_position_size(
        "BUY", 10000.0, calibrated_confidence_score=90, signal_quality_tier="WEAK",
    )
    assert out["status"] == "NO_POSITION"
    assert "WEAK" in out["reason"]


def test_strong_signal_quality_does_not_block_sizing():
    out = compute_position_size(
        "BUY", 10000.0, calibrated_confidence_score=70, signal_quality_tier="STRONG",
    )
    assert out["status"] == "OK"


def test_no_signal_quality_tier_given_behaves_as_before():
    """Omitting signal_quality_tier entirely (existing callers, old data)
    must not change behavior -- this is purely additive."""
    out = compute_position_size("BUY", 10000.0, calibrated_confidence_score=70)
    assert out["status"] == "OK"


def test_prefers_calibrated_confidence_over_raw():
    """Raw confidence 95 (would size up a lot) must be ignored in favor of a
    low calibrated confidence (sizes down) when both are given -- this is the
    whole point: raw confidence is confirmed inversely correlated with
    correctness, so it must never win over a real calibrated estimate."""
    out = compute_position_size(
        "BUY", 10000.0, confidence_score=95, calibrated_confidence_score=30,
    )
    assert out["status"] == "OK"
    assert out["confidence_source"] == "calibrated"
    assert out["confidence_used"] == 30
    # calibrated 30 is below the 50% coin-flip baseline -> floor position
    assert out["position_fraction"] == MIN_POSITION_FRACTION


def test_falls_back_to_raw_only_when_no_calibration_available():
    out = compute_position_size("SELL", 10000.0, confidence_score=80)
    assert out["status"] == "OK"
    assert out["confidence_source"] == "raw_uncalibrated"
    assert out["confidence_used"] == 80


def test_high_calibrated_confidence_low_risk_sizes_up_toward_cap():
    """Needs the best-known regime (sideways, regime_factor=1.0) to actually
    reach the cap -- any other/unknown regime is deliberately dampened
    below it per the real, measured regime-reliability finding."""
    out = compute_position_size(
        "BUY", 100000.0, calibrated_confidence_score=100, risk_score=0,
        trend_regime="sideways", max_position_fraction=0.25,
    )
    assert out["status"] == "OK"
    assert out["position_fraction"] == MAX_POSITION_FRACTION
    assert out["position_dollars"] == 25000.0


def test_coin_flip_calibrated_confidence_sizes_to_floor():
    out = compute_position_size("BUY", 10000.0, calibrated_confidence_score=50, risk_score=50)
    assert out["status"] == "OK"
    assert out["position_fraction"] == MIN_POSITION_FRACTION


def test_missing_risk_score_is_conservative_not_neutral():
    """Missing risk_score must shrink the position (treated as risky), never
    default to a full-confidence-only size as if risk were known to be low."""
    with_risk = compute_position_size("BUY", 10000.0, calibrated_confidence_score=90, risk_score=0)
    no_risk = compute_position_size("BUY", 10000.0, calibrated_confidence_score=90)
    assert no_risk["position_fraction"] < with_risk["position_fraction"]


def test_position_fraction_never_exceeds_cap_even_with_extreme_inputs():
    out = compute_position_size(
        "BUY", 10000.0, calibrated_confidence_score=100, risk_score=0,
        max_position_fraction=0.10,
    )
    assert out["position_fraction"] <= 0.10


def test_bearish_regime_sizes_down_vs_sideways():
    """Real, measured finding (436 DB predictions): direction match is 63.8%
    in sideways regimes vs 38.9% in bearish -- a position in a bearish regime
    must size smaller than an identical call in a sideways regime."""
    sideways = compute_position_size(
        "BUY", 10000.0, calibrated_confidence_score=90, risk_score=10, trend_regime="sideways",
    )
    bearish = compute_position_size(
        "BUY", 10000.0, calibrated_confidence_score=90, risk_score=10, trend_regime="bearish",
    )
    assert bearish["position_fraction"] < sideways["position_fraction"]
    assert bearish["regime_factor"] < sideways["regime_factor"]
    assert sideways["regime_factor"] == 1.0


def test_unknown_regime_treated_as_conservatively_as_worst_known():
    unknown = compute_position_size("BUY", 10000.0, calibrated_confidence_score=90, risk_score=10)
    bearish = compute_position_size(
        "BUY", 10000.0, calibrated_confidence_score=90, risk_score=10, trend_regime="bearish",
    )
    assert unknown["regime_factor"] == bearish["regime_factor"]


def test_dollars_scale_with_capital():
    small = compute_position_size("BUY", 1000.0, calibrated_confidence_score=90, risk_score=10)
    big = compute_position_size("BUY", 100000.0, calibrated_confidence_score=90, risk_score=10)
    assert small["position_fraction"] == big["position_fraction"]
    assert big["position_dollars"] == small["position_dollars"] * 100


# ── kelly_fraction (adapted from claude-trading-skills' position-sizer) ────

def test_kelly_positive_expectancy():
    """60% win rate, 2:1 payoff -> Kelly% = 0.6 - 0.4/2 = 0.40 -> 40%, half=20%."""
    result = kelly_fraction(win_rate=0.6, avg_win=200.0, avg_loss=100.0)
    assert result["kelly_pct"] == 40.0
    assert result["half_kelly_pct"] == 20.0


def test_kelly_negative_expectancy_floors_at_zero():
    """Low win rate + poor payoff -> negative raw Kelly must floor at 0, not go negative."""
    result = kelly_fraction(win_rate=0.2, avg_win=100.0, avg_loss=200.0)
    assert result["kelly_pct"] == 0.0
    assert result["half_kelly_pct"] == 0.0


def test_kelly_matches_this_projects_own_measured_ev_numbers():
    """Sanity-check against this project's own real EV probe result cited in
    position_sizing.py's module docstring: 38.5% win rate, +$2,904.74 avg
    win, -$319.02 avg loss -- a real payoff asymmetry that should still
    clear a positive (if modest) Kelly fraction despite the sub-50% win rate."""
    result = kelly_fraction(win_rate=0.385, avg_win=2904.74, avg_loss=319.02)
    assert result["kelly_pct"] > 0.0
    # half_kelly_pct is independently rounded from the unrounded Kelly%
    # (not recomputed from the already-rounded kelly_pct), matching the
    # source position-sizer skill's own rounding order -- so it's within a
    # rounding cent of half, not necessarily bit-identical to kelly_pct/2.
    assert abs(result["half_kelly_pct"] - result["kelly_pct"] / 2) < 0.01


def test_kelly_rejects_invalid_win_rate():
    import pytest
    with pytest.raises(ValueError):
        kelly_fraction(win_rate=0.0, avg_win=100.0, avg_loss=50.0)
    with pytest.raises(ValueError):
        kelly_fraction(win_rate=1.5, avg_win=100.0, avg_loss=50.0)


def test_kelly_rejects_non_positive_payoff_inputs():
    import pytest
    with pytest.raises(ValueError):
        kelly_fraction(win_rate=0.5, avg_win=0.0, avg_loss=50.0)
    with pytest.raises(ValueError):
        kelly_fraction(win_rate=0.5, avg_win=100.0, avg_loss=-10.0)


# ── fixed_fractional_shares / atr_based_shares (adapted from position-sizer) ─

def test_fixed_fractional_basic():
    # $100k account, 1% risk = $1000 dollar risk; $5 risk/share -> 200 shares.
    result = fixed_fractional_shares(account_size=100000, entry_price=50, stop_price=45, risk_pct=1.0)
    assert result["dollar_risk"] == 1000.0
    assert result["risk_per_share"] == 5.0
    assert result["shares"] == 200


def test_fixed_fractional_rejects_stop_above_entry():
    import pytest
    with pytest.raises(ValueError):
        fixed_fractional_shares(account_size=10000, entry_price=50, stop_price=55, risk_pct=1.0)


def test_fixed_fractional_rejects_non_positive_inputs():
    import pytest
    with pytest.raises(ValueError):
        fixed_fractional_shares(account_size=0, entry_price=50, stop_price=45, risk_pct=1.0)


def test_atr_based_basic():
    # ATR=2, multiplier=2 -> stop distance=4; $100k account, 1% risk=$1000 -> 250 shares.
    result = atr_based_shares(account_size=100000, entry_price=50, atr=2.0, risk_pct=1.0, atr_multiplier=2.0)
    assert result["stop_price"] == 46.0
    assert result["risk_per_share"] == 4.0
    assert result["shares"] == 250


def test_atr_based_rejects_non_positive_inputs():
    import pytest
    with pytest.raises(ValueError):
        atr_based_shares(account_size=10000, entry_price=50, atr=0, risk_pct=1.0)
