"""Portfolio data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class Holding:
    ticker: str
    weight: float
    market_value: Optional[Decimal] = None
    shares: Optional[float] = None
    current_price: Optional[Decimal] = None
    cost_basis: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    signal: Optional[str] = None
    score: Optional[float] = None


@dataclass
class PortfolioMetrics:
    total_value: Decimal
    num_holdings: int
    top_holding_weight: float
    concentration_hhi: float
    weighted_score: Optional[float] = None
    buy_count: int = 0
    hold_count: int = 0
    sell_count: int = 0
    correlation_risk: Optional[str] = None
    diversification_score: Optional[float] = None

    @property
    def concentration_label(self) -> str:
        if self.concentration_hhi > 0.25:
            return "HIGH"
        if self.concentration_hhi > 0.15:
            return "MODERATE"
        return "LOW"


@dataclass
class PortfolioAnalysisResult:
    status: str
    holdings: List[Holding] = field(default_factory=list)
    metrics: Optional[PortfolioMetrics] = None
    correlation_matrix: Optional[Dict[str, Any]] = None
    report_text: str = ""
    errors: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
