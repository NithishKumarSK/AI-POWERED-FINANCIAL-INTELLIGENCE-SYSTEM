"""
Pytest: Provider Resolver Tests.

Verifies symbol resolution (RapidAPI TradingView exchange mapping) and
that TSLA does not silently resolve to AMEX (it should be NASDAQ).

No real API calls. Tests the resolver logic in isolation.
RapidAPI TradingView is the only provider — no fallback.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from historical_price_service import (
    _fmt,
    _NASDAQ,
    _NYSE,
    _AMEX,
)


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1 — TSLA resolves to NASDAQ, not AMEX
# ══════════════════════════════════════════════════════════════════════════════

def test_tsla_resolves_to_nasdaq():
    """
    TSLA is a NASDAQ-listed stock. _fmt("TSLA") must return "NASDAQ:TSLA".
    The error "HTTP 404 from batch endpoint for AMEX:TSLA" proved the resolver
    was trying all three exchanges and reporting the last failure (AMEX).
    """
    result = _fmt("TSLA")
    assert result == "NASDAQ:TSLA", (
        f"TSLA must resolve to NASDAQ:TSLA, got {result!r}. "
        "This caused the 404 error: AMEX:TSLA doesn't exist."
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2 — Common NASDAQ stocks resolve correctly
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("symbol,expected_exchange", [
    ("AAPL",  "NASDAQ"),
    ("MSFT",  "NASDAQ"),
    ("GOOGL", "NASDAQ"),
    ("AMZN",  "NASDAQ"),
    ("NVDA",  "NASDAQ"),
    ("META",  "NASDAQ"),
    ("NFLX",  "NASDAQ"),
    ("TSLA",  "NASDAQ"),
])
def test_nasdaq_symbols_resolve_correctly(symbol, expected_exchange):
    result = _fmt(symbol)
    assert result.startswith(f"{expected_exchange}:"), (
        f"{symbol} expected {expected_exchange}:{symbol}, got {result!r}"
    )
    assert result == f"{expected_exchange}:{symbol}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3 — Common NYSE stocks resolve correctly
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("symbol,expected_exchange", [
    ("JPM", "NYSE"),
    ("V",   "NYSE"),
    ("JNJ", "NYSE"),
    ("WMT", "NYSE"),
    ("BA",  "NYSE"),
])
def test_nyse_symbols_resolve_correctly(symbol, expected_exchange):
    result = _fmt(symbol)
    assert result == f"{expected_exchange}:{symbol}", (
        f"{symbol} expected {expected_exchange}:{symbol}, got {result!r}"
    )



# ══════════════════════════════════════════════════════════════════════════════
# TEST 5 — Symbol with exchange prefix passes through unchanged
# ══════════════════════════════════════════════════════════════════════════════

def test_prefixed_symbol_passthrough():
    """If symbol already has EXCHANGE: prefix, return as-is."""
    assert _fmt("NASDAQ:TSLA") == "NASDAQ:TSLA"
    assert _fmt("NYSE:JPM")    == "NYSE:JPM"
    assert _fmt("AMEX:SPY")    == "AMEX:SPY"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 6 — Unknown symbol defaults to NASDAQ (not AMEX)
# ══════════════════════════════════════════════════════════════════════════════

def test_unknown_symbol_defaults_to_nasdaq():
    """
    Unknown symbols should default to NASDAQ (most active exchange for US tech/growth).
    They must NOT default to AMEX (which causes 404 for most symbols).
    """
    result = _fmt("ZZZUNKNOWN")
    assert result.startswith("NASDAQ:"), (
        f"Unknown symbol must default to NASDAQ, got {result!r}. "
        "Defaulting to AMEX causes 404 for most symbols."
    )
    assert not result.startswith("AMEX:"), (
        f"Unknown symbol must NOT default to AMEX. Got {result!r}."
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 7 — TSLA is in NASDAQ set, NOT in AMEX set
# ══════════════════════════════════════════════════════════════════════════════

def test_tsla_not_in_amex():
    """TSLA is NASDAQ-listed. It must not be in the AMEX set."""
    assert "TSLA" in _NASDAQ, "TSLA must be in _NASDAQ set"
    assert "TSLA" not in _AMEX, "TSLA must NOT be in _AMEX set (this caused 404 errors)"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 8 — SPY resolves to AMEX (ETF exchange routing via RapidAPI)
# ══════════════════════════════════════════════════════════════════════════════

def test_spy_in_amex():
    """SPY is an ETF. It must be in _AMEX for correct exchange routing via RapidAPI."""
    assert "SPY" in _AMEX, "SPY must be in _AMEX (ETF exchange routing)"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 10 — No symbol is in both NASDAQ and AMEX (no double-registration)
# ══════════════════════════════════════════════════════════════════════════════

def test_no_symbol_in_both_nasdaq_and_amex():
    """
    Symbols must not be in both _NASDAQ and _AMEX.
    Double-registration would cause ambiguous exchange resolution.
    """
    overlap = _NASDAQ & _AMEX
    assert not overlap, (
        f"These symbols are in both _NASDAQ and _AMEX: {overlap}. "
        "Each symbol should belong to only one exchange set."
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 11 — No symbol in both NASDAQ and NYSE
# ══════════════════════════════════════════════════════════════════════════════

def test_no_symbol_in_both_nasdaq_and_nyse():
    """Symbols must not be in both _NASDAQ and _NYSE."""
    overlap = _NASDAQ & _NYSE
    assert not overlap, (
        f"These symbols are in both _NASDAQ and _NYSE: {overlap}. "
        "Ambiguous exchange assignment."
    )
