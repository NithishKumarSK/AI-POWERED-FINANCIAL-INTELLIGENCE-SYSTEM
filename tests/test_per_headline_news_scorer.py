"""Tests for core/per_headline_news_scorer.py -- the actual mechanism
behind Lopez-Lira & Tang's real edge (per-headline YES/NO classification,
not one aggregate sentiment score). No live API calls -- tests the
input-guard and aggregation logic only."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))


def test_score_headlines_empty_titles_returns_error():
    from per_headline_news_scorer import score_headlines
    data, err = score_headlines("TSLA", [])
    assert data is None
    assert err == "No headlines to score"


def test_score_headlines_blank_titles_filtered_out():
    from per_headline_news_scorer import score_headlines
    data, err = score_headlines("TSLA", ["", "   ", None])
    assert data is None
    assert err == "No headlines to score"


def test_score_headlines_no_api_key(monkeypatch):
    import per_headline_news_scorer as mod
    monkeypatch.setattr(mod, "_GEMINI_KEY", "")
    data, err = mod.score_headlines("TSLA", ["Tesla beats earnings estimates"])
    assert data is None
    assert "GEMINI_API_KEY" in err or "GOOGLE_API_KEY" in err


def test_score_headlines_caps_at_max_headlines(monkeypatch):
    """More than _MAX_HEADLINES titles must be truncated, not sent in full --
    cost control for the single batched call."""
    import per_headline_news_scorer as mod
    monkeypatch.setattr(mod, "_GEMINI_KEY", "fake-key")

    captured = {}

    class _FakeResponse:
        text = '{"classifications": [{"index": 0, "direction": "UP"}]}'

    class _FakeModels:
        def generate_content(self, **kwargs):
            captured["contents"] = kwargs["contents"]
            return _FakeResponse()

    class _FakeClient:
        def __init__(self, *a, **k):
            self.models = _FakeModels()

    import google.genai as real_genai
    monkeypatch.setattr(real_genai, "Client", _FakeClient)

    titles = [f"Headline {i}" for i in range(25)]
    mod.score_headlines("TSLA", titles)
    # Only the first _MAX_HEADLINES titles should appear in the prompt sent.
    assert "Headline 9" in captured["contents"]
    assert "Headline 15" not in captured["contents"]


def test_score_headlines_aggregates_classifications(monkeypatch):
    import per_headline_news_scorer as mod
    monkeypatch.setattr(mod, "_GEMINI_KEY", "fake-key")

    class _FakeResponse:
        text = (
            '{"classifications": ['
            '{"index": 0, "direction": "UP"}, '
            '{"index": 1, "direction": "UP"}, '
            '{"index": 2, "direction": "DOWN"}, '
            '{"index": 3, "direction": "UNCLEAR"}'
            ']}'
        )

    class _FakeModels:
        def generate_content(self, **kwargs):
            return _FakeResponse()

    class _FakeClient:
        def __init__(self, *a, **k):
            self.models = _FakeModels()

    import google.genai as real_genai
    monkeypatch.setattr(real_genai, "Client", _FakeClient)

    data, err = mod.score_headlines("TSLA", ["h1", "h2", "h3", "h4"])
    assert err == ""
    assert data["per_headline_news_up_count"] == 2
    assert data["per_headline_news_down_count"] == 1
    assert data["per_headline_news_unclear_count"] == 1
    assert data["per_headline_news_n_scored"] == 4
    # score = (up - down) / n_scored = (2 - 1) / 4 = 0.25
    assert data["per_headline_news_score"] == 0.25


def test_score_headlines_malformed_response_returns_error(monkeypatch):
    import per_headline_news_scorer as mod
    monkeypatch.setattr(mod, "_GEMINI_KEY", "fake-key")

    class _FakeResponse:
        text = "not json at all"

    class _FakeModels:
        def generate_content(self, **kwargs):
            return _FakeResponse()

    class _FakeClient:
        def __init__(self, *a, **k):
            self.models = _FakeModels()

    import google.genai as real_genai
    monkeypatch.setattr(real_genai, "Client", _FakeClient)

    data, err = mod.score_headlines("TSLA", ["h1"])
    assert data is None
    assert err
