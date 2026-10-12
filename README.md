# AlphaVerity

### *An AI market-intelligence platform that predicts, then proves itself against real history — and tells you the truth about how often it's right.*

---

> **"The AI predicts. History verifies. The system shows you exactly how good it really is — no inflated numbers, no cherry-picked runs, no hiding behind a vague 'accuracy' badge."**

---

## The Problem

Every "AI stock predictor" makes the same two mistakes:

1. **It never tells you how it's actually done historically** — predictions appear, nobody checks them against what really happened.
2. **When it does report accuracy, the number is usually fake** — trained and measured on the same data, or quietly inflated by a threshold mismatch that makes the model look better than it is.

AlphaVerity does neither. Every prediction runs through a **walk-forward validator**: the AI only ever sees data up to the moment of prediction, the real outcome is fetched *after* the fact, and every run — win or lose — is written to a shared database and shown in the UI. If the model is only right 35% of the time this week, the dashboard says 35%, not "exceptional accuracy."

---

## What This Is

AlphaVerity's live product is a **Stock Price Walk-Forward Validation Engine**: given a symbol, a historical context window, and a prediction horizon, it produces a BUY/SELL/HOLD call and a target price — using a multi-call Gemini consensus engine fed by technical indicators, insider trading activity, retail social-media attention, earnings proximity, and a trained ML signal model — then checks that call against what the market actually did.

It is not one model. It is a **pipeline of independently-verified components**, each one added only after being proven to work against live data, each gated by the same rule: *if it doesn't clear a real, pre-defined accuracy bar, it doesn't ship into the live decision path.*

```
                              ┌───────────────────────────────────────┐
                              │              USER INPUT                │
                              │  Symbol · Context Window · Horizon ·   │
                              │  Capital · Benchmark · Price Basis     │
                              └───────────────────┬─────────────────────┘
                                                  │
                      ┌───────────────────────────▼────────────────────────────┐
                      │              TWO-WINDOW LEAKAGE GUARD                    │
                      │  Historical Context  →  Prediction Origin  →  Target     │
                      │  AI sees ONLY the left side. The right side is fetched   │
                      │  and compared AFTER the AI has already committed.        │
                      └───────────────────────────┬────────────────────────────┘
                                                  │
        ┌─────────────────────────────────────────▼─────────────────────────────────────────┐
        │                              SIGNAL ENRICHMENT LAYER                                 │
        │                                                                                      │
        │   Technical indicators (RSI/MACD/SMA/Bollinger/ATR)  ·  Benchmark relative strength  │
        │   SEC EDGAR insider Form-4 activity (free, official)  ·  Put/call ratio               │
        │   ApeWisdom Reddit mention velocity (free, live-only)                                 │
        │   Alpha Vantage earnings-proximity warning + news sentiment                            │
        │   Symbol-specific calibration history  ·  Segment reliability label (PROVEN/UNPROVEN)  │
        └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                                  │
                      ┌───────────────────────────▼────────────────────────────┐
                      │               GEMINI CONSENSUS ENGINE                    │
                      │                                                          │
                      │  Standard mode (default): 3 independent framings         │
                      │    standard · devil's-advocate · pure-technical          │
                      │                                                          │
                      │  Debate mode (opt-in, ENABLE_DEBATE_CONSENSUS):          │
                      │    bull round 1 → bear round 1 → each rebuts the other's │
                      │    specific argument → round 2 → final synthesis         │
                      │                                                          │
                      │  + structured numeric alpha scores (bull/bear conviction, │
                      │    narrative-dependency) fed forward as ML features       │
                      │  + horizon-scaled decision threshold (sqrt-time dead-band)│
                      └───────────────────────────┬────────────────────────────┘
                                                  │
                      ┌───────────────────────────▼────────────────────────────┐
                      │          ML SIGNAL MODEL — SHADOW-MODE CROSS-CHECK       │
                      │  Segmented gradient-boosting ensemble (per symbol ×      │
                      │  horizon bucket). Only saved if it beats its own         │
                      │  walk-forward holdout baseline by ≥3pp AND clears a 52%  │
                      │  floor — un-proven segments ship with no model at all,   │
                      │  not a fake one.                                        │
                      └───────────────────────────┬────────────────────────────┘
                                                  │
                      ┌───────────────────────────▼────────────────────────────┐
                      │              CONFIDENCE CALIBRATION                      │
                      │  Maps the AI's self-reported confidence to its REAL      │
                      │  historical hit rate in that confidence bin — corrects   │
                      │  for the common case where raw confidence is inverted    │
                      │  relative to real accuracy.                              │
                      └───────────────────────────┬────────────────────────────┘
                                                  │
                      ┌───────────────────────────▼────────────────────────────┐
                      │        ACTUAL OUTCOME FETCHED (strictly AFTER the AI    │
                      │        has already produced its prediction)             │
                      └───────────────────────────┬────────────────────────────┘
                                                  │
                      ┌───────────────────────────▼────────────────────────────┐
                      │   COMPARISON ENGINE — decision_match · directional_match │
                      │   abs_return_error_pct, scored against a horizon-scaled  │
                      │   threshold identical to the one the AI itself used      │
                      └───────────────────────────┬────────────────────────────┘
                                                  │
                      ┌───────────────────────────▼────────────────────────────┐
                      │        CENTRAL SUPABASE POSTGRES — every run persists    │
                      │        here, win or lose, and feeds every badge above    │
                      │        back in real time.                               │
                      └───────────────────────────────────────────────────────────┘
```

---

## Why the Accuracy Numbers Are Believable

This is the part most "AI trading" projects get wrong, so it gets stated plainly:

- **No training-on-test leakage.** The historical context window and the prediction window are hard-separated; the AI call that produces a prediction never receives the target-window data.
- **No threshold gaming.** The decision boundary (BUY/SELL/HOLD) is scaled by `√(horizon_days)` and applied **identically** on the AI's own guardrails and on the ground-truth labeling — so the AI can't look better just because its deciding band and the scoring band disagree.
- **No silent re-tries or stale caches.** Every in-app accuracy badge reads live from the shared database on every render (5-minute cache, not a static number baked into a file) — a bug that let one badge go stale for weeks was found and fixed in this project's own history, which is exactly the kind of thing this discipline exists to prevent.
- **Literature-grounded targets, not vanity numbers.** Academic research on short-horizon stock direction prediction consistently finds **50-60% directional accuracy is the legitimate, defensible range** — and that anything a system reports above ~70-80% is a leakage red flag, not a breakthrough. AlphaVerity's own in-app messaging cites this range explicitly instead of chasing or claiming an unrealistic number.
- **Honest failure is a feature.** When the AI's own 3-way consensus genuinely disagrees, it **refuses to force a decision** rather than guess — that shows up in the data as a "SKIP — INSUFFICIENT SIGNAL QUALITY" result, not a coin-flip dressed up as confidence.
- **Segment-aware, not blended.** A single blended "accuracy %" hides that a broad index ETF and a narrative-driven single stock behave completely differently. AlphaVerity labels each `(symbol, horizon-bucket)` segment as `PROVEN` / `UNPROVEN` / `INSUFFICIENT_DATA` from its own real track record (minimum 10 resolved runs before it's trusted either way), so the UI never presents a coin-flip segment with the same visual confidence as a working one.

The live numbers move every time a new prediction is saved — that's the point. Open the app for the current, real figures rather than trusting a number printed in this file.

---

## The Thirteen Components

Built incrementally, each one validated against live data before being trusted, each one allowed to simply *not help* without being forced into the product:

| # | Component | What it does |
|---|-----------|---------------|
| 1 | **Horizon-scaled decision threshold** | Replaces a flat ±2% BUY/SELL/HOLD band with `2.0 × √(horizon_days/7)` — a 1-day call and a 30-day call are no longer judged by the same yardstick. |
| 2 | **Walk-forward batch validation harness** | Runs seeded symbol/horizon/origin-date grids through the real prediction pipeline and breaks results down by segment — the same harness used to evaluate every change below before it ships. |
| 3 | **Segment reliability labeling** | Classifies every `(symbol, horizon-bucket)` as PROVEN / UNPROVEN / INSUFFICIENT_DATA from real resolved history, shown directly in the prediction form before you run anything. |
| 4 | **Confidence calibration** | Builds a mapping from the AI's stated confidence to its actual historical hit rate in that bin, correcting for over- or under-confidence. |
| 5 | **ML signal model (shadow-mode)** | A segmented gradient-boosting ensemble trained on technical + alternative-data features, gated by a non-negotiable "beat baseline by ≥3pp" rule before it's ever saved. |
| 6 | **SEC EDGAR insider activity** | Free, official Form-4 insider buy/sell signal, fetched and parsed directly from `data.sec.gov` with strict as-of-date leakage filtering. |
| 7 | **ApeWisdom Reddit attention** | Free, keyless retail-attention signal (mention volume, rank, 24h change) — live-only, explicitly excluded from historical backtests since it has no point-in-time history. |
| 8 | **Alpha Vantage earnings & sentiment** | Earnings-proximity warnings and news-sentiment scoring layered into the prompt context. |
| 9 | **LLM-generated structured alpha scores** | Gemini outputs numeric bull/bear conviction and narrative-dependency scores alongside its decision — these feed the ML model as features, not just prose nobody can act on. |
| 10 | **Bull/Bear debate consensus (opt-in)** | A TradingAgents-inspired 5-call architecture — bull and bear each argue, then each rebuts the *other's specific* round-1 argument — gated behind `ENABLE_DEBATE_CONSENSUS` and never defaulted on without first winning head-to-head against the standard 3-call consensus on the batch harness. |
| 11 | **Central Supabase Postgres DB** | Every validated run persists centrally (not to a local file), so every accuracy badge, every segment label, and every historical record is shared and live. |
| 12 | **Chart-vision input (opt-in)** | Candlestick chart rendering fed directly to Gemini as an image, behind `ENABLE_CHART_VISION`. |
| 13 | **Literature-grounded UI messaging** | Every accuracy claim in the product cites the real academic realistic range (50-60%) instead of an arbitrary internal target. |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **AI reasoning** | Google Gemini (`gemini-3.7-flash` default, configurable via `GEMINI_MODEL`) — 3-call or 5-call consensus |
| **ML signal model** | scikit-learn `HistGradientBoostingClassifier`, segmented per symbol × horizon bucket |
| **Database** | Supabase (managed Postgres) — central, shared, real-time |
| **Backend API** | FastAPI (`backend/main.py` — "AlphaVerity API") |
| **Frontend** | React 19 + TypeScript + Vite + Tailwind CSS + Recharts |
| **Interactive dashboard** | Streamlit (`core/stock_prediction_app.py`) |
| **Market data** | RapidAPI TradingView (primary), yfinance (fallback), with transparent per-run provider attribution |
| **Alternative data** | SEC EDGAR (insider trades), ApeWisdom (Reddit attention), Alpha Vantage (earnings/sentiment) |
| **Language / runtime** | Python 3.11+, Node.js (frontend tooling) |
| **Testing** | pytest — **868 passing, 1 skipped** across the full suite |

---

## Repository Map

```
Stock-Prediction-Agent/
│
├── core/                        ← Live product logic (34 modules)
│   ├── stock_prediction_app.py      Streamlit dashboard (the live demo entry point)
│   ├── gemini_stock_prediction_agent.py   Gemini consensus engine + every enrichment layer
│   ├── stock_walkforward_validator.py     Leakage-safe walk-forward validation
│   ├── stock_comparison_engine.py         Horizon-scaled decision + comparison logic
│   ├── batch_validation_runner.py         Seeded multi-run backtest harness
│   ├── segment_reliability.py             PROVEN/UNPROVEN classification
│   ├── confidence_calibrator.py           Confidence-to-real-hit-rate mapping
│   ├── ml_signal_model.py / ml_training_runner.py / ml_feature_extractor.py
│   ├── insider_activity_service.py        SEC EDGAR insider signal
│   ├── social_attention_service.py        ApeWisdom Reddit signal
│   └── news_sentiment_service.py          Alpha Vantage earnings/sentiment
│
├── backend/                     ← FastAPI REST API
│   ├── main.py                      uvicorn entry point ("AlphaVerity API")
│   ├── orchestration.py             Shared prediction pipeline (same path the UI uses)
│   └── routers/                     stock_predictions · pending_predictions · me
│
├── frontend/                    ← React + TypeScript dashboard (Vite, Tailwind, Recharts)
│
├── db/                          ← Central Postgres layer
│   ├── connection.py                Supabase connection pooling
│   ├── stock_prediction_repository.py   Save/load validated prediction records
│   └── schema.sql / rls.sql
│
├── tools/                       ← External API clients
│   ├── alpha_vantage_client.py · apewisdom_client.py · sec_edgar_client.py
│   └── tradingview_*.py, rapidapi_client.py
│
├── tests/                       ← 868 passing tests
├── scripts/adhoc/                ← One-off migration/backfill scripts
├── discord_stock_prediction_agent/  ← Discord paper-trading bot (Alpaca paper endpoint only)
├── legacy/                      ← Archived options-strategy pipeline (not the live flow)
└── docs/                        ← Integration notes, diagnostic reports
```

---

## Quick Start

### Prerequisites

```
Python 3.11+
Node.js 18+ (for the React frontend)
Google Gemini API key
Supabase project (Postgres connection string)
Optional: RapidAPI key, Alpha Vantage key, SEC EDGAR contact email
```

### Installation

```bash
git clone <repository-url>
cd Stock-Prediction-Agent

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Environment Configuration

Copy `.env.example` to `.env` and fill in real values — see that file for the complete, current list (Gemini, Supabase, RapidAPI, Alpha Vantage, SEC EDGAR contact, Discord, Alpaca).

### Launch the live demo (Streamlit)

```bash
streamlit run core/stock_prediction_app.py
```

### Launch the API + web dashboard

```bash
# Terminal 1 — API
uvicorn backend.main:app --reload --port 8000
# Docs at http://localhost:8000/docs

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

### Run the tests

```bash
pytest -q
# 868 passed, 1 skipped
```

---

## Design Principles

| Principle | What it means in practice |
|-----------|---------------------------|
| **No data leakage** | The AI never sees the target window before predicting; every new data source (SEC EDGAR, ApeWisdom, Alpha Vantage) is re-validated against its own as-of-date, not trusted from the upstream API's own filter alone. |
| **No inflated accuracy** | Every accuracy badge reads live from the shared database. No hardcoded numbers, no stale snapshots, no local-file caches presented as current truth. |
| **No forced decisions** | When the consensus genuinely disagrees, the system skips the prediction rather than output a coin-flip dressed as confidence. |
| **No unproven claims about unproven segments** | A symbol/horizon combination with too little history says "insufficient data" — not a confident-looking number built on five runs. |
| **Gate every model change on evidence** | New ML models must beat their own walk-forward baseline by a real margin before they're saved. New consensus architectures (like the debate mode) must win head-to-head on the batch harness before being defaulted on. |
| **Literature-grounded targets** | 50-60% directional accuracy is treated as a real, legitimate edge — not a disappointment to be hidden, and not something to inflate past the point where it would be a leakage red flag. |
| **Paper trading only** | The Discord extension can submit orders only to Alpaca's paper endpoint; production configuration rejects a live Alpaca base URL. |

---

## Discord Paper-Trading Agent

`discord_stock_prediction_agent/` runs a production-oriented Discord layer that receives raw equity and options signals, routes stock trades through Stock Price Validation, and submits approved orders only to Alpaca's paper endpoint.

```powershell
python -m discord_stock_prediction_agent.discord_agent
```

Full setup, environment variables, signal formats, and runtime controls (`!agent_on` / `!agent_off` / `!agent_mode`) are documented in [`discord_stock_prediction_agent/README.md`](discord_stock_prediction_agent/README.md).

---

## Legacy: Options-Strategy Pipeline

An earlier options-strategy backtesting pipeline (`strategy_prediction_agent.py`, `strategy_calibration_engine.py`, the tastytrade production backtester integration) is preserved under `legacy/` for reference. It is **not** part of the live product and is not run by the Quick Start commands above.

---

## Roadmap

- [ ] Validate the Bull/Bear debate consensus against the standard 3-call consensus on the batch harness, segment-by-segment, before considering a default flip
- [ ] Alpha Vantage `NEWS_SENTIMENT` on a paid tier (currently gated by plan access)
- [ ] Expand the SEC EDGAR / ApeWisdom feature set into the segmented ML ensemble as more live history accumulates
- [ ] REST API authentication and multi-user scoping for the FastAPI backend
- [ ] Mobile-responsive React dashboard

---

## License

This project is proprietary software. All rights reserved.

---

*Predicted independently. Verified against real history. Reported honestly — including when the honest number isn't exciting.*
