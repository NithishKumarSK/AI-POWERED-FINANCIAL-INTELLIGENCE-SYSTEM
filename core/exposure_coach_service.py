"""
Live orchestrator for core/exposure_coach.py -- calls this project's own
market_breadth_service, macro_regime_service, market_top_detector_service,
and ftd_status_service (all already live, cached, and tested) and feeds
their outputs into the exposure synthesis.

Standalone, market-wide (not per-symbol) reporting tool -- not wired into
feature_packet, since it answers "how much capital overall," not a
per-symbol question. A trader-facing caller (e.g. a future UI panel)
would call this once per day/session, same cadence as its upstream
sources' own disk caches.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from exposure_coach import build_exposure_posture


def fetch_exposure_posture(as_of_date: str, use_cache: bool = True) -> Tuple[Dict[str, Any], str]:
    """Build today's (or a historical) Market Posture summary.

    Returns (data, warnings_string). Unlike most *_service.py functions
    here, this ALWAYS returns a usable data dict -- per the source
    skill's own "accepts partial inputs; missing files reduce confidence
    but do not block execution" rule -- so a dead upstream source
    degrades the posture's confidence/inputs_missing rather than failing
    the whole call. warnings_string collects the individual source
    errors for visibility, joined with "; ".
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

    posture = build_exposure_posture(
        breadth_data=breadth_data,
        regime_data=regime_data,
        top_risk_data=top_risk_data,
        ftd_data=ftd_data,
    )
    return posture, "; ".join(warnings)
