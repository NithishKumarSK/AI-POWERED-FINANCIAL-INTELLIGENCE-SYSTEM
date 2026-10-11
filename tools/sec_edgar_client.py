"""Central SEC EDGAR client — Research Expansion Program, Component 1
(insider transactions, free, no key).

Mirrors tools/alpha_vantage_client.py's pattern: structured {"status": ...}
returns, never raises. SEC-specific requirements, verified live this session
against real filings (CIK0001318605, accession 0001104659-26-106432):
- Every request needs a User-Agent with real contact info (SEC_EDGAR_CONTACT_EMAIL)
  -- this is SEC's own rule, not optional; non-compliant IPs can be blocked.
- CIK is zero-padded to exactly 10 digits in URLs.
- No API key, but keep requests well under SEC's ~10 req/sec guidance.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
_TICKER_CACHE_PATH = ROOT / "data" / "sec_edgar_ticker_cik_cache.json"

_DEFAULT_CONTACT = "research-contact@example.com"
_MIN_REQUEST_INTERVAL_S = 0.15  # stays well under SEC's ~10 req/sec guidance

_last_request_ts = 0.0


def get_sec_edgar_contact() -> str:
    return os.getenv("SEC_EDGAR_CONTACT_EMAIL", "") or _DEFAULT_CONTACT


def _headers() -> Dict[str, str]:
    return {"User-Agent": f"Stock-Prediction-Agent ({get_sec_edgar_contact()})"}


def _throttle() -> None:
    global _last_request_ts
    elapsed = time.time() - _last_request_ts
    if elapsed < _MIN_REQUEST_INTERVAL_S:
        time.sleep(_MIN_REQUEST_INTERVAL_S - elapsed)
    _last_request_ts = time.time()


def _get(url: str, timeout: int = 20) -> Dict[str, Any]:
    """GET request to a sec.gov/data.sec.gov URL.

    Returns:
        {"status": "SUCCESS", "data": <parsed JSON>}           -- for .json URLs
        {"status": "SUCCESS", "text": <raw text>}               -- for .xml/.htm URLs
        {"status": "ERROR", "error_type": ..., "message": ...}
    Never raises.
    """
    _throttle()
    try:
        resp = requests.get(url, headers=_headers(), timeout=timeout)
        if resp.status_code != 200:
            return {
                "status": "ERROR", "error_type": f"HTTP_{resp.status_code}",
                "message": f"SEC EDGAR returned HTTP {resp.status_code}",
                "preview": resp.text[:200],
            }
        if url.endswith(".json"):
            return {"status": "SUCCESS", "data": resp.json()}
        return {"status": "SUCCESS", "text": resp.text}
    except requests.Timeout:
        return {"status": "ERROR", "error_type": "TIMEOUT", "message": "Request timed out"}
    except Exception as exc:
        return {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc)}


def _load_ticker_cache() -> Optional[Dict[str, Any]]:
    if not _TICKER_CACHE_PATH.exists():
        return None
    try:
        import json
        return json.loads(_TICKER_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_ticker_cache(data: Dict[str, Any]) -> None:
    try:
        import json
        _TICKER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TICKER_CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass  # cache write failure must never block a lookup


def get_cik_for_symbol(symbol: str) -> Dict[str, Any]:
    """Resolve a ticker to its zero-padded-10-digit CIK, caching the full
    ticker->CIK map locally (it's a ~1MB file covering all US issuers,
    refetching it per lookup would be wasteful and slow).

    Returns {"status": "SUCCESS", "cik": "0001318605"} or {"status": "ERROR", ...}.
    """
    sym_upper = symbol.strip().upper()
    cache = _load_ticker_cache()
    if cache is None:
        result = _get("https://www.sec.gov/files/company_tickers.json")
        if result.get("status") != "SUCCESS":
            return result
        cache = result["data"]
        _save_ticker_cache(cache)

    for entry in cache.values():
        if entry.get("ticker", "").upper() == sym_upper:
            cik_str = str(entry["cik_str"]).zfill(10)
            return {"status": "SUCCESS", "cik": cik_str, "company_name": entry.get("title", "")}

    return {"status": "ERROR", "error_type": "SYMBOL_NOT_FOUND", "message": f"{sym_upper} not found in SEC ticker list"}


def get_submissions(cik: str) -> Dict[str, Any]:
    """Fetch filing metadata (form type, filing date, accession number per
    filing) for a CIK. Returns {"status": "SUCCESS", "data": <json>} or error."""
    return _get(f"https://data.sec.gov/submissions/CIK{cik}.json")


def get_filing_document_text(cik: str, accession_number: str, document_name: str) -> Dict[str, Any]:
    """Fetch a specific document's raw text/XML from a filing's archive
    directory. accession_number should be in dashed form (e.g.
    "0001104659-26-106432"); this function strips the dashes for the URL path."""
    accn_nodash = accession_number.replace("-", "")
    cik_nopad = str(int(cik))  # archive URLs use the un-padded CIK in the path
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_nopad}/{accn_nodash}/{document_name}"
    return _get(url)
