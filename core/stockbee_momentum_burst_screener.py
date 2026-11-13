"""
stockbee_momentum_burst_screener.py -- Stockbee-style short-term Momentum
Burst detection (4% breakout, dollar breakout, range expansion, 9M-volume
trigger, prior-base contraction, close-location, failure filters, risk
distance -> composite score/rating/state), ported from claude-trading-skills'
stockbee-momentum-burst-screener skill
(vendor/claude-trading-skills/skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py,
MIT License, Copyright (c) 2026 TraderMonty).

Only the per-symbol ANALYSIS pipeline (analyze_symbol + its helpers) is
ported -- the skill's own FMP-universe-scan input mode was not, same
reasoning as core/stockbee_exhaustion_hammer_screener.py (its sibling
skill, built just before this one, sharing the same structure).
core/stockbee_momentum_burst_service.py (the live orchestrator) reuses
historical_price_service.py for price history and the same
ibd_distribution_day_service-derived market_gate.

All Bar lists are MOST-RECENT-FIRST, same convention as
core/stockbee_exhaustion_hammer_screener.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class BaseProfile:
    prior_base_days: int
    base_width_pct: float
    avg_prior_range_pct: float
    volume_dry_up: bool


@dataclass
class TriggerProfile:
    trigger_tags: list
    primary_trigger: str
    day_gain_pct: float
    dollar_gain: float
    current_range_pct: float
    current_range_dollars: float
    volume_ratio_1d: float
    volume_ratio_20d: float
    close_location_pct: float
    prev_day_gain_pct: float


@dataclass
class ScreenerConfig:
    """Faithful port of parse_arguments()'s defaults (Mode A/B/C input
    args excluded -- only the per-symbol analysis thresholds remain)."""
    min_price: float = 5.0
    min_volume: int = 100_000
    four_pct_threshold: float = 4.0
    dollar_threshold: float = 0.90
    nine_million_volume: int = 9_000_000
    max_prev_day_gain_for_range: float = 2.0
    min_base_days: int = 3
    max_base_days: int = 20
    max_base_width_pct: float = 15.0
    max_prior_avg_range_pct: float = 5.0
    narrow_prior_day_range_pct: float = 3.0
    recent_breakdown_lookback: int = 5
    breakdown_threshold_pct: float = 4.0
    max_risk_pct_to_stop: float = 10.0
    market_gate: str = "neutral"  # "allowed" | "neutral" | "restrictive"


def normalize_symbol(value: str) -> str:
    return (value or "").strip().upper()


def safe_round(value: Any, digits: int = 2) -> float:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0


def average(values: list) -> float:
    return sum(values) / len(values) if values else 0.0


def pct_change(new: float, old: float) -> float:
    if old <= 0:
        return 0.0
    return (new / old - 1.0) * 100.0


def close_location_pct(bar: Bar) -> float:
    day_range = bar.high - bar.low
    if day_range <= 0:
        return 50.0
    return (bar.close - bar.low) / day_range * 100.0


def up_streak_before_trigger(bars: list, max_days: int = 5) -> int:
    """Consecutive up closes immediately before the latest trigger bar."""
    streak = 0
    for idx in range(1, min(len(bars) - 1, max_days) + 1):
        if bars[idx].close > bars[idx + 1].close:
            streak += 1
        else:
            break
    return streak


def has_recent_breakdown(bars: list, lookback_days: int = 5, threshold_pct: float = -4.0) -> bool:
    end = min(len(bars) - 1, lookback_days + 1)
    for idx in range(1, end):
        if pct_change(bars[idx].close, bars[idx + 1].close) <= threshold_pct:
            return True
    return False


def detect_base_profile(bars: list, min_base_days: int, max_base_days: int, max_base_width_pct: float, max_prior_avg_range_pct: float) -> BaseProfile:
    """Best simple prior consolidation window before the trigger day."""
    if len(bars) < min_base_days + 2:
        return BaseProfile(0, 0.0, 0.0, False)

    best = None
    longest_window = min(max_base_days, len(bars) - 1)
    for window in range(min_base_days, longest_window + 1):
        prior = bars[1 : 1 + window]
        ref_close = prior[0].close
        if ref_close <= 0:
            continue
        base_width_pct = (max(b.high for b in prior) - min(b.low for b in prior)) / ref_close * 100
        avg_range_pct = average([(b.high - b.low) / b.close * 100 for b in prior if b.close > 0])
        if base_width_pct <= max_base_width_pct and avg_range_pct <= max_prior_avg_range_pct:
            base_vol = average([float(b.volume) for b in prior])
            older = bars[1 + window : 1 + window * 2]
            older_vol = average([float(b.volume) for b in older]) if older else 0.0
            volume_dry_up = bool(older_vol and base_vol <= older_vol * 0.85)
            candidate = BaseProfile(window, base_width_pct, avg_range_pct, volume_dry_up)
            if best is None:
                best = candidate
            elif candidate.prior_base_days > best.prior_base_days:
                best = candidate
            elif candidate.prior_base_days == best.prior_base_days and candidate.base_width_pct < best.base_width_pct:
                best = candidate

    if best:
        return best

    fallback_window = min(longest_window, max(min_base_days, 1))
    prior = bars[1 : 1 + fallback_window]
    ref_close = prior[0].close if prior else 1.0
    width = ((max(b.high for b in prior) - min(b.low for b in prior)) / ref_close * 100) if prior else 0.0
    avg_range = average([(b.high - b.low) / b.close * 100 for b in prior if b.close > 0])
    return BaseProfile(0, width, avg_range, False)


def detect_triggers(bars: list, cfg: ScreenerConfig) -> TriggerProfile:
    latest, prev, prior_2 = bars[0], bars[1], bars[2]
    day_gain_pct = pct_change(latest.close, prev.close)
    dollar_gain = latest.close - latest.open
    current_range = latest.high - latest.low
    current_range_pct = current_range / latest.close * 100 if latest.close > 0 else 0.0
    prior_ranges = [b.high - b.low for b in bars[1:4]]
    prior_range_max = max(prior_ranges) if prior_ranges else 0.0
    prev_day_gain_pct = pct_change(prev.close, prior_2.close)
    volume_ratio_1d = latest.volume / prev.volume if prev.volume > 0 else 0.0
    avg_vol_20 = average([float(b.volume) for b in bars[1:21]])
    volume_ratio_20d = latest.volume / avg_vol_20 if avg_vol_20 > 0 else 0.0

    trigger_tags = []
    volume_floor_ok = latest.volume >= cfg.min_volume
    volume_expanded = latest.volume > prev.volume

    if day_gain_pct >= cfg.four_pct_threshold and volume_expanded and volume_floor_ok:
        trigger_tags.append("4pct_breakout")
    if dollar_gain >= cfg.dollar_threshold and volume_floor_ok:
        trigger_tags.append("dollar_breakout")
    if current_range > prior_range_max and prev_day_gain_pct <= cfg.max_prev_day_gain_for_range and volume_expanded and volume_floor_ok:
        trigger_tags.append("range_expansion")
    if latest.volume >= cfg.nine_million_volume:
        trigger_tags.append("9m_volume")

    primary_order = ["4pct_breakout", "range_expansion", "dollar_breakout", "9m_volume"]
    primary = next((tag for tag in primary_order if tag in trigger_tags), "none")

    return TriggerProfile(
        trigger_tags=trigger_tags, primary_trigger=primary, day_gain_pct=day_gain_pct,
        dollar_gain=dollar_gain, current_range_pct=current_range_pct, current_range_dollars=current_range,
        volume_ratio_1d=volume_ratio_1d, volume_ratio_20d=volume_ratio_20d,
        close_location_pct=close_location_pct(latest), prev_day_gain_pct=prev_day_gain_pct,
    )


def trigger_score(profile: TriggerProfile) -> int:
    score = 0
    if "4pct_breakout" in profile.trigger_tags:
        score += 14
        if profile.day_gain_pct >= 7:
            score += 3
    if "range_expansion" in profile.trigger_tags:
        score += 10
    if "dollar_breakout" in profile.trigger_tags:
        score += 8
    if "9m_volume" in profile.trigger_tags:
        score += 2
    return min(20, score)


def volume_score(profile: TriggerProfile) -> int:
    best_ratio = max(profile.volume_ratio_1d, profile.volume_ratio_20d)
    if best_ratio >= 3.0:
        return 15
    if best_ratio >= 2.0:
        return 12
    if best_ratio >= 1.5:
        return 9
    if best_ratio >= 1.0:
        return 6
    return 0


def setup_score(base: BaseProfile, prev_bar: Bar, cfg: ScreenerConfig) -> int:
    score = 0
    if base.prior_base_days >= 10:
        score += 10
    elif base.prior_base_days >= 5:
        score += 8
    elif base.prior_base_days >= 3:
        score += 6
    elif base.prior_base_days > 0:
        score += 3

    if base.base_width_pct and base.base_width_pct <= 8:
        score += 7
    elif base.base_width_pct <= 12:
        score += 5
    elif base.base_width_pct <= cfg.max_base_width_pct:
        score += 3

    prev_range_pct = (prev_bar.high - prev_bar.low) / prev_bar.close * 100 if prev_bar.close > 0 else 0
    if prev_range_pct <= cfg.narrow_prior_day_range_pct:
        score += 5
    elif prev_bar.close < prev_bar.open:
        score += 4

    if base.volume_dry_up:
        score += 3
    return min(25, score)


def close_quality_score(location_pct: float) -> int:
    if location_pct >= 90:
        return 10
    if location_pct >= 80:
        return 9
    if location_pct >= 70:
        return 7
    if location_pct >= 60:
        return 5
    if location_pct >= 50:
        return 3
    return 0


def risk_distance_score(risk_pct_to_stop: float) -> int:
    if risk_pct_to_stop <= 0:
        return 0
    if risk_pct_to_stop <= 2.5:
        return 15
    if risk_pct_to_stop <= 4.0:
        return 12
    if risk_pct_to_stop <= 6.0:
        return 8
    if risk_pct_to_stop <= 8.0:
        return 5
    if risk_pct_to_stop <= 10.0:
        return 2
    return 0


def failure_filter_score(profile: TriggerProfile, base: BaseProfile, prior_up_streak: int, recent_breakdown: bool, cfg: ScreenerConfig):
    score = 10
    reasons = []
    if prior_up_streak >= 3:
        score -= 4
        reasons.append("prior_3day_runup")
    if recent_breakdown:
        score -= 4
        reasons.append("recent_4pct_breakdown")
    if base.base_width_pct > cfg.max_base_width_pct:
        score -= 3
        reasons.append("wide_prior_base")
    if profile.close_location_pct < 50:
        score -= 2
        reasons.append("weak_close_location")
    return max(0, score), reasons


def market_gate_score(market_gate: str) -> int:
    if market_gate == "allowed":
        return 5
    if market_gate == "neutral":
        return 3
    return 0


def score_to_rating(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "A-"
    if score >= 70:
        return "B"
    if score >= 55:
        return "Watch"
    return "Reject"


def score_to_state(score: int, market_gate: str, hard_rejected: bool) -> str:
    if hard_rejected:
        return "REJECTED"
    if market_gate == "restrictive" and score >= 70:
        return "MANUAL_REVIEW_ONLY"
    if score >= 80:
        return "ACTIONABLE_DAY1"
    if score >= 70:
        return "MANUAL_REVIEW"
    if score >= 55:
        return "WATCH_ONLY"
    return "REJECTED"


def downstream_action(state: str, rating: str) -> str:
    if state == "ACTIONABLE_DAY1":
        return "Send to technical-analyst, then position-sizer if chart review passes."
    if state == "MANUAL_REVIEW":
        return "Manual chart review only; consider reduced risk if upgraded by chart quality."
    if state == "MANUAL_REVIEW_ONLY":
        return "Market gate is restrictive; review for model book or very selective exceptions only."
    if state == "WATCH_ONLY":
        return "Watchlist/model-book candidate; wait for cleaner risk or follow-through."
    return "Do not trade from this screen; retain only for review statistics."


def analyze_symbol(symbol: str, bars: list, cfg: ScreenerConfig) -> dict:
    """Analyze one symbol and return a structured result. bars: most-recent-first Bar list."""
    symbol = normalize_symbol(symbol)
    reject_reasons = []
    if len(bars) < max(25, cfg.min_base_days + 3):
        return {"symbol": symbol, "state": "REJECTED", "rating": "Reject", "setup_score": 0, "reject_reasons": ["insufficient_history"]}

    latest, prev = bars[0], bars[1]
    if latest.close < cfg.min_price:
        reject_reasons.append("below_min_price")
    if latest.volume < cfg.min_volume:
        reject_reasons.append("below_min_volume")

    profile = detect_triggers(bars, cfg)
    executable_tags = [t for t in profile.trigger_tags if t != "9m_volume"]
    if not executable_tags:
        reject_reasons.append("no_momentum_burst_trigger")

    base = detect_base_profile(bars, cfg.min_base_days, cfg.max_base_days, cfg.max_base_width_pct, cfg.max_prior_avg_range_pct)
    prior_up_streak = up_streak_before_trigger(bars)
    recent_breakdown = has_recent_breakdown(bars, cfg.recent_breakdown_lookback, -abs(cfg.breakdown_threshold_pct))

    entry_reference = latest.close
    stop_reference = latest.low
    risk_pct_to_stop = (entry_reference - stop_reference) / entry_reference * 100 if entry_reference else 0.0
    if entry_reference <= stop_reference:
        reject_reasons.append("invalid_stop_reference")
    if risk_pct_to_stop > cfg.max_risk_pct_to_stop:
        reject_reasons.append("risk_too_wide")

    components = {
        "trigger": trigger_score(profile), "volume": volume_score(profile),
        "setup": setup_score(base, prev, cfg), "close_quality": close_quality_score(profile.close_location_pct),
        "risk_distance": risk_distance_score(risk_pct_to_stop), "failure_filters": 0,
        "market_gate": market_gate_score(cfg.market_gate),
    }
    components["failure_filters"], soft_failure_tags = failure_filter_score(profile, base, prior_up_streak, recent_breakdown, cfg)
    composite_score = int(sum(components.values()))
    hard_rejected = bool(reject_reasons)
    rating = score_to_rating(composite_score if not hard_rejected else 0)
    state = score_to_state(composite_score, cfg.market_gate, hard_rejected)

    return {
        "symbol": symbol, "date": latest.date, "state": state, "rating": rating,
        "setup_score": composite_score if not hard_rejected else 0, "raw_setup_score": composite_score,
        "primary_trigger": profile.primary_trigger, "trigger_tags": profile.trigger_tags,
        "day_gain_pct": safe_round(profile.day_gain_pct), "dollar_gain": safe_round(profile.dollar_gain),
        "close": safe_round(latest.close), "prev_close": safe_round(prev.close), "open": safe_round(latest.open),
        "high": safe_round(latest.high), "low": safe_round(latest.low), "volume": latest.volume, "prev_volume": prev.volume,
        "volume_ratio_1d": safe_round(profile.volume_ratio_1d, 2), "volume_ratio_20d": safe_round(profile.volume_ratio_20d, 2),
        "current_range_pct": safe_round(profile.current_range_pct), "current_range_dollars": safe_round(profile.current_range_dollars),
        "close_location_pct": safe_round(profile.close_location_pct), "prior_base_days": base.prior_base_days,
        "base_width_pct": safe_round(base.base_width_pct), "avg_prior_range_pct": safe_round(base.avg_prior_range_pct),
        "volume_dry_up": base.volume_dry_up, "prior_up_streak": prior_up_streak, "recent_4pct_breakdown": recent_breakdown,
        "entry_reference": safe_round(entry_reference), "stop_reference": safe_round(stop_reference),
        "risk_pct_to_stop": safe_round(risk_pct_to_stop), "exit_template": "3_to_5_day_or_abnormal_profit_protection",
        "components": components, "soft_failure_tags": soft_failure_tags, "reject_reasons": reject_reasons,
        "downstream_action": downstream_action(state, rating),
    }
