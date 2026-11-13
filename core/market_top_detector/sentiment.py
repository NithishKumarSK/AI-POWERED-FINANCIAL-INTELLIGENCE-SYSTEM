"""
Component 6: Sentiment & Speculation (Weight: 10%). Ported verbatim from
calculators/sentiment_calculator.py.

vix_level comes from this project's historical_price_service.py (ticker
"^VIX", confirmed resolvable via its yfinance fallback this session).
put_call_ratio, vix_term_structure, and margin_debt_yoy_pct have no free,
keyless, programmatic source -- even the source skill only gets them via
a human running WebSearch and passing them as CLI args. They're left None
here; the scoring below already handles that gracefully (0 points, not a
crash), an honest gap carried over unchanged.
"""
from __future__ import annotations

from typing import Optional

STEEP_CONTANGO = "steep_contango"
NORMAL_CONTANGO = "contango"
FLAT = "flat"
BACKWARDATION = "backwardation"


def calculate_sentiment(
    vix_level: Optional[float] = None,
    put_call_ratio: Optional[float] = None,
    vix_term_structure: Optional[str] = None,
    margin_debt_yoy_pct: Optional[float] = None,
) -> dict:
    if vix_level is None and put_call_ratio is None and vix_term_structure is None:
        return {
            "score": 50, "signal": "NO DATA: All sentiment inputs missing (neutral default)",
            "data_available": False, "total_points": 0, "details": {},
        }

    total_points = 0
    details = {}

    pc_points = 0
    if put_call_ratio is not None:
        if put_call_ratio < 0.60:
            pc_points = 35
        elif put_call_ratio < 0.70:
            pc_points = 25
        elif put_call_ratio < 0.80:
            pc_points = 12
        details["put_call_ratio"] = {"value": put_call_ratio, "points": pc_points, "interpretation": _interpret_put_call(put_call_ratio)}
    else:
        details["put_call_ratio"] = {"value": None, "points": 0, "interpretation": "No data"}
    total_points += pc_points

    vix_points = 0
    if vix_level is not None:
        if vix_level < 12:
            vix_points = 25
        elif vix_level < 14:
            vix_points = 17
        elif vix_level < 16:
            vix_points = 8
        elif vix_level <= 25:
            vix_points = 0
        else:
            vix_points = -8
        details["vix_level"] = {"value": round(vix_level, 2), "points": vix_points, "interpretation": _interpret_vix(vix_level)}
    else:
        details["vix_level"] = {"value": None, "points": 0, "interpretation": "No data"}
    total_points += vix_points

    vts_points = 0
    if vix_term_structure:
        if vix_term_structure == STEEP_CONTANGO:
            vts_points = 25
        elif vix_term_structure == NORMAL_CONTANGO:
            vts_points = 12
        elif vix_term_structure == FLAT:
            vts_points = 0
        elif vix_term_structure == BACKWARDATION:
            vts_points = -8
        details["vix_term_structure"] = {"value": vix_term_structure, "points": vts_points, "interpretation": _interpret_vix_term(vix_term_structure)}
    else:
        details["vix_term_structure"] = {"value": None, "points": 0, "interpretation": "No data"}
    total_points += vts_points

    md_points = 0
    if margin_debt_yoy_pct is not None:
        if margin_debt_yoy_pct > 30:
            md_points = 15
        elif margin_debt_yoy_pct > 20:
            md_points = 10
        elif margin_debt_yoy_pct > 10:
            md_points = 5
        details["margin_debt"] = {"yoy_pct": margin_debt_yoy_pct, "points": md_points, "interpretation": _interpret_margin_debt(margin_debt_yoy_pct)}
    total_points += md_points

    score = max(0, min(100, total_points))

    if score >= 70:
        signal = "CRITICAL: Extreme complacency / speculation"
    elif score >= 50:
        signal = "WARNING: Elevated complacency"
    elif score >= 30:
        signal = "CAUTION: Some speculative excess"
    elif score >= 10:
        signal = "MIXED: Moderate sentiment"
    else:
        signal = "HEALTHY: No excessive speculation"

    return {"score": score, "signal": signal, "data_available": True, "total_points": total_points, "details": details}


def _interpret_put_call(ratio: float) -> str:
    if ratio < 0.60:
        return "Extreme call buying - maximum complacency"
    elif ratio < 0.70:
        return "Elevated call buying - notable optimism"
    elif ratio < 0.80:
        return "Slightly optimistic"
    elif ratio < 0.90:
        return "Normal range"
    return "Elevated put buying - caution/fear present"


def _interpret_vix(level: float) -> str:
    if level < 12:
        return "Extreme low fear - complacency zone"
    elif level < 14:
        return "Low fear"
    elif level < 16:
        return "Mildly low volatility"
    elif level <= 20:
        return "Normal range"
    elif level <= 25:
        return "Elevated fear"
    return "High fear - panic present"


def _interpret_vix_term(structure: str) -> str:
    mapping = {
        STEEP_CONTANGO: "Market expects calm - complacency in term structure",
        NORMAL_CONTANGO: "Normal term structure",
        FLAT: "Uncertainty - no clear expectation",
        BACKWARDATION: "Hedging demand elevated - fear in term structure",
    }
    return mapping.get(structure, "Unknown")


def _interpret_margin_debt(yoy_pct: float) -> str:
    if yoy_pct >= 30:
        return f"DANGER: Margin debt surging +{yoy_pct:.0f}% YoY"
    elif yoy_pct >= 20:
        return f"WARNING: Rapid leverage increase +{yoy_pct:.0f}% YoY"
    elif yoy_pct >= 10:
        return f"Elevated: +{yoy_pct:.0f}% YoY"
    elif yoy_pct >= 0:
        return f"Normal: +{yoy_pct:.0f}% YoY"
    return f"Deleveraging: {yoy_pct:.0f}% YoY"
