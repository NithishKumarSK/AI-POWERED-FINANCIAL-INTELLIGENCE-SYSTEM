"""
Batch orchestrator for core/breakout_trade_planner.py -- takes a list of
core/vcp_screener.py `analyze_stock()` results (one per candidate symbol,
already fetched by the caller via vcp_screener_service.fetch_vcp_analysis
or equivalent) and produces categorized, portfolio-heat-constrained trade
plans, mirroring the source skill's CLI contract (it reads a VCP screener
JSON file; here the caller passes the equivalent list of dicts directly).

Pure/no I/O, no network -- every input is caller-supplied, so this stays
testable without re-fetching live VCP data the vcp_screener tests already
cover.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from breakout_trade_planner import plan_trade_for_candidate


def plan_breakout_trades(
    vcp_results: List[Dict[str, Any]],
    account_size: float,
    risk_pct: float = 0.5,
    max_position_pct: float = 10.0,
    max_sector_pct: float = 30.0,
    max_portfolio_heat_pct: float = 6.0,
    target_r_multiple: float = 2.0,
    stop_buffer_pct: float = 1.0,
    max_chase_pct: float = 2.0,
    pivot_buffer_pct: float = 0.1,
) -> Dict[str, Any]:
    """Plan trades for every candidate, then apply portfolio heat/sector caps
    sequentially, highest composite_score first -- a deterministic, documented
    sequencing choice (the source skill's own internal sequencing algorithm
    isn't available to read), so the best setups claim the shared risk budget
    first and later ones are CONSTRAINED once a cap is hit.
    """
    plans = [
        plan_trade_for_candidate(
            vcp_result, account_size, risk_pct, max_position_pct,
            max_chase_pct, stop_buffer_pct, pivot_buffer_pct, target_r_multiple,
        )
        for vcp_result in vcp_results
    ]

    actionable_or_revalidation = [p for p in plans if p["category"] in ("ACTIONABLE", "REVALIDATION")]
    actionable_or_revalidation.sort(key=lambda p: p.get("composite_score", 0), reverse=True)
    others = [p for p in plans if p["category"] not in ("ACTIONABLE", "REVALIDATION")]

    cumulative_heat_pct = 0.0
    sector_exposure_pct: Dict[str, float] = {}
    final_plans: List[Dict[str, Any]] = []

    for plan in actionable_or_revalidation:
        risk_pct_worst = plan.get("risk_pct_worst") or 0.0
        position_pct = plan.get("sizing", {}).get("position_pct", 0.0)
        sector = plan.get("sector", "Unknown")
        trade_heat_contribution = position_pct * risk_pct_worst / 100 if position_pct else 0.0

        projected_heat = cumulative_heat_pct + trade_heat_contribution
        projected_sector = sector_exposure_pct.get(sector, 0.0) + position_pct

        if projected_heat > max_portfolio_heat_pct:
            plan = {**plan, "category": "CONSTRAINED",
                    "reasons": [f"Portfolio heat {projected_heat:.2f}% would exceed cap {max_portfolio_heat_pct}%"]}
        elif projected_sector > max_sector_pct:
            plan = {**plan, "category": "CONSTRAINED",
                    "reasons": [f"Sector '{sector}' exposure {projected_sector:.2f}% would exceed cap {max_sector_pct}%"]}
        else:
            cumulative_heat_pct = projected_heat
            sector_exposure_pct[sector] = projected_sector
            plan = {**plan, "portfolio_heat_after_pct": round(cumulative_heat_pct, 2)}

        final_plans.append(plan)

    final_plans.extend(others)

    return {
        "schema_version": "1.0",
        "actionable": [p for p in final_plans if p["category"] == "ACTIONABLE"],
        "revalidation": [p for p in final_plans if p["category"] == "REVALIDATION"],
        "watchlist": [p for p in final_plans if p["category"] == "WATCHLIST"],
        "rejected": [p for p in final_plans if p["category"] == "REJECTED"],
        "constrained": [p for p in final_plans if p["category"] == "CONSTRAINED"],
        "total_portfolio_heat_pct": round(cumulative_heat_pct, 2),
        "sector_exposure_pct": {k: round(v, 2) for k, v in sector_exposure_pct.items()},
    }
