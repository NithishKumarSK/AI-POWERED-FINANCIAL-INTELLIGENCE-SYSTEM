"""
Tests for core/market_top_detector/ -- the ported claude-trading-skills
market-top-detector (6 calculators + composite scorer). Synthetic data
only, no network. All histories are MOST-RECENT-FIRST (same convention
as core/ibd_distribution_day_monitor.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _bar(date, close, volume=1000, high=None, open_=None):
    return {
        "date": date, "close": float(close), "volume": float(volume),
        "high": float(high if high is not None else close),
        "open": float(open_ if open_ is not None else close),
    }


def _flat_mrf(n, price=100.0, volume=1000, start_date="2026-01-01"):
    import datetime as dt
    d0 = dt.date.fromisoformat(start_date)
    chrono = [_bar((d0 + dt.timedelta(days=i)).isoformat(), price, volume) for i in range(n)]
    return list(reversed(chrono))


# ── distribution_days ─────────────────────────────────────────────────────

def test_distribution_days_zero_in_flat_market():
    from market_top_detector.distribution_days import calculate_distribution_days
    flat = _flat_mrf(40)
    result = calculate_distribution_days(flat, flat)
    assert result["score"] == 0
    assert result["effective_count"] == 0


def test_distribution_days_counts_decline_on_rising_volume():
    from market_top_detector.distribution_days import calculate_distribution_days
    # Chronological: day0(100,1000) day1(99,2000) -- decline -1% on rising volume = 1 DD
    chrono = [_bar("2026-01-01", 100, 1000), _bar("2026-01-02", 99, 2000)]
    mrf = list(reversed(chrono))
    padded = mrf + _flat_mrf(30, price=99, start_date="2025-11-01")  # pad for window math
    result = calculate_distribution_days(padded, padded)
    assert result["sp500"]["distribution_days"] >= 1


# ── index_technical ──────────────────────────────────────────────────────

def test_index_technical_healthy_in_strong_uptrend():
    from market_top_detector.index_technical import calculate_index_technical
    import datetime as dt
    d0 = dt.date(2025, 1, 1)
    chrono = [_bar((d0 + dt.timedelta(days=i)).isoformat(), 100 + i * 0.5) for i in range(250)]
    mrf = list(reversed(chrono))  # price trending up, history[0] = highest/most-recent
    result = calculate_index_technical(mrf, mrf)
    assert result["data_available"] is True
    assert result["score"] <= 15  # strong uptrend -- should be HEALTHY


def test_index_technical_insufficient_data_is_not_available():
    from market_top_detector.index_technical import calculate_index_technical
    short = _flat_mrf(5)
    result = calculate_index_technical(short, short)
    assert result["data_available"] is False
    assert result["score"] == 50


# ── defensive_rotation ─────────────────────────────────────────────────────

def test_defensive_rotation_insufficient_data_returns_neutral():
    from market_top_detector.defensive_rotation import calculate_defensive_rotation
    result = calculate_defensive_rotation({})
    assert result["score"] == 50
    assert result["data_available"] is False


def test_defensive_rotation_detects_defensive_leadership():
    from market_top_detector.defensive_rotation import calculate_defensive_rotation, DEFENSIVE_ETFS, OFFENSIVE_ETFS
    import datetime as dt
    d0 = dt.date(2025, 1, 1)

    def _rising_mrf(n, daily_pct):
        chrono = []
        price = 100.0
        for i in range(n):
            chrono.append(_bar((d0 + dt.timedelta(days=i)).isoformat(), price))
            price *= (1 + daily_pct)
        return list(reversed(chrono))

    historical = {}
    for sym in DEFENSIVE_ETFS:
        historical[sym] = _rising_mrf(60, 0.004)  # defensives rising
    for sym in OFFENSIVE_ETFS:
        historical[sym] = _rising_mrf(60, 0.0005)  # offensives flat-ish

    result = calculate_defensive_rotation(historical)
    assert result["data_available"] is True
    assert result["relative_performance"] > 0  # defensive outperforming
    assert result["score"] > 50


# ── breadth_divergence ─────────────────────────────────────────────────────

def test_breadth_divergence_no_data_is_neutral():
    from market_top_detector.breadth_divergence import calculate_breadth_divergence
    result = calculate_breadth_divergence(None, None, 0.0)
    assert result["score"] == 50
    assert result["data_available"] is False


def test_breadth_divergence_critical_when_breadth_collapses_near_highs():
    from market_top_detector.breadth_divergence import calculate_breadth_divergence
    result = calculate_breadth_divergence(35.0, 25.0, -1.0)  # near highs, breadth <40%
    assert result["score"] >= 80
    assert result["divergence_detected"] is True


def test_breadth_divergence_halved_when_not_near_highs():
    from market_top_detector.breadth_divergence import calculate_breadth_divergence
    near_highs = calculate_breadth_divergence(35.0, 50.0, -1.0)
    not_near_highs = calculate_breadth_divergence(35.0, 50.0, -10.0)
    assert not_near_highs["score"] < near_highs["score"]


# ── leading_stocks ─────────────────────────────────────────────────────────

def test_leading_stocks_insufficient_data_without_quotes():
    from market_top_detector.leading_stocks import calculate_leading_stock_health
    result = calculate_leading_stock_health({}, {})
    assert result["score"] == 50
    assert result["data_available"] is False


def test_leading_stocks_deep_below_52wk_high_scores_high_deterioration():
    from market_top_detector.leading_stocks import calculate_leading_stock_health, DEFAULT_LEADING_ETFS
    # -30% below 52wk high AND below a declining 50DMA -- both penalty bands fire.
    quotes = {sym: {"price": 70.0, "yearHigh": 100.0} for sym in DEFAULT_LEADING_ETFS}

    def _declining_history():
        import datetime as dt
        d0 = dt.date(2025, 11, 1)
        chrono = [_bar((d0 + dt.timedelta(days=i)).isoformat(), 70.0 + (59 - i) * 0.5) for i in range(60)]
        return list(reversed(chrono))  # most-recent-first, price=70, sma50 > 70

    historical = {sym: _declining_history() for sym in DEFAULT_LEADING_ETFS}
    result = calculate_leading_stock_health(quotes, historical)
    assert result["data_available"] is True
    assert result["score"] >= 50  # -30% (40pt) + below 50DMA (20pt), clamped to 100
    assert result["amplified"] is True  # 100% of basket deteriorating


def test_leading_stocks_at_highs_scores_healthy():
    from market_top_detector.leading_stocks import calculate_leading_stock_health, DEFAULT_LEADING_ETFS
    quotes = {sym: {"price": 100.0, "yearHigh": 100.0} for sym in DEFAULT_LEADING_ETFS}
    historical = {sym: _flat_mrf(60, price=100.0) for sym in DEFAULT_LEADING_ETFS}
    result = calculate_leading_stock_health(quotes, historical)
    assert result["score"] < 30


# ── sentiment ──────────────────────────────────────────────────────────────

def test_sentiment_no_data_is_neutral():
    from market_top_detector.sentiment import calculate_sentiment
    result = calculate_sentiment()
    assert result["score"] == 50
    assert result["data_available"] is False


def test_sentiment_extreme_complacency_scores_high():
    from market_top_detector.sentiment import calculate_sentiment
    result = calculate_sentiment(vix_level=10.0, put_call_ratio=0.5, vix_term_structure="steep_contango")
    assert result["score"] >= 70


def test_sentiment_high_vix_alone_scores_low_or_negative_contribution():
    from market_top_detector.sentiment import calculate_sentiment
    result = calculate_sentiment(vix_level=30.0)
    assert result["details"]["vix_level"]["points"] == -8


# ── scorer (composite) ──────────────────────────────────────────────────────

def test_composite_score_all_normal_is_green():
    from market_top_detector.scorer import calculate_composite_score
    scores = {k: 0 for k in ("distribution_days", "leading_stocks", "defensive_rotation", "breadth_divergence", "index_technical", "sentiment")}
    result = calculate_composite_score(scores)
    assert result["composite_score"] == 0
    assert result["zone"] == "Green (Normal)"


def test_composite_score_all_critical_is_critical_zone():
    from market_top_detector.scorer import calculate_composite_score
    scores = {k: 100 for k in ("distribution_days", "leading_stocks", "defensive_rotation", "breadth_divergence", "index_technical", "sentiment")}
    result = calculate_composite_score(scores)
    assert result["composite_score"] >= 81
    assert result["zone"] == "Critical (Very High Risk)"


def test_composite_score_missing_component_redistributes_weight():
    from market_top_detector.scorer import calculate_composite_score
    scores = {"distribution_days": 0, "leading_stocks": 0, "defensive_rotation": 0,
              "breadth_divergence": 0, "index_technical": 0, "sentiment": 100}
    availability = {"distribution_days": True, "leading_stocks": True, "defensive_rotation": True,
                     "breadth_divergence": True, "index_technical": True, "sentiment": False}
    result = calculate_composite_score(scores, availability)
    assert result["composite_score"] == 0  # sentiment's 100 excluded entirely
    assert result["data_quality"]["available_count"] == 5


def test_composite_score_correlation_discount_applied():
    from market_top_detector.scorer import calculate_composite_score
    scores = {"distribution_days": 90, "leading_stocks": 0, "defensive_rotation": 90,
              "breadth_divergence": 0, "index_technical": 0, "sentiment": 0}
    result = calculate_composite_score(scores)
    adj = result["correlation_adjustment"]
    assert len(adj) == 1
    assert adj[0]["discounted_component"] == "defensive_rotation"  # lower weight of the pair
