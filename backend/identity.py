"""Per-request user identity for the API.

v1 note: this is NOT real authentication (no password, no session token) --
it's the same Phase 1 attribution bridge (a display name mapped to a
`profiles` row via db.profiles) extended to the web: the frontend asks for a
name once, stores it in the browser, and sends it as the X-User-Name header
on every request. Good enough to give every record a real owner and power
"My Runs" vs "Team Runs" -- but anyone can type any name. Real login
(Supabase Auth, a password, a session that can't be spoofed) is a documented
follow-up, not done here.
"""
from __future__ import annotations

from fastapi import Header, HTTPException

from db.profiles import get_or_create_profile_id


def get_current_user_id(x_user_name: str | None = Header(default=None)) -> str:
    name = (x_user_name or "").strip()
    if not name:
        raise HTTPException(status_code=401, detail="X-User-Name header is required")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Name is too long")
    return get_or_create_profile_id(name)
