"""Stock analysis data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class IntelligenceScore:
    score: float
    signal: str
    factors: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.score >= 67:
            return "BUY"
        if self.score <= 33:
            return "SELL"
        return "HOLD"


@dataclass
class StockVerdict:
    value: str
    score: float
    confidence: float
    risk_label: str
    composite_score: float


@dataclass
class PredictionRecord:
    symbol: str
    as_of_date: str
    horizon_days: int
    verdict: str
    confidence: float
    composite_score: float
    predicted_direction: str
    actual_return: Optional[float] = None
    actual_direction: Optional[str] = None
    correct: Optional[bool] = None
    evaluated: bool = False
    evaluation_date: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StockAnalysisResult:
    status: str
    symbol: str
    verdict: Optional[StockVerdict] = None
    fundamental: Optional[IntelligenceScore] = None
    technical: Optional[IntelligenceScore] = None
    valuation: Optional[IntelligenceScore] = None
    risk: Optional[IntelligenceScore] = None
    macro: Optional[IntelligenceScore] = None
    sentiment: Optional[IntelligenceScore] = None
    report: str = ""
    errors: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
