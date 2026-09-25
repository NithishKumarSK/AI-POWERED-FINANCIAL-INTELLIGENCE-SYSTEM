"""
Prototype (not wired into the app): can Gemini's VISION input read a price
chart image and identify support/resistance levels / patterns better than the
numeric-only feature packet the pipeline uses today?

For each known case below, renders a candlestick chart using only bars up to
the prediction origin date (same leakage discipline as the rest of the app),
sends it to Gemini alongside a chart-reading prompt, and prints the result
next to what the existing numeric-only pipeline decided and what actually
happened. This is standalone research -- it does not touch
gemini_stock_prediction_agent.py's real prediction path.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from historical_price_service import fetch_price_history

GEMINI_KEY = __import__("os").getenv("GEMINI_API_KEY", "") or __import__("os").getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = __import__("os").getenv("AGENT_MODEL", "gemini-2.5-flash")

# Known cases: (symbol, origin_date, numeric_pipeline_decision, actual_decision, actual_return_pct, note)
CASES = [
    ("TSLA", "2026-07-31", "SELL (pre-fix) / HOLD (post-fix)", "BUY", 18.23,
     "RSI=18 extreme oversold, strong downtrend -- capitulation-guard case"),
    ("TSLA", "2025-09-01", "SELL", "BUY", 37.62,
     "Choppy market (ADX=13.6), no level nearby on 20d window -- massive missed reversal"),
    ("TSLA", "2026-07-01", "BUY", "SELL", -26.83,
     "Choppy market (ADX=16.3), near_resistance=True -- bought into a ceiling"),
    ("TSLA", "2025-11-01", "BUY", "SELL", -5.79,
     "Choppy market (ADX=8.9), near_resistance=True, near 120d high -- bought into a ceiling"),
]

CHART_LOOKBACK_DAYS = 90  # ~4-4.5 trading months -- legible daily candles, clear recent trend


def render_chart(bars: list, symbol: str, origin: str, lookback_days: int = CHART_LOOKBACK_DAYS) -> bytes:
    """Simple OHLC candlestick chart, bars already filtered to <= origin.

    SMA20/SMA50 are computed over the FULL history (not just the visible
    window) so they're accurate all the way to the left edge of a zoomed-in
    chart -- computing them only from the sliced window would understate the
    lookback for the first ~50 visible bars.
    """
    full_closes = [b["close"] for b in bars]
    full_sma20 = [sum(full_closes[max(0, i - 19):i + 1]) / len(full_closes[max(0, i - 19):i + 1]) for i in range(len(full_closes))]
    full_sma50 = [sum(full_closes[max(0, i - 49):i + 1]) / len(full_closes[max(0, i - 49):i + 1]) for i in range(len(full_closes))]

    plot_bars = bars[-lookback_days:]
    sma20 = full_sma20[-lookback_days:]
    sma50 = full_sma50[-lookback_days:]

    fig, ax = plt.subplots(figsize=(14, 7), dpi=130)

    for i, b in enumerate(plot_bars):
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        color = "#2ca02c" if c >= o else "#d62728"
        ax.plot([i, i], [l, h], color=color, linewidth=0.8, zorder=2)
        body_low, body_high = min(o, c), max(o, c)
        ax.add_patch(Rectangle((i - 0.3, body_low), 0.6, max(body_high - body_low, 0.01),
                                facecolor=color, edgecolor=color, zorder=3))

    ax.plot(range(len(plot_bars)), sma20, color="#1f77b4", linewidth=1.2, label="SMA20")
    ax.plot(range(len(plot_bars)), sma50, color="#ff7f0e", linewidth=1.2, label="SMA50")

    n = len(plot_bars)
    tick_idx = list(range(0, n, max(1, n // 15)))
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([plot_bars[i]["date"] for i in tick_idx], rotation=45, ha="right")
    ax.set_xlim(-1, n)
    ax.set_title(f"{symbol} daily chart through {origin} (prediction origin -- no data after this date) -- last {n} trading days")
    ax.set_ylabel("Price ($)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.25)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


CHART_PROMPT = """You are a professional technical chart analyst. You are shown a daily candlestick
chart for {symbol} ending on {origin} (the prediction origin -- this is the LAST date
you may use; nothing after it exists yet as far as you are concerned). SMA20 (blue) and
SMA50 (orange) are overlaid.

Visually read the chart the way an experienced trader would:
1. Identify concrete horizontal support and resistance levels -- price zones where the
   chart shows multiple touches, rejections, or consolidation, not just the most recent
   local high/low. Give approximate price values.
2. Describe the overall pattern (e.g. range-bound/consolidation, breakout, channel,
   double top/bottom, head-and-shoulders, flag) if one is visible.
3. State where the current price sits relative to those levels, and whether that
   position argues for continuation or reversal over the next 30 calendar days.
4. Give a decision: BUY, SELL, or HOLD, with a predicted_return_pct estimate.

Respond ONLY with JSON:
{{"support_levels": [<price>, ...], "resistance_levels": [<price>, ...],
  "chart_pattern": "<description>", "position_vs_levels": "<description>",
  "decision": "BUY|SELL|HOLD", "predicted_return_pct": <number>,
  "reasoning": "<2-4 sentences>"}}
"""


def analyze_chart(symbol: str, origin: str, image_bytes: bytes) -> dict:
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=GEMINI_KEY)
    prompt = CHART_PROMPT.format(symbol=symbol, origin=origin)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            genai_types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            prompt,
        ],
        config=genai_types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=8000,
            response_mime_type="application/json",
        ),
    )
    raw = (response.text or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"error": "parse_failed", "raw": raw[:2000], "raw_len": len(raw)}


if __name__ == "__main__":
    if not GEMINI_KEY:
        print("No GEMINI_API_KEY/GOOGLE_API_KEY configured.")
        sys.exit(1)

    price_cache: dict = {}
    for symbol, origin, numeric_decision, actual_decision, actual_return, note in CASES:
        if symbol not in price_cache:
            hist, err = fetch_price_history(symbol, min_days=1200)
            price_cache[symbol] = hist
        bars = [b for b in price_cache[symbol] if b["date"] <= origin]

        img_bytes = render_chart(bars, symbol, origin)
        out_dir = ROOT / "data" / "chart_reading_prototype"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{symbol}_{origin}.png").write_bytes(img_bytes)

        result = analyze_chart(symbol, origin, img_bytes)

        print(f"\n{'='*90}")
        print(f"{symbol} origin={origin}  |  {note}")
        print(f"  Numeric pipeline said: {numeric_decision}   |   Actual: {actual_decision} ({actual_return:+.2f}%)")
        print(f"  Chart image saved to: {out_dir / f'{symbol}_{origin}.png'}")
        if "error" in result:
            print(f"  CHART READ FAILED: {result}")
            continue
        print(f"  Vision decision: {result.get('decision')}  predicted_return_pct={result.get('predicted_return_pct')}")
        print(f"  Support levels found:    {result.get('support_levels')}")
        print(f"  Resistance levels found: {result.get('resistance_levels')}")
        print(f"  Chart pattern: {result.get('chart_pattern')}")
        print(f"  Position vs levels: {result.get('position_vs_levels')}")
        print(f"  Reasoning: {result.get('reasoning')}")
