"""
Tests for core/ibd_distribution_day_monitor.py -- the ported
claude-trading-skills ibd-distribution-day-monitor skill. Synthetic data
only, no network. All histories here are MOST-RECENT-FIRST, matching the
module's own convention (the opposite of core/ftd_detector.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _bar(date, close, volume, high=None):
    return {"date": date, "close": float(close), "high": float(high if high is not None else close), "volume": float(volume)}


def _flat_history(n, start_price=100.0, volume=1000, start_date="2026-01-01"):
    import datetime as dt
    d0 = dt.date.fromisoformat(start_date)
    chrono = [_bar((d0 + dt.timedelta(days=i)).isoformat(), start_price, volume) for i in range(n)]
    return list(reversed(chrono))  # most-recent-first


# ── detect_distribution_days ─────────────────────────────────────────────

def test_detect_distribution_days_requires_decline_and_higher_volume():
    from ibd_distribution_day_monitor import DistributionDayRule, detect_distribution_days

    # Chronological: day0(100,1000) day1(99,900) day2(98,1500) day3(99,1600) day4(97,2000)
    # day1: decline but volume DOWN -- not a DD.
    # day2: decline (-1.01%) + volume up (1500>900) -- DD.
    # day3: price UP -- not a DD.
    # day4: decline (-2.02%) + volume up (2000>1600) -- DD.
    chrono = [
        _bar("2026-01-01", 100, 1000),
        _bar("2026-01-02", 99, 900),
        _bar("2026-01-03", 98, 1500),
        _bar("2026-01-04", 99, 1600),
        _bar("2026-01-05", 97, 2000),
    ]
    mrf = list(reversed(chrono))  # history[0] = day4 (latest)

    records, skipped = detect_distribution_days(mrf, DistributionDayRule())
    dd_dates = sorted(r.date for r in records)
    assert dd_dates == ["2026-01-03", "2026-01-05"]
    assert skipped == []


def test_detect_distribution_days_skips_missing_volume():
    from ibd_distribution_day_monitor import DistributionDayRule, detect_distribution_days

    mrf = [
        {"date": "2026-01-02", "close": 97.0, "high": 97.0, "volume": 2000.0},
        {"date": "2026-01-01", "close": 100.0, "high": 100.0, "volume": None},
    ]
    records, skipped = detect_distribution_days(mrf, DistributionDayRule())
    assert records == []
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "missing_or_invalid_close_volume"


# ── enrich_records (invalidation / expiration / active) ─────────────────

def test_enrich_records_invalidates_on_5pct_post_dd_gain():
    from ibd_distribution_day_monitor import DistributionDayRule, detect_distribution_days, enrich_records

    # Chronological: day0(100,1000) -> day1: DD (close 97, vol 2000, decline+vol-up)
    # -> day2: recovers to high=104 (>= 97*1.05=101.85) -- invalidates the DD.
    chrono = [
        _bar("2026-01-01", 100, 1000),
        _bar("2026-01-02", 97, 2000),
        _bar("2026-01-03", 103, 1500, high=104),
    ]
    mrf = list(reversed(chrono))  # history[0]=day2(latest), [1]=day1(DD), [2]=day0

    rule = DistributionDayRule()
    records, _ = detect_distribution_days(mrf, rule)
    assert len(records) == 1
    enriched = enrich_records(records, mrf, rule)
    assert enriched[0].status == "invalidated"
    assert enriched[0].removal_reason == "invalidated_5pct_gain"
    assert enriched[0].invalidation_date == "2026-01-03"


def test_enrich_records_expires_after_window_without_invalidation():
    from ibd_distribution_day_monitor import DistributionDayRule, detect_distribution_days, enrich_records

    # One DD at the oldest position, followed by 27 flat (no-recovery) sessions
    # -- age_sessions (27) > expiration_sessions (25), no 5% gain anywhere -- expired.
    import datetime as dt
    d0 = dt.date(2026, 1, 1)
    chrono = [_bar(d0.isoformat(), 100, 1000), _bar((d0 + dt.timedelta(days=1)).isoformat(), 97, 2000)]
    for i in range(2, 29):
        chrono.append(_bar((d0 + dt.timedelta(days=i)).isoformat(), 97.5, 1000))  # flat, well under 97*1.05
    mrf = list(reversed(chrono))

    rule = DistributionDayRule()
    records, _ = detect_distribution_days(mrf, rule)
    assert len(records) == 1
    enriched = enrich_records(records, mrf, rule)
    assert enriched[0].age_sessions == 27
    assert enriched[0].status == "expired"
    assert enriched[0].removal_reason == "expired_25_sessions"


def test_enrich_records_active_within_window_no_recovery():
    from ibd_distribution_day_monitor import DistributionDayRule, detect_distribution_days, enrich_records

    chrono = [_bar("2026-01-01", 100, 1000), _bar("2026-01-02", 97, 2000), _bar("2026-01-03", 97.2, 1000)]
    mrf = list(reversed(chrono))
    rule = DistributionDayRule()
    records, _ = detect_distribution_days(mrf, rule)
    enriched = enrich_records(records, mrf, rule)
    assert enriched[0].status == "active"
    assert enriched[0].age_sessions == 1


def test_count_active_in_window():
    from ibd_distribution_day_monitor import DDRecord, count_active_in_window

    records = [
        DDRecord(date="d1", dd_index=0, age_sessions=0, close=1, pct_change=-0.01, volume=1, prev_volume=1, volume_change_pct=0, status="active"),
        DDRecord(date="d2", dd_index=10, age_sessions=10, close=1, pct_change=-0.01, volume=1, prev_volume=1, volume_change_pct=0, status="active"),
        DDRecord(date="d3", dd_index=20, age_sessions=20, close=1, pct_change=-0.01, volume=1, prev_volume=1, volume_change_pct=0, status="expired"),
    ]
    assert count_active_in_window(records, 5) == 1
    assert count_active_in_window(records, 15) == 2
    assert count_active_in_window(records, 25) == 2  # expired one excluded regardless of age


# ── math_utils ────────────────────────────────────────────────────────────

def test_calc_sma_most_recent_first():
    from ibd_distribution_day_monitor import calc_sma
    assert calc_sma([5, 4, 3, 2, 1], 3) == 4.0  # avg of [5,4,3]


def test_calc_ema_falls_back_to_average_when_insufficient_data():
    from ibd_distribution_day_monitor import calc_ema
    assert calc_ema([10, 20], 5) == 15.0


# ── risk_classifier ────────────────────────────────────────────────────────

def test_classify_risk_normal_caution_high_severe_thresholds():
    from ibd_distribution_day_monitor import RiskThresholds, classify_risk
    t = RiskThresholds()
    assert classify_risk(0, 0, 0, False, t) == "NORMAL"
    assert classify_risk(0, 0, 3, False, t) == "CAUTION"
    assert classify_risk(2, 0, 0, False, t) == "HIGH"       # high_d5
    assert classify_risk(0, 0, 5, False, t) == "HIGH"       # high_d25
    assert classify_risk(0, 0, 6, False, t) == "SEVERE"     # severe_d25
    assert classify_risk(0, 4, 0, False, t) == "SEVERE"     # severe_d15


def test_classify_risk_market_below_ma_escalates_to_severe():
    from ibd_distribution_day_monitor import RiskThresholds, classify_risk
    t = RiskThresholds()
    # d25=5 alone is only HIGH, but with market_below_ma=True and d25>=severe_ma_d25(5) -> SEVERE
    assert classify_risk(0, 0, 5, True, t) == "SEVERE"
    # None (MA unknown) must NOT trigger the escalation
    assert classify_risk(0, 0, 5, None, t) == "HIGH"


def test_combine_index_risks_qqq_weighted():
    from ibd_distribution_day_monitor import combine_index_risks
    assert combine_index_risks({"QQQ": "NORMAL", "SPY": "HIGH"}) == "HIGH"
    assert combine_index_risks({"QQQ": "CAUTION", "SPY": "CAUTION"}) == "HIGH"
    assert combine_index_risks({"QQQ": "HIGH", "SPY": "NORMAL"}) == "HIGH"
    assert combine_index_risks({"QQQ": "NORMAL", "SPY": "NORMAL"}) == "NORMAL"
    assert combine_index_risks({"QQQ": "SEVERE", "SPY": "NORMAL"}) == "SEVERE"


# ── prepare_effective_history ────────────────────────────────────────────

def test_prepare_effective_history_as_of_slices_to_evaluation_day():
    from ibd_distribution_day_monitor import prepare_effective_history
    history = _flat_history(10, start_date="2026-01-01")
    effective, audit = prepare_effective_history(history, "2026-01-05", required_min_sessions=1)
    assert effective[0]["date"] == "2026-01-05"
    assert audit["as_of_resolved"] == "2026-01-05"


def test_prepare_effective_history_flags_insufficient_lookback():
    from ibd_distribution_day_monitor import prepare_effective_history
    history = _flat_history(5)
    _, audit = prepare_effective_history(history, None, required_min_sessions=80)
    assert "insufficient_lookback" in audit["audit_flags"]


def test_prepare_effective_history_missing_as_of_raises():
    from ibd_distribution_day_monitor import prepare_effective_history
    import pytest
    history = _flat_history(5)
    with pytest.raises(ValueError):
        prepare_effective_history(history, "2099-01-01", required_min_sessions=1)


# ── analyze_index end-to-end ──────────────────────────────────────────────

def test_analyze_index_normal_risk_in_flat_market():
    from ibd_distribution_day_monitor import DistributionDayRule, RiskThresholds, analyze_index
    history = _flat_history(90)
    result = analyze_index("SPY", history, DistributionDayRule(), RiskThresholds(), required_min_sessions=80)
    assert result["risk_level"] == "NORMAL"
    assert result["d5_count"] == 0
    assert result["is_distribution_day_today"] is False


def test_analyze_index_empty_history_raises():
    from ibd_distribution_day_monitor import DistributionDayRule, RiskThresholds, analyze_index
    import pytest
    with pytest.raises(ValueError):
        analyze_index("SPY", [], DistributionDayRule(), RiskThresholds())
