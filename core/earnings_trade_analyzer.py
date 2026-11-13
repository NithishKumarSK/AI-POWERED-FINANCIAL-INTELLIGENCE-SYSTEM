"""
earnings_trade_analyzer.py -- 5-factor post-earnings reaction scoring
(gap size, pre-earnings trend, volume trend, MA200/MA50 position), ported
from claude-trading-skills' earnings-trade-analyzer skill
(vendor/claude-trading-skills/skills/earnings-trade-analyzer/scripts/
{analyze_earnings_trades.py,scorer.py,calculators/*.py}, MIT License,
Copyright (c) 2026 TraderMonty).

Only the single-stock ANALYSIS pipeline (analyze_stock + its 5 calculators
+ scorer) is ported -- the skill's own 4-phase candidate-DISCOVERY
pipeline (FMP earnings calendar -> company-profile batch -> market-cap
filter) was not, same reasoning as pead_screener.py:
core/earnings_trade_analyzer_service.py (the live orchestrator) already
knows which symbol it's scoring and uses
core/free_news_service.fetch_most_recent_earnings_8k() for the earnings
date instead.

SCOPE NOTE carried over from volume_trend_calculator.py's own comment:
this analyzer's volume-trend window assumes the MOST RECENT bars in
daily_prices are close to the earnings date (the skill's own default
--lookback-days is 2-5) -- the service wrapper enforces this by only
running the analysis when earnings happened within ~10 days of as_of_date,
rather than stretching it across pead_screener.py's longer 5-week window.

All price lists are MOST-RECENT-FIRST, same convention as
core/pead_screener.py and core/ibd_distribution_day_monitor.py.

Grade bands (composite, 0-100): A >= 85, B >= 70, C >= 55, D < 55.
"""
from __future__ import annotations

from typing import Optional

COMPONENT_WEIGHTS = {
    "gap_size": 0.25,
    "pre_earnings_trend": 0.30,
    "volume_trend": 0.20,
    "ma200_position": 0.15,
    "ma50_position": 0.10,
}

GRADE_THRESHOLDS = [
    (85, "A", "Strong earnings reaction with institutional accumulation"),
    (70, "B", "Good earnings reaction worth monitoring"),
    (55, "C", "Mixed signals, use caution"),
    (0, "D", "Weak setup, avoid"),
]

GRADE_GUIDANCE = {
    "A": "Consider entry on pullback to gap support or breakout continuation. High conviction setup.",
    "B": "Monitor for follow-through buying. Wait for pullback to key support or volume confirmation.",
    "C": "Additional analysis needed. Consider waiting for clearer price action or catalyst.",
    "D": "Avoid trading. Weak setup with poor risk/reward profile.",
}


def _find_index_by_date(daily_prices: list, target_date: str) -> int:
    for i, bar in enumerate(daily_prices):
        if bar.get("date") == target_date:
            return i
    return -1


# ── gap_size_calculator.py ──────────────────────────────────────────────

def _score_gap(abs_gap_pct: float) -> float:
    if abs_gap_pct >= 10.0:
        return 100.0
    elif abs_gap_pct >= 7.0:
        return 85.0
    elif abs_gap_pct >= 5.0:
        return 70.0
    elif abs_gap_pct >= 3.0:
        return 55.0
    elif abs_gap_pct >= 1.0:
        return 35.0
    return 15.0


def calculate_gap(daily_prices: list, earnings_date: str, timing: str) -> dict:
    """BMO: gap = open[earnings_date]/close[prev_day] - 1.
    AMC/unknown: gap = open[next_day]/close[earnings_date] - 1."""
    earnings_idx = _find_index_by_date(daily_prices, earnings_date)
    if earnings_idx == -1:
        return {"gap_pct": 0.0, "gap_type": "up", "base_price": 0.0, "gap_price": 0.0,
                "timing_used": timing, "score": 0.0, "warning": f"Earnings date {earnings_date} not found in price data"}

    timing_lower = timing.lower() if timing else "unknown"
    if timing_lower == "bmo":
        prev_idx = earnings_idx + 1
        if prev_idx >= len(daily_prices):
            return {"gap_pct": 0.0, "gap_type": "up", "base_price": 0.0, "gap_price": 0.0,
                    "timing_used": timing_lower, "score": 0.0, "warning": "No previous trading day available for BMO gap calculation"}
        base_price = daily_prices[prev_idx]["close"]
        gap_price = daily_prices[earnings_idx]["open"]
    else:
        next_idx = earnings_idx - 1
        if next_idx < 0:
            return {"gap_pct": 0.0, "gap_type": "up", "base_price": 0.0, "gap_price": 0.0,
                    "timing_used": timing_lower, "score": 0.0, "warning": "No next trading day available for AMC gap calculation"}
        base_price = daily_prices[earnings_idx]["close"]
        gap_price = daily_prices[next_idx]["open"]

    if base_price == 0:
        return {"gap_pct": 0.0, "gap_type": "up", "base_price": base_price, "gap_price": gap_price,
                "timing_used": timing_lower, "score": 0.0, "warning": "Base price is zero, cannot calculate gap"}

    gap_pct = (gap_price / base_price - 1.0) * 100.0
    score = _score_gap(abs(gap_pct))
    result = {
        "gap_pct": round(gap_pct, 2), "gap_type": "up" if gap_pct >= 0 else "down",
        "base_price": round(base_price, 2), "gap_price": round(gap_price, 2),
        "timing_used": timing_lower, "score": score,
    }
    if timing_lower == "unknown":
        result["timing_note"] = "timing unknown; AMC window assumed (BMO reporters may be measured on the wrong session pair)"
    return result


# ── pre_earnings_trend_calculator.py ──────────────────────────────────────

def _score_trend(return_pct: float) -> float:
    if return_pct >= 15.0:
        return 100.0
    elif return_pct >= 10.0:
        return 85.0
    elif return_pct >= 5.0:
        return 70.0
    elif return_pct >= 0.0:
        return 50.0
    elif return_pct >= -5.0:
        return 30.0
    return 15.0


def calculate_pre_earnings_trend(daily_prices: list, earnings_date: str) -> dict:
    """20-trading-day return ending at the earnings date."""
    earnings_idx = _find_index_by_date(daily_prices, earnings_date)
    if earnings_idx == -1:
        return {"return_20d_pct": 0.0, "trend_direction": "up", "score": 0.0, "warning": f"Earnings date {earnings_date} not found in price data"}

    lookback_idx = earnings_idx + 20
    if lookback_idx >= len(daily_prices):
        return {"return_20d_pct": 0.0, "trend_direction": "up", "score": 0.0, "warning": "Insufficient data for 20-day pre-earnings trend calculation"}

    close_at_earnings = daily_prices[earnings_idx]["close"]
    close_20d_before = daily_prices[lookback_idx]["close"]
    if close_20d_before == 0:
        return {"return_20d_pct": 0.0, "trend_direction": "up", "score": 0.0, "warning": "Price 20 days before earnings is zero"}

    return_20d_pct = (close_at_earnings / close_20d_before - 1.0) * 100.0
    return {
        "return_20d_pct": round(return_20d_pct, 2),
        "trend_direction": "up" if return_20d_pct >= 0 else "down",
        "score": _score_trend(return_20d_pct),
    }


# ── volume_trend_calculator.py ────────────────────────────────────────────

def _score_volume_ratio(ratio: float) -> float:
    if ratio >= 2.0:
        return 100.0
    elif ratio >= 1.5:
        return 80.0
    elif ratio >= 1.2:
        return 60.0
    elif ratio >= 1.0:
        return 40.0
    return 20.0


def calculate_volume_trend(daily_prices: list, earnings_date: str) -> dict:
    """ratio = most-recent-20-bar avg volume / most-recent-60-bar avg volume.
    Only meaningful when daily_prices[0] is close to earnings_date -- see
    module docstring's SCOPE NOTE."""
    earnings_idx = _find_index_by_date(daily_prices, earnings_date)
    if earnings_idx == -1:
        return {"vol_ratio_20_60": 0.0, "recent_avg_volume": 0, "longer_avg_volume": 0, "score": 0.0, "warning": f"Earnings date {earnings_date} not found in price data"}

    end_20 = min(20, len(daily_prices))
    if end_20 < 5:
        return {"vol_ratio_20_60": 0.0, "recent_avg_volume": 0, "longer_avg_volume": 0, "score": 0.0, "warning": "Insufficient data for 20-day volume calculation"}
    volumes_20 = [daily_prices[i]["volume"] for i in range(end_20)]
    recent_avg = sum(volumes_20) / len(volumes_20)

    end_60 = min(60, len(daily_prices))
    if end_60 < 20:
        return {"vol_ratio_20_60": 0.0, "recent_avg_volume": int(recent_avg), "longer_avg_volume": 0, "score": 0.0, "warning": "Insufficient data for 60-day volume calculation"}
    volumes_60 = [daily_prices[i]["volume"] for i in range(end_60)]
    longer_avg = sum(volumes_60) / len(volumes_60)
    if longer_avg == 0:
        return {"vol_ratio_20_60": 0.0, "recent_avg_volume": int(recent_avg), "longer_avg_volume": 0, "score": 0.0, "warning": "60-day average volume is zero"}

    vol_ratio = recent_avg / longer_avg
    return {
        "vol_ratio_20_60": round(vol_ratio, 2), "recent_avg_volume": int(recent_avg),
        "longer_avg_volume": int(longer_avg), "score": _score_volume_ratio(vol_ratio),
    }


# ── ma200_calculator.py / ma50_calculator.py ──────────────────────────────

def _score_ma200_distance(distance_pct: float) -> float:
    if distance_pct >= 20.0:
        return 100.0
    elif distance_pct >= 10.0:
        return 85.0
    elif distance_pct >= 5.0:
        return 70.0
    elif distance_pct >= 0.0:
        return 55.0
    elif distance_pct >= -5.0:
        return 35.0
    return 15.0


def calculate_ma200_position(daily_prices: list) -> dict:
    if len(daily_prices) < 200:
        return {"ma200": 0.0, "distance_pct": 0.0, "above_ma200": False, "score": 0.0,
                "warning": f"Insufficient data for MA200: {len(daily_prices)} days available, 200 required"}
    ma200 = sum(daily_prices[i]["close"] for i in range(200)) / 200.0
    current_price = daily_prices[0]["close"]
    if ma200 == 0:
        return {"ma200": 0.0, "distance_pct": 0.0, "above_ma200": False, "score": 0.0, "warning": "MA200 is zero"}
    distance_pct = (current_price / ma200 - 1.0) * 100.0
    return {"ma200": round(ma200, 2), "distance_pct": round(distance_pct, 2),
            "above_ma200": distance_pct >= 0, "score": _score_ma200_distance(distance_pct)}


def _score_ma50_distance(distance_pct: float) -> float:
    if distance_pct >= 10.0:
        return 100.0
    elif distance_pct >= 5.0:
        return 80.0
    elif distance_pct >= 0.0:
        return 60.0
    elif distance_pct >= -5.0:
        return 35.0
    return 15.0


def calculate_ma50_position(daily_prices: list) -> dict:
    if len(daily_prices) < 50:
        return {"ma50": 0.0, "distance_pct": 0.0, "above_ma50": False, "score": 0.0,
                "warning": f"Insufficient data for MA50: {len(daily_prices)} days available, 50 required"}
    ma50 = sum(daily_prices[i]["close"] for i in range(50)) / 50.0
    current_price = daily_prices[0]["close"]
    if ma50 == 0:
        return {"ma50": 0.0, "distance_pct": 0.0, "above_ma50": False, "score": 0.0, "warning": "MA50 is zero"}
    distance_pct = (current_price / ma50 - 1.0) * 100.0
    return {"ma50": round(ma50, 2), "distance_pct": round(distance_pct, 2),
            "above_ma50": distance_pct >= 0, "score": _score_ma50_distance(distance_pct)}


# ── scorer.py ────────────────────────────────────────────────────────────

def calculate_composite_score(gap_score: float, trend_score: float, volume_score: float, ma200_score: float, ma50_score: float) -> dict:
    components = {
        "Gap Size": {"score": gap_score, "weight": COMPONENT_WEIGHTS["gap_size"]},
        "Pre-Earnings Trend": {"score": trend_score, "weight": COMPONENT_WEIGHTS["pre_earnings_trend"]},
        "Volume Trend": {"score": volume_score, "weight": COMPONENT_WEIGHTS["volume_trend"]},
        "MA200 Position": {"score": ma200_score, "weight": COMPONENT_WEIGHTS["ma200_position"]},
        "MA50 Position": {"score": ma50_score, "weight": COMPONENT_WEIGHTS["ma50_position"]},
    }
    composite_score = round(sum(c["score"] * c["weight"] for c in components.values()), 1)

    grade, grade_description = "D", "Weak setup, avoid"
    for threshold, g, desc in GRADE_THRESHOLDS:
        if composite_score >= threshold:
            grade, grade_description = g, desc
            break

    weakest_name = min(components, key=lambda k: components[k]["score"])
    strongest_name = max(components, key=lambda k: components[k]["score"])

    return {
        "composite_score": composite_score, "grade": grade, "grade_description": grade_description,
        "guidance": GRADE_GUIDANCE.get(grade, ""), "weakest_component": weakest_name,
        "weakest_score": components[weakest_name]["score"], "strongest_component": strongest_name,
        "strongest_score": components[strongest_name]["score"],
        "component_breakdown": {
            name: {"score": c["score"], "weight": c["weight"], "weighted_score": round(c["score"] * c["weight"], 1)}
            for name, c in components.items()
        },
    }


# ── analyze_earnings_trades.py ────────────────────────────────────────────

def analyze_stock(daily_prices: list, earnings_date: str, timing: str) -> dict:
    """Score a single stock across all 5 factors. daily_prices: most-recent-first."""
    gap_result = calculate_gap(daily_prices, earnings_date, timing)
    trend_result = calculate_pre_earnings_trend(daily_prices, earnings_date)
    volume_result = calculate_volume_trend(daily_prices, earnings_date)
    ma200_result = calculate_ma200_position(daily_prices)
    ma50_result = calculate_ma50_position(daily_prices)

    composite = calculate_composite_score(
        gap_score=gap_result["score"], trend_score=trend_result["score"],
        volume_score=volume_result["score"], ma200_score=ma200_result["score"], ma50_score=ma50_result["score"],
    )

    return {
        "gap": gap_result, "pre_earnings_trend": trend_result, "volume_trend": volume_result,
        "ma200_position": ma200_result, "ma50_position": ma50_result, "composite": composite,
    }
