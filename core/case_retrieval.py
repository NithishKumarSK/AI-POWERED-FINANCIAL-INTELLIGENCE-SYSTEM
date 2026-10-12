"""
case_retrieval.py — nearest-neighbor retrieval of similar past validated
predictions, so the Gemini prompt can see concrete historical precedent
("here are the 5 closest real cases and what actually happened") instead of
only aggregate percentages (symbol_calibration, segment_reliability).

Uses the same numeric feature vector ml_feature_extractor.py already defines
for ML training (FEATURE_SPEC), so this is a second consumer of that same
vector space rather than a new, inconsistent one.

Leakage safety: callers MUST pass only records already filtered so that no
candidate's outcome could have been known as of the current prediction's
origin_date (build_calibration_summary's existing as_of_date filtering, which
excludes any record whose target_date >= as_of_date, already does this).
This module additionally re-validates each candidate's own prediction_origin_date
against `current_origin_date` as defense-in-depth -- the same "never trust the
caller's filter alone" discipline already applied to SEC EDGAR / Alpha Vantage /
ApeWisdom data this session -- so a bug in the caller can't silently leak a
future-resolved case into a historical replay.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_paths
bootstrap_paths.add_module_paths()

from ml_feature_extractor import feature_packet_to_vector

# Need at least this many non-NaN values in a feature column across the
# candidate pool before trusting a computed mean/std for it; below this a
# single outlier could swing standardization wildly.
MIN_SAMPLES_FOR_STATS = 2


def _candidate_vector(record: dict) -> Optional[List[float]]:
    fp = (record.get("ai_prediction") or {}).get("_feature_packet")
    if not fp:
        return None
    return feature_packet_to_vector(fp)


def _standardize(vectors: List[List[float]]) -> List[List[float]]:
    """Z-score each feature column across the pool (NaN-safe), so no single
    large-scale feature (e.g. volume_ratio) dominates Euclidean distance over
    small-scale ones (e.g. a 0-1 bollinger-band position). NaN entries become
    0.0 post-standardization -- "no information", not "equal to the mean" in
    a way that would bias distance toward or away from any direction."""
    if not vectors:
        return []
    n_features = len(vectors[0])
    means = [0.0] * n_features
    stds = [1.0] * n_features
    for j in range(n_features):
        col = [v[j] for v in vectors if not math.isnan(v[j])]
        if len(col) >= MIN_SAMPLES_FOR_STATS:
            m = sum(col) / len(col)
            var = sum((x - m) ** 2 for x in col) / len(col)
            s = math.sqrt(var) if var > 1e-9 else 1.0
            means[j], stds[j] = m, s
    return [
        [(v[j] - means[j]) / stds[j] if not math.isnan(v[j]) else 0.0 for j in range(n_features)]
        for v in vectors
    ]


def _distance(a: List[float], b: List[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def find_similar_cases(
    current_feature_packet: dict,
    symbol: str,
    horizon_days: Optional[int],
    records: List[dict],
    current_origin_date: str = "",
    k: int = 5,
) -> List[dict]:
    """Find the k most similar past validated runs to the current prediction.

    Prefers SAME_SYMBOL matches; backfills with SAME_SEGMENT (same horizon
    bucket, different symbol) matches only if there aren't enough same-symbol
    candidates. Each result is labeled with its tier so callers (and the
    prompt) know how directly comparable it actually is -- a same-symbol
    precedent and a different-symbol-same-bucket precedent are not equally
    strong evidence, and nothing here should pretend otherwise.

    Returns [] (never raises) if there's no usable current vector or no
    eligible candidates -- this is enrichment, not a required input.
    """
    current_vec = feature_packet_to_vector(current_feature_packet)
    if current_vec is None or not records:
        return []

    from batch_validation_runner import horizon_bucket
    current_bucket = horizon_bucket(horizon_days)
    sym_upper = str(symbol or "").upper()

    candidates = []
    for r in records:
        spi = r.get("stock_prediction_input") or {}
        cmp = r.get("comparison") or {}
        if cmp.get("decision_match") is None:
            continue  # unresolved record -- not a real precedent

        if current_origin_date:
            cand_origin = str(spi.get("prediction_origin_date") or "")
            if not cand_origin or cand_origin >= current_origin_date:
                continue  # defense in depth -- see module docstring

        vec = _candidate_vector(r)
        if vec is None:
            continue

        cand_symbol = str(spi.get("symbol") or "").upper()
        cand_bucket = horizon_bucket(spi.get("decision_horizon_days"))
        if cand_symbol == sym_upper:
            tier = "SAME_SYMBOL"
        elif cand_bucket == current_bucket:
            tier = "SAME_SEGMENT"
        else:
            continue
        candidates.append((r, vec, tier))

    if not candidates:
        return []

    all_vecs = [current_vec] + [c[1] for c in candidates]
    std_vecs = _standardize(all_vecs)
    std_current, std_candidates = std_vecs[0], std_vecs[1:]

    scored = [
        (_distance(std_current, svec), tier, r)
        for (r, _vec, tier), svec in zip(candidates, std_candidates)
    ]
    same_symbol = sorted((s for s in scored if s[1] == "SAME_SYMBOL"), key=lambda t: t[0])
    same_segment = sorted((s for s in scored if s[1] == "SAME_SEGMENT"), key=lambda t: t[0])
    ranked = (same_symbol + same_segment)[:k]

    results = []
    for dist, tier, r in ranked:
        spi = r.get("stock_prediction_input") or {}
        ai  = r.get("ai_prediction") or {}
        av  = r.get("actual_validation") or {}
        cmp = r.get("comparison") or {}
        results.append({
            "match_tier":            tier,
            "distance":              round(dist, 3),
            "symbol":                spi.get("symbol"),
            "horizon_days":          spi.get("decision_horizon_days"),
            "origin_date":           spi.get("prediction_origin_date"),
            "ai_decision":           ai.get("decision"),
            "actual_decision":       av.get("actual_decision"),
            "decision_match":        cmp.get("decision_match"),
            "directional_match":     cmp.get("directional_match"),
            "abs_return_error_pct":  cmp.get("abs_return_error_pct"),
        })
    return results
