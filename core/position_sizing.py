"""
position_sizing.py -- Research Expansion Program, Component: risk-managed
position sizing.

Motivation (real, measured, not theoretical): this project's own EV test
found the system can be net profitable despite a sub-50% win rate, because
winning trades are sized asymmetrically larger than losing ones in the real
market data (see scratchpad ml_shadow_ev_probe results: 38.5% win rate,
+$2,904.74 avg win vs -$319.02 avg loss, net +$11,971.54 on 13 trades). That
is exactly the mechanism real quant funds exploit through position sizing,
and this project had no position-sizing logic at all -- every prediction
was treated as "bet the same amount," which cannot realize a payoff-asymmetry
edge the way variable sizing can.

This is a deliberately simple, transparent heuristic, NOT a rigorously
back-tested Kelly-criterion implementation -- Gemini's confidence_score is
self-reported, not a calibrated probability, so treating it as one would be
dishonest. It uses calibrated_confidence_score (confidence_calibrator.py)
wherever available, since raw confidence_score has been confirmed, with 572
real predictions, to be INVERSELY correlated with correctness (0-60% stated
confidence -> 59.5% actual hit rate; 80-100% stated confidence -> only 28.6%
actual hit rate). Sizing up on raw high confidence would be sizing up
exactly when the system is more likely to be wrong -- this function refuses
to do that.
"""
from __future__ import annotations

from typing import Optional

# Never risk more than this fraction of capital on one position, regardless
# of how favorable the inputs look -- a ceiling against overconfidence in
# the sizing formula itself, not just the prediction.
MAX_POSITION_FRACTION = 0.25

# Floor so a position is never literally zero when a trade is recommended at
# all (REVIEW/HOLD should already have filtered those out upstream) -- a
# nonzero floor keeps the output interpretable as "small but real," not a
# rounding artifact.
MIN_POSITION_FRACTION = 0.02

# Real, measured regime reliability -- from 436 DB predictions with a known
# trend_regime, direction-match rate was sideways 63.8%, bullish 49.0%,
# bearish 38.9% (a real 25-percentage-point spread, not noise). Normalized
# against the best-performing regime (sideways) so sideways gets full size
# and the others are scaled down proportionally to their real, measured
# relative reliability -- not an arbitrary guess.
REGIME_FACTOR = {
    "sideways": 1.00,
    "bullish":  round(49.0 / 63.8, 2),  # 0.77
    "bearish":  round(38.9 / 63.8, 2),  # 0.61
}
_DEFAULT_REGIME_FACTOR = 0.61  # unknown regime -- treat as conservatively as the worst known one


def compute_position_size(
    decision: str,
    initial_capital: float,
    confidence_score: Optional[float] = None,
    calibrated_confidence_score: Optional[float] = None,
    risk_score: Optional[float] = None,
    trend_regime: Optional[str] = None,
    max_position_fraction: float = MAX_POSITION_FRACTION,
    signal_quality_tier: Optional[str] = None,
) -> dict:
    """Return a recommended position size for a BUY/SELL decision.

    Returns {"status": "OK", "position_fraction": float, "position_dollars": float,
    "confidence_used": float, "confidence_source": "calibrated"|"raw_uncalibrated",
    "basis": str} on success, or {"status": "NO_POSITION", "reason": str} for
    HOLD/REVIEW (no position recommended -- not a sizing question).

    Prefers calibrated_confidence_score. Falls back to raw confidence_score
    only when no calibration map is available, and flags that explicitly in
    the result (confidence_source="raw_uncalibrated") so a caller never
    silently treats an uncalibrated number as if it had been validated.
    """
    if decision not in ("BUY", "SELL"):
        return {"status": "NO_POSITION", "reason": f"No position sizing for decision={decision!r} -- only BUY/SELL get a sized position."}

    # Research Expansion Program -- "no signal" gate (core/magnitude_calibrator.py
    # signal_quality_tier). Without this, MIN_POSITION_FRACTION below is a
    # floor that sizes a WEAK-tier prediction (both stated confidence AND
    # predicted-move size in a historically unreliable bucket) the same as
    # any other BUY/SELL -- never actually producing "no signal" regardless
    # of how poor the real track record at that tier is. This is the one
    # real override of that floor.
    if signal_quality_tier == "WEAK":
        return {
            "status": "NO_POSITION",
            "reason": "signal_quality_tier=WEAK -- stated confidence and/or predicted-move "
                      "size are both in a historically unreliable range for this system's own "
                      "real track record; no position sized rather than defaulting to the floor.",
        }

    if calibrated_confidence_score is not None:
        conf = max(0.0, min(100.0, float(calibrated_confidence_score)))
        source = "calibrated"
    elif confidence_score is not None:
        conf = max(0.0, min(100.0, float(confidence_score)))
        source = "raw_uncalibrated"
    else:
        return {"status": "NO_POSITION", "reason": "No confidence score available to size from."}

    # Confidence factor: calibrated confidence IS the real hit-rate estimate
    # at that stated level, so a calibrated 50% should size like a coin
    # flip (small), not like a strong signal -- rescale so only confidence
    # meaningfully above a 50% coin-flip baseline adds position size.
    confidence_factor = max(0.0, (conf - 50.0) / 50.0)  # 50->0.0, 75->0.5, 100->1.0

    # Risk factor: higher Gemini-reported risk_score shrinks the position.
    # risk_score is also self-reported and unvalidated the way confidence
    # was -- treated conservatively (any missing value assumes high risk,
    # i.e. small position, never assumes low risk by default).
    if risk_score is not None:
        risk_factor = max(0.0, 1.0 - (float(risk_score) / 100.0))
    else:
        risk_factor = 0.3  # unknown risk -> conservative, not neutral

    regime_factor = REGIME_FACTOR.get(trend_regime, _DEFAULT_REGIME_FACTOR) if trend_regime else _DEFAULT_REGIME_FACTOR

    raw_fraction = confidence_factor * risk_factor * regime_factor * max_position_fraction
    fraction = max(MIN_POSITION_FRACTION, min(raw_fraction, max_position_fraction))
    dollars = round(fraction * initial_capital, 2)

    return {
        "status": "OK",
        "position_fraction": round(fraction, 4),
        "position_dollars": dollars,
        "confidence_used": conf,
        "confidence_source": source,
        "regime_factor": regime_factor,
        "trend_regime_used": trend_regime or "unknown (treated as worst-known regime)",
        "basis": (
            f"confidence_factor={confidence_factor:.2f} (from {source} confidence {conf:.0f}) "
            f"x risk_factor={risk_factor:.2f} x regime_factor={regime_factor:.2f} "
            f"({trend_regime or 'unknown'}) x cap={max_position_fraction:.0%} "
            f"-> {fraction:.1%} of capital"
        ),
    }


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> dict:
    """Kelly Criterion: Kelly% = W - (1-W)/R, where W = win_rate and
    R = avg_win / avg_loss. Returns both full and half-Kelly (the
    conventionally recommended, less-volatile amount).

    Adapted from claude-trading-skills' position-sizer skill
    (vendor/claude-trading-skills/skills/position-sizer/, MIT License,
    Copyright (c) 2026 TraderMonty).

    DELIBERATELY NOT wired into compute_position_size() above: Kelly needs
    a real, measured win_rate and payoff ratio, and this project's only
    directly-available "confidence" signal (Gemini's self-reported
    confidence_score) is confirmed INVERSELY correlated with correctness --
    feeding that into Kelly would be exactly the dishonest move this
    module's own docstring already refuses to make. This function is only
    honest to call with real inputs: a segment's measured direction-match
    rate (segment_reliability.classify_records) as win_rate, and this
    project's own measured average win/loss P&L (e.g. from a batch
    validation or shadow-EV run) as avg_win/avg_loss -- never a stated
    confidence score standing in for either.

    Returns {"kelly_pct": float, "half_kelly_pct": float}. Negative
    expectancy (win_rate/payoff too poor) floors at 0%, not a negative
    position size.
    """
    if not (0.0 < win_rate <= 1.0):
        raise ValueError("win_rate must be between 0 (exclusive) and 1.0 (inclusive)")
    if avg_win <= 0 or avg_loss <= 0:
        raise ValueError("avg_win and avg_loss must both be positive (avg_loss as a magnitude)")

    payoff_ratio = avg_win / avg_loss
    kelly_pct = win_rate - (1 - win_rate) / payoff_ratio
    kelly_pct = max(0.0, kelly_pct) * 100
    return {"kelly_pct": round(kelly_pct, 2), "half_kelly_pct": round(kelly_pct / 2, 2)}


def fixed_fractional_shares(account_size: float, entry_price: float, stop_price: float, risk_pct: float) -> dict:
    """Fixed-fractional position sizing: risk a fixed % of account on the
    distance from entry to a stop price. Adapted from claude-trading-skills'
    position-sizer skill (see kelly_fraction's docstring for attribution).

    Returns {"shares": int, "risk_per_share": float, "dollar_risk": float}.
    Floors to whole shares (no fractional-share support here, unlike the
    source skill -- this project doesn't place fractional-share orders)."""
    if account_size <= 0 or entry_price <= 0 or risk_pct <= 0:
        raise ValueError("account_size, entry_price and risk_pct must all be positive")
    if stop_price >= entry_price:
        raise ValueError("stop_price must be below entry_price for a long position")

    risk_per_share = entry_price - stop_price
    dollar_risk = account_size * risk_pct / 100.0
    shares = int(dollar_risk / risk_per_share)
    return {"shares": shares, "risk_per_share": round(risk_per_share, 2), "dollar_risk": round(dollar_risk, 2)}


def atr_based_shares(account_size: float, entry_price: float, atr: float, risk_pct: float, atr_multiplier: float = 2.0) -> dict:
    """ATR-based position sizing: stop distance = atr * atr_multiplier,
    sized the same way as fixed_fractional_shares from there. Adapted from
    claude-trading-skills' position-sizer skill.

    Returns {"shares": int, "stop_price": float, "risk_per_share": float, "dollar_risk": float}."""
    if account_size <= 0 or entry_price <= 0 or atr <= 0 or risk_pct <= 0:
        raise ValueError("account_size, entry_price, atr and risk_pct must all be positive")

    stop_distance = atr * atr_multiplier
    stop_price = round(entry_price - stop_distance, 2)
    dollar_risk = account_size * risk_pct / 100.0
    shares = int(dollar_risk / stop_distance)
    return {
        "shares": shares, "stop_price": stop_price,
        "risk_per_share": round(stop_distance, 2), "dollar_risk": round(dollar_risk, 2),
    }
