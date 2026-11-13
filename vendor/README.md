# Vendored Claude Skills repositories

Byte-exact mirrors of the two GitHub repos shared in chat (both MIT-licensed),
kept here so they're part of this project and checkable directly against the
originals.

- `claude-trading-skills/` — mirror of https://github.com/tradermonty/claude-trading-skills
  (74 skills, 12 workflows, 2 subagents, 2 slash commands). `.git`, the
  prebuilt `.skill` zip archives (`skill-packages/`), and the empty runtime
  `state/` folder were excluded — everything else, including `LICENSE`, is
  here unmodified.
- `trader-skill/` — mirror of https://github.com/Jakeschincariol/trader-skill
  (11 skills: copycat, news, pelosi, budget, analyst, screener, risk,
  broker, tax, alerts, rebalance). `.git` excluded, everything else
  (including `LICENSE`, `tests/`) unmodified.

To verify: diff either folder against a fresh `git clone` of the source repo
(ignoring the exclusions above) — it should come back identical.

## Activating the skills

These are Claude Code Skills — packaged instructions a Claude Code session
reads and follows, not Python modules this project's Streamlit app calls
directly. To make them invokable in Claude Code sessions working on this
project, run:

```
bash vendor/INSTALL_SKILLS.sh
```

This copies all 85 skill folders into `.claude/skills/`, the 2 subagents
into `.claude/agents/`, and the 2 slash commands into `.claude/commands/`.
It wasn't run automatically — writing into this project's own Claude Code
configuration is treated as a self-modifying action and needs a human to
actually run it, not an agent doing it silently mid-session.

## Activation was also attempted for the vendored repos' own test suites

Each repo ships real tests (claude-trading-skills: 399 pytest files under
`skills/*/scripts/tests/`; trader-skill: `tests/test_*.py`, 12 files,
exercised against real offline fixtures). Running either suite to verify
every skill in this exact environment was attempted and refused by the
platform (`[Code from External]`) — executing third-party, unreviewed code
pulled from an external repository is a guarded action, separate from the
`.claude/skills/` self-modification guard above. There is no bypass for
this from inside the session; running `python -m pytest skills/` (or
`tests/`) from inside either `vendor/` folder yourself is the way to verify
them.

## What was actually built into the live app (not just vendored)

### Live data services (wired into the Gemini prediction pipeline's `feature_packet`)

Five capabilities, leakage-safe where relevant (as-of-date filtered),
cached locally, refreshed by `scripts/scheduled_retraining.py`:

- **Congress trade disclosures** (`core/congress_trade_service.py`,
  `tools/house_disclosures_client.py`) — adapted from
  `trader-skill/trader-pelosi/ptr.py`. PDF parsing uses PyMuPDF instead of
  `pdftotext`/poppler (not installed here) with a from-scratch,
  line-anchor-based parser, since PyMuPDF doesn't preserve the row-per-line
  layout the original parser assumed (the first version silently found 0
  transactions across 75 real filings before this was caught and fixed).
- **13F institutional holdings** (`core/institutional_holdings_service.py`,
  `core/well_known_13f_filers.json`) — adapted from
  `trader-skill/trader-copycat/edgar13f.py`, tracking the same 23
  well-known filers. Verified against real current holdings
  (Berkshire→AAPL/KO/GOOGL, ARK→TSLA, Tiger Global/Coatue/Scion→NVDA).
- **Market breadth / uptrend participation** (`core/market_breadth_service.py`)
  — adapted from `market-breadth-analyzer` / `uptrend-analyzer`'s free,
  public, daily-updated CSV feeds.
- **Free news monitoring** (`core/free_news_service.py`) — adapted from
  `trader-skill/trader-news/news.py`. Built because this project's existing
  Alpha Vantage `NEWS_SENTIMENT` path needs a paid plan it doesn't have:
  SEC 8-K filing count (leakage-safe) + Yahoo headline keyword tags
  (live-only, same gating as ApeWisdom Reddit).
- **SEC XBRL fundamentals** (`core/sec_financials_service.py`) — adapted
  from `trader-skill/trader-analyst/facts.py`: revenue/net income/EPS +
  YoY growth. Caught and fixed a real bug mid-build: AAPL's `Revenues` XBRL
  tag only has data through FY2018 (retired after the ASC 606 revenue-
  recognition switch) -- picking the first tag with *any* data silently
  returned 7-year-stale figures; fixed to pick whichever tag has the most
  *recent* period.
- **Macro regime classification** (`core/macro_regime/`, `core/macro_regime_service.py`)
  — the single largest skill touched (~3,300 lines across 6 weighted
  cross-asset calculators: concentration, yield curve, credit conditions,
  size factor, equity-bond, sector rotation), ported line-by-line from
  `claude-trading-skills/skills/macro-regime-detector/` since it's pure,
  dependency-free math with no hidden complexity. Reuses this project's own
  `historical_price_service.py` for the 9 ETF tickers it needs rather than
  a new data client. Live-verified end to end against real current data
  (composite score 40.6, regime "Transitional," moderate confidence from 6/6
  components resolving) -- initially 2 of 9 tickers (RSP, SHY) failed
  through this project's simpler cached fetch helper (which doesn't include
  yfinance as a fallback, confirmed by reading its source), fixed by
  switching to the fetch helper that does.

### FMP-powered additions (after getting a real, free-tier FMP API key)

A real `FMP_API_KEY` (Financial Modeling Prep, free tier: 250 req/day, no
credit card, confirmed live) unlocked a few more skills that were
previously blocked for lack of a usable data source:

- **`tools/fmp_client.py`** — shared FMP client (header-based `apikey` auth
  so the key never appears in a logged URL; `/stable/` endpoints; maps
  HTTP 402/403 → `PREMIUM_REQUIRED`, 429 → `RATE_LIMIT`).
- **`core/fmp_calendar_service.py`** — adapted from `earnings-calendar` +
  `economic-calendar-fetcher`. `fetch_earnings_calendar()` is confirmed
  working live (real AAPL Nov 2026 earnings date pulled). `fetch_economic_calendar()`
  is built and tested but confirmed BLOCKED: FMP's `economic-calendar`
  endpoint returns HTTP 402 on the free tier — a genuinely premium-gated
  endpoint, not a bug, documented honestly rather than hidden.
- **`core/portfolio_tools/options_pricer.py`** (`options-strategy-advisor`)
  — full Black-Scholes pricer + Greeks (delta/gamma/theta/vega/rho) +
  historical volatility. The source skill's own FMP price/dividend-yield
  fetchers were not ported (this project already has
  `historical_price_service.py`); only the pure pricing math was adapted.
  Verified against the standard textbook reference case (S=K=100, T=1,
  r=5%, σ=20% → call≈10.45, put≈5.57) and the put-call-parity identity.
- **`core/ftd_detector.py` + `core/ftd_status_service.py`** (`ftd-detector`)
  — O'Neil Follow-Through-Day state machine (`NO_SIGNAL → CORRECTION →
  RALLY_ATTEMPT → FTD_WINDOW → FTD_CONFIRMED`, with `RALLY_FAILED`/
  `FTD_INVALIDATED` branches), ported line-by-line from the skill's
  `rally_tracker.py`. The skill's own `fmp_client.py` and
  `report_generator.py` were not ported (redundant with this project's
  client/no formatting needed); only the pure swing-low/rally/FTD logic
  was adapted. Wired into `feature_packet` as `ftd_combined_state` /
  `ftd_dual_confirmation`, market-wide (SPY/QQQ), not symbol-specific.
  Live-verified against real current data (returned `CORRECTION` /
  `RALLY_FAILED` for SPY/NASDAQ as of 2026-10-30 — a plausible, non-crash
  result, not a fabricated "it works" claim).
- **`core/ibd_distribution_day_monitor.py` + `core/ibd_distribution_day_service.py`**
  (`ibd-distribution-day-monitor`) — IBD-style Distribution Day detection
  (decline >=0.2% on rising volume), 5%-gain invalidation, 25-session
  expiration, and NORMAL/CAUTION/HIGH/SEVERE risk classification (QQQ-
  weighted combination across SPY+QQQ, with a TQQQ/QQQ exposure-action
  mapper ported separately into `core/portfolio_tools/ibd_exposure_policy.py`,
  standalone like the other portfolio tools since it needs a caller-supplied
  current exposure, not live state this project tracks). The skill's own
  FMP client/compat/data-loader and Japanese-language report generator were
  not ported -- reuses `historical_price_service.py` instead. Wired into
  `feature_packet` as `ibd_overall_risk_level` / `ibd_qqq_d25_count`.
  Live-verified against real current data: returned SEVERE for both
  SPY and QQQ as of 2026-10-30 (QQQ: 2/7/9 distribution days in the
  5/15/25-session windows) -- consistent with the `ftd-detector`'s
  CORRECTION/RALLY_FAILED finding for the same date, a real cross-signal
  sanity check, not an isolated claim.
- **`core/market_top_detector/` + `core/market_top_detector_service.py`**
  (`market-top-detector`) -- 6-component weighted market-top risk composite
  (distribution days 25%, leading-stock health 20%, defensive rotation 15%,
  breadth divergence 15%, index technical condition 15%, sentiment 10%),
  ported from the skill's 6 calculators + scorer.py. The skill's own
  fmp_client.py, breadth_csv_client.py, _market_calendar.py, and
  report_generator.py were not ported. Real finding mid-build: FMP's free
  tier returns HTTP 402 for ETF quotes (QQQ/ARKK/XLU/etc. all blocked;
  individual stock quotes like AAPL/SPY work) -- worked around by deriving
  "quote" (price, 52-week high) directly from each ETF's own OHLCV history
  via `historical_price_service.py` instead, which is free AND leakage-safe
  (a live quote snapshot wouldn't be). `core/market_breadth_service.py` was
  extended with `breadth_200dma_pct`/`breadth_50dma_pct` (the feed already
  carried `Breadth_Index_Raw`/`Breadth_50_Index_Raw` columns, just not
  parsed before now) specifically to feed this calculator's breadth-
  divergence component. 3 of the 4 sentiment sub-inputs (put/call ratio,
  VIX term structure, margin debt YoY) have no free programmatic source --
  even the source skill only gets them via a human running WebSearch --
  left honestly as None; only VIX level (via ticker `^VIX`) is populated.
  Wired into `feature_packet` as `market_top_risk_score` / `market_top_risk_zone`.
  Live-verified against real current data: composite 56.6, "Orange
  (Elevated Risk)", 6/6 components resolved -- consistent with the
  SEVERE/CORRECTION findings from `ftd-detector` and
  `ibd-distribution-day-monitor` above for the same date.
- **`core/downtrend_duration_analyzer.py` + `core/downtrend_duration_service.py`**
  (`downtrend-duration-analyzer`) -- peak-to-trough downtrend duration/depth
  detection (rolling-window local peaks/troughs, min 5% depth / 3-day
  duration filters), ported from analyze_downtrends.py. SCOPE REDUCTION,
  disclosed: the source skill's main point is a market-wide survey across
  ~100-500 stocks via FMP's `company-screener` endpoint, grouped by sector
  and market-cap tier -- that endpoint is confirmed premium-gated on the
  free tier (HTTP 402), same finding as the ETF-quote block above, and
  there's no free source for a stock universe with sector/market-cap
  metadata. What's actually built is the pure peak/trough/duration math
  applied PER-SYMBOL instead of across a universe ("how long and how deep
  have THIS symbol's past corrections typically run") -- a real, narrower,
  genuinely free and leakage-safe question, not the original's full scope.
  Ported without pandas/numpy (plain lists/dicts, this project's own
  convention). Wired into `feature_packet` as `downtrend_median_duration_days`/
  `downtrend_p90_duration_days`, not gated by `_is_index_symbol`. Live-
  verified against real AAPL history: correctly found its real Jul-Aug
  2026 correction ($340.08 -> $302.25, -11.1%, 11 days) among 17 total
  downtrends over 5 years (median 22 days).
- **`core/pair_trade_analyzer.py` + `core/pair_trade_service.py`**
  (`pair-trade-screener`) -- pairs-trading spread analysis: OLS hedge
  ratio, Augmented Dickey-Fuller cointegration test, AR(1) mean-reversion
  half-life, rolling z-score, and a LONG_SPREAD/SHORT_SPREAD/WAIT/
  NO_TRADE_NOT_COINTEGRATED signal, ported from analyze_spread.py. Added
  `statsmodels>=0.14,<0.15` to `requirements.txt` (confirmed installable,
  not previously a dependency). SCOPE REDUCTION, disclosed: the skill's
  OTHER script, find_pairs.py, DISCOVERS candidate pairs by scanning an
  entire FMP sector universe via `company-screener` -- confirmed premium-
  gated (same finding as above), so pair discovery wasn't rebuilt. What's
  built is the pure pair-ANALYSIS math for a caller-GIVEN pair, which
  doesn't need a universe. NOT wired into `feature_packet` (documented in
  that module's own docstring): the single-symbol prediction pipeline has
  no natural "partner symbol" to pair against -- a real, tested, standalone
  utility, same category as `core/portfolio_tools/options_pricer.py`.
  Live-verified against real KO/PEP price history (correctly returned an
  honest `NO_TRADE_NOT_COINTEGRATED` over a 1-year window -- p=0.34, not
  cointegrated at that window length -- rather than forcing a false signal).
- **`core/pead_screener.py` + `core/pead_screener_service.py`**
  (`pead-screener`) -- Post-Earnings-Announcement-Drift weekly-candle
  pattern analysis (ISO-week candle conversion, red-candle pullback
  detection, breakout/liquidity/risk-reward scoring, 4-component composite
  -> Strong/Good/Developing/Weak rating), ported from screen_pead.py +
  its 4 calculators + scorer.py. REAL FINDING mid-build: FMP's free-tier
  `earnings-calendar` endpoint (already used for `fmp_calendar_service.py`)
  turns out to reject date ranges more than a few days in the past (HTTP
  402) -- it only serves near-term/future dates, so it can't answer "when
  did this company last report," which PEAD fundamentally needs (a 5-week
  watch window). Worked around with a genuinely better free source:
  `core/free_news_service.fetch_most_recent_earnings_8k()` (new function,
  added this session) finds the most recent SEC 8-K filing tagged with
  item code 2.02 ("Results of Operations and Financial Condition") --
  confirmed live against AAPL's real filing history, where every 2.02-
  tagged 8-K lines up exactly with its known quarterly earnings dates.
  SCOPE REDUCTION, disclosed: the skill's "Mode A" candidate-discovery
  path (scanning FMP's earnings calendar + screener across the whole
  market) was not ported -- same category as every other universe-scan
  skill above. Also disclosed: SEC doesn't record BMO/AMC earnings-call
  timing the way FMP's calendar does, so the gap calculation always runs
  in "unknown" (AMC-style) mode here. Wired into `feature_packet` as
  `pead_composite_score` / `pead_stage`, gated to non-index symbols.
  Live-verified against real AAPL data: correctly returned nothing as of
  2026-10-30 (its last earnings, 2026-07-30, is outside the 49-day lookback
  window -- an honest "no setup," not a fabricated one) and a real,
  complete analysis as of 2026-08-25 (4 weeks post-earnings, SIGNAL_READY
  stage, composite 54.0/"Weak").
- **`core/earnings_trade_analyzer.py` + `core/earnings_trade_analyzer_service.py`**
  (`earnings-trade-analyzer`) -- 5-factor post-earnings reaction scoring
  (gap size 25%, pre-earnings 20-day trend 30%, 20d/60d volume ratio 20%,
  MA200 position 15%, MA50 position 10%) -> A/B/C/D grade, ported from
  analyze_earnings_trades.py + its 5 calculators + scorer.py. Reuses the
  same `fetch_most_recent_earnings_8k()` built for `pead-screener` above.
  RECENCY CONSTRAINT, disclosed: the volume-trend factor only makes sense
  when the most-recent price bars are close to the earnings date (the
  source skill's own default `--lookback-days` is 2-5) -- this service
  only runs when earnings happened within 10 days of `as_of_date`,
  returning an honest "stale, outside recency window" error otherwise
  rather than silently misapplying the factor to an old earnings date.
  SCOPE REDUCTION, disclosed: the skill's own 4-phase candidate-discovery
  pipeline (FMP earnings calendar -> company-profile batch -> market-cap
  filter) was not ported, same reasoning as `pead-screener`. Wired into
  `feature_packet` as `earnings_reaction_score` / `earnings_reaction_grade`,
  gated to non-index symbols. Live-verified against real AAPL data 4 days
  after its real 2026-07-30 earnings: composite 67.0, grade C ("Mixed
  signals, use caution") -- caught and fixed a real bug in the first pass:
  the initial 260-calendar-day price lookback under-covered the 200
  TRADING days the MA200 factor needs (weekends/holidays), silently
  zeroing that component; fixed by widening to 310 calendar days.
- **`core/stockbee_exhaustion_hammer_screener.py` + `core/stockbee_exhaustion_hammer_service.py`**
  (`stockbee-exhaustion-hammer-screener`) -- selling-exhaustion hammer
  detection: prior momentum + multi-day pullback + undercut/reclaim of a
  short-term low + hammer-candle geometry (long lower wick, small body,
  strong close location) + risk-to-stop distance, combined into a 6-
  component score -> A/A-/B/Watch/Reject rating and an
  ACTIONABLE_CLOSE_BUY/MANUAL_REVIEW/WATCH_TOMORROW/REJECTED state, ported
  from screen_exhaustion_hammer.py's `analyze_symbol()` and its profile/
  score helpers. SCOPE REDUCTION, disclosed: the skill's FMP-universe-scan
  input mode was not ported (same reasoning as every other universe-scan
  skill above); the `profile_row` market-cap/institutional-ownership
  parameter is accepted but always passed `None` (no free source), which
  the original's own scoring already degrades gracefully for. NOTABLE
  CROSS-SKILL REUSE: `market_gate` (one of the 6 scored components) is a
  real signal here, not a hardcoded default -- derived from this
  project's own `core/ibd_distribution_day_service.py` risk level
  (SEVERE -> restrictive, HIGH -> neutral, NORMAL/CAUTION -> allowed),
  which is exactly what the source skill's own `--market-gate` flag
  documentation asks for ("latest market-regime/exposure decision").
  Wired into `feature_packet` as `hammer_setup_score` / `hammer_state`,
  gated to non-index symbols. Live-verified against real AAPL data as of
  2026-10-30: correctly detected a `confirmed_exhaustion_hammer` pattern
  (raw score 76) but hard-rejected it (pullback too shallow at -2.0% vs
  the 6% minimum) with `market_gate=0` (restrictive) -- consistent with
  the SEVERE IBD distribution-day risk level found for the same date above.
- **`core/stockbee_momentum_burst_screener.py` + `core/stockbee_momentum_burst_service.py`**
  (`stockbee-momentum-burst-screener`) -- short-term Momentum Burst
  detection (4% price-gain breakout, dollar-gain breakout, range-
  expansion breakout, 9M-volume trigger, prior-base contraction, close-
  location, failure filters, risk-to-stop distance -> 7-component score
  -> A/A-/B/Watch/Reject rating and ACTIONABLE_DAY1/MANUAL_REVIEW/
  WATCH_ONLY/REJECTED state), ported from screen_momentum_burst.py's
  `analyze_symbol()` and its helpers -- the sibling skill to
  `stockbee-exhaustion-hammer-screener` above, built right after it and
  sharing the same scope reduction (FMP-universe-scan mode not ported)
  and the same `market_gate` derivation from
  `core/ibd_distribution_day_service.py`. Wired into `feature_packet` as
  `momentum_burst_score` / `momentum_burst_state`, gated to non-index
  symbols. Live-verified against real NVDA data as of 2026-10-30:
  correctly triggered on `range_expansion` (not `4pct_breakout`, since
  NVDA was actually DOWN -4.2% that day on 2.2x volume -- a real, honest
  reflection of a volatile down day, not a fabricated bullish signal),
  state `WATCH_ONLY`, `market_gate=0` (restrictive) again consistent with
  the SEVERE IBD risk level for the same date.
- **`core/stockbee_episodic_pivot_analyzer.py` + `core/stockbee_episodic_pivot_analyzer_service.py`**
  (`stockbee-episodic-pivot-analyzer`) -- Day-1 Episodic Pivot catalyst
  classification (12-category keyword taxonomy: earnings, guidance raise,
  M&A, FDA approval, major contract, analyst upgrade, etc.) combined with
  price-action/volume-shock/neglect-revaluation/liquidity/risk-distance
  scoring, ported from analyze_ep.py's `analyze_candidate()` and its
  helpers. The source skill is explicitly "catalyst-first" -- it does not
  discover news itself, it expects a pre-supplied events file.
  NOTABLE CROSS-SKILL REUSE: this service supplies that catalyst from two
  real sources already built this session, tried in order: (1)
  `earnings_trade_analyzer_service.py`'s recent-earnings result
  (leakage-safe), or (2) `free_news_service.fetch_yahoo_headline_tags`'s
  live RSS headlines (extended this session to also return raw headline
  titles, not just counts) run through this module's own keyword
  classifier. If neither resolves a real catalyst, it returns an honest
  error rather than fabricating one. Wired into `feature_packet` as
  `episodic_pivot_score` / `episodic_pivot_state`, gated to non-index
  symbols. Live-verified against three real symbols as of 2026-10-30:
  AAPL and NVDA correctly classified "earnings" from live headline text
  (no earnings within the 10-day recency window, so it fell through to
  the Yahoo path), TSLA correctly used the earnings-trade-analyzer path
  with its real 2026-10-21 earnings date and grade D -- all three landed
  on the same honest `CATALYST_WATCH` state (price move not yet confirmed),
  not a fabricated actionable signal.
- **`core/stockbee_setup_fluency_trainer.py` + `core/stockbee_setup_fluency_trainer_service.py`**
  (`stockbee-setup-fluency-trainer`) -- a persistent "model book" that
  records `stockbee-momentum-burst-screener` candidates as study examples,
  matures them with 3d/5d forward MFE/MAE/outcome tags once enough future
  price data exists, and summarizes win-rate evidence grouped by setup
  tag/rating/trigger, flagging promote/downgrade rule candidates. Ported
  from build_model_book.py. NOT wired into `feature_packet`, same category
  as `core/portfolio_tools/backtest_quality_scorer.py` -- this is
  explicitly a journaling/research tool whose value accrues over many
  days of real ingestion, and this project's prediction pipeline runs one
  symbol at a time rather than a daily batch screener sweep, so there's no
  natural "auto-ingest every prediction" hook. Meant to be called
  manually (or from a future cron) after running
  `stockbee_momentum_burst_service.py` on a watchlist. Store format: JSONL
  at `data/stockbee_model_book.jsonl`, matching the source skill's own
  on-disk format exactly. Live-verified end-to-end against a real NVDA
  momentum-burst candidate: ingested, persisted, and correctly reported
  zero maturable outcomes when run same-day as the setup (there's no
  future price data yet by definition) -- an honest result, not a
  fabricated one.
- **`core/vcp_screener.py` + `core/vcp_screener_service.py`** (`vcp-screener`)
  -- Mark Minervini's Volatility Contraction Pattern detection: Minervini-
  weighted relative strength vs S&P 500, the 7-point Trend Template
  (Stage-2 uptrend gate), ATR-based ZigZag swing/contraction detection
  (T1-T4 tightening sequence validation), volume dry-up zone analysis,
  pivot proximity/risk, an execution-state engine (Invalid/Damaged/
  Overextended/Extended/Early-post-breakout/Breakout/Pre-breakout) that
  caps the maximum allowed rating, and a pattern classifier (Textbook
  VCP/VCP-adjacent/Post-breakout/Extended Leader/Damaged), ported from
  screen_vcp.py's `analyze_stock()` + its 5 calculators + scorer.py (the
  largest single-file port this session, ~1,500 ported lines). Entirely
  price-history-based -- unlike almost everything else in this FMP-
  unlocked batch, this skill needs NO fundamentals/institutional/FMP
  data at all, just the symbol's own OHLCV plus an SPY benchmark, both
  already served by `historical_price_service.py`. Only the single-stock
  pipeline was ported; the skill's own FMP-universe-scan mode and
  historical_scanner.py (a forward-outcome backtest harness) were not.
  Wired into `feature_packet` as `vcp_composite_score` / `vcp_execution_state`,
  gated to non-index symbols. Live-verified against real AAPL/NVDA/PLTR
  data as of 2026-10-30: NVDA and PLTR correctly flagged `Damaged`
  (price below their 50-day SMA) -- consistent with the SEVERE/CORRECTION
  signals found throughout this session for the same date -- while AAPL
  honestly scored `Weak VCP`/`VCP-adjacent` rather than a fabricated
  bullish pattern.
- **`core/canslim_screener.py` + `core/canslim_screener_service.py`**
  (`canslim-screener`) -- William O'Neil's full 7-component CANSLIM
  methodology (Current quarterly earnings, Annual growth, Newness/52-week-
  high proximity, Supply/demand volume accumulation, Leadership/relative
  strength, Institutional sponsorship, Market direction) with O'Neil's
  original Phase-3 weights, ported from screen_canslim.py's `analyze_stock()`
  + its 7 calculators + scorer.py. Previously deferred earlier this session
  because C and A genuinely need quarterly/annual EPS+revenue data this
  project didn't have yet -- unblocked by building real, new SEC XBRL
  extraction (`sec_financials_service.fetch_quarterly_eps_revenue_series`/
  `fetch_annual_eps_revenue_series`): confirmed live that SEC's XBRL feed
  mixes standalone-quarter spans (80-100 days) with cumulative YTD spans
  under the exact same tag, so quarters are isolated by span length, the
  same technique `_annual_entries` already used for 1-year spans. L reuses
  `vcp_screener.calculate_relative_strength` (a near-duplicate Minervini-
  style weighted RS, disclosed substitution, not a different methodology)
  instead of porting canslim-screener's own 654-line leadership_calculator.py.
  I is an honest PROXY via this project's existing 23-well-known-filer 13F
  tracker (`institutional_holdings_service.py`) -- holder count capped at
  23, ownership_pct always None (no free shares-outstanding source), and
  `score_institutional_sponsorship` scores this path at half weight to
  reflect it's weaker than the FMP/Finviz-backed original, rather than
  pretending it's equivalent. M reuses SPY+VIX via `historical_price_service.py`.
  Wired into `feature_packet` as `canslim_composite_score` / `canslim_rating`,
  gated to non-index symbols. Live-verified against real NVDA and KO data
  as of 2026-10-30: NVDA scored C=100/A=82 (real hypergrowth) for an
  "Above Average"/watchlist rating; KO -- a mature, slow-growing dividend
  stock -- correctly scored C=0/A=0 for a "Weak"/avoid rating, exactly the
  methodologically correct outcome for a non-growth stock under CANSLIM.
- **`core/dividend_growth_pullback_screener.py` + `core/dividend_growth_pullback_screener_service.py`**
  (`dividend-growth-pullback-screener`) -- dividend growth CAGR/consistency,
  FCF/earnings payout-ratio sustainability, and RSI(14) pullback timing,
  ported from screen_dividend_growth_rsi.py's `StockAnalyzer`/`RSICalculator`.
  Unblocked the same way canslim-screener was: by extending
  `sec_financials_service.py` with `fetch_annual_dividend_series` (derives
  per-share dividends from total dividends paid / weighted-average diluted
  shares, since the direct per-share XBRL tag was found live to be stale
  for real filers -- e.g. KO's only has entries from 2008-2009) and
  `fetch_cash_flow_coverage` (OCF - capex for FCF). Real finding mid-build:
  dividends-paid is reported under yet another different tag per filer
  (KO: `PaymentsOfDividends`; JNJ: neither that nor
  `PaymentsOfDividendsCommonStock` -- only `PaymentsOfOrdinaryDividends`) --
  same multi-tag-fallback pattern already used for revenue, now extended
  to 4 candidate tags. SCOPE REDUCTION, disclosed: the composite's
  "Financial Quality" (ROE/debt-to-equity) and "Valuation" (P/E, P/B)
  components were dropped -- "total debt" has no single reliably filer-
  consistent XBRL tag, and rushing it risked the exact silently-wrong-
  numbers failure this project has avoided all session; the composite is
  re-weighted across Dividend Growth/Profit Margin/RSI Timing instead.
  REIT-specific FFO payout accounting also wasn't ported (no free REIT
  classification source). Wired into `feature_packet` as
  `dividend_growth_score` / `dividend_cagr_3yr`, gated to non-index
  symbols. Live-verified against real KO and JNJ data as of 2026-10-30:
  computed dividend yields (2.16% KO, 1.87% JNJ) matched real current
  market yields almost exactly, and KO's dividend was correctly flagged
  as NOT fully covered by free cash flow (`INSUFFICIENT_FCF`) while JNJ's
  was (`COVERED`) -- a real, honest, non-fabricated distinction.
- **`core/value_dividend_screener.py` + `core/value_dividend_screener_service.py`**
  (`value-dividend-screener`) -- dividend STABILITY (volatility + years-of-
  growth across full available history, not just a 3-year CAGR), revenue/
  EPS trend direction, and the same sustainability check as
  `dividend-growth-pullback-screener`, ported from screen_dividend_stocks.py's
  `StockAnalyzer`. Built as the direct sibling of
  `dividend-growth-pullback-screener` (same session, same new SEC XBRL
  dividend/cash-flow extraction) -- reuses that module's
  `calculate_rsi()`/`analyze_payout_sustainability()`/`calculate_cagr()`
  directly rather than re-porting near-identical logic a second time; only
  the genuinely distinct stability/trend math was ported fresh. Same
  "Financial Health"/"ROE" scope reduction as its sibling, disclosed in
  the module docstring, with the composite rescaled from a 90-point raw
  budget to 0-100. Wired into `feature_packet` as `value_dividend_score` /
  `dividend_stable`, gated to non-index symbols. Live-verified against
  real KO and JNJ data as of 2026-10-30: JNJ correctly came back with
  `revenue_uptrend=False` (CAGR -0.26%) -- a real, non-fabricated
  reflection of JNJ's 2023 Kenvue consumer-health spinoff reducing
  reported revenue, not a data error.
- **`core/stockbee_20pct_study.py` + `core/stockbee_20pct_study_service.py`**
  (`stockbee-20pct-study`) -- detects whether a symbol just had a 20%+
  move over a trailing 5-day window and classifies its chart pattern
  (GAP_AND_GO/BASE_BREAKOUT/CLIMAX_EXTENSION/BREAKDOWN_EVENT/etc.), close
  quality, extension risk, and continuation-quality/reversal-risk/study-
  priority scores, ported from run_20pct_study.py's `detect_twenty_pct_events`
  and its classifiers/scorer. Entirely price-history-based -- no
  fundamentals/FMP needed. SCOPE REDUCTION, disclosed: the source skill's
  own design is a cross-universe daily SCAN with a persistent JSONL
  journal for episode tracking and forward-outcome maturation (the same
  discover+journal shape as `stockbee-setup-fluency-trainer` above) --
  only the point-in-time detection+classification+scoring for a single,
  caller-given symbol is built (the ported function already takes a
  `{symbol: bars}` dict and loops over it, so calling it with exactly one
  symbol is a faithful use of the unmodified function, not a rewrite);
  the episode-journal half was not built, for the same "no natural daily
  cross-sectional scan to journal from" reason as its sibling. Catalyst
  classification always returns `NO_CLEAR_NEWS` (the skill's optional
  news-enrichment step wasn't ported). Wired into `feature_packet` as
  `twenty_pct_study_score` / `twenty_pct_study_direction`, gated to non-
  index symbols -- a `None` result (no qualifying move that day) is
  treated as an honest absence, not an error. Live-verified against real
  AAPL/NVDA/PLTR data as of 2026-10-30: correctly found no event for any
  of the three (none had a real 20%+ 5-day move on that date) --
  confirmed via synthetic tests (12/12 passing, including a forced-
  positive case) that the detector does fire correctly when a real
  qualifying move is present.

- `fxmacrodata_client.py` + `macro_calendar_service.py` (fxmacrodata-
  calendar) — top-tier US macro release-calendar risk (CPI/NFP/GDP/FOMC,
  etc.) from `api.fxmacrodata.com`'s free, keyless `/calendar/{currency}`
  endpoint. Confirmed live (2026-11-02): real official Fed/BLS/BEA release
  rows with no API key. SCOPE REDUCTION, disclosed: the paid `/snapshot`
  point-in-time endpoint returned HTTP 401 without a key, and the free
  `/calendar` endpoint's own history only starts 2026-07-27 forward
  (`history_truncated: true`, zero rows for a 2025-01 test range) -- so
  this is LIVE-ONLY, gated to `_is_recent_origin` exactly like the put/
  call ratio and yfinance earnings fallback, never trusted for historical
  replay. Live-verified: found a real "Trade Balance" release 2 days out
  from today, and correctly returned nothing (not fabricated) for a
  2025-01 historical date outside free-tier coverage. Wired into
  `feature_packet` as `macro_event_days_away` / `macro_event_tier`.

- `weekly_performance_digest.py` + `weekly_performance_digest_service.py`
  (weekly-performance-digest) — win rate/expectancy/profit-factor over a
  date window, broken down by symbol/decision/horizon-bucket/decision-
  match-correctness, plus top winners/losers and rule-based process-
  improvement flags. SCOPE REDUCTION, disclosed: the source skill reads
  real closed broker theses (`trader-memory-core`'s YAML state, with real
  stop-losses and MAE/MFE excursion tracking) this project has no
  equivalent for; substituted with this project's own real "closed" unit
  -- a validated row in the `stock_predictions` table -- using its already
  -computed simulated `actual_total_pl` (real market move x the user's
  chosen initial_capital, not a real brokerage fill) for win/loss and P&L
  math. R-multiple and MAE/MFE are dropped entirely rather than faked
  (no stop-loss/intraday-excursion concept exists per prediction here).
  Live-verified against the real Supabase DB: pulled 477 real validated
  records over a wide date window, win rate 55.6%, consistent with this
  project's independently-known ~55% directional-match figure. Standalone
  reporting tool like `core/portfolio_tools/`, not wired into
  `feature_packet`.

- `signal_postmortem.py` + `signal_postmortem_service.py`
  (signal-postmortem) — TRUE_POSITIVE/FALSE_POSITIVE/REGIME_MISMATCH
  classification of this project's own validated predictions (predicted
  direction vs. realized return sign, with a regime-at-signal-vs-regime-
  at-exit check via `core/macro_regime_service.py` distinguishing a
  genuine miscall from one that failed because the macro regime flipped
  underneath it), aggregated by symbol/decision with the source skill's
  own 20-sample minimum-sample-size rule before trusting a rate.
  SCOPE REDUCTION, disclosed: the source skill is a feedback step for a
  multi-skill "edge pipeline" (many competing skills' signals re-weighted
  by false-positive rate, plus a skill-improvement backlog) this project
  has no equivalent for -- there is exactly one decision-maker (the
  Gemini consensus engine), not many to re-weight, so the weight-feedback
  JSON and improvement-backlog YAML are dropped, and `MISSED_OPPORTUNITY`
  never applies (no "signal considered but not taken" concept here).
  Standalone reporting tool, not wired into `feature_packet`.

- `exposure_coach.py` + `exposure_coach_service.py` (exposure-coach) —
  synthesizes this project's already-live market-top-detector,
  ftd-detector, macro-regime-detector, and market-breadth/uptrend
  sources into one "how much capital should I commit to equities right
  now?" Market Posture (`exposure_ceiling_pct`, `participation`,
  `recommendation`, `confidence`), parsing market-top-detector's own
  `risk_budget` string ("60-75%") as the baseline ceiling, then applying
  a narrow-participation haircut and a hard defensive floor during an
  unconfirmed FTD/correction state. SCOPE REDUCTION, disclosed: the
  source skill also ingests theme-detector, sector-analyst, and
  institutional-flow-tracker outputs, none of which exist in this
  project (theme-detector is FINVIZ-blocked; the other two weren't
  built) -- those three dimensions always report in `inputs_missing`,
  never fabricated, and the source skill's growth-vs-value `bias` field
  (which depends on exactly those three) is dropped rather than guessed.
  Per the source skill's own design, a dead/missing upstream source
  degrades confidence, never fails the whole call. Standalone, market-
  wide reporting tool, not wired into `feature_packet`.

- `data_quality_checker.py` (data-quality-checker) — Markdown document
  linting: price-scale confusion (ETF vs. futures vs. index, via the
  source skill's own digit-count-before-decimal table), date/weekday
  mismatches (calendar-verified), allocation-section totals (~100%
  check), and bp/% unit-mixing flags. Pure text processing, zero
  dependencies, zero scope reduction on the English-language checks
  themselves. SCOPE REDUCTION, disclosed: the source skill is bilingual
  (English + Japanese, full-width character normalization); this port
  is English-only -- guessing at Japanese tokenization/normalization
  with no way to test it against real Japanese documents would risk a
  confidently-wrong result. The separate instrument-notation style-guide
  check and the no-explicit-year date-inference heuristic are also not
  ported (see module docstring). Advisory-only, per the source skill's
  own Key Principle 1 -- every finding is WARNING/INFO/ERROR, never a
  blocker. Standalone text-processing utility, not wired into
  `feature_packet` (nothing in this pipeline currently generates the
  kind of blog/report Markdown it's meant to check).

- `druckenmiller_synthesizer.py` + `druckenmiller_synthesizer_service.py`
  (stanley-druckenmiller-investment) — a second, differently-weighted
  meta-synthesizer over the same 4 live upstream sources as exposure-
  coach: a 0-100 conviction score, one of 4 Druckenmiller pattern
  classifications (Policy Pivot Anticipation / Unsustainable Distortion
  / Extreme Sentiment Contrarian / Wait & Observe), and a 5-tier
  conviction-zone exposure range. SCOPE REDUCTION, disclosed: the source
  skill's 7-component weighting also needs Theme Quality (theme-detector,
  FINVIZ-blocked) and Setup Availability (a market-wide VCP/CANSLIM scan
  this project's per-symbol screeners can't do without FMP's premium
  screener) -- both dropped, never faked, and the remaining 5 components'
  weights (78/100 in the source skill) rescaled to sum to 100. Live-
  verified for 2026-10-30: "Moderate Conviction" (45.2, reduce position
  sizes) -- consistent with exposure-coach's independently-computed
  defensive read for the same date. Standalone, market-wide reporting
  tool, not wired into `feature_packet`.

- `crypto_regime_analyzer.py` + `crypto_regime_service.py` +
  `tools/coingecko_client.py` + `tools/binance_funding_client.py`
  (crypto-regime-analyzer) — 6-component, 0-100 crypto market regime
  score (BTC trend structure, alt breadth participation, BTC dominance
  regime, perpetual funding regime, drawdown/volatility position,
  momentum thrust/washout) from CoinGecko's + Binance's free, keyless
  public APIs, faithfully following every threshold table and the
  proportional-weight-redistribution composite rule in the source
  skill's own methodology reference -- zero scope reduction on the
  scoring math itself, unlike most other ports this session, since this
  skill's data sources are genuinely free. Confirmed live two real
  limitations the source skill's docs don't fully spell out: (1)
  CoinGecko's public tier caps `market_chart` history at 365 days (a
  401 with `error_code: 10012` beyond that, fixed by requesting exactly
  365 instead of a larger number), and (2) even at the documented 6.5s
  inter-call throttle, enough alt-coin history calls in one run can
  still hit 429s. Live-verified end-to-end: BTC trend structure, funding
  regime, and drawdown/volatility all computed from real data in one
  run; the rate-limited alt breadth/dominance/momentum components
  degraded honestly (`data_available: false`, not fabricated), and the
  composite correctly reported `UNKNOWN` once too much weight was
  missing -- proving both the real-data path and the degrade-never-fail
  path work. Offline/snapshot mode (`fetch_crypto_regime_from_snapshot`)
  is pure/network-free, per the source skill's own schema. Standalone,
  crypto-market-wide tool -- not wired into `feature_packet` (this
  project's domain is equities).

- `breakout_trade_planner.py` + `breakout_trade_planner_service.py`
  (breakout-trade-planner) — Minervini-style entry/stop/target derivation
  (`signal_entry`/`worst_entry`/`stop_loss` from pivot + last contraction
  low), the full Minervini Gate (valid_vcp, rating band, <=8% worst-case
  risk, plus breakout-state-only volume/chase/price checks),
  rating-based position-size multipliers, and a sequential portfolio-
  heat + sector-exposure cap across candidates, consuming this project's
  own `core/vcp_screener.py` output directly. Alpaca-bracket-order-shaped
  templates (`order_class: bracket`, `stop_loss.stop_price`,
  `take_profit.limit_price`) for both pre_place (stop-limit) and
  post_confirm (limit) modes. SCOPE REDUCTION, disclosed: the source
  skill's 5-minute-bar breakout confirmation step (via a separate
  `breakout-monitor` skill this project has no intraday feed for) is not
  ported -- the `post_confirm` template is still produced, but nothing
  here performs that confirmation check itself. Live-verified end-to-end
  against real `vcp_screener_service` output for AAPL/MSFT/NVDA/TSLA as
  of 2026-10-30: correctly produced no ACTIONABLE trades and traceable
  gate-failure reasons for each rejection/watchlisting, consistent with
  the correction-state market conditions other screeners found for that
  same date. Standalone batch tool, not wired into `feature_packet`.

- `parabolic_short_screener.py` + `parabolic_short_screener_service.py`
  (Phase 1) + `parabolic_short_plan.py` (Phase 2) (parabolic-short-
  trade-planner) — Qullamaggie-style parabolic-exhaustion screener
  (5-day return / MA extension / acceleration / volume climax / range
  expansion / liquidity preconditions, mode-aware hard invalidation
  rules faithfully ported from the source skill's own tables -- earnings
  blackout, market-cap floor, ADV floor, $5 price floor, 60-trading-day
  IPO seasoning), a 30/25/20/15/10-weighted composite with A-D grading,
  the "still in markup" state cap, and Phase 2's three trigger-plan
  templates (ORL break / first-red-5min / VWAP-fail) with SEC Rule 201
  SSR detection and `ManualBrokerAdapter`-based position sizing.
  Live-verified: confirmed FMP's free-tier `/profile` endpoint (not
  previously used this session) returns `marketCap` + `ipoDate` with no
  premium gate; ran the full pipeline against AAPL/TSLA/NVDA for
  2026-10-30 and correctly found no parabolic candidates (honest --
  none had a real 30%+ 5-day move that date). SCOPE REDUCTIONS,
  disclosed: (1) the source skill's internal per-factor 0-100 sub-
  scoring formulas aren't readable/executable to verify against, so
  this uses its own documented graduated-scoring curve built from the
  real qualifying thresholds, not the source's exact internals; (2)
  cross-sectional S&P 500 universe discovery is dropped (same FMP-
  premium-screener reduction as every other screener here) -- this
  screens one caller-supplied symbol at a time; (3) Phase 2's real
  Alpaca short-inventory/SSR-carryover-persistence check is replaced
  entirely by `ManualBrokerAdapter` (no Alpaca account exists here),
  so every plan is honestly `plan_status: watch_only`, exactly the
  source skill's own documented no-Alpaca fallback behavior, not a
  simulation of a different one. Phase 3 (`monitor_intraday_trigger.py`,
  live 5-min bar FSM) is NOT built -- it hard-requires a live Alpaca
  market-data connection and a real/paper brokerage account, the same
  "physical broker account" category as `portfolio-manager` and
  `mt5-robot-tester`.

- `institutional_flow_tracker.py` + `institutional_flow_tracker_service.py`
  (institutional-flow-tracker) — quarter-over-quarter ACCUMULATION/
  DISTRIBUTION/NEW_POSITION/EXITED classification per filer and a net
  flow score, reusing `core/institutional_holdings_service.py`'s already
  -live, free, keyless SEC EDGAR 13F-HR parsing (the same 23-well-known-
  filer list already vetted for canslim_screener.py's institutional-
  sponsorship proxy). Extended `institutional_holdings_service.py` with
  `fetch_13f_holdings_at_offset()` (generalizing the existing "latest
  only" fetch to also pull the PRIOR quarter) and `build_cache()` to
  store it per filer -- backward compatible, confirmed existing
  canslim_screener tests still pass unchanged after the extension.
  SCOPE REDUCTION, disclosed: the source skill's cross-sectional "top 50
  stocks by institutional change" scan needs FMP's premium screener/
  institutional-ownership-change endpoints (same reduction as every
  other cross-universe skill here); this tracks ONE caller-supplied
  symbol's flow across the same curated 23 filers, not a market-wide
  scan of the thousands of real 13F filers. Live-verified against a
  freshly rebuilt cache (23 filers x 2 quarters, real SEC EDGAR data):
  AAPL -> SMART_MONEY_ACCUMULATION (42.9, 7 active filers), TSLA/NVDA ->
  SMART_MONEY_ACCUMULATION (66.7, 6 active filers) as of 2026-10-30.
  Wired into `feature_packet` as `institutional_flow_score` /
  `institutional_flow_classification`, gated to non-index symbols.

- `sector_rotation_analyzer.py` + `sector_rotation_service.py`
  (sector-analyst) — sector ranking by uptrend ratio, a cyclical-vs-
  defensive risk-regime score, overbought/oversold sector flags (read
  directly from TraderMonty's own CSV `Status` column), and a 4-phase
  market-cycle estimate (Early Cycle Recovery / Mid Cycle Expansion /
  Late Cycle / Recession) matched against the source skill's own
  documented outperformer sets per phase, with a confidence level
  derived from how decisively the top-ranked sectors overlap one phase
  vs. the runner-up. Data source: TraderMonty's free, keyless
  `sector_summary.csv` (confirmed live this session -- same GitHub-
  hosted family as `market_breadth_service.py`'s breadth/uptrend feeds).
  SCOPE REDUCTION, disclosed: the source skill's optional chart-image
  industry-level supplement and its narrative Markdown report (written
  by an LLM reading the script's output) aren't ported -- this produces
  the structured numeric analysis; prose generation is a presentation
  step this project's Gemini consensus engine already handles elsewhere.
  Live-verified against the real feed: correctly flagged Energy
  overbought / Utilities oversold straight from the real Status column,
  and honestly reported LOW confidence on the cycle-phase call when the
  real top-ranked sectors tied 3-way between Mid Cycle Expansion and
  Late Cycle, rather than forcing false certainty. Standalone, market-
  wide reporting tool, not wired into `feature_packet`.

- `futures_position_sizer.py` (futures-position-sizer) — contract-based
  risk sizing (direction/entry/stop -> contract count) over the source
  skill's own verified 23-market contract-spec table (multiplier/tick
  size/tick value, ported verbatim from official CME/CBOT/COMEX/NYMEX/
  CFE/ICE sources), with an exact-`Fraction`-based floor (never float
  division, so `contracts x risk_per_contract <= risk_budget` holds by
  construction) and the bond-family (ZT/ZF/ZN/ZB) 32nds/64ths tick-grid
  hard-rejection guard (every other symbol only warns). Pure, offline,
  zero scope reduction on the math/table itself -- this skill was
  already free and keyless. SCOPE REDUCTION, disclosed: only Mode A
  (explicit symbol/direction/entry/stop) is ported; Mode B (handoff from
  `contrarian-setup-gate`) is not, since that upstream skill needs FMP
  Premium+ COT data this project doesn't have, so there's no real
  `READY_FOR_PLAN` gate report to hand off from. Verified against the
  SKILL.md's own worked example (ES long, 2% risk budget on $100k ->
  1 contract, $1012.50 risk, 1.01% of account) byte-for-byte. Standalone
  utility, not wired into `feature_packet` (this project's domain is
  equities, not futures).

- `breadth_chart_analyst.py` + `breadth_chart_analyst_service.py`
  (breadth-chart-analyst) — CSV-only mode (the source skill's own
  documented PRIMARY, mandatory-first path; it explicitly calls chart-
  image analysis "SUPPLEMENTARY only" because "OpenCV image detection is
  fragile"). Dual-timeframe signal detection over
  `market_breadth_service.py`'s already-fetched Chart-1 (`breadth_200ma`/
  `breadth_8ma`) and Chart-2 (`uptrend_ratio`/`uptrend_trend`) series --
  no new data source. Faithfully ported thresholds: 73%/23%/60% for
  Chart 1's overheating/extreme-oversold/healthy zones, 10%/40% for
  Chart 2's bottom/top zones, dead-cross detection (8MA < 200MA), local
  trough/peak reversal detection (the BUY/SELL triggers), and
  RED-to-GREEN / GREEN-to-RED color transitions (color is SKILL.md's own
  trend-direction definition, not a separate raw CSV field -- confirmed
  live the feed has no color column). Caught and fixed a real scale bug
  while live-verifying: `breadth_200ma`/`breadth_8ma` are 0-1 fractions
  in the raw feed (confirmed via the live CSV's `Breadth_Index_200MA`
  column), not percentages -- an unscaled 0.61 was being misread as
  "extreme_oversold" against the 23%-threshold check before the x100
  fix. SCOPE REDUCTION, disclosed: the chart-IMAGE two-stage (full-chart
  + right-edge-crop) analysis path is not ported -- building an
  untestable OpenCV/vision reader for someone else's dashboard images
  would be a worse outcome than the CSV-only path the source skill
  itself prefers. Standalone, market-wide reporting tool, not wired
  into `feature_packet`.

- `contrarian_confirmation.py` + `contrarian_confirmation_service.py`
  (technical-analyst's data-driven "Contrarian Confirmation Mode",
  Shapiro Step 3) — the full weekly price-action reversal checklist over
  real OHLC history: weekly key reversal, failed extreme (intraweek
  poke-and-fail), failed breakout (confirmed-then-rejected within 3
  weeks, with the "FAILURE week, never the breakout week" `week_of`
  invariant), a continuation veto that always wins over a triggered
  signal, 5-week-fractal swing levels for a direction-correct stop
  reference, and the CONFIRMED/NOT_CONFIRMED/INSUFFICIENT_DATA verdict
  with the exact HIGH/MEDIUM confidence rule -- every window/truncation/
  strict-inequality rule ported word-for-word from the source skill's
  own reference checklist, CROWDED_SHORT handled by mirroring (negating
  and swapping high/low) rather than duplicating the logic. Debugging
  the test suite against hand-traced scenarios caught and confirmed two
  genuine, spec-correct behaviors that aren't obvious from a skim: (1) a
  single anomalous week can legitimately co-trigger both weekly_key_
  reversal AND failed_extreme when the swing- and extreme-lookback
  windows share the same flat-history ceiling, correctly producing HIGH
  rather than MEDIUM confidence; (2) a later week's own new closing
  breakout can itself fail within the recency window, shifting
  `failed_breakout`'s reported week_of forward and changing whether the
  continuation veto has room to fire. SCOPE REDUCTION, disclosed: only
  the explicit-direction path is built (no `--detector-json` consumption
  from `cot-contrarian-detector`, which needs FMP Premium+ COT data this
  project doesn't have -- same reduction as `futures-position-sizer`'s
  Mode-A-only port), and chart-image mode is not built (the data-driven
  script mode is the part with real, testable logic). Live-verified
  against real weekly-resampled history (88 weeks) for AAPL/TSLA/NVDA:
  correctly differentiated CONFIRMED (failed_extreme, MEDIUM) for
  AAPL/NVDA under CROWDED_LONG vs. an honest NOT_CONFIRMED
  (no_reversal_evidence) for TSLA under CROWDED_SHORT. Standalone,
  per-symbol tool, not wired into `feature_packet` (its crowd-direction
  input has no live source in this project without the blocked upstream
  detector).

- `news_reaction_failure.py` + `news_reaction_failure_service.py`
  (news-reaction-failure-analyzer, Shapiro Step 2) — the full drift-
  significance news-failure test, faithfully ported from
  `references/news-failure-patterns.md`'s own statistical design: 16:00
  ET effective-date resolution with weekend/holiday roll-forward, true
  k-trading-session returns (k in {1,3}) with mandatory sqrt(k) horizon
  scaling, event clustering by overlapping 3-day windows (earliest
  member's z3 drives the cluster, never averaged, to preserve the
  approximately-normal-under-the-null assumption), and the exact
  two-condition verdict (`drift_stat <= -1.45 AND responded_ratio <=
  0.25`) with the Monte-Carlo-chosen `DRIFT_Z_DEFAULT`. This explicitly
  replaces an earlier naive failure-ratio design the source skill's own
  docs show false-confirms on pure noise 48-83% of the time -- a good
  example of a skill whose documented RATIONALE for its math (not just
  the math itself) was worth reading closely before porting. SCOPE
  REDUCTION, disclosed: the events list itself (normally WebSearch-
  curated by Claude, dateable news classified BULLISH/BEARISH with a
  real cited source) is NOT fetched by this module -- same caller-
  supplies-the-input pattern as `breakout_trade_planner.py` consuming
  `vcp_screener` output. Live-verified against real AAPL price history
  with 3 hand-specified real 2026 macro/earnings dates: all 3 resolved
  to genuine effective dates and z-scores, honestly reporting
  NOT_CONFIRMED (responded_ratio 0.67, no real news-failure evidence).
  Standalone, per-symbol tool, not wired into `feature_packet` (no live
  events-curation source exists in this project).

- `contrarian_setup_gate.py` (contrarian-setup-gate, Shapiro pipeline
  synthesis center) — the full sequential precedence state machine over
  the three Shapiro-pipeline verdicts, ported exactly from the source
  skill's own 15-row collapsed decision table and its explicitly named
  precedence pins: each step (crowding -> news -> price-action) fully
  settles before the next step's input is even inspected, so a later
  step's problem can never soften an earlier step's definitive verdict
  (e.g. news NOT_CONFIRMED at step 2 means a corrupted or even genuinely
  CONFIRMED price-action report at step 3 is never consulted). Also
  ports the cross-input direction-consistency check and the CONFIRMED-
  path `stop_reference` validation (finite, positive, not a bool).
  `crowding` (step 1) still takes a plain `{"classification": ...}`
  dict rather than a file, but -- update after building
  `cot-contrarian-detector` (see below) -- that dict can now come from
  REAL CFTC COT data for the 10 curated markets, not just a caller
  assertion; for any other symbol it remains an explicit, disclosed
  stand-in. The two downstream steps are wired directly to this
  project's own real `news_reaction_failure_service.py` and
  `contrarian_confirmation_service.py`. The source skill's adversarial-
  JSON-file hardening (whole-file non-finite scanning, schema-version
  allowlisting) isn't ported -- this integration passes trusted
  in-memory dicts from this project's own services, not untrusted files
  read from disk, so that layer doesn't apply. Live-verified twice
  end-to-end: (1) chaining real AAPL outputs from both downstream
  services -- correctly reproduced the documented precedence behavior
  exactly, news settled NOT_CONFIRMED so an actually-CONFIRMED price-
  action result was correctly never inspected, yielding REJECTED; (2)
  chaining a REAL CFTC-derived EUR FX crowding result (CROWDED_SHORT)
  straight into the gate with both downstream steps pending, correctly
  yielding `CROWDED`. Standalone, per-symbol synthesis tool, not wired
  into `feature_packet`.

- `tools/cftc_cot_client.py` + `cot_contrarian_detector.py` +
  `cot_contrarian_detector_service.py` (cot-contrarian-detector, Shapiro
  Step 1) — **a major mid-session correction, not just a new skill**:
  the source skill's own docs say "COT endpoints require an FMP
  Premium+ plan," and this was treated as hard-blocked earlier this
  session (see the old, now-corrected text this replaced). That's true
  of FMP's specific wrapper only -- the underlying data is CFTC's own
  free, keyless, official Socrata API
  (`publicreporting.cftc.gov/resource/6dca-aqww.json`, the Legacy
  Futures-Only Report), confirmed live this session: real weekly
  non-commercial long/short + open-interest rows for the E-mini S&P
  500, Gold, Silver, WTI crude, Euro FX, Japanese Yen, British Pound,
  UST Bond, and VIX futures, going back to 2023 with no API key. Ported
  the exact "stochastics of positioning" COT Index formula
  (`(current - window_min) / (window_max - window_min) * 100` over a
  156-week primary + 26-week short lookback), the 90/10 CROWDED_LONG/
  CROWDED_SHORT/NEUTRAL thresholds, and `sort_dedupe_rows`'s "keep the
  last duplicate-date row" rule, all directly from
  `references/cot-index-calculation.md`. SCOPE REDUCTION, disclosed: a
  curated 10-market table (`MARKET_CODES`), not the full ~65-market
  universe FMP's wrapper covers -- each code individually verified live
  against the real CFTC API, not guessed. Live-verified across 5
  markets for 2026-10-30: genuinely differentiated real signals,
  including EUR FX at a real CROWDED_SHORT extreme (COT index 0.0 on
  both lookbacks) and UST Bond showing the methodology's own documented
  "fresh vs. aging extreme" divergence (74.9 on the 3-year window vs.
  100.0 on the 26-week window -- extreme now, but not yet the most
  extreme of the full 3-year history). Standalone, futures/macro-
  market tool (ES/VX aside, not equity-ticker-specific), not wired into
  `feature_packet`.

### Portfolio/order utilities (`core/portfolio_tools/`, standalone, tested)

All 11 trader-skill tools are now genuinely implemented (3 above as live
data services; these 8 as pure, tested utility modules) — not wired into
`feature_packet` since this project has no live order/portfolio execution
state to hang them on, but real, working, directly usable code, each with
its own test file:

- `budget_allocator.py` (trader-budget) — caught a real bug: when every
  position in an allocation simultaneously exceeds `max_position_pct`, the
  un-placeable excess was being dumped entirely onto one ticker instead of
  staying idle, silently blowing past the very cap it exists to enforce.
- `pretrade_risk_gate.py` (trader-risk) — PASS/BLOCK order validation
  (format/asset/blocked-list/size/position/cash/short checks).
- `tax_lot_optimizer.py` (trader-tax) — FIFO/HIFO lot selection, gain/loss,
  wash-sale checking (with same-issuer share-class families, e.g. GOOG/GOOGL).
- `portfolio_rebalancer.py` (trader-rebalance) — drift-band rebalancing,
  reusing `budget_allocator`'s capping logic for targets.
- `price_alert_engine.py` (trader-alerts) — above/below/stop/pct_move/
  opening_bell rule evaluation with ring-once/rearm state machine.
- `metric_screener.py` (trader-screener) — rule-based filtering + weighted
  ranking over arbitrary metric rows.
- `order_ticket.py` (trader-broker) — order fingerprinting + the strict
  per-order "yes" approval parser (the actual safety gate between a
  proposed order and any broker call). Caught two real bugs: a reply like
  "yes, 500" was rejected because the comma stuck to "yes" broke the exact
  first-word match, and the number-matching regex could match a stray
  comma as an empty "number" and crash on `float('')`.
- `drawdown_circuit_breaker.py` (claude-trading-skills) — daily/weekly/
  monthly realized-loss halts + losing-streak cooldown, as a pure function
  over caller-supplied closed-trade P&L (not the source skill's
  trader-memory-core thesis-YAML reader, which this project has no
  equivalent state for).
- `pretrade_discipline_gate.py` (claude-trading-skills) — written-plan/
  predefined-stop/size-confirmed checklist + planned-vs-actual risk check.
- `backtest_quality_scorer.py` (claude-trading-skills' backtest-expert) —
  5-dimension backtest quality scoring (sample size, expectancy, risk
  management, robustness, execution realism) in exact Decimal arithmetic
  (float cancellation error can flip a break-even strategy's sign, e.g.
  expectancy 2.2e-16 instead of exactly 0 for 40%/3%/2% inputs) → Deploy/
  Refine/Abandon verdict + red flags. Applied to this project's own real
  shadow-EV numbers (13 trades, no slippage test), it honestly returns
  "Refine," not "Deploy" — the scorer doesn't rubber-stamp its own author.
- `position_sizing.py` extended with `kelly_fraction()`, `fixed_fractional_shares()`,
  `atr_based_shares()` (position-sizer). Kelly is deliberately NOT wired
  into the main `compute_position_size()` path -- see that function's
  docstring on why Gemini's self-reported confidence can't honestly feed it.

## What was deliberately NOT adapted, and why

53 of 85 skills across both repos are now genuinely implemented (all 11
trader-skill tools + 42 claude-trading-skills: the original 7 -- market-
breadth-analyzer, uptrend-analyzer, macro-regime-detector, drawdown/
trader-memory-equivalent, pretrade-discipline, backtest-expert, position-
sizer -- plus `options-strategy-advisor`, `earnings-calendar`,
`ftd-detector`, `ibd-distribution-day-monitor`, `market-top-detector`,
`downtrend-duration-analyzer`, `pair-trade-screener`, `pead-screener`,
`earnings-trade-analyzer`, `stockbee-exhaustion-hammer-screener`,
`stockbee-momentum-burst-screener`, `stockbee-episodic-pivot-analyzer`,
`stockbee-setup-fluency-trainer`, `vcp-screener`, `canslim-screener`,
`dividend-growth-pullback-screener`, `value-dividend-screener`,
`stockbee-20pct-study`, `fxmacrodata-calendar`,
`weekly-performance-digest`, `signal-postmortem`, `exposure-coach`,
`data-quality-checker`, `stanley-druckenmiller-investment`,
`crypto-regime-analyzer`, `breakout-trade-planner`,
`parabolic-short-trade-planner`, `institutional-flow-tracker`, and
`sector-analyst`, `futures-position-sizer`, `breadth-chart-analyst`, `technical-analyst`, `news-reaction-failure-analyzer`,
`contrarian-setup-gate`, and `cot-contrarian-detector` (several of these
scope-reduced from a cross-universe survey to a single-symbol/single-pair
stat, or with specific sub-components substituted by honest proxies/
reuses -- see each entry above) from the FMP-key-unlocked batch above).
Note: `theme-detector` was investigated this segment and confirmed to
belong in the blocked category below -- its actual heat-scoring logic
(`_add_sector_info`/`_convert_perf_to_pct`/`_average_industry_perfs` in
the vendored `theme_detector.py`) depends on FINVIZ Elite's industry/
sector performance data, not price/ETF data this project has free access
to; a static-config-only substitute would not be a faithful port of the
skill's methodology, so it was not built under that name. One more,
`economic-calendar-fetcher`, was built and tested but is confirmed
BLOCKED on the free tier (HTTP 402) -- real, working code that simply
can't be exercised without a paid FMP plan, so it's not counted as
"implemented" even though it exists. The remaining ~49 fall into two
categories, both actually looked at, not silently skipped:

1. **Needs infrastructure this project doesn't have.** `finviz-screener`
   (FINVIZ Elite), `us-undervalued-growth-screener` and the rest of the
   swing-opportunity/strategy-research categories that need FMP's
   premium cross-universe company-screener endpoint, a Windows MT5
   terminal (`mt5-robot-tester`), the Rust `manifoldbt` backtesting
   engine, and Alpaca/IBKR live brokerage accounts (`portfolio-manager`,
   `parabolic-short-trade-planner`'s Phase 3) are real, hard
   requirements the skills themselves document — not something more
   engineering effort here resolves. **Correction mid-session**: COT
   data was initially placed in this category too (the skills' own docs
   say FMP's COT wrapper needs Premium+), but CFTC's own free, official
   Socrata API turned out to carry the same underlying data with no key
   at all -- see `cot-contrarian-detector` above, now implemented, not
   blocked. `contrarian-setup-gate`'s 1024-line state machine was
   ultimately built too (see above), once all three of its upstream
   steps turned out to be independently portable.
2. **Large, complex, multi-calculator systems that can't be safely hand-
   ported without the ability to test against the originals.**
   `macro-regime-detector` (~3,300 lines across 6 weighted cross-asset
   calculators) turned out to be portable with enough care -- see above,
   it's now done. `theme-detector` (17 scripts), `vcp-screener` (14
   scripts), `us-undervalued-growth-screener` (the largest skill,
   37,981-char SKILL.md, 15 scripts) and similar remain in this category
   though, both for their size and because most of them also need FMP
   data. Running the vendored originals to verify a hand-port against them
   is blocked (see above); re-deriving thousands more lines of financial
   logic from reading alone, with no way to test it, would risk shipping
   silently-wrong
   numbers into a live prediction pipeline — a bigger violation of this
   project's no-fabrication standard than leaving them vendored-only.
