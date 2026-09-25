"""Financial math helpers using Decimal for money values."""
from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Sequence


TWO_DP = Decimal("0.01")


def to_decimal(v: object) -> Decimal:
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def round_money(v: Decimal) -> Decimal:
    return v.quantize(TWO_DP, rounding=ROUND_HALF_UP)


def pct(v: float, decimals: int = 2) -> str:
    return f"{v * 100:.{decimals}f}%"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def annualised_return(total_return: float, days: int) -> float:
    if days <= 0 or total_return <= -1:
        return 0.0
    return (1 + total_return) ** (365.0 / days) - 1


def sharpe_ratio(returns: Sequence[float], risk_free: float = 0.0, periods_per_year: int = 252) -> Optional[float]:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std == 0:
        return None
    excess = mean - risk_free / periods_per_year
    return (excess / std) * math.sqrt(periods_per_year)


def max_drawdown(equity_curve: Sequence[float]) -> float:
    peak = float("-inf")
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def herfindahl_hirschman_index(weights: Sequence[float]) -> float:
    return sum(w ** 2 for w in weights)


def win_rate(profits: List[Decimal]) -> float:
    if not profits:
        return 0.0
    wins = sum(1 for p in profits if p > Decimal("0"))
    return wins / len(profits)
