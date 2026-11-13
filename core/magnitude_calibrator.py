"""
magnitude_calibrator.py -- signal-quality layer, second half of the
calibration pair alongside confidence_calibrator.py.

This project's own live DB (744 validated predictions) shows predicted-move
SIZE is inversely related to correctness, the same inverted pattern already
found and fixed for stated confidence: predictions with |predicted_return_pct|
< 2% were right 73.6% of the time (n=129), 2-5% only 48.9% (n=354), and >5%
only 48.3% (n=261) -- a large, dramatic predicted move is not evidence of a
stronger signal, it is evidence of a LESS reliable one.

Same statistical-calibration-after-the-fact approach as confidence_calibrator
(not a prompt-engineering fix -- this session already found more LLM
"sophistication" doesn't improve raw accuracy): bin the historical record by
predicted-move magnitude, read back each bucket's empirical hit rate.

Pure functions only -- no API calls, no Streamlit, importable anywhere.
"""
from __future__ import annotations

from typing import List, Optional

# Matches the real break points this session's own data showed (<2% / 2-5% /
# >5%) -- hi is exclusive except the last bucket, which has no upper bound.
DEFAULT_BIN_EDGES = [0, 2, 5, 10_000]

MIN_BIN_N = 5


def fit_magnitude_calibration_map(
    records: List[dict],
    bin_edges: Optional[List[float]] = None,
    min_n: int = MIN_BIN_N,
) -> dict:
    """
    records: DB-record-shaped dicts, each with
        record["ai_prediction"]["predicted_return_pct"]
        record["comparison"]["directional_match"] (bool)
    Rows missing either field are skipped. Bins on abs(predicted_return_pct).

    Returns the same shape as confidence_calibrator.fit_calibration_map:
        {"bins": [{"lo", "hi", "n", "hit_rate"}, ...],
         "overall_hit_rate": float | None, "n_total": int}
    """
    edges = list(bin_edges or DEFAULT_BIN_EDGES)

    pairs = []
    for r in records or []:
        pr = (r.get("ai_prediction") or {}).get("predicted_return_pct")
        dm = (r.get("comparison") or {}).get("directional_match")
        if pr is None or dm is None:
            continue
        try:
            pairs.append((abs(float(pr)), bool(dm)))
        except (TypeError, ValueError):
            continue

    if not pairs:
        return {"bins": [], "overall_hit_rate": None, "n_total": 0}

    pairs.sort(key=lambda p: p[0])
    overall_hit_rate = round(sum(1 for _, dm in pairs if dm) / len(pairs) * 100, 1)

    raw_bins = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        members = [dm for m, dm in pairs if lo <= m < hi]
        raw_bins.append({"lo": lo, "hi": hi, "members": members})

    merged: List[dict] = []
    carry: Optional[dict] = None
    for b in raw_bins:
        if carry is None:
            carry = dict(b)
        else:
            carry["hi"] = b["hi"]
            carry["members"] = carry["members"] + b["members"]
        if len(carry["members"]) >= min_n:
            merged.append(carry)
            carry = None
    if carry is not None:
        if merged:
            merged[-1]["hi"] = carry["hi"]
            merged[-1]["members"] = merged[-1]["members"] + carry["members"]
        else:
            merged.append(carry)

    bins = []
    for b in merged:
        n = len(b["members"])
        hit_rate = round(sum(1 for m in b["members"] if m) / n * 100, 1) if n else None
        bins.append({"lo": b["lo"], "hi": b["hi"], "n": n, "hit_rate": hit_rate})

    return {"bins": bins, "overall_hit_rate": overall_hit_rate, "n_total": len(pairs)}


def calibrate_magnitude(predicted_return_pct: Optional[float], calibration_map: Optional[dict]) -> Optional[float]:
    """Map |predicted_return_pct| to its calibrated, empirically-grounded hit
    rate from calibration_map (as returned by fit_magnitude_calibration_map).
    Falls back to the overall historical hit rate if missing/out of bin."""
    cal = calibration_map or {}
    bins = cal.get("bins") or []
    if predicted_return_pct is None or not bins:
        return cal.get("overall_hit_rate")

    m = abs(float(predicted_return_pct))
    for b in bins:
        if b["lo"] <= m < b["hi"] and b.get("hit_rate") is not None:
            return b["hit_rate"]

    if m >= bins[-1]["lo"]:
        return bins[-1].get("hit_rate")
    if m < bins[0]["lo"]:
        return bins[0].get("hit_rate")
    return cal.get("overall_hit_rate")


# ── Signal-quality composite ────────────────────────────────────────────────
# Combines calibrated confidence hit-rate and calibrated magnitude hit-rate
# into one display-only tier. Deliberately the weaker (minimum) of the two,
# not an average -- a signal is only as trustworthy as its weakest input;
# averaging would let one good number mask one bad one.
STRONG_THRESHOLD_PCT = 58.0
WEAK_THRESHOLD_PCT = 48.0


def signal_quality_tier(calibrated_confidence_hit_rate: Optional[float],
                         calibrated_magnitude_hit_rate: Optional[float]) -> dict:
    """Returns {"signal_quality_score": float|None, "signal_quality_tier": str}.
    Tier is one of "STRONG", "MODERATE", "WEAK", "UNKNOWN" (missing inputs).
    This NEVER changes the underlying decision/prediction -- display/filter
    layer only, exactly as the pre-registered plan requires."""
    vals = [v for v in (calibrated_confidence_hit_rate, calibrated_magnitude_hit_rate) if v is not None]
    if not vals:
        return {"signal_quality_score": None, "signal_quality_tier": "UNKNOWN"}
    score = round(min(vals), 1)
    if score >= STRONG_THRESHOLD_PCT:
        tier = "STRONG"
    elif score >= WEAK_THRESHOLD_PCT:
        tier = "MODERATE"
    else:
        tier = "WEAK"
    return {"signal_quality_score": score, "signal_quality_tier": tier}
