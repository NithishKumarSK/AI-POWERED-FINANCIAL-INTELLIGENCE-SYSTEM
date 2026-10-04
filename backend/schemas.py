"""Pydantic request/response models for the API."""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class StockPredictionRequest(BaseModel):
    symbol: str = Field(..., examples=["AAPL"])
    historical_context_start_date: str = Field(..., description="YYYY-MM-DD")
    prediction_origin_date: str = Field(..., description="YYYY-MM-DD")
    decision_horizon_days: int = 30
    target_date: Optional[str] = Field(None, description="YYYY-MM-DD; derived from decision_horizon_days if omitted")
    initial_capital: float = 50000
    benchmark: str = "SPY"
    validation_mode: str = "horizon_days"
    price_basis: str = "close"


class ValidationResult(BaseModel):
    status: str
    run_type: Optional[str] = None
    error: Optional[str] = None
    stock_prediction_input_hash: Optional[str] = None
    spi: Optional[Dict[str, Any]] = None
    ai_prediction: Optional[Dict[str, Any]] = None
    actual_validation: Optional[Dict[str, Any]] = None
    comparison: Optional[Dict[str, Any]] = None
    saved: Optional[bool] = None
    save_message: Optional[str] = None
    ctx_summary: Optional[Dict[str, Any]] = None


class Profile(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    team: str
    role: str


class ResolverResult(BaseModel):
    candidates: int
    resolved: int
    invalid: int
    skipped: int
    error: Optional[str] = None
