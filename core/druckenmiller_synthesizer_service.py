"""
Live orchestrator for core/druckenmiller_synthesizer.py -- reuses the
exact same 4 upstream live sources as exposure_coach_service.py
(market_breadth_service, macro_regime_service, market_top_detector_service,
ftd_status_service), so the two synthesizers can run side-by-side off one
set of upstream fetches without duplicating fetch logic.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from druckenmiller_synthesizer import build_druckenmiller_synthesis


def fetch_druckenmiller_synthesis(as_of_date: str, use_cache: bool = True) -> Tuple[Dict[str, Any], str]:
    """Build today's (or a historical) Druckenmiller conviction synthesis.

    Returns (data, warnings_string). Always returns a usable data dict,
    same "accepts partial inputs" contract as exposure_coach_service.py.
    """
    warnings = []

    breadth_data = None
    try:
        from market_breadth_service import fetch_market_breadth_snapshot
        breadth_data, breadth_err = fetch_market_breadth_snapshot(as_of_date)
        if breadth_err:
            warnings.append(f"breadth: {breadth_err}")
    except Exception as exc:
        warnings.append(f"breadth: {type(exc).__name__}: {exc}")

    regime_data = None
    try:
        from macro_regime_service import compute_macro_regime
        regime_data, regime_err = compute_macro_regime(as_of_date, use_cache=use_cache)
        if regime_err:
            warnings.append(f"regime: {regime_err}")
    except Exception as exc:
        warnings.append(f"regime: {type(exc).__name__}: {exc}")

    top_risk_data = None
    try:
        from market_top_detector_service import compute_market_top_risk
        top_risk_data, top_risk_err = compute_market_top_risk(as_of_date, use_cache=use_cache)
        if top_risk_err:
            warnings.append(f"top_risk: {top_risk_err}")
    except Exception as exc:
        warnings.append(f"top_risk: {type(exc).__name__}: {exc}")

    ftd_data = None
    try:
        from ftd_status_service import compute_ftd_status
        ftd_data, ftd_err = compute_ftd_status(as_of_date, use_cache=use_cache)
        if ftd_err:
            warnings.append(f"ftd: {ftd_err}")
    except Exception as exc:
        warnings.append(f"ftd: {type(exc).__name__}: {exc}")

    synthesis = build_druckenmiller_synthesis(
        breadth_data=breadth_data,
        regime_data=regime_data,
        top_risk_data=top_risk_data,
        ftd_data=ftd_data,
    )
    return synthesis, "; ".join(warnings)
