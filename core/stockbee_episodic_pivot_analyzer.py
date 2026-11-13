"""
stockbee_episodic_pivot_analyzer.py -- Day-1 Episodic Pivot (EP) catalyst
classification and scoring, ported from claude-trading-skills'
stockbee-episodic-pivot-analyzer skill
(vendor/claude-trading-skills/skills/stockbee-episodic-pivot-analyzer/scripts/analyze_ep.py,
MIT License, Copyright (c) 2026 TraderMonty).

The source skill is explicitly "catalyst-first": it does not discover
news itself, it takes a pre-supplied events JSON (or an
earnings-trade-analyzer JSON) and enriches it with price/volume stats.
core/stockbee_episodic_pivot_analyzer_service.py (the live orchestrator)
supplies that catalyst event from two real sources already built this
session: (1) core/earnings_trade_analyzer_service.py's recent-earnings
result (leakage-safe, catalyst_type="earnings"), or (2)
core/free_news_service.fetch_yahoo_headline_tags's live headline text run
through this module's own keyword classifier (LIVE-ONLY, same as every
other Yahoo-headline use in this project) -- if neither resolves a real
catalyst, the service returns an honest "no catalyst identified" error
rather than fabricating one, matching the source skill's own catalyst-
first design.

Price bars here are CHRONOLOGICAL (oldest first), matching
historical_price_service.py's native order directly -- unlike the
Stockbee hammer/burst screeners (which need most-recent-first), this
skill's own price_stats_from_bars() indexes forward from an event date,
so no reversal is needed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

CATALYST_ALIASES = {
    "earnings": "earnings", "earnings_beat": "earnings", "earnings_acceleration": "earnings",
    "beat_and_raise": "guidance_raise", "guidance": "guidance_raise", "guidance_raise": "guidance_raise",
    "raise_guidance": "guidance_raise", "m&a": "m_and_a", "ma": "m_and_a", "m_and_a": "m_and_a",
    "merger": "m_and_a", "acquisition": "m_and_a", "buyout": "m_and_a", "fda": "fda_approval",
    "fda_approval": "fda_approval", "approval": "regulatory_approval", "regulatory": "regulatory_approval",
    "regulatory_approval": "regulatory_approval", "contract": "major_contract", "major_contract": "major_contract",
    "partnership": "major_partnership", "major_partnership": "major_partnership", "analyst": "analyst_upgrade",
    "analyst_upgrade": "analyst_upgrade", "upgrade": "analyst_upgrade", "product": "product_launch",
    "product_launch": "product_launch", "story": "story_theme", "theme": "story_theme",
    "story_theme": "story_theme", "short_squeeze": "short_squeeze",
}

CATALYST_KEYWORDS = [
    ("guidance_raise", r"\b(raise[sd]?|boost[sed]?|lift[sed]?|increase[sd]?)\b.*\bguidance\b"),
    ("guidance_raise", r"\bguidance\b.*\b(raise[sd]?|boost[sed]?|lift[sed]?|increase[sd]?)\b"),
    ("earnings", r"\b(beat|beats|surprise|eps|earnings|revenue)\b"),
    ("m_and_a", r"\b(acquire[sd]?|acquisition|merger|buyout|takeover|tender offer)\b"),
    ("fda_approval", r"\b(fda|pdufa|phase 3|phase iii|drug approval|approved)\b"),
    ("regulatory_approval", r"\b(regulatory approval|approved by|clearance|authorization)\b"),
    ("major_contract", r"\b(contract|order|backlog|award|customer win|deal)\b"),
    ("major_partnership", r"\b(partnership|collaboration|strategic alliance)\b"),
    ("analyst_upgrade", r"\b(upgrade[sd]?|price target|initiates coverage|overweight|buy rating)\b"),
    ("product_launch", r"\b(launch|unveil|new product|commercialization)\b"),
    ("short_squeeze", r"\b(short squeeze|squeeze|short interest)\b"),
    ("story_theme", r"\b(ai|artificial intelligence|crypto|bitcoin|nuclear|uranium|space|robotics|ev|defense)\b"),
]

CATALYST_BASE_SCORES = {
    "guidance_raise": 95, "fda_approval": 94, "earnings": 88, "m_and_a": 84, "regulatory_approval": 82,
    "major_contract": 76, "major_partnership": 72, "product_launch": 66, "short_squeeze": 58,
    "analyst_upgrade": 54, "story_theme": 50, "unknown": 35,
}

EP_TYPE_BY_CATALYST = {
    "earnings": "EARNINGS_EP", "guidance_raise": "GUIDANCE_EP", "m_and_a": "M_AND_A_EP",
    "fda_approval": "FDA_EP", "regulatory_approval": "REGULATORY_EP", "major_contract": "CONTRACT_EP",
    "major_partnership": "PARTNERSHIP_EP", "analyst_upgrade": "ANALYST_EP", "product_launch": "PRODUCT_EP",
    "short_squeeze": "SQUEEZE_EP", "story_theme": "STORY_EP", "unknown": "UNCLASSIFIED_EP",
}

GRADE_TO_BONUS = {"A": 8, "B": 4, "C": 0, "D": -4}


@dataclass
class PriceStats:
    symbol: str
    event_date: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    prev_close: Optional[float] = None
    volume: Optional[float] = None
    avg_volume_20: Optional[float] = None
    avg_volume_50: Optional[float] = None
    gap_pct: Optional[float] = None
    day_gain_pct: Optional[float] = None
    range_pct: Optional[float] = None
    close_location_pct: Optional[float] = None
    volume_ratio_20: Optional[float] = None
    volume_ratio_50: Optional[float] = None
    dollar_volume: Optional[float] = None
    risk_pct_to_low: Optional[float] = None
    prior_5d_return_pct: Optional[float] = None
    prior_20d_return_pct: Optional[float] = None


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def round_or_none(value: Optional[float], digits: int = 2) -> Optional[float]:
    return round(value, digits) if value is not None else None


def normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


def parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def normalize_catalyst_type(raw: Any) -> str:
    text = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return "unknown"
    return CATALYST_ALIASES.get(text, text if text in CATALYST_BASE_SCORES else "unknown")


def classify_catalyst(record: dict) -> tuple:
    explicit = normalize_catalyst_type(record.get("catalyst_type") or record.get("event_type") or record.get("type") or record.get("category"))
    if explicit != "unknown":
        return explicit, [f"explicit:{explicit}"]

    text = " ".join(str(record.get(key, "")) for key in ("headline", "summary", "description", "notes")).lower()
    for catalyst_type, pattern in CATALYST_KEYWORDS:
        if re.search(pattern, text):
            return catalyst_type, [f"keyword:{catalyst_type}"]
    return "unknown", ["no_clear_catalyst_keyword"]


def average(values: list) -> Optional[float]:
    cleaned = [v for v in values if v is not None and v > 0]
    return sum(cleaned) / len(cleaned) if cleaned else None


def find_event_index(bars: list, event_date: Optional[str]) -> Optional[int]:
    """bars: chronological (oldest first)."""
    if not bars:
        return None
    if event_date:
        for idx, bar in enumerate(bars):
            if bar["date"] == event_date:
                return idx
        target = parse_date(event_date)
        if target:
            for idx, bar in enumerate(bars):
                bar_date = parse_date(bar["date"])
                if bar_date and bar_date >= target:
                    return idx
    return len(bars) - 1


def price_stats_from_bars(symbol: str, bars: list, event_date: Optional[str]) -> PriceStats:
    """bars: chronological (oldest first)."""
    idx = find_event_index(bars, event_date)
    if idx is None or idx <= 0 or idx >= len(bars):
        return PriceStats(symbol=symbol, event_date=event_date)

    bar, prev = bars[idx], bars[idx - 1]
    prev_close = safe_float(prev.get("close"))
    open_price, high, low, close = safe_float(bar.get("open")), safe_float(bar.get("high")), safe_float(bar.get("low")), safe_float(bar.get("close"))
    volume = safe_float(bar.get("volume"))

    prior_bars = bars[max(0, idx - 50) : idx]
    avg20 = average([safe_float(b.get("volume"), 0) or 0 for b in prior_bars[-20:]])
    avg50 = average([safe_float(b.get("volume"), 0) or 0 for b in prior_bars])

    gap_pct = day_gain_pct = range_pct = close_location_pct = risk_pct_to_low = dollar_volume = None
    if prev_close and prev_close > 0:
        if open_price:
            gap_pct = (open_price / prev_close - 1.0) * 100.0
        if close:
            day_gain_pct = (close / prev_close - 1.0) * 100.0
        if high and low:
            range_pct = (high - low) / prev_close * 100.0
    if high and low and close and high > low:
        close_location_pct = (close - low) / (high - low) * 100.0
    if close and low and close > 0:
        risk_pct_to_low = (close - low) / close * 100.0
    if close and volume:
        dollar_volume = close * volume

    volume_ratio_20 = volume / avg20 if volume and avg20 else None
    volume_ratio_50 = volume / avg50 if volume and avg50 else None

    prior_5d = prior_20d = None
    if idx >= 5 and prev_close and safe_float(bars[idx - 5].get("close")):
        base = safe_float(bars[idx - 5].get("close"))
        prior_5d = (prev_close / base - 1.0) * 100.0 if base else None
    if idx >= 20 and prev_close and safe_float(bars[idx - 20].get("close")):
        base = safe_float(bars[idx - 20].get("close"))
        prior_20d = (prev_close / base - 1.0) * 100.0 if base else None

    return PriceStats(
        symbol=symbol, event_date=bar["date"], open=open_price, high=high, low=low, close=close,
        prev_close=prev_close, volume=volume, avg_volume_20=avg20, avg_volume_50=avg50, gap_pct=gap_pct,
        day_gain_pct=day_gain_pct, range_pct=range_pct, close_location_pct=close_location_pct,
        volume_ratio_20=volume_ratio_20, volume_ratio_50=volume_ratio_50, dollar_volume=dollar_volume,
        risk_pct_to_low=risk_pct_to_low, prior_5d_return_pct=prior_5d, prior_20d_return_pct=prior_20d,
    )


def merge_price_fields(record: dict, stats: PriceStats) -> dict:
    """Momentum-enrichment-file merging (a 3rd optional source in the
    original skill) was not ported -- this project has no equivalent
    cached-report file to enrich from."""
    merged = dict(record)
    stat_map = {
        "open": stats.open, "high": stats.high, "low": stats.low, "close": stats.close,
        "prev_close": stats.prev_close, "volume": stats.volume, "avg_volume_20": stats.avg_volume_20,
        "avg_volume_50": stats.avg_volume_50, "gap_pct": stats.gap_pct, "day_gain_pct": stats.day_gain_pct,
        "range_pct": stats.range_pct, "close_location_pct": stats.close_location_pct,
        "volume_ratio_20": stats.volume_ratio_20, "volume_ratio_50": stats.volume_ratio_50,
        "dollar_volume": stats.dollar_volume, "risk_pct_to_low": stats.risk_pct_to_low,
        "prior_5d_return_pct": stats.prior_5d_return_pct, "prior_20d_return_pct": stats.prior_20d_return_pct,
    }
    for key, value in stat_map.items():
        if merged.get(key) is None and value is not None:
            merged[key] = value
    if stats.event_date and not merged.get("price_event_date"):
        merged["price_event_date"] = stats.event_date
    return merged


def score_catalyst(record: dict) -> tuple:
    catalyst_type = normalize_catalyst_type(record.get("catalyst_type"))
    base = CATALYST_BASE_SCORES.get(catalyst_type, 35)
    reasons = [f"base_{catalyst_type}:{base}"]

    grade = str(record.get("source_grade") or record.get("grade") or "").upper()
    if grade in GRADE_TO_BONUS:
        base += GRADE_TO_BONUS[grade]
        reasons.append(f"earnings_grade_{grade}:{GRADE_TO_BONUS[grade]:+d}")

    text = " ".join(str(record.get(k, "")) for k in ("headline", "summary", "description", "notes")).lower()
    if re.search(r"\b(first|record|accelerat|inflect|turnaround|transform|breakthrough)\b", text):
        base += 6
        reasons.append("game_change_language:+6")
    if re.search(r"\b(secondary offering|dilution|investigation|downgrade|lawsuit|resignation)\b", text):
        base -= 12
        reasons.append("negative_or_dilutive_language:-12")

    return max(0.0, min(100.0, base)) * 0.35, reasons


def score_price_action(record: dict) -> tuple:
    gap, day_gain = safe_float(record.get("gap_pct")), safe_float(record.get("day_gain_pct"))
    close_loc, range_pct = safe_float(record.get("close_location_pct")), safe_float(record.get("range_pct"))
    score, reasons = 0.0, []

    move = day_gain if day_gain is not None else gap
    if move is None:
        reasons.append("missing_move:0")
    elif move >= 12:
        score += 12; reasons.append("move_12pct_plus:+12")
    elif move >= 8:
        score += 10; reasons.append("move_8pct_plus:+10")
    elif move >= 4:
        score += 8; reasons.append("move_4pct_plus:+8")
    elif move >= 2:
        score += 4; reasons.append("move_2pct_plus:+4")
    else:
        reasons.append("weak_move:0")

    if gap is not None and gap >= 4:
        score += 4; reasons.append("gap_confirmation:+4")
    elif gap is not None and gap >= 2:
        score += 2; reasons.append("small_gap_confirmation:+2")

    if close_loc is not None:
        if close_loc >= 80:
            score += 4; reasons.append("close_near_high:+4")
        elif close_loc >= 60:
            score += 2; reasons.append("close_upper_range:+2")
        elif close_loc < 40:
            score -= 4; reasons.append("weak_close_location:-4")

    if range_pct is not None and range_pct >= 6:
        score += 2; reasons.append("range_expansion:+2")

    return max(0.0, min(20.0, score)), reasons


def score_volume(record: dict) -> tuple:
    ratio = safe_float(record.get("volume_ratio_50") or record.get("volume_ratio_20") or record.get("volume_ratio_1d"))
    volume = safe_float(record.get("volume"))
    score, reasons = 0.0, []
    if ratio is not None:
        if ratio >= 10:
            score = 20; reasons.append("volume_10x_plus:+20")
        elif ratio >= 5:
            score = 17; reasons.append("volume_5x_plus:+17")
        elif ratio >= 3:
            score = 14; reasons.append("volume_3x_plus:+14")
        elif ratio >= 1.5:
            score = 8; reasons.append("volume_1_5x_plus:+8")
        else:
            score = 2; reasons.append("weak_volume_ratio:+2")
    elif volume is not None:
        if volume >= 9_000_000:
            score = 14; reasons.append("absolute_9m_volume:+14")
        elif volume >= 1_000_000:
            score = 8; reasons.append("absolute_1m_volume:+8")
        elif volume >= 300_000:
            score = 4; reasons.append("absolute_300k_volume:+4")
        else:
            reasons.append("thin_absolute_volume:0")
    else:
        score = 3; reasons.append("missing_volume:+3")

    if volume is not None and volume >= 9_000_000 and score < 20:
        score += 3; reasons.append("9m_ep_bonus:+3")
    return min(20.0, score), reasons


def score_revaluation(record: dict) -> tuple:
    prior_20 = safe_float(record.get("prior_20d_return_pct"))
    market_cap = safe_float(record.get("market_cap") or record.get("mktCap"))
    score, reasons = 5.0, ["default_revaluation:+5"]

    if prior_20 is not None:
        if prior_20 <= 5:
            score, reasons = 8, ["neglected_or_not_extended:+8"]
        elif prior_20 <= 15:
            score, reasons = 6, ["moderately_extended:+6"]
        elif prior_20 <= 30:
            score, reasons = 3, ["extended_prior_run:+3"]
        else:
            score, reasons = 1, ["very_extended_prior_run:+1"]

    if market_cap is not None:
        if market_cap < 10_000_000_000:
            score += 2; reasons.append("cap_under_10b:+2")
        elif market_cap > 100_000_000_000:
            score -= 1; reasons.append("mega_cap_less_revaluation:+-1")
    return max(0.0, min(10.0, score)), reasons


def score_liquidity(record: dict) -> tuple:
    price = safe_float(record.get("close") or record.get("price") or record.get("current_price"))
    volume = safe_float(record.get("volume"))
    dollar_volume = safe_float(record.get("dollar_volume"))
    if dollar_volume is None and price and volume:
        dollar_volume = price * volume
    score, reasons = 0.0, []
    if dollar_volume is not None:
        if dollar_volume >= 50_000_000:
            score = 10; reasons.append("dollar_volume_50m_plus:+10")
        elif dollar_volume >= 10_000_000:
            score = 8; reasons.append("dollar_volume_10m_plus:+8")
        elif dollar_volume >= 2_000_000:
            score = 4; reasons.append("dollar_volume_2m_plus:+4")
        else:
            score = 1; reasons.append("thin_dollar_volume:+1")
    elif volume is not None:
        if volume >= 1_000_000:
            score = 7; reasons.append("absolute_volume_liquid:+7")
        elif volume >= 300_000:
            score = 4; reasons.append("absolute_volume_moderate:+4")
        else:
            score = 1; reasons.append("absolute_volume_thin:+1")
    else:
        score = 2; reasons.append("missing_liquidity_data:+2")
    return min(10.0, score), reasons


def score_risk(record: dict) -> tuple:
    risk = safe_float(record.get("risk_pct_to_low") or record.get("risk_pct_to_stop"))
    if risk is None:
        return 2.0, ["missing_risk_distance:+2"]
    if risk <= 4:
        return 5.0, ["tight_risk_4pct_or_less:+5"]
    if risk <= 7:
        return 3.5, ["manageable_risk_7pct_or_less:+3.5"]
    if risk <= 10:
        return 1.5, ["wide_risk_10pct_or_less:+1.5"]
    return 0.0, ["too_wide_risk:0"]


def rating_from_score(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "A-"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    return "D"


def determine_state(record: dict, score: float, max_risk_pct: float) -> tuple:
    reasons = []
    day_gain, gap = safe_float(record.get("day_gain_pct")), safe_float(record.get("gap_pct"))
    volume_ratio = safe_float(record.get("volume_ratio_50") or record.get("volume_ratio_20") or record.get("volume_ratio_1d"))
    close_loc = safe_float(record.get("close_location_pct"))
    risk = safe_float(record.get("risk_pct_to_low") or record.get("risk_pct_to_stop"))
    catalyst_type = normalize_catalyst_type(record.get("catalyst_type"))

    move_confirmed = (day_gain is not None and day_gain >= 4) or (gap is not None and gap >= 4)
    volume_confirmed = volume_ratio is None or volume_ratio >= 1.5 or safe_float(record.get("volume"), 0) >= 300_000
    weak_close = close_loc is not None and close_loc < 40
    risk_too_wide = risk is not None and risk > max_risk_pct

    if weak_close:
        reasons.append("weak_close_location")
    if risk_too_wide:
        reasons.append("risk_too_wide_for_day1")
    if not move_confirmed:
        reasons.append("price_move_not_confirmed")
    if not volume_confirmed:
        reasons.append("volume_not_confirmed")

    if score >= 85 and move_confirmed and volume_confirmed and not weak_close and not risk_too_wide:
        return "ACTIONABLE_DAY1", reasons
    if score >= 75 and move_confirmed and volume_confirmed and not weak_close and not risk_too_wide:
        return "DAY1_WATCH", reasons
    if score >= 70 and (risk_too_wide or weak_close):
        return "DELAYED_EP_WATCH", reasons
    if catalyst_type != "unknown" and not move_confirmed and score >= 55:
        return "CATALYST_WATCH", reasons
    return "REJECT", reasons


def analyze_candidate(event: dict, bars: list, max_risk_pct: float = 10.0) -> dict:
    """event: a catalyst record with at minimum 'symbol' and either an
    explicit 'catalyst_type' or headline/summary text to classify.
    bars: chronological (oldest first) OHLCV for that symbol."""
    symbol = normalize_symbol(event.get("symbol"))
    event_date = event.get("event_date")

    stats = price_stats_from_bars(symbol, bars, event_date) if bars else PriceStats(symbol, event_date)
    record = merge_price_fields(event, stats)
    catalyst_type = normalize_catalyst_type(record.get("catalyst_type"))
    ep_type = EP_TYPE_BY_CATALYST.get(catalyst_type, "UNCLASSIFIED_EP")

    component_scores, component_reasons = {}, {}
    for name, scorer in (
        ("catalyst_quality", score_catalyst), ("price_action", score_price_action),
        ("volume_shock", score_volume), ("neglect_revaluation", score_revaluation),
        ("liquidity", score_liquidity), ("risk_distance", score_risk),
    ):
        score, reasons = scorer(record)
        component_scores[name] = round(score, 2)
        component_reasons[name] = reasons

    composite = round(sum(component_scores.values()), 2)
    state, state_reasons = determine_state(record, composite, max_risk_pct=max_risk_pct)
    rating = rating_from_score(composite)

    close_loc = safe_float(record.get("close_location_pct"))
    if close_loc is not None and close_loc < 30 and composite >= 55:
        composite = round(max(0.0, composite - 8.0), 2)
        rating = rating_from_score(composite)
        state_reasons.append("fade_deduction_applied")
        state, more_reasons = determine_state(record, composite, max_risk_pct=max_risk_pct)
        state_reasons.extend([r for r in more_reasons if r not in state_reasons])

    pead_handoff = catalyst_type in {"earnings", "guidance_raise"} and state in {"ACTIONABLE_DAY1", "DAY1_WATCH", "DELAYED_EP_WATCH"}
    momentum_handoff = (safe_float(record.get("day_gain_pct"), 0) or 0) >= 4 and state != "REJECT"

    return {
        "symbol": symbol, "event_date": event_date, "price_event_date": record.get("price_event_date"),
        "headline": record.get("headline") or record.get("title") or "",
        "summary": record.get("summary") or record.get("description") or record.get("notes") or "",
        "source_input": record.get("source_input"), "catalyst_type": catalyst_type, "ep_type": ep_type,
        "state": state, "state_reasons": sorted(set(state_reasons)), "rating": rating,
        "composite_score": composite, "component_scores": component_scores, "component_reasons": component_reasons,
        "catalyst_reasons": record.get("catalyst_reasons", []),
        "gap_pct": round_or_none(safe_float(record.get("gap_pct"))),
        "day_gain_pct": round_or_none(safe_float(record.get("day_gain_pct"))),
        "range_pct": round_or_none(safe_float(record.get("range_pct"))),
        "close_location_pct": round_or_none(safe_float(record.get("close_location_pct"))),
        "volume": round_or_none(safe_float(record.get("volume")), 0),
        "avg_volume_50": round_or_none(safe_float(record.get("avg_volume_50")), 0),
        "volume_ratio_50": round_or_none(safe_float(record.get("volume_ratio_50"))),
        "dollar_volume": round_or_none(safe_float(record.get("dollar_volume")), 0),
        "open": round_or_none(safe_float(record.get("open"))), "high": round_or_none(safe_float(record.get("high"))),
        "low": round_or_none(safe_float(record.get("low"))),
        "close": round_or_none(safe_float(record.get("close") or record.get("price") or record.get("current_price"))),
        "prev_close": round_or_none(safe_float(record.get("prev_close"))),
        "risk_pct_to_low": round_or_none(safe_float(record.get("risk_pct_to_low"))),
        "prior_20d_return_pct": round_or_none(safe_float(record.get("prior_20d_return_pct"))),
        "source_grade": record.get("source_grade") or record.get("grade"),
        "source_score": round_or_none(safe_float(record.get("source_score") or record.get("score"))),
        "market_cap": round_or_none(safe_float(record.get("market_cap") or record.get("mktCap")), 0),
        "pead_handoff": pead_handoff, "momentum_handoff": momentum_handoff,
        "delayed_ep_watch": state == "DELAYED_EP_WATCH",
        "trade_plan_inputs": {
            "entry_reference": round_or_none(safe_float(record.get("close") or record.get("price") or record.get("current_price"))),
            "stop_reference": round_or_none(safe_float(record.get("low"))),
            "stop_basis": "ep_day_low",
        },
    }
