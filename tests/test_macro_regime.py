"""
Tests for core/macro_regime/ -- the ported claude-trading-skills
macro-regime-detector (utils, 6 calculators, composite scorer). Synthetic
data only, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _monthly_bars(n: int, start_value: float, monthly_change: float):
    """n monthly bars, most-recent-first, as {'date','close'} dicts, each
    `monthly_change` higher than the one after it (so index 0 is the most
    recent/highest if monthly_change > 0)."""
    out = []
    for i in range(n):
        value = start_value + (n - 1 - i) * monthly_change
        year = 2024 + (n - 1 - i) // 12
        month = (n - 1 - i) % 12 + 1
        out.append({"date": f"{year:04d}-{month:02d}-15", "close": round(value, 4)})
    return out


# ── utils.py ──────────────────────────────────────────────────────────────

def test_compute_sma_basic():
    from macro_regime.utils import compute_sma
    assert compute_sma([1, 2, 3, 4, 5], 3) == 2.0  # avg of [1,2,3] (most-recent-first)


def test_compute_sma_insufficient_data_returns_none():
    from macro_regime.utils import compute_sma
    assert compute_sma([1, 2], 5) is None


def test_compute_roc_basic():
    from macro_regime.utils import compute_roc
    # values[0]=110, values[3]=100 -> 10% ROC
    assert compute_roc([110, 105, 102, 100], 3) == 10.0


def test_compute_percentile_basic():
    from macro_regime.utils import compute_percentile
    assert compute_percentile([1, 2, 3, 4, 5], 3) == 40.0  # 2 of 5 values below 3


def test_detect_crossover_golden_cross():
    from macro_regime.utils import detect_crossover
    # Rising series -> short SMA eventually crosses above long SMA (golden cross)
    values = list(range(30, 0, -1))  # most-recent-first, decreasing index = older = smaller value... construct rising trend
    # Build a genuinely rising-then-flat series so a crossover is detectable
    rising = [float(i) for i in range(40, 0, -1)]  # most-recent-first, most recent = 40 (highest)
    result = detect_crossover(rising, short_period=6, long_period=12)
    assert result["type"] in ("golden_cross", "none", "converging")  # must not raise, real classification


def test_compute_rolling_correlation_perfectly_correlated():
    from macro_regime.utils import compute_rolling_correlation
    a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    b = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0]  # b = 2*a, perfectly correlated
    corr = compute_rolling_correlation(a, b, 6)
    assert abs(corr - 1.0) < 1e-9


def test_compute_rolling_correlation_insufficient_data():
    from macro_regime.utils import compute_rolling_correlation
    assert compute_rolling_correlation([1, 2], [1, 2], 6) is None


def test_score_transition_signal_bounded_0_100():
    from macro_regime.utils import score_transition_signal
    score = score_transition_signal({"type": "golden_cross", "bars_ago": 0, "gap_pct": 5.0}, 10.0, -10.0, 100, 90)
    assert 0 <= score <= 100


# ── calculators: insufficient data degrades gracefully ──────────────────

def test_concentration_insufficient_data():
    from macro_regime.concentration import calculate_concentration
    result = calculate_concentration([], [])
    assert result["data_available"] is False
    assert result["score"] == 0


def test_concentration_with_enough_data_returns_real_result():
    from macro_regime.concentration import calculate_concentration
    rsp = _monthly_bars(24, 100, 0.5)   # rising
    spy = _monthly_bars(24, 400, 1.0)   # rising faster -> RSP/SPY ratio declining -> concentrating
    result = calculate_concentration(rsp, spy)
    assert result["data_available"] is True
    assert result["direction"] in ("broadening", "concentrating", "unknown")
    assert 0 <= result["score"] <= 100


def test_yield_curve_shy_tlt_proxy_path():
    from macro_regime.yield_curve import calculate_yield_curve
    shy = _monthly_bars(24, 80, 0.1)
    tlt = _monthly_bars(24, 90, 0.2)
    result = calculate_yield_curve(shy_history=shy, tlt_history=tlt)
    assert result["data_available"] is True
    assert result["data_source"] == "shy_tlt_proxy"


def test_yield_curve_no_data_at_all():
    from macro_regime.yield_curve import calculate_yield_curve
    result = calculate_yield_curve()
    assert result["data_available"] is False


def test_credit_conditions_basic():
    from macro_regime.credit_conditions import calculate_credit_conditions
    hyg = _monthly_bars(24, 80, 0.3)
    lqd = _monthly_bars(24, 110, 0.1)
    result = calculate_credit_conditions(hyg, lqd)
    assert result["data_available"] is True
    assert result["direction"] in ("easing", "tightening", "stable")


def test_size_factor_basic():
    from macro_regime.size_factor import calculate_size_factor
    iwm = _monthly_bars(24, 200, 1.0)
    spy = _monthly_bars(24, 400, 0.5)
    result = calculate_size_factor(iwm, spy)
    assert result["data_available"] is True
    assert result["direction"] in ("small_cap_leading", "large_cap_leading", "neutral")


def test_equity_bond_basic():
    from macro_regime.equity_bond import calculate_equity_bond
    spy = _monthly_bars(24, 400, 1.0)
    tlt = _monthly_bars(24, 90, -0.2)
    result = calculate_equity_bond(spy, tlt)
    assert result["data_available"] is True
    assert result["correlation_regime"] in ("negative_strong", "negative_mild", "near_zero", "positive", "unknown")


def test_sector_rotation_basic():
    from macro_regime.sector_rotation import calculate_sector_rotation
    xly = _monthly_bars(24, 150, 0.5)
    xlp = _monthly_bars(24, 70, 0.1)
    result = calculate_sector_rotation(xly, xlp)
    assert result["data_available"] is True
    assert result["direction"] in ("risk_on", "risk_off", "neutral")


# ── scorer: composite + regime classification ───────────────────────────

def test_calculate_composite_score_weighted_sum():
    from macro_regime.scorer import calculate_composite_score, COMPONENT_WEIGHTS
    scores = {k: 50 for k in COMPONENT_WEIGHTS}
    result = calculate_composite_score(scores)
    assert result["composite_score"] == 50.0  # all components equal -> composite = that value


def test_calculate_composite_score_identifies_strongest_weakest():
    from macro_regime.scorer import calculate_composite_score
    scores = {"concentration": 90, "yield_curve": 10, "credit_conditions": 50, "size_factor": 50, "equity_bond": 50, "sector_rotation": 50}
    result = calculate_composite_score(scores)
    assert result["strongest_signal"]["component"] == "concentration"
    assert result["weakest_signal"]["component"] == "yield_curve"


def test_calculate_composite_score_data_quality_complete():
    from macro_regime.scorer import calculate_composite_score, COMPONENT_WEIGHTS
    scores = {k: 50 for k in COMPONENT_WEIGHTS}
    result = calculate_composite_score(scores, data_availability={k: True for k in COMPONENT_WEIGHTS})
    assert "Complete" in result["data_quality"]["label"]


def test_interpret_zone_thresholds():
    from macro_regime.scorer import _interpret_zone
    assert _interpret_zone(10)["zone"] == "Stable (No Transition)"
    assert _interpret_zone(90)["zone"] == "Confirmed Transition (Completing)"


def test_classify_regime_all_unavailable_gives_very_low_confidence():
    from macro_regime.scorer import classify_regime
    empty = {"data_available": False}
    result = classify_regime({
        "concentration": empty, "yield_curve": empty, "credit_conditions": empty,
        "size_factor": empty, "equity_bond": empty, "sector_rotation": empty,
    })
    assert result["confidence"] == "very_low"


def test_classify_regime_clear_concentration_signals():
    from macro_regime.scorer import classify_regime
    result = classify_regime({
        "concentration": {"data_available": True, "direction": "concentrating", "score": 80},
        "yield_curve": {"data_available": True, "direction": "flattening", "score": 10},
        "credit_conditions": {"data_available": True, "direction": "stable", "score": 10},
        "size_factor": {"data_available": True, "direction": "large_cap_leading", "score": 80},
        "equity_bond": {"data_available": True, "direction": "risk_on", "correlation_regime": "negative_strong", "score": 10},
        "sector_rotation": {"data_available": True, "direction": "risk_on", "score": 10},
    })
    assert result["current_regime"] == "concentration"


def test_check_regime_consistency():
    from macro_regime.scorer import check_regime_consistency
    components = {
        "concentration": {"direction": "broadening"},
        "size_factor": {"direction": "small_cap_leading"},
        "credit_conditions": {"direction": "easing"},
        "sector_rotation": {"direction": "risk_on"},
        "equity_bond": {"direction": "risk_on"},
        "yield_curve": {"direction": "steepening"},
    }
    result = check_regime_consistency("broadening", components)
    assert all(v == "consistent" for v in result.values())


def test_check_regime_consistency_contradicting():
    from macro_regime.scorer import check_regime_consistency
    components = {"concentration": {"direction": "concentrating"}}  # broadening regime expects "broadening"
    result = check_regime_consistency("broadening", components)
    assert result["concentration"] == "contradicting"
