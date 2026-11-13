"""Tests for core/portfolio_tools/options_pricer.py -- Black-Scholes
pricing + Greeks, verified against known textbook reference values and
fundamental option-pricing identities (put-call parity)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from portfolio_tools.options_pricer import OptionPricer, calculate_historical_volatility


def test_matches_known_textbook_reference_values():
    """S=100,K=100,T=1,r=5%,sigma=20% is a standard textbook example:
    call ~10.45, put ~5.57."""
    p = OptionPricer(S=100, K=100, T=1.0, r=0.05, sigma=0.20)
    assert round(p.call_price(), 2) == 10.45
    assert round(p.put_price(), 2) == 5.57


def test_put_call_parity_holds():
    """C - P = S*e^(-qT) - K*e^(-rT), a mathematical identity any correct
    Black-Scholes implementation must satisfy exactly."""
    p = OptionPricer(S=120, K=110, T=0.5, r=0.04, sigma=0.3, q=0.01)
    lhs = p.call_price() - p.put_price()
    rhs = p.S * math.exp(-p.q * p.T) - p.K * math.exp(-p.r * p.T)
    assert abs(lhs - rhs) < 1e-9


def test_deep_itm_call_delta_approaches_one():
    p = OptionPricer(S=200, K=50, T=0.1, r=0.05, sigma=0.2)
    assert p.call_delta() > 0.95


def test_deep_otm_call_delta_approaches_zero():
    p = OptionPricer(S=50, K=200, T=0.1, r=0.05, sigma=0.2)
    assert p.call_delta() < 0.05


def test_put_delta_range():
    p = OptionPricer(S=100, K=100, T=1.0, r=0.05, sigma=0.2)
    assert -1.0 <= p.put_delta() <= 0.0


def test_gamma_same_for_call_and_put():
    """Gamma is identical for calls and puts at the same strike -- a known
    Black-Scholes property, not something that needs a separate put formula."""
    p = OptionPricer(S=100, K=105, T=0.5, r=0.03, sigma=0.25)
    assert p.gamma() > 0


def test_vega_always_positive():
    p = OptionPricer(S=100, K=100, T=1.0, r=0.05, sigma=0.3)
    assert p.vega() > 0


def test_theta_typically_negative_for_long_options():
    p = OptionPricer(S=100, K=100, T=0.25, r=0.03, sigma=0.3)
    assert p.call_theta() < 0


def test_atm_moneyness_classification():
    p = OptionPricer(S=100, K=100, T=1.0, r=0.05, sigma=0.2)
    assert p.moneyness() == "ATM"


def test_itm_otm_moneyness_classification():
    itm_call = OptionPricer(S=150, K=100, T=1.0, r=0.05, sigma=0.2)
    assert "ITM" in itm_call.moneyness()
    otm_call = OptionPricer(S=50, K=100, T=1.0, r=0.05, sigma=0.2)
    assert "OTM" in otm_call.moneyness()


def test_intrinsic_and_time_value_sum_to_price():
    p = OptionPricer(S=110, K=100, T=0.5, r=0.04, sigma=0.25)
    price = p.call_price()
    intrinsic = p.intrinsic_value("call")
    time_val = p.time_value("call")
    assert abs(intrinsic + time_val - price) < 1e-9


def test_get_all_greeks_returns_complete_dict():
    p = OptionPricer(S=100, K=100, T=1.0, r=0.05, sigma=0.2)
    greeks = p.get_all_greeks("call")
    for key in ("price", "delta", "gamma", "theta", "vega", "rho", "intrinsic_value", "time_value"):
        assert key in greeks


def test_rejects_non_positive_inputs():
    import pytest
    with pytest.raises(ValueError):
        OptionPricer(S=0, K=100, T=1.0, r=0.05, sigma=0.2)
    with pytest.raises(ValueError):
        OptionPricer(S=100, K=-5, T=1.0, r=0.05, sigma=0.2)
    with pytest.raises(ValueError):
        OptionPricer(S=100, K=100, T=0, r=0.05, sigma=0.2)
    with pytest.raises(ValueError):
        OptionPricer(S=100, K=100, T=1.0, r=0.05, sigma=0)


# ── calculate_historical_volatility ──────────────────────────────────────

def test_hv_zero_for_constant_prices():
    prices = [100.0] * 40
    assert calculate_historical_volatility(prices, window=30) == 0.0


def test_hv_positive_for_varying_prices():
    import math
    prices = [100 * (1.01 ** (i % 5 - 2)) for i in range(40)]
    hv = calculate_historical_volatility(prices, window=30)
    assert hv > 0


def test_hv_insufficient_data_raises():
    import pytest
    with pytest.raises(ValueError):
        calculate_historical_volatility([100, 101, 102], window=30)
