from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.identity import get_current_user_id
from backend.schemas import Profile
from db.connection import get_connection

router = APIRouter()


@router.get("/me", response_model=Profile)
def me(user_id: str = Depends(get_current_user_id)) -> Profile:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id, email, display_name, team, role from profiles where id=%s",
                (user_id,),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return Profile(id=str(row[0]), email=row[1], display_name=row[2], team=row[3], role=row[4])
