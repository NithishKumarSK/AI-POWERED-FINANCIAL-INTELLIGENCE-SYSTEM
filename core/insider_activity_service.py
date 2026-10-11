"""
insider_activity_service.py — Research Expansion Program, Component 1.

SEC Form 4 insider-transaction activity for single-name symbols, via SEC
EDGAR (tools/sec_edgar_client.py). Free, official, no key. Targets the same
proven weak spot as Phase 3's earnings/sentiment work: narrative-driven
single names where technical-only features show no edge.

XML schema verified live this session against a real filing (TSLA,
CIK0001318605, accession 0001104659-26-106432) -- not assumed from docs.
Only nonDerivativeTransaction entries are counted (actual share buys/sells),
not derivative/option transactions, which are a noisier signal.

LEAKAGE SAFETY: only filings with a filing date on/before as_of_date are
counted -- same discipline as news_sentiment_service.py. SEC's submissions
API gives the actual filing date per entry, so this is a real point-in-time
filter, not an approximation.

Follows the (data, error_string) tuple convention from historical_price_service.py.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))

MAX_FILINGS_TO_PARSE = 20  # bounds latency -- most-recent N Form 4s in the lookback window


def _parse_form4_transactions(xml_text: str) -> list:
    """Parse nonDerivativeTransaction entries from a Form 4 XML document.
    Returns a list of {"date": str, "code": str, "acquired_disposed": "A"|"D",
    "shares": float} dicts. Malformed/unexpected entries are skipped, not
    fatal -- one bad filing must not break the whole aggregate signal."""
    out = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out

    for txn in root.findall(".//nonDerivativeTransaction"):
        try:
            date_el = txn.find("./transactionDate/value")
            code_el = txn.find("./transactionCoding/transactionCode")
            ad_el = txn.find("./transactionAmounts/transactionAcquiredDisposedCode/value")
            shares_el = txn.find("./transactionAmounts/transactionShares/value")
            if date_el is None or ad_el is None:
                continue
            out.append({
                "date": (date_el.text or "").strip(),
                "code": (code_el.text or "").strip() if code_el is not None else "",
                "acquired_disposed": (ad_el.text or "").strip(),
                "shares": float(shares_el.text) if shares_el is not None and shares_el.text else 0.0,
            })
        except (ValueError, AttributeError):
            continue
    return out


def fetch_insider_activity(symbol: str, as_of_date: str, lookback_days: int = 90) -> Tuple[Optional[dict], str]:
    """Fetch and aggregate insider buy/sell activity for a symbol, counting
    only Form 4 filings with filing_date in [as_of_date - lookback_days, as_of_date]
    (LEAKAGE SAFETY -- see module docstring).

    Returns (data, error_string). data shape on success:
        {"buy_count": int, "sell_count": int, "net_signal": float,
         "filings_parsed": int}
    net_signal = (buy_count - sell_count) / max(buy_count + sell_count, 1),
    a bounded [-1, 1] direction signal regardless of absolute filing volume.
    """
    from sec_edgar_client import get_cik_for_symbol, get_submissions, get_filing_document_text
    from datetime import datetime, timedelta

    try:
        as_of_dt = datetime.strptime(as_of_date[:10], "%Y-%m-%d")
    except ValueError:
        return None, f"Malformed as_of_date: {as_of_date!r}"
    lookback_start = (as_of_dt - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    as_of_str = as_of_dt.strftime("%Y-%m-%d")

    cik_result = get_cik_for_symbol(symbol)
    if cik_result.get("status") != "SUCCESS":
        return None, cik_result.get("message", "CIK lookup failed")
    cik = cik_result["cik"]

    sub_result = get_submissions(cik)
    if sub_result.get("status") != "SUCCESS":
        return None, sub_result.get("message", "SEC submissions request failed")

    recent = (sub_result.get("data") or {}).get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accns = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])

    if not (len(forms) == len(dates) == len(accns) == len(docs)):
        return None, "Unexpected SEC submissions response shape (parallel arrays mismatched)"

    # Filter to Form 4 filings within [lookback_start, as_of_str] -- leakage
    # safety: a filing dated AFTER as_of_date must never be counted.
    candidates = []
    for i, form in enumerate(forms):
        if form != "4":
            continue
        fdate = dates[i]
        if lookback_start <= fdate <= as_of_str:
            candidates.append((fdate, accns[i], docs[i]))

    candidates.sort(reverse=True)  # most recent first
    candidates = candidates[:MAX_FILINGS_TO_PARSE]

    buy_count = 0
    sell_count = 0
    filings_parsed = 0
    for fdate, accn, doc_name in candidates:
        # primaryDocument is sometimes the XSLT-rendering path
        # ("xslF345X06/<name>.xml") rather than the raw XML filename -- the
        # raw XML lives at the filing root under just <name>.xml (verified
        # live this session). Strip any directory prefix.
        raw_doc_name = doc_name.rsplit("/", 1)[-1]
        doc_result = get_filing_document_text(cik, accn, raw_doc_name)
        if doc_result.get("status") != "SUCCESS":
            continue  # one unreadable filing must not kill the whole aggregate
        transactions = _parse_form4_transactions(doc_result.get("text", ""))
        if not transactions:
            continue
        filings_parsed += 1
        for t in transactions:
            # Re-check the transaction's own date too, not just the filing
            # date -- defense in depth, same "don't trust upstream alone"
            # discipline as news_sentiment_service.py.
            if t["date"] and t["date"] > as_of_str:
                continue
            if t["acquired_disposed"] == "A":
                buy_count += 1
            elif t["acquired_disposed"] == "D":
                sell_count += 1

    total = buy_count + sell_count
    net_signal = round((buy_count - sell_count) / total, 4) if total else 0.0

    return {
        "buy_count": buy_count,
        "sell_count": sell_count,
        "net_signal": net_signal,
        "filings_parsed": filings_parsed,
    }, ""
