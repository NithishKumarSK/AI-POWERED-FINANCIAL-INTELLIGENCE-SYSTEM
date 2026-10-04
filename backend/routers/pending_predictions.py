from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends

from backend.identity import get_current_user_id
from backend.schemas import ResolverResult
from db.stock_prediction_repository import load_pending_predictions

router = APIRouter()

Scope = Literal["team", "mine"]


@router.get("/pending-predictions")
def list_pending(scope: Scope = "team", user_id: str = Depends(get_current_user_id)) -> dict:
    uid = user_id if scope == "mine" else None
    records = load_pending_predictions(user_id=uid)
    return {"records": records, "count": len(records)}


@router.post("/pending-predictions/resolve", response_model=ResolverResult)
def resolve(user_id: str = Depends(get_current_user_id)) -> dict:
    # Any authenticated user can trigger a resolve pass -- it only ever acts
    # on rows whose target_date has already arrived, so there's no
    # privileged action being gated here (matches the Streamlit sidebar
    # button's behavior in Phase 1).
    from db.resolver import resolve_pending_predictions
    return resolve_pending_predictions()
