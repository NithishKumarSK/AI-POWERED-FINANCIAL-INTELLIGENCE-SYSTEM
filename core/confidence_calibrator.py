"""
confidence_calibrator.py — Phase 1 of the accuracy improvement program.

The AI's self-reported confidence_score is actively misleading: this session's
own live DB query found predictions with 80-100% stated confidence were right
only 40.0% of the time (n=25), while 40-59% confidence predictions were right
62.1% of the time -- confidence is INVERTED. Prompting the model to "be better
calibrated" is not the fix (more LLM sophistication already made raw accuracy
worse elsewhere this session, not better). Instead: calibrate statistically,
after the fact, from the DB's own track record.

Pure functions only -- no API calls, no Streamlit, importable anywhere.

Key entry points:
- fit_calibration_map(records) -> dict
    Bins raw confidence_score into coarse buckets and computes each bucket's
    EMPIRICAL direction-match rate. Buckets with too few samples are merged
    into a neighbor so every reported rate has a trustworthy sample size.
- calibrate(raw_confidence, calibration_map) -> float | None
    Maps a raw confidence_score to its calibrated (empirically-grounded) value.
"""
from __future__ import annotations

from typing import List, Optional

# Coarse default buckets -- matches the four ranges already used ad hoc this
# session's live analysis (0-39/40-59/60-79/80-100), which is about as fine as
# ~138 total records supports. hi is exclusive except the last bucket, whose
# hi=101 makes a raw value of exactly 100 fall inside it.
DEFAULT_BIN_EDGES = [0, 40, 60, 80, 101]

# A bucket's hit_rate is only reported once it has at least this many samples;
# sparser buckets are merged into their neighbor. Below this, a rate is noise,
# not a trustworthy calibration signal.
MIN_BIN_N = 5


def fit_calibration_map(
    records: List[dict],
    bin_edges: Optional[List[int]] = None,
    min_n: int = MIN_BIN_N,
) -> dict:
    """
    records: DB-record-shaped dicts, each with
        record["ai_prediction"]["confidence_score"] (0-100)
        record["comparison"]["directional_match"] (bool)
    Rows missing either field are skipped.

    Returns:
        {
          "bins": [{"lo": int, "hi": int, "n": int, "hit_rate": float}, ...],
          "overall_hit_rate": float | None,
          "n_total": int,
        }
    """
    edges = list(bin_edges or DEFAULT_BIN_EDGES)

    pairs = []
    for r in records or []:
        conf = (r.get("ai_prediction") or {}).get("confidence_score")
        dm   = (r.get("comparison") or {}).get("directional_match")
        if conf is None or dm is None:
            continue
        try:
            pairs.append((float(conf), bool(dm)))
        except (TypeError, ValueError):
            continue

    if not pairs:
        return {"bins": [], "overall_hit_rate": None, "n_total": 0}

    pairs.sort(key=lambda p: p[0])
    overall_hit_rate = round(sum(1 for _, dm in pairs if dm) / len(pairs) * 100, 1)

    # Initial bins strictly by the configured edges.
    raw_bins = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        members = [dm for c, dm in pairs if lo <= c < hi]
        raw_bins.append({"lo": lo, "hi": hi, "members": members})

    # Merge sparse bins forward (left to right) so every reported bin has
    # n >= min_n -- a single pass accumulator, not a re-binning from scratch.
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
            # Not enough data anywhere to hit min_n even once -- keep the one
            # under-powered bin rather than silently reporting nothing.
            merged.append(carry)

    bins = []
    for b in merged:
        n = len(b["members"])
        hit_rate = round(sum(1 for m in b["members"] if m) / n * 100, 1) if n else None
        bins.append({"lo": b["lo"], "hi": b["hi"], "n": n, "hit_rate": hit_rate})

    return {"bins": bins, "overall_hit_rate": overall_hit_rate, "n_total": len(pairs)}


def calibrate(raw_confidence: Optional[float], calibration_map: Optional[dict]) -> Optional[float]:
    """Map a raw confidence_score (0-100) to its calibrated, empirically-
    grounded value from calibration_map (as returned by fit_calibration_map).

    Falls back to the overall historical hit rate if raw_confidence is missing
    or doesn't fall cleanly in any bin; returns None only if no calibration
    data exists at all.
    """
    cal = calibration_map or {}
    bins = cal.get("bins") or []
    if raw_confidence is None or not bins:
        return cal.get("overall_hit_rate")

    c = float(raw_confidence)
    for b in bins:
        if b["lo"] <= c < b["hi"] and b.get("hit_rate") is not None:
            return b["hit_rate"]

    # Out-of-range raw value (shouldn't happen for a 0-100 score, but degrade
    # gracefully rather than return nothing) -- clamp to the nearest edge bin.
    if c >= bins[-1]["lo"]:
        return bins[-1].get("hit_rate")
    if c < bins[0]["lo"]:
        return bins[0].get("hit_rate")
    return cal.get("overall_hit_rate")
