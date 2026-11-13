"""
Tests for core/crypto_regime_analyzer.py -- pure calculation, synthetic
price/dominance/funding series only, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from crypto_regime_analyzer import (
    WEIGHTS,
    alt_breadth_participation,
    btc_dominance_regime,
    btc_trend_structure,
    compute_composite,
    drawdown_volatility_position,
    momentum_thrust_washout,
    perpetual_funding_regime,
)


def _rising_series(n, start=100.0, daily_pct=0.01):
    out = [start]
    for _ in range(n - 1):
        out.append(out[-1] * (1 + daily_pct))
    return out


def _flat_series(n, price=100.0):
    return [price] * n


def test_btc_trend_structure_insufficient_history():
    result = btc_trend_structure([100.0] * 100)
    assert result["data_available"] is False


def test_btc_trend_structure_bull_stack():
    closes = _rising_series(250, start=50.0, daily_pct=0.005)
    result = btc_trend_structure(closes)
    assert result["data_available"] is True
    assert result["score"] >= 90  # bull stack (90) + rising slope (+10), clamped to 100


def test_btc_trend_structure_bear_stack():
    closes = list(reversed(_rising_series(250, start=50.0, daily_pct=0.005)))
    result = btc_trend_structure(closes)
    assert result["data_available"] is True
    assert result["score"] <= 15  # bear stack (15) + falling slope (-10), clamped to 0


def test_alt_breadth_insufficient_universe():
    result = alt_breadth_participation({"ETH": [100.0] * 250, "SOL": [50.0] * 250})
    assert result["data_available"] is False


def test_alt_breadth_broad_participation():
    alts = {f"ALT{i}": _rising_series(250, start=10.0, daily_pct=0.01) for i in range(6)}
    result = alt_breadth_participation(alts)
    assert result["data_available"] is True
    assert result["score"] >= 80


def test_alt_breadth_skips_short_history_coins():
    alts = {f"ALT{i}": _rising_series(250, start=10.0, daily_pct=0.01) for i in range(6)}
    alts["TOOSHORT"] = [10.0] * 50
    result = alt_breadth_participation(alts)
    assert "TOOSHORT" in result["skipped"]


def test_btc_dominance_insufficient_history():
    result = btc_dominance_regime([55.0] * 10, 70)
    assert result["data_available"] is False


def test_btc_dominance_alt_rotation():
    series = [60.0] * 20 + [55.0] * 11  # falling >0.5
    result = btc_dominance_regime(series, btc_trend_score=70)
    assert result["data_available"] is True
    assert result["score"] == 90


def test_btc_dominance_indiscriminate_derisking():
    series = [60.0] * 20 + [55.0] * 11
    result = btc_dominance_regime(series, btc_trend_score=30)
    assert result["score"] == 10


def test_perpetual_funding_insufficient_symbols():
    result = perpetual_funding_regime({"BTCUSDT": 0.0001})
    assert result["data_available"] is False


def test_perpetual_funding_euphoric():
    result = perpetual_funding_regime({"BTCUSDT": 0.001, "ETHUSDT": 0.0009})
    assert result["data_available"] is True
    assert result["score"] == 10


def test_perpetual_funding_washed_out():
    result = perpetual_funding_regime({"BTCUSDT": -0.0002, "ETHUSDT": -0.0003})
    assert result["score"] == 80


def test_drawdown_volatility_insufficient_history():
    result = drawdown_volatility_position([100.0] * 100)
    assert result["data_available"] is False


def test_drawdown_volatility_near_highs():
    closes = _rising_series(400, start=50.0, daily_pct=0.002)
    result = drawdown_volatility_position(closes)
    assert result["data_available"] is True
    assert result["drawdown_pct"] < 5


def test_momentum_thrust_insufficient_universe():
    result = momentum_thrust_washout({"BTC": [100.0] * 40})
    assert result["data_available"] is False


def test_momentum_thrust_broad_positive():
    universe = {f"COIN{i}": _rising_series(40, start=10.0, daily_pct=0.02) for i in range(6)}
    result = momentum_thrust_washout(universe)
    assert result["data_available"] is True
    assert result["pct_positive_30d"] == 100.0
    assert result["score"] == 90


def test_compute_composite_insufficient_components_returns_unknown():
    components = {
        "btc_trend_structure": {"score": 90, "data_available": True},
    }
    result = compute_composite(components)
    assert result["zone"] == "UNKNOWN"
    assert result["score"] is None


def test_compute_composite_full_bullish():
    components = {
        "btc_trend_structure": {"score": 95, "data_available": True},
        "alt_breadth_participation": {"score": 90, "data_available": True},
        "btc_dominance_regime": {"score": 85, "data_available": True},
        "perpetual_funding_regime": {"score": 75, "data_available": True},
        "drawdown_volatility_position": {"score": 90, "data_available": True},
        "momentum_thrust_washout": {"score": 90, "data_available": True},
    }
    result = compute_composite(components)
    assert result["zone"] == "RISK_ON"
    assert result["score"] >= 80
    assert abs(sum(result["effective_weights"].values()) - 100.0) < 1e-6


def test_compute_composite_redistributes_weight_for_missing_component():
    components = {
        "btc_trend_structure": {"score": 10, "data_available": True},
        "alt_breadth_participation": {"score": 10, "data_available": True},
        "btc_dominance_regime": {"score": 10, "data_available": True},
        "drawdown_volatility_position": {"score": 10, "data_available": True},
        "perpetual_funding_regime": {"score": None, "data_available": False},
        "momentum_thrust_washout": {"score": None, "data_available": False},
    }
    result = compute_composite(components)
    assert result["zone"] == "RISK_OFF"
    assert set(result["components_used"]) == {
        "btc_trend_structure", "alt_breadth_participation", "btc_dominance_regime", "drawdown_volatility_position",
    }
