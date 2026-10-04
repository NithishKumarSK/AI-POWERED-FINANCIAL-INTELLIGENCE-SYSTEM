from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from backend.identity import get_current_user_id
from backend.orchestration import run_stock_price_validation
from backend.schemas import StockPredictionRequest, ValidationResult
from db.stock_prediction_repository import get_accuracy_summary, load_stock_prediction_records

router = APIRouter()

Scope = Literal["team", "mine"]


@router.post("/stock-predictions/validate", response_model=ValidationResult)
def validate(payload: StockPredictionRequest, user_id: str = Depends(get_current_user_id)) -> dict:
    result = run_stock_price_validation(payload.model_dump())
    return result


@router.get("/stock-predictions")
def list_predictions(
    scope: Scope = "team",
    limit: int = Query(50, ge=1, le=500),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    uid = user_id if scope == "mine" else None
    records = load_stock_prediction_records(limit=limit, user_id=uid)
    return {"records": records, "count": len(records)}


@router.get("/stock-predictions/summary")
def summary(scope: Scope = "team", user_id: str = Depends(get_current_user_id)) -> dict:
    uid = user_id if scope == "mine" else None
    records = load_stock_prediction_records(limit=10000, user_id=uid)
    return get_accuracy_summary(records)
