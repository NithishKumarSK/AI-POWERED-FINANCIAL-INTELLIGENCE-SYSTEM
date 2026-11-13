"""
options_pricer.py -- Black-Scholes option pricing + Greeks, ported from
claude-trading-skills' options-strategy-advisor skill
(vendor/claude-trading-skills/skills/options-strategy-advisor/scripts/black_scholes.py,
MIT License, Copyright (c) 2026 TraderMonty).

Pure textbook Black-Scholes math (standard, independently verifiable
formulas) -- ported line-by-line with full confidence. The source skill's
own FMP-specific price/dividend-yield fetchers are NOT ported (this
project already has historical_price_service.py for price history); only
the pricing engine and historical-volatility calculator are reused here.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm


class OptionPricer:
    """Black-Scholes option pricer with Greeks calculation.

    S: current stock price. K: strike price. T: time to expiration in
    years (e.g. 30/365). r: annual risk-free rate (e.g. 0.053). sigma:
    annual volatility (e.g. 0.25). q: continuous dividend yield (default 0).
    """

    def __init__(self, S: float, K: float, T: float, r: float, sigma: float, q: float = 0):
        self.S, self.K, self.T, self.r, self.sigma, self.q = S, K, T, r, sigma, q
        if S <= 0:
            raise ValueError("Stock price must be positive")
        if K <= 0:
            raise ValueError("Strike price must be positive")
        if T <= 0:
            raise ValueError("Time to expiration must be positive")
        if sigma <= 0:
            raise ValueError("Volatility must be positive")

    def _d1(self):
        numerator = np.log(self.S / self.K) + (self.r - self.q + 0.5 * self.sigma ** 2) * self.T
        denominator = self.sigma * np.sqrt(self.T)
        return numerator / denominator

    def _d2(self):
        return self._d1() - self.sigma * np.sqrt(self.T)

    def call_price(self):
        d1, d2 = self._d1(), self._d2()
        price = self.S * np.exp(-self.q * self.T) * norm.cdf(d1) - self.K * np.exp(-self.r * self.T) * norm.cdf(d2)
        return max(0, price)

    def put_price(self):
        d1, d2 = self._d1(), self._d2()
        price = self.K * np.exp(-self.r * self.T) * norm.cdf(-d2) - self.S * np.exp(-self.q * self.T) * norm.cdf(-d1)
        return max(0, price)

    def call_delta(self):
        return np.exp(-self.q * self.T) * norm.cdf(self._d1())

    def put_delta(self):
        return np.exp(-self.q * self.T) * (norm.cdf(self._d1()) - 1)

    def vega(self):
        d1 = self._d1()
        v = self.S * np.exp(-self.q * self.T) * norm.pdf(d1) * np.sqrt(self.T)
        return v / 100  # per 1% change in volatility

    def call_theta(self):
        d1, d2 = self._d1(), self._d2()
        term1 = -self.S * norm.pdf(d1) * self.sigma * np.exp(-self.q * self.T) / (2 * np.sqrt(self.T))
        term2 = -self.r * self.K * np.exp(-self.r * self.T) * norm.cdf(d2)
        term3 = self.q * self.S * norm.cdf(d1) * np.exp(-self.q * self.T)
        return (term1 + term2 + term3) / 365  # per day

    def put_theta(self):
        d1, d2 = self._d1(), self._d2()
        term1 = -self.S * norm.pdf(d1) * self.sigma * np.exp(-self.q * self.T) / (2 * np.sqrt(self.T))
        term2 = self.r * self.K * np.exp(-self.r * self.T) * norm.cdf(-d2)
        term3 = -self.q * self.S * norm.cdf(-d1) * np.exp(-self.q * self.T)
        return (term1 + term2 + term3) / 365

    def call_rho(self):
        rho = self.K * self.T * np.exp(-self.r * self.T) * norm.cdf(self._d2())
        return rho / 100

    def put_rho(self):
        rho = -self.K * self.T * np.exp(-self.r * self.T) * norm.cdf(-self._d2())
        return rho / 100

    def gamma(self):
        d1 = self._d1()
        return (np.exp(-self.q * self.T) * norm.pdf(d1)) / (self.S * self.sigma * np.sqrt(self.T))

    def intrinsic_value(self, option_type: str = "call") -> float:
        return max(0, self.S - self.K) if option_type.lower() == "call" else max(0, self.K - self.S)

    def time_value(self, option_type: str = "call") -> float:
        price = self.call_price() if option_type.lower() == "call" else self.put_price()
        return price - self.intrinsic_value(option_type)

    def moneyness(self) -> str:
        ratio = self.S / self.K
        if abs(ratio - 1.0) < 0.02:
            return "ATM"
        elif ratio > 1.0:
            return "ITM (Call) / OTM (Put)"
        return "OTM (Call) / ITM (Put)"

    def get_all_greeks(self, option_type: str = "call") -> dict:
        if option_type.lower() == "call":
            return {
                "price": self.call_price(), "delta": self.call_delta(), "gamma": self.gamma(),
                "theta": self.call_theta(), "vega": self.vega(), "rho": self.call_rho(),
                "intrinsic_value": self.intrinsic_value("call"), "time_value": self.time_value("call"),
            }
        return {
            "price": self.put_price(), "delta": self.put_delta(), "gamma": self.gamma(),
            "theta": self.put_theta(), "vega": self.vega(), "rho": self.put_rho(),
            "intrinsic_value": self.intrinsic_value("put"), "time_value": self.time_value("put"),
        }


def calculate_historical_volatility(prices, window: int = 30) -> float:
    """Annualized historical volatility from daily closing prices (most
    recent last), via log returns over the trailing `window` days."""
    if len(prices) < window + 1:
        raise ValueError(f"Need at least {window + 1} price points")
    prices = np.array(prices)
    log_returns = np.log(prices[1:] / prices[:-1])
    recent_returns = log_returns[-window:]
    return float(np.std(recent_returns) * np.sqrt(252))
