"""
congress_trade_service.py — Congress stock-trade disclosure tracking
(House Periodic Transaction Reports, via tools/house_disclosures_client.py).

Free, official, no key. Targets the same "real alternative data this
project didn't have" gap as SEC EDGAR insider transactions and ApeWisdom
Reddit attention -- genuinely new signal, not a re-derivation of price data.

The transaction-row parsing logic (TXN regex, LABELS, _finish, _amount) is
ported closely from trader-pelosi/ptr.py in vendor/trader-skill/ (MIT
License, Copyright (c) 2026 Jake Schincariol -- see vendor/trader-skill/LICENSE),
whose parser is exercised by that project's own test fixtures against real
House Clerk filings. Adapted here for this project's conventions: the
(data, error_string) tuple contract, leakage-safe as_of_date filtering, and
a ticker-indexed on-disk cache (this project needs "what did Congress trade
in THIS symbol as of THIS historical date," not ptr.py's "alert me to
anything new since my last check" design, so a full-year scan-once,
query-by-ticker-many-times shape fits better than per-prediction PDF fetches).

LEAKAGE SAFETY: fetch_congress_trades only returns transactions from PTRs
with a filing date on/before as_of_date -- same discipline as
news_sentiment_service.py / insider_activity_service.py. The cache itself
stores every transaction's filing date so this filter can be applied purely
locally, without re-fetching per as_of_date.

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

CACHE_PATH = ROOT / "data" / "congress_trade_cache.json"

# Bounds how many PTR PDFs build_cache() will fetch in one run -- a full
# year can have 1000+ filings; most don't mention a ticker anyone queries,
# and fetching every single one is both slow and unnecessary for a cache
# that's refreshed periodically (see scripts/adhoc/build_congress_trade_cache.py).
# Most-recent-filed-first, so the cache stays useful even if cut off early.
DEFAULT_MAX_FILINGS_PER_RUN = 400

TXN_TYPES = {"P": "purchase", "S": "sale", "S (partial)": "partial sale", "E": "exchange"}
OWNERS = {"SP": "spouse", "JT": "joint", "DC": "dependent child", "": "self"}
LATE_DAYS = 45

# NOTE: PyMuPDF's get_text() does NOT reproduce `pdftotext -layout`'s
# one-row-per-table-row text, which is what ptr.py's original single-line
# TXN regex assumed. Verified live this session against a real 2026 filing
# (doc 20034201): each table ROW is split across several separate physical
# text lines instead (asset name on 1-2 lines, then the transaction TYPE
# alone on its own line, then "MM/DD/YYYY MM/DD/YYYY" alone, then the
# dollar-range amount alone) -- so parsing here is anchored on those three
# unambiguous, fixed-format lines (TYPE/DATES/AMOUNT) and looks BACKWARD a
# short window for the asset name/ticker, rather than matching one row per
# line. A ticker is only trusted when it appears in parenthesized form
# "(TSLA)" -- the filing's free-text Description fields reference tickers
# unparenthesized ("TSLA – 25 shares sold"), so requiring parens is a real,
# observed discriminator against misreading description prose as the
# traded asset.
_TYPE_LINE = re.compile(r"^(S \(partial\)|P|S|E)$")
_DATE_LINE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})$")
_OWNER_PREFIX = re.compile(r"^(SP|JT|DC)\s+")
_TICKER_IN_PARENS = re.compile(r"\(([A-Z][A-Z0-9.\-/]{0,9})\)")
_PAGE_HEADER = re.compile(
    r"^(ID$|Owner Asset$|Transaction$|Type$|Date$|Notification$|Amount$|Cap\.$|Gains >\$?$|\$200\?$)", re.I)
_END = re.compile(r"^(\* For the complete|I CERTIFY|Digitally Signed|Filing ID #)", re.I)
_LABEL_LINE = re.compile(r"^(Filing Status|Subholding Of|Description|Location)\s*:", re.I)
_AMOUNT = re.compile(r"\$([\d,]+)")
_ASSET_WINDOW = 3  # non-empty, non-label lines to look back from a TYPE anchor


def _iso(mdy: str) -> Optional[str]:
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*$", mdy or "")
    if not m:
        return None
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year < 100:
        year += 2000
    try:
        return _dt.date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_index(xml_bytes: bytes, year: int) -> list:
    """Every filing in a <YEAR>FD.xml index as a dict, newest filed-date first.
    Only FilingType == 'P' (Periodic Transaction Report) matters here --
    other types (annual reports, amendments, ...) don't list trades."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_bytes)
    out = []
    for m in root.iter("Member"):
        f = {c.tag: (c.text or "").strip() for c in m}
        if f.get("FilingType") != "P":
            continue
        doc = f.get("DocID", "")
        y = int(f.get("Year") or year)
        name = " ".join(x for x in (f.get("Prefix"), f.get("First"), f.get("Last"), f.get("Suffix")) if x)
        out.append({
            "doc_id": doc, "year": y, "name": name, "district": f.get("StateDst", ""),
            "filed": _iso(f.get("FilingDate", "")),
        })
    out.sort(key=lambda r: (r["filed"] or "", r["doc_id"]), reverse=True)
    return out


def _amount_range(text: str):
    nums = [int(x.replace(",", "")) for x in _AMOUNT.findall(text or "")]
    return (nums[0] if nums else None), (nums[1] if len(nums) > 1 else None)


def parse_ptr_text(text: str, filed: Optional[str], doc_id: str, member: str) -> list:
    """Transaction rows from a glyph-shift-corrected PTR PDF text extract
    (tools.house_disclosures_client.get_ptr_pdf_text already applies the
    correction).

    Anchor-based parser (see module-level comment above the regexes for
    why): walks the text once, and whenever it finds the unambiguous
    sequence TYPE-line -> DATES-line -> AMOUNT-line, looks backward up to
    _ASSET_WINDOW non-empty/non-label/non-page-header lines for a
    parenthesized ticker. A transaction with no ticker found (can't be
    matched to a tradeable symbol) is still returned -- callers filter on
    ticker presence, same as insider_activity_service does for its own
    unresolved rows -- never silently dropped without a trace.

    Returns a flat list of transaction dicts: {owner, type, type_name,
    date, amount, amount_low, amount_high, ticker, doc_id, member, filed,
    days_to_disclose}."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    recent_asset_lines: list = []  # sliding window of candidate asset-name lines
    out = []
    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if _PAGE_HEADER.match(s) or _END.match(s) or _LABEL_LINE.match(s):
            i += 1
            continue
        if _TYPE_LINE.match(s) and i + 2 < n:
            date_line = lines[i + 1].strip()
            amount_line = lines[i + 2].strip()
            date_m = _DATE_LINE.match(date_line)
            if date_m and amount_line.startswith("$"):
                window_text = " ".join(recent_asset_lines[-_ASSET_WINDOW:])
                tick_matches = _TICKER_IN_PARENS.findall(window_text)
                owner_m = _OWNER_PREFIX.match(recent_asset_lines[0]) if recent_asset_lines else None
                owner = owner_m.group(1) if owner_m else ""
                txn_type = s
                row = {
                    "owner": owner, "owner_name": OWNERS.get(owner, owner),
                    "ticker": tick_matches[-1] if tick_matches else None,
                    "type": txn_type, "type_name": TXN_TYPES.get(txn_type, txn_type),
                    "date": _iso(date_m.group(1)),
                    "amount": " ".join(amount_line.split()),
                    "doc_id": doc_id, "member": member, "filed": filed,
                }
                row["amount_low"], row["amount_high"] = _amount_range(row["amount"])
                if filed and row["date"]:
                    row["days_to_disclose"] = (
                        _dt.date.fromisoformat(filed) - _dt.date.fromisoformat(row["date"])
                    ).days
                out.append(row)
                recent_asset_lines = []
                i += 3
                continue
        # Not a recognized anchor line -- a candidate asset-name fragment.
        recent_asset_lines.append(s)
        if len(recent_asset_lines) > _ASSET_WINDOW:
            recent_asset_lines = recent_asset_lines[-_ASSET_WINDOW:]
        i += 1
    return out


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"by_ticker": {}, "scanned_doc_ids": [], "built_at": None}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def build_cache(year: Optional[int] = None, max_filings: int = DEFAULT_MAX_FILINGS_PER_RUN) -> Tuple[Optional[dict], str]:
    """Scan one year's PTR filings (most-recent-first, bounded to
    max_filings) and build/update data/congress_trade_cache.json, a
    ticker -> [transactions] index. Designed to be re-run periodically
    (see scripts/adhoc/build_congress_trade_cache.py), not per-prediction --
    PDF fetches are slow and the data moves at most daily.

    Returns (summary_dict, error_string). Partial progress is always saved
    (a filing that fails to parse is skipped, not fatal to the run)."""
    from house_disclosures_client import get_ptr_index, get_ptr_pdf_text

    year = year or _dt.date.today().year
    idx_result = get_ptr_index(year)
    if idx_result.get("status") != "SUCCESS":
        return None, idx_result.get("message", "PTR index fetch failed")

    try:
        filings = parse_index(idx_result["xml_bytes"], year)
    except Exception as exc:
        return None, f"Index parse failed: {type(exc).__name__}: {exc}"

    cache = _load_cache()
    scanned = set(cache.get("scanned_doc_ids", []))
    by_ticker = cache.get("by_ticker", {})

    new_scanned = 0
    for f in filings:
        if new_scanned >= max_filings:
            break
        if f["doc_id"] in scanned:
            continue
        pdf_result = get_ptr_pdf_text(f["year"], f["doc_id"])
        new_scanned += 1
        scanned.add(f["doc_id"])
        if pdf_result.get("status") != "SUCCESS":
            continue
        try:
            rows = parse_ptr_text(pdf_result["text"], f["filed"], f["doc_id"], f["name"])
        except Exception:
            continue
        for row in rows:
            if not row.get("ticker"):
                continue
            by_ticker.setdefault(row["ticker"], []).append(row)

    cache["by_ticker"] = by_ticker
    cache["scanned_doc_ids"] = sorted(scanned)
    cache["built_at"] = _dt.datetime.utcnow().isoformat()
    _save_cache(cache)

    return {
        "year": year, "filings_in_index": len(filings),
        "newly_scanned_this_run": new_scanned,
        "total_scanned": len(scanned),
        "tickers_with_trades": len(by_ticker),
    }, ""


def fetch_congress_trades(symbol: str, as_of_date: str, lookback_days: int = 180) -> Tuple[Optional[dict], str]:
    """Aggregate Congress buy/sell activity for a symbol from the cache,
    counting only transactions from PTRs filed in
    [as_of_date - lookback_days, as_of_date] (LEAKAGE SAFETY -- a filing
    dated after as_of_date must never be counted, same discipline as
    insider_activity_service.fetch_insider_activity).

    Returns (data, error_string). data shape on success:
        {"buy_count": int, "sell_count": int, "net_signal": float,
         "transactions_considered": int}
    net_signal = (buy_count - sell_count) / max(buy_count + sell_count, 1),
    same bounded [-1, 1] convention as insider_activity_service.

    Reads the local cache only -- never fetches live (see build_cache()).
    If the cache doesn't exist yet or has no entry for this symbol, returns
    ({"buy_count": 0, "sell_count": 0, "net_signal": 0.0, ...}, "") -- a
    real "no data" result, not an error, since most symbols genuinely have
    no Congress trade disclosures."""
    try:
        as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d")
    except ValueError:
        return None, f"Malformed as_of_date: {as_of_date!r}"
    lookback_start = (as_of_dt - _dt.timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    as_of_str = as_of_dt.strftime("%Y-%m-%d")

    cache = _load_cache()
    if cache.get("built_at") is None:
        return None, "No congress trade cache built yet -- run scripts/adhoc/build_congress_trade_cache.py"

    rows = cache.get("by_ticker", {}).get(symbol.upper(), [])
    in_window = [
        r for r in rows
        if r.get("filed") and lookback_start <= r["filed"] <= as_of_str
    ]

    buy_count = sum(1 for r in in_window if r.get("type") == "P")
    sell_count = sum(1 for r in in_window if r.get("type") in ("S", "S (partial)"))
    total = buy_count + sell_count
    net_signal = round((buy_count - sell_count) / total, 4) if total else 0.0

    return {
        "buy_count": buy_count,
        "sell_count": sell_count,
        "net_signal": net_signal,
        "transactions_considered": len(in_window),
    }, ""
