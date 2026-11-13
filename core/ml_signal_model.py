"""
ml_signal_model.py — Phase 4 of the accuracy improvement program.

Trains a real statistical model (gradient-boosted trees) on the feature
vectors from ml_feature_extractor.py, as a non-narrative alternative/ensemble
signal alongside the LLM consensus -- motivated directly by this session's own
finding that the newer, more sophisticated triple-consensus Gemini
architecture scores WORSE than an older, simpler baseline already in the DB
(32.0%/47.6% decision/direction match vs 38.2%/58.8%). More LLM reasoning
alone did not help; this is a genuinely different kind of signal.

Persisted as a plain joblib artifact to data/ml_signal_model.pkl -- same
"static file checked into data/" convention already used for
data/calibration_profiles.json, no new deployment/serving infrastructure.

CRITICAL: cross-validation must be walk-forward (time-ordered), never random
k-fold. Randomly shuffling time-series data leaks future information into
training folds and produces a fake confidence win -- exactly the mistake
stock_comparison_engine's leakage checks exist to prevent elsewhere in this
codebase. walk_forward_split() below is the only sanctioned way to split this
data; see test_ml_signal_model.py's leakage test.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "data" / "ml_signal_model.pkl"

MIN_TRAINING_SAMPLES = 30  # below this, a model is a toy, not a signal -- refuse to train


def walk_forward_split(meta: List[dict], test_frac: float = 0.25) -> Tuple[List[int], List[int]]:
    """Time-ordered train/test split: every test-fold origin_date is AFTER
    every train-fold origin_date for rows sorted by date. Returns (train_idx,
    test_idx) into the original X/y/meta lists (original order preserved
    within each split, only the split POINT is time-based).

    Deliberately simple (one split, not k-fold) -- with ~tens to low hundreds
    of samples, repeated folds would each be even thinner than the whole
    set; a single honest holdout is more trustworthy than a fragile k-fold
    average here.
    """
    order = sorted(range(len(meta)), key=lambda i: (meta[i].get("origin_date") or ""))
    n_test = max(1, int(len(order) * test_frac))
    train_idx = order[: len(order) - n_test]
    test_idx = order[len(order) - n_test:]
    return train_idx, test_idx


def train(X: List[List[float]], y: List[int], meta: Optional[List[dict]] = None):
    """Train a gradient-boosted classifier. Raises ValueError if there isn't
    enough data to train something meaningful (see MIN_TRAINING_SAMPLES) --
    callers must not silently accept a toy model as if it were real."""
    if len(X) < MIN_TRAINING_SAMPLES:
        raise ValueError(
            f"Only {len(X)} training samples available (need >= {MIN_TRAINING_SAMPLES}). "
            "This is a known, honest limitation -- see ml_feature_extractor.py's module "
            "docstring: most historical DB rows predate _feature_packet capture. Use "
            "generate_bulk_training_data() for more symbols/horizons/months_back, or wait "
            "for more live predictions to accumulate."
        )

    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    X_arr = np.array(X, dtype=float)
    y_arr = np.array(y, dtype=int)

    # HistGradientBoostingClassifier natively handles NaN (missing feature
    # values from an indicator that failed to compute for this bar), but an
    # explicit imputer keeps the pipeline robust if swapped for a model that
    # doesn't support NaN natively later.
    # min_samples_leaf: sklearn's default (20) silently prevents the model
    # from splitting at all on realistic training set sizes for this app
    # (30-200 samples today, growing slowly) -- a split that would isolate a
    # leaf smaller than min_samples_leaf is simply never made, and the model
    # falls back to predicting the class prior for every input, looking
    # "trained" while having learned nothing from the features. Confirmed by
    # test_train_predict_evaluate_round_trip during development: default
    # settings produced a constant prediction (p_buy == training class
    # fraction) on trivially separable synthetic data. 5 is small enough to
    # let the model actually split on this data size, without going to 1
    # (which would let individual noisy points define a leaf on real,
    # non-synthetic market data).
    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("clf", HistGradientBoostingClassifier(
            max_depth=4, max_iter=100, learning_rate=0.08, random_state=42,
            min_samples_leaf=5,
        )),
    ])
    pipeline.fit(X_arr, y_arr)
    return pipeline


class SegmentedModel:
    """Research Expansion Program, Component 6 -- a dict of
    {segment_label: Pipeline} plus an optional default_model, saved/loaded as
    one joblib artifact, instead of one global model blended across every
    symbol/horizon. Motivated by a real, named candidate explanation for the
    single blended model's weak result (69.8% holdout vs. 67.7% baseline):
    mixing SPY's behavior with TSLA's behavior in one classifier may dilute
    whatever signal exists in either.

    A segment with enough training data gets its own dedicated model. A
    segment without enough data falls back to default_model (the same
    all-data-blended model this module trained before Component 6) rather
    than returning nothing -- every segment gets SOME answer, just a less
    specific one when there isn't enough segment-specific evidence yet.
    predict_proba returns None only when there's truly no model at all
    (default_model also absent/not trained).
    """
    def __init__(self, models: Dict[str, object], default_model: Optional[object] = None):
        self.models = models
        self.default_model = default_model

    def has_segment(self, segment_label: str) -> bool:
        return segment_label in self.models or self.default_model is not None

    def get_model_for(self, segment_label: Optional[str]):
        if segment_label and segment_label in self.models:
            return self.models[segment_label]
        return self.default_model

    def segments(self) -> List[str]:
        return list(self.models.keys())


def _predict_proba_single(model, feature_vector: List[float]) -> dict:
    import numpy as np

    # A saved model's feature count is frozen at its training time
    # (FEATURE_SPEC/BOOL_FEATURE_SPEC in ml_feature_extractor.py). Appending
    # a new feature there (e.g. the macro/rate data added for to-do item #9)
    # changes the live vector length for every NEWER prediction, but an
    # already-saved OLDER model still expects its original, shorter shape --
    # this happened for real this session. sklearn's own error for that case
    # ("X has N features, but SimpleImputer is expecting M features") is
    # accurate but cryptic; raise the same real condition with the actual
    # cause named, so a caller reading ml_signal_shadow_error understands
    # WHY rather than needing to decode an internal sklearn message.
    expected = getattr(model, "n_features_in_", None)
    if expected is not None and len(feature_vector) != expected:
        raise ValueError(
            f"Stale model: trained on {expected} features but this prediction's "
            f"vector has {len(feature_vector)} -- FEATURE_SPEC has grown since this "
            "model was last trained. Not a bug; awaiting the next retrain that "
            "clears the save gate with the current feature set."
        )

    x = np.array([feature_vector], dtype=float)
    proba = model.predict_proba(x)[0]  # [p(class=0 SELL), p(class=1 BUY)]
    p_sell, p_buy = float(proba[0]), float(proba[1])
    return {
        "p_buy": round(p_buy, 4),
        "p_sell": round(p_sell, 4),
        "decision": "BUY" if p_buy >= p_sell else "SELL",
    }


def predict_proba(model, feature_vector: List[float], segment_label: Optional[str] = None) -> Optional[dict]:
    """Returns {"p_buy": float, "p_sell": float, "decision": "BUY"|"SELL"},
    or None if `model` is a SegmentedModel with neither a segment-specific
    nor a default model available -- a real "no signal at all yet" state,
    not an error. A plain (non-segmented) Pipeline ignores segment_label
    entirely, for backward compatibility with a single global model."""
    if isinstance(model, SegmentedModel):
        target = model.get_model_for(segment_label)
        if target is None:
            return None
        return _predict_proba_single(target, feature_vector)
    return _predict_proba_single(model, feature_vector)


def evaluate(model, X_test: List[List[float]], y_test: List[int]) -> dict:
    """Honest holdout accuracy -- the only number that should ever be quoted
    as "the ML model's accuracy," never training-set accuracy."""
    if not X_test:
        return {"n": 0, "accuracy_pct": None}
    correct = 0
    for xi, yi in zip(X_test, y_test):
        pred = predict_proba(model, xi)
        pred_label = 1 if pred["decision"] == "BUY" else 0
        if pred_label == yi:
            correct += 1
    return {"n": len(X_test), "accuracy_pct": round(correct / len(X_test) * 100, 1)}


def save_model(model, path: Path = MODEL_PATH) -> None:
    import joblib
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)


def load_model(path: Path = MODEL_PATH):
    """Returns None (not an exception) if no model has been trained yet --
    callers (the shadow-mode cross-check in gemini_stock_prediction_agent.py)
    must treat "no model" as a normal, expected state, not an error."""
    import joblib
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception:
        return None
