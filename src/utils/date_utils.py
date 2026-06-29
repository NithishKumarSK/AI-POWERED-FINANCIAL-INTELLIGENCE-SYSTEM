"""Date helpers used across services."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional


def today_str() -> str:
    return date.today().isoformat()


def n_years_ago(n: int) -> str:
    d = date.today() - timedelta(days=365 * n)
    return d.isoformat()


def to_iso_date(value: str) -> str:
    """Normalise various date strings to YYYY-MM-DD."""
    value = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value


def to_iso_datetime(d: str) -> str:
    """Return YYYY-MM-DDT00:00:00Z format expected by tastytrade end_date."""
    base = to_iso_date(d)
    return f"{base}T00:00:00Z"


def days_between(start: str, end: str) -> Optional[int]:
    try:
        d1 = date.fromisoformat(to_iso_date(start))
        d2 = date.fromisoformat(to_iso_date(end))
        return (d2 - d1).days
    except Exception:
        return None


def default_backtest_range(years: int = 5) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=365 * years)
    return start.isoformat(), end.isoformat()
