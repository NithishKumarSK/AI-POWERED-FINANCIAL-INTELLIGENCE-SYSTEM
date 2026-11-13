"""
Tests for core/pair_trade_analyzer.py -- ported hedge-ratio/cointegration/
half-life/z-score pairs-trading math. Synthetic data only, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import math
import random

from pair_trade_analyzer import (
    analyze_pair,
    calculate_half_life,
    calculate_hedge_ratio,
    calculate_zscore_series,
    check_cointegration,
)


def _mean_reverting_pair(n=300, beta=1.5, seed=42):
    """Two price series whose spread (a - beta*b) is a stationary,
    mean-reverting AR(1) process -- a textbook cointegrated pair."""
    rng = random.Random(seed)
    b_prices = [100.0]
    for _ in range(n - 1):
        b_prices.append(b_prices[-1] * (1 + rng.gauss(0, 0.01)))

    spread = [0.0]
    for _ in range(n - 1):
        spread.append(spread[-1] * 0.85 + rng.gauss(0, 1.0))  # phi=0.85 -> mean-reverting

    a_prices = [beta * b + s for b, s in zip(b_prices, spread)]
    return a_prices, b_prices


def _independent_random_walks(n=300, seed=7):
    """Two independent random walks -- should NOT be cointegrated."""
    rng = random.Random(seed)
    a = [100.0]
    b = [50.0]
    for _ in range(n - 1):
        a.append(a[-1] + rng.gauss(0, 1.0))
        b.append(b[-1] + rng.gauss(0, 1.0))
    return a, b


def test_calculate_hedge_ratio_recovers_known_beta():
    a_prices, b_prices = _mean_reverting_pair(beta=1.5)
    result = calculate_hedge_ratio(a_prices, b_prices)
    assert abs(result["beta"] - 1.5) < 0.2
    assert result["r_squared"] > 0.8


def test_calculate_hedge_ratio_rejects_mismatched_lengths():
    import pytest
    with pytest.raises(ValueError):
        calculate_hedge_ratio([1.0, 2.0, 3.0], [1.0, 2.0])


def test_calculate_hedge_ratio_rejects_constant_prices():
    import pytest
    with pytest.raises(ValueError):
        calculate_hedge_ratio([100.0] * 10, [50.0] * 10)


def test_cointegration_detects_mean_reverting_spread():
    a_prices, b_prices = _mean_reverting_pair(beta=1.5)
    hedge = calculate_hedge_ratio(a_prices, b_prices)
    spread = [a - hedge["beta"] * b for a, b in zip(a_prices, b_prices)]
    result = check_cointegration(spread)
    assert result is not None
    assert result["is_cointegrated"] is True
    assert result["p_value"] < 0.05


def test_half_life_is_positive_and_finite_for_mean_reverting_spread():
    _, _ = _mean_reverting_pair()
    rng = random.Random(1)
    spread = [0.0]
    for _ in range(299):
        spread.append(spread[-1] * 0.85 + rng.gauss(0, 1.0))
    half_life = calculate_half_life(spread)
    assert half_life is not None
    assert half_life > 0
    assert math.isfinite(half_life)


def test_zscore_series_first_window_entries_are_none():
    spread = list(range(100))
    z = calculate_zscore_series(spread, window=20)
    assert all(v is None for v in z[:19])
    assert z[19] is not None


def test_zscore_series_matches_hand_calculation():
    spread = [1.0, 2.0, 3.0, 4.0, 5.0]
    z = calculate_zscore_series(spread, window=5)
    mean = 3.0
    std = (sum((x - mean) ** 2 for x in spread) / 4) ** 0.5  # ddof=1
    expected = (5.0 - mean) / std
    assert abs(z[-1] - expected) < 1e-9


def test_analyze_pair_full_pipeline_on_mean_reverting_pair():
    a_prices, b_prices = _mean_reverting_pair(beta=1.5)
    result = analyze_pair("AAA", "BBB", a_prices, b_prices, entry_zscore=2.0)
    assert result["symbol_a"] == "AAA"
    assert result["symbol_b"] == "BBB"
    assert result["cointegration"]["is_cointegrated"] is True
    assert result["signal"] in ("WAIT", "LONG_SPREAD", "SHORT_SPREAD")


def test_analyze_pair_independent_walks_not_cointegrated():
    a_prices, b_prices = _independent_random_walks()
    result = analyze_pair("AAA", "BBB", a_prices, b_prices, entry_zscore=2.0)
    assert result["cointegration"]["is_cointegrated"] is False
    assert result["signal"] == "NO_TRADE_NOT_COINTEGRATED"
