"""
stockbee_20pct_study.py -- detects whether a symbol just had a 20%+ price
move (over a trailing N-day window) and classifies its chart pattern,
close quality, extension risk, and continuation-quality/reversal-risk
scores, ported from claude-trading-skills' stockbee-20pct-study skill
(vendor/claude-trading-skills/skills/stockbee-20pct-study/scripts/run_20pct_study.py,
MIT License, Copyright (c) 2026 TraderMonty).

Entirely price-history-based -- no fundamentals/FMP needed at all, same
category as core/vcp_screener.py.

SCOPE REDUCTION, disclosed: the source skill's own design is a cross-
universe DAILY SCAN with a persistent JSONL state file for episode
tracking and forward-outcome maturation (`determine_episode_id`,
`episode_day_index`, `outcomes`) -- a two-part discover+journal system
like core/stockbee_setup_fluency_trainer.py. Only the point-in-time
DETECTION + classification + scoring for a single, caller-given symbol
is ported here (`detect_twenty_pct_events` already takes a
{symbol: bars} dict and loops over it, so calling it with exactly one
symbol is a faithful use of the unmodified function, not a rewrite); the
episode-journal/forward-outcome-maturation half was not built, since this
project's single-symbol-per-prediction architecture has no natural
"daily cross-sectional scan" to journal from (same reasoning noted for
core/stockbee_setup_fluency_trainer.py's own non-wiring).

Catalyst classification (`default_catalyst`) is always "NO_CLEAR_NEWS" --
the skill's own optional news-enrichment step was not ported (this
project's free_news_service.py's categories don't map onto the skill's
own catalyst-label taxonomy cleanly enough to port without guessing).

Bars are CHRONOLOGICAL (oldest first), matching historical_price_service's
native order -- `idx` increases moving forward in time.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

PCT_EPSILON = 1e-9
DEFAULT_LOOKBACK_DAYS = 5
DEFAULT_MIN_ABS_RETURN_PCT = 20.0
DEFAULT_MIN_PRICE = 5.0
DEFAULT_MIN_DOLLAR_VOLUME = 20_000_000.0


@dataclass
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def parse_date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def find_as_of_index(bars: list, as_of: Optional[str]) -> Optional[int]:
    if not bars:
        return None
    if as_of is None:
        return len(bars) - 1
    target = parse_date(as_of)
    eligible = [idx for idx, bar in enumerate(bars) if parse_date(bar.date) <= target]
    if not eligible:
        return None
    return eligible[-1]


def pct_change(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0
    return (current / previous - 1.0) * 100.0


def safe_pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator * 100.0


def close_location_pct(bar) -> float:
    if bar.high <= bar.low:
        return 50.0
    return max(0.0, min(100.0, (bar.close - bar.low) / (bar.high - bar.low) * 100.0))


def average(values: list) -> float:
    return sum(values) / len(values) if values else 0.0


def classify_close_quality(close_loc: float, direction: str) -> str:
    if direction == "UP":
        if close_loc >= 80:
            return "STRONG_CLOSE"
        if close_loc >= 55:
            return "MID_CLOSE"
        return "WEAK_CLOSE"
    if close_loc <= 20:
        return "WEAK_CLOSE_DOWN"
    if close_loc <= 45:
        return "MID_CLOSE_DOWN"
    return "REVERSAL_CLOSE"


def classify_extension_risk(abs_return_pct: float, abs_prior_20d_return_pct: float, close_loc: float) -> str:
    score = 0
    if abs_return_pct >= 60:
        score += 2
    elif abs_return_pct >= 35:
        score += 1
    if abs_prior_20d_return_pct >= 50:
        score += 2
    elif abs_prior_20d_return_pct >= 25:
        score += 1
    if close_loc < 45:
        score += 1
    if score >= 4:
        return "HIGH"
    if score >= 2:
        return "MODERATE"
    return "LOW"


def classify_chart_pattern(direction: str, close_location: float, gap_pct: float, range_pct: float, return_pct: float,
                            distance_to_52w_high_pct: float, volume_ratio_20: float, prior_20d_return_pct: float) -> str:
    if direction == "DOWN":
        if close_location >= 65:
            return "DOWN_GAP_REVERSAL_CANDIDATE"
        if abs(return_pct) >= 35 and close_location <= 25:
            return "STRUCTURAL_BREAKDOWN"
        return "BREAKDOWN_EVENT"

    near_52w_high = distance_to_52w_high_pct >= -5.0
    if gap_pct >= 8 and close_location >= 75 and volume_ratio_20 >= 2:
        return "GAP_AND_GO"
    if near_52w_high and close_location >= 70 and volume_ratio_20 >= 1.5:
        return "BASE_BREAKOUT"
    if return_pct >= 50 and close_location < 55:
        return "CLIMAX_EXTENSION"
    if close_location < 45:
        return "FAILED_BREAKOUT"
    if prior_20d_return_pct > 40:
        return "EXTENDED_MOMENTUM"
    return "MOMENTUM_EVENT"


def estimate_base_length(bars: list, idx: int, max_lookback: int = 80) -> int:
    if idx <= 0:
        return 0
    current_close = bars[idx].close
    threshold = current_close * 0.75
    count = 0
    for bar in reversed(bars[max(0, idx - max_lookback):idx]):
        if bar.close < threshold:
            break
        count += 1
    return count


def estimate_base_depth_pct(bars: list, idx: int, lookback: int = 50) -> float:
    segment = bars[max(0, idx - lookback):idx]
    if not segment:
        return 0.0
    high = max(bar.high for bar in segment)
    low = min(bar.low for bar in segment)
    return safe_pct(high - low, high)


def default_catalyst(direction: str) -> dict:
    return {
        "label": "NO_CLEAR_NEWS", "confidence": 0.0, "source_type": "price_only",
        "summary": f"{direction} 20% mover detected from price/volume data; catalyst not enriched.",
    }


def data_quality_flags_for_event(bars: list, idx: int, current_bar, return_pct: float, avg_dollar_volume_20: float) -> list:
    flags = []
    if len(bars) < 260:
        flags.append("SHORT_HISTORY_LT_260_BARS")
    if avg_dollar_volume_20 and avg_dollar_volume_20 < 5_000_000:
        flags.append("LOW_AVG_DOLLAR_VOLUME")
    if current_bar.volume <= 0:
        flags.append("MISSING_VOLUME")
    if abs(return_pct) > 200:
        flags.append("EXTREME_MOVE_CHECK_SPLIT_OR_CORPORATE_ACTION")
    if idx > 0:
        previous = bars[idx - 1]
        if current_bar.open > previous.close * 4 or current_bar.open < previous.close * 0.25:
            flags.append("POSSIBLE_SPLIT_OR_SPECIAL_DISTRIBUTION")
    return flags


def score_event(direction: str, catalyst: dict, dollar_volume: float, volume_ratio_20: float, close_location: float,
                 distance_to_52w_high_pct: float, pattern_label: str, extension_risk: str, data_quality_flags: list) -> dict:
    catalyst_points_by_label = {
        "EARNINGS_REVALUATION": 24, "GUIDANCE_RAISE": 24, "M&A": 22, "CONTRACT_ORDER": 18,
        "FDA_CLINICAL": 14, "ANALYST_UPGRADE": 12, "SHORT_SQUEEZE": 8, "THEME_SYMPATHY": 14,
        "NO_CLEAR_NEWS": 3, "LOW_FLOAT_SPECULATION": 0, "CAPITAL_STRUCTURE": 0,
    }
    catalyst_label = str(catalyst.get("label") or "NO_CLEAR_NEWS")
    catalyst_quality = catalyst_points_by_label.get(catalyst_label, 5)
    liquidity_score = min(15, int(dollar_volume / 20_000_000 * 10))
    volume_score = min(10, int(volume_ratio_20 * 3))
    close_score = int(close_location / 100 * 15) if direction == "UP" else int((100 - close_location) / 100 * 15)
    setup_score = 12 if pattern_label in {"BASE_BREAKOUT", "GAP_AND_GO"} else 8 if "MOMENTUM" in pattern_label else 3
    high_score = 10 if direction == "UP" and distance_to_52w_high_pct >= -5 else 4
    if direction == "DOWN":
        high_score = 5
    extension_penalty = {"LOW": 0, "MODERATE": -5, "HIGH": -12}.get(extension_risk, -5)
    data_quality_score = max(0, 100 - len(data_quality_flags) * 15)
    data_quality_component = int(data_quality_score / 100 * 10)
    continuation_quality_score = max(0, min(100, catalyst_quality + liquidity_score + volume_score + close_score
                                               + setup_score + high_score + data_quality_component + extension_penalty))
    reversal_risk_score = 0
    if catalyst_label in {"NO_CLEAR_NEWS", "LOW_FLOAT_SPECULATION", "CAPITAL_STRUCTURE"}:
        reversal_risk_score += 25
    if extension_risk == "HIGH":
        reversal_risk_score += 25
    elif extension_risk == "MODERATE":
        reversal_risk_score += 12
    if direction == "UP" and close_location < 50:
        reversal_risk_score += 25
    if dollar_volume < 20_000_000:
        reversal_risk_score += 15
    if data_quality_flags:
        reversal_risk_score += min(20, len(data_quality_flags) * 8)
    study_priority_score = max(0, min(100, continuation_quality_score + 20 - abs(50 - reversal_risk_score) // 3))
    return {
        "continuation_quality_score": int(continuation_quality_score), "reversal_risk_score": int(min(100, reversal_risk_score)),
        "study_priority_score": int(study_priority_score), "data_quality_score": int(data_quality_score),
    }


def labels_for_event(direction: str, pattern_label: str, close_quality: str, extension_risk: str, scores: dict) -> list:
    labels = [direction, pattern_label, close_quality]
    if extension_risk != "LOW":
        labels.append(f"{extension_risk}_EXTENSION_RISK")
    if scores.get("continuation_quality_score", 0) >= 75:
        labels.append("A_REVALUATION_OR_HIGH_QUALITY_EVENT")
    elif scores.get("continuation_quality_score", 0) >= 60:
        labels.append("B_MOMENTUM_EVENT")
    elif scores.get("reversal_risk_score", 0) >= 65:
        labels.append("D_LOW_QUALITY_OR_REVERSAL_RISK")
    else:
        labels.append("C_STUDY_ONLY")
    return labels


def handoff_flags(direction: str, catalyst_label: str, pattern_label: str, scores: dict) -> dict:
    return {
        "stockbee_episodic_pivot": direction == "UP" and pattern_label in {"GAP_AND_GO", "BASE_BREAKOUT"},
        "pead_screener": catalyst_label in {"EARNINGS_REVALUATION", "GUIDANCE_RAISE"},
        "theme_detector": catalyst_label == "THEME_SYMPATHY" or scores.get("study_priority_score", 0) >= 80,
        "edge_candidate_agent": scores.get("study_priority_score", 0) >= 85,
        "parabolic_short_watch": direction == "UP" and scores.get("reversal_risk_score", 0) >= 70,
    }


def detect_twenty_pct_event(
    bars: list, as_of: Optional[str] = None, lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_abs_return_pct: float = DEFAULT_MIN_ABS_RETURN_PCT, min_price: float = DEFAULT_MIN_PRICE,
    min_dollar_volume: float = DEFAULT_MIN_DOLLAR_VOLUME, include_down_movers: bool = True,
) -> Optional[dict]:
    """Check whether `bars`' as_of day qualifies as a 20%+ (or configured
    threshold) move over `lookback_days`, and if so, classify + score it.
    bars: chronological (oldest first). Returns None if no event (below
    threshold, or filtered out by price/liquidity gates) -- not an error,
    just "no event today," the same honest-absence convention every other
    detector in this project uses.
    """
    idx = find_as_of_index(bars, as_of)
    if idx is None or idx < lookback_days:
        return None

    current_bar = bars[idx]
    lookback_bar = bars[idx - lookback_days]
    previous_bar = bars[idx - 1] if idx > 0 else lookback_bar
    return_pct = pct_change(current_bar.close, lookback_bar.close)

    direction = None
    if return_pct + PCT_EPSILON >= min_abs_return_pct:
        direction = "UP"
    elif include_down_movers and return_pct - PCT_EPSILON <= -min_abs_return_pct:
        direction = "DOWN"
    if direction is None:
        return None
    if current_bar.close < min_price:
        return None
    dollar_volume = current_bar.close * current_bar.volume
    if dollar_volume < min_dollar_volume:
        return None

    history_20 = bars[max(0, idx - 20):idx]
    history_252 = bars[max(0, idx - 252):idx + 1]
    avg_volume_20 = average([bar.volume for bar in history_20])
    avg_dollar_volume_20 = average([bar.close * bar.volume for bar in history_20])
    volume_ratio_20 = current_bar.volume / avg_volume_20 if avg_volume_20 else 0.0
    high_52w = max([bar.high for bar in history_252], default=current_bar.high)
    low_52w = min([bar.low for bar in history_252], default=current_bar.low)
    distance_to_52w_high_pct = pct_change(current_bar.close, high_52w)
    distance_to_52w_low_pct = pct_change(current_bar.close, low_52w)
    prior_20d_return_pct = pct_change(previous_bar.close, bars[max(0, idx - 21)].close) if idx >= 21 else 0.0
    prior_50d_return_pct = pct_change(previous_bar.close, bars[max(0, idx - 51)].close) if idx >= 51 else 0.0
    close_loc = close_location_pct(current_bar)
    range_pct = safe_pct(current_bar.high - current_bar.low, previous_bar.close)
    gap_pct = pct_change(current_bar.open, previous_bar.close)

    pattern_label = classify_chart_pattern(direction, close_loc, gap_pct, range_pct, return_pct,
                                             distance_to_52w_high_pct, volume_ratio_20, prior_20d_return_pct)
    close_quality = classify_close_quality(close_loc, direction)
    extension_risk = classify_extension_risk(abs(return_pct), abs(prior_20d_return_pct), close_loc)
    data_quality_flags = data_quality_flags_for_event(bars, idx, current_bar, return_pct, avg_dollar_volume_20)
    catalyst = default_catalyst(direction)
    scores = score_event(direction, catalyst, dollar_volume, volume_ratio_20, close_loc,
                          distance_to_52w_high_pct, pattern_label, extension_risk, data_quality_flags)

    return {
        "event_date": current_bar.date, "direction": direction, "window_days": lookback_days,
        "price_snapshot": {
            "open": round(current_bar.open, 4), "high": round(current_bar.high, 4), "low": round(current_bar.low, 4),
            "close": round(current_bar.close, 4), "previous_close": round(previous_bar.close, 4),
            "lookback_close": round(lookback_bar.close, 4), "return_pct": round(return_pct, 4),
            "day_return_pct": round(pct_change(current_bar.close, previous_bar.close), 4),
            "gap_pct": round(gap_pct, 4), "range_pct": round(range_pct, 4), "close_location_pct": round(close_loc, 2),
        },
        "liquidity": {
            "volume": current_bar.volume, "avg_volume_20d": round(avg_volume_20, 2), "volume_ratio_20d": round(volume_ratio_20, 3),
            "dollar_volume": round(dollar_volume, 2), "avg_dollar_volume_20d": round(avg_dollar_volume_20, 2),
            "price_pass": current_bar.close >= min_price, "liquidity_pass": dollar_volume >= min_dollar_volume,
        },
        "technical_context": {
            "distance_to_52w_high_pct": round(distance_to_52w_high_pct, 4), "distance_to_52w_low_pct": round(distance_to_52w_low_pct, 4),
            "prior_20d_return_pct": round(prior_20d_return_pct, 4), "prior_50d_return_pct": round(prior_50d_return_pct, 4),
            "base_length_days": estimate_base_length(bars, idx), "base_depth_pct": round(estimate_base_depth_pct(bars, idx), 4),
            "pattern_label": pattern_label, "close_quality": close_quality, "extension_risk": extension_risk,
        },
        "catalyst": catalyst, "scores": scores,
        "labels": labels_for_event(direction, pattern_label, close_quality, extension_risk, scores),
        "handoffs": handoff_flags(direction, catalyst["label"], pattern_label, scores),
        "data_quality": {"flags": data_quality_flags, "data_quality_score": scores["data_quality_score"]},
    }
