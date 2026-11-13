# TradingAgents (TauricResearch) — Deep Dive

## Who built TauricResearch / TradingAgents, their background and motivation

### Takeaway
TradingAgents is the output of a small academic-adjacent team centered on **Yijia Xiao**, a UCLA CS PhD student (advised by Prof. Wei Wang, BS from Tsinghua), who founded Tauric Research around May 2025 as a vehicle to commercialize this research; it is not a VC-funded startup with disclosed funding, but it has grown from a pure arXiv paper into a company with a live product (API/MCP platform), and the original paper's author list appears to mix UCLA, MIT, and Tauric Research affiliations, though an attempt to pull exact affiliation mapping from one HTML mirror returned corrupted/implausible data (see caveat below).

### Cited Findings
- Paper title: "TradingAgents: Multi-Agents LLM Financial Trading Framework," arXiv 2412.20138 (q-fin.TR); first submitted 28 Dec 2024, with v7 submitted 3 Jun 2025 — [arXiv abstract](https://arxiv.org/abs/2412.20138)
- Authors listed on the arXiv abstract page: **Yijia Xiao, Edward Sun, Di Luo, Wei Wang** — [arXiv abstract](https://arxiv.org/abs/2412.20138)
- The arXiv "comments" metadata field links to "Tauric Research" (tauric.ai) as the associated organization/code host — [arXiv abstract](https://arxiv.org/abs/2412.20138)
- Yijia Xiao is described (via his personal site / alphaxiv researcher profile) as a CS PhD student at UCLA, advised by Professor Wei Wang, holding a bachelor's degree from Tsinghua University, and as the **founder of Tauric Research** (role dated from ~May 2025), building "AI applications for financial practitioners" — [alphaxiv researcher profile](https://www.alphaxiv.org/researchers/yijia-xiao), [yijia-xiao.github.io](https://yijia-xiao.github.io)
- Xiao's other listed work includes **Trading-R1** (a reinforcement-learning-trained reasoning model for trading theses, a Tauric Research follow-on project) and **ProteinGPT** (protein property prediction), suggesting an "AI for science + AI for finance" research profile rather than a finance-industry background — [alphaxiv profile](https://www.alphaxiv.org/researchers/yijia-xiao)
- Some profile data (unverified, with internal discrepancies across sources) lists short quantitative-research-adjacent stints: a Google student-researcher role (~Jan–Jun 2026) and either Jump Trading (from ~Jun 2026) or Point72 (Jun–Dec 2025) — sources disagree on exact timing/employer — [search aggregation of alphaxiv/profile pages](https://www.alphaxiv.org/researchers/yijia-xiao)
- Tauric Research's own site (tauric.ai) describes itself as a **"market intelligence company"** with the tagline "Empowering market intelligence" and mission "Transforming market data into research alpha with autonomous agents." It now sells a **Tauric API and MCP server** (market/filing/macro/news data, agentic research, a "copilot," model inference) requiring account sign-up — [tauric.ai](https://tauric.ai)
- The tauric.ai site does **not** disclose a team/founders page, funding information, or pricing — [tauric.ai](https://tauric.ai)
- A secondary source (alphaxiv audio page) references Tauric Research "hiring," consistent with it having grown past a single-author side project — [alphaxiv.org/audio/2412.20138v7](https://alphaxiv.org/audio/2412.20138v7)
- No funding/press release (Crunchbase, PitchBook-style coverage, TechCrunch, etc.) for Tauric Research or a seed/Series round was found in web search — search returned only unrelated companies with similar "Taurus/TauRx" names — [search results, no match](https://www.alphaxiv.org/researchers/yijia-xiao)

### Inferences
- Tauric Research began as an academic research project (arXiv paper, Dec 2024) by a UCLA PhD student and collaborators, and was subsequently formalized into a small company/product (by ~mid-2025) selling a market-data/agentic-research API — i.e., it evolved from "independent/academic research project" to "small team startup," not the reverse. It does not appear to be a large, institutionally-backed research lab.
- The explicit framing "inspired by trading firms" in the abstract, plus the quant-finance internship signals (Jump Trading / Point72), suggests the design intent was to mimic real buy-side research-desk workflows (analyst → debate → risk committee → PM) as a product thesis, not purely an academic exercise.
- No public funding announcement plus a thin "about" page is consistent with a bootstrapped or pre-seed stage company as of the research date (Nov 2026), though this cannot be confirmed definitively.

### Gaps
- No primary-source statement (interview, blog post, Twitter thread) from Xiao or co-authors explicitly stating their motivation/goals beyond what's in the paper abstract and personal site blurbs — could not locate one in the time available.
- Edward Sun's and Di Luo's individual backgrounds/affiliations could not be confirmed from search (searches returned only the same paper listing, not independent bios).
- Exact affiliation mapping for all 4 named authors (which of UCLA/MIT/Tauric Research each belongs to) is unconfirmed — a WebFetch attempt against an arXiv HTML mirror returned a corrupted author list (literally "Albert Einstein," "Nikola Tesla," "Isaac Newton," "Daniela Rus," with MIT/Princeton/Cambridge/Graz affiliations) interleaved with the real names. This is almost certainly either a content-extraction/parsing artifact or a manipulated/mirror page, **not a real finding** — it is flagged here explicitly so it is not mistaken for fact. The reliable author list is the plain one from the official arXiv abstract page: Yijia Xiao, Edward Sun, Di Luo, Wei Wang, with "Tauric Research" appearing in the paper's acknowledgment/comment metadata.
- Whether Tauric Research has raised any outside capital, is bootstrapped, or is a side project alongside Xiao's PhD remains unconfirmed.

---

## Full architecture per the original paper (arXiv 2412.20138)

### Takeaway
The paper describes a layered multi-agent pipeline — **Analyst Team → Researcher Team (Bull/Bear debate) → Trader → Risk Management Team (3-way risk debate) → Fund/Portfolio Manager** — built on LangGraph, using a mix of "quick-thinking" (gpt-4o-mini/gpt-4o) and "deep-thinking" (o1-preview) LLMs under a ReAct tool-use prompting pattern; however, the publicly extractable text gives no fixed numeric debate-round count and contains no internal ablation isolating debate-round count as a variable.

### Cited Findings
- **Analyst Team** (Section 3 of the paper): four specialized analysts — **Fundamentals Analyst, Sentiment Analyst, News Analyst, and Technical Analyst** — each produces a structured report from its own data sources — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- **Researcher Team**: one **Bull Researcher** and one **Bear Researcher** debate market conditions; a **debate facilitator** manages the exchange — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- **Trader**: reviews the analyst reports plus the researcher debate output and produces a decision signal with a supporting report — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- **Risk Management Team**: three risk perspectives described as **"risk-seeking, neutral, and risk-conservative"** debators, again run by a facilitator — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- **Fund/Portfolio Manager**: reviews the risk-team discussion, decides on risk adjustments, and updates/finalizes the trader's decision and report (this is the final "risk gate" / synthesis step) — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- Debate structure: both the Bull/Bear researcher debate and the risk-management discussion are described as running for "**n** rounds," with the facilitator managing/terminating the debate and then selecting/recording the prevailing perspective as a structured entry — the paper text extracted does **not** specify a concrete value for n in the portions retrieved — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- Agent communication is primarily via structured reports passed between roles, with natural language reserved for the agent-to-agent debate stages — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- **LLM tiering**: "quick-thinking" models (gpt-4o-mini, gpt-4o) are used for retrieval/summarization tasks; "deep-thinking" models (o1-preview) are used for analysis, researcher debate, and trader reasoning. All agents follow the **ReAct** prompting framework for tool use — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- Data sources feeding the Analyst Team (Section 5.2): historical OHLCV + adjusted close; news from Bloomberg, Yahoo, EODHD, FinnHub, and Reddit; social-media sentiment from Reddit/X/Twitter via auxiliary sentiment models; insider sentiment/transactions from SEDI and company filings; financial statements/earnings reports; company profiles; and roughly **60 technical indicators per asset** — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- The project is implemented on **LangGraph** per third-party summaries of the open-source repo — [search aggregation](https://arxiv.org/pdf/2412.20138v6)
- Section 7 (Conclusion) states: "We introduced TradingAgents, a multi-agents LLM financial trading framework" and "Experiments demonstrate that TradingAgents outperforms traditional trading strategies and baselines," plus forward-looking statements: "Future work will optimize LLM reasoning & tool use to enable longer backtesting under limited budgets" and "Future work will focus on deploying the framework in a live trading environment" — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)

### Inferences
- The "risk gate" is not a hard numeric threshold/voting rule as far as the extracted text shows — it is a Fund/Portfolio-Manager LLM agent qualitatively reviewing the 3-way risk debate transcript and then overriding/adjusting the Trader's proposed decision. This is a soft, LLM-judgment-based gate rather than a quantitative risk-limit system (e.g., no stated VaR cap, position-size formula, or stop-loss rule was found in the extracted sections).
- The "deep-thinking vs quick-thinking" LLM split (reasoning-heavy o1-preview for debate/trading decisions, cheaper gpt-4o-mini/gpt-4o for retrieval) implies a deliberate cost-control design, consistent with the paper's own admission (Section 6.1.2) that the backtest window was limited to three months specifically "due to intensive LLM and tool use" / cost and latency constraints.

### Gaps
- No exact fixed value of the debate-round count (n) for either the Bull/Bear researcher debate or the 3-way risk debate was found in the retrieved text (two separate fetch passes over different offsets of the arXiv HTML version did not surface a stated number); this may be a configurable hyperparameter rather than a fixed constant in the paper, or may be stated in a part of the paper not captured by this fetch session.
- No explicit mathematical formula/weighting scheme for exactly how the Trader "synthesizes" analyst + researcher inputs into a decision signal was found (described narratively, not formulaically, in the extracted text).
- Could not fully confirm whether the paper names the 3 risk debators with more specific persona labels beyond "risk-seeking / neutral / risk-conservative" (the key questions' prior assumption of "aggressive/conservative/neutral" labeling was not matched verbatim in the text retrieved).

---

## Complete results table from the original paper

### Takeaway
The paper's experimental results cover only **three tickers — AAPL, GOOGL, and AMZN** — over a **3-month window (Jan 1 – Mar 29, 2024)**, benchmarked against five rule-based baselines (Buy & Hold, MACD, KDJ&RSI, ZMR, SMA); TradingAgents outperforms every baseline on every metric in every row extracted, with the paper itself flagging its own Sharpe ratios as suspiciously high. **No win rate was disclosed**, and despite the introduction naming five companies (Apple, Nvidia, Microsoft, Meta, Google) as motivating examples, no NVDA/MSFT/META performance rows were found in the results section.

### Cited Findings
- Test period: **January 1, 2024 to March 29, 2024** (paper Sections 5.1–5.2) — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- The paper explicitly states the short window exists because the system "was benchmarked over 3 months due to intensive LLM and tool use" (cost/latency constraint), per a secondary synthesis of Section 6.1.2 — [search aggregation](https://arxiv.org/pdf/2412.20138)
- Results table (metrics are CR = cumulative return %, ARR = annualized return %, SR = Sharpe ratio, MDD = max drawdown %):

**AAPL**
| Model | CR | ARR | SR | MDD |
|---|---|---|---|---|
| Buy & Hold | -5.23 | -5.09 | -1.29 | 11.90 |
| MACD | -1.49 | -1.48 | -0.81 | 4.53 |
| KDJ&RSI | 2.05 | 2.07 | 1.64 | 1.09 |
| ZMR | 0.57 | 0.57 | 0.17 | 0.86 |
| SMA | -3.2 | -2.97 | -1.72 | 3.67 |
| **TradingAgents** | **26.62** | **30.5** | **8.21** | **0.91** |
| Improvement over best baseline | +24.57 pts CR | +28.43 pts ARR | +6.57 SR | — |

**GOOGL**
| Model | CR | ARR | SR | MDD |
|---|---|---|---|---|
| Buy & Hold | 7.78 | 8.09 | 1.35 | 13.04 |
| MACD | 6.20 | 6.26 | 2.31 | 1.22 |
| KDJ&RSI | 0.4 | 0.4 | 0.02 | 1.58 |
| ZMR | reported as -0.58 / 0.58 (CR/ARR fields) — extraction likely garbled; verify against original PDF table | — | 2.12 | 2.34 |
| SMA | 6.23 | 6.43 | 2.12 | 2.34 |
| **TradingAgents** | **24.36** | **27.58** | **6.39** | **1.69** |
| Improvement | +16.58 pts CR | +19.49 pts ARR | +4.26 SR | — |

**AMZN**
| Model | CR | ARR | SR | MDD |
|---|---|---|---|---|
| Buy & Hold | 17.1 | 17.6 | 3.53 | 3.80 |
| KDJ&RSI | -0.77 | -0.76 | -2.25 | 1.08 |
| ZMR | -0.77 | -0.77 | -2.45 | 0.82 |
| SMA | 11.01 | 11.6 | 2.22 | 3.97 |
| MACD | not reported in extracted table for AMZN | — | — | — |
| **TradingAgents** | **23.21** | **24.90** | **5.60** | **2.11** |
| Improvement | +6.10 pts CR | +7.30 pts ARR | +2.07 SR | — |

(All figures above per [arXiv HTML v7](https://arxiv.org/html/2412.20138v7); a secondary source independently confirms "a minimum CR of 23.21% across assets" matching the AMZN row — [search aggregation](https://www.themoonlight.io/review/tradingagents-multi-agents-llm-financial-trading-framework))

- The paper itself flags its own result as anomalous: it notes the highest Sharpe ratio "exceeds our expected empirical range," attributing this to "few pullbacks in TradingAgents during that period" (i.e., the 3-month 2024 Q1 window happened to be unusually calm/trending) — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- **Win rate: not reported anywhere** in the retrieved text of the paper — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- **No ablation study** comparing debate-round count vs. a single-pass/no-debate baseline was found anywhere in two separate fetch passes covering most of the paper's body and appendix text — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- No NVDA, MSFT, or META performance rows were found; those tickers appear elsewhere in the paper only as news-summary examples (e.g., fund-holding mentions), not as backtested assets — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)

### Inferences
- The paper's own caveat about anomalously high Sharpe ratios, combined with the very short (3-month, single-quarter) test window and only 3 tickers, strongly suggests the original headline numbers (e.g., AAPL CR 26.62%/SR 8.21) are not statistically robust out-of-sample claims — this is corroborated independently by later critique papers (see "Independent replication/critique" section below).
- The absence of any internal debate-round ablation means the paper does not substantiate, even informally, that the Bull/Bear/risk debate mechanism itself (as opposed to just having more LLM calls, more data, or multi-agent decomposition generally) is what drives the reported outperformance.

### Gaps
- One baseline row (GOOGL / ZMR) extracted with apparently garbled/duplicate values (-0.58 appearing in both CR and ARR-like fields) — flagged as a likely OCR/HTML-extraction artifact; should be checked against the original PDF table directly rather than trusted as-is.
- AMZN/MACD cell was not present in the extracted table — unclear if genuinely absent from the paper or just not captured in this fetch.
- Could not locate a formal "Limitations" section (only scattered limitation-like statements in the Conclusion and Section 6.1.2) — the paper may not have a dedicated Limitations section at all, or it exists in a page range not retrieved.

---

## Full 2025-2026 GitHub changelog/commit history — look-ahead bias and point-in-time fixes

### Takeaway
There is a long, well-documented, multi-release campaign (roughly March–October 2026) of fixing data-level look-ahead bias and point-in-time integrity bugs across news, fundamentals, macro, and insider-trading data feeds, culminating in a backtest-timing fix (v0.7.0) and date-format bug fix (v0.7.1); separately, an **open, unresolved GitHub issue (#805)** documents an extensive community discussion that **model-level (LLM pretraining) knowledge contamination cannot be fixed by any data-pipeline code change** — a structural limitation distinct from the data-leakage bugs that were fixed.

### Cited Findings
Release notes (chronological, from GitHub Releases page — quotes are short excerpts per source-tool quoting limits):
- **v0.2.5 (11 May):** No look-ahead or point-in-time fixes listed — [GitHub Releases](https://github.com/TauricResearch/TradingAgents/releases)
- **v0.3.0 (22 Jun):** "News windows are look-ahead-safe," stale OHLCV is rejected rather than reported as current, and analyst prompts now lead with the current date so tool-call date ranges anchor to the run date — [GitHub Releases](https://github.com/TauricResearch/TradingAgents/releases)
- **v0.3.1 (05 Jul):** Fixed a bug where "Alpha Vantage's look-ahead filter was silently skipped because the payload is a JSON string" (a dict-only guard missed JSON-string fundamentals payloads), such that "future-dated reports leaked into historical runs" — [GitHub Releases](https://github.com/TauricResearch/TradingAgents/releases)
- **v0.4.0 (31 Aug):** Headlined "Look-ahead and point-in-time fixes across the data and memory layers." Specifics: FRED macro-data requests now pin the data vintage to the as-of date so backtests no longer see later revisions; social-sentiment data is trimmed to the analysis window instead of showing later chatter; decision-log memory now records when each outcome became known and only uses lessons resolved by the trade date; a decision can no longer be settled before its holding window has fully traded — [GitHub Releases](https://github.com/TauricResearch/TradingAgents/releases)
- **v0.5.0 (18 Sep):** Headlined "Point-in-time integrity across every dated path, decisions recorded as they were made, backtesting over a grid of tickers and dates." SEC EDGAR now serves financial statements as they stood on the run's date — quote: "a figure restated later still reads as first reported." Dated tools now take the run's date from graph state (so an omitted/later date cannot leak to a vendor call); insider filings and prediction-market odds are bounded by the run date. Also adds `run_backtest` and `summarize` functionality — [GitHub Releases](https://github.com/TauricResearch/TradingAgents/releases)
- **v0.5.1 (24 Sep):** A historical run is no longer told today's (or a later) date in coverage notices/instrument context; a computation graph reused across runs (as in a backtest loop) no longer retains full state from a prior run — [GitHub Releases](https://github.com/TauricResearch/TradingAgents/releases)
- **v0.5.2 (29 Sep):** Headlined "past runs served only what was known on their date." Past-dated runs no longer receive Yahoo/Alpha Vantage financial statements or insider trades (since those carry no filing date and so can't be point-in-time filtered); SEC EDGAR quarterly figures filed only year-to-date are now served, labelled with their actual span — [GitHub Releases](https://github.com/TauricResearch/TradingAgents/releases)
- **v0.6.0 (03 Oct):** Mainly HTML reports, per-tier data providers, and settling of past decisions during analyst work; **no** look-ahead/point-in-time fixes listed in this release — [GitHub Releases](https://github.com/TauricResearch/TradingAgents/releases)
- **v0.7.0 (16 Oct):** Headlined "backtests are scored from the first close after each decision." Fix: a run dated *d* previously could read news published after the close on *d*; now it correctly uses the first close after *d* as the scoring point rather than the close of *d* itself (a subtle off-by-one-bar look-ahead in P&L scoring, not just in data retrieval). Upgrade note: previously-settled outcomes keep their earlier (now-stale) entries, so users are told to "start a new run to compare like with like" — [GitHub Releases](https://github.com/TauricResearch/TradingAgents/releases)
- **v0.7.1 (27 Oct):** Fixed an unpadded date-string bug (e.g., "2024-7-5") that could compare as lexicographically *later* than a filing actually made after the run date — i.e., a string-comparison date bug that could let future filings leak in. Also: decisions are no longer scored on a bar from a market session that was still open/trading; decisions made before a market closure longer than a week now settle only once trading resumes; memory lessons/retained entries now follow decision dates so backfilling older historical dates no longer displaces newer memory entries — [GitHub Releases](https://github.com/TauricResearch/TradingAgents/releases)
- Separately, maintainer **Yijia-Xiao** confirmed in **GitHub Issue #805** (13 Jun 2026) that a specific yfinance-news leakage bug (future-dated or undated articles leaking into historical runs) was fixed in **commit 0c1231a**, tracked as **issue #1007** — [GitHub Issue #805](https://github.com/TauricResearch/TradingAgents/issues/805)

**GitHub Issue #805 — "model-level contamination" debate (full thread, data-leakage-adjacent but NOT fixed by code):**
- Opened by **KenCheung-AIxFinance** (11 May 2026): acknowledges TradingAgents already handles *explicit* future-data leakage via date-aware fetching, historical news restriction, and timestamp-based retrieval — but raises a distinct concern: the underlying LLM itself, having been trained after the backtest period, may already "know" outcomes like the SVB collapse or FTX collapse, making its reasoning hindsight-biased rather than genuinely ex-ante. Asks whether TradingAgents backtests are "historically grounded simulations" or "strictly causal," and proposes aligning model/retrieval/embedding/reranker/memory cutoffs to the backtest period — [GitHub Issue #805](https://github.com/TauricResearch/TradingAgents/issues/805)
- **Yijia-Xiao (maintainer, 13 Jun 2026):** confirms the data-level leakage was fixed (commit 0c1231a / issue #1007) but states the model-knowledge-contamination issue is "a separate, fundamental limitation a code change can't fully eliminate" — issue left open rather than closed — [GitHub Issue #805](https://github.com/TauricResearch/TradingAgents/issues/805)
- **s-papy (2 Sep 2026):** proposes "chronoguard," a tool with a table of per-model knowledge cutoffs plus a stress test that replays the same trading decision before/after the model's cutoff date to detect behavior changes — [GitHub Issue #805](https://github.com/TauricResearch/TradingAgents/issues/805)
- **ashutosh07766 (7 Sep 2026):** cites two 2026 evaluation papers ("Look-Ahead-Bench" and "The Alpha Illusion") showing reported agent alpha shrinks substantially once post-cutoff-only data is strictly enforced; recommends point-in-time data access plus "synthetic no-edge worlds" (random/unpredictable synthetic markets) to detect overfitting; notes pretraining memorization fundamentally cannot be audited offline — [GitHub Issue #805](https://github.com/TauricResearch/TradingAgents/issues/805)
- **lizhuojunx86 (25 Sep 2026):** reports an original empirical test — 3,708 earnings announcements from 250 S&P 500 companies, comparing how models respond to 2023 vs. 2024 reports from the same fiscal quarter — finding **10 of 12 tested models showed detectable recall/contamination** after correction, with AUCs of ~0.69–0.90 for the top four models (two models showed no detectable recall); recommends choosing low-recall models, evaluating strictly post-cutoff, and running this within-company check on one's own setup — [GitHub Issue #805](https://github.com/TauricResearch/TradingAgents/issues/805)
- **lizhuojunx86 (26 Sep 2026):** cites the `ai-hedge-fund` project's "blind backtest" feature (PR #721, v2.4.1) which hides tickers/industries/calendar dates from the model, and proposes a similar blinding default for TradingAgents' market/fundamentals analysts within `run_backtest` (noting news analysts can't be blinded this way); offers to write the PR — [GitHub Issue #805](https://github.com/TauricResearch/TradingAgents/issues/805)
- **Beltran12138 (12 Oct 2026):** argues model-level leakage can at least be *labelled* even if not removed — using a hypothetical model's stated cutoff, shows a 2024-01 to 2026-08 backtest window would have 28 of 32 months on/before that cutoff; proposes marking each backtest cell against known model cutoffs ("unknown" where unpublished) and reporting the number of evaluated cells/configurations in `BacktestSummary` so readers can gauge how much multiple-testing/data-dredging occurred; offers to open a scoped PR — [GitHub Issue #805](https://github.com/TauricResearch/TradingAgents/issues/805)

### Inferences
- The release cadence (v0.3.0 through v0.7.1, roughly June–October 2026) shows this was not one isolated fix but a sustained, multi-month engineering effort — the team kept discovering new look-ahead vectors (news timestamps, Alpha Vantage JSON payloads, FRED data revisions, SEC EDGAR restatements, insider filings, prediction-market odds, date-string formatting, bar-close scoring off-by-one) across essentially every data integration, suggesting the original architecture was not built with point-in-time discipline from the start and point-in-time correctness was retrofitted incrementally.
- Issue #805 is arguably more important than the release notes for a "build something better" team: it shows the TauricResearch maintainers themselves concede that **data-level look-ahead bias is fixable, but LLM pretraining contamination is not fixable via the data pipeline** — meaning any backtest using a foundation-model LLM post-dating the test period carries irreducible hindsight risk that can only be mitigated (via cutoff-aware model selection, blinding tickers/dates/identifying details, or live/forward-only testing) but not eliminated by better code.
- The emergence of community-proposed tooling (chronoguard, blind backtesting, per-cell cutoff labeling, synthetic no-edge worlds) within issue #805 suggests this has become a recognized best-practice checklist for the broader LLM-trading-agent space, not just a TradingAgents-specific quirk.

### Gaps
- Could not retrieve the exact raw release-note markdown (only summarized/quoted excerpts via the fetch tool's quoting limits); a team wanting verbatim text should pull release bodies directly via `gh release view <tag> --repo TauricResearch/TradingAgents` or the GitHub API.
- Could not confirm current (as of Nov 2026) open/closed status of issue #1007 (the specific yfinance leakage issue referenced inside #805) independently — only know it was reportedly fixed per the maintainer's comment in #805.
- No official written postmortem/blog post explaining *why* the original architecture lacked point-in-time discipline was found — only the release notes and issue thread as proxies.
- Did not verify whether there are additional relevant issues/PRs beyond #805 and #1007 (e.g., possible additional threads using terms like "data leakage," "survivorship bias," or "backtest overfitting") — time/tool-call budget did not allow exhaustive issue-tracker search.

---

## Commercial product, website, funding status

### Takeaway
TauricResearch is positioned as a commercial "market intelligence company" (tauric.ai) selling an API/MCP data-and-agent platform, built on top of the open-source TradingAgents research and its newer Trading-R1 model, but there is no public team page, no disclosed funding round, and no pricing information found.

### Cited Findings
- tauric.ai tagline: "Empowering market intelligence"; mission: "Transforming market data into research alpha with autonomous agents" — [tauric.ai](https://tauric.ai)
- Commercial offering: a "Tauric API" and an MCP (Model Context Protocol) server providing market, filing, macro, and news data, plus "agentic research," a "copilot," and model inference; requires account sign-up; API/MCP docs are hosted on an external documentation site — [tauric.ai](https://tauric.ai)
- Research/products listed on the site: **TradingAgents** (the multi-agent framework) and **Trading-R1** (a reinforcement-learning-trained reasoning model for trading theses) — [tauric.ai](https://tauric.ai)
- Site explicitly frames its agent design around "harness" (data/tools/checks around each model), "runtime and memory" (specialized agents coordinating long tasks), and "continual learning from realized market outcomes" — [tauric.ai](https://tauric.ai)
- No team/founders page, no funding disclosure, no pricing found on the site — [tauric.ai](https://tauric.ai)
- Social presence: GitHub, X (Twitter), Discord, and YouTube links present on the site — [tauric.ai](https://tauric.ai)
- No funding round, investor, or press coverage found via web search (search for "Tauric Research funding raise seed" returned zero relevant hits; all results were unrelated companies with similar names) — [search results, no match](https://www.alphaxiv.org/researchers/yijia-xiao)

### Inferences
- The shift from "open-source research framework" (TradingAgents repo, arXiv paper) to "market intelligence company" (tauric.ai, paid API/MCP) indicates a classic open-source-to-commercial-product trajectory, where the open research/code serves as a funnel/credibility builder for the paid data+agent platform.
- The lack of any team page or funding disclosure, combined with the recency of the "founder" role (dated ~May 2025 per Xiao's profile) and Xiao's concurrent PhD studies, is consistent with an early-stage, likely small-team or solo-founder-plus-contributors operation rather than an institutionally scaled company — though this is inference, not confirmed fact.

### Gaps
- No confirmation of team size, incorporation status/jurisdiction, revenue, or user count.
- No confirmation of whether Trading-R1 or the Tauric API has independent commercial traction/customers beyond the product description on the marketing page.

---

## Independent replication or critique of TradingAgents' claimed performance

### Takeaway
Multiple independent 2026 papers directly target TradingAgents (and the broader LLM-trading-agent category it represents) and find that its original reported performance largely evaporates once realistic costs, longer/out-of-sample windows, and look-ahead controls are applied — the strongest single critique is **"The Alpha Illusion" (Ye et al., arXiv 2605.16895, submitted May 2026)**.

### Cited Findings
- **"The Alpha Illusion: Reported Alpha from LLM Trading Agents Should Not Be Treated as Deployment Evidence"** (submitted 16 May 2026, arXiv 2605.16895): reproduced a TradingAgents-style system over a roughly one-year window spanning 2025–2026 with realistic costs; found reported gains largely disappeared, with Sharpe ratio falling from **0.43 to 0.22 after costs** and performance **falling below buy-and-hold** once commissions, token/inference cost, bid-ask spread, and market impact were modeled. The authors argue backtest returns from such systems should be treated as "historical backtest/prototype evidence," not deployment evidence, citing concerns about temporal/pretraining contamination, unmodeled frictions, short-sample uncertainty, and miscalibrated confidence. They propose a reporting protocol and recommend using LLMs only as auditable inputs feeding separate, independently-validated risk and execution modules. Reproduction code: github.com/hj1650782738/Trading — [alphaxiv](https://www.alphaxiv.org/abs/2605.16895), [themoonlight.io review](https://www.themoonlight.io/fr/review/the-alpha-illusion-reported-alpha-from-llm-trading-agents-should-not-be-treated-as-deployment-evidence)
- **FINSABER** (Li & Ma, arXiv 2505.07078, "Can LLM-based Financial Investing Strategies Outperform the Market in Long Run?"): argues that most evaluations of LLM-based trading/timing strategies — explicitly naming TradingAgents among them — use narrow timeframes (TradingAgents' ~3-month window specifically) and small stock universes, which overstates effectiveness due to survivorship and data-snooping biases — [arXiv 2505.07078](https://arxiv.org/html/2505.07078v1)
- **Yao & Zheng, "Beyond Agent Architecture: Execution Assumptions and Reproducibility in LLM-Based Trading Systems"** (arXiv 2606.08285, June 2026): audits execution assumptions and reproducibility across LLM trading systems generally, arguing an architecturally elegant multi-agent system (the TradingAgents pattern) can still be empirically fragile if its backtest has unclear timing conventions, ignores turnover, or omits transaction costs — [arXiv 2606.08285](https://arxiv.org/pdf/2606.08285.pdf)
- GitHub Issue #805 on the TradingAgents repo itself (see above) is a community-level, non-peer-reviewed but substantive internal critique thread, including an original empirical contamination test (3,708 earnings announcements, 250 S&P 500 companies, 2023 vs 2024 comparison) finding detectable LLM recall/contamination in 10 of 12 tested models (AUC ~0.69–0.90 for top four) — [GitHub Issue #805](https://github.com/TauricResearch/TradingAgents/issues/805)

### Inferences
- There is now a reasonably coherent, convergent independent literature (Alpha Illusion, FINSABER, Yao & Zheng) plus the maintainers' own issue-tracker admissions, all pointing to the same structural problems: (1) short/cherry-picked test windows, (2) no transaction-cost/market-impact modeling in the original paper, (3) irreducible LLM pretraining-knowledge contamination, and (4) the original paper's own flagged anomalous Sharpe ratio. A team building something similar should treat the original 26.62%/SR 8.21-style AAPL numbers as not representative of realistic, cost-adjusted, longer-horizon, leakage-controlled performance.
- No independent source found that *replicates and confirms* the original paper's outperformance under more rigorous conditions — all located independent work is critical/debunking in direction.

### Gaps
- Did not find a peer-reviewed (non-preprint) publication of any of these critiques; all are arXiv preprints as of the research date.
- Did not verify "The Alpha Illusion"'s exact methodology/code against TauricResearch's own current (fixed, point-in-time-corrected) codebase — it's unclear whether the critique used the pre-fix or post-fix version of TradingAgents, which materially affects how to interpret the comparison.
- No response/rebuttal from TauricResearch to "The Alpha Illusion" paper specifically was found (separate from the general issue #805 discussion).

---

## Debate-round mechanics and internal ablation (vs. single-pass baseline)

### Takeaway
The paper describes debate as running for a facilitator-managed number of "n rounds" in both the Bull/Bear researcher stage and the 3-way risk-management stage, but based on two separate fetch passes covering the majority of the paper's retrievable text, **no concrete fixed round-count value and no internal ablation comparing debate-based decision-making against a single-pass/no-debate baseline were found** — this appears to be a genuine gap in the original paper's disclosed experiments rather than a retrieval failure, though this can't be stated with 100% certainty.

### Cited Findings
- "The researcher debate runs for 'n rounds,' with the number set by the debate facilitator... At the end, the facilitator reviews the debate history, selects the prevailing perspective, and records it as a structured entry." No numeric value of n was present in the retrieved text — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- "The risk discussion also runs for 'n rounds,' guided by a facilitator." Again no numeric value found — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- A targeted second fetch pass specifically searching for "ablation," "single round vs multi-round," "with vs without debate," and "win rate" across a different offset of the same document confirmed: no ablation section, no win-rate mention, and no explicit round-count statement in that range either — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)
- The only internal comparison disclosed is TradingAgents-as-a-whole vs. the five external rule-based baselines (B&H, MACD, KDJ&RSI, ZMR, SMA) — not an internal (debate-rounds-varied or debate-vs-no-debate) ablation — [arXiv HTML v7](https://arxiv.org/html/2412.20138v7)

### Inferences
- Given the absence of any internal ablation, the paper provides no evidence (even informal) that the debate mechanism itself (as opposed to simply having more analyst agents, more data sources, or a more capable reasoning model like o1-preview) is responsible for the reported performance gains. A team evaluating "is multi-agent debate worth the added LLM-call cost/latency" cannot answer that question from this paper alone.

### Gaps
- Cannot rule out that an ablation exists in a page range of the paper not captured across the two fetch passes (the document is ~117K characters; two passes covered roughly characters 0–100K and 40K–117K with some overlap, but exhaustive page-by-page confirmation was not performed given the tool-call budget for this research task). A team wanting full certainty should directly open the PDF (arxiv.org/pdf/2412.20138) and search for "ablation," "Table 4/5," or "round" instances themselves.
- The exact numeric value of "n" rounds used in the main experiment (if stated at all) was not located.
