"""
Component 4: Market Breadth Divergence (Weight: 15%). Ported from
calculators/breadth_calculator.py.

breadth_200dma/breadth_50dma: % of S&P 500 stocks above their 200DMA/50DMA
(0-100). This project's core/market_breadth_service.py now exposes these
as breadth_200dma_pct/breadth_50dma_pct (added this session specifically
to feed this calculator -- see that module's docstring).
"""
from __future__ import annotations

from typing import Optional


def calculate_breadth_divergence(
    breadth_200dma: Optional[float],
    breadth_50dma: Optional[float],
    index_distance_from_high_pct: float,
) -> dict:
    if breadth_200dma is None:
        return {
            "score": 50, "signal": "NO DATA: Breadth data not provided (neutral default)",
            "data_available": False, "breadth_200dma": None, "breadth_50dma": breadth_50dma,
            "index_near_highs": False, "divergence_detected": False,
        }

    index_near_highs = index_distance_from_high_pct >= -5.0
    raw_score = _score_200dma_breadth(breadth_200dma)
    if not index_near_highs:
        raw_score = raw_score * 0.5

    if breadth_50dma is not None:
        if breadth_50dma < 30 and index_near_highs:
            raw_score = min(100, raw_score + 10)
        elif breadth_50dma > 70:
            raw_score = max(0, raw_score - 5)

    score = round(min(100, max(0, raw_score)))
    divergence_detected = index_near_highs and breadth_200dma < 60

    if score >= 80:
        signal = "CRITICAL: Severe breadth divergence - index at highs but breadth collapsing"
    elif score >= 60:
        signal = "WARNING: Significant breadth divergence"
    elif score >= 35:
        signal = "CAUTION: Mild breadth weakness"
    elif divergence_detected:
        signal = "WATCH: Some breadth deterioration despite index strength"
    else:
        signal = "HEALTHY: Breadth supports index level"

    return {
        "score": score, "signal": signal, "data_available": True,
        "breadth_200dma": breadth_200dma, "breadth_50dma": breadth_50dma,
        "index_near_highs": index_near_highs,
        "index_distance_from_high_pct": round(index_distance_from_high_pct, 1),
        "divergence_detected": divergence_detected,
    }


def _score_200dma_breadth(breadth_200dma: float) -> int:
    """< 40% -> 100; 40-50% -> 100..55; 50-60% -> 55..30; 60-70% -> 30..5; >= 70% -> 5."""
    if breadth_200dma < 40:
        return 100
    elif breadth_200dma < 50:
        return round(100 - (breadth_200dma - 40) / 10 * 45)
    elif breadth_200dma < 60:
        return round(55 - (breadth_200dma - 50) / 10 * 25)
    elif breadth_200dma < 70:
        return round(30 - (breadth_200dma - 60) / 10 * 25)
    return 5
