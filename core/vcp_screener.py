"""
vcp_screener.py -- Mark Minervini's Volatility Contraction Pattern (VCP)
detection: relative strength, 7-point Trend Template (Stage 2 filter),
ATR-based swing/contraction detection, volume dry-up analysis, pivot
proximity/risk, execution-state gating, and pattern classification,
combined into a weighted composite score. Ported from claude-trading-skills'
vcp-screener skill (vendor/claude-trading-skills/skills/vcp-screener/scripts/
{screen_vcp.py,scorer.py,calculators/*.py}, MIT License, Copyright (c) 2026 TraderMonty).

Entirely price-history-based -- no FMP/fundamentals/institutional data
needed at all, unlike most of this session's other FMP-adjacent ports.
Only the single-stock `analyze_stock()` pipeline is ported; the skill's
own FMP-universe-scan input mode, historical_scanner.py (forward-outcome
backtest harness) and report_generator.py were not.

All price lists are MOST-RECENT-FIRST (the convention this module's own
source uses throughout), matching core/stockbee_exhaustion_hammer_screener.py.
"""
from __future__ import annotations

from typing import Optional

# ── relative_strength_calculator.py ──────────────────────────────────────

RS_PERIODS = [(63, 0.40), (126, 0.20), (189, 0.20), (252, 0.20)]


def _period_return(closes: list, period: int) -> float:
    if len(closes) <= period or closes[period] <= 0:
        return 0.0
    return (closes[0] - closes[period]) / closes[period] * 100


def _score_rs(weighted_rs: float) -> tuple:
    if weighted_rs >= 50:
        return 100, 99
    elif weighted_rs >= 30:
        return 95, 95
    elif weighted_rs >= 20:
        return 90, 90
    elif weighted_rs >= 10:
        return 80, 80
    elif weighted_rs >= 5:
        return 70, 70
    elif weighted_rs >= 0:
        return 60, 60
    elif weighted_rs >= -5:
        return 50, 50
    elif weighted_rs >= -10:
        return 40, 40
    elif weighted_rs >= -20:
        return 20, 25
    return 0, 10


def calculate_relative_strength(stock_prices: list, sp500_prices: list) -> dict:
    """Minervini-weighted RS vs S&P 500. *_prices: most-recent-first, need 63+ days."""
    if not stock_prices or len(stock_prices) < 63:
        return {"score": 0, "rs_rank_estimate": 0, "weighted_rs": None, "error": "Insufficient stock price data (need 63+ days)"}
    if not sp500_prices or len(sp500_prices) < 63:
        return {"score": 0, "rs_rank_estimate": 0, "weighted_rs": None, "error": "Insufficient S&P 500 price data (need 63+ days)"}

    stock_closes = [d.get("close", d.get("adjClose", 0)) for d in stock_prices]
    sp500_closes = [d.get("close", d.get("adjClose", 0)) for d in sp500_prices]

    weighted_rs, total_weight = 0.0, 0.0
    period_details = []

    for period_days, weight in RS_PERIODS:
        if len(stock_closes) > period_days and len(sp500_closes) > period_days:
            stock_return = _period_return(stock_closes, period_days)
            sp500_return = _period_return(sp500_closes, period_days)
            relative = stock_return - sp500_return
            weighted_rs += relative * weight
            total_weight += weight
            period_details.append({"period_days": period_days, "weight": weight,
                "stock_return_pct": round(stock_return, 2), "sp500_return_pct": round(sp500_return, 2), "relative_pct": round(relative, 2)})
        elif len(stock_closes) > period_days // 2 and len(sp500_closes) > period_days // 2:
            available = min(len(stock_closes) - 1, len(sp500_closes) - 1)
            stock_return = _period_return(stock_closes, available)
            sp500_return = _period_return(sp500_closes, available)
            relative = stock_return - sp500_return
            reduced_weight = weight * 0.5
            weighted_rs += relative * reduced_weight
            total_weight += reduced_weight
            period_details.append({"period_days": period_days, "weight": reduced_weight,
                "stock_return_pct": round(stock_return, 2), "sp500_return_pct": round(sp500_return, 2),
                "relative_pct": round(relative, 2), "note": f"Partial data ({available} days available)"})

    if total_weight <= 0:
        return {"score": 0, "rs_rank_estimate": 0, "weighted_rs": None, "error": "Unable to calculate weighted RS (insufficient overlapping data)"}

    weighted_rs = weighted_rs / total_weight
    score, rs_rank = _score_rs(weighted_rs)
    return {"score": score, "rs_rank_estimate": rs_rank, "weighted_rs": round(weighted_rs, 2), "period_details": period_details, "error": None}


# ── trend_template_calculator.py ─────────────────────────────────────────

def _sma(prices: list, period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    return sum(prices[:period]) / period


def _calculate_extended_penalty(price: float, sma50: Optional[float], base_threshold: float = 8.0) -> tuple:
    if sma50 is None or sma50 <= 0:
        return 0, None
    distance_pct = (price - sma50) / sma50 * 100
    if distance_pct < base_threshold:
        return 0, distance_pct
    excess = distance_pct - base_threshold
    if excess >= 17:
        return -20, distance_pct
    elif excess >= 10:
        return -15, distance_pct
    elif excess >= 4:
        return -10, distance_pct
    return -5, distance_pct


def _calculate_sma200_penalty(price: float, sma200: Optional[float], max_extension: float = 50.0) -> tuple:
    if sma200 is None or sma200 <= 0:
        return 0, None
    distance_pct = (price - sma200) / sma200 * 100
    if distance_pct <= max_extension:
        return 0, distance_pct
    excess = distance_pct - max_extension
    if excess >= 20:
        return -20, distance_pct
    elif excess >= 10:
        return -15, distance_pct
    return -10, distance_pct


def calculate_trend_template(historical_prices: list, quote_data: dict, rs_rank: Optional[int] = None,
                               ext_threshold: float = 8.0, max_sma200_extension: float = 50.0) -> dict:
    """Minervini's 7-point Stage 2 filter. historical_prices: most-recent-first, need 50+ days."""
    if not historical_prices or len(historical_prices) < 50:
        return {"score": 0, "passed": False, "criteria": {}, "error": "Insufficient historical data (need 50+ days)"}

    closes = [d.get("close", d.get("adjClose", 0)) for d in historical_prices]
    price = quote_data.get("price", closes[0] if closes else 0)
    year_high = quote_data.get("yearHigh", 0)
    year_low = quote_data.get("yearLow", 0)

    criteria = {}
    sma150, sma200, sma50 = _sma(closes, 150), _sma(closes, 200), _sma(closes, 50)

    c1_pass = False
    if sma150 is not None and sma200 is not None:
        c1_pass = price > sma150 and price > sma200
    elif sma150 is not None:
        c1_pass = price > sma150
    criteria["c1_price_above_sma150_200"] = {"passed": c1_pass, "detail": f"Price ${price:.2f} vs SMA150 ${sma150:.2f}" if sma150 is not None else "Insufficient data for SMA150"}

    c2_pass = sma150 is not None and sma200 is not None and sma150 > sma200
    criteria["c2_sma150_above_sma200"] = {"passed": c2_pass, "detail": f"SMA150 ${sma150:.2f} vs SMA200 ${sma200:.2f}" if sma150 and sma200 else "Insufficient data"}

    c3_pass = False
    if len(closes) >= 222 and sma200 is not None:
        sma200_22d_ago = _sma(closes[22:], 200)
        if sma200_22d_ago is not None:
            c3_pass = sma200 > sma200_22d_ago
            criteria["c3_sma200_trending_up"] = {"passed": c3_pass, "detail": f"SMA200 today ${sma200:.2f} vs 22d ago ${sma200_22d_ago:.2f}"}
        else:
            criteria["c3_sma200_trending_up"] = {"passed": False, "detail": "Insufficient data for 22d SMA200 comparison"}
    elif sma200 is not None and len(closes) >= 200:
        criteria["c3_sma200_trending_up"] = {"passed": False, "detail": f"Cannot verify 22d SMA200 trend (only {len(closes)} days available, need 222+)"}
    else:
        criteria["c3_sma200_trending_up"] = {"passed": False, "detail": "Insufficient data"}

    c4_pass = sma50 is not None and price > sma50
    criteria["c4_price_above_sma50"] = {"passed": c4_pass, "detail": f"Price ${price:.2f} vs SMA50 ${sma50:.2f}" if sma50 else "Insufficient data"}

    c5_pass = False
    if year_low > 0:
        pct_above_low = (price - year_low) / year_low * 100
        c5_pass = pct_above_low >= 25
        criteria["c5_25pct_above_52w_low"] = {"passed": c5_pass, "detail": f"{pct_above_low:.1f}% above 52w low ${year_low:.2f} (need >= 25%)"}
    else:
        criteria["c5_25pct_above_52w_low"] = {"passed": False, "detail": "52-week low data unavailable"}

    c6_pass = False
    if year_high > 0:
        pct_below_high = (year_high - price) / year_high * 100
        c6_pass = pct_below_high <= 25
        criteria["c6_within_25pct_52w_high"] = {"passed": c6_pass, "detail": f"{pct_below_high:.1f}% below 52w high ${year_high:.2f} (need <= 25%)"}
    else:
        criteria["c6_within_25pct_52w_high"] = {"passed": False, "detail": "52-week high data unavailable"}

    c7_pass = rs_rank is not None and rs_rank > 70
    criteria["c7_rs_rank_above_70"] = {"passed": c7_pass, "detail": f"RS Rank: {rs_rank} (need > 70)" if rs_rank is not None else "RS Rank not yet calculated"}

    passed_count = sum(1 for c in criteria.values() if c["passed"])
    raw_score = min(100, round(passed_count * 14.3, 1))
    passed = raw_score >= 85

    extended_penalty, sma50_distance_pct = _calculate_extended_penalty(price, sma50, base_threshold=ext_threshold)
    sma200_penalty, sma200_distance_pct = _calculate_sma200_penalty(price, sma200, max_extension=max_sma200_extension)
    score = max(0, raw_score + extended_penalty)

    return {
        "score": score, "raw_score": raw_score, "passed": passed, "extended_penalty": extended_penalty,
        "sma200_penalty": sma200_penalty,
        "sma50_distance_pct": round(sma50_distance_pct, 2) if sma50_distance_pct is not None else None,
        "sma200_distance_pct": round(sma200_distance_pct, 2) if sma200_distance_pct is not None else None,
        "criteria_passed": passed_count, "criteria_total": 7, "criteria": criteria,
        "sma50": round(sma50, 2) if sma50 else None, "sma150": round(sma150, 2) if sma150 else None,
        "sma200": round(sma200, 2) if sma200 else None, "error": None,
    }


# ── vcp_pattern_calculator.py ─────────────────────────────────────────────

def _calculate_atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """highs/lows/closes: chronological (oldest first)."""
    n = len(highs)
    if n < period + 1:
        return 0.0
    true_ranges = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])) for i in range(1, n)]
    if len(true_ranges) < period:
        return 0.0
    return sum(true_ranges[-period:]) / period


def _zigzag_swing_points(highs: list, lows: list, closes: list, dates: list, atr_multiplier: float = 1.5, atr_period: int = 14) -> tuple:
    n = len(highs)
    if n < atr_period + 1:
        return [], []
    atr = _calculate_atr(highs, lows, closes, atr_period)
    if atr <= 0:
        return [], []
    threshold = atr * atr_multiplier

    swing_highs, swing_lows = [], []
    extreme_idx, extreme_val = 0, highs[0]
    for i in range(min(atr_period, n)):
        if highs[i] > extreme_val:
            extreme_val, extreme_idx = highs[i], i

    direction = 1
    extreme_val = highs[extreme_idx]
    for i in range(extreme_idx + 1, n):
        if direction == 1:
            if highs[i] > extreme_val:
                extreme_val, extreme_idx = highs[i], i
            elif extreme_val - lows[i] >= threshold:
                swing_highs.append((extreme_idx, extreme_val))
                direction, extreme_val, extreme_idx = -1, lows[i], i
        else:
            if lows[i] < extreme_val:
                extreme_val, extreme_idx = lows[i], i
            elif highs[i] - extreme_val >= threshold:
                swing_lows.append((extreme_idx, extreme_val))
                direction, extreme_val, extreme_idx = 1, highs[i], i
    return swing_highs, swing_lows


def _find_swing_highs(highs: list, window: int = 5) -> list:
    out = []
    for i in range(window, len(highs) - window):
        if all(highs[i] > highs[i - j] and highs[i] > highs[i + j] for j in range(1, window + 1)):
            out.append((i, highs[i]))
    return out


def _find_swing_lows(lows: list, window: int = 5) -> list:
    out = []
    for i in range(window, len(lows) - window):
        if all(lows[i] < lows[i - j] and lows[i] < lows[i + j] for j in range(1, window + 1)):
            out.append((i, lows[i]))
    return out


def _build_contractions_from(start_high: tuple, swing_highs: list, swing_lows: list, highs: list, lows: list, dates: list, min_contraction_days: int = 5) -> list:
    h1_idx, h1_val = start_high
    contractions = []
    current_high_idx, current_high_val = h1_idx, h1_val

    for _ in range(4):
        next_low = next(((idx, val) for idx, val in swing_lows if idx > current_high_idx), None)
        if next_low is None:
            break
        low_idx, low_val = next_low
        duration = low_idx - current_high_idx

        if duration < min_contraction_days:
            next_high_boundary = next((idx for idx, _ in swing_highs if idx > current_high_idx), None)
            found_valid = False
            for idx, val in swing_lows:
                if idx > current_high_idx and (idx - current_high_idx) >= min_contraction_days:
                    if next_high_boundary is not None and idx > next_high_boundary:
                        break
                    low_idx, low_val = idx, val
                    duration = low_idx - current_high_idx
                    found_valid = True
                    break
            if not found_valid:
                break

        depth_pct = (current_high_val - low_val) / current_high_val * 100 if current_high_val > 0 else 0

        if contractions:
            pct_from_h1 = abs(current_high_val - h1_val) / h1_val * 100
            if pct_from_h1 > 5:
                break

        contractions.append({
            "label": f"T{len(contractions) + 1}", "high_idx": current_high_idx, "high_price": round(current_high_val, 2),
            "high_date": dates[current_high_idx] if current_high_idx < len(dates) else "N/A",
            "low_idx": low_idx, "low_price": round(low_val, 2), "low_date": dates[low_idx] if low_idx < len(dates) else "N/A",
            "depth_pct": round(depth_pct, 2), "duration_days": duration,
        })

        next_high = next(((idx, val) for idx, val in swing_highs if idx > low_idx), None)
        if next_high is None:
            break
        current_high_idx, current_high_val = next_high

    return contractions


def _validate_vcp(contractions: list, total_days: int, min_contractions: int = 2, t1_depth_min: float = 8.0, contraction_ratio: float = 0.75) -> dict:
    if len(contractions) < min_contractions:
        return {"valid": False, "issues": [f"Need at least {min_contractions} contractions"]}

    issues, valid = [], True
    t1_depth = contractions[0]["depth_pct"]
    if t1_depth < t1_depth_min:
        issues.append(f"T1 depth too shallow ({t1_depth:.1f}%, need >= {t1_depth_min}%)")
        valid = False
    elif t1_depth > 35:
        issues.append(f"T1 depth too deep ({t1_depth:.1f}%, prefer <= 35%)")

    contraction_ratios = []
    for i in range(1, len(contractions)):
        prev_depth, curr_depth = contractions[i - 1]["depth_pct"], contractions[i]["depth_pct"]
        if prev_depth > 0:
            ratio = curr_depth / prev_depth
            contraction_ratios.append(ratio)
            if ratio > contraction_ratio:
                issues.append(f"{contractions[i]['label']} ({curr_depth:.1f}%) does not contract vs {contractions[i-1]['label']} ({prev_depth:.1f}%), ratio={ratio:.2f} (need <= {contraction_ratio})")
                valid = False

    for i in range(1, len(contractions)):
        curr_high = contractions[i]["high_price"]
        pct_diff = abs(curr_high - contractions[0]["high_price"]) / contractions[0]["high_price"] * 100 if contractions[0]["high_price"] > 0 else 0
        if pct_diff > 5:
            issues.append(f"{contractions[i]['label']} high ${curr_high:.2f} is {pct_diff:.1f}% from H1 ${contractions[0]['high_price']:.2f}")

    if len(contractions) >= 2:
        duration = contractions[-1]["low_idx"] - contractions[0]["high_idx"]
        if duration < 15:
            issues.append(f"Pattern too short ({duration} days, need >= 15)")
            valid = False
        elif duration > 325:
            issues.append(f"Pattern too long ({duration} days, prefer <= 325)")

    return {"valid": valid, "issues": issues, "contraction_ratios": [round(r, 3) for r in contraction_ratios], "t1_depth": t1_depth}


def _compute_wide_and_loose(contractions: list, threshold: float) -> bool:
    if not contractions:
        return False
    final = contractions[-1]
    return final.get("depth_pct", 0.0) > threshold and final.get("duration_days", 999) < 10


def _get_pivot_price(contractions: list, highs: list, swing_highs: list) -> Optional[float]:
    if contractions:
        return contractions[-1]["high_price"]
    if swing_highs:
        return swing_highs[-1][1]
    return None


def _score_vcp(contractions: list, validation: dict) -> int:
    if not validation["valid"]:
        return min(40, len(contractions) * 15)

    num = len(contractions)
    if num >= 4:
        base = 90
    elif num >= 3:
        base = 80
    elif num >= 2:
        base = 60
    else:
        return 20

    score = base
    if contractions[-1]["depth_pct"] < 5:
        score += 10
    ratios = validation.get("contraction_ratios", [])
    if ratios and sum(ratios) / len(ratios) < 0.4:
        score += 10
    if validation.get("t1_depth", 0) > 30:
        score -= 10
    return max(0, min(100, score))


def calculate_vcp_pattern(historical_prices: list, lookback_days: int = 120, atr_multiplier: float = 1.5, atr_period: int = 14,
                            min_contraction_days: int = 5, min_contractions: int = 2, t1_depth_min: float = 8.0,
                            contraction_ratio: float = 0.75, wide_and_loose_threshold: float = 15.0) -> dict:
    """Detect VCP. historical_prices: most-recent-first, need 30+ days."""
    empty_result = {"score": 0, "valid_vcp": False, "contractions": [], "num_contractions": 0, "pivot_price": None,
                     "atr_compression_ratio": None, "wide_and_loose": False, "right_side_range_ratio": None, "error": None}

    if not historical_prices or len(historical_prices) < 30:
        empty_result["error"] = "Insufficient data (need 30+ days)"
        return empty_result

    prices = list(reversed(historical_prices[:lookback_days]))  # chronological
    n = len(prices)
    if n < 30:
        empty_result["error"] = "Insufficient data in lookback window"
        return empty_result

    highs = [d.get("high", d.get("close", 0)) for d in prices]
    lows = [d.get("low", d.get("close", 0)) for d in prices]
    closes = [d.get("close", 0) for d in prices]
    dates = [d.get("date", f"day-{i}") for i, d in enumerate(prices)]

    atr_val = _calculate_atr(highs, lows, closes, atr_period)
    atr_10 = _calculate_atr(highs, lows, closes, 10)
    atr_50 = _calculate_atr(highs, lows, closes, 50)
    zz_highs, zz_lows = _zigzag_swing_points(highs, lows, closes, dates, atr_multiplier, atr_period)

    if len(zz_highs) >= 1 and len(zz_lows) >= 1:
        swing_highs, swing_lows = zz_highs, zz_lows
    else:
        swing_highs, swing_lows = _find_swing_highs(highs, window=5), _find_swing_lows(lows, window=5)

    if len(swing_highs) < 1 or len(swing_lows) < 1:
        empty_result["error"] = "Insufficient swing points detected"
        return empty_result

    sorted_highs = sorted(swing_highs, key=lambda x: x[1], reverse=True)
    best_contractions, best_score, best_valid = [], -1, False

    for start_high in sorted_highs[:3]:
        candidate = _build_contractions_from(start_high, swing_highs, swing_lows, highs, lows, dates, min_contraction_days=min_contraction_days)
        if len(candidate) >= min_contractions:
            v = _validate_vcp(candidate, n, min_contractions, t1_depth_min, contraction_ratio)
            s = _score_vcp(candidate, v)
        else:
            v, s = {"valid": False}, 0
        key = (int(v.get("valid", False)), s, len(candidate))
        best_key = (int(best_valid), best_score, len(best_contractions))
        if key > best_key:
            best_contractions, best_score, best_valid = candidate, s, v.get("valid", False)

    contractions = best_contractions
    if len(contractions) < min_contractions:
        atr_compression_ratio = (atr_10 / atr_50) if (atr_50 > 0 and atr_10 > 0) else None
        return {"score": 0, "valid_vcp": False, "contractions": contractions, "num_contractions": len(contractions),
                "pivot_price": _get_pivot_price(contractions, highs, swing_highs), "atr_value": round(atr_val, 4) if atr_val else None,
                "atr_compression_ratio": round(atr_compression_ratio, 3) if atr_compression_ratio is not None else None,
                "wide_and_loose": False, "right_side_range_ratio": None, "error": f"Fewer than {min_contractions} contractions found"}

    validation = _validate_vcp(contractions, n, min_contractions, t1_depth_min, contraction_ratio)
    pivot_price = _get_pivot_price(contractions, highs, swing_highs)
    pattern_duration = contractions[-1]["low_idx"] - contractions[0]["high_idx"]
    score = _score_vcp(contractions, validation)

    atr_compression_ratio = (atr_10 / atr_50) if (atr_10 > 0 and atr_50 > 0) else None
    wide_and_loose = _compute_wide_and_loose(contractions, wide_and_loose_threshold)

    right_side_range_ratio = None
    if atr_50 > 0 and n >= 15:
        right_side_range_ratio = (max(highs[-15:]) - min(lows[-15:])) / atr_50

    return {
        "score": score, "valid_vcp": validation["valid"], "contractions": contractions, "num_contractions": len(contractions),
        "pivot_price": round(pivot_price, 2) if pivot_price else None, "pattern_duration_days": pattern_duration,
        "validation": validation, "atr_value": round(atr_val, 4) if atr_val else None,
        "atr_compression_ratio": round(atr_compression_ratio, 3) if atr_compression_ratio is not None else None,
        "wide_and_loose": wide_and_loose,
        "right_side_range_ratio": round(right_side_range_ratio, 3) if right_side_range_ratio is not None else None,
        "error": None,
    }


# ── volume_pattern_calculator.py ──────────────────────────────────────────

def _zone_volume_analysis(volumes: list, closes: list, contractions: list, pivot_price: Optional[float], avg_volume_50d: float) -> tuple:
    n = len(volumes)
    last_c = contractions[-1]
    zone_a_start_rev, zone_a_end_rev = n - 1 - last_c["low_idx"], n - 1 - last_c["high_idx"]
    zone_a_start, zone_a_end = min(zone_a_start_rev, zone_a_end_rev), max(zone_a_start_rev, zone_a_end_rev)
    zone_a_vols = volumes[max(0, zone_a_start):min(n, zone_a_end + 1)]
    zone_a_avg = int(sum(zone_a_vols) / len(zone_a_vols)) if zone_a_vols else 0

    zone_b_vols = volumes[1:min(11, n)]
    zone_b_avg = int(sum(zone_b_vols) / len(zone_b_vols)) if zone_b_vols else 0

    zone_c_vol = zone_c_ratio = None
    if pivot_price and n > 0 and closes[0] > pivot_price:
        zone_c_vol = volumes[0]
        zone_c_ratio = round(zone_c_vol / avg_volume_50d, 3) if avg_volume_50d > 0 else None

    zone_analysis = {
        "zone_a_avg_volume": zone_a_avg, "zone_a_ratio": round(zone_a_avg / avg_volume_50d, 3) if avg_volume_50d > 0 else None,
        "zone_b_avg_volume": zone_b_avg, "zone_b_ratio": round(zone_b_avg / avg_volume_50d, 3) if avg_volume_50d > 0 else None,
        "zone_c_volume": zone_c_vol, "zone_c_ratio": zone_c_ratio,
    }

    contraction_avgs = []
    for c in contractions:
        c_start_rev, c_end_rev = n - 1 - c["low_idx"], n - 1 - c["high_idx"]
        c_start, c_end = min(c_start_rev, c_end_rev), max(c_start_rev, c_end_rev)
        c_vols = volumes[max(0, c_start):min(n, c_end + 1)]
        if c_vols:
            contraction_avgs.append(int(sum(c_vols) / len(c_vols)))

    declining = len(contraction_avgs) >= 2 and all(contraction_avgs[i] > contraction_avgs[i + 1] for i in range(len(contraction_avgs) - 1))
    return zone_analysis, {"declining": declining, "contraction_volumes": contraction_avgs}


def calculate_volume_pattern(historical_prices: list, pivot_price: Optional[float] = None, contractions: Optional[list] = None, breakout_volume_ratio: float = 1.5) -> dict:
    """historical_prices: most-recent-first, need 20+ days."""
    if not historical_prices or len(historical_prices) < 20:
        return {"score": 0, "dry_up_ratio": None, "error": "Insufficient data (need 20+ days)"}

    volumes = [d.get("volume", 0) for d in historical_prices]
    closes = [d.get("close", d.get("adjClose", 0)) for d in historical_prices]

    vol_period = min(50, len(volumes))
    avg_volume_50d = sum(volumes[:vol_period]) / vol_period if vol_period > 0 else 0
    if avg_volume_50d <= 0:
        return {"score": 0, "dry_up_ratio": None, "error": "No volume data available"}

    zone_analysis = contraction_volume_trend = None
    use_zone = contractions is not None and len(contractions) >= 1
    if use_zone:
        zone_analysis, contraction_volume_trend = _zone_volume_analysis(volumes, closes, contractions, pivot_price, avg_volume_50d)

    if use_zone and zone_analysis and zone_analysis.get("zone_b_avg_volume"):
        avg_volume_recent = zone_analysis["zone_b_avg_volume"]
    else:
        legacy_vols = volumes[1:11] if len(volumes) > 1 else []
        avg_volume_recent = sum(legacy_vols) / len(legacy_vols) if legacy_vols else 0

    dry_up_ratio = avg_volume_recent / avg_volume_50d if avg_volume_50d > 0 else 1.0

    if dry_up_ratio < 0.30:
        base_score = 90
    elif dry_up_ratio < 0.50:
        base_score = 75
    elif dry_up_ratio < 0.70:
        base_score = 60
    elif dry_up_ratio <= 1.00:
        base_score = 40
    else:
        base_score = 20
    score = base_score

    breakout_volume, breakout_volume_score = False, 0
    current_price = closes[0] if closes else 0
    if len(volumes) >= 1 and avg_volume_50d > 0:
        bar0_ratio = volumes[0] / avg_volume_50d
        if pivot_price and current_price > pivot_price:
            if bar0_ratio >= breakout_volume_ratio:
                breakout_volume = True
                score += 10
            if bar0_ratio >= 3.0:
                breakout_volume_score = 100
            elif bar0_ratio >= 2.0:
                breakout_volume_score = 80
            elif bar0_ratio >= breakout_volume_ratio:
                breakout_volume_score = 60
            elif bar0_ratio >= 1.0:
                breakout_volume_score = 30

    up_vol_days = down_vol_days = 0
    analysis_period = min(20, len(closes) - 1)
    for i in range(analysis_period):
        if i + 1 < len(closes) and volumes[i] > avg_volume_50d:
            if closes[i] > closes[i + 1]:
                up_vol_days += 1
            elif closes[i] < closes[i + 1]:
                down_vol_days += 1

    net_accumulation = up_vol_days - down_vol_days
    if net_accumulation > 3:
        score += 10
    elif net_accumulation < -3:
        score -= 10

    if contraction_volume_trend and contraction_volume_trend.get("declining"):
        score += 10

    score = max(0, min(100, score))
    result = {
        "score": score, "dry_up_ratio": round(dry_up_ratio, 3), "avg_volume_50d": int(avg_volume_50d),
        "avg_volume_recent_10d": int(avg_volume_recent), "breakout_volume_detected": breakout_volume,
        "breakout_volume_score": breakout_volume_score, "up_volume_days_20d": up_vol_days,
        "down_volume_days_20d": down_vol_days, "net_accumulation": net_accumulation, "error": None,
    }
    if zone_analysis is not None:
        result["zone_analysis"] = zone_analysis
    if contraction_volume_trend is not None:
        result["contraction_volume_trend"] = contraction_volume_trend
    return result


# ── pivot_proximity_calculator.py ─────────────────────────────────────────

def calculate_pivot_proximity(current_price: float, pivot_price: Optional[float], last_contraction_low: Optional[float] = None, breakout_volume: bool = False) -> dict:
    if not pivot_price or pivot_price <= 0:
        return {"score": 0, "distance_from_pivot_pct": None, "stop_loss_price": None, "risk_pct": None, "trade_status": "NO PIVOT", "error": "No valid pivot price"}
    if current_price <= 0:
        return {"score": 0, "distance_from_pivot_pct": None, "stop_loss_price": None, "risk_pct": None, "trade_status": "INVALID PRICE", "error": "Invalid current price"}

    distance_pct = (current_price - pivot_price) / pivot_price * 100

    if distance_pct > 20:
        score, trade_status = 20, "OVEREXTENDED - Do not chase"
    elif distance_pct > 10:
        score, trade_status = 35, "EXTENDED - Very high chase risk"
    elif distance_pct > 5:
        score, trade_status = 50, "EXTENDED - High chase risk"
    elif distance_pct > 3:
        score, trade_status = 65, "EXTENDED - Moderate chase risk"
    elif distance_pct > 0:
        score, trade_status = 90, "ABOVE PIVOT (within 3%)"
    elif distance_pct >= -2:
        score, trade_status = 90, "AT PIVOT (within 2%)"
    elif distance_pct >= -5:
        score, trade_status = 75, "NEAR PIVOT (2-5% below)"
    elif distance_pct >= -8:
        score, trade_status = 60, "APPROACHING (5-8% below)"
    elif distance_pct >= -10:
        score, trade_status = 45, "DEVELOPING (8-10% below)"
    elif distance_pct >= -15:
        score, trade_status = 30, "EARLY (10-15% below)"
    else:
        score, trade_status = 10, "FAR FROM PIVOT (>15% below)"

    if breakout_volume and distance_pct > 0:
        if distance_pct <= 3:
            score += 10
            trade_status = "BREAKOUT CONFIRMED"
        elif distance_pct <= 5:
            score += 10
            trade_status += " (vol confirmed)"

    stop_loss_price = risk_pct = None
    if last_contraction_low and last_contraction_low > 0:
        stop_loss_price = round(last_contraction_low * 0.99, 2)
        if current_price > stop_loss_price:
            risk_pct = round((current_price - stop_loss_price) / current_price * 100, 2)
        else:
            risk_pct, trade_status, score = None, "BELOW STOP LEVEL", 0

    return {"score": score, "distance_from_pivot_pct": round(distance_pct, 2), "pivot_price": round(pivot_price, 2),
            "stop_loss_price": stop_loss_price, "risk_pct": risk_pct, "trade_status": trade_status, "error": None}


# ── execution_state.py ────────────────────────────────────────────────────

STATE_ORDER = ["Invalid", "Damaged", "Overextended", "Extended", "Early-post-breakout", "Breakout", "Pre-breakout"]
STATE_MAX_RATING = {"Invalid": "No VCP", "Damaged": "No VCP", "Overextended": "Weak VCP", "Extended": "Developing VCP",
                     "Early-post-breakout": "Strong VCP", "Breakout": None, "Pre-breakout": None}
RATING_ORDER = ["No VCP", "Weak VCP", "Developing VCP", "Good VCP", "Strong VCP", "Textbook VCP"]


def compute_execution_state(distance_from_pivot_pct: Optional[float], price: float, sma50: Optional[float], sma200: Optional[float],
                              sma200_distance_pct: Optional[float], last_contraction_low: Optional[float], breakout_volume: bool,
                              max_sma200_extension: float = 50.0) -> dict:
    reasons = []

    if sma50 is not None and sma200 is not None and price < sma50 and sma50 < sma200:
        reasons.append(f"Price ${price:.2f} < SMA50 ${sma50:.2f} < SMA200 ${sma200:.2f}")
        return {"state": "Invalid", "reasons": reasons}

    if last_contraction_low is not None and last_contraction_low > 0 and price < last_contraction_low:
        reasons.append(f"Price ${price:.2f} below last contraction low ${last_contraction_low:.2f}")
        return {"state": "Damaged", "reasons": reasons}

    if sma50 is not None and price < sma50:
        reasons.append(f"Price ${price:.2f} below SMA50 ${sma50:.2f}")
        return {"state": "Damaged", "reasons": reasons}

    if sma200_distance_pct is not None and sma200_distance_pct > max_sma200_extension:
        reasons.append(f"SMA200 distance {sma200_distance_pct:.1f}% > max {max_sma200_extension:.0f}%")
        return {"state": "Overextended", "reasons": reasons}

    if distance_from_pivot_pct is None:
        reasons.append("No pivot available")
        return {"state": "Pre-breakout", "reasons": reasons}

    if distance_from_pivot_pct > 10.0:
        reasons.append(f"+{distance_from_pivot_pct:.1f}% above pivot (> 10%)")
        return {"state": "Overextended", "reasons": reasons}
    if distance_from_pivot_pct > 5.0:
        reasons.append(f"+{distance_from_pivot_pct:.1f}% above pivot (5-10% zone)")
        return {"state": "Extended", "reasons": reasons}
    if distance_from_pivot_pct > 3.0:
        reasons.append(f"+{distance_from_pivot_pct:.1f}% above pivot (3-5% zone)")
        return {"state": "Early-post-breakout", "reasons": reasons}

    if distance_from_pivot_pct >= 0.0:
        if breakout_volume:
            reasons.append(f"+{distance_from_pivot_pct:.1f}% above pivot with volume confirmation")
            return {"state": "Breakout", "reasons": reasons}
        reasons.append(f"+{distance_from_pivot_pct:.1f}% above pivot (volume unconfirmed)")
        return {"state": "Early-post-breakout", "reasons": reasons}

    reasons.append(f"{distance_from_pivot_pct:.1f}% below pivot (forming pattern)")
    return {"state": "Pre-breakout", "reasons": reasons}


def apply_state_cap(rating: str, execution_state: str) -> tuple:
    max_rating = STATE_MAX_RATING.get(execution_state)
    if max_rating is None:
        return rating, False
    current_idx = RATING_ORDER.index(rating) if rating in RATING_ORDER else 0
    max_idx = RATING_ORDER.index(max_rating) if max_rating in RATING_ORDER else 0
    if current_idx > max_idx:
        return max_rating, True
    return rating, False


# ── pattern_classifier.py ──────────────────────────────────────────────────

def classify_pattern(valid_vcp: bool, num_contractions: int, final_contraction_depth: Optional[float], execution_state: str,
                       dry_up_ratio: Optional[float], wide_and_loose: bool = False) -> str:
    if execution_state in ("Invalid", "Damaged"):
        return "Damaged"
    if execution_state in ("Overextended", "Extended"):
        return "Extended Leader" if valid_vcp else "VCP-adjacent"
    if execution_state in ("Early-post-breakout", "Breakout"):
        return "Post-breakout" if valid_vcp else "VCP-adjacent"
    if not valid_vcp or wide_and_loose:
        return "VCP-adjacent"
    textbook = (num_contractions >= 3 and (final_contraction_depth is None or final_contraction_depth <= 10.0)
                and (dry_up_ratio is not None and dry_up_ratio <= 0.7) and execution_state == "Pre-breakout")
    return "Textbook VCP" if textbook else "VCP-adjacent"


# ── scorer.py ────────────────────────────────────────────────────────────

COMPONENT_WEIGHTS = {"trend_template": 0.25, "contraction_quality": 0.25, "volume_pattern": 0.20, "pivot_proximity": 0.15, "relative_strength": 0.15}
COMPONENT_LABELS = {"trend_template": "Trend Template (Stage 2)", "contraction_quality": "Contraction Quality",
                     "volume_pattern": "Volume Pattern", "pivot_proximity": "Pivot Proximity", "relative_strength": "Relative Strength"}

_RATING_TABLE = {
    "Textbook VCP": {"description": "Ideal VCP setup with all components aligned", "guidance": "Buy at pivot, aggressive position sizing (1.5-2x normal)"},
    "Strong VCP": {"description": "High-quality VCP with minor imperfections", "guidance": "Buy at pivot, standard position sizing"},
    "Good VCP": {"description": "Solid VCP pattern developing", "guidance": "Buy on volume confirmation above pivot"},
    "Developing VCP": {"description": "VCP forming but not yet actionable", "guidance": "Watchlist - wait for tighter contraction near pivot"},
    "Weak VCP": {"description": "Some VCP characteristics but incomplete", "guidance": "Monitor only - pattern needs more development"},
    "No VCP": {"description": "Does not qualify as a VCP setup", "guidance": "Not actionable as VCP"},
}


def _get_rating_info_for(rating: str) -> dict:
    info = _RATING_TABLE.get(rating, {"description": "", "guidance": ""})
    return {"rating": rating, **info}


def _get_rating(composite: float) -> dict:
    if composite >= 90:
        return _get_rating_info_for("Textbook VCP")
    elif composite >= 80:
        return _get_rating_info_for("Strong VCP")
    elif composite >= 70:
        return _get_rating_info_for("Good VCP")
    elif composite >= 60:
        return _get_rating_info_for("Developing VCP")
    elif composite >= 50:
        return _get_rating_info_for("Weak VCP")
    return _get_rating_info_for("No VCP")


def calculate_composite_score(trend_score: float, contraction_score: float, volume_score: float, pivot_score: float, rs_score: float,
                                valid_vcp: bool = True, execution_state: Optional[str] = None, pattern_type: Optional[str] = None,
                                wide_and_loose: bool = False, sma200_extension_pct: Optional[float] = None) -> dict:
    component_scores = {"trend_template": trend_score, "contraction_quality": contraction_score, "volume_pattern": volume_score,
                         "pivot_proximity": pivot_score, "relative_strength": rs_score}
    composite = round(sum(component_scores[k] * w for k, w in COMPONENT_WEIGHTS.items()), 1)

    weakest_key = min(component_scores, key=component_scores.get)
    strongest_key = max(component_scores, key=component_scores.get)

    rating_info = _get_rating(composite)
    if not valid_vcp and composite >= 70:
        rating_info = {"rating": "Developing VCP", "description": "VCP pattern not confirmed - contractions do not meet criteria",
                        "guidance": "Watchlist only - VCP pattern not validated, do not buy"}

    rating = rating_info["rating"]
    quality_rating = rating
    cap_applied, cap_reason = False, None

    if execution_state is not None:
        capped_rating, capped = apply_state_cap(rating, execution_state)
        if capped:
            cap_reason = f"State cap from {execution_state}: {rating} -> {capped_rating}"
            rating = capped_rating
            cap_applied = True
            rating_info = _get_rating_info_for(rating)

    if wide_and_loose and rating in ("Textbook VCP", "Strong VCP", "Good VCP"):
        cap_reason = (cap_reason or "") + f" | Wide-and-loose: {rating} -> Developing VCP"
        rating = "Developing VCP"
        cap_applied = True
        rating_info = _get_rating_info_for(rating)

    return {
        "composite_score": composite, "quality_rating": quality_rating, "rating": rating,
        "rating_description": rating_info["description"], "guidance": rating_info["guidance"],
        "valid_vcp": valid_vcp, "execution_state": execution_state, "pattern_type": pattern_type,
        "state_cap_applied": cap_applied, "cap_reason": cap_reason,
        "weakest_component": COMPONENT_LABELS[weakest_key], "weakest_score": component_scores[weakest_key],
        "strongest_component": COMPONENT_LABELS[strongest_key], "strongest_score": component_scores[strongest_key],
        "component_breakdown": {k: {"score": component_scores[k], "weight": w, "weighted": round(component_scores[k] * w, 1), "label": COMPONENT_LABELS[k]}
                                  for k, w in COMPONENT_WEIGHTS.items()},
    }


# ── screen_vcp.py's analyze_stock() ────────────────────────────────────────

def analyze_stock(symbol: str, historical: list, quote: dict, sp500_history: list, sector: str = "Unknown", company_name: str = "",
                    ext_threshold: float = 8.0, min_contractions: int = 2, t1_depth_min: float = 10.0, contraction_ratio: float = 0.70,
                    atr_multiplier: float = 1.5, min_contraction_days: int = 5, lookback_days: int = 120,
                    breakout_volume_ratio: float = 1.5, max_sma200_extension: float = 50.0, wide_and_loose_threshold: float = 15.0) -> Optional[dict]:
    """Full VCP analysis for a single stock. historical/sp500_history: most-recent-first."""
    price = quote.get("price", 0)
    market_cap = quote.get("marketCap", 0)

    rs_result = calculate_relative_strength(historical, sp500_history)
    rs_rank = rs_result.get("rs_rank_estimate", 0)

    tt_result = calculate_trend_template(historical, quote, rs_rank=rs_rank, ext_threshold=ext_threshold, max_sma200_extension=max_sma200_extension)

    vcp_result = calculate_vcp_pattern(historical, lookback_days=lookback_days, atr_multiplier=atr_multiplier,
                                         min_contraction_days=min_contraction_days, min_contractions=min_contractions,
                                         t1_depth_min=t1_depth_min, contraction_ratio=contraction_ratio, wide_and_loose_threshold=wide_and_loose_threshold)

    pivot_price = vcp_result.get("pivot_price")
    historical_lookback = historical[:lookback_days]
    vol_result = calculate_volume_pattern(historical_lookback, pivot_price=pivot_price, contractions=vcp_result.get("contractions"), breakout_volume_ratio=breakout_volume_ratio)

    contractions = vcp_result.get("contractions", [])
    last_low = contractions[-1].get("low_price") if contractions else None

    piv_result = calculate_pivot_proximity(current_price=price, pivot_price=pivot_price, last_contraction_low=last_low, breakout_volume=vol_result.get("breakout_volume_detected", False))

    sma200_tt = tt_result.get("sma200")
    sma200_distance_pct = (price - sma200_tt) / sma200_tt * 100 if sma200_tt and sma200_tt > 0 else None

    exec_state_result = compute_execution_state(
        distance_from_pivot_pct=piv_result.get("distance_from_pivot_pct"), price=price, sma50=tt_result.get("sma50"),
        sma200=sma200_tt, sma200_distance_pct=sma200_distance_pct, last_contraction_low=last_low,
        breakout_volume=vol_result.get("breakout_volume_detected", False), max_sma200_extension=max_sma200_extension,
    )
    execution_state = exec_state_result["state"]

    valid_vcp = vcp_result.get("valid_vcp", False)
    wide_and_loose = vcp_result.get("wide_and_loose", False)
    final_depth = contractions[-1].get("depth_pct") if contractions else None

    pattern_type = classify_pattern(valid_vcp=valid_vcp, num_contractions=vcp_result.get("num_contractions", 0),
                                      final_contraction_depth=final_depth, execution_state=execution_state,
                                      dry_up_ratio=vol_result.get("dry_up_ratio"), wide_and_loose=wide_and_loose)

    composite = calculate_composite_score(trend_score=tt_result.get("score", 0), contraction_score=vcp_result.get("score", 0),
                                            volume_score=vol_result.get("score", 0), pivot_score=piv_result.get("score", 0),
                                            rs_score=rs_result.get("score", 0), valid_vcp=valid_vcp, execution_state=execution_state,
                                            pattern_type=pattern_type, wide_and_loose=wide_and_loose, sma200_extension_pct=sma200_distance_pct)

    return {
        "symbol": symbol, "company_name": company_name, "sector": sector, "price": price, "market_cap": market_cap,
        "composite_score": composite["composite_score"], "quality_rating": composite.get("quality_rating", composite["rating"]),
        "rating": composite["rating"], "rating_description": composite["rating_description"], "guidance": composite["guidance"],
        "valid_vcp": valid_vcp, "execution_state": execution_state, "execution_state_reasons": exec_state_result.get("reasons", []),
        "pattern_type": pattern_type, "wide_and_loose": wide_and_loose, "state_cap_applied": composite.get("state_cap_applied", False),
        "cap_reason": composite.get("cap_reason"),
        "sma200_distance_pct": round(sma200_distance_pct, 1) if sma200_distance_pct is not None else None,
        "distance_from_pivot_pct": piv_result.get("distance_from_pivot_pct"),
        "weakest_component": composite["weakest_component"], "weakest_score": composite["weakest_score"],
        "strongest_component": composite["strongest_component"], "strongest_score": composite["strongest_score"],
        "trend_template": tt_result, "vcp_pattern": vcp_result, "volume_pattern": vol_result,
        "pivot_proximity": piv_result, "relative_strength": rs_result,
    }
