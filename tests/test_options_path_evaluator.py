"""Tests for core/options_path_evaluator.py -- day-by-day options
repricing (real Black-Scholes, core/portfolio_tools/options_pricer.py)
across a predicted underlying price path, with shrinking DTE."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from options_path_evaluator import evaluate_options_path
from day_by_day_path_predictor import predict_daily_path


def _nvda_like_path():
    """Mirrors the real leakage-safe NVDA case: origin $173.73, predicted
    -10.27% over 16 days -- a real, declining path, used here only as
    realistic test fixture data, not re-asserted as a live result."""
    out = predict_daily_path(173.73, -10.27, 16, atr_daily_pct=5.26)
    return out["path"]


def test_invalid_option_type_returns_error():
    path = _nvda_like_path()
    out = evaluate_options_path(path, strike=185, option_type="straddle", dte_at_day0=16, contracts=25, annual_volatility_pct=50.0)
    assert out["status"] == "ERROR"


def test_call_prices_decrease_as_underlying_falls_and_dte_shrinks():
    """A declining underlying path + shrinking DTE should drive a call's
    value down over time -- both real option-pricing effects (delta and
    theta) point the same direction here, so this is a strong, simple check."""
    path = _nvda_like_path()
    out = evaluate_options_path(path, strike=185, option_type="call", dte_at_day0=16, contracts=25, annual_volatility_pct=50.0)
    assert out["status"] == "OK"
    values = [r["predicted_option_value_per_share"] for r in out["daily_option_path"]]
    assert values[0] > values[-1]


def test_expired_days_are_skipped_with_warning():
    path = _nvda_like_path()  # 16 days
    out = evaluate_options_path(path, strike=185, option_type="call", dte_at_day0=10, contracts=25, annual_volatility_pct=50.0)
    assert out["status"] == "OK"
    assert max(r["day_offset"] for r in out["daily_option_path"]) < 10
    assert any("expiration" in w for w in out["warnings"])


def test_new_position_recommendation_buy_before_sell():
    path = _nvda_like_path()
    out = evaluate_options_path(path, strike=185, option_type="call", dte_at_day0=16, contracts=25, annual_volatility_pct=50.0)
    rec = out["new_position_recommendation"]
    assert rec["best_buy_day"] is not None
    if rec["best_sell_day"] is not None:
        assert rec["best_sell_day"] > rec["best_buy_day"]


def test_existing_position_requires_premium_paid():
    path = _nvda_like_path()
    out_without = evaluate_options_path(path, strike=185, option_type="call", dte_at_day0=16, contracts=25, annual_volatility_pct=50.0)
    assert out_without["existing_position_recommendation"] is None

    out_with = evaluate_options_path(
        path, strike=185, option_type="call", dte_at_day0=16, contracts=25,
        annual_volatility_pct=50.0, premium_paid_per_share=1.50,
    )
    rec = out_with["existing_position_recommendation"]
    assert rec is not None
    assert rec["total_cost"] == 1.50 * 100 * 25
    # Independent rounding paths (value_per_share rounded to 4dp before this
    # recompute vs. computed at full precision inside evaluate_options_path)
    # can differ by a few cents -- check they're close, not bit-identical.
    expected = round(rec["best_exit_value_per_share"] * 100 * 25 - rec["total_cost"], 2)
    assert abs(rec["predicted_pl_at_best_exit"] - expected) < 1.0


def test_contracts_scale_total_position_value_linearly():
    path = _nvda_like_path()
    out_1 = evaluate_options_path(path, strike=185, option_type="call", dte_at_day0=16, contracts=1, annual_volatility_pct=50.0)
    out_25 = evaluate_options_path(path, strike=185, option_type="call", dte_at_day0=16, contracts=25, annual_volatility_pct=50.0)
    v1 = out_1["daily_option_path"][0]["predicted_total_position_value"]
    v25 = out_25["daily_option_path"][0]["predicted_total_position_value"]
    # Rounding per-share value to 4dp before scaling by contracts means
    # 1-contract vs 25-contract totals aren't bit-identical multiples --
    # within a few cents is the real, expected behavior.
    assert abs(v25 - v1 * 25) < 0.5


def test_no_valid_days_returns_error():
    path = _nvda_like_path()
    out = evaluate_options_path(path, strike=185, option_type="call", dte_at_day0=0, contracts=25, annual_volatility_pct=50.0)
    assert out["status"] == "ERROR"
