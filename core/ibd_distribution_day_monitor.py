"""
ibd_distribution_day_monitor.py -- IBD-style Distribution Day detection,
enrichment, counting, and risk classification, ported line-by-line from
claude-trading-skills' ibd-distribution-day-monitor skill
(vendor/claude-trading-skills/skills/ibd-distribution-day-monitor/scripts/
models.py, distribution_day_tracker.py, math_utils.py, risk_classifier.py,
history_utils.py, and the FMP-agnostic parts of ibd_monitor.py,
MIT License, Copyright (c) 2026 TraderMonty).

The skill's own fmp_client.py, _fmp_compat.py, data_loader.py (FMP-specific
price fetching) and report_generator.py (Japanese-language report text)
are NOT ported -- this project already has core/historical_price_service.py
for price history, and core/ibd_distribution_day_service.py (the live
orchestrator) reuses it instead.

All OHLCV history consumed here must be MOST-RECENT-FIRST (history[0] =
latest session) -- this is the opposite convention from core/ftd_detector.py
(which needs chronological/oldest-first), carried over unchanged from the
source skill since it's load-bearing for every index calculation below
(dd_index == age_sessions == position from the evaluation day).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

EPSILON = 1e-12


@dataclass
class DistributionDayRule:
    min_decline_pct: float = -0.002
    expiration_sessions: int = 25
    invalidation_gain_pct: float = 0.05
    invalidation_price_source: str = "high"  # "high" | "close"


@dataclass
class RiskThresholds:
    caution_d25: int = 3
    high_d25: int = 5
    high_d15: int = 3
    high_d5: int = 2
    severe_d25: int = 6
    severe_d15: int = 4
    severe_ma_d25: int = 5  # SEVERE escalation when market_below_ma is True


@dataclass
class DDRecord:
    date: str
    dd_index: int  # = age_sessions, index in effective_history
    age_sessions: int
    close: float
    pct_change: float
    volume: float
    prev_volume: float
    volume_change_pct: float
    high_since: Optional[float] = None
    invalidation_price: Optional[float] = None
    invalidation_date: Optional[str] = None
    invalidation_trigger_price: Optional[float] = None
    invalidation_trigger_source: Optional[str] = None
    expires_in_sessions: Optional[int] = None
    status: str = "active"  # active | expired | invalidated
    removal_reason: Optional[str] = None


_RISK_ORDER = {"NORMAL": 0, "CAUTION": 1, "HIGH": 2, "SEVERE": 3}


# ── math_utils.py ────────────────────────────────────────────────────────

def calc_ema(prices: list, period: int) -> float:
    """Exponential Moving Average from prices, most recent first."""
    if not prices:
        raise ValueError("prices must not be empty")
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(prices) < period:
        return sum(prices) / len(prices)
    prices_rev = prices[::-1]
    sma = sum(prices_rev[:period]) / period
    ema = sma
    k = 2 / (period + 1)
    for p in prices_rev[period:]:
        ema = p * k + ema * (1 - k)
    return ema


def calc_sma(prices: list, period: int) -> float:
    """Simple Moving Average from prices, most recent first."""
    if not prices:
        raise ValueError("prices must not be empty")
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(prices) < period:
        return sum(prices) / len(prices)
    return sum(prices[:period]) / period


# ── distribution_day_tracker.py ─────────────────────────────────────────

def _has_valid_detection_pair(today: dict, yesterday: dict) -> bool:
    """For DD detection: requires close, volume only (high not needed)."""
    for row in (today, yesterday):
        for key in ("close", "volume"):
            v = row.get(key)
            if v is None or v <= 0:
                return False
    return True


def detect_distribution_days(effective_history: list, rule: DistributionDayRule):
    """Detect raw Distribution Days (no enrichment).

    Returns (records, skipped_sessions). Records have only detection-time fields.
    """
    records = []
    skipped = []

    for i in range(len(effective_history) - 1):
        today = effective_history[i]
        yesterday = effective_history[i + 1]
        if not _has_valid_detection_pair(today, yesterday):
            skipped.append({"date": today.get("date"), "reason": "missing_or_invalid_close_volume"})
            continue

        pct_change = today["close"] / yesterday["close"] - 1
        volume_up = today["volume"] > yesterday["volume"]
        if pct_change <= rule.min_decline_pct + EPSILON and volume_up:
            volume_change_pct = today["volume"] / yesterday["volume"] - 1
            records.append(
                DDRecord(
                    date=today["date"],
                    dd_index=i,
                    age_sessions=i,
                    close=today["close"],
                    pct_change=pct_change,
                    volume=today["volume"],
                    prev_volume=yesterday["volume"],
                    volume_change_pct=volume_change_pct,
                )
            )
    return records, skipped


def _find_invalidation_event(effective_history: list, dd_index: int, dd_close: float, rule: DistributionDayRule):
    """Find the first chronological post-DD session where price crosses the
    5% invalidation threshold, within the expiration window."""
    if dd_index <= 0:
        return None

    source = rule.invalidation_price_source
    if source not in {"high", "close"}:
        raise ValueError(f"Unsupported invalidation_price_source: {source}")

    threshold = dd_close * (1 + rule.invalidation_gain_pct)
    min_event_index = max(dd_index - rule.expiration_sessions, 0)

    for event_index in range(dd_index - 1, min_event_index - 1, -1):
        row = effective_history[event_index]
        trigger_value = row.get(source)
        if trigger_value is None or trigger_value <= 0:
            continue
        if trigger_value >= threshold:
            return {
                "date": row["date"],
                "trigger_price": trigger_value,
                "trigger_source": source,
                "elapsed_sessions_since_dd": dd_index - event_index,
            }
    return None


def enrich_records(records: list, effective_history: list, rule: DistributionDayRule) -> list:
    """Fill display, invalidation, expiration, and status fields on each record."""
    for r in records:
        k = r.dd_index

        sessions_on_or_after_dd = effective_history[0 : k + 1]
        valid_highs = [
            row["high"]
            for row in sessions_on_or_after_dd
            if row.get("high") is not None and row["high"] > 0
        ]
        r.high_since = max(valid_highs) if valid_highs else r.close

        r.invalidation_price = r.close * (1 + rule.invalidation_gain_pct)
        ev = _find_invalidation_event(effective_history, k, r.close, rule)
        r.invalidation_date = ev["date"] if ev else None
        r.invalidation_trigger_price = ev["trigger_price"] if ev else None
        r.invalidation_trigger_source = ev["trigger_source"] if ev else None

        if ev is not None:
            r.status = "invalidated"
            r.removal_reason = "invalidated_5pct_gain"
        elif r.age_sessions > rule.expiration_sessions:
            r.status = "expired"
            r.removal_reason = "expired_25_sessions"
        else:
            r.status = "active"
            r.removal_reason = None

        r.expires_in_sessions = max(rule.expiration_sessions - r.age_sessions, 0)
    return records


def count_active_in_window(records: list, max_age_sessions: int) -> int:
    """Count active records within elapsed-session window (age <= max_age_sessions)."""
    return sum(1 for r in records if r.status == "active" and r.age_sessions <= max_age_sessions)


# ── risk_classifier.py ──────────────────────────────────────────────────

def classify_risk(d5: int, d15: int, d25: int, market_below_ma, thresholds: RiskThresholds) -> str:
    """Classify a single index's risk level.

    market_below_ma may be True | False | None. None means MA could not be
    computed (insufficient data); SEVERE escalation is skipped in that case.
    """
    if d25 >= thresholds.severe_d25 or d15 >= thresholds.severe_d15:
        return "SEVERE"
    if market_below_ma is True and d25 >= thresholds.severe_ma_d25:
        return "SEVERE"
    if d25 >= thresholds.high_d25 or d15 >= thresholds.high_d15 or d5 >= thresholds.high_d5:
        return "HIGH"
    if d25 >= thresholds.caution_d25:
        return "CAUTION"
    return "NORMAL"


def combine_index_risks(risk_by_symbol: dict) -> str:
    """Combine per-index risks into an overall risk level (TQQQ-aware,
    QQQ-weighted). risk_by_symbol: {"QQQ": "HIGH", "SPY": "NORMAL", ...}."""
    if any(risk == "SEVERE" for risk in risk_by_symbol.values()):
        return "SEVERE"

    qqq = risk_by_symbol.get("QQQ")
    spy = risk_by_symbol.get("SPY")

    if qqq == "HIGH":
        return "HIGH"

    if qqq and spy:
        if qqq == "NORMAL" and spy == "HIGH":
            return "HIGH"
        if qqq == "CAUTION" and spy in ("CAUTION", "HIGH"):
            return "HIGH"

    return max(risk_by_symbol.values(), key=lambda lv: _RISK_ORDER[lv])


# ── history_utils.py ─────────────────────────────────────────────────────

def prepare_effective_history(history: list, as_of, required_min_sessions: int):
    """Rebase history so index 0 is the evaluation session.

    Args:
        history: Most-recent-first list of OHLCV dicts (history[0] = latest).
        as_of: ISO date string or None. If None, evaluation session = history[0].
        required_min_sessions: If the resulting effective_history has fewer
            rows, an "insufficient_lookback" audit flag is appended.
    """
    if not history:
        raise ValueError("history is empty; cannot prepare effective_history")

    audit = {"as_of_resolved": None, "sessions_available": 0, "audit_flags": []}

    if as_of is None:
        effective = history
        audit["as_of_resolved"] = history[0]["date"]
    else:
        idx = next((i for i, row in enumerate(history) if row.get("date") == as_of), None)
        if idx is None:
            raise ValueError(f"as_of {as_of} not found in loaded history")
        effective = history[idx:]
        audit["as_of_resolved"] = as_of

    audit["sessions_available"] = len(effective)
    if len(effective) < required_min_sessions:
        audit["audit_flags"].append("insufficient_lookback")
    return effective, audit


# ── ibd_monitor.py (FMP-agnostic parts only) ─────────────────────────────

def _compute_ma_filters(effective_history: list, ema_period: int = 21, sma_period: int = 50):
    """Compute close_above_21ema, close_above_50sma, market_below_21ema_or_50ma."""
    audit_flags = []
    if not effective_history:
        return {
            "close_above_21ema": None,
            "close_above_50sma": None,
            "market_below_21ema_or_50ma": None,
        }, audit_flags

    closes = [row["close"] for row in effective_history]
    today_close = closes[0]

    def _ma_or_none(fn, period):
        if len(closes) < period:
            return None
        try:
            return fn(closes, period)
        except ValueError:
            return None

    ema_val = _ma_or_none(calc_ema, ema_period)
    sma_val = _ma_or_none(calc_sma, sma_period)

    close_above_ema = (today_close > ema_val) if ema_val is not None else None
    close_above_sma = (today_close > sma_val) if sma_val is not None else None

    if close_above_ema is None or close_above_sma is None:
        audit_flags.append("insufficient_data_for_moving_average")
        market_below = None
    else:
        market_below = (not close_above_ema) and (not close_above_sma)

    return {
        "close_above_21ema": close_above_ema,
        "close_above_50sma": close_above_sma,
        "market_below_21ema_or_50ma": market_below,
    }, audit_flags


def analyze_index(
    symbol: str,
    history: list,
    rule: DistributionDayRule,
    thresholds: RiskThresholds,
    as_of: Optional[str] = None,
    required_min_sessions: int = 80,
) -> dict:
    """Run the full per-index Distribution-Day pipeline.

    Args:
        symbol: Index/ETF ticker (e.g. "SPY", "QQQ").
        history: Most-recent-first OHLCV dicts (history[0] = latest session).
        as_of: ISO date to evaluate as of, or None for the latest session.
    """
    effective_history, hist_audit = prepare_effective_history(history, as_of, required_min_sessions)
    audit_flags = list(hist_audit.get("audit_flags", []))

    raw_records, skipped = detect_distribution_days(effective_history, rule)
    records = enrich_records(raw_records, effective_history, rule)

    active = [r for r in records if r.status == "active"]
    removed = [r for r in records if r.status != "active"]

    d5 = count_active_in_window(records, 5)
    d15 = count_active_in_window(records, 15)
    d25 = count_active_in_window(records, 25)

    trend_filters, ma_flags = _compute_ma_filters(effective_history)
    audit_flags.extend(ma_flags)

    market_below = trend_filters.get("market_below_21ema_or_50ma")
    risk = classify_risk(d5, d15, d25, market_below, thresholds)

    today_is_dd = any(r.dd_index == 0 and r.status == "active" for r in records)

    return {
        "symbol": symbol,
        "is_distribution_day_today": today_is_dd,
        "d5_count": d5,
        "d15_count": d15,
        "d25_count": d25,
        "active_distribution_days": active,
        "removed_distribution_days": removed,
        "risk_level": risk,
        "trend_filters": trend_filters,
        "skipped_sessions": skipped,
        "audit_flags": audit_flags,
    }
