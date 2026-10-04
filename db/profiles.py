"""Maps the per-teammate CURRENT_USER env var to a `profiles` row.

Phase 1 attribution bridge: there is no real login yet (that's Phase 3,
Supabase Auth), so each teammate sets CURRENT_USER=<their name> in their own
local .env, and that name is resolved/created as a profiles row here. See
C:\\Users\\nithi\\.claude\\plans\\glowing-rolling-globe.md for the full design.
"""
from __future__ import annotations

import re
from functools import lru_cache

from db.connection import get_connection

_DEFAULT_USER = "unknown"


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", ".", name.strip().lower()).strip(".")
    return s or _DEFAULT_USER


@lru_cache(maxsize=32)
def get_or_create_profile_id(display_name: str) -> str:
    """Return profiles.id (uuid str) for display_name, creating the row if needed.

    Cached per-process: the same display_name always resolves to the same id
    within one run, avoiding a DB round trip on every single call.
    """
    name = (display_name or "").strip() or _DEFAULT_USER
    email = f"{_slug(name)}@local.alphaverity"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into profiles (email, display_name) values (%s, %s) "
                "on conflict (email) do update set display_name = excluded.display_name "
                "returning id",
                (email, name),
            )
            row = cur.fetchone()
            return str(row[0])


def get_current_profile_id() -> str:
    """Resolve the current teammate's profile id from settings.current_user."""
    from src.config.settings import settings
    return get_or_create_profile_id(settings.current_user or _DEFAULT_USER)
