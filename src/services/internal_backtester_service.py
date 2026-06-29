"""Internal equity backtester — used for stocks/ETFs since tastytrade is options-only.

Strategies:
- buy_and_hold: buy on start_date, sell on end_date
- ma_crossover: go long when fast SMA > slow SMA, flat otherwise
"""
from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from src.utils.logging_utils import get_logger
from src.utils.math_utils import annualised_return, max_drawdown, sharpe_ratio

logger = get_logger(__name__)


def _load_csv_prices(
    ticker: str,
    start_date: str,
    end_date: str,
    dataset_path: str = "data/stock_prices_daily.csv",
) -> List[Dict[str, Any]]:
    """Load OHLCV rows for ticker from CSV within date range."""
    try:
        import pandas as pd

        df = pd.read_csv(dataset_path, parse_dates=["Date"])
        df.columns = [c.strip() for c in df.columns]
        df = df[df["Ticker"] == ticker.upper()]
        df = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)]
        df = df.sort_values("Date")
        rows = df[["Date", "Open", "High", "Low", "Close", "Volume"]].to_dict("records")
        return rows
    except Exception as exc:
        logger.warning(f"[InternalBacktester] Could not load CSV for {ticker}: {exc}")
        return []


def _sma(prices: List[float], period: int) -> List[Optional[float]]:
    result: List[Optional[float]] = []
    for i in range(len(prices)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(prices[i - period + 1: i + 1]) / period)
    return result


def run_buy_and_hold(
    ticker: str,
    start_date: str,
    end_date: str,
    initial_capital: float = 10_000.0,
    dataset_path: str = "data/stock_prices_daily.csv",
) -> Dict[str, Any]:
    """Simple buy-and-hold baseline."""
    rows = _load_csv_prices(ticker, start_date, end_date, dataset_path)
    if len(rows) < 2:
        return {"status": "ERROR", "message": f"Insufficient data for {ticker} in range."}

    entry_price = float(rows[0]["Close"])
    exit_price = float(rows[-1]["Close"])

    if entry_price <= 0:
        return {"status": "ERROR", "message": "Entry price is zero."}

    shares = initial_capital / entry_price
    final_value = shares * exit_price
    total_return = (exit_price - entry_price) / entry_price

    daily_returns = []
    prices = [float(r["Close"]) for r in rows]
    for i in range(1, len(prices)):
        if prices[i - 1] > 0:
            daily_returns.append((prices[i] - prices[i - 1]) / prices[i - 1])

    equity_curve = [initial_capital * (1 + sum(daily_returns[:i])) for i in range(len(daily_returns) + 1)]
    days = (rows[-1]["Date"] - rows[0]["Date"]).days if hasattr(rows[-1]["Date"], "year") else len(rows)

    return {
        "status": "SUCCESS",
        "strategy": "buy_and_hold",
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "entry_price": round(entry_price, 4),
        "exit_price": round(exit_price, 4),
        "shares": round(shares, 4),
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "total_return": round(total_return, 6),
        "total_return_pct": round(total_return * 100, 2),
        "cagr": round(annualised_return(total_return, max(days, 1)), 6),
        "max_drawdown": round(max_drawdown(equity_curve), 6),
        "sharpe": sharpe_ratio(daily_returns),
        "num_days": len(rows),
        "equity_curve": [
            {"date": str(rows[i]["Date"])[:10], "value": round(equity_curve[i], 2)}
            for i in range(min(len(rows), len(equity_curve)))
        ],
    }


def run_ma_crossover(
    ticker: str,
    start_date: str,
    end_date: str,
    fast: int = 20,
    slow: int = 50,
    initial_capital: float = 10_000.0,
    dataset_path: str = "data/stock_prices_daily.csv",
) -> Dict[str, Any]:
    """MA crossover: long when fast SMA > slow SMA."""
    rows = _load_csv_prices(ticker, start_date, end_date, dataset_path)
    min_required = slow + 5
    if len(rows) < min_required:
        return {"status": "ERROR", "message": f"Need at least {min_required} rows, got {len(rows)}."}

    closes = [float(r["Close"]) for r in rows]
    fast_sma = _sma(closes, fast)
    slow_sma = _sma(closes, slow)

    capital = initial_capital
    position = 0.0
    entry_price_val = 0.0
    trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []
    daily_returns: List[float] = []

    for i in range(len(rows)):
        price = closes[i]
        f = fast_sma[i]
        s = slow_sma[i]
        portfolio_val = capital + position * price
        equity_curve.append({"date": str(rows[i]["Date"])[:10], "value": round(portfolio_val, 2)})

        if f is None or s is None:
            continue

        if f > s and position == 0 and capital > 0:
            position = capital / price
            entry_price_val = price
            capital = 0.0

        elif f < s and position > 0:
            proceeds = position * price
            ret = (price - entry_price_val) / entry_price_val if entry_price_val > 0 else 0.0
            trades.append({
                "entry_date": str(rows[max(0, i - 10)]["Date"])[:10],
                "exit_date": str(rows[i]["Date"])[:10],
                "entry_price": round(entry_price_val, 4),
                "exit_price": round(price, 4),
                "profit_loss": round(proceeds - position * entry_price_val, 2),
                "return": round(ret * 100, 2),
            })
            daily_returns.append(ret)
            capital = proceeds
            position = 0.0

    final_value = capital + position * closes[-1] if closes else capital
    total_return = (final_value - initial_capital) / initial_capital

    days = len(rows)
    eq_values = [e["value"] for e in equity_curve]

    return {
        "status": "SUCCESS",
        "strategy": "ma_crossover",
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "fast_period": fast,
        "slow_period": slow,
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "total_return": round(total_return, 6),
        "total_return_pct": round(total_return * 100, 2),
        "cagr": round(annualised_return(total_return, days), 6),
        "max_drawdown": round(max_drawdown(eq_values), 6),
        "sharpe": sharpe_ratio(daily_returns) if daily_returns else None,
        "num_trades": len(trades),
        "win_rate": round(sum(1 for t in trades if t["return"] > 0) / max(len(trades), 1), 4),
        "trade_log": trades,
        "equity_curve": equity_curve,
    }


def run_equity_backtest(
    ticker: str,
    start_date: str,
    end_date: str,
    strategy: str = "buy_and_hold",
    initial_capital: float = 10_000.0,
    fast_ma: int = 20,
    slow_ma: int = 50,
    dataset_path: str = "data/stock_prices_daily.csv",
) -> Dict[str, Any]:
    """Dispatcher: run the named equity backtest strategy."""
    if strategy == "buy_and_hold":
        return run_buy_and_hold(ticker, start_date, end_date, initial_capital, dataset_path)
    if strategy == "ma_crossover":
        return run_ma_crossover(ticker, start_date, end_date, fast_ma, slow_ma, initial_capital, dataset_path)
    return {"status": "ERROR", "message": f"Unknown strategy: {strategy}"}
