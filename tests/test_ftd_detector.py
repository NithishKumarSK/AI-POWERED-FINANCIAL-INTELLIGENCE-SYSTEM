"""
Tests for core/ftd_detector.py -- the ported claude-trading-skills
ftd-detector O'Neil Follow-Through-Day state machine. Synthetic data
only, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _bars(closes_volumes, start_year=2026, start_month=1, start_day=1):
    """Chronological (oldest-first) OHLCV bars from a list of
    (close, volume) tuples. high = close+0.5, low = close-0.5 for every
    bar (simple, consistent range) unless overridden."""
    import datetime as dt

    out = []
    d = dt.date(start_year, start_month, start_day)
    for close, volume in closes_volumes:
        out.append({
            "date": d.isoformat(),
            "close": float(close),
            "high": float(close) + 0.5,
            "low": float(close) - 0.5,
            "volume": float(volume),
        })
        d += dt.timedelta(days=1)
    return out


# Shared "correction -> rally -> FTD" sequence used by several tests.
# idx0-9: uptrend to a high of 109 (idx9). idx10-12: 3 down days to a
# swing low of 97 (idx12, -11% decline, 3 down days -- clears both O'Neil
# thresholds). idx13: Day 1 of rally (up close). idx14-15: Day 2-3, hold
# above Day-1 low. idx16: Day 4, +2.0% on 1.5x volume -- a textbook
# "strong" FTD. idx17-20: price continues up, FTD stays unbreached.
_FTD_SEQUENCE = (
    [(100 + i, 1000) for i in range(10)]  # idx0-9: 100..109
    + [(101, 1000), (99, 1000), (97, 1000)]  # idx10-12: swing low at 97
    + [(98, 1000), (99, 1000), (100, 1000)]  # idx13-15: Day1-3 of rally
    + [(102, 1500)]  # idx16: Day4 FTD (+2.0%, 1.5x volume)
    + [(103, 1000), (104, 1000), (105, 1000), (106, 1000)]  # idx17-20
)


# ── _is_swing_low / find_swing_low ──────────────────────────────────────

def test_swing_low_detected_at_correct_index_and_price():
    from ftd_detector import find_swing_low
    history = _bars(_FTD_SEQUENCE)
    sl = find_swing_low(history)
    assert sl is not None
    assert sl["swing_low_idx"] == 12
    assert sl["swing_low_price"] == 97.0
    assert sl["down_days"] == 3
    assert sl["decline_pct"] < -3.0


def test_no_swing_low_in_pure_uptrend():
    from ftd_detector import find_swing_low
    history = _bars([(100 + i, 1000) for i in range(30)])
    assert find_swing_low(history) is None


def test_find_all_swing_lows_respects_max_count():
    from ftd_detector import _find_all_swing_lows
    history = _bars(_FTD_SEQUENCE)
    lows = _find_all_swing_lows(history, max_count=6)
    assert len(lows) == 1
    assert lows[0]["swing_low_idx"] == 12


# ── track_rally_attempt ──────────────────────────────────────────────────

def test_track_rally_attempt_finds_day1_and_counts_days():
    from ftd_detector import track_rally_attempt
    history = _bars(_FTD_SEQUENCE)
    rally = track_rally_attempt(history, swing_low_idx=12)
    assert rally["invalidated"] is False
    assert rally["day1_idx"] == 13
    assert rally["day1_low"] == 97.5
    assert rally["current_day_count"] == 8  # idx13..idx20 inclusive


def test_rally_invalidated_when_close_drops_below_swing_low():
    from ftd_detector import track_rally_attempt
    seq = (
        [(100 + i, 1000) for i in range(10)]
        + [(101, 1000), (99, 1000), (97, 1000)]  # swing low at idx12, price 97
        + [(96, 1000)]  # idx13: closes BELOW the swing low -- invalidated
    )
    history = _bars(seq)
    rally = track_rally_attempt(history, swing_low_idx=12)
    assert rally["invalidated"] is True
    assert rally["day1_idx"] is None
    assert "below swing low" in rally["invalidation_reason"]


def test_rally_invalidated_on_day2_3_breach_of_day1_low():
    from ftd_detector import track_rally_attempt
    seq = (
        [(100 + i, 1000) for i in range(10)]
        + [(101, 1000), (99, 1000), (97, 1000)]  # swing low idx12, price 97
        + [(98, 1000)]  # idx13: Day 1 (up close), day1_low = 97.5
        + [(97, 1000)]  # idx14: Day 2, close 97 < day1_low 97.5 (but not < swing low 97) -- breach
    )
    history = _bars(seq)
    rally = track_rally_attempt(history, swing_low_idx=12)
    assert rally["invalidated"] is True
    assert "Day 2" in rally["invalidation_reason"]


# ── detect_ftd / analyze_single_index ────────────────────────────────────

def test_detect_ftd_confirms_strong_gain_on_rising_volume():
    from ftd_detector import track_rally_attempt, detect_ftd
    history = _bars(_FTD_SEQUENCE)
    rally = track_rally_attempt(history, swing_low_idx=12)
    ftd = detect_ftd(history, rally)
    assert ftd["ftd_detected"] is True
    assert ftd["ftd_day_number"] == 4
    assert ftd["gain_tier"] == "strong"
    assert ftd["gain_pct"] == 2.0
    assert ftd["volume_above_avg"] is True


def test_detect_ftd_rejects_gain_without_volume_increase():
    from ftd_detector import track_rally_attempt, detect_ftd
    seq = (
        [(100 + i, 1000) for i in range(10)]
        + [(101, 1000), (99, 1000), (97, 1000)]
        + [(98, 1000), (99, 1000), (100, 1000)]
        + [(102, 900)]  # Day4: +2.0% gain, but volume DROPS vs previous day -- no FTD
    )
    history = _bars(seq)
    rally = track_rally_attempt(history, swing_low_idx=12)
    ftd = detect_ftd(history, rally)
    assert ftd["ftd_detected"] is False


def test_analyze_single_index_reaches_ftd_confirmed():
    from ftd_detector import analyze_single_index, MarketState
    history = _bars(_FTD_SEQUENCE)
    result = analyze_single_index(history, "S&P 500")
    assert result["state"] == MarketState.FTD_CONFIRMED.value
    assert result["ftd"]["ftd_detected"] is True
    assert result["ftd"]["ftd_day_number"] == 4


def test_analyze_single_index_no_signal_in_pure_uptrend():
    from ftd_detector import analyze_single_index, MarketState
    history = _bars([(100 + i, 1000) for i in range(30)])
    result = analyze_single_index(history, "NASDAQ")
    assert result["state"] == MarketState.NO_SIGNAL.value


def test_analyze_single_index_insufficient_data():
    from ftd_detector import analyze_single_index
    result = analyze_single_index(_bars([(100, 1000), (101, 1000)]), "S&P 500")
    assert result.get("error") == "Insufficient data"


# ── get_market_state (dual-index combiner) ───────────────────────────────

def test_get_market_state_single_index_ftd_is_sufficient():
    from ftd_detector import get_market_state, MarketState
    ftd_history = _bars(_FTD_SEQUENCE)
    flat_history = _bars([(100 + i, 1000) for i in range(30)])

    combined = get_market_state(ftd_history, flat_history)
    assert combined["combined_state"] == MarketState.FTD_CONFIRMED.value
    assert combined["dual_confirmation"] is False
    assert combined["ftd_index"] == "S&P 500"


def test_get_market_state_dual_confirmation_when_both_confirm():
    from ftd_detector import get_market_state, MarketState
    ftd_history = _bars(_FTD_SEQUENCE)

    combined = get_market_state(ftd_history, ftd_history)
    assert combined["combined_state"] == MarketState.FTD_CONFIRMED.value
    assert combined["dual_confirmation"] is True
    assert combined["ftd_index"] == "Both"


def test_get_market_state_no_signal_when_neither_has_data():
    from ftd_detector import get_market_state, MarketState
    flat_history = _bars([(100 + i, 1000) for i in range(30)])

    combined = get_market_state(flat_history, flat_history)
    assert combined["combined_state"] == MarketState.NO_SIGNAL.value
    assert combined["dual_confirmation"] is False
