"""
Tests for core/sector_rotation_analyzer.py -- pure calculation, synthetic
sector_summary.csv-shaped rows only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from sector_rotation_analyzer import (
    analyze_sector_rotation,
    compute_risk_regime_score,
    estimate_cycle_phase,
    find_overbought_oversold,
    rank_sectors,
)


def _row(sector, ratio, trend="Up", status="Normal"):
    return {"sector": sector, "ratio": ratio, "ma10": ratio, "trend": trend, "status": status, "slope": 0.0}


def test_rank_sectors_descending_by_ratio():
    rows = [_row("Utilities", 0.1), _row("Technology", 0.5), _row("Energy", 0.3)]
    ranked = rank_sectors(rows)
    assert [r["sector"] for r in ranked] == ["Technology", "Energy", "Utilities"]


def test_compute_risk_regime_score_cyclical_leadership():
    rows = [_row("Technology", 0.8), _row("Energy", 0.7), _row("Utilities", 0.1), _row("Healthcare", 0.1)]
    result = compute_risk_regime_score(rows)
    assert result["regime"] == "CYCLICAL_LEADERSHIP"
    assert result["score"] > 5


def test_compute_risk_regime_score_defensive_leadership():
    rows = [_row("Technology", 0.1), _row("Energy", 0.1), _row("Utilities", 0.8), _row("Healthcare", 0.7)]
    result = compute_risk_regime_score(rows)
    assert result["regime"] == "DEFENSIVE_LEADERSHIP"


def test_compute_risk_regime_score_missing_group_is_unknown():
    rows = [_row("Technology", 0.5)]
    result = compute_risk_regime_score(rows)
    assert result["regime"] == "UNKNOWN"
    assert result["score"] is None


def test_find_overbought_oversold_reads_status_column():
    rows = [_row("Energy", 0.5, status="Overbought"), _row("Utilities", 0.02, status="Oversold"), _row("Technology", 0.3)]
    extremes = find_overbought_oversold(rows)
    assert extremes["overbought"] == ["Energy"]
    assert extremes["oversold"] == ["Utilities"]


def test_estimate_cycle_phase_early_recovery():
    rows = [
        _row("Technology", 0.9), _row("Consumer Cyclical", 0.8), _row("Industrials", 0.7),
        _row("Financial", 0.6), _row("Real Estate", 0.5),
        _row("Utilities", 0.1), _row("Healthcare", 0.1), _row("Consumer Defensive", 0.1),
    ]
    result = estimate_cycle_phase(rows, top_n=5)
    assert result["phase"] == "Early Cycle Recovery"
    assert result["confidence"] in ("HIGH", "MEDIUM")


def test_estimate_cycle_phase_recession():
    rows = [
        _row("Utilities", 0.9), _row("Consumer Defensive", 0.8), _row("Healthcare", 0.7),
        _row("Communication Services", 0.6),
        _row("Technology", 0.1), _row("Energy", 0.1), _row("Industrials", 0.1),
    ]
    result = estimate_cycle_phase(rows, top_n=4)
    assert result["phase"] == "Recession"


def test_analyze_sector_rotation_full_pipeline():
    rows = [
        _row("Technology", 0.8), _row("Energy", 0.5, status="Overbought"), _row("Utilities", 0.02, status="Oversold"),
        _row("Healthcare", 0.3), _row("Consumer Cyclical", 0.4), _row("Financial", 0.2),
    ]
    result = analyze_sector_rotation(rows)
    assert result["ranked_sectors"][0]["sector"] == "Technology"
    assert result["risk_regime"]["regime"] in ("CYCLICAL_LEADERSHIP", "DEFENSIVE_LEADERSHIP", "MIXED")
    assert "Energy" in result["overbought_oversold"]["overbought"]
    assert "Utilities" in result["overbought_oversold"]["oversold"]
    assert result["cycle_phase"]["phase"]
