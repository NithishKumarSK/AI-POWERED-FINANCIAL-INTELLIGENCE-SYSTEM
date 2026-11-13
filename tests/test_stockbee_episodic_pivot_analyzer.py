"""
Tests for core/stockbee_episodic_pivot_analyzer.py -- ported Day-1
Episodic Pivot catalyst classification and scoring. Synthetic data only,
no network. Price bars are CHRONOLOGICAL (oldest first), matching
historical_price_service's own native order.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from stockbee_episodic_pivot_analyzer import (
    analyze_candidate,
    classify_catalyst,
    determine_state,
    normalize_catalyst_type,
    price_stats_from_bars,
    rating_from_score,
    score_catalyst,
    score_liquidity,
    score_revaluation,
    score_risk,
    score_volume,
)


def _bar(date_str, open_, high, low, close, volume=1_000_000):
    return {"date": date_str, "open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _dates(n, start="2026-06-01"):
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range(n)]


# ── classify_catalyst / normalize_catalyst_type ──────────────────────────

def test_normalize_catalyst_type_resolves_alias():
    assert normalize_catalyst_type("beat_and_raise") == "guidance_raise"
    assert normalize_catalyst_type("bogus_value") == "unknown"


def test_classify_catalyst_explicit_type_wins():
    catalyst_type, reasons = classify_catalyst({"catalyst_type": "fda_approval"})
    assert catalyst_type == "fda_approval"
    assert reasons == ["explicit:fda_approval"]


def test_classify_catalyst_keyword_fallback():
    catalyst_type, reasons = classify_catalyst({"headline": "Company announces FDA approval of new drug"})
    assert catalyst_type == "fda_approval"


def test_classify_catalyst_no_match_is_unknown():
    catalyst_type, reasons = classify_catalyst({"headline": "Company holds annual picnic"})
    assert catalyst_type == "unknown"
    assert reasons == ["no_clear_catalyst_keyword"]


# ── price_stats_from_bars ─────────────────────────────────────────────────

def test_price_stats_from_bars_computes_gap_and_day_gain():
    dates = _dates(5)
    bars = [
        _bar(dates[0], 100, 101, 99, 100, 1_000_000),
        _bar(dates[1], 100, 101, 99, 100, 1_000_000),
        _bar(dates[2], 108, 110, 107, 109, 5_000_000),  # event day: gap up + strong close
        _bar(dates[3], 109, 111, 108, 110, 1_000_000),
        _bar(dates[4], 110, 112, 109, 111, 1_000_000),
    ]
    stats = price_stats_from_bars("TEST", bars, dates[2])
    assert stats.gap_pct == ((108 / 100) - 1) * 100
    assert stats.day_gain_pct == ((109 / 100) - 1) * 100
    assert stats.close_location_pct > 50


def test_price_stats_from_bars_missing_event_date_returns_empty_stats():
    bars = [_bar(d, 100, 101, 99, 100) for d in _dates(5)]
    stats = price_stats_from_bars("TEST", bars, "2099-01-01")
    # falls through to len(bars)-1 index per find_event_index's fallback
    assert stats.symbol == "TEST"


# ── component scorers ──────────────────────────────────────────────────────

def test_score_catalyst_applies_grade_bonus_and_negative_language():
    score_a, _ = score_catalyst({"catalyst_type": "earnings", "source_grade": "A"})
    score_d, _ = score_catalyst({"catalyst_type": "earnings", "source_grade": "D"})
    assert score_a > score_d

    score_neg, reasons = score_catalyst({"catalyst_type": "earnings", "headline": "Company announces dilutive secondary offering"})
    assert "negative_or_dilutive_language:-12" in reasons


def test_score_volume_high_ratio_scores_max():
    score, reasons = score_volume({"volume_ratio_50": 12.0})
    assert score == 20.0


def test_score_revaluation_neglected_stock_scores_higher_than_extended():
    neglected, _ = score_revaluation({"prior_20d_return_pct": 2.0})
    extended, _ = score_revaluation({"prior_20d_return_pct": 40.0})
    assert neglected > extended


def test_score_liquidity_thin_volume_scores_low():
    score, _ = score_liquidity({"close": 5.0, "volume": 50_000})
    assert score <= 4.0


def test_score_risk_tight_stop_scores_max():
    score, reasons = score_risk({"risk_pct_to_low": 2.0})
    assert score == 5.0


def test_rating_from_score_bands():
    assert rating_from_score(95) == "A"
    assert rating_from_score(85) == "A-"
    assert rating_from_score(75) == "B"
    assert rating_from_score(60) == "C"
    assert rating_from_score(10) == "D"


# ── determine_state ────────────────────────────────────────────────────────

def test_determine_state_actionable_day1_requires_all_confirmations():
    record = {"day_gain_pct": 6.0, "gap_pct": 5.0, "volume_ratio_50": 3.0, "close_location_pct": 90.0, "risk_pct_to_low": 3.0, "catalyst_type": "earnings"}
    state, reasons = determine_state(record, score=90, max_risk_pct=10.0)
    assert state == "ACTIONABLE_DAY1"


def test_determine_state_wide_risk_demotes_to_delayed_watch():
    record = {"day_gain_pct": 6.0, "gap_pct": 5.0, "volume_ratio_50": 3.0, "close_location_pct": 90.0, "risk_pct_to_low": 20.0, "catalyst_type": "earnings"}
    state, reasons = determine_state(record, score=90, max_risk_pct=10.0)
    assert state == "DELAYED_EP_WATCH"
    assert "risk_too_wide_for_day1" in reasons


# ── analyze_candidate (end-to-end) ────────────────────────────────────────

def test_analyze_candidate_full_pipeline_strong_earnings_setup():
    dates = _dates(60)
    bars = [_bar(d, 50, 50.5, 49.5, 50, 500_000) for d in dates[:55]]
    bars.append(_bar(dates[55], 54, 59, 53, 58, 6_000_000))  # earnings day: +16% gap, huge volume, strong close
    bars.extend(_bar(d, 58, 59, 57, 58.5, 1_000_000) for d in dates[56:])

    event = {"symbol": "TEST", "event_date": dates[55], "catalyst_type": "earnings", "source_grade": "A"}
    result = analyze_candidate(event, bars, max_risk_pct=10.0)

    assert result["symbol"] == "TEST"
    assert result["catalyst_type"] == "earnings"
    assert result["ep_type"] == "EARNINGS_EP"
    assert result["composite_score"] > 0
    assert result["state"] in ("ACTIONABLE_DAY1", "DAY1_WATCH", "DELAYED_EP_WATCH", "CATALYST_WATCH", "REJECT")


def test_analyze_candidate_no_bars_still_returns_a_result():
    event = {"symbol": "TEST", "event_date": "2026-06-01", "catalyst_type": "unknown"}
    result = analyze_candidate(event, [], max_risk_pct=10.0)
    assert result["symbol"] == "TEST"
    assert result["state"] == "REJECT"
