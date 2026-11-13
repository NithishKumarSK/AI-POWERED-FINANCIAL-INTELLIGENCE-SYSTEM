"""
pead_screener.py -- Post-Earnings-Announcement-Drift (PEAD) weekly-candle
pattern analysis, ported from claude-trading-skills' pead-screener skill
(vendor/claude-trading-skills/skills/pead-screener/scripts/
{screen_pead.py,scorer.py,calculators/*.py}, MIT License,
Copyright (c) 2026 TraderMonty).

Only the single-stock ANALYSIS pipeline (analyze_stock + its calculators)
is ported -- the skill's "Mode A" candidate-discovery path (scanning FMP's
earnings calendar + company profiles across the whole market) and its
fmp_client.py/report_generator.py are NOT ported. This project already
knows which symbol it's predicting, so the discovery step isn't needed;
core/pead_screener_service.py (the live orchestrator) answers "is THIS
symbol, right now, in a PEAD setup" using
core/free_news_service.fetch_most_recent_earnings_8k() for the earnings
date (see that function's docstring for why FMP's own earnings-calendar
couldn't be used instead -- confirmed free-tier-blocked for lookback
beyond a few days) and core/historical_price_service.py for price history.

All price lists here are MOST-RECENT-FIRST, same convention as
core/ibd_distribution_day_monitor.py and core/market_top_detector/.

4-component composite (Setup Quality 30%, Breakout Strength 25%,
Liquidity 25%, Risk/Reward 20%):
  85-100: Strong Setup   70-84: Good Setup
  55-69:  Developing     <55:   Weak (not actionable)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

COMPONENT_WEIGHTS = {
    "setup_quality": 0.30,
    "breakout_strength": 0.25,
    "liquidity": 0.25,
    "risk_reward": 0.20,
}

COMPONENT_LABELS = {
    "setup_quality": "Setup Quality",
    "breakout_strength": "Breakout Strength",
    "liquidity": "Liquidity",
    "risk_reward": "Risk/Reward",
}


# ── weekly_candle_calculator.py ──────────────────────────────────────────

def _parse_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def _iso_week_to_monday(iso_year: int, iso_week: int) -> date:
    jan4 = date(iso_year, 1, 4)
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    return week1_monday + timedelta(weeks=iso_week - 1)


def daily_to_weekly(daily_prices: list, earnings_date: Optional[str] = None) -> list:
    """Convert daily OHLCV (most-recent-first) to weekly candles (ISO week,
    Monday start), also most-recent-first. If earnings_date is given, the
    earnings week only includes days on/after it."""
    if not daily_prices:
        return []

    earnings_dt = _parse_date(earnings_date) if earnings_date else None
    sorted_prices = sorted(daily_prices, key=lambda p: p["date"])

    week_groups = {}
    for day in sorted_prices:
        day_dt = _parse_date(day["date"])
        iso_year, iso_week, _ = day_dt.isocalendar()
        week_key = (iso_year, iso_week)

        if earnings_dt:
            earnings_iso = earnings_dt.isocalendar()
            earnings_week_key = (earnings_iso[0], earnings_iso[1])
            if week_key == earnings_week_key and day_dt < earnings_dt:
                continue

        week_groups.setdefault(week_key, []).append(day)

    if sorted_prices:
        latest_dt = _parse_date(sorted_prices[-1]["date"])
        latest_iso = latest_dt.isocalendar()
        latest_week_key = (latest_iso[0], latest_iso[1])
        is_latest_partial = latest_iso[2] < 5
    else:
        latest_week_key = None
        is_latest_partial = False

    weekly_candles = []
    for week_key in sorted(week_groups.keys()):
        days = week_groups[week_key]
        if not days:
            continue
        iso_year, iso_week = week_key
        monday = _iso_week_to_monday(iso_year, iso_week)

        week_open = days[0]["open"]
        week_high = max(d["high"] for d in days)
        week_low = min(d["low"] for d in days)
        week_close = days[-1]["close"]
        week_volume = sum(d.get("volume", 0) for d in days)

        partial = week_key == latest_week_key and is_latest_partial
        if earnings_dt:
            earnings_iso = earnings_dt.isocalendar()
            earnings_week_key = (earnings_iso[0], earnings_iso[1])
            if week_key == earnings_week_key and len(days) < 5:
                partial = True

        weekly_candles.append({
            "week_start": monday.strftime("%Y-%m-%d"), "year": iso_year, "week": iso_week,
            "open": round(week_open, 2), "high": round(week_high, 2), "low": round(week_low, 2),
            "close": round(week_close, 2), "volume": week_volume,
            "is_green": week_close >= week_open, "partial_week": partial, "trading_days": len(days),
        })

    weekly_candles.reverse()
    return weekly_candles


def find_red_candle(weekly_candles: list, earnings_week_idx: Optional[int] = None) -> Optional[dict]:
    """Most recent red candle (close < open) after earnings week."""
    if not weekly_candles:
        return None

    end_idx = earnings_week_idx if earnings_week_idx is not None else len(weekly_candles) - 1
    for i in range(0, min(end_idx, len(weekly_candles))):
        candle = weekly_candles[i]
        if not candle["is_green"]:
            candle_range = candle["high"] - candle["low"]
            if candle_range > 0:
                body_low = min(candle["open"], candle["close"])
                lower_wick_pct = (body_low - candle["low"]) / candle_range * 100
            else:
                lower_wick_pct = 0.0

            surrounding = [weekly_candles[j]["volume"] for j in range(max(0, i - 2), min(len(weekly_candles), i + 3)) if j != i]
            if surrounding:
                avg_vol = sum(surrounding) / len(surrounding)
                volume_vs_avg = candle["volume"] / avg_vol if avg_vol > 0 else 1.0
            else:
                volume_vs_avg = 1.0

            return {
                "high": candle["high"], "low": candle["low"], "open": candle["open"], "close": candle["close"],
                "week_start": candle["week_start"], "week_index": i,
                "lower_wick_pct": round(lower_wick_pct, 1), "volume_vs_avg": round(volume_vs_avg, 2),
            }
    return None


def analyze_weekly_pattern(weekly_candles: list, earnings_date: str, watch_weeks: int = 5) -> dict:
    result = {
        "weeks_since_earnings": 0, "earnings_week_idx": None, "red_candle": None,
        "is_breakout": False, "breakout_pct": 0.0, "stage": "MONITORING",
    }
    if not weekly_candles:
        return result

    earnings_dt = _parse_date(earnings_date)
    earnings_iso = earnings_dt.isocalendar()
    earnings_week_key = (earnings_iso[0], earnings_iso[1])

    earnings_week_idx = None
    for i, candle in enumerate(weekly_candles):
        if candle["year"] == earnings_week_key[0] and candle["week"] == earnings_week_key[1]:
            earnings_week_idx = i
            break
    result["earnings_week_idx"] = earnings_week_idx

    if earnings_week_idx is not None:
        result["weeks_since_earnings"] = earnings_week_idx
    else:
        latest_dt = _parse_date(weekly_candles[0]["week_start"])
        result["weeks_since_earnings"] = max(0, (latest_dt - earnings_dt).days // 7)

    if result["weeks_since_earnings"] > watch_weeks:
        result["stage"] = "EXPIRED"
        return result

    red_candle = find_red_candle(weekly_candles, earnings_week_idx=earnings_week_idx)
    result["red_candle"] = red_candle
    if red_candle is None:
        result["stage"] = "MONITORING"
        return result

    current_candle = weekly_candles[0]
    if current_candle["is_green"] and current_candle["close"] > red_candle["high"]:
        result["is_breakout"] = True
        result["breakout_pct"] = round((current_candle["close"] - red_candle["high"]) / red_candle["high"] * 100, 2)
        result["stage"] = "BREAKOUT"
    else:
        result["stage"] = "SIGNAL_READY"
    return result


# ── breakout_calculator.py ──────────────────────────────────────────────

def _check_volume_confirmation(weekly_candles: list, current_candle: dict) -> bool:
    if len(weekly_candles) < 2:
        return False
    prior_volumes = [weekly_candles[i]["volume"] for i in range(1, min(5, len(weekly_candles))) if weekly_candles[i].get("volume", 0) > 0]
    if not prior_volumes:
        return False
    avg_volume = sum(prior_volumes) / len(prior_volumes)
    return current_candle.get("volume", 0) > avg_volume


def calculate_breakout(weekly_candles: list, red_candle: Optional[dict], current_price: float) -> dict:
    result = {"is_breakout": False, "breakout_pct": 0.0, "volume_confirmation": False, "score": 0.0}
    if not red_candle or not weekly_candles:
        return result

    red_high = red_candle["high"]
    if red_high <= 0:
        return result

    breakout_pct = (current_price - red_high) / red_high * 100
    result["breakout_pct"] = round(breakout_pct, 2)
    if breakout_pct <= 0:
        return result

    result["is_breakout"] = True
    volume_confirmed = _check_volume_confirmation(weekly_candles, weekly_candles[0])
    result["volume_confirmation"] = volume_confirmed

    if breakout_pct >= 3.0 and volume_confirmed:
        result["score"] = 100.0
    elif breakout_pct >= 2.0 and volume_confirmed:
        result["score"] = 85.0
    elif breakout_pct >= 1.0:
        result["score"] = 70.0
    else:
        result["score"] = 55.0
    return result


# ── liquidity_calculator.py ──────────────────────────────────────────────

def calculate_liquidity(daily_prices: list, current_price: float) -> dict:
    result = {"adv20_dollar": 0.0, "avg_volume_20d": 0.0, "price": current_price, "passes_all": False, "score": 15.0}
    if not daily_prices or current_price <= 0:
        return result

    recent_20 = daily_prices[:20]
    volumes = [d.get("volume", 0) for d in recent_20]
    if not volumes:
        return result

    avg_volume = sum(volumes) / len(volumes)
    result["avg_volume_20d"] = round(avg_volume, 0)

    dollar_volumes = [d.get("volume", 0) * d.get("close", 0) for d in recent_20 if d.get("volume", 0) > 0 and d.get("close", 0) > 0]
    adv20 = sum(dollar_volumes) / len(dollar_volumes) if dollar_volumes else avg_volume * current_price
    result["adv20_dollar"] = round(adv20, 0)

    passes_count = sum([adv20 >= 25_000_000, avg_volume >= 1_000_000, current_price >= 10.0])
    result["passes_all"] = passes_count == 3

    if passes_count == 3:
        result["score"] = 100.0 if adv20 > 100_000_000 else 85.0 if adv20 > 50_000_000 else 70.0
    elif passes_count == 2:
        result["score"] = 40.0
    else:
        result["score"] = 15.0
    return result


# ── risk_reward_calculator.py ─────────────────────────────────────────────

def calculate_risk_reward(current_price: float, red_candle: Optional[dict], target_multiplier: float = 2.0) -> dict:
    result = {
        "entry_price": current_price, "stop_price": 0.0, "target_price": 0.0,
        "risk_pct": 0.0, "reward_pct": 0.0, "risk_reward_ratio": 0.0, "score": 25.0,
    }
    if not red_candle or current_price <= 0:
        return result

    stop_price = red_candle["low"]
    if stop_price <= 0 or stop_price >= current_price:
        return result

    risk = current_price - stop_price
    reward = risk * target_multiplier
    target_price = current_price + reward
    rr_ratio = reward / risk if risk > 0 else 0.0

    result.update({
        "entry_price": round(current_price, 2), "stop_price": round(stop_price, 2),
        "target_price": round(target_price, 2), "risk_pct": round(risk / current_price * 100, 2),
        "reward_pct": round(reward / current_price * 100, 2), "risk_reward_ratio": round(rr_ratio, 2),
    })

    if rr_ratio >= 3.0:
        result["score"] = 100.0
    elif rr_ratio >= 2.5:
        result["score"] = 85.0
    elif rr_ratio >= 2.0:
        result["score"] = 70.0
    elif rr_ratio >= 1.5:
        result["score"] = 50.0
    else:
        result["score"] = 25.0
    return result


# ── scorer.py ────────────────────────────────────────────────────────────

def calculate_composite_score(setup_score: float, breakout_score: float, liquidity_score: float, rr_score: float) -> dict:
    component_scores = {
        "setup_quality": setup_score, "breakout_strength": breakout_score,
        "liquidity": liquidity_score, "risk_reward": rr_score,
    }
    composite = round(sum(component_scores[k] * w for k, w in COMPONENT_WEIGHTS.items()), 1)
    weakest_key = min(component_scores, key=component_scores.get)
    strongest_key = max(component_scores, key=component_scores.get)
    rating_info = _get_rating(composite)

    return {
        "composite_score": composite, "rating": rating_info["rating"],
        "rating_description": rating_info["description"], "guidance": rating_info["guidance"],
        "weakest_component": COMPONENT_LABELS[weakest_key], "weakest_score": component_scores[weakest_key],
        "strongest_component": COMPONENT_LABELS[strongest_key], "strongest_score": component_scores[strongest_key],
        "component_breakdown": {
            k: {"score": component_scores[k], "weight": w, "weighted": round(component_scores[k] * w, 1), "label": COMPONENT_LABELS[k]}
            for k, w in COMPONENT_WEIGHTS.items()
        },
    }


def _get_rating(composite: float) -> dict:
    if composite >= 85:
        return {"rating": "Strong Setup", "description": "High-conviction PEAD trade with all components aligned",
                "guidance": "High-conviction PEAD trade, full position size"}
    elif composite >= 70:
        return {"rating": "Good Setup", "description": "Solid PEAD setup with minor imperfections",
                "guidance": "Solid PEAD setup, standard position size"}
    elif composite >= 55:
        return {"rating": "Developing", "description": "PEAD pattern forming but not yet fully actionable",
                "guidance": "Watchlist, wait for cleaner breakout"}
    return {"rating": "Weak", "description": "Insufficient PEAD characteristics for trading", "guidance": "Not actionable"}


# ── screen_pead.py (calculate_price_gap + calculate_setup_quality + analyze_stock) ─

def calculate_price_gap(daily_prices: list, earnings_date: str, timing: str) -> float:
    """BMO: gap = open[earnings_date]/close[prev_day] - 1.
    AMC/unknown: gap = open[next_day]/close[earnings_date] - 1.
    daily_prices: most-recent-first."""
    earnings_idx = next((i for i, bar in enumerate(daily_prices) if bar.get("date") == earnings_date), -1)
    if earnings_idx == -1:
        return 0.0

    timing_lower = (timing or "").lower().strip()
    if timing_lower == "bmo":
        prev_idx = earnings_idx + 1
        if prev_idx >= len(daily_prices):
            return 0.0
        base_price = daily_prices[prev_idx].get("close", 0)
        gap_price = daily_prices[earnings_idx].get("open", 0)
    else:
        next_idx = earnings_idx - 1
        if next_idx < 0:
            return 0.0
        base_price = daily_prices[earnings_idx].get("close", 0)
        gap_price = daily_prices[next_idx].get("open", 0)

    if not base_price:
        return 0.0
    return round((gap_price / base_price - 1.0) * 100.0, 2)


def calculate_setup_quality(gap_pct: float, pattern_result: dict) -> float:
    score = 0.0
    if gap_pct >= 10.0:
        score += 50
    elif gap_pct >= 7.0:
        score += 40
    elif gap_pct >= 5.0:
        score += 30
    elif gap_pct >= 3.0:
        score += 20
    else:
        score += 10

    stage = pattern_result.get("stage", "MONITORING")
    weeks = pattern_result.get("weeks_since_earnings", 0)
    red_candle = pattern_result.get("red_candle")

    if stage == "BREAKOUT":
        score += 50
    elif stage == "SIGNAL_READY":
        score += 40
        if red_candle and red_candle.get("lower_wick_pct", 0) > 30:
            score += 5
    elif stage == "MONITORING":
        score += 25 if weeks <= 2 else 15
    # EXPIRED -> +0

    return min(100.0, score)


def analyze_stock(
    symbol: str, daily_prices: list, earnings_date: str, earnings_timing: str,
    gap_pct: float, current_price: float, watch_weeks: int = 5,
) -> Optional[dict]:
    """Full PEAD analysis for a single stock. daily_prices: most-recent-first."""
    if not daily_prices or len(daily_prices) < 5:
        return None

    weekly_candles = daily_to_weekly(daily_prices, earnings_date=earnings_date)
    if not weekly_candles:
        return None

    pattern = analyze_weekly_pattern(weekly_candles, earnings_date, watch_weeks=watch_weeks)
    setup_score = calculate_setup_quality(gap_pct, pattern)

    red_candle = pattern.get("red_candle")
    if red_candle:
        breakout = calculate_breakout(weekly_candles, red_candle, current_price)
    else:
        breakout = {"is_breakout": False, "breakout_pct": 0.0, "volume_confirmation": False, "score": 0.0}

    liquidity = calculate_liquidity(daily_prices, current_price)

    if red_candle:
        rr = calculate_risk_reward(current_price, red_candle)
    else:
        rr = {"entry_price": current_price, "stop_price": 0.0, "target_price": 0.0,
              "risk_pct": 0.0, "reward_pct": 0.0, "risk_reward_ratio": 0.0, "score": 25.0}

    composite = calculate_composite_score(
        setup_score=setup_score, breakout_score=breakout["score"],
        liquidity_score=liquidity["score"], rr_score=rr["score"],
    )

    return {
        "symbol": symbol, "stage": pattern["stage"], "earnings_date": earnings_date,
        "earnings_timing": earnings_timing, "gap_pct": gap_pct,
        "weeks_since_earnings": pattern["weeks_since_earnings"], "red_candle": red_candle,
        "current_price": current_price, "breakout_pct": breakout["breakout_pct"],
        "entry_price": rr["entry_price"], "stop_price": rr["stop_price"], "target_price": rr["target_price"],
        "risk_pct": rr["risk_pct"], "risk_reward_ratio": rr["risk_reward_ratio"],
        "adv20_dollar": liquidity["adv20_dollar"], "composite_score": composite["composite_score"],
        "rating": composite["rating"], "guidance": composite["guidance"], "components": composite["component_breakdown"],
    }
