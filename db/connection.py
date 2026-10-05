"""Shared Postgres connection helper for the central accuracy database (Supabase).

Opens a short-lived connection per call rather than holding a long-lived pool --
this is the correct usage pattern against Supabase's transaction-mode pgbouncer
endpoint (SUPABASE_DB_URL, port 6543), which should not have connections held
open idle across unrelated statements.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env", override=False)

# Makes core/, legacy/, agents/, tools/, src/ importable by bare name for
# anything that imports this module -- other db/ modules (resolver.py,
# stock_prediction_repository.py) bare-import historical_price_service,
# stock_walkforward_validator, stock_accuracy_engine, which stay at repo
# root, so this is defense-in-depth for whichever process imports db.* first.
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
import bootstrap_paths  # noqa: E402

bootstrap_paths.add_module_paths()


def _db_url() -> str:
    url = os.getenv("SUPABASE_DB_URL", "").strip()
    if not url:
        raise RuntimeError(
            "SUPABASE_DB_URL is not set in .env -- the central database is not configured."
        )
    return url


@contextmanager
def get_connection():
    """Yield a psycopg connection (autocommit), closed on exit.

    prepare_threshold=None disables psycopg's automatic server-side prepared
    statements. Supabase's pooled endpoint (SUPABASE_DB_URL, port 6543) is
    pgbouncer in transaction-pooling mode, which can silently swap the
    physical backend between statements on what looks like one logical
    connection -- a prepared statement name from one backend can then
    collide with an unrelated session's statement of the same name on
    another ("DuplicatePreparedStatement"). This is a known pgbouncer
    transaction-mode incompatibility, not specific to one query.
    """
    conn = psycopg.connect(_db_url(), connect_timeout=10, autocommit=True, prepare_threshold=None)
    try:
        yield conn
    finally:
        conn.close()
