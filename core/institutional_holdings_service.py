"""
institutional_holdings_service.py — 13F institutional-ownership tracking
for a curated list of well-known investors (Berkshire, Pershing Square,
Scion, Bridgewater, ARK, ...), via SEC EDGAR 13F-HR filings.

Free, official, no key -- reuses tools/sec_edgar_client.py's existing
get_submissions/get_filing_document_text (already built this session for
insider transactions, same CIK/throttling/User-Agent discipline).

The filer list (core/well_known_13f_filers.json, 23 names) is vendored
verbatim from trader-copycat/filers.json in vendor/trader-skill/ (MIT
License, Copyright (c) 2026 Jake Schincariol) -- see that JSON file's
"source" key. The information-table XML parsing (parse_info_table) is
adapted from the same source's edgar13f.py.

WHAT A 13F IS, AND IS NOT (same caveats trader-copycat documents, repeated
here because they matter for how this signal should be read):
  - Filed quarterly, up to 45 days after quarter-end -- holdings can be
    up to 4.5 months stale by the time they're read.
  - Long US-listed stock positions only. No shorts, cash, bonds, foreign
    stocks, private companies, or intra-quarter trades.
  - Filed by the FIRM, not the person the firm is known for.

LEAKAGE SAFETY: fetch_institutional_holders only counts a filer's holding
if that 13F's filing date is on/before as_of_date -- a filing dated after
as_of_date must never be counted, same discipline as every other context-
enrichment source in this project.

Follows the (data, error_string) tuple convention from historical_price_service.py.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))

FILERS_PATH = ROOT / "core" / "well_known_13f_filers.json"
CACHE_PATH = ROOT / "data" / "institutional_holdings_cache.json"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def load_filers() -> list:
    try:
        return json.loads(FILERS_PATH.read_text(encoding="utf-8"))["filers"]
    except Exception:
        return []


def parse_info_table(xml_bytes: bytes) -> list:
    """Rows of a 13F information table XML, as dicts (issuer, title, cusip,
    value in dollars, shares). Adapted from trader-copycat/edgar13f.py's
    parse_info_table -- see module docstring for attribution."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_bytes)
    rows = []
    for el in root.iter():
        if _local(el.tag) != "infoTable":
            continue
        f = {}
        for child in el.iter():
            name = _local(child.tag)
            if name not in f and child.text and child.text.strip():
                f[name] = child.text.strip()
        try:
            value = float(f.get("value", "0").replace(",", ""))
            shares = float(f.get("sshPrnamt", "0").replace(",", ""))
        except ValueError:
            continue
        rows.append({
            "issuer": f.get("nameOfIssuer", ""),
            "title": f.get("titleOfClass", ""),
            "cusip": f.get("cusip", "").upper(),
            "value": value,
            "shares": shares,
        })
    return rows


def _find_info_table_document(cik_nopad: str, accn_nodash: str) -> Tuple[Optional[str], str]:
    """A 13F-HR filing's primaryDocument (from submissions JSON) is the XSLT-
    rendered cover page, not the information table -- same quirk already
    found and handled this session for Form 4 insider filings. The real
    info table is a separate, larger XML file in the same archive
    directory; verified live this session (Berkshire 2026-08-14 filing:
    cover "primary_doc.xml" is 5.5KB, the actual table "56757.xml" is
    44.7KB) so this picks the largest *.xml file that isn't primary_doc.xml."""
    from sec_edgar_client import _get

    url = f"https://www.sec.gov/Archives/edgar/data/{cik_nopad}/{accn_nodash}/index.json"
    result = _get(url)
    if result.get("status") != "SUCCESS":
        return None, result.get("message", "Archive index fetch failed")

    items = result.get("data", {}).get("directory", {}).get("item", [])
    candidates = [
        it for it in items
        if it.get("name", "").lower().endswith(".xml") and it.get("name") != "primary_doc.xml"
    ]
    if not candidates:
        return None, "No information-table XML found in filing archive"

    def _size(it):
        try:
            return int(it.get("size") or 0)
        except ValueError:
            return 0

    best = max(candidates, key=_size)
    return best["name"], ""


def fetch_latest_13f_holdings(cik: str) -> Tuple[Optional[dict], str]:
    """Fetch one filer's most recent 13F-HR holdings. Thin wrapper over
    fetch_13f_holdings_at_offset(cik, offset=0) -- kept as its own name
    for backward compatibility with existing callers (build_cache()).

    Returns (data, error_string). data shape on success:
        {"filed": "YYYY-MM-DD", "period": "YYYY-MM-DD", "rows": [...]}
    """
    return fetch_13f_holdings_at_offset(cik, offset=0)


def fetch_13f_holdings_at_offset(cik: str, offset: int = 0) -> Tuple[Optional[dict], str]:
    """Fetch one filer's Nth-most-recent 13F-HR holdings (offset=0 is the
    latest, offset=1 is the prior quarter, etc.) -- generalized for
    core/institutional_flow_tracker_service.py's quarter-over-quarter
    comparison, which needs two consecutive quarters per filer.

    Returns (data, error_string). data shape on success:
        {"filed": "YYYY-MM-DD", "period": "YYYY-MM-DD", "rows": [...]}
    """
    from sec_edgar_client import get_submissions, get_filing_document_text

    sub_result = get_submissions(cik)
    if sub_result.get("status") != "SUCCESS":
        return None, sub_result.get("message", "SEC submissions request failed")

    rec = (sub_result.get("data") or {}).get("filings", {}).get("recent", {})
    forms = rec.get("form", [])
    dates = rec.get("filingDate", [])
    accns = rec.get("accessionNumber", [])
    periods = rec.get("reportDate", [""] * len(forms))

    candidates = [
        (dates[i], accns[i], periods[i] if i < len(periods) else "")
        for i in range(len(forms)) if forms[i] == "13F-HR"
    ]
    if not candidates:
        return None, "No 13F-HR filings found for this CIK"
    candidates.sort(reverse=True)
    if offset >= len(candidates):
        return None, f"No 13F-HR filing at offset {offset} (only {len(candidates)} on record in this submissions page)"
    filed, accession, period = candidates[offset]

    cik_nopad = str(int(cik))
    accn_nodash = accession.replace("-", "")
    doc_name, err = _find_info_table_document(cik_nopad, accn_nodash)
    if not doc_name:
        return None, err

    doc_result = get_filing_document_text(cik, accession, doc_name)
    if doc_result.get("status") != "SUCCESS":
        return None, doc_result.get("message", "Information table fetch failed")

    try:
        rows = parse_info_table(doc_result["text"].encode("utf-8"))
    except Exception as exc:
        return None, f"Information table parse failed: {type(exc).__name__}: {exc}"

    return {"filed": filed, "period": period, "rows": rows}, ""


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"filers": {}, "built_at": None}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def build_cache() -> Tuple[Optional[dict], str]:
    """Refresh every filer's latest-known 13F holdings. 13F data moves at
    most quarterly, so this is meant to be re-run periodically (see
    scripts/adhoc/build_institutional_holdings_cache.py), never per-prediction.
    One filer's failure doesn't block the others -- partial progress is
    still saved."""
    filers = load_filers()
    cache = _load_cache()
    filer_cache = cache.get("filers", {})

    ok, failed = 0, []
    for f in filers:
        cik = f["cik"]
        data, err = fetch_latest_13f_holdings(cik)
        if data is None:
            failed.append({"name": f["name"], "cik": cik, "error": err})
            continue
        prior_data, _prior_err = fetch_13f_holdings_at_offset(cik, offset=1)
        filer_cache[cik] = {
            "name": f["name"], "person": f.get("person", ""),
            "filed": data["filed"], "period": data["period"], "rows": data["rows"],
            # "prior" (the quarter before "filed") powers
            # institutional_flow_tracker_service.py's QoQ accumulation/
            # distribution classification. None when unavailable (e.g. a
            # newly-registered filer) -- never blocks the "latest" caching
            # every existing caller (fetch_institutional_holders) depends on.
            "prior": prior_data,
        }
        ok += 1

    cache["filers"] = filer_cache
    cache["built_at"] = _dt.datetime.utcnow().isoformat()
    _save_cache(cache)

    return {"filers_updated": ok, "filers_failed": len(failed), "failures": failed}, ""


def _name_matches(issuer: str, company_name: str) -> bool:
    """Fuzzy match a 13F row's free-text issuer name against SEC's own
    company name for the queried symbol -- 13F issuers are often formatted
    differently ("APPLE INC" vs "Apple Inc."), so this compares normalized,
    punctuation-stripped significant words rather than requiring an exact
    string match."""
    def _words(s: str) -> set:
        s = re.sub(r"[.,\-&]", " ", s.upper())
        stop = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LLC", "THE", "CLASS", "A", "B"}
        return {w for w in s.split() if w and w not in stop}

    issuer_words = _words(issuer)
    company_words = _words(company_name)
    if not issuer_words or not company_words:
        return False
    return issuer_words.issubset(company_words) or company_words.issubset(issuer_words)


def fetch_institutional_holders(symbol: str, as_of_date: str) -> Tuple[Optional[dict], str]:
    """How many of the 23 well-known filers hold `symbol`, as of their most
    recent 13F filed on/before as_of_date (LEAKAGE SAFETY). Reads the local
    cache only -- never fetches live (see build_cache()).

    Returns (data, error_string). data shape on success:
        {"holder_count": int, "holders": [{"name", "pct_of_13f", "filed"}],
         "total_value": float}
    holder_count=0 with no error is the normal, expected "none of these 23
    hold it as of this date" result, not a failure.
    """
    from sec_edgar_client import get_cik_for_symbol

    cik_result = get_cik_for_symbol(symbol)
    if cik_result.get("status") != "SUCCESS":
        return None, cik_result.get("message", "Symbol->CIK lookup failed")
    company_name = cik_result.get("company_name", "")
    if not company_name:
        return None, "No company name resolved for this symbol"

    cache = _load_cache()
    if cache.get("built_at") is None:
        return None, "No institutional holdings cache built yet -- run scripts/adhoc/build_institutional_holdings_cache.py"

    holders = []
    total_value = 0.0
    for cik, filer in cache.get("filers", {}).items():
        if not filer.get("filed") or filer["filed"] > as_of_date[:10]:
            continue  # LEAKAGE SAFETY -- filing not yet filed as of as_of_date
        matches = [r for r in filer.get("rows", []) if _name_matches(r["issuer"], company_name)]
        if not matches:
            continue
        value = sum(r["value"] for r in matches)
        holders.append({"name": filer["name"], "value": value, "filed": filer["filed"]})
        total_value += value

    holders.sort(key=lambda h: -h["value"])
    return {
        "holder_count": len(holders),
        "holders": [{"name": h["name"], "filed": h["filed"]} for h in holders],
        "total_value": round(total_value, 2),
    }, ""
