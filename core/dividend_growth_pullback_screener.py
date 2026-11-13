"""
dividend_growth_pullback_screener.py -- dividend growth quality + RSI
pullback-timing analysis, ported from claude-trading-skills'
dividend-growth-pullback-screener skill
(vendor/claude-trading-skills/skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py,
MIT License, Copyright (c) 2026 TraderMonty).

Only the per-symbol ANALYSIS math is ported -- the skill's own FINVIZ/FMP
candidate-DISCOVERY pipeline (screen_stocks(), the two-stage FINVIZ+FMP
universe scan) was not, same reasoning as every other universe-scan skill
this session. core/dividend_growth_pullback_screener_service.py (the live
orchestrator) already knows which symbol it's analyzing and sources real
data from core/sec_financials_service.py's new dividend/cash-flow
extraction (built this session specifically for this and canslim-screener)
plus core/historical_price_service.py for RSI.

SCOPE REDUCTION, disclosed: the composite score's "Financial Quality"
component (30 pts: ROE, profit margin, debt-to-equity) and "Valuation"
component (10 pts: P/E, P/B) needed balance-sheet tags (StockholdersEquity,
total debt) this project does not yet have a reliably filer-consistent
free extraction for -- unlike revenue/EPS/dividends, "total debt" has no
single universally-reported XBRL tag (filers mix LongTermDebtNoncurrent,
ShortTermBorrowings, and several others in filer-specific combinations),
and rushing that risked exactly the silently-wrong-numbers failure mode
this project has avoided all session. Profit margin (net_income/revenue)
IS kept, since both inputs are already reliably sourced; ROE, debt-to-
equity, P/E, and P/B are left out and the composite re-weights across
Dividend Growth (45%), Profit Margin (15%), and RSI Timing (40%) instead
of the original's 40/30/20/10 split -- a smaller, honest methodology
rather than a fabricated "Financial Quality"/"Valuation" score.

REIT-specific FFO-based payout accounting (the source skill's `is_reit`
branch) was also not ported -- this project has no free REIT/industry
classification source; all symbols use the standard net-income-based
payout ratio.
"""
from __future__ import annotations

from typing import Optional


def calculate_rsi(prices: list, period: int = 14) -> Optional[float]:
    """Standard Wilder's RSI. prices: chronological (oldest first)."""
    if len(prices) < period + 1:
        return None

    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [c if c > 0 else 0 for c in changes]
    losses = [-c if c < 0 else 0 for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calculate_cagr(start_value: float, end_value: float, years: int) -> Optional[float]:
    if start_value <= 0 or end_value <= 0 or years <= 0:
        return None
    return round(((end_value / start_value) ** (1 / years) - 1) * 100, 2)


def analyze_dividend_growth(dividend_series: list) -> dict:
    """dividend_series: most-recent-year-first list of
    {"date", "dividend_per_share"} (>=4 years, from
    sec_financials_service.fetch_annual_dividend_series).

    Returns {"cagr_3yr", "consistent", "latest_annual_dividend", "years_of_growth"}."""
    usable = [d for d in dividend_series if d.get("dividend_per_share") is not None]
    if len(usable) < 4:
        return {"cagr_3yr": None, "consistent": False, "latest_annual_dividend": None, "years_of_growth": 0}

    chrono = list(reversed(usable[:4]))  # oldest first, most-recent 4 years
    values = [d["dividend_per_share"] for d in chrono]

    cagr = calculate_cagr(values[0], values[-1], 3)
    consistent = all(values[i] >= values[i - 1] * 0.95 for i in range(1, len(values)))

    years_of_growth = 0
    all_chrono = list(reversed(usable))
    all_values = [d["dividend_per_share"] for d in all_chrono]
    for i in range(len(all_values) - 1, 0, -1):
        if all_values[i] >= all_values[i - 1] * 0.95:
            years_of_growth += 1
        else:
            break

    return {"cagr_3yr": cagr, "consistent": consistent, "latest_annual_dividend": values[-1], "years_of_growth": years_of_growth}


def analyze_payout_sustainability(cash_flow_coverage: dict, net_income: Optional[float]) -> dict:
    """cash_flow_coverage: from sec_financials_service.fetch_cash_flow_coverage.
    net_income: latest annual net income, from sec_financials_service.fetch_key_financials."""
    result = {
        "payout_ratio": None, "fcf_payout_ratio": None, "fcf_amount": cash_flow_coverage.get("free_cash_flow"),
        "fcf_coverage_status": "MISSING_DATA", "sustainable": False,
        "sustainability_note": "Required cash-flow data is unavailable; sustainability cannot be confirmed.",
    }

    dividends_paid = cash_flow_coverage.get("dividends_paid")
    if dividends_paid is None:
        result["sustainability_note"] = "Dividend payment data is unavailable; sustainability cannot be confirmed."
        return result
    if dividends_paid == 0:
        result["fcf_coverage_status"] = "NO_DIVIDEND"
        result["sustainability_note"] = "No dividend payment was reported; no sustainability bonus is awarded."
        return result

    fcf = result["fcf_amount"]
    if fcf is not None:
        if fcf < 0:
            result["fcf_coverage_status"] = "NEGATIVE_FCF"
        elif fcf == 0:
            result["fcf_coverage_status"] = "ZERO_FCF"
        elif fcf < dividends_paid:
            result["fcf_coverage_status"] = "INSUFFICIENT_FCF"
        elif fcf == dividends_paid:
            result["fcf_coverage_status"] = "AT_LIMIT"
        else:
            result["fcf_coverage_status"] = "COVERED"
        if fcf > 0:
            result["fcf_payout_ratio"] = dividends_paid / fcf * 100

    if net_income is not None and net_income > 0:
        result["payout_ratio"] = dividends_paid / net_income * 100

    result["sustainable"] = (
        result["payout_ratio"] is not None and result["payout_ratio"] < 80
        and result["fcf_coverage_status"] == "COVERED" and result["fcf_payout_ratio"] is not None and result["fcf_payout_ratio"] < 100
    )

    if result["fcf_coverage_status"] == "NEGATIVE_FCF":
        result["sustainability_note"] = "Observed negative free cash flow does not cover dividends; a future cut is not certain."
    elif result["fcf_coverage_status"] == "ZERO_FCF":
        result["sustainability_note"] = "Observed zero free cash flow does not cover dividends; a future cut is not certain."
    elif result["fcf_coverage_status"] == "INSUFFICIENT_FCF":
        result["sustainability_note"] = "Observed free cash flow is below dividends; a future cut is not certain."
    elif result["fcf_coverage_status"] == "AT_LIMIT":
        result["sustainability_note"] = "Free cash flow exactly equals dividends, leaving no coverage buffer."
    elif result["payout_ratio"] is None:
        result["sustainability_note"] = "Earnings payout cannot be assessed from available data."
    elif result["payout_ratio"] >= 80:
        result["sustainability_note"] = "Earnings payout does not meet the under-80% threshold."
    else:
        result["sustainability_note"] = "Earnings payout is below 80% and free cash flow covers dividends with a buffer."

    return result


def calculate_composite_score(div_cagr: Optional[float], div_consistent: bool, profit_margin: Optional[float], rsi: Optional[float]) -> float:
    """Re-weighted scope-reduced composite (see module docstring): Dividend
    Growth 45%, Profit Margin 15%, RSI Timing 40%."""
    score = 0.0

    cagr = div_cagr if div_cagr is not None else 0.0
    if cagr >= 20:
        score += 40
    elif cagr >= 15:
        score += 35
    elif cagr >= 12:
        score += 30
    else:
        score += 20
    if div_consistent:
        score += 5

    margin = profit_margin if profit_margin is not None else 0.0
    if margin >= 20:
        score += 15
    elif margin >= 15:
        score += 12
    elif margin >= 10:
        score += 9
    else:
        score += 4

    rsi_val = rsi if rsi is not None else 50.0
    if rsi_val <= 25:
        score += 40
    elif rsi_val <= 30:
        score += 36
    elif rsi_val <= 35:
        score += 30
    elif rsi_val <= 40:
        score += 24
    else:
        score += 10

    return round(min(score, 100), 1)
