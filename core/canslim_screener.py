"""
canslim_screener.py -- William O'Neil's CANSLIM methodology (7 components:
Current earnings, Annual growth, Newness, Supply/demand, Leadership,
Institutional sponsorship, Market direction), ported from
claude-trading-skills' canslim-screener skill
(vendor/claude-trading-skills/skills/canslim-screener/scripts/
{screen_canslim.py,scorer.py,calculators/*.py}, MIT License,
Copyright (c) 2026 TraderMonty).

Data sourcing, all real, none fabricated:
  C, A  -- quarterly/annual EPS + revenue from SEC XBRL (new this session:
           core/sec_financials_service.fetch_quarterly_eps_revenue_series/
           fetch_annual_eps_revenue_series), not FMP's income-statement
           endpoint the source skill uses.
  N, S  -- this project's own historical_price_service.py (price/volume).
  L     -- REUSES core/vcp_screener.calculate_relative_strength instead of
           porting canslim-screener's own 654-line leadership_calculator.py:
           both are Minervini-style multi-period-weighted RS vs a benchmark
           with near-identical score bands (this one's periods are 3/6/9/12mo
           at 40/20/20/20%; canslim's own is 3/6/12mo at 40/30/30%) -- a
           disclosed, deliberate substitution of one already-built, tested
           equivalent for a near-duplicate, not a different methodology.
  I     -- core/institutional_holdings_service.py (23 well-known 13F filers,
           already built this session) as an honest PROXY for "institutional
           sponsorship": num_holders is capped at len(well_known_filers), not
           a true full-market holder count, and ownership_pct is always None
           (no free shares-outstanding source) -- this scores conservatively
           low rather than fabricating a number; see
           core/canslim_screener_service.py's docstring.
  M     -- SPY (S&P 500 proxy) + VIX, both already resolvable via
           historical_price_service.py (confirmed live earlier this session).

Only Phase 3 (the full 7-component methodology, O'Neil's original weights)
is ported -- Phase 1/Phase 2 (partial-component MVP variants) were not,
since Phase 3 is strictly more complete and this project has real data for
every component.
"""
from __future__ import annotations

from typing import Optional

# ── earnings_calculator.py (C) ────────────────────────────────────────────

def score_current_earnings(eps_growth: float, revenue_growth: float) -> int:
    if eps_growth >= 50 and revenue_growth >= 25:
        return 100
    if eps_growth >= 30 and revenue_growth >= 15:
        return 80
    if eps_growth >= 18 and revenue_growth >= 10:
        return 60
    if eps_growth >= 10:
        return 40
    return 0


def interpret_earnings_score(score: int, eps_growth: float, revenue_growth: float) -> str:
    if score >= 90:
        return f"Exceptional - Explosive earnings acceleration (EPS +{eps_growth:.1f}%, Revenue +{revenue_growth:.1f}%)"
    elif score >= 70:
        return f"Strong - Well above CANSLIM threshold (EPS +{eps_growth:.1f}%, Revenue +{revenue_growth:.1f}%)"
    elif score >= 50:
        return f"Acceptable - Meets CANSLIM minimum 18% threshold (EPS +{eps_growth:.1f}%, Revenue +{revenue_growth:.1f}%)"
    elif score >= 30:
        return f"Below threshold - Insufficient growth (EPS +{eps_growth:.1f}%, Revenue +{revenue_growth:.1f}%)"
    return f"Weak - Does not meet CANSLIM criteria (EPS {eps_growth:+.1f}%, Revenue {revenue_growth:+.1f}%)"


def calculate_quarterly_growth(income_statements: list) -> dict:
    """income_statements: most-recent-quarter-first, need 5+ (idx0 vs idx4 = YoY)."""
    if not income_statements or len(income_statements) < 5:
        return {"score": 0, "error": "Insufficient quarterly data (need at least 5 quarters for YoY comparison)",
                "latest_qtr_eps_growth": None, "latest_qtr_revenue_growth": None, "latest_eps": None,
                "year_ago_eps": None, "latest_revenue": None, "year_ago_revenue": None, "interpretation": "Data unavailable"}

    latest, year_ago = income_statements[0], income_statements[4]
    latest_eps = latest.get("eps") or latest.get("epsdiluted") or latest.get("netIncomePerShare")
    year_ago_eps = year_ago.get("eps") or year_ago.get("epsdiluted") or year_ago.get("netIncomePerShare")
    latest_revenue, year_ago_revenue = latest.get("revenue"), year_ago.get("revenue")

    if latest_eps is None or year_ago_eps is None:
        return {"score": 0, "error": "EPS data missing or invalid", "latest_qtr_eps_growth": None,
                "latest_qtr_revenue_growth": None, "latest_eps": latest_eps, "year_ago_eps": year_ago_eps,
                "latest_revenue": latest_revenue, "year_ago_revenue": year_ago_revenue, "interpretation": "EPS data unavailable"}

    if latest_revenue is None or year_ago_revenue is None or year_ago_revenue == 0:
        return {"score": 0, "error": "Revenue data missing or invalid", "latest_qtr_eps_growth": None,
                "latest_qtr_revenue_growth": None, "latest_eps": latest_eps, "year_ago_eps": year_ago_eps,
                "latest_revenue": latest_revenue, "year_ago_revenue": year_ago_revenue, "interpretation": "Revenue data unavailable"}

    if year_ago_eps == 0:
        eps_growth = 999.9 if (latest_eps > 0 and year_ago_eps <= 0) else 0
    else:
        eps_growth = (latest_eps - year_ago_eps) / abs(year_ago_eps) * 100
    revenue_growth = (latest_revenue - year_ago_revenue) / year_ago_revenue * 100

    score = score_current_earnings(eps_growth, revenue_growth)
    interpretation = interpret_earnings_score(score, eps_growth, revenue_growth)

    quality_warning = None
    if revenue_growth < (eps_growth * 0.5) and eps_growth > 20:
        quality_warning = "Revenue growth significantly lags EPS growth - investigate earnings quality (potential buyback-driven)"

    return {
        "score": score, "latest_qtr_eps_growth": round(eps_growth, 1), "latest_qtr_revenue_growth": round(revenue_growth, 1),
        "latest_eps": latest_eps, "year_ago_eps": year_ago_eps, "latest_revenue": latest_revenue,
        "year_ago_revenue": year_ago_revenue, "latest_qtr_date": latest.get("date"), "year_ago_qtr_date": year_ago.get("date"),
        "interpretation": interpretation, "quality_warning": quality_warning, "error": None,
    }


# ── growth_calculator.py (A) ──────────────────────────────────────────────

def score_annual_growth(eps_cagr: float, revenue_cagr: float, stable: bool) -> int:
    if eps_cagr >= 40:
        base_score = 90
    elif eps_cagr >= 30:
        base_score = 70
    elif eps_cagr >= 25:
        base_score = 50
    elif eps_cagr >= 15:
        base_score = 30
    else:
        base_score = 0
    if revenue_cagr < (eps_cagr * 0.5):
        base_score = int(base_score * 0.8)
    if stable:
        base_score += 10
    return min(base_score, 100)


def interpret_growth_score(score: int, eps_cagr: float, stable: bool) -> str:
    stability_text = "stable" if stable else "erratic"
    if score >= 90:
        return f"Exceptional - {eps_cagr:.1f}% CAGR, {stability_text} growth trajectory"
    elif score >= 70:
        return f"Strong - {eps_cagr:.1f}% CAGR, well above CANSLIM 25% threshold ({stability_text})"
    elif score >= 50:
        return f"Acceptable - {eps_cagr:.1f}% CAGR meets CANSLIM minimum ({stability_text})"
    elif score >= 30:
        return f"Below threshold - {eps_cagr:.1f}% CAGR insufficient (<25% required)"
    return f"Weak - {eps_cagr:.1f}% CAGR does not meet CANSLIM criteria"


def calculate_annual_growth(income_statements: list) -> dict:
    """income_statements: most-recent-year-first, need 4+ years for 3-year CAGR."""
    if not income_statements or len(income_statements) < 4:
        return {"score": 50, "error": "Insufficient annual data (need at least 4 years for 3-year CAGR)",
                "eps_cagr_3yr": None, "revenue_cagr_3yr": None, "stability": "unknown", "eps_values": None, "interpretation": "Data unavailable"}

    eps_values, revenue_values = [], []
    for i in range(4):
        stmt = income_statements[i]
        eps = stmt.get("eps") or stmt.get("epsdiluted")
        revenue = stmt.get("revenue")
        if eps is None:
            return {"score": 0, "error": f"Missing EPS data for year {stmt.get('date', 'unknown')}", "eps_cagr_3yr": None,
                    "revenue_cagr_3yr": None, "stability": "unknown", "eps_values": None, "interpretation": "EPS data incomplete"}
        if eps <= 0:
            return {"score": 0, "error": f"Negative or zero EPS in year {stmt.get('date', 'unknown')} - cannot calculate CAGR",
                    "eps_cagr_3yr": None, "revenue_cagr_3yr": None, "stability": "unknown", "eps_values": None,
                    "interpretation": "Negative EPS - not a CANSLIM candidate"}
        eps_values.append(eps)
        revenue_values.append(revenue if revenue else 0)

    eps_values_chrono = eps_values[::-1]
    revenue_values_chrono = revenue_values[::-1]

    eps_start, eps_end = eps_values_chrono[0], eps_values_chrono[3]
    eps_cagr = ((eps_end / eps_start) ** (1 / 3) - 1) * 100

    revenue_start, revenue_end = revenue_values_chrono[0], revenue_values_chrono[3]
    revenue_cagr = ((revenue_end / revenue_start) ** (1 / 3) - 1) * 100 if revenue_start > 0 else 0

    stable = all(eps_values_chrono[i] >= eps_values_chrono[i - 1] for i in range(1, len(eps_values_chrono)))
    score = score_annual_growth(eps_cagr, revenue_cagr, stable)
    interpretation = interpret_growth_score(score, eps_cagr, stable)

    quality_warning = None
    if revenue_cagr < (eps_cagr * 0.5) and eps_cagr > 20:
        quality_warning = "Revenue CAGR significantly lags EPS CAGR - growth may be buyback-driven rather than organic"

    return {
        "score": score, "eps_cagr_3yr": round(eps_cagr, 1), "revenue_cagr_3yr": round(revenue_cagr, 1),
        "stability": "stable" if stable else "erratic", "eps_values": [round(e, 2) for e in eps_values_chrono],
        "revenue_values": [int(r) for r in revenue_values_chrono], "years_analyzed": len(eps_values_chrono),
        "interpretation": interpretation, "quality_warning": quality_warning, "error": None,
    }


# ── new_highs_calculator.py (N) ───────────────────────────────────────────

def score_newness(distance_from_high_pct: float, breakout_detected: bool) -> int:
    if distance_from_high_pct >= -5 and breakout_detected:
        return 100
    elif distance_from_high_pct >= -10 and breakout_detected:
        return 80
    elif distance_from_high_pct >= -15 or breakout_detected:
        return 60
    elif distance_from_high_pct >= -25:
        return 40
    return 20


def interpret_newness_score(score: int, distance: float, breakout: bool) -> str:
    breakout_text = " with volume breakout" if breakout else ""
    if score >= 90:
        return f"Exceptional - At new highs{breakout_text} ({distance:+.1f}% from high)"
    elif score >= 70:
        return f"Strong - Near 52-week high{breakout_text} ({distance:+.1f}% from high)"
    elif score >= 50:
        return f"Acceptable - Within 15% of high ({distance:+.1f}% from high)"
    elif score >= 30:
        return f"Weak - Lacks momentum ({distance:+.1f}% from high)"
    return f"Poor - Too far from highs, overhead resistance ({distance:+.1f}% from high)"


def calculate_newness(quote: dict) -> dict:
    if not quote:
        return {"score": 0, "error": "Quote data missing", "distance_from_high_pct": None, "interpretation": "Data unavailable"}

    current_price, week_52_high, week_52_low = quote.get("price"), quote.get("yearHigh"), quote.get("yearLow")
    current_volume, avg_volume = quote.get("volume"), quote.get("avgVolume")

    if not current_price or not week_52_high:
        return {"score": 0, "error": "Price or 52-week high data missing", "distance_from_high_pct": None, "interpretation": "Data unavailable"}

    distance_from_high_pct = (current_price / week_52_high - 1) * 100
    breakout_detected = bool(current_volume and avg_volume and current_price >= week_52_high * 0.995 and current_volume > avg_volume * 1.4)

    score = score_newness(distance_from_high_pct, breakout_detected)
    interpretation = interpret_newness_score(score, distance_from_high_pct, breakout_detected)

    return {
        "score": score, "distance_from_high_pct": round(distance_from_high_pct, 1), "current_price": current_price,
        "week_52_high": week_52_high, "week_52_low": week_52_low, "breakout_detected": breakout_detected,
        "current_volume": current_volume, "avg_volume": avg_volume,
        "volume_ratio": round(current_volume / avg_volume, 2) if avg_volume else None,
        "interpretation": interpretation, "error": None,
    }


# ── supply_demand_calculator.py (S) ───────────────────────────────────────

def score_supply_demand(ratio: float) -> int:
    if ratio >= 2.0:
        return 100
    elif ratio >= 1.5:
        return 80
    elif ratio >= 1.0:
        return 60
    elif ratio >= 0.7:
        return 40
    elif ratio >= 0.5:
        return 20
    return 0


def interpret_supply_demand(ratio: float, accumulation: bool) -> str:
    if ratio >= 2.0:
        return f"Strong Accumulation (ratio: {ratio:.2f}x) - Institutions aggressively buying. Volume precedes price."
    elif ratio >= 1.5:
        return f"Accumulation (ratio: {ratio:.2f}x) - Bullish volume pattern. Institutional interest building."
    elif ratio >= 1.0:
        return f"Neutral/Weak Accumulation (ratio: {ratio:.2f}x) - Slightly positive volume trend."
    elif ratio >= 0.7:
        return f"Neutral/Weak Distribution (ratio: {ratio:.2f}x) - Slightly negative volume trend. Monitor closely."
    elif ratio >= 0.5:
        return f"Distribution (ratio: {ratio:.2f}x) - Bearish volume pattern. Institutions may be selling."
    return f"Strong Distribution (ratio: {ratio:.2f}x) - Heavy selling pressure. Volume leads price lower."


def calculate_supply_demand(historical_prices: dict) -> dict:
    """historical_prices: {"historical": [most-recent-first daily bars]}."""
    if not historical_prices or "historical" not in historical_prices:
        return {"score": 0, "error": "No historical price data provided", "up_down_ratio": None, "accumulation_detected": False,
                "avg_up_volume": None, "avg_down_volume": None, "up_days_count": 0, "down_days_count": 0, "interpretation": "Data unavailable"}

    prices = historical_prices["historical"]
    if not prices or len(prices) < 60:
        return {"score": 0, "error": f"Insufficient data (need 60+ days, got {len(prices)})", "up_down_ratio": None,
                "accumulation_detected": False, "avg_up_volume": None, "avg_down_volume": None, "up_days_count": 0,
                "down_days_count": 0, "interpretation": "Data unavailable", "quality_warning": "Less than 60 days of historical data available"}

    analysis_period = prices[:60]
    up_days, down_days = [], []
    previous_close = None
    for day in reversed(analysis_period):
        current_close, current_volume = day.get("close"), day.get("volume")
        if current_close is None or current_volume is None:
            continue
        if previous_close is not None:
            if current_close > previous_close:
                up_days.append(current_volume)
            elif current_close < previous_close:
                down_days.append(current_volume)
        previous_close = current_close

    if len(up_days) < 10 or len(down_days) < 10:
        return {"score": 0, "error": "Insufficient up/down days for analysis", "up_down_ratio": None, "accumulation_detected": False,
                "avg_up_volume": None, "avg_down_volume": None, "up_days_count": len(up_days), "down_days_count": len(down_days),
                "interpretation": "Data quality issues", "quality_warning": f"Too few classified days (up: {len(up_days)}, down: {len(down_days)})"}

    avg_up_volume, avg_down_volume = sum(up_days) / len(up_days), sum(down_days) / len(down_days)
    ratio = 5.0 if avg_down_volume == 0 else avg_up_volume / avg_down_volume
    accumulation_detected = ratio >= 1.5
    score = score_supply_demand(ratio)
    interpretation = interpret_supply_demand(ratio, accumulation_detected)

    return {
        "score": score, "up_down_ratio": ratio, "accumulation_detected": accumulation_detected,
        "avg_up_volume": int(avg_up_volume), "avg_down_volume": int(avg_down_volume),
        "up_days_count": len(up_days), "down_days_count": len(down_days), "interpretation": interpretation,
    }


# ── institutional_calculator.py (I) -- simplified, no FINVIZ fallback ────

SUPERINVESTORS = [
    "BERKSHIRE HATHAWAY", "BAUPOST GROUP", "PERSHING SQUARE", "GREENLIGHT CAPITAL", "THIRD POINT",
    "APPALOOSA MANAGEMENT", "VIKING GLOBAL", "SCION ASSET MANAGEMENT", "BRIDGEWATER ASSOCIATES", "RENAISSANCE TECHNOLOGIES",
]


def score_institutional_sponsorship(num_holders: int, ownership_pct: Optional[float], superinvestor_present: bool, quality_warning: Optional[str]) -> int:
    if ownership_pct is not None:
        if 50 <= num_holders <= 100 and 30 <= ownership_pct <= 60:
            score = 100
        elif superinvestor_present and num_holders >= 20:
            score = 90
        elif (30 <= num_holders <= 50 and 20 <= ownership_pct <= 40) or (100 <= num_holders <= 150 and 40 <= ownership_pct <= 70):
            score = 80
        elif ownership_pct < 10 or ownership_pct > 90:
            score = 20
        elif ownership_pct < 20 or ownership_pct > 80:
            score = 40
        else:
            score = 60
    else:
        # No ownership_pct available (this project's honest proxy never has
        # one -- see canslim_screener_service.py's docstring): score from
        # holder count alone, superinvestor presence as a bonus signal, and
        # halve the result since this is a meaningfully weaker signal than
        # the full FMP/Finviz-backed version.
        if superinvestor_present and num_holders >= 5:
            score = 70
        elif num_holders >= 10:
            score = 60
        elif num_holders >= 3:
            score = 40
        elif num_holders >= 1:
            score = 20
        else:
            score = 0
        score = int(score * 0.5)
    return max(0, min(100, score))


def interpret_institutional_sponsorship(num_holders: int, ownership_pct: Optional[float], superinvestor_present: bool, superinvestors_found: list) -> str:
    superinvestor_text = f" (incl. {', '.join(superinvestors_found)})" if superinvestors_found else ""
    ownership_text = f"{ownership_pct:.1f}% ownership" if ownership_pct is not None else "ownership % unavailable"
    return f"{num_holders} known institutional holders{superinvestor_text}, {ownership_text}"


def calculate_institutional_sponsorship(num_holders: int, superinvestors_found: list) -> dict:
    """Simplified from the source skill: takes the already-resolved holder
    count + superinvestor list from core/institutional_holdings_service.py
    directly (no FMP holder list to parse, no Finviz fallback, no shares-
    outstanding-derived ownership_pct -- always None here)."""
    superinvestor_present = len(superinvestors_found) > 0
    score = score_institutional_sponsorship(num_holders, None, superinvestor_present, None)
    interpretation = interpret_institutional_sponsorship(num_holders, None, superinvestor_present, superinvestors_found)
    return {
        "score": score, "num_holders": num_holders, "ownership_pct": None, "superinvestor_present": superinvestor_present,
        "superinvestors": superinvestors_found, "interpretation": interpretation,
        "quality_warning": "Proxy signal: holder count limited to 23 well-known 13F filers tracked by this project, not a full-market count; ownership_pct unavailable (no free shares-outstanding source).",
        "data_source": "institutional_holdings_service (13F, 23 well-known filers)",
    }


# ── market_calculator.py (M) ──────────────────────────────────────────────

def calculate_ema(prices: list, period: int = 50) -> float:
    """prices: most-recent-first."""
    if len(prices) < period:
        return sum(prices) / len(prices)
    prices_reversed = prices[::-1]
    sma = sum(prices_reversed[:period]) / period
    ema = sma
    k = 2 / (period + 1)
    for price in prices_reversed[period:]:
        ema = price * k + ema * (1 - k)
    return ema


def score_market_direction(trend: str, vix_level: Optional[float]) -> int:
    if trend == "strong_uptrend":
        base_score = 90
    elif trend == "uptrend":
        base_score = 70
    elif trend == "choppy":
        base_score = 40
    elif trend == "downtrend":
        base_score = 20
    else:
        base_score = 0

    if vix_level:
        if vix_level < 15:
            base_score += 10
        elif vix_level > 30:
            base_score = 0
    return min(max(base_score, 0), 100)


def interpret_market_score(score: int, trend: str, distance: float, vix: Optional[float]) -> str:
    vix_text = f", VIX {vix:.1f}" if vix else ""
    if score >= 90:
        return f"Strong bull market - Aggressive buying recommended (S&P 500 {distance:+.1f}% from 50-EMA{vix_text})"
    elif score >= 70:
        return f"Bull market - Standard position sizing (S&P 500 {distance:+.1f}% from 50-EMA{vix_text})"
    elif score >= 50:
        return f"Early uptrend - Small initial positions (S&P 500 {distance:+.1f}% from 50-EMA{vix_text})"
    elif score >= 30:
        return f"Choppy/neutral - Reduce exposure, be selective (S&P 500 {distance:+.1f}% from 50-EMA{vix_text})"
    elif score >= 10:
        return f"Downtrend forming - Defensive posture (S&P 500 {distance:+.1f}% from 50-EMA{vix_text})"
    return f"Bear market - Raise 80-100% cash, DO NOT BUY (S&P 500 {distance:+.1f}% from 50-EMA{vix_text})"


def calculate_market_direction(sp500_quote: dict, sp500_prices: Optional[list] = None, vix_quote: Optional[dict] = None) -> dict:
    if not sp500_quote:
        return {"score": 50, "error": "S&P 500 quote data missing", "trend": "unknown", "interpretation": "Market data unavailable"}

    sp500_price = sp500_quote.get("price")
    if not sp500_price:
        return {"score": 50, "error": "S&P 500 price missing", "trend": "unknown", "interpretation": "Market data unavailable"}

    sp500_ema_50 = None
    if sp500_prices and len(sp500_prices) >= 50:
        close_prices = [d.get("close") for d in sp500_prices if d.get("close")]
        if len(close_prices) >= 50:
            sp500_ema_50 = calculate_ema(close_prices, period=50)

    if not sp500_ema_50:
        return {"score": 50, "error": "Insufficient S&P 500 history for 50-day EMA", "trend": "unknown",
                "sp500_price": sp500_price, "sp500_ema_50": None, "interpretation": "Market trend unavailable - insufficient historical data"}

    distance_from_ema_pct = (sp500_price / sp500_ema_50 - 1) * 100
    vix_level = vix_quote.get("price") if vix_quote else None

    if distance_from_ema_pct >= 2.0:
        trend = "strong_uptrend"
    elif distance_from_ema_pct >= 0:
        trend = "uptrend"
    elif distance_from_ema_pct >= -2.0:
        trend = "choppy"
    elif distance_from_ema_pct >= -5.0:
        trend = "downtrend"
    else:
        trend = "bear_market"

    score = score_market_direction(trend, vix_level)
    interpretation = interpret_market_score(score, trend, distance_from_ema_pct, vix_level)
    warning = "BEAR MARKET - Do not buy stocks regardless of C, A, N scores. Raise 80-100% cash and wait for market recovery." if score == 0 else None

    return {
        "score": score, "trend": trend, "sp500_price": sp500_price, "sp500_ema_50": sp500_ema_50,
        "distance_from_ema_pct": round(distance_from_ema_pct, 2), "vix_level": vix_level,
        "interpretation": interpretation, "warning": warning, "error": None,
    }


# ── scorer.py (Phase 3: full 7-component weights) ─────────────────────────

WEIGHTS_PHASE3 = {"C": 0.15, "A": 0.20, "N": 0.15, "S": 0.15, "L": 0.20, "I": 0.10, "M": 0.05}


def interpret_composite_score(composite: float) -> dict:
    if composite >= 90:
        return {"rating": "Exceptional+", "description": "Rare multi-bagger setup - all components near-perfect",
                "guidance": "Immediate buy, aggressive position sizing (15-20% of portfolio)"}
    elif composite >= 80:
        return {"rating": "Exceptional", "description": "Outstanding fundamentals + strong momentum",
                "guidance": "Strong buy, standard sizing (10-15% of portfolio)"}
    elif composite >= 70:
        return {"rating": "Strong", "description": "Solid across all components, minor weaknesses",
                "guidance": "Buy, standard sizing (8-12% of portfolio)"}
    elif composite >= 60:
        return {"rating": "Above Average", "description": "Meets thresholds, one component weak",
                "guidance": "Buy on pullback, conservative sizing (5-8% of portfolio)"}
    elif composite >= 50:
        return {"rating": "Average", "description": "Marginal CANSLIM candidate",
                "guidance": "Watchlist only, consider 3-5% if high conviction"}
    elif composite >= 40:
        return {"rating": "Below Average", "description": "Fails one or more key thresholds", "guidance": "Monitor, do not buy"}
    return {"rating": "Weak", "description": "Does not meet CANSLIM criteria", "guidance": "Avoid"}


def calculate_composite_score_phase3(c_score: float, a_score: float, n_score: float, s_score: float, l_score: float, i_score: float, m_score: float) -> dict:
    composite = (c_score * WEIGHTS_PHASE3["C"] + a_score * WEIGHTS_PHASE3["A"] + n_score * WEIGHTS_PHASE3["N"]
                 + s_score * WEIGHTS_PHASE3["S"] + l_score * WEIGHTS_PHASE3["L"] + i_score * WEIGHTS_PHASE3["I"] + m_score * WEIGHTS_PHASE3["M"])

    components = {"C": c_score, "A": a_score, "N": n_score, "S": s_score, "L": l_score, "I": i_score, "M": m_score}
    weakest_component = min(components, key=components.get)
    weakest_score = components[weakest_component]

    rating_info = interpret_composite_score(composite)
    return {
        "composite_score": round(composite, 1), "rating": rating_info["rating"], "rating_description": rating_info["description"],
        "guidance": rating_info["guidance"], "weakest_component": weakest_component, "weakest_score": weakest_score,
        "component_scores": components,
    }


def check_minimum_thresholds_phase3(c_score: float, a_score: float, n_score: float, s_score: float, l_score: float, i_score: float, m_score: float) -> dict:
    thresholds = {"C": 60, "A": 50, "N": 40, "S": 40, "L": 50, "I": 40, "M": 40}
    scores = {"C": c_score, "A": a_score, "N": n_score, "S": s_score, "L": l_score, "I": i_score, "M": m_score}
    failed = [comp for comp, threshold in thresholds.items() if scores[comp] < threshold]

    if m_score == 0:
        return {"passes_all": False, "failed_components": ["M"], "recommendation": "avoid",
                "reason": "Bear market - M component = 0. Do NOT buy regardless of other scores."}

    if l_score < 40:
        if "L" not in failed:
            failed.append("L")
        return {"passes_all": False, "failed_components": failed, "recommendation": "avoid",
                "reason": f"Stock significantly underperforming market (L={l_score}). CANSLIM requires market leaders."}

    if not failed:
        return {"passes_all": True, "failed_components": [], "recommendation": "buy", "reason": "All 7 CANSLIM thresholds met - Full methodology validation"}
    elif len(failed) == 1:
        return {"passes_all": False, "failed_components": failed, "recommendation": "watchlist", "reason": f"One component below threshold: {failed[0]}"}
    return {"passes_all": False, "failed_components": failed, "recommendation": "avoid", "reason": f"Multiple components below threshold: {', '.join(failed)}"}
