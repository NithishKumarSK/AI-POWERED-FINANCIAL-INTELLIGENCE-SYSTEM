"""
stockbee_exhaustion_hammer_screener.py -- Stockbee-style selling-exhaustion
hammer detection (prior momentum + pullback + undercut/reclaim + hammer
candle geometry + risk-to-stop -> composite score/rating/state), ported
from claude-trading-skills' stockbee-exhaustion-hammer-screener skill
(vendor/claude-trading-skills/skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py,
MIT License, Copyright (c) 2026 TraderMonty).

Only the per-symbol ANALYSIS pipeline (analyze_symbol + its profile/score
helpers) is ported -- the skill's own FMP-universe-scan input mode
("Mode A", via company-screener, confirmed premium-gated elsewhere this
session) and its report-generation code were not. This project already
knows which symbol it's analyzing;
core/stockbee_exhaustion_hammer_service.py (the live orchestrator) reuses
historical_price_service.py for price history instead.

The `profile_row` parameter (FMP market-cap/institutional-ownership
metadata) is accepted but the live orchestrator always passes None --
no free source for that data; quality_score()/detect_quality_profile()
already degrade gracefully when it's missing (same handling as the
source skill's own offline mode).

All Bar lists are MOST-RECENT-FIRST, same convention as
core/pead_screener.py and core/ibd_distribution_day_monitor.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class HammerProfile:
    day_range: float
    day_range_pct: float
    body: float
    body_pct_of_range: float
    lower_wick: float
    lower_wick_pct_of_range: float
    upper_wick: float
    upper_wick_pct_of_range: float
    lower_wick_to_body: float
    close_location_pct: float
    recovery_from_low_pct: float
    day_gain_pct: float
    dollar_gain: float
    green_close: bool
    hammer_tags: list = field(default_factory=list)
    primary_trigger: str = ""


@dataclass
class PullbackProfile:
    recent_high: float
    recent_high_date: str
    days_since_recent_high: int
    pullback_pct_from_high: float
    prior_low: float
    prior_low_date: str
    undercut_reclaim: bool
    low_undercut_pct: float
    down_days_10: int
    lower_closes_5: int
    consecutive_down_closes: int
    below_10dma_pct: float
    above_50dma: bool
    return_20d_pct: float
    return_60d_pct: float


@dataclass
class QualityProfile:
    avg_volume_20d: float
    avg_dollar_volume_20d: float
    volume_ratio_1d: float
    volume_ratio_20d: float
    market_cap: float
    institutional_ownership_pct: float
    mutual_fund_holders: int
    institutional_holders: int


@dataclass
class ScreenerConfig:
    """Faithful port of parse_arguments()'s defaults (Mode A/B/C input
    args excluded -- only the per-symbol analysis thresholds remain)."""
    min_price: float = 20.0
    min_volume: int = 100_000
    min_avg_dollar_volume: float = 20_000_000
    min_market_cap: float = 2_000_000_000
    recent_high_lookback: int = 40
    min_days_since_high: int = 3
    max_days_since_high: int = 30
    min_pullback_pct: float = 6.0
    max_pullback_pct: float = 35.0
    undercut_lookback: int = 5
    require_undercut_reclaim: bool = False
    min_lower_wick_pct: float = 40.0
    max_body_pct: float = 35.0
    max_upper_wick_pct: float = 35.0
    min_close_location_pct: float = 60.0
    min_lower_wick_to_body: float = 1.5
    min_recovery_from_low_pct: float = 2.0
    max_risk_pct_to_stop: float = 12.0
    stop_buffer_pct: float = 0.10
    market_gate: str = "neutral"  # "allowed" | "neutral" | "restrictive"


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


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


def simple_moving_average(bars: list, start: int, length: int) -> float:
    window = bars[start : start + length]
    return average([bar.close for bar in window]) if window else 0.0


def consecutive_down_closes_before_latest(bars: list, max_days: int = 7) -> int:
    streak = 0
    for idx in range(1, min(len(bars) - 1, max_days) + 1):
        if bars[idx].close < bars[idx + 1].close:
            streak += 1
        else:
            break
    return streak


def detect_hammer_profile(bars: list, cfg: ScreenerConfig) -> HammerProfile:
    latest, prev = bars[0], bars[1]
    day_range = latest.high - latest.low
    if day_range <= 0:
        day_range = 0.000001
    body = abs(latest.close - latest.open)
    lower_wick = max(0.0, min(latest.open, latest.close) - latest.low)
    upper_wick = max(0.0, latest.high - max(latest.open, latest.close))
    close_loc = close_location_pct(latest)
    lower_wick_to_body = lower_wick / body if body > 0 else 999.0
    recovery_from_low = pct_change(latest.close, latest.low)
    day_gain = pct_change(latest.close, prev.close)
    dollar_gain = latest.close - latest.open

    lower_pct = lower_wick / day_range * 100.0
    body_pct = body / day_range * 100.0
    upper_pct = upper_wick / day_range * 100.0
    day_range_pct = day_range / latest.close * 100.0 if latest.close > 0 else 0.0

    tags = []
    if lower_pct >= cfg.min_lower_wick_pct:
        tags.append("long_lower_wick")
    if body_pct <= cfg.max_body_pct:
        tags.append("small_body")
    if close_loc >= cfg.min_close_location_pct:
        tags.append("strong_close_location")
    if lower_wick_to_body >= cfg.min_lower_wick_to_body:
        tags.append("wick_body_asymmetry")
    if recovery_from_low >= cfg.min_recovery_from_low_pct:
        tags.append("recovered_from_low")
    if latest.close >= latest.open:
        tags.append("green_or_flat_close")
    if upper_pct <= cfg.max_upper_wick_pct:
        tags.append("controlled_upper_wick")

    primary = "selling_exhaustion_hammer"
    if {"long_lower_wick", "small_body", "strong_close_location"}.issubset(set(tags)):
        primary = "confirmed_exhaustion_hammer"

    return HammerProfile(
        day_range=day_range, day_range_pct=day_range_pct, body=body, body_pct_of_range=body_pct,
        lower_wick=lower_wick, lower_wick_pct_of_range=lower_pct, upper_wick=upper_wick,
        upper_wick_pct_of_range=upper_pct, lower_wick_to_body=lower_wick_to_body,
        close_location_pct=close_loc, recovery_from_low_pct=recovery_from_low, day_gain_pct=day_gain,
        dollar_gain=dollar_gain, green_close=latest.close >= latest.open, hammer_tags=tags, primary_trigger=primary,
    )


def detect_pullback_profile(bars: list, cfg: ScreenerConfig) -> PullbackProfile:
    latest = bars[0]
    prior_window = bars[1 : 1 + cfg.recent_high_lookback]
    if not prior_window:
        return PullbackProfile(0, "", 0, 0, 0, "", False, 0, 0, 0, 0, 0, False, 0, 0)

    recent_high_bar = max(prior_window, key=lambda bar: bar.high)
    days_since_high = bars.index(recent_high_bar)
    pullback_pct = pct_change(latest.close, recent_high_bar.high)

    low_window = bars[1 : 1 + cfg.undercut_lookback]
    prior_low_bar = min(low_window, key=lambda bar: bar.low) if low_window else bars[1]
    prior_low = prior_low_bar.low
    undercut = latest.low < prior_low
    reclaim = latest.close > prior_low
    low_undercut_pct = pct_change(latest.low, prior_low) if prior_low > 0 else 0.0

    prior_10 = bars[1:11]
    down_days_10 = sum(1 for bar in prior_10 if bar.close < bar.open)
    lower_closes_5 = 0
    for idx in range(1, min(len(bars) - 1, 6)):
        if bars[idx].close < bars[idx + 1].close:
            lower_closes_5 += 1
    down_streak = consecutive_down_closes_before_latest(bars)

    ma10 = simple_moving_average(bars, 1, min(10, len(bars) - 1))
    ma50 = simple_moving_average(bars, 0, min(50, len(bars)))
    below_10dma_pct = pct_change(latest.close, ma10) if ma10 > 0 else 0.0
    above_50dma = latest.close >= ma50 if ma50 > 0 else False

    return_20d = pct_change(bars[1].close, bars[21].close) if len(bars) > 21 else 0.0
    return_60d = pct_change(bars[1].close, bars[61].close) if len(bars) > 61 else 0.0

    return PullbackProfile(
        recent_high=recent_high_bar.high, recent_high_date=recent_high_bar.date,
        days_since_recent_high=days_since_high, pullback_pct_from_high=pullback_pct,
        prior_low=prior_low, prior_low_date=prior_low_bar.date, undercut_reclaim=undercut and reclaim,
        low_undercut_pct=low_undercut_pct, down_days_10=down_days_10, lower_closes_5=lower_closes_5,
        consecutive_down_closes=down_streak, below_10dma_pct=below_10dma_pct, above_50dma=above_50dma,
        return_20d_pct=return_20d, return_60d_pct=return_60d,
    )


def detect_quality_profile(bars: list, profile_row: Optional[dict], cfg: ScreenerConfig) -> QualityProfile:
    latest, prev = bars[0], bars[1]
    avg_volume_20d = average([float(bar.volume) for bar in bars[1:21]])
    avg_dollar_volume_20d = average([bar.close * float(bar.volume) for bar in bars[1:21]])
    volume_ratio_1d = latest.volume / prev.volume if prev.volume > 0 else 0.0
    volume_ratio_20d = latest.volume / avg_volume_20d if avg_volume_20d > 0 else 0.0
    row = profile_row or {}
    market_cap = to_float(row.get("marketCap") or row.get("mktCap") or row.get("market_cap"))
    institutional_ownership_pct = to_float(
        row.get("institutionalOwnershipPct") or row.get("institutionalOwnership") or row.get("institutional_ownership_pct")
    )
    mutual_fund_holders = to_int(row.get("mutualFundHolders") or row.get("mutual_fund_holders") or row.get("fundHolderCount"))
    institutional_holders = to_int(row.get("institutionalHolders") or row.get("institutional_holders") or row.get("institutionalHolderCount"))
    return QualityProfile(
        avg_volume_20d=avg_volume_20d, avg_dollar_volume_20d=avg_dollar_volume_20d,
        volume_ratio_1d=volume_ratio_1d, volume_ratio_20d=volume_ratio_20d, market_cap=market_cap,
        institutional_ownership_pct=institutional_ownership_pct, mutual_fund_holders=mutual_fund_holders,
        institutional_holders=institutional_holders,
    )


def quality_score(quality: QualityProfile, latest: Bar, cfg: ScreenerConfig) -> int:
    score = 0
    if latest.close >= cfg.min_price * 2:
        score += 4
    elif latest.close >= cfg.min_price:
        score += 3

    if quality.avg_dollar_volume_20d >= cfg.min_avg_dollar_volume * 3:
        score += 6
    elif quality.avg_dollar_volume_20d >= cfg.min_avg_dollar_volume:
        score += 5
    elif latest.volume >= cfg.min_volume:
        score += 2

    if quality.market_cap >= cfg.min_market_cap * 5:
        score += 5
    elif quality.market_cap >= cfg.min_market_cap:
        score += 4
    elif quality.market_cap <= 0:
        score += 2  # unknown profile should not make offline mode unusable

    if quality.mutual_fund_holders >= 1000 or quality.institutional_holders >= 1000:
        score += 3
    elif quality.institutional_ownership_pct >= 40:
        score += 2

    if quality.avg_volume_20d >= cfg.min_volume:
        score += 2
    return min(20, score)


def prior_momentum_score(pullback: PullbackProfile, cfg: ScreenerConfig) -> int:
    score = 0
    if cfg.min_days_since_high <= pullback.days_since_recent_high <= cfg.max_days_since_high:
        score += 5
    elif pullback.days_since_recent_high <= cfg.recent_high_lookback:
        score += 2

    if pullback.return_60d_pct >= 30:
        score += 5
    elif pullback.return_60d_pct >= 15:
        score += 4
    elif pullback.return_20d_pct >= 10:
        score += 3

    if pullback.above_50dma:
        score += 3
    if pullback.recent_high > 0:
        score += 2
    return min(15, score)


def pullback_exhaustion_score(pullback: PullbackProfile, quality: QualityProfile, cfg: ScreenerConfig) -> int:
    score = 0
    depth = abs(pullback.pullback_pct_from_high)
    if cfg.min_pullback_pct <= depth <= min(25.0, cfg.max_pullback_pct):
        score += 6
    elif depth <= cfg.max_pullback_pct:
        score += 4

    if pullback.undercut_reclaim:
        score += 6
    elif pullback.low_undercut_pct < 0:
        score += 3

    if pullback.down_days_10 >= 5:
        score += 3
    elif pullback.down_days_10 >= 3:
        score += 2

    if pullback.lower_closes_5 >= 3 or pullback.consecutive_down_closes >= 2:
        score += 2

    if quality.volume_ratio_20d >= 1.5:
        score += 3
    elif quality.volume_ratio_20d >= 1.0:
        score += 2
    return min(20, score)


def hammer_geometry_score(hammer: HammerProfile, cfg: ScreenerConfig) -> int:
    score = 0
    if hammer.lower_wick_pct_of_range >= 60:
        score += 8
    elif hammer.lower_wick_pct_of_range >= cfg.min_lower_wick_pct:
        score += 6

    if hammer.body_pct_of_range <= 20:
        score += 5
    elif hammer.body_pct_of_range <= cfg.max_body_pct:
        score += 4

    if hammer.close_location_pct >= 75:
        score += 5
    elif hammer.close_location_pct >= cfg.min_close_location_pct:
        score += 4

    if hammer.lower_wick_to_body >= 3:
        score += 3
    elif hammer.lower_wick_to_body >= cfg.min_lower_wick_to_body:
        score += 2

    if hammer.recovery_from_low_pct >= cfg.min_recovery_from_low_pct * 2:
        score += 2
    elif hammer.recovery_from_low_pct >= cfg.min_recovery_from_low_pct:
        score += 1

    if hammer.green_close:
        score += 1
    if hammer.upper_wick_pct_of_range <= cfg.max_upper_wick_pct:
        score += 1
    return min(25, score)


def risk_distance_score(risk_pct_to_stop: float) -> int:
    if risk_pct_to_stop <= 0:
        return 0
    if risk_pct_to_stop <= 3.0:
        return 15
    if risk_pct_to_stop <= 5.0:
        return 12
    if risk_pct_to_stop <= 7.5:
        return 9
    if risk_pct_to_stop <= 10.0:
        return 6
    if risk_pct_to_stop <= 12.0:
        return 3
    return 0


def market_gate_score(market_gate: str) -> int:
    if market_gate == "allowed":
        return 5
    if market_gate == "neutral":
        return 3
    return 0


def score_to_rating(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 82:
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
    if score >= 82:
        return "ACTIONABLE_CLOSE_BUY"
    if score >= 70:
        return "MANUAL_REVIEW"
    if score >= 55:
        return "WATCH_TOMORROW"
    return "REJECTED"


def detect_soft_failure_tags(hammer: HammerProfile, pullback: PullbackProfile, quality: QualityProfile, risk_pct_to_stop: float, cfg: ScreenerConfig) -> list:
    tags = []
    if not pullback.undercut_reclaim:
        tags.append("no_undercut_reclaim")
    if abs(pullback.pullback_pct_from_high) > 25:
        tags.append("deep_pullback")
    if pullback.days_since_recent_high > cfg.max_days_since_high:
        tags.append("stale_high")
    if quality.volume_ratio_20d < 0.8:
        tags.append("weak_volume_confirmation")
    if hammer.close_location_pct < 70:
        tags.append("moderate_close_location")
    if hammer.day_gain_pct < -3:
        tags.append("still_down_big_on_day")
    if risk_pct_to_stop >= 8:
        tags.append("wide_risk")
    return tags


def downstream_action(state: str, rating: str) -> str:
    if state == "ACTIONABLE_CLOSE_BUY":
        return "Near-close candidate. Manually validate chart, news/earnings risk, and size from entry_reference to stop_reference before any order."
    if state == "MANUAL_REVIEW":
        return "Manual chart review; consider next-day hammer-high trigger or reduced risk only if upgraded."
    if state == "MANUAL_REVIEW_ONLY":
        return "Market gate is restrictive; study/model-book only unless a documented exception is approved."
    if state == "WATCH_TOMORROW":
        return "Watch for next-day follow-through, hammer-high reclaim, or tighter risk."
    return "Do not trade from this screen; retain only for review statistics."


def normalize_symbol(value: str) -> str:
    return (value or "").strip().upper()


def analyze_symbol(symbol: str, bars: list, cfg: ScreenerConfig, profile_row: Optional[dict] = None) -> dict:
    """Analyze one symbol and return a structured result. bars: most-recent-first Bar list."""
    symbol = normalize_symbol(symbol)
    reject_reasons = []
    min_history = max(30, cfg.recent_high_lookback + 2, cfg.undercut_lookback + 2)
    if len(bars) < min_history:
        return {"symbol": symbol, "state": "REJECTED", "rating": "Reject", "setup_score": 0, "reject_reasons": ["insufficient_history"]}

    latest, prev = bars[0], bars[1]
    if latest.close < cfg.min_price:
        reject_reasons.append("below_min_price")
    if latest.volume < cfg.min_volume:
        reject_reasons.append("below_min_volume")

    hammer = detect_hammer_profile(bars, cfg)
    pullback = detect_pullback_profile(bars, cfg)
    quality = detect_quality_profile(bars, profile_row, cfg)

    if quality.avg_dollar_volume_20d < cfg.min_avg_dollar_volume:
        reject_reasons.append("below_min_avg_dollar_volume")
    if quality.market_cap > 0 and quality.market_cap < cfg.min_market_cap:
        reject_reasons.append("below_min_market_cap")

    if hammer.lower_wick_pct_of_range < cfg.min_lower_wick_pct:
        reject_reasons.append("lower_wick_too_small")
    if hammer.body_pct_of_range > cfg.max_body_pct:
        reject_reasons.append("body_too_large")
    if hammer.close_location_pct < cfg.min_close_location_pct:
        reject_reasons.append("weak_close_location")
    if hammer.lower_wick_to_body < cfg.min_lower_wick_to_body:
        reject_reasons.append("weak_wick_body_asymmetry")
    if hammer.recovery_from_low_pct < cfg.min_recovery_from_low_pct:
        reject_reasons.append("insufficient_recovery_from_low")

    pullback_depth = abs(pullback.pullback_pct_from_high)
    if pullback_depth < cfg.min_pullback_pct:
        reject_reasons.append("pullback_too_shallow")
    if pullback_depth > cfg.max_pullback_pct:
        reject_reasons.append("pullback_too_deep")
    if pullback.days_since_recent_high < cfg.min_days_since_high:
        reject_reasons.append("too_close_to_recent_high")
    if pullback.days_since_recent_high > cfg.max_days_since_high:
        reject_reasons.append("recent_high_too_stale")
    if cfg.require_undercut_reclaim and not pullback.undercut_reclaim:
        reject_reasons.append("missing_undercut_reclaim")

    entry_reference = latest.close
    stop_reference = latest.low * (1.0 - cfg.stop_buffer_pct / 100.0)
    risk_pct_to_stop = (entry_reference - stop_reference) / entry_reference * 100 if entry_reference else 0.0
    if entry_reference <= stop_reference:
        reject_reasons.append("invalid_stop_reference")
    if risk_pct_to_stop > cfg.max_risk_pct_to_stop:
        reject_reasons.append("risk_too_wide")

    components = {
        "quality": quality_score(quality, latest, cfg),
        "prior_momentum": prior_momentum_score(pullback, cfg),
        "pullback_exhaustion": pullback_exhaustion_score(pullback, quality, cfg),
        "hammer_geometry": hammer_geometry_score(hammer, cfg),
        "risk_distance": risk_distance_score(risk_pct_to_stop),
        "market_gate": market_gate_score(cfg.market_gate),
    }
    composite_score = int(sum(components.values()))
    hard_rejected = bool(reject_reasons)
    rating = score_to_rating(composite_score if not hard_rejected else 0)
    state = score_to_state(composite_score, cfg.market_gate, hard_rejected)

    trigger_tags = sorted(set(hammer.hammer_tags + ["selling_exhaustion", "pullback_reversal"]))
    if pullback.undercut_reclaim:
        trigger_tags.append("undercut_reclaim")
    if quality.volume_ratio_20d >= 1.5:
        trigger_tags.append("volume_shock")

    return {
        "symbol": symbol, "date": latest.date, "state": state, "rating": rating,
        "setup_score": composite_score if not hard_rejected else 0, "raw_setup_score": composite_score,
        "primary_trigger": hammer.primary_trigger, "trigger_tags": trigger_tags,
        "day_gain_pct": safe_round(hammer.day_gain_pct), "dollar_gain": safe_round(hammer.dollar_gain),
        "close": safe_round(latest.close), "prev_close": safe_round(prev.close), "open": safe_round(latest.open),
        "high": safe_round(latest.high), "low": safe_round(latest.low), "volume": latest.volume, "prev_volume": prev.volume,
        "avg_volume_20d": safe_round(quality.avg_volume_20d, 0), "avg_dollar_volume_20d": safe_round(quality.avg_dollar_volume_20d, 0),
        "volume_ratio_1d": safe_round(quality.volume_ratio_1d, 2), "volume_ratio_20d": safe_round(quality.volume_ratio_20d, 2),
        "current_range_pct": safe_round(hammer.day_range_pct), "current_range_dollars": safe_round(hammer.day_range),
        "close_location_pct": safe_round(hammer.close_location_pct), "body_pct_of_range": safe_round(hammer.body_pct_of_range),
        "lower_wick_pct_of_range": safe_round(hammer.lower_wick_pct_of_range), "upper_wick_pct_of_range": safe_round(hammer.upper_wick_pct_of_range),
        "lower_wick_to_body": safe_round(hammer.lower_wick_to_body, 2), "recovery_from_low_pct": safe_round(hammer.recovery_from_low_pct),
        "recent_high": safe_round(pullback.recent_high), "recent_high_date": pullback.recent_high_date,
        "days_since_recent_high": pullback.days_since_recent_high, "pullback_pct_from_high": safe_round(pullback.pullback_pct_from_high),
        "prior_low": safe_round(pullback.prior_low), "prior_low_date": pullback.prior_low_date,
        "undercut_reclaim": pullback.undercut_reclaim, "low_undercut_pct": safe_round(pullback.low_undercut_pct),
        "down_days_10": pullback.down_days_10, "lower_closes_5": pullback.lower_closes_5,
        "consecutive_down_closes": pullback.consecutive_down_closes, "below_10dma_pct": safe_round(pullback.below_10dma_pct),
        "above_50dma": pullback.above_50dma, "return_20d_pct": safe_round(pullback.return_20d_pct),
        "return_60d_pct": safe_round(pullback.return_60d_pct), "market_cap": safe_round(quality.market_cap, 0),
        "institutional_ownership_pct": safe_round(quality.institutional_ownership_pct),
        "mutual_fund_holders": quality.mutual_fund_holders, "institutional_holders": quality.institutional_holders,
        "entry_reference": safe_round(entry_reference), "stop_reference": safe_round(stop_reference),
        "risk_pct_to_stop": safe_round(risk_pct_to_stop),
        "exit_template": "low_of_day_stop_then_3_to_5_day_follow_through_review", "components": components,
        "soft_failure_tags": detect_soft_failure_tags(hammer, pullback, quality, risk_pct_to_stop, cfg),
        "reject_reasons": reject_reasons, "downstream_action": downstream_action(state, rating),
    }
