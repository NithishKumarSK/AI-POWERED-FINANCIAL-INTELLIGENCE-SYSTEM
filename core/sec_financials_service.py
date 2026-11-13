"""
sec_financials_service.py -- key fundamentals (revenue, net income, EPS,
YoY growth) from SEC EDGAR's XBRL company-facts API, adapted from
trader-skill's trader-analyst skill
(vendor/trader-skill/trader-analyst/facts.py, MIT License, Copyright (c)
2026 Jake Schincariol).

Free, official, no key -- reuses tools/sec_edgar_client.py (same
CIK/throttling/User-Agent discipline already built this session for
insider transactions and 13F holdings).

Response shape verified live this session against real AAPL XBRL facts:
each fact entry has start/end/val/accn/fy/fp/form/filed. A single XBRL tag
(e.g. NetIncomeLoss) mixes quarterly-span AND cumulative/YTD-span entries
in the same list -- this module keeps only entries whose (end - start) is
approximately one year (350-380 days) for the "annual" figures used here,
rather than attempting the source skill's fuller quarterly-derivation
logic (deriving Q4 = 10-K minus three 10-Qs), which needs more fixture
coverage to get right than is warranted for this project's purposes (YoY
annual context, not full quarterly modeling).

LEAKAGE SAFETY: only XBRL facts from filings with a 'filed' date on/before
as_of_date are used -- same discipline as every other context-enrichment
source in this project.

Follows the (data, error_string) tuple convention from historical_price_service.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))

_ANNUAL_SPAN_MIN_DAYS = 350
_ANNUAL_SPAN_MAX_DAYS = 380

# Revenue has two common tag names across different filers/periods --
# tried in order, first one with usable annual data wins.
_REVENUE_TAGS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")
_NET_INCOME_TAG = "NetIncomeLoss"
_EPS_TAG = "EarningsPerShareDiluted"


def _annual_entries(fact_entries: list, as_of_date: str) -> list:
    """Entries with roughly a 1-year span, filed on/before as_of_date,
    sorted newest period-end first."""
    import datetime as _dt
    as_of = as_of_date[:10]
    out = []
    for e in fact_entries:
        if not e.get("filed") or e["filed"] > as_of:
            continue  # LEAKAGE SAFETY
        try:
            start = _dt.date.fromisoformat(e["start"])
            end = _dt.date.fromisoformat(e["end"])
        except (KeyError, ValueError):
            continue
        span_days = (end - start).days
        if _ANNUAL_SPAN_MIN_DAYS <= span_days <= _ANNUAL_SPAN_MAX_DAYS:
            out.append(e)
    out.sort(key=lambda e: e["end"], reverse=True)
    return out


def _latest_and_prior_year(fact_entries: list, as_of_date: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """Returns (latest_value, prior_year_value, latest_period_end) from the
    most recent two non-overlapping annual entries, or (None, None, None)
    if fewer than one is available."""
    annual = _annual_entries(fact_entries, as_of_date)
    if not annual:
        return None, None, None
    latest = annual[0]
    prior = next((e for e in annual[1:] if e["end"] < latest["start"]), None)
    return latest["val"], (prior["val"] if prior else None), latest["end"]


_QUARTER_SPAN_MIN_DAYS = 80
_QUARTER_SPAN_MAX_DAYS = 100


def _quarterly_entries(fact_entries: list, as_of_date: str) -> list:
    """Single-quarter-span entries (80-100 days), filed on/before as_of_date,
    sorted newest period-end first. SEC XBRL mixes standalone-quarter spans
    with cumulative/YTD spans in the same tag's entry list (confirmed live
    this session against real KO EarningsPerShareDiluted data: a Q3 entry
    with start=2026-07-04/end=2026-10-02 (91-day standalone quarter) sits
    alongside a start=2026-01-01/end=2026-10-02 entry (9-month YTD) under
    the exact same tag) -- this filters to only the standalone-quarter ones,
    the same span-based technique _annual_entries already uses for 1-year spans."""
    import datetime as _dt
    as_of = as_of_date[:10]
    out = []
    for e in fact_entries:
        if not e.get("filed") or e["filed"] > as_of:
            continue  # LEAKAGE SAFETY
        try:
            start = _dt.date.fromisoformat(e["start"])
            end = _dt.date.fromisoformat(e["end"])
        except (KeyError, ValueError):
            continue
        span_days = (end - start).days
        if _QUARTER_SPAN_MIN_DAYS <= span_days <= _QUARTER_SPAN_MAX_DAYS:
            out.append(e)
    # De-duplicate identical (start,end) pairs filed in multiple 10-Qs (e.g.
    # the same Q3 reported in both the Q3 10-Q and the next Q's comparative
    # column); keep the one with the latest 'filed' date for each period.
    by_period: dict = {}
    for e in out:
        key = (e["start"], e["end"])
        if key not in by_period or e["filed"] > by_period[key]["filed"]:
            by_period[key] = e
    deduped = list(by_period.values())
    deduped.sort(key=lambda e: e["end"], reverse=True)
    return deduped


def fetch_quarterly_eps_revenue_series(symbol: str, as_of_date: str, num_quarters: int = 8) -> Tuple[Optional[list], str]:
    """Most-recent `num_quarters` standalone-quarter EPS (diluted) + revenue
    figures for a symbol, as of a given date, most-recent-quarter-first --
    the same shape claude-trading-skills' canslim-screener expects from FMP's
    quarterly income statement endpoint (list of {"date","eps","revenue"}),
    built here from SEC XBRL instead (no FMP needed).

    Returns (data, error_string). data: list of
        {"date": "YYYY-MM-DD" (period end), "eps": float, "revenue": float}
    newest first. Entries with a resolvable EPS but no resolvable revenue
    still appear (revenue=None) rather than being dropped -- callers that
    need both (like calculate_quarterly_growth) already check for None.
    """
    from sec_edgar_client import get_cik_for_symbol, _get

    cik_result = get_cik_for_symbol(symbol)
    if cik_result.get("status") != "SUCCESS":
        return None, cik_result.get("message", "Symbol->CIK lookup failed")
    cik = cik_result["cik"]

    facts_result = _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    if facts_result.get("status") != "SUCCESS":
        return None, facts_result.get("message", "XBRL company facts request failed")

    us_gaap = (facts_result.get("data") or {}).get("facts", {}).get("us-gaap", {})
    if not us_gaap:
        return None, "No us-gaap XBRL facts available for this filer"

    eps_entries_raw = (us_gaap.get(_EPS_TAG, {}).get("units", {}) or {}).get("USD/shares", [])
    eps_quarters = _quarterly_entries(eps_entries_raw, as_of_date)
    if not eps_quarters:
        return None, "No standalone-quarter EPS facts found on/before as_of_date"

    # Revenue by period-end (best-available tag), to merge onto the EPS quarters.
    revenue_by_period: dict = {}
    for tag in _REVENUE_TAGS:
        entries = (us_gaap.get(tag, {}).get("units", {}) or {}).get("USD", [])
        for e in _quarterly_entries(entries, as_of_date):
            revenue_by_period.setdefault(e["end"], e["val"])

    series = []
    for e in eps_quarters[:num_quarters]:
        series.append({"date": e["end"], "eps": e["val"], "revenue": revenue_by_period.get(e["end"])})

    if not series:
        return None, "No usable quarterly EPS facts found on/before as_of_date"
    return series, ""


def fetch_annual_eps_revenue_series(symbol: str, as_of_date: str, num_years: int = 4) -> Tuple[Optional[list], str]:
    """Most-recent `num_years` annual EPS (diluted) + revenue figures, most-
    recent-year-first -- the shape claude-trading-skills' canslim-screener
    expects from FMP's annual income statement endpoint, built from SEC
    XBRL instead.

    Returns (data, error_string). data: list of
        {"date": "YYYY-MM-DD" (period end), "eps": float, "revenue": float}
    """
    from sec_edgar_client import get_cik_for_symbol, _get

    cik_result = get_cik_for_symbol(symbol)
    if cik_result.get("status") != "SUCCESS":
        return None, cik_result.get("message", "Symbol->CIK lookup failed")
    cik = cik_result["cik"]

    facts_result = _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    if facts_result.get("status") != "SUCCESS":
        return None, facts_result.get("message", "XBRL company facts request failed")

    us_gaap = (facts_result.get("data") or {}).get("facts", {}).get("us-gaap", {})
    if not us_gaap:
        return None, "No us-gaap XBRL facts available for this filer"

    eps_entries_raw = (us_gaap.get(_EPS_TAG, {}).get("units", {}) or {}).get("USD/shares", [])
    eps_years = _annual_entries(eps_entries_raw, as_of_date)
    if not eps_years:
        return None, "No annual EPS facts found on/before as_of_date"

    # De-duplicate to one entry per fiscal year-end (same technique as quarterly).
    by_period: dict = {}
    for e in eps_years:
        key = e["end"]
        if key not in by_period or e["filed"] > by_period[key]["filed"]:
            by_period[key] = e
    eps_years = sorted(by_period.values(), key=lambda e: e["end"], reverse=True)

    revenue_by_period: dict = {}
    for tag in _REVENUE_TAGS:
        entries = (us_gaap.get(tag, {}).get("units", {}) or {}).get("USD", [])
        for e in _annual_entries(entries, as_of_date):
            revenue_by_period.setdefault(e["end"], e["val"])

    series = []
    for e in eps_years[:num_years]:
        series.append({"date": e["end"], "eps": e["val"], "revenue": revenue_by_period.get(e["end"])})

    if not series:
        return None, "No usable annual EPS facts found on/before as_of_date"
    return series, ""


_DIVIDENDS_PAID_TAGS = ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "PaymentsOfOrdinaryDividends", "DividendsCommonStockCash")
_OCF_TAG = "NetCashProvidedByUsedInOperatingActivities"
_CAPEX_TAG = "PaymentsToAcquirePropertyPlantAndEquipment"
_DILUTED_SHARES_TAG = "WeightedAverageNumberOfDilutedSharesOutstanding"
_EQUITY_TAG = "StockholdersEquity"


def fetch_annual_dividend_series(symbol: str, as_of_date: str, num_years: int = 4) -> Tuple[Optional[list], str]:
    """Most-recent `num_years` annual dividends-per-share figures (derived
    as total dividends paid / weighted-average diluted shares, since the
    per-share XBRL tag CommonStockDividendsPerShareDeclared was found live
    this session to be stale/unreported for some real filers -- e.g. KO's
    only entries are from 2008-2009 -- while PaymentsOfDividends and
    WeightedAverageNumberOfDilutedSharesOutstanding are both reliably
    current), most-recent-year-first.

    Returns (data, error_string). data: list of
        {"date": "YYYY-MM-DD" (period end), "dividend_per_share": float,
         "dividends_paid_total": float}
    """
    from sec_edgar_client import get_cik_for_symbol, _get

    cik_result = get_cik_for_symbol(symbol)
    if cik_result.get("status") != "SUCCESS":
        return None, cik_result.get("message", "Symbol->CIK lookup failed")
    cik = cik_result["cik"]

    facts_result = _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    if facts_result.get("status") != "SUCCESS":
        return None, facts_result.get("message", "XBRL company facts request failed")

    us_gaap = (facts_result.get("data") or {}).get("facts", {}).get("us-gaap", {})
    if not us_gaap:
        return None, "No us-gaap XBRL facts available for this filer"

    # Dividends-paid is reported under different tag names across filers
    # (confirmed live this session: KO uses PaymentsOfDividends, JNJ uses
    # PaymentsOfOrdinaryDividends/DividendsCommonStockCash instead and has
    # neither PaymentsOfDividends nor PaymentsOfDividendsCommonStock at
    # all) -- same multi-tag-fallback pattern as _REVENUE_TAGS, keeping
    # whichever tag gives the most recent period.
    div_years = []
    best_tag_period = None
    for tag in _DIVIDENDS_PAID_TAGS:
        entries = (us_gaap.get(tag, {}).get("units", {}) or {}).get("USD", [])
        candidate_years = _annual_entries(entries, as_of_date)
        if candidate_years and (best_tag_period is None or candidate_years[0]["end"] > best_tag_period):
            div_years = candidate_years
            best_tag_period = candidate_years[0]["end"]
    if not div_years:
        return None, "No annual dividends-paid facts found on/before as_of_date"

    by_period: dict = {}
    for e in div_years:
        key = e["end"]
        if key not in by_period or e["filed"] > by_period[key]["filed"]:
            by_period[key] = e
    div_years = sorted(by_period.values(), key=lambda e: e["end"], reverse=True)

    shares_entries_raw = (us_gaap.get(_DILUTED_SHARES_TAG, {}).get("units", {}) or {}).get("shares", [])
    shares_by_period: dict = {}
    for e in _annual_entries(shares_entries_raw, as_of_date):
        shares_by_period.setdefault(e["end"], e["val"])

    series = []
    for e in div_years[:num_years]:
        shares = shares_by_period.get(e["end"])
        dividends_paid_total = abs(e["val"])
        dividend_per_share = (dividends_paid_total / shares) if shares else None
        series.append({"date": e["end"], "dividend_per_share": dividend_per_share, "dividends_paid_total": dividends_paid_total})

    if not series:
        return None, "No usable annual dividend facts found on/before as_of_date"
    return series, ""


def fetch_cash_flow_coverage(symbol: str, as_of_date: str) -> Tuple[Optional[dict], str]:
    """Latest annual dividends paid, operating cash flow, and capex (for a
    free-cash-flow dividend-coverage check), as of a given date.

    Returns (data, error_string). data shape on success:
        {"dividends_paid": float, "operating_cash_flow": float,
         "capex": float, "free_cash_flow": float, "period_end": "YYYY-MM-DD"}
    Fields are present only for tags that resolved -- a partial result is
    still useful (fcf_payout_ratio just can't be computed without both
    operating_cash_flow and capex).
    """
    from sec_edgar_client import get_cik_for_symbol, _get

    cik_result = get_cik_for_symbol(symbol)
    if cik_result.get("status") != "SUCCESS":
        return None, cik_result.get("message", "Symbol->CIK lookup failed")
    cik = cik_result["cik"]

    facts_result = _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    if facts_result.get("status") != "SUCCESS":
        return None, facts_result.get("message", "XBRL company facts request failed")

    us_gaap = (facts_result.get("data") or {}).get("facts", {}).get("us-gaap", {})
    if not us_gaap:
        return None, "No us-gaap XBRL facts available for this filer"

    out = {}
    period_end = None

    def _note_period_end(pend: Optional[str]) -> None:
        nonlocal period_end
        if pend and (period_end is None or pend > period_end):
            period_end = pend

    # Dividends: try every candidate tag, keep whichever has the most
    # recent period (same reasoning as fetch_annual_dividend_series above).
    best_div, best_div_period = None, None
    for tag in _DIVIDENDS_PAID_TAGS:
        entries = (us_gaap.get(tag, {}).get("units", {}) or {}).get("USD", [])
        annual = _annual_entries(entries, as_of_date)
        if annual and (best_div_period is None or annual[0]["end"] > best_div_period):
            best_div, best_div_period = annual[0], annual[0]["end"]
    if best_div:
        out["dividends_paid"] = abs(best_div["val"])
        _note_period_end(best_div["end"])

    for key, tag, take_abs in (
        ("operating_cash_flow", _OCF_TAG, False),
        ("capex", _CAPEX_TAG, True),
    ):
        entries = (us_gaap.get(tag, {}).get("units", {}) or {}).get("USD", [])
        annual = _annual_entries(entries, as_of_date)
        if annual:
            val = annual[0]["val"]
            out[key] = abs(val) if take_abs else val
            _note_period_end(annual[0]["end"])

    if "operating_cash_flow" in out and "capex" in out:
        out["free_cash_flow"] = out["operating_cash_flow"] - out["capex"]

    if not out:
        return None, "No usable annual cash-flow facts found on/before as_of_date"
    if period_end:
        out["period_end"] = period_end
    return out, ""


def _latest_instant_value(fact_entries: list, as_of_date: str) -> Optional[float]:
    """Balance-sheet ('instant') XBRL facts carry only an 'end' date, no
    'start'/span -- unlike the duration facts (revenue, net income, EPS)
    _annual_entries handles. Returns the value with the latest 'end' among
    entries filed on/before as_of_date, or None."""
    as_of = as_of_date[:10]
    candidates = [e for e in fact_entries if e.get("filed") and e["filed"] <= as_of and e.get("end")]
    if not candidates:
        return None
    candidates.sort(key=lambda e: e["end"], reverse=True)
    return candidates[0]["val"]


def fetch_key_financials(symbol: str, as_of_date: str) -> Tuple[Optional[dict], str]:
    """Fetch the latest annual revenue/net income/EPS (diluted), diluted
    shares outstanding, and stockholders' equity for a symbol, as of a
    given date -- the inputs needed for P/E, P/B, P/S alongside the
    prediction's own origin_price (this function has no price input, so it
    returns raw fundamentals; compute_valuation_ratios below does the
    division).

    Returns (data, error_string). data shape on success (fields present
    only for tags that resolved -- a partial result is still useful):
        {"revenue": float, "revenue_yoy_pct": float,
         "net_income": float, "net_income_yoy_pct": float,
         "eps_diluted": float, "diluted_shares_outstanding": float,
         "stockholders_equity": float, "period_end": "YYYY-MM-DD"}
    """
    from sec_edgar_client import get_cik_for_symbol, _get

    cik_result = get_cik_for_symbol(symbol)
    if cik_result.get("status") != "SUCCESS":
        return None, cik_result.get("message", "Symbol->CIK lookup failed")
    cik = cik_result["cik"]

    facts_result = _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    if facts_result.get("status") != "SUCCESS":
        return None, facts_result.get("message", "XBRL company facts request failed")

    us_gaap = (facts_result.get("data") or {}).get("facts", {}).get("us-gaap", {})
    if not us_gaap:
        return None, "No us-gaap XBRL facts available for this filer"

    out = {}
    period_end = None  # tracks the MOST RECENT period_end seen across all metrics

    def _note_period_end(pend: Optional[str]) -> None:
        nonlocal period_end
        if pend and (period_end is None or pend > period_end):
            period_end = pend

    # Revenue is reported under different tag names across different
    # filers/eras (e.g. AAPL reported "Revenues" only through FY2018, then
    # switched to "RevenueFromContractWithCustomerExcludingAssessedTax"
    # after adopting ASC 606) -- picking the FIRST tag with any data at all
    # would silently return years-stale figures if that tag was retired.
    # Try every candidate and keep whichever gives the most recent period.
    best_revenue = None  # (period_end, latest, prior)
    for tag in _REVENUE_TAGS:
        entries = (us_gaap.get(tag, {}).get("units", {}) or {}).get("USD", [])
        latest, prior, pend = _latest_and_prior_year(entries, as_of_date)
        if latest is not None and pend and (best_revenue is None or pend > best_revenue[0]):
            best_revenue = (pend, latest, prior)
    if best_revenue:
        pend, latest, prior = best_revenue
        out["revenue"] = latest
        if prior:
            out["revenue_yoy_pct"] = round((latest - prior) / abs(prior) * 100, 2)
        _note_period_end(pend)

    ni_entries = (us_gaap.get(_NET_INCOME_TAG, {}).get("units", {}) or {}).get("USD", [])
    latest, prior, pend = _latest_and_prior_year(ni_entries, as_of_date)
    if latest is not None:
        out["net_income"] = latest
        if prior:
            out["net_income_yoy_pct"] = round((latest - prior) / abs(prior) * 100, 2)
        _note_period_end(pend)

    eps_entries = (us_gaap.get(_EPS_TAG, {}).get("units", {}) or {}).get("USD/shares", [])
    latest, _prior, pend = _latest_and_prior_year(eps_entries, as_of_date)
    if latest is not None:
        out["eps_diluted"] = latest
        _note_period_end(pend)

    shares_entries = (us_gaap.get(_DILUTED_SHARES_TAG, {}).get("units", {}) or {}).get("shares", [])
    latest, _prior, pend = _latest_and_prior_year(shares_entries, as_of_date)
    if latest is not None:
        out["diluted_shares_outstanding"] = latest
        _note_period_end(pend)

    equity_entries = (us_gaap.get(_EQUITY_TAG, {}).get("units", {}) or {}).get("USD", [])
    equity_val = _latest_instant_value(equity_entries, as_of_date)
    if equity_val is not None:
        out["stockholders_equity"] = equity_val

    if not out:
        return None, "No usable annual revenue/net income/EPS facts found on/before as_of_date"

    if period_end:
        out["period_end"] = period_end
    return out, ""


def compute_valuation_ratios(symbol: str, as_of_date: str, price: float) -> Tuple[Optional[dict], str]:
    """P/E, P/B, P/S for a symbol as of a given date, given the prediction's
    own origin_price (leakage-safe: callers pass the SAME origin_price
    already used for the rest of the feature packet, never a live/current
    quote). Built from fetch_key_financials' raw fundamentals -- no new SEC
    calls beyond what that function already makes.

    Returns (data, error_string). data: {"pe_ratio": float, "pb_ratio":
    float, "ps_ratio": float} -- only keys that could be computed are
    present (e.g. a loss-making company has no meaningful P/E).
    """
    if not price or price <= 0:
        return None, "No valid price provided"

    fin, err = fetch_key_financials(symbol, as_of_date)
    if not fin:
        return None, err or "No fundamentals available"

    out: dict = {}
    eps = fin.get("eps_diluted")
    if eps is not None and eps > 0:
        out["pe_ratio"] = round(price / eps, 4)

    shares = fin.get("diluted_shares_outstanding")
    revenue = fin.get("revenue")
    if shares and shares > 0 and revenue is not None and revenue > 0:
        out["ps_ratio"] = round((price * shares) / revenue, 4)

    equity = fin.get("stockholders_equity")
    if shares and shares > 0 and equity is not None and equity > 0:
        out["pb_ratio"] = round((price * shares) / equity, 4)

    if not out:
        return None, "Fundamentals resolved but none support a valuation ratio (e.g. negative EPS/equity)"
    return out, ""
