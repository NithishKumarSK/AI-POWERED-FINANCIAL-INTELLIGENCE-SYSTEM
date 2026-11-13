"""
Client for CFTC's own free, keyless, official Commitment of Traders
(COT) Legacy Futures-Only Report, adapted from claude-trading-skills'
`cot-contrarian-detector` skill (vendor/claude-trading-skills/skills/
cot-contrarian-detector/). MIT License, Copyright (c) 2026 TraderMonty.

CRITICAL FINDING, disclosed: the source skill documents COT data as
requiring an FMP Premium+ plan ("COT endpoints require an FMP
Premium+ plan -- a free-tier key will not have access"). That is true
of FMP's specific wrapper, but the underlying data is CFTC's own
PUBLIC, FREE, government Socrata API (publicreporting.cftc.gov,
dataset `6dca-aqww`, the Legacy Futures-Only Report) -- confirmed live
this session: real weekly rows (noncomm_positions_long_all /
noncomm_positions_short_all / open_interest_all, the exact fields
cot-index-calculation.md's formula needs), no API key, going back
multiple years for e.g. the E-mini S&P 500 (code 13874A, 200 weekly
rows fetched live spanning 2023-01-03 to 2026-10-27). This unblocks
`cot-contrarian-detector` itself, not just a smaller workaround --
see core/cot_contrarian_detector_service.py.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import requests

BASE_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
TIMEOUT_SECONDS = 20

# A curated subset of CFTC's own `cftc_contract_market_code` values,
# confirmed live this session against the real Legacy report -- not the
# full ~65-market universe FMP's wrapper covers, but real, verified
# codes for the most liquid/representative markets across the same
# asset classes (indices, FX, metals, energy, rates, vol).
MARKET_CODES: Dict[str, Dict[str, str]] = {
    "ES": {"code": "13874A", "name": "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE"},
    "NQ": {"code": "209742", "name": "NASDAQ MINI - CHICAGO MERCANTILE EXCHANGE"},
    "GC": {"code": "088691", "name": "GOLD - COMMODITY EXCHANGE INC."},
    "SI": {"code": "084691", "name": "SILVER - COMMODITY EXCHANGE INC."},
    "CL": {"code": "067651", "name": "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"},
    "E6": {"code": "099741", "name": "EURO FX - CHICAGO MERCANTILE EXCHANGE"},
    "J6": {"code": "097741", "name": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE"},
    "B6": {"code": "096742", "name": "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE"},
    "ZB": {"code": "020601", "name": "UST BOND - CHICAGO BOARD OF TRADE"},
    "VX": {"code": "1170E1", "name": "VIX FUTURES - CBOE FUTURES EXCHANGE"},
}


def fetch_cot_history(contract_market_code: str, limit: int = 250) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """Weekly COT rows for one market, most-recent-first. Returns (rows, error)."""
    try:
        resp = requests.get(
            BASE_URL,
            params={
                "cftc_contract_market_code": contract_market_code,
                "$limit": limit,
                "$order": "report_date_as_yyyy_mm_dd DESC",
            },
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return None, f"network_error: {type(exc).__name__}: {exc}"
    if resp.status_code != 200:
        return None, f"http_{resp.status_code}"
    try:
        rows = resp.json()
    except ValueError:
        return None, "invalid_json_response"
    if not isinstance(rows, list) or not rows:
        return None, "no_cot_data"
    return rows, ""
