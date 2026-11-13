"""
Tests for core/breadth_chart_analyst.py -- pure calculation, synthetic
series only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from breadth_chart_analyst import (
    analyze_breadth_charts,
    classify_200ma_zone,
    classify_8ma_zone,
    classify_uptrend_zone,
    detect_color_transition,
    detect_dead_cross,
    detect_local_peak,
    detect_local_trough,
    uptrend_color,
)


def test_classify_200ma_zone_bands():
    assert classify_200ma_zone(80) == "overheating_peak_zone"
    assert classify_200ma_zone(20) == "extreme_oversold_trough_zone"
    assert classify_200ma_zone(65) == "healthy"
    assert classify_200ma_zone(40) == "neutral"


def test_classify_8ma_zone_bands():
    assert classify_8ma_zone(75) == "overheating"
    assert classify_8ma_zone(20) == "extreme_oversold"
    assert classify_8ma_zone(67) == "healthy_bullish"
    assert classify_8ma_zone(40) == "neutral"


def test_detect_dead_cross_true_and_false():
    assert detect_dead_cross(breadth_8ma=50, breadth_200ma=60)["dead_cross"] is True
    assert detect_dead_cross(breadth_8ma=70, breadth_200ma=60)["dead_cross"] is False


def test_detect_local_trough():
    assert detect_local_trough([30, 20, 25]) is True
    assert detect_local_trough([30, 20, 15]) is False
    assert detect_local_trough([10, 20]) is False


def test_detect_local_peak():
    assert detect_local_peak([60, 75, 70]) is True
    assert detect_local_peak([60, 75, 80]) is False


def test_classify_uptrend_zone_bands():
    assert classify_uptrend_zone(5) == "extreme_oversold_bottom"
    assert classify_uptrend_zone(12) == "near_bottom"
    assert classify_uptrend_zone(45) == "overheating_top"
    assert classify_uptrend_zone(37) == "near_top"
    assert classify_uptrend_zone(25) == "neutral"


def test_uptrend_color_mapping():
    assert uptrend_color("Up") == "GREEN"
    assert uptrend_color("Down") == "RED"
    assert uptrend_color("neutral") == "NEUTRAL"
    assert uptrend_color(None) == "NEUTRAL"


def test_detect_color_transition_red_to_green():
    assert detect_color_transition(["Down", "Up"]) == "RED_TO_GREEN"


def test_detect_color_transition_green_to_red():
    assert detect_color_transition(["Up", "Down"]) == "GREEN_TO_RED"


def test_detect_color_transition_none_when_stable():
    assert detect_color_transition(["Up", "Up"]) is None
    assert detect_color_transition(["Up"]) is None


def test_analyze_breadth_charts_buy_signal_on_trough_reversal():
    result = analyze_breadth_charts(
        breadth_200ma_series=[50, 50, 50],
        breadth_8ma_series=[30, 18, 25],   # trough at 18 (extreme_oversold), reversing up
        uptrend_ratio_series=[20, 20, 20],
        uptrend_trend_series=["neutral", "neutral", "neutral"],
    )
    assert result["chart1_strategic"]["signal"] == "BUY"
    assert result["combined_outlook"] == "BULLISH"


def test_analyze_breadth_charts_sell_signal_on_peak_formation():
    result = analyze_breadth_charts(
        breadth_200ma_series=[70, 80, 70],  # peak at 80 (overheating), reversing down
        breadth_8ma_series=[50, 50, 50],
        uptrend_ratio_series=[20, 20, 20],
        uptrend_trend_series=["neutral", "neutral", "neutral"],
    )
    assert result["chart1_strategic"]["signal"] == "SELL"
    assert result["combined_outlook"] == "BEARISH"


def test_analyze_breadth_charts_enter_long_on_color_transition_from_bottom():
    result = analyze_breadth_charts(
        breadth_200ma_series=[50, 50, 50],
        breadth_8ma_series=[50, 50, 50],
        uptrend_ratio_series=[8, 8, 15],
        uptrend_trend_series=["Down", "Down", "Up"],
    )
    assert result["chart2_tactical"]["signal"] == "ENTER_LONG"
    assert result["combined_outlook"] == "BULLISH"


def test_analyze_breadth_charts_neutral_when_no_signals():
    result = analyze_breadth_charts(
        breadth_200ma_series=[50, 50, 50],
        breadth_8ma_series=[50, 50, 50],
        uptrend_ratio_series=[20, 20, 20],
        uptrend_trend_series=["Up", "Up", "Up"],
    )
    assert result["combined_outlook"] == "NEUTRAL"
