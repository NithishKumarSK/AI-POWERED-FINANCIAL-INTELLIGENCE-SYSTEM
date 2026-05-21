# MASTER PROMPT — AI FINANCIAL ANALYST SYSTEM (Institutional, Evaluation‑First)

You are building **AI FINANCIAL ANALYST SYSTEM**: an **institutional‑grade financial intelligence infrastructure**.

This is **NOT**:
- a chatbot
- a stock report generator
- an essay‑writing LLM wrapper
- a generic Streamlit dashboard
- a student AI project

This system must feel like:
- Bloomberg‑lite / research terminal UX
- hedge‑fund/institutional research tooling
- evaluation‑first investment intelligence infrastructure
- auditable, measurable decision system

## 0) Naming (Hard Rule)
- Do **not** use “Xeltrix” anywhere (UI, code, docs, comments).
- Product name: **AI Financial Analyst System**.

---

## 1) Non‑Negotiable Execution Rules (Hard Rules)

1) **No walls of text.**
- Never output giant paragraphs in UI or agent output.
- Default format: cards/tables + compact bullets (max 2–3 bullets per section).

2) **No hallucinations, no inference of missing data.**
- If any tool/source is missing/unavailable: explicitly mark `unavailable`.
- Never guess, infer, or fabricate bullish/bearish reasons.

3) **Data → Normalization → Scoring → Signals → (Constrained) Agents → Decision Trace → Evaluation.**
- LLMs/agents are secondary. The center is **data + evaluation**.

4) **UI must never consume raw tool payloads.**
- UI can only render **normalized internal schemas** (defined below).

5) **Minimal, modular, fast.**
- Avoid fake enterprise bloat: no 100 helper files, no dead abstractions.
- Add structure only when it improves measurability, evaluation rigor, or maintainability.

---

## 2) Normalization Contracts (Required)

Define normalized schemas (dataclasses / TypedDicts / Pydantic models) with:
- explicit types
- null handling
- validation rules
- timestamp lineage (`as_of`, `source_timestamp`)
- source reliability metadata

Required normalized schemas:
- `NormalizedStockData`
- `NormalizedTechnicalData`
- `NormalizedFundamentalData`
- `NormalizedMacroData`
- `NormalizedSentimentData`
- `NormalizedSourceMeta`

`NormalizedSourceMeta` MUST include:
- `source_name`
- `as_of`
- `latency_ms` (if measurable)
- `completeness` (0–1)
- `reliability` (0–1)
- `status` (SUCCESS/UNAVAILABLE/ERROR)

---

## 3) Scoring Engine (Required, Decomposable)

All scores are **0–100**, computed algorithmically from normalized data.

### 3.1 Decomposition (Required)
Scores must be decomposable into subfactor contributions.

Instead of only:
- `fundamental_score()`

You must also have sub‑scores:
- `profitability_score()`
- `growth_score()`
- `balance_sheet_score()`
- `cashflow_score()`
- `valuation_score()` (standalone)
- `technical_score()` (standalone)
- `risk_score()` (standalone)
- `macro_score()` (standalone)
- `sentiment_score()` (standalone)

Then:
- `fundamental_score = weighted_sum(profitability, growth, balance_sheet, cashflow)`

### 3.2 Feature Attribution (Required)
Every engine must output:
- `score: int (0–100)`
- `signal: "Bullish"|"Neutral"|"Bearish"|"Unavailable"`
- `contributions: [{factor, delta}]` where deltas roughly sum to the final score movement
- `missing_inputs: [...]`

Example contribution table:
| Factor | Contribution |
|---|---:|
| Revenue growth | +12 |
| P/E overvaluation | -18 |
| Momentum | +7 |
| High beta | -5 |

---

## 4) Source Reliability + Confidence (Required)

### 4.1 Source Reliability System (Required)
Treat sources differently. Compute:
- `source_completeness`
- `source_reliability`
- `source_staleness_penalty`
- `engine_availability`

### 4.2 Confidence Engine (Must be Algorithmic)
**No arbitrary confidence numbers.**
Confidence must be computed from:
- data completeness (weight ~25%)
- historical calibration (weight ~25%)
- signal agreement (weight ~20%)
- volatility regime (weight ~15%)
- missing engines penalty (weight ~10%)
- contradiction penalty (weight ~5%)

Confidence output:
- `confidence_score: 0–100`
- `confidence_penalties: [...]` (explicit)

---

## 5) Agents (Constrained Reasoning Modules, Not Essays)

Mandatory agents:
- Bull Agent
- Bear Agent
- Risk Agent
- Critic Agent
- Final Decision Agent

### 5.1 Allowed Inputs (Hard Rule)
Agents may only consume:
- normalized scores
- validated signals
- feature contributions
- risk flags
- missing fields
- source reliability summary
- confidence penalties

Agents must **not** read raw API payloads.

### 5.2 Strict Output Schema (Hard Rule)
Each agent returns:
```json
{
  "agent": "bull|bear|risk|critic|final",
  "status": "SUCCESS|PARTIAL|UNAVAILABLE",
  "verdict": "BUY|HOLD|SELL|NO_CALL",
  "confidence": 0,
  "thesis_bullets": ["...", "..."],
  "key_signals": [{"name":"...", "value":"...", "direction":"up|down|flat"}],
  "risk_flags": ["..."],
  "missing_data": ["..."],
  "disallowed_inferences": ["..."],
  "evidence": [{"source":"engine_name", "field":"field_name"}]
}
```
Rules:
- `thesis_bullets` max 3
- If `missing_data` contains a field, agent must not cite it as evidence.

---

## 6) Decision Accountability (Decision Trace) — Required

Every recommendation must produce an auditable `decision_trace`:
```json
{
  "top_positive_factors": [{"factor":"...", "weight":0}],
  "top_negative_factors": [{"factor":"...", "weight":0}],
  "critical_missing_inputs": ["..."],
  "confidence_penalties": ["..."],
  "risk_overrides": ["..."],
  "final_rule_path": ["..."]
}
```

This trace must be rendered in UI.

---

## 7) Evaluation‑First Core (Most Important)

### 7.1 Leakage Prevention Rules (Hard Rule)
Backtests must enforce:
- `historical_cutoff_timestamp` (as‑of date `T`)
- **news before cutoff only**
- **analyst data before cutoff only**
- technical indicators computed only using data up to cutoff
- no “current price” leakage for past runs

### 7.2 Historical Evaluation Engine (Required)
Support:
- cutoff testing
- prediction vs actual comparison
- win rate tracking
- calibration tracking
- sharpe ratio tracking (where applicable)
- reproducible evaluation reports

### 7.3 Experiment Tracking (Required “Wow” Differentiator)
Every run must persist:
- `experiment_id`
- `model_version`
- `prompt_version`
- `scoring_weights_version`
- `agent_config_version`
- `data_sources_version`
- evaluation metrics

Enable comparisons:
| Experiment | Win Rate | Calibration |
|---|---:|---|
| v1 | 58% | weak |
| v2 | 64% | improved |

---

## 8) Institutional UI Requirements (Stripe/Linear/Bloomberg‑lite)

### 8.1 Visual Hierarchy (Required)
Tier 1 (Decision):
- BUY/HOLD/SELL
- confidence
- risk

Tier 2 (Core intelligence):
- 0–100 scores + signals
- key contributions
- missing inputs

Tier 3 (Supporting evidence):
- news/macro/technicals summaries **only if available**

Tier 4 (Raw evidence + diagnostics):
- expandable traces
- pipeline monitor
- tool statuses

### 8.2 “AI Pipeline Monitor” (Required)
Use institutional engine names:
- Market Intelligence Engine
- Technical Intelligence Engine
- Macro Intelligence Engine
- Risk Intelligence Engine
- Sentiment Intelligence Engine
- Agentic Decision Engine
- Evaluation Engine

Never show raw “FAILED”; show “Temporarily unavailable” + what was skipped.

---

## 9) Definition of Done (Per Phase)

Phase 1 (Scoring foundation + UI cleanup) DONE when:
- UI shows real computed 0–100 scores (no placeholders)
- contributions + missing inputs displayed
- no text walls

Phase 2 (Agentic decomposition) DONE when:
- final decision is composed from Bull/Bear/Risk/Critic outputs
- each agent obeys schema + constraints

Phase 3 (Evaluation core) DONE when:
- a 10‑ticker backtest run is reproducible
- results stored with experiment metadata
- evaluation dashboard shows win rate + calibration

---

## 10) Single Guiding Question (Hard Filter)
For every component ask:
> “Would this impress a hedge‑fund engineer or AI infrastructure lead?”

If not, redesign it.

