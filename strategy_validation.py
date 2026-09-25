"""
Strategy Input Validation Gate (Central)
FINAL STRICT PROMPT Phase 1: ALL strategy inputs MUST pass this gate before AI/backtest.
If validation fails: st.error() + st.stop() — NO AI, NO backtest, NO charts, NO accuracy record.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import List, Tuple

# Known placeholder / fake / test symbols that are not real tradable instruments
_BLOCKED_SYMBOLS: frozenset = frozenset({
    "XYZ", "ABCXYZ", "ABC", "ABCD", "ABCDE",
    "TEST", "NONE", "NULL", "NA", "N/A",
    "SYMBOL", "TICKER", "STOCK", "EXAMPLE", "FAKE", "DEMO",
    "PLACEHOLDER", "SAMPLE",
    "XXXX", "YYYY", "ZZZZ",
    "AAAA", "BBBB", "CCCC", "DDDD", "EEEE",
    "QQQQ",  # real ETF but also common test placeholder — allow QQQQ if ever needed by removing
})

# 1-5 uppercase letters, optionally followed by . or - and one letter (for BRK.B, BRK-B)
_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}([.\-][A-Z])?$")

# Earliest date with reliable options data on tastytrade
_MIN_DATE = date(2000, 1, 1)


def _parse_date_safe(s: str):
    """Return date object or None on any parse failure."""
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError, AttributeError):
        return None


def validate_symbol(symbol: str) -> Tuple[bool, str]:
    """
    Validate a ticker symbol.
    Returns (is_valid, error_message).
    """
    if not symbol or not str(symbol).strip():
        return False, "Symbol is required — cannot be blank."

    sym = str(symbol).strip().upper()

    if not sym:
        return False, "Symbol is required — cannot be blank or whitespace-only."

    if not _SYMBOL_RE.match(sym):
        return False, (
            f"Symbol '{sym}' is invalid. Use 1-5 uppercase letters "
            f"(e.g., AAPL, MSFT, SPY, BRK.B). Got '{sym}' ({len(sym)} chars)."
        )

    if sym in _BLOCKED_SYMBOLS:
        return False, (
            f"Symbol '{sym}' is a placeholder/test symbol and is not a real "
            f"tradable instrument. Enter a valid stock or ETF ticker."
        )

    return True, ""


def validate_dates(start_date: str, end_date: str) -> Tuple[bool, List[str]]:
    """
    Validate date range.
    Rules: both parseable, start >= 2000-01-01, end <= today, start < end, range >= 180 days.
    Returns (is_valid, list_of_errors).
    """
    errors: List[str] = []
    today = date.today()

    s = _parse_date_safe(start_date)
    e = _parse_date_safe(end_date)

    if s is None:
        errors.append(
            f"Start date '{start_date}' is not a valid date. "
            f"Use YYYY-MM-DD format (e.g., 2021-06-25)."
        )
    if e is None:
        errors.append(
            f"End date '{end_date}' is not a valid date. "
            f"Use YYYY-MM-DD format (e.g., 2025-01-24)."
        )

    if s is not None:
        if s < _MIN_DATE:
            errors.append(
                f"Start date {start_date} is before 2000-01-01. "
                f"Historical options data is not available before year 2000."
            )
        if s >= today:
            errors.append(
                f"Start date {start_date} is today or in the future "
                f"(today = {today}). Start date must be in the past."
            )

    if e is not None:
        if e > today:
            errors.append(
                f"End date {end_date} is in the future (today = {today}). "
                f"Backtesting requires historical data only — no future dates allowed."
            )

    if s is not None and e is not None and not errors:
        if s >= e:
            errors.append(
                f"Start date {start_date} must be before end date {end_date}."
            )
        else:
            days = (e - s).days
            if days < 180:
                errors.append(
                    f"Date range is only {days} days "
                    f"({start_date} → {end_date}). "
                    f"A minimum of 180 days is required for meaningful backtesting."
                )

    return len(errors) == 0, errors


def validate_strategy_input(si: dict) -> Tuple[bool, str]:
    """
    Central validation gate. Validates ALL strategy inputs.
    Returns (is_valid, error_message_string).

    Called BEFORE every run. Failure MUST block all downstream processing:
    no AI prediction, no backtest, no charts, no accuracy record.
    """
    errors: List[str] = []

    # ── Symbol ────────────────────────────────────────────────────────────────
    raw_symbol = str(si.get("symbol", "") or "")
    sym_ok, sym_err = validate_symbol(raw_symbol)
    if not sym_ok:
        errors.append(sym_err)

    # ── Dates ─────────────────────────────────────────────────────────────────
    start = str(si.get("start_date", "") or "")
    end   = str(si.get("end_date",   "") or "")
    dates_ok, date_errors = validate_dates(start, end)
    errors.extend(date_errors)

    # ── Benchmark ─────────────────────────────────────────────────────────────
    bench = str(si.get("benchmark", "SPY") or "SPY").strip().upper()
    if bench and not _SYMBOL_RE.match(bench):
        errors.append(f"Benchmark '{bench}' is not a valid symbol.")

    # ── Initial capital ────────────────────────────────────────────────────────
    try:
        cap = float(si.get("initial_capital", 0) or 0)
        if cap <= 0:
            errors.append("Initial capital must be greater than $0.")
        elif cap < 1000:
            errors.append("Initial capital must be at least $1,000.")
    except (TypeError, ValueError):
        errors.append("Initial capital must be a valid number.")

    # ── Direction / side ───────────────────────────────────────────────────────
    direction = str(si.get("direction", "") or "").lower().strip()
    if direction not in ("short", "long"):
        errors.append(f"Direction must be 'short' or 'long', got '{direction}'.")

    side = str(si.get("side", "") or "").lower().strip()
    if side not in ("put", "call"):
        errors.append(f"Side must be 'put' or 'call', got '{side}'.")

    # ── DTE ───────────────────────────────────────────────────────────────────
    try:
        dte = int(si.get("dte", 0) or 0)
        if not 1 <= dte <= 365:
            errors.append(f"DTE must be between 1 and 365, got {dte}.")
    except (TypeError, ValueError):
        errors.append("DTE must be a valid integer.")

    # ── Delta ─────────────────────────────────────────────────────────────────
    try:
        delta = int(si.get("delta", 0) or 0)
        if not 1 <= delta <= 99:
            errors.append(f"Delta must be between 1 and 99, got {delta}.")
    except (TypeError, ValueError):
        errors.append("Delta must be a valid integer.")

    # ── Legs ──────────────────────────────────────────────────────────────────
    try:
        legs = int(si.get("legs", 1) or 1)
        if not 1 <= legs <= 4:
            errors.append(f"Legs must be 1-4, got {legs}.")
    except (TypeError, ValueError):
        errors.append("Legs must be a valid integer.")

    # ── Entry frequency ───────────────────────────────────────────────────────
    freq = str(si.get("entry_frequency", "") or "").lower().strip()
    if freq not in ("daily", "weekly", "monthly"):
        errors.append(
            f"Entry frequency must be daily/weekly/monthly, got '{freq}'."
        )

    # ── Decision horizon ──────────────────────────────────────────────────────
    try:
        horizon = int(si.get("decision_horizon", 30) or 30)
        if not 1 <= horizon <= 365:
            errors.append(f"Decision horizon must be 1-365, got {horizon}.")
    except (TypeError, ValueError):
        errors.append("Decision horizon must be a valid integer.")

    if errors:
        return False, "; ".join(errors)
    return True, ""


def validate_strategy_input_all_errors(si: dict) -> Tuple[bool, List[str]]:
    """Same as validate_strategy_input but returns the full list of errors."""
    ok, combined = validate_strategy_input(si)
    if ok:
        return True, []
    return False, [e.strip() for e in combined.split(";") if e.strip()]
