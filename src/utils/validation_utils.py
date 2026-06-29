"""Input validation helpers."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Tuple


TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def validate_ticker(ticker: str) -> Tuple[bool, str]:
    t = ticker.strip().upper()
    if not t:
        return False, "Ticker is empty."
    if not TICKER_RE.match(t):
        return False, f"Invalid ticker format: {t}"
    return True, t


def validate_date_str(value: str, field_name: str = "date") -> Tuple[bool, Optional[date], str]:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return True, datetime.strptime(value, fmt).date(), ""
        except ValueError:
            continue
    return False, None, f"{field_name} must be YYYY-MM-DD, got: {value!r}"


def validate_date_range(start: str, end: str) -> Tuple[bool, str]:
    ok_s, d_start, err_s = validate_date_str(start, "start_date")
    if not ok_s:
        return False, err_s
    ok_e, d_end, err_e = validate_date_str(end, "end_date")
    if not ok_e:
        return False, err_e
    if d_start >= d_end:
        return False, f"start_date ({start}) must be before end_date ({end})."
    return True, ""


def validate_positive_int(value: int, field_name: str = "value") -> Tuple[bool, str]:
    if not isinstance(value, int) or value <= 0:
        return False, f"{field_name} must be a positive integer, got {value!r}."
    return True, ""


def is_valid_delta(delta: int) -> bool:
    return isinstance(delta, int) and 1 <= delta <= 99


def is_valid_dte(dte: int) -> bool:
    return isinstance(dte, int) and 1 <= dte <= 730
