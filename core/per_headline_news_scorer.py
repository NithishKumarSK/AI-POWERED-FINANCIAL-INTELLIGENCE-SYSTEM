"""
per_headline_news_scorer.py -- Research Expansion Program: per-headline
directional scoring, the actual mechanism behind Lopez-Lira & Tang's real,
tradable edge (arXiv 2304.07619 v6): their GPT-4 call classified EACH
headline YES/NO/UNKNOWN for "will this news increase the stock price,"
rather than this project's existing approach of showing the whole feature
packet (including an aggregate news_sentiment_score from Alpha Vantage) to
one model call that reasons over everything at once.

Live-only (core/free_news_service.py's fetch_yahoo_headline_tags has no
historical capability -- same gate as market movers and yfinance earnings
fallback: _is_recent_origin). OPT-IN (ENABLE_PER_HEADLINE_NEWS_SCORING,
default false) -- costs one extra Gemini call per prediction, only when
there are fresh headlines to score.

One batched call (not N calls, one per headline) for cost reasons -- Gemini
classifies all headlines in a single structured-JSON response.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_paths
bootstrap_paths.add_module_paths()

_GEMINI_KEY = os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", os.getenv("AGENT_MODEL", "gemini-3.7-flash"))

_MAX_HEADLINES = 10

_PROMPT_TEMPLATE = """For {symbol}, classify each headline below for whether it is likely to \
INCREASE or DECREASE the stock price in the short term (same-day to next-few-days), \
based ONLY on the headline text itself -- not on any price data or your own \
knowledge of what actually happened. If a headline is neutral, off-topic, or \
you can't tell, classify it UNCLEAR.

Headlines:
{headlines_block}

Respond with ONLY a JSON object, no other text:
{{"classifications": [{{"index": <int>, "direction": "UP" | "DOWN" | "UNCLEAR"}}, ...]}}
One entry per headline, in the same order, using the same index (0-based)."""


def score_headlines(symbol: str, titles: List[str]) -> Tuple[Optional[dict], str]:
    """Returns (data, error_string). data shape on success:
        {"per_headline_news_score": float (-1..1), "up_count": int,
         "down_count": int, "unclear_count": int, "n_scored": int}
    per_headline_news_score = (up_count - down_count) / n_scored (0 if
    n_scored == 0). Returns (None, error) on any failure -- never raises."""
    titles = [t for t in (titles or []) if t and t.strip()][:_MAX_HEADLINES]
    if not titles:
        return None, "No headlines to score"
    if not _GEMINI_KEY:
        return None, "GEMINI_API_KEY/GOOGLE_API_KEY not set"

    headlines_block = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
    prompt = _PROMPT_TEMPLATE.format(symbol=symbol, headlines_block=headlines_block)

    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=_GEMINI_KEY, http_options=genai_types.HttpOptions(timeout=30000))
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=600,
                response_mime_type="application/json",
                thinking_config=genai_types.ThinkingConfig(thinking_budget=512),
            ),
        )
        raw = (response.text or "").strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None, "No JSON object found in response"
        parsed = json.loads(match.group(0))
        classifications = parsed.get("classifications", [])
        if not classifications:
            return None, "Empty classifications list"

        up = sum(1 for c in classifications if c.get("direction") == "UP")
        down = sum(1 for c in classifications if c.get("direction") == "DOWN")
        unclear = sum(1 for c in classifications if c.get("direction") == "UNCLEAR")
        n_scored = up + down + unclear
        score = round((up - down) / n_scored, 4) if n_scored else 0.0

        return {
            "per_headline_news_score": score,
            "per_headline_news_up_count": up,
            "per_headline_news_down_count": down,
            "per_headline_news_unclear_count": unclear,
            "per_headline_news_n_scored": n_scored,
        }, ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
