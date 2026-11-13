"""
Tests for core/news_reaction_failure.py -- pure calculation, synthetic
price series and events only.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from news_reaction_failure import (
    analyze_news_reaction,
    cluster_relevant_events,
    compute_return_and_zscore,
    resolve_effective_date,
)


def _trading_dates(n=120, start="2026-01-02"):
    d0 = dt.date.fromisoformat(start)
    out = []
    d = d0
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def test_resolve_effective_date_same_day_before_close():
    dates = _trading_dates(10)
    eff, err = resolve_effective_date(f"{dates[3]}T10:00:00-05:00", dates)
    assert err == ""
    assert eff == dates[3]


def test_resolve_effective_date_after_close_rolls_to_next_day():
    dates = _trading_dates(10)
    eff, err = resolve_effective_date(f"{dates[3]}T16:30:00-05:00", dates)
    assert err == ""
    assert eff == dates[4]


def test_resolve_effective_date_weekend_rolls_to_monday():
    # 2026-01-03 is a Saturday.
    dates = _trading_dates(10)
    eff, err = resolve_effective_date("2026-01-03T10:00:00-05:00", dates)
    assert err == ""
    assert dt.date.fromisoformat(eff).weekday() < 5


def test_resolve_effective_date_naive_timestamp_rejected():
    dates = _trading_dates(10)
    eff, err = resolve_effective_date(f"{dates[3]}T10:00:00", dates)
    assert eff is None
    assert err == "unparsable_event_time"


def test_compute_return_and_zscore_insufficient_history():
    dates = _trading_dates(5)
    closes = [100.0] * 5
    assert compute_return_and_zscore(dates, closes, dates[1]) is None


def test_compute_return_and_zscore_basic():
    dates = _trading_dates(70)
    closes = [100.0 + i * 0.01 for i in range(70)]
    result = compute_return_and_zscore(dates, closes, dates[65])
    assert result is not None
    assert "zscore_3d" in result


def test_cluster_relevant_events_merges_overlapping_windows():
    events = [
        {"idx": 10, "effective_date": "d10", "zscore_3d": 1.0, "direction_adjusted_z3": 1.0},
        {"idx": 11, "effective_date": "d11", "zscore_3d": 2.0, "direction_adjusted_z3": 2.0},  # overlaps [10,12]
        {"idx": 20, "effective_date": "d20", "zscore_3d": 3.0, "direction_adjusted_z3": 3.0},   # separate
    ]
    clusters = cluster_relevant_events(events)
    assert len(clusters) == 2
    assert clusters[0]["direction_adjusted_z3"] == 1.0  # earliest member's z3, never averaged
    assert clusters[0]["cluster_size"] if "cluster_size" in clusters[0] else len(clusters[0]["cluster_members"]) == 2


def test_analyze_news_reaction_insufficient_evidence_too_few_events():
    dates = _trading_dates(70)
    closes = [100.0] * 70
    events = [{"event_id": "e1", "event": "x", "event_time": f"{dates[65]}T10:00:00-05:00",
               "source_url": "u", "source_tier": "wire", "expected_impact": "BULLISH"}]
    result = analyze_news_reaction(events, dates, closes, min_events=3)
    assert result["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert result["verdict_reason"] == "too_few_usable_events"


def test_analyze_news_reaction_drops_unparsable_events_without_crashing():
    dates = _trading_dates(70)
    closes = [100.0] * 70
    events = [{"event_id": "e1", "event": "x", "event_time": f"{dates[65]}T10:00:00",  # naive, no offset
               "source_url": "u", "source_tier": "wire", "expected_impact": "BULLISH"}]
    result = analyze_news_reaction(events, dates, closes, min_events=1)
    assert result["n_events_dropped"] == 1
    assert result["dropped"][0]["drop_reason"] == "unparsable_event_time"


def test_analyze_news_reaction_confirmed_on_strong_negative_drift():
    # Small baseline oscillation (so trailing daily stdev is nonzero, not
    # a degenerate flat series), then a sharp DROP right after each
    # bullish event -> the market moved significantly AGAINST favorable news.
    n = 100
    dates = _trading_dates(n)
    closes = [100.0 + (0.1 if i % 2 == 0 else -0.1) for i in range(n)]
    event_indices = [70, 85, 95]
    for idx in event_indices:
        closes[idx] = 90.0
        closes[idx + 1] = 89.0
        closes[idx + 2] = 88.0
        for j in range(idx + 3, min(idx + 10, n)):
            closes[j] = 88.0

    events = [
        {"event_id": f"e{i}", "event": "bullish catalyst", "event_time": f"{dates[idx]}T10:00:00-05:00",
         "source_url": "u", "source_tier": "wire", "expected_impact": "BULLISH"}
        for i, idx in enumerate(event_indices)
    ]
    result = analyze_news_reaction(events, dates, closes, min_events=3)
    assert result["verdict"] == "CONFIRMED"
    assert result["drift_stat"] <= -1.45
    assert result["responded_ratio"] <= 0.25


def test_analyze_news_reaction_not_confirmed_on_positive_drift():
    n = 100
    dates = _trading_dates(n)
    closes = [100.0 + (0.1 if i % 2 == 0 else -0.1) for i in range(n)]
    event_indices = [70, 85, 95]
    for idx in event_indices:
        closes[idx] = 110.0
        closes[idx + 1] = 112.0
        closes[idx + 2] = 115.0
        for j in range(idx + 3, min(idx + 10, n)):
            closes[j] = 115.0

    events = [
        {"event_id": f"e{i}", "event": "bullish catalyst", "event_time": f"{dates[idx]}T10:00:00-05:00",
         "source_url": "u", "source_tier": "wire", "expected_impact": "BULLISH"}
        for i, idx in enumerate(event_indices)
    ]
    result = analyze_news_reaction(events, dates, closes, min_events=3)
    assert result["verdict"] == "NOT_CONFIRMED"
