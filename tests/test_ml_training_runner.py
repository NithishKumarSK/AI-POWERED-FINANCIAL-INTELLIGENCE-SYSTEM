"""Tests for core/ml_training_runner.py -- Research Expansion Program,
Component 6 (per-segment ML model training)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _dataset(n, label="1"):
    """n rows, alternating labels 0/1, distinct dates so walk_forward_split
    has something real to sort by."""
    from ml_feature_extractor import FEATURE_NAMES
    X = [[float(i % 2)] * len(FEATURE_NAMES) for i in range(n)]
    y = [i % 2 for i in range(n)]
    meta = [{"origin_date": f"2026-01-{(i % 28) + 1:02d}", "symbol": "TEST"} for i in range(n)]
    return X, y, meta


def test_train_and_gate_below_min_samples_returns_none_gracefully():
    from ml_training_runner import _train_and_gate
    X, y, meta = _dataset(10)
    model, info = _train_and_gate(X, y, meta, "TEST|0-7d")
    assert model is None
    assert info["saved"] is False
    assert "need >=" in info["reason"]


def test_train_and_gate_full_segment_passes_but_train_split_does_not_crash():
    """The exact bug found during development: a segment with enough TOTAL
    rows to pass the outer floor can still have too few rows after the 75/25
    walk-forward split for train() to accept -- this must degrade gracefully
    (model=None, informative reason), never raise an unhandled exception that
    kills the rest of a multi-segment sweep."""
    from ml_training_runner import _train_and_gate
    from ml_signal_model import MIN_TRAINING_SAMPLES
    # 38 rows * 0.75 = 28.5 -> 28 train rows, below MIN_TRAINING_SAMPLES (30),
    # while 38 itself clears the outer >=30 floor.
    n = int(MIN_TRAINING_SAMPLES * 38 / 30)  # scales correctly if the floor ever changes
    assert n >= MIN_TRAINING_SAMPLES  # sanity: this case must actually exercise the outer-pass path
    X, y, meta = _dataset(n)
    model, info = _train_and_gate(X, y, meta, "TEST|0-7d")
    assert model is None
    assert info["saved"] is False
    assert "holdout split" in info["reason"]


def test_train_and_gate_enough_data_after_split_trains_successfully():
    """A segment with enough rows both before AND after the split must train
    and evaluate without error (may or may not clear the baseline gate --
    this only confirms it doesn't crash and reports a real accuracy number)."""
    from ml_training_runner import _train_and_gate
    X, y, meta = _dataset(200)
    model, info = _train_and_gate(X, y, meta, "TEST|0-7d")
    assert info["accuracy_pct"] is not None
    assert info["n_total"] == 200
