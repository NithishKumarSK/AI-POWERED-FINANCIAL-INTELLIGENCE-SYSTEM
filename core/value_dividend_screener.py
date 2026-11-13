"""
value_dividend_screener.py -- dividend stability + revenue/EPS trend +
sustainability composite, ported from claude-trading-skills'
value-dividend-screener skill
(vendor/claude-trading-skills/skills/value-dividend-screener/scripts/screen_dividend_stocks.py,
MIT License, Copyright (c) 2026 TraderMonty).

Sibling to core/dividend_growth_pullback_screener.py (built just before
this one, same session) -- reuses its calculate_rsi() and
analyze_payout_sustainability() rather than re-porting near-identical
logic a second time. The genuinely distinct pieces ported here are
dividend STABILITY (volatility/years-of-growth across the full available
history, not just a 3-year CAGR) and revenue/EPS TREND direction.

Data sourcing: core/sec_financials_service.py's fetch_annual_dividend_series/
fetch_annual_eps_revenue_series/fetch_cash_flow_coverage/fetch_key_financials
(all built this session), same as the CANSLIM and dividend-growth-pullback
ports -- no FMP/FINVIZ needed. Only the per-symbol ANALYSIS math is
ported; the skill's own FINVIZ/FMP candidate-discovery pipeline was not.

SCOPE REDUCTION, disclosed (same reasoning as dividend_growth_pullback_screener.py):
"Financial Health" (debt-to-equity, 10 pts) was dropped entirely --
"total debt" has no single reliably filer-consistent XBRL tag. "Quality
Score" (ROE + profit margin, 25 pts) keeps only the profit-margin half
(ROE needs StockholdersEquity which this project has, but combining it
correctly with the right debt/equity-adjusted "quality" semantics is the
same risk category as the dropped Financial Health score, so it's left
out too). The composite's point budget is 15 (div CAGR) + 20 (stability)
+ 10 (revenue CAGR) + 10 (EPS CAGR) + 10 (sustainability) + 25 (profit
margin, in place of margin+ROE) = 90 of the original's 100, then rescaled
to 0-100 -- an honest smaller methodology, not a fabricated "Financial
Health"/"ROE" score.
"""
from __future__ import annotations

from typing import Optional

_MAX_RAW_POINTS = 15 + 20 + 10 + 10 + 10 + 25  # = 90, rescaled to 100 below


def analyze_dividend_stability(annual_dividend_series: list) -> dict:
    """annual_dividend_series: most-recent-year-first list of
    {"date", "dividend_per_share"} (from sec_financials_service.fetch_annual_dividend_series).

    Returns {"is_stable", "is_growing", "volatility_pct", "years_of_growth"}."""
    result = {"is_stable": False, "is_growing": False, "volatility_pct": None, "years_of_growth": 0}

    usable = [d for d in annual_dividend_series if d.get("dividend_per_share") is not None]
    if len(usable) < 3:
        return result

    div_values = [d["dividend_per_share"] for d in usable]  # newest first

    avg_div = sum(div_values) / len(div_values)
    if avg_div > 0:
        volatility = (max(div_values) - min(div_values)) / avg_div * 100
        result["volatility_pct"] = round(volatility, 1)
        result["is_stable"] = volatility < 50

    oldest_first = list(reversed(div_values))
    years_of_growth = 0
    for i in range(1, len(oldest_first)):
        if oldest_first[i] >= oldest_first[i - 1] * 0.95:
            years_of_growth += 1
        else:
            years_of_growth = 0
    result["years_of_growth"] = years_of_growth

    if len(oldest_first) >= 3:
        overall_growth = oldest_first[-1] > oldest_first[0]
        result["is_growing"] = years_of_growth >= 2 and overall_growth

    return result


def calculate_stability_score(stability: dict) -> float:
    score = 0.0
    if stability.get("is_stable"):
        score += 40
    elif stability.get("volatility_pct") is not None:
        volatility = stability["volatility_pct"]
        if volatility < 100:
            score += max(0, 40 - volatility * 0.4)

    if stability.get("is_growing"):
        score += 30

    years = stability.get("years_of_growth", 0)
    score += min(years * 10, 30)
    return round(score, 1)


def _trend(values_newest_first: list) -> dict:
    """Shared logic for analyze_revenue_trend/analyze_earnings_trend.
    values_newest_first: up to 4 annual figures, newest first."""
    result = {"is_uptrend": False, "years_of_growth": 0, "cagr": None}
    if len(values_newest_first) < 3:
        return result

    oldest_first = list(reversed(values_newest_first[:4]))
    years_of_growth = sum(1 for i in range(1, len(oldest_first)) if oldest_first[i] > oldest_first[i - 1])
    result["years_of_growth"] = years_of_growth

    if oldest_first[0] > 0 and oldest_first[-1] > 0:
        years = len(oldest_first) - 1
        if years > 0:
            result["cagr"] = round((pow(oldest_first[-1] / oldest_first[0], 1 / years) - 1) * 100, 2)

    overall_growth = oldest_first[-1] > oldest_first[0]
    result["is_uptrend"] = overall_growth and years_of_growth >= 2
    return result


def analyze_revenue_trend(annual_eps_revenue_series: list) -> dict:
    """annual_eps_revenue_series: most-recent-year-first list of
    {"date", "eps", "revenue"} (from sec_financials_service.fetch_annual_eps_revenue_series)."""
    revenues = [e.get("revenue") or 0 for e in annual_eps_revenue_series]
    return _trend(revenues)


def analyze_earnings_trend(annual_eps_revenue_series: list, annual_net_income_series: Optional[list] = None) -> dict:
    """Uses net income when available (closer to the source skill's own
    `netIncome` field), falling back to EPS * a constant share count isn't
    meaningful here, so this falls back to EPS directly when net income
    isn't supplied -- still a valid growth-trend signal, just a different unit."""
    values = annual_net_income_series if annual_net_income_series else [e.get("eps") or 0 for e in annual_eps_revenue_series]
    return _trend(values)


def calculate_profit_margin_score(profit_margin_pct: Optional[float]) -> float:
    """Scope-reduced replacement for the source skill's ROE+margin
    "quality score" -- see module docstring. Scaled to the full 100 (not
    split 50/50 with ROE)."""
    if not profit_margin_pct:
        return 0.0
    return round(min(profit_margin_pct / 15 * 100, 100), 1)


def calculate_composite_score(
    div_cagr: Optional[float], stability_score: float, revenue_cagr: Optional[float],
    eps_cagr: Optional[float], sustainable: bool, profit_margin_score: float,
) -> float:
    raw = 0.0
    raw += min((div_cagr or 0) / 10 * 15, 15)
    raw += stability_score * 0.2
    raw += min((revenue_cagr or 0) / 10 * 10, 10)
    raw += min((eps_cagr or 0) / 15 * 10, 10)
    raw += 10 if sustainable else 0
    raw += profit_margin_score * 0.25
    return round(min(raw / _MAX_RAW_POINTS * 100, 100), 1)
