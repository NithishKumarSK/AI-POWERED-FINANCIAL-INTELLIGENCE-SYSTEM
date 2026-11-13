"""
Component 5: Index Technical Condition (Weight: 15%). Ported from
calculators/index_technical_calculator.py.

Checkpoints (per index, S&P 500 + NASDAQ):
1. Price < 21 EMA (short-term weakness)         -> +8pt
2. Price < 50 EMA (medium-term breakdown)        -> +12pt
3. 21 EMA < 50 EMA (MA bearish crossover)         -> +10pt
4. Price < 200 SMA (long-term trend breakdown)    -> +15pt
5. Failed rally pattern                           -> +10pt
6. Lower highs pattern                            -> +10pt
7. Gap down on volume                             -> +10pt
"""
from __future__ import annotations

from typing import Optional

from ibd_distribution_day_monitor import calc_ema


def calculate_index_technical(
    sp500_history: list,
    nasdaq_history: list,
    sp500_quote: Optional[dict] = None,
    nasdaq_quote: Optional[dict] = None,
) -> dict:
    """Args: *_history are most-recent-first OHLCV, 250+ days preferred."""
    sp500_result = _evaluate_index("S&P 500", sp500_history, sp500_quote)
    nasdaq_result = _evaluate_index("NASDAQ", nasdaq_history, nasdaq_quote)

    scores = []
    if sp500_result.get("data_available", False):
        scores.append(sp500_result["raw_score"])
    if nasdaq_result.get("data_available", False):
        scores.append(nasdaq_result["raw_score"])

    if not scores:
        return {
            "score": 50,
            "signal": "NO DATA: Index data unavailable",
            "sp500": sp500_result,
            "nasdaq": nasdaq_result,
            "data_available": False,
        }

    avg_score = sum(scores) / len(scores)
    final_score = round(min(100, max(0, avg_score)))

    if final_score >= 70:
        signal = "CRITICAL: Major technical breakdown"
    elif final_score >= 50:
        signal = "WARNING: Significant technical deterioration"
    elif final_score >= 35:
        signal = "CAUTION: Short-term weakness detected"
    elif final_score >= 15:
        signal = "MIXED: Minor technical concerns"
    else:
        signal = "HEALTHY: Technical structure intact"

    return {
        "score": final_score,
        "signal": signal,
        "sp500": sp500_result,
        "nasdaq": nasdaq_result,
        "data_available": True,
    }


def _evaluate_index(name: str, history: list, quote: Optional[dict] = None) -> dict:
    if not history or len(history) < 21:
        return {"raw_score": 0, "flags": ["Insufficient data"], "mas": {}, "data_available": False}

    closes = [d.get("close", d.get("adjClose", 0)) for d in history]
    highs = [d.get("high", d.get("close", 0)) for d in history]
    volumes = [d.get("volume", 0) for d in history]

    price = quote.get("price", closes[0]) if quote else closes[0]

    score = 0
    flags = []
    mas = {}

    ema21 = calc_ema(closes, 21)
    mas["ema21"] = round(ema21, 2)

    ema50 = calc_ema(closes, 50) if len(closes) >= 50 else None
    if ema50 is not None:
        mas["ema50"] = round(ema50, 2)

    sma200 = sum(closes[:200]) / 200 if len(closes) >= 200 else None
    if sma200 is not None:
        mas["sma200"] = round(sma200, 2)

    if price < ema21:
        score += 8
        flags.append(f"Below 21 EMA ({(price - ema21) / ema21 * 100:+.1f}%)")

    if ema50 and price < ema50:
        score += 12
        flags.append(f"Below 50 EMA ({(price - ema50) / ema50 * 100:+.1f}%)")

    if ema50 and ema21 < ema50:
        score += 10
        flags.append("21 EMA < 50 EMA (bearish crossover)")

    if sma200 and price < sma200:
        score += 15
        flags.append(f"Below 200 SMA ({(price - sma200) / sma200 * 100:+.1f}%)")

    if _detect_failed_rally(closes):
        score += 10
        flags.append("Failed rally pattern detected")

    if _detect_lower_highs(highs, lookback=20):
        score += 10
        flags.append("Lower highs pattern (20 day)")

    if _detect_gap_down(history):
        score += 10
        flags.append("Recent gap down on volume")

    return {
        "raw_score": min(100, score),
        "price": round(price, 2),
        "flags": flags,
        "mas": mas,
        "data_available": True,
    }


def _detect_failed_rally(closes: list, lookback: int = 15) -> bool:
    """Detect failed rally: price bounces then fails to make new high
    within recent lookback period."""
    if len(closes) < lookback:
        return False
    recent = closes[:lookback]
    peak_idx = recent.index(max(recent))
    if 3 <= peak_idx <= 10:
        drop = (recent[0] - recent[peak_idx]) / recent[peak_idx] * 100
        if drop < -2.0:
            return True
    return False


def _detect_lower_highs(highs: list, lookback: int = 20) -> bool:
    if len(highs) < lookback:
        return False
    recent_highs = highs[:lookback]
    swing_highs = []
    for i in range(1, len(recent_highs) - 1):
        if recent_highs[i] > recent_highs[i - 1] and recent_highs[i] > recent_highs[i + 1]:
            swing_highs.append(recent_highs[i])
    if len(swing_highs) < 2:
        return False
    return swing_highs[0] < swing_highs[1]


def _detect_gap_down(history: list, lookback: int = 5) -> bool:
    if len(history) < lookback + 1:
        return False
    for i in range(lookback):
        today = history[i]
        yesterday = history[i + 1]
        today_open = today.get("open", 0)
        yesterday_close = yesterday.get("close", yesterday.get("adjClose", 0))
        today_volume = today.get("volume", 0)
        yesterday_volume = yesterday.get("volume", 0)
        if yesterday_close == 0 or yesterday_volume == 0:
            continue
        gap_pct = (today_open - yesterday_close) / yesterday_close * 100
        volume_increase = today_volume > yesterday_volume * 1.1
        if gap_pct <= -0.5 and volume_increase:
            return True
    return False
