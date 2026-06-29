"""4 tests for portfolio service concentration, correlation, and summary."""
from __future__ import annotations

import pytest

from src.services.portfolio_service import (
    analyse_portfolio_concentration,
    build_portfolio_summary,
    analyse_portfolio,
)


_HOLDINGS = [
    {"ticker": "AAPL", "weight": 0.40, "signal": "BUY", "score": 72},
    {"ticker": "MSFT", "weight": 0.35, "signal": "HOLD", "score": 55},
    {"ticker": "NVDA", "weight": 0.15, "signal": "BUY", "score": 80},
    {"ticker": "SGOV", "weight": 0.10, "signal": "HOLD", "score": 50},
]


class TestConcentration:
    def test_high_concentration_detected(self):
        concentrated = [
            {"ticker": "A", "weight": 0.90},
            {"ticker": "B", "weight": 0.10},
        ]
        result = analyse_portfolio_concentration(concentrated)
        assert result["status"] == "SUCCESS"
        assert result["concentration_label"] == "HIGH"

    def test_low_concentration_detected(self):
        equal = [{"ticker": chr(65 + i), "weight": 0.1} for i in range(10)]
        result = analyse_portfolio_concentration(equal)
        assert result["concentration_label"] == "LOW"


class TestPortfolioSummary:
    def test_aggregates_signals(self):
        summary = build_portfolio_summary(_HOLDINGS)
        assert summary["buy_count"] == 2
        assert summary["hold_count"] == 2
        assert summary["sell_count"] == 0
        assert summary["overall_signal"] in ("BUY", "HOLD", "SELL")

    def test_weighted_score_computed(self):
        summary = build_portfolio_summary(_HOLDINGS)
        assert isinstance(summary["weighted_score"], float)
        assert 0 < summary["weighted_score"] <= 100
