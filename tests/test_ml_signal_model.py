"""Tests for core/ml_feature_extractor.py and core/ml_signal_model.py --
Phase 4 of the accuracy improvement program: a trained, non-narrative
alternative/ensemble signal alongside the LLM consensus, run in shadow mode
only until it has proven itself against the Phase 5 batch harness."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _good_feature_packet(**overrides):
    fp = {
        "status": "OK",
        "returns": {"return_1d": 0.1, "return_5d": 0.5, "return_10d": 1.0, "return_20d": 2.0, "return_60d": 4.0},
        "trend": {"price_vs_sma_20_pct": 1.5, "price_vs_sma_50_pct": 2.0, "ADX_14": 25.0},
        "momentum": {"RSI_14": 55.0, "MACD_histogram": 0.3},
        "volatility": {"annualized_volatility": 20.0, "ATR_daily_pct": 1.2, "BB_position": 0.6,
                       "max_drawdown_context": -5.0, "dist_from_low_pct": 10.0},
        "volume": {"volume_ratio_20": 1.1},
        "support_resistance": {"dist_to_support_pct": 3.0, "dist_to_resistance_pct": 4.0},
        "benchmark_comparison": {"benchmark_return_20d": 1.8, "relative_strength_20d": 0.2, "relative_strength_60d": 0.1},
        "reversal_signals": {"oversold_signal": False, "overbought_signal": False,
                              "near_support": True, "near_resistance": False, "momentum_divergence": False},
    }
    fp.update(overrides)
    return fp


# ── ml_feature_extractor ──────────────────────────────────────────────────────

def test_feature_packet_to_vector_bad_status_returns_none():
    from ml_feature_extractor import feature_packet_to_vector
    assert feature_packet_to_vector({"status": "INSUFFICIENT"}) is None
    assert feature_packet_to_vector({}) is None
    assert feature_packet_to_vector(None) is None


def test_feature_packet_to_vector_correct_length():
    from ml_feature_extractor import feature_packet_to_vector, FEATURE_NAMES
    vec = feature_packet_to_vector(_good_feature_packet())
    assert vec is not None
    assert len(vec) == len(FEATURE_NAMES)


def test_feature_packet_to_vector_missing_field_becomes_nan():
    import math
    from ml_feature_extractor import feature_packet_to_vector
    fp = _good_feature_packet()
    fp["momentum"] = {}  # RSI_14/MACD_histogram missing entirely
    vec = feature_packet_to_vector(fp)
    assert any(math.isnan(v) for v in vec)


def test_feature_packet_to_vector_bool_encoding():
    from ml_feature_extractor import feature_packet_to_vector, FEATURE_NAMES
    fp = _good_feature_packet()
    fp["reversal_signals"]["oversold_signal"] = True
    vec = feature_packet_to_vector(fp)
    idx = FEATURE_NAMES.index("oversold_signal")
    assert vec[idx] == 1.0


def test_feature_packet_to_vector_top_level_keys():
    """Phase 3 (earnings/sentiment) and Research Expansion Program (insider/
    reddit/LLM-alpha) fields live as top-level feature_packet keys, not
    nested under a sub-dict -- confirm the section="" lookup path works."""
    import math
    from ml_feature_extractor import feature_packet_to_vector, FEATURE_NAMES
    fp = _good_feature_packet()
    fp["earnings_days_away"] = 5
    fp["insider_net_signal"] = 0.5
    fp["reddit_mentions"] = 42
    fp["bull_conviction_score"] = None  # not yet computed -- should be NaN, not crash
    vec = feature_packet_to_vector(fp)
    assert vec[FEATURE_NAMES.index("earnings_days_away")] == 5.0
    assert vec[FEATURE_NAMES.index("insider_net_signal")] == 0.5
    assert vec[FEATURE_NAMES.index("reddit_mentions")] == 42.0
    assert math.isnan(vec[FEATURE_NAMES.index("news_sentiment_score")])  # never set in this fixture


def test_extract_from_db_records_skips_missing_feature_packet():
    from ml_feature_extractor import extract_from_db_records
    records = [
        {"ai_prediction": {}, "stock_prediction_input": {"symbol": "SPY", "decision_horizon_days": 7},
         "actual_validation": {"actual_return_pct": 5.0}},  # no _feature_packet -- skipped
    ]
    X, y, names, meta = extract_from_db_records(records)
    assert X == []
    assert y == []


def test_extract_from_db_records_excludes_hold_labels():
    from ml_feature_extractor import extract_from_db_records
    records = [
        {
            "ai_prediction": {"_feature_packet": _good_feature_packet()},
            "stock_prediction_input": {"symbol": "SPY", "decision_horizon_days": 7},
            "actual_validation": {"actual_return_pct": 0.5},  # inside the 7d HOLD band (+-2.0) -> excluded
        },
        {
            "ai_prediction": {"_feature_packet": _good_feature_packet()},
            "stock_prediction_input": {"symbol": "SPY", "decision_horizon_days": 7},
            "actual_validation": {"actual_return_pct": 5.0},  # clear BUY
        },
    ]
    X, y, names, meta = extract_from_db_records(records)
    assert len(X) == 1
    assert y == [1]  # BUY


# ── ml_signal_model: walk_forward_split (the leakage test) ───────────────────

def test_walk_forward_split_is_time_ordered():
    """No training-fold origin_date may exceed any test-fold origin_date --
    the one rule this whole module exists to enforce."""
    from ml_signal_model import walk_forward_split
    meta = [{"origin_date": d} for d in
            ["2026-01-01", "2026-03-01", "2026-02-01", "2026-05-01", "2026-04-01",
             "2026-06-01", "2026-07-01", "2026-08-01"]]
    train_idx, test_idx = walk_forward_split(meta, test_frac=0.25)
    train_dates = [meta[i]["origin_date"] for i in train_idx]
    test_dates = [meta[i]["origin_date"] for i in test_idx]
    assert max(train_dates) <= min(test_dates)
    assert len(train_idx) + len(test_idx) == len(meta)


def test_walk_forward_split_respects_test_frac():
    from ml_signal_model import walk_forward_split
    meta = [{"origin_date": f"2026-01-{d:02d}"} for d in range(1, 21)]  # 20 rows
    train_idx, test_idx = walk_forward_split(meta, test_frac=0.25)
    assert len(test_idx) == 5
    assert len(train_idx) == 15


# ── ml_signal_model: train / predict / evaluate round trip ───────────────────

def _separable_dataset(n_per_class=20):
    """A trivially linearly-separable synthetic dataset so a real model can
    legitimately hit high holdout accuracy -- proves the pipeline works
    end-to-end without needing real market data in a unit test."""
    import random
    from ml_feature_extractor import FEATURE_NAMES
    random.seed(42)
    X, y, meta = [], [], []
    n_features = len(FEATURE_NAMES)
    for i in range(n_per_class):
        X.append([5.0 + random.gauss(0, 0.3)] * n_features)
        y.append(1)
        meta.append({"origin_date": f"2026-01-{(i % 28) + 1:02d}", "symbol": "SPY"})
    for i in range(n_per_class):
        X.append([-5.0 + random.gauss(0, 0.3)] * n_features)
        y.append(0)
        meta.append({"origin_date": f"2026-02-{(i % 28) + 1:02d}", "symbol": "SPY"})
    return X, y, meta


def test_train_raises_below_min_samples():
    from ml_signal_model import train, MIN_TRAINING_SAMPLES
    from ml_feature_extractor import FEATURE_NAMES
    import pytest
    X = [[1.0] * len(FEATURE_NAMES)] * (MIN_TRAINING_SAMPLES - 1)
    y = [1] * (MIN_TRAINING_SAMPLES - 1)
    with pytest.raises(ValueError):
        train(X, y)


def test_train_predict_evaluate_round_trip():
    from ml_signal_model import train, predict_proba, evaluate, walk_forward_split
    X, y, meta = _separable_dataset(n_per_class=25)
    train_idx, test_idx = walk_forward_split(meta, test_frac=0.3)
    X_train = [X[i] for i in train_idx]
    y_train = [y[i] for i in train_idx]
    X_test  = [X[i] for i in test_idx]
    y_test  = [y[i] for i in test_idx]

    model = train(X_train, y_train)
    pred = predict_proba(model, X_test[0])
    assert pred["decision"] in ("BUY", "SELL")
    assert 0.0 <= pred["p_buy"] <= 1.0
    assert abs(pred["p_buy"] + pred["p_sell"] - 1.0) < 1e-6

    result = evaluate(model, X_test, y_test)
    assert result["n"] == len(X_test)
    assert result["accuracy_pct"] > 80.0  # trivially separable data -- should be near-perfect


def test_evaluate_empty_test_set():
    from ml_signal_model import evaluate
    result = evaluate(object(), [], [])
    assert result == {"n": 0, "accuracy_pct": None}


# ── save_model / load_model ──────────────────────────────────────────────────

def test_load_model_missing_file_returns_none(tmp_path):
    from ml_signal_model import load_model
    assert load_model(tmp_path / "does_not_exist.pkl") is None


# ── SegmentedModel (Research Expansion Program, Component 6) ────────────────

def test_segmented_model_uses_segment_specific_model_when_present():
    from ml_signal_model import train, predict_proba, SegmentedModel
    X_up, y_up, _ = _separable_dataset(n_per_class=20)
    bull_model = train(X_up, y_up)   # always predicts BUY-leaning for positive features
    seg = SegmentedModel(models={"SPY|0-7d": bull_model}, default_model=None)
    pred = predict_proba(seg, X_up[0], segment_label="SPY|0-7d")
    assert pred is not None
    assert pred["decision"] == "BUY"


def test_segmented_model_falls_back_to_default_for_unknown_segment():
    from ml_signal_model import train, predict_proba, SegmentedModel
    X, y, _ = _separable_dataset(n_per_class=20)
    default_model = train(X, y)
    seg = SegmentedModel(models={}, default_model=default_model)
    # "TSLA|120d+" was never given its own model -- must still get an answer
    # from default_model, not None.
    pred = predict_proba(seg, X[0], segment_label="TSLA|120d+")
    assert pred is not None


def test_segmented_model_returns_none_with_no_models_at_all():
    from ml_signal_model import predict_proba, SegmentedModel
    from ml_feature_extractor import FEATURE_NAMES
    seg = SegmentedModel(models={}, default_model=None)
    pred = predict_proba(seg, [1.0] * len(FEATURE_NAMES), segment_label="SPY|0-7d")
    assert pred is None


def test_segmented_model_has_segment():
    from ml_signal_model import train, SegmentedModel
    X, y, _ = _separable_dataset(n_per_class=20)
    model = train(X, y)
    seg_with_default = SegmentedModel(models={}, default_model=model)
    seg_empty = SegmentedModel(models={}, default_model=None)
    assert seg_with_default.has_segment("ANYTHING") is True  # default covers it
    assert seg_empty.has_segment("ANYTHING") is False


def test_plain_pipeline_still_works_without_segment_label():
    """Backward compatibility: a bare Pipeline (pre-Component-6 saved model)
    must keep working when segment_label is never passed."""
    from ml_signal_model import train, predict_proba
    X, y, _ = _separable_dataset(n_per_class=20)
    model = train(X, y)
    pred = predict_proba(model, X[0])
    assert pred is not None
    assert pred["decision"] in ("BUY", "SELL")


def test_save_and_load_model_round_trip(tmp_path):
    from ml_signal_model import train, save_model, load_model, predict_proba
    X, y, meta = _separable_dataset(n_per_class=20)
    model = train(X, y)
    path = tmp_path / "test_model.pkl"
    save_model(model, path)
    assert path.exists()

    loaded = load_model(path)
    assert loaded is not None
    pred = predict_proba(loaded, X[0])
    assert pred["decision"] in ("BUY", "SELL")
