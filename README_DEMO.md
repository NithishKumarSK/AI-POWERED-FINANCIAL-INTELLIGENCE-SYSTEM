# AI Financial Analyst System — Demo Guide

## CORRECT command (Ajay / Sujith demo)

```
streamlit run stock_prediction_app.py
```

## WRONG command (legacy options backtest — DO NOT use for demo)

```
streamlit run streamlit_app.py
```

`streamlit_app.py` is the old options strategy backtest app and shows the WRONG flow
(DTE, delta, legs, tastytrade backtest over 6+ months). It now displays a visible warning
banner at the top. Do not use it to demo one-month stock prediction.

---

## What the correct app shows

**AI Financial Analyst System — One-Month Stock Prediction Validation**

The system answers:
> *What did AI predict for the next 30 days? What actually happened? How far was AI from actual?*

### Two-window architecture

```
[Historical Context Window]          [Prediction / Validation Window]
  ctx_start  →  origin_date    |    origin_date  →  target_date
  ──────────────────────────── | ──────────────────────────────────
  AI receives ONLY these bars  |  AI predicts this window.
  (leakage-free)               |  Actual validation reveals real
                               |  price at target_date AFTER AI runs.
```

### Exact formula (example: TSLA)

```
origin_date  = 2026-03-01   origin_price  = $402.00
target_date  = 2026-03-31   target_price  = $371.00
initial_capital = $50,000

actual_return_pct    = (371 - 402) / 402 × 100 = -7.71%
actual_final_capital = 50,000 × (371 / 402)    = $46,144.28
```

AI's predicted_target_price is compared to the actual $371. The difference is the error.

---

## Data flow (no options, no tastytrade)

1. **User inputs**: symbol, context start date, prediction origin date, horizon days, capital
2. **Historical price fetch** — RapidAPI TradingView daily bars (no yfinance)
3. **Filter** — AI receives only bars ≤ prediction_origin_date (leakage prevention)
4. **AI prediction** — momentum-based model with Gemini explanation text
5. **Actual validation** — fetch real price on target_date AFTER AI has predicted
6. **Comparison** — decision match, return error pp, capital error $, capital error %
7. **JSONL record** — saved to `stock_prediction_evaluation_runs.jsonl`

---

## File map

| File | Purpose |
|------|---------|
| `stock_prediction_app.py` | **Correct demo app** — run this |
| `stock_prediction_agent.py` | AI prediction engine (momentum + Gemini) |
| `stock_walkforward_validator.py` | Actual validation against real historical prices |
| `historical_price_service.py` | RapidAPI TradingView price fetcher (no yfinance) |
| `stock_accuracy_engine.py` | JSONL save/load and accuracy summary |
| `stock_prediction_evaluation_runs.jsonl` | Valid accuracy records |
| `stock_prediction_evaluation_runs_invalid.jsonl` | Rejected records (audit trail) |
| `streamlit_app.py` | LEGACY options app — shows warning, do not use for demo |
| `ajay_backtest_audit_demo.py` | Temporary options audit demo — delete after review |

---

## Environment variables required

```
RAPIDAPI_KEY=<your RapidAPI key>
GEMINI_API_KEY=<your Gemini API key>
```

RapidAPI host must remain `trading-view.p.rapidapi.com`. Do not change it.

---

## Rolling monthly validation (sidebar)

The sidebar allows multi-month back-testing:
- Select a symbol, context start date, and number of past months
- Each month is validated independently: AI predicts using only pre-month data, actual outcome is checked
- All valid records are saved to the JSONL accuracy log
