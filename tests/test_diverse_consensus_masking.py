"""Tests for _mask_feature_packet_for_diversity (core/gemini_stock_prediction_agent.py)
-- the genuinely-diverse 3-call consensus component (ENABLE_DIVERSE_CONSENSUS).
Pure function, no API calls -- fast, no mocks needed."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def _sample_feature_packet():
    return {
        "status": "OK", "symbol": "TSLA", "origin_price": 250.0, "horizon_days": 14,
        "returns": {"return_1d": 1.2, "return_5d": 3.0},
        "trend": {"ADX_14": 22.0, "trend_regime": "bullish"},
        "momentum": {"RSI_14": 55.0},
        "volatility": {"ATR_daily_pct": 2.1},
        "news_sentiment_score": 0.4,
        "news_sentiment_article_count": 12,
        "insider_buy_count": 3,
        "congress_net_signal": 1.0,
        "sec_revenue": 1000000,
        "macro_regime_composite_score": 5.0,
        "market_breadth_200ma": 0.6,
        "fed_funds_rate_pct": 4.5,
    }


def test_technicals_only_excludes_news_and_regime_keys():
    from gemini_stock_prediction_agent import _mask_feature_packet_for_diversity
    fp = _sample_feature_packet()
    masked = _mask_feature_packet_for_diversity(fp, "technicals_only")
    assert "trend" in masked and "momentum" in masked and "volatility" in masked
    assert "news_sentiment_score" not in masked
    assert "insider_buy_count" not in masked
    assert "macro_regime_composite_score" not in masked
    assert "fed_funds_rate_pct" not in masked


def test_news_only_excludes_technical_and_regime_keys():
    from gemini_stock_prediction_agent import _mask_feature_packet_for_diversity
    fp = _sample_feature_packet()
    masked = _mask_feature_packet_for_diversity(fp, "news_only")
    assert masked.get("news_sentiment_score") == 0.4
    assert masked.get("insider_buy_count") == 3
    assert masked.get("sec_revenue") == 1000000
    assert "trend" not in masked
    assert "momentum" not in masked
    assert "macro_regime_composite_score" not in masked


def test_regime_only_excludes_technical_and_news_keys():
    from gemini_stock_prediction_agent import _mask_feature_packet_for_diversity
    fp = _sample_feature_packet()
    masked = _mask_feature_packet_for_diversity(fp, "regime_only")
    assert masked.get("macro_regime_composite_score") == 5.0
    assert masked.get("market_breadth_200ma") == 0.6
    assert masked.get("fed_funds_rate_pct") == 4.5
    assert "trend" not in masked
    assert "news_sentiment_score" not in masked
    assert "insider_buy_count" not in masked


def test_all_three_modes_keep_metadata_and_returns():
    """Basic identity/price metadata + returns must survive every mask --
    otherwise a call can't even produce a numeric predicted_return_pct."""
    from gemini_stock_prediction_agent import _mask_feature_packet_for_diversity
    fp = _sample_feature_packet()
    for mode in ("technicals_only", "news_only", "regime_only"):
        masked = _mask_feature_packet_for_diversity(fp, mode)
        assert masked["symbol"] == "TSLA"
        assert masked["origin_price"] == 250.0
        assert masked["returns"] == fp["returns"]


def test_three_modes_produce_three_disjoint_evidence_sets():
    """The core premise of this component: the three masks must not be
    identical to each other, unlike the existing framing-only consensus."""
    from gemini_stock_prediction_agent import _mask_feature_packet_for_diversity
    fp = _sample_feature_packet()
    tech = _mask_feature_packet_for_diversity(fp, "technicals_only")
    news = _mask_feature_packet_for_diversity(fp, "news_only")
    regime = _mask_feature_packet_for_diversity(fp, "regime_only")
    assert tech != news
    assert news != regime
    assert tech != regime


def test_unknown_mode_returns_full_copy():
    from gemini_stock_prediction_agent import _mask_feature_packet_for_diversity
    fp = _sample_feature_packet()
    masked = _mask_feature_packet_for_diversity(fp, "bogus_mode")
    assert masked == fp
