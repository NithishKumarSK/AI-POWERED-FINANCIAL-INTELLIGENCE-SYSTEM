"""4 tests for the internal equity backtester — runs without real data by using a temp CSV."""
from __future__ import annotations

import csv
import os
import tempfile
from datetime import date, timedelta

import pytest

from src.services.internal_backtester_service import (
    run_buy_and_hold,
    run_ma_crossover,
    run_equity_backtest,
)


def _write_temp_csv(ticker: str = "TEST", n_days: int = 120) -> str:
    rows = []
    base = date(2020, 1, 2)
    price = 100.0
    for i in range(n_days):
        d = base + timedelta(days=i)
        price = max(10.0, price + (1 if i % 3 == 0 else -0.5))
        rows.append({
            "Date": d.isoformat(),
            "Ticker": ticker,
            "Open": round(price * 0.99, 2),
            "High": round(price * 1.01, 2),
            "Low": round(price * 0.98, 2),
            "Close": round(price, 2),
            "Volume": 1_000_000,
        })
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
    writer = csv.DictWriter(tmp, fieldnames=["Date", "Ticker", "Open", "High", "Low", "Close", "Volume"])
    writer.writeheader()
    writer.writerows(rows)
    tmp.close()
    return tmp.name


class TestBuyAndHold:
    def setup_method(self):
        self.csv = _write_temp_csv("ATEST", 100)

    def teardown_method(self):
        os.unlink(self.csv)

    def test_success_with_valid_data(self):
        result = run_buy_and_hold("ATEST", "2020-01-02", "2020-04-10", dataset_path=self.csv)
        assert result["status"] == "SUCCESS"
        assert "total_return" in result
        assert "final_value" in result

    def test_missing_ticker_returns_error(self):
        result = run_buy_and_hold("NODATA", "2020-01-02", "2020-04-10", dataset_path=self.csv)
        assert result["status"] == "ERROR"


class TestMACrossover:
    def setup_method(self):
        self.csv = _write_temp_csv("BTEST", 200)

    def teardown_method(self):
        os.unlink(self.csv)

    def test_success_with_enough_data(self):
        result = run_ma_crossover("BTEST", "2020-01-02", "2020-07-10", fast=10, slow=30, dataset_path=self.csv)
        assert result["status"] == "SUCCESS"
        assert "win_rate" in result

    def test_dispatcher_routes_correctly(self):
        result = run_equity_backtest("BTEST", "2020-01-02", "2020-07-10", strategy="ma_crossover",
                                     fast_ma=10, slow_ma=30, dataset_path=self.csv)
        assert result["status"] == "SUCCESS"
        assert result["strategy"] == "ma_crossover"
