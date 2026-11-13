"""
Live orchestrator for core/institutional_flow_tracker.py -- reads the
same local cache core/institutional_holdings_service.py's
fetch_institutional_holders() reads (built by build_cache(), which this
session extended to also store each filer's PRIOR-quarter 13F), and
diffs current vs. prior value per filer for one symbol.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from institutional_flow_tracker import classify_filer_flow, compute_flow_score
from institutional_holdings_service import _load_cache, _name_matches


def fetch_institutional_flow(symbol: str, as_of_date: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Returns (data, error_string). LEAKAGE SAFETY: a filer's "current" or
    "prior" 13F is only used if its OWN filing date is on/before as_of_date --
    same discipline as fetch_institutional_holders()."""
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

    filer_flows = []
    for cik, filer in cache.get("filers", {}).items():
        if not filer.get("filed") or filer["filed"] > as_of_date[:10]:
            continue  # LEAKAGE SAFETY -- "current" filing not yet filed as of as_of_date

        current_rows = [r for r in filer.get("rows", []) if _name_matches(r["issuer"], company_name)]
        current_value = sum(r["value"] for r in current_rows)

        prior = filer.get("prior")
        prior_value = None
        if prior and prior.get("filed") and prior["filed"] <= as_of_date[:10]:
            prior_rows = [r for r in prior.get("rows", []) if _name_matches(r["issuer"], company_name)]
            prior_value = sum(r["value"] for r in prior_rows)

        if current_value <= 0 and (prior_value is None or prior_value <= 0):
            continue  # no position in either period we can see -- not a signal, not an entry

        flow = classify_filer_flow(current_value, prior_value)
        filer_flows.append({
            "name": filer["name"], "current_value": current_value, "prior_value": prior_value,
            "flow": flow, "filed": filer["filed"],
        })

    summary = compute_flow_score(filer_flows)
    return {"symbol": symbol, "filer_flows": filer_flows, **summary}, ""
