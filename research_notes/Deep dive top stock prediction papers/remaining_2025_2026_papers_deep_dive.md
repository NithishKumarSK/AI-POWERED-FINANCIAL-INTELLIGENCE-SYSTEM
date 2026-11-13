# Deep Dive: Four Remaining 2025–2026 LLM Stock-Prediction Papers

Scope: arXiv 2512.23847 (lookahead/memorization detection), arXiv 2603.26797 (MemGuard-Alpha filtering tool), arXiv 2601.11958 (agentic nowcasting), arXiv 2603.20324 (Selection Bottleneck / judge vs. vote). Researched November 2026 via arXiv HTML full text, alphaXiv, EconPapers, and emergentmind.com. All four are very recent (Dec 2025–Mar 2026 initial submission); independent secondary coverage is thin, so several figures below rely on a single primary-source read and could not be cross-checked against a second full-text copy.

---

## PAPER 1 — "Detecting Lookahead Bias in LLM Forecasts" (arXiv 2512.23847) — Authors, Affiliation, Status

### Takeaway
This is a CUHK Business School (Chinese University of Hong Kong) Department of Finance paper by Zhenyu Gao, Wenxi Jiang, and Yutong Yan. It is arXiv-only (q-fin.GN), not peer-reviewed, first posted Dec 29 2025 under the title "A Test of Lookahead Bias in LLM Forecasts" and revised (v2) June 12 2026 under the current title; EconPapers shows a citation count of 4 as of its June 15 2026 snapshot (0 as of the Jan 13 2026 snapshot).

### Cited Findings
- Authors and affiliation: Zhenyu Gao, Wenxi Jiang, Yutong Yan, Department of Finance, CUHK Business School, The Chinese University of Hong Kong — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)
- v1 (Dec 29, 2025) title was "A Test of Lookahead Bias in LLM Forecasts"; v2 (June 12, 2026) retitled "Detecting Lookahead Bias in LLM Forecasts" — [arXiv abs](https://arxiv.org/abs/2512.23847), [arXiv v1 HTML](https://arxiv.org/html/2512.23847v1)
- Subject tags: General Finance (q-fin.GN), with cross-listing to Machine Learning and Trading/Market Microstructure — [EconPapers](https://econpapers.repec.org/paper/arxpapers/2512.23847.htm)
- EconPapers citation counter reads "Citations: (4)" as of a 2026-06-15 update; an earlier 2026-01-13 snapshot showed no citation count — [EconPapers](https://econpapers.repec.org/RePEc:arx:papers:2512.23847)
- No journal name, DOI, or peer-review acceptance notice appears anywhere in the captured arXiv HTML text — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)

### Inferences
- The term "Lookahead-Avoidance Probability" used in the assignment brief does not match the paper's own terminology; the paper's actual construct is called "Lookahead Propensity" (LAP). These likely refer to the same underlying idea (a probability that the model already "knows" an answer, hence the forecast should be discounted/avoided), but the team should use "LAP" when citing this paper to avoid confusion with other literature.
- A citation count of 4 after roughly six months, with no named citing papers surfaced, suggests the paper has very limited independent scholarly traction so far — treat it as a frontier/unvetted finding rather than an established result.

### Gaps
- No Google Scholar or Semantic Scholar citation count was independently retrieved (only EconPapers); the true current count may differ.
- No author seniority/role information (e.g., professor vs. PhD student) was found.

---

## PAPER 1 — Exact Methodology and Full Quantitative Results

### Takeaway
LAP is a literal "does the model already know the answer" probe: the model is asked, given only a firm/ticker and a date, whether the realized outcome went up or down, and LAP = P(up)+P(down) from first-token probabilities (near 1 = model commits to a direction = suspected memorization; near 0 = model abstains = likely genuine out-of-sample ignorance). Contamination is tested by seeing whether a forecast-accuracy regression's forecast coefficient is amplified specifically when LAP is high, via a triple interaction; the amplification effect is strong and statistically significant in-sample (pre-training-cutoff) and becomes statistically indistinguishable from zero in both of the paper's two post-cutoff out-of-sample tasks.

### Cited Findings
- Only one LLM tested: Llama-3.3-70B-Instruct, run locally via vLLM at temperature 0; stated training-data cutoff December 2023 — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)
- LAP construction: a "date-only recall" query gives the model just the firm name, ticker, and date, and asks whether the stock return (or capex) went up, down, or is unknown; LAP = P_up + P_down (first-token probabilities); a companion directional recall signal is (U−D) = P_up − P_down — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)
- Detection regression: Y = β₁·μ̂ + β₂·LAP + β₃·(LAP × μ̂) + ε, where μ̂ is the LLM's forecast; a positive β₃ is treated as a one-sided test for contamination loading γ > 0. The paper explicitly states it identifies only the *sign* of γ, not its magnitude — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)
- Task 1 (stock news → returns): Bloomberg headlines matched to CRSP returns. In-sample Jan 2012–Dec 2023, 91,357 headlines / 1,587 firms. Out-of-sample calendar-year 2024, 7,568 headlines (one part of the text says 7,806 recall queries for 2024 — an internal inconsistency the authors do not resolve) — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)
- Task 2 (earnings calls → capex): StreetEvents transcripts matched to CRSP/Compustat. In-sample 2006Q1–2020Q4, 106,994 firm-quarters / 3,920 firms. Out-of-sample 2023Q3–2024Q1, 6,744 firm-quarters (vs. 6,619 recall queries elsewhere in text — same kind of inconsistency) — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)
- Stock-news results: in-sample LLM-only forecast coefficient 0.21%-per-step equivalent / φ̂ not directly comparable; LLM×LAP interaction δ̂ = 0.162 (t = 3.64) in-sample, dropping to t = 1.06 post-cutoff; recall-only signal (U−D) θ̂ = 0.264 (t = 3.53) pooled in-sample, splitting into θ̂ = 0.306 (t = 3.59) for the high-LAP half vs. θ̂ = −0.159 (t = −0.33, insignificant) for the low-LAP half; post-cutoff the (U−D) effect is t ≈ 0 — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)
- Earnings-call/capex results: in-sample LLM-only coefficient 0.547 (t = 16.69), falling to φ̂ = 0.230 (t = 3.44) post-cutoff; LLM×LAP interaction δ̂ = 0.512 (t = 2.01) in-sample vs. a scale-distorted δ̂ = 276,109.73 (t = 1.35) post-cutoff; recall-only (U−D) θ̂ = 0.368 (t = 2.13) pooled in-sample, splitting into θ̂ = 0.539 (t = 2.90) high-LAP vs. a scale-distorted θ̂ = 27.05 (t = 0.71) low-LAP — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)
- Mean in-sample LAP for the stock-news task is 0.414 (SD 0.415); the post-cutoff (2024) mean LAP collapses to roughly 7×10⁻⁶ — i.e., the model essentially never commits to a direction for genuinely future dates, which the authors use as the mechanism explaining why the contamination interaction vanishes out-of-sample — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)
- Illustrative single-firm recall probabilities: Kodak P_up ≈ 0.9999 (an obviously memorized historical bankruptcy-adjacent fact), Amazon P_up ≈ 0.97 — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)
- R² values by table: stock-news Table III 0.178/0.244(high-LAP)/0.236(low-LAP); Table IV 0.179/0.180; Table V 0.179/0.180; Table VI (post-cutoff 2024) 0.207/0.213/0.213; capex Table VII 0.625/0.631(high-LAP)/0.613(low-LAP); Table VIII 0.628/0.628; Table IX 0.628/0.628; Table X (post-cutoff) 0.213/0.212/0.216 — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)
- Post-cutoff precision problem: in Table VI the U−D coefficient is −81.65 with t ≈ −0.00; in Table X the post-cutoff U−D coefficient is on a rescaled variable (~415,385), making magnitude hard to interpret directly — the authors' own text flags these as numerical artifacts of near-zero LAP variance rather than meaningful point estimates — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)
- Table X uses industry fixed effects while earlier capex tables use firm fixed effects — an unresolved specification inconsistency noted in the paper's own text — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)
- Appendix C: prompt-level mitigations such as masking firm identifiers "may not remove contamination" and must be empirically tested rather than assumed effective; if the in-sample LAP test shows contamination, the authors recommend backtests be restricted to data after the model's training cutoff — [arXiv:2512.23847](https://arxiv.org/html/2512.23847)

### Inferences
- The core, robust, headline finding — stated directly by the authors and consistent across both tasks — is: the amplifying interaction between LLM-forecast accuracy and memorization-proxy (LAP) is large and significant pre-cutoff, and the effect size/significance collapses post-cutoff mainly *because LAP itself collapses to near-zero post-cutoff* (the model simply won't commit to a direction for genuinely unseen dates), not because of some separate degradation of accuracy. This is a mechanism claim, not just an observation that "significance is lost."
- Because only one model (Llama-3.3-70B) and two narrow tasks (headline-return mapping, capex-from-earnings-calls) were tested, the generalizability of the exact coefficients to other models (e.g., GPT-4o, Gemini, Claude) or to a multi-ticker-ranking/consensus system is unconfirmed by this paper alone.

### Gaps
- The paper does not report a point estimate of the contamination loading γ itself — only its sign — so there is no number for "how much of the apparent edge is memorization" that can be lifted directly into a correction factor.
- It's unclear from the retrieved text whether the method was tested on any model newer than Llama-3.3-70B-Instruct (Dec 2023 cutoff); no results for frontier 2024/2025-cutoff models were found.

---

## PAPER 1 — Direct Applicability to Our Stock-Prediction System

### Takeaway
This paper provides a cheap, reusable diagnostic — the LAP probe — that our system could run against any ticker/date pair before trusting a signal, but it is a diagnostic tool, not a performance result we can import; the one number worth taking seriously is that LAP → ~0 almost immediately after a model's training cutoff, meaning genuinely forward-looking predictions should show near-zero LAP by construction.

### Inferences (team-specific, not stated by the authors)
- We should implement a LAP-style self-check: before accepting an LLM's directional call on a ticker, separately prompt the same model with a stripped-down "ticker + date, up/down/unknown" recall query and record the first-token P_up/P_down. If LAP is high (model commits confidently) for a date that is supposed to be in the future/out-of-sample relative to that model's training cutoff, that is a red flag for data leakage or an incorrectly-assumed cutoff date — directly actionable for `core/gemini_stock_prediction_agent.py` and `core/ml_feature_extractor.py`.
- Because the interaction/contamination effect is strongest specifically when the model is confident AND the query maps closely to something in training data (e.g., well-known historical price moves, famous bankruptcies), our calibration pipeline (`core/calibration_profile_builder.py`, `core/confidence_calibration_map.json`) should consider down-weighting or flagging high-confidence calls on stale/famous historical analogs as a contamination-risk category, separate from ordinary low-confidence calls.
- The paper's recommendation to "restrict backtests to data after the model's training cutoff" directly supports keeping (or tightening) any existing cutoff-date filtering logic in `core/historical_price_service.py` / `core/batch_validation_runner.py` — any backtest period that overlaps a model's pretraining window should be treated as contaminated unless proven otherwise via a LAP check.

### Gaps
- Without knowing our production models' exact training cutoffs and whether we already have any leakage-detection step, it's unclear how large an engineering lift adding a LAP probe would be; that is a codebase question, not a literature gap.

---

## PAPER 2 — MemGuard-Alpha (arXiv 2603.26797) — Authors, Affiliation, Status, and a Major Version Conflict

### Takeaway
MemGuard-Alpha is by Anisha Roy and Dip Roy, Indian Institute of Technology Patna, posted to cs.LG. Critically, the paper changed its central conclusion between versions: v1 (initial submission, title referencing "via Membership Inference and Cross-Model Disagreement") reported that its Cross-Model Memorization Disagreement (CMMD) filter *improved* trading performance; v2 (revised Sept 24 2026, retitled to lead with "Limits of Membership Inference...") reports the opposite — that no contamination-based filter beats the unfiltered ensemble once costs are applied symmetrically, and that the detection signal is mostly a scale/normalization artifact. This is a genuine, source-confirmed discrepancy, not researcher error — different secondary aggregators independently reflect the two different versions' claims.

### Cited Findings
- Authors: Anisha Roy and Dip Roy; affiliation given as Indian Institute of Technology, Patna, for both authors — [alphaXiv](https://www.alphaxiv.org/abs/2603.26797)
- Full current title: "MemGuard-Alpha: Limits of Membership Inference for Detecting and Filtering Memorization-Contaminated Signals in LLM-Based Financial Forecasting" — [arXiv:2603.26797](https://arxiv.org/html/2603.26797) (note: the direct arXiv HTML endpoint 404'd for this paper; title/abstract were read via alphaXiv mirror and Google-indexed snippets)
- v1 submitted March 26, 2026; v2 revised September 24, 2026; primary category cs.LG (Machine Learning) — [alphaXiv](https://www.alphaxiv.org/abs/2603.26797)
- A Google-indexed snippet of an earlier version shows the alternate title "Detecting and Filtering Memorization-Contaminated Signals in LLM-Based Financial Forecasting via Membership Inference and Cross-Model Disagreement," with that version's introduction arguing LLM alpha gains "tend to vanish once survivorship and look-ahead biases are controlled" — already a somewhat skeptical framing even in that earlier pass — [Google search snippet of arxiv.org/pdf/2603.26797.pdf]
- No journal/conference acceptance is stated anywhere; a "NeurIPS 2026" link on the alphaXiv page is site navigation, not a claim of acceptance — [alphaXiv](https://www.alphaxiv.org/abs/2603.26797)
- alphaXiv lists this paper separately from two unrelated "MemGuard" papers (arXiv 2605.28009 and 2608.21867), which are LLM-agent memory-governance papers with no connection to financial forecasting — [Google Search]

### Inferences
- The title change plus the sign-flip in reported conclusions (from "the filter works, CMMD improves Sharpe" to "no filter beats the unfiltered ensemble") strongly suggests the authors themselves found their original positive result was a measurement artifact and issued a self-correcting revision. This is scientifically healthy, but it means any single-source summary of "MemGuard-Alpha's results" risks citing the wrong version. **Our team should explicitly cite v2 (Sept 2026, the "Limits of..." version) as the authoritative, current claim**, and treat v1's positive numbers as superseded/retracted-in-spirit.
- No independent peer review exists yet for either version; this is an unusually fast public reversal on arXiv, which somewhat increases confidence that the authors are being rigorous rather than overclaiming, but also means the field has not yet weighed in.

### Gaps
- Could not obtain the raw PDF text (binary/compressed, not extractable by the fetch tool) to directly quote the five named MIA methods or the exact names/sizes of all seven tested LLMs; only the aggregate "seven LLMs, 124M–7B parameters" range was confirmed.
- No definitive resolution of which number set (v1's Sharpe 4.11 vs 2.76, or v2's "no filter beats unfiltered") is the authors' final intended claim beyond the version/title evidence above — this should be treated as the paper's own internal correction, but a direct read of the v2 PDF text (not just its abstract/summary) would be needed to fully confirm the v1 numbers were disavowed rather than merely superseded by new experiments.

---

## PAPER 2 — Filtering Mechanism and Performance Deltas (Both Reported Versions)

### Takeaway
The method combines five membership-inference-attack (MIA) scores plus a temporal-proximity feature into one "MemGuard Composite Score" (MCS) via logistic regression, plus a second signal called Cross-Model Memorization Disagreement (CMMD) that exploits the fact different models have different training cutoffs. The two versions disagree sharply on whether this composite score, once filtered into a trading strategy, actually helps: v1-era reporting shows large improvements (Sharpe 4.11 vs. 2.76, clean-signal returns of 14.48 bps/day vs. 2.13 bps/day for tainted signals); the v2 "Limits of..." framing reports that under symmetric transaction costs, no filter variant improves risk-adjusted performance over the unfiltered ensemble, and simply dropping the single weakest model beats every contamination-based filter.

### Cited Findings
- Composite detection method: "MemGuard Composite Score" (MCS) combines five MIA methods with a temporal-proximity feature via logistic regression; a second method, "CMMD" (Cross-Model Memorization Disagreement), uses divergence in model-reported confidence across models with different training cutoffs — [Google Search snippet of arxiv.org/pdf/2603.26797.pdf]
- Models tested: seven LLMs ranging 124M to 7B parameters (exact names not retrieved) on S&P 100 stocks, 2019–2024 — [alphaXiv](https://www.alphaxiv.org/abs/2603.26797)
- v1/positive-framing numbers (via emergentmind.com summary): Cohen's d = 18.57 for the composite score (d = 0.39–1.37 for individual MIA features alone); in-sample accuracy rises from 40.8% to 52.5% as contamination increases, while out-of-sample accuracy falls from 47% to 42% as contamination increases (i.e., contamination correlates with in-sample overperformance and out-of-sample underperformance — the classic memorization signature); CMMD-filtered Sharpe ratio 4.11 vs. 2.76 unfiltered (a 49% improvement); clean signals average 14.48 bps/day vs. 2.13 bps/day for tainted signals — [emergentmind.com](https://www.emergentmind.com/papers/2603.26797)
- v2/negative-framing numbers (via alphaXiv full-text read): temporal-proximity feature alone achieves ROC-AUC 1.000 for recovering the in-sample/out-of-sample label, which the authors attribute to it being a monotone transform of the label-defining variable itself (i.e., a tautology, not real detection); raw MIA scores reach AUC up to 0.99 at a fixed date but fall to 0.487–0.537 (chance level) under three different within-model normalizations; with transaction costs applied symmetrically, no filtering variant improves risk-adjusted performance over the unfiltered ensemble; no filtering variant attains significant Fama-French five-factor alpha; excluding the single weakest model outperforms every contamination-based filter — [arXiv:2603.26797 via alphaXiv read](https://www.alphaxiv.org/abs/2603.26797)
- The authors frame the (v2) paper explicitly as reporting "negative results... with the failure modes that produced them," and state the work "needs no model modification" — [alphaXiv](https://www.alphaxiv.org/abs/2603.26797)

### Inferences
- Reconciling the two number sets: the most likely explanation is that the AUC=1.000/0.99 "detection" numbers in both framings are the *same underlying measurement* — the v1 framing reported them as evidence the method "works," while the v2 framing re-analyzed those same high AUCs and showed they are artifacts of scale differences between models and of the temporal-proximity feature being definitionally correlated with the label, not genuine memorization detection. The portfolio-performance improvement (Sharpe 4.11 vs 2.76) reported under v1 framing was apparently not replicated once transaction costs were applied symmetrically and a proper within-model normalization was used in v2 — this is the authors retracting their own earlier positive trading claim.
- This paper is best read by our team as a cautionary case study in distinguishing "detector has high AUC" from "detector delivers real portfolio alpha after controlling for confounds and costs" — exactly the trap the authors say they themselves initially fell into.

### Gaps
- The exact five MIA method names (e.g., LOSS attack, Min-K%, zlib-based, perplexity-ratio, neighborhood attack — these are common MIA methods in the broader literature but were not confirmed as the specific five used in this paper) could not be extracted from the available text.
- The seven specific LLM names/sizes (124M–7B range only) were not retrieved.
- It remains unconfirmed whether the 49%-Sharpe-improvement number and the "no filter improves performance" conclusion appeared in genuinely different experimental setups (e.g., different normalization choices) within the same version, or whether they strictly correspond to v1 vs. v2 as inferred above — treat this gap as the single most important follow-up if a future researcher has full-PDF-text access.

---

## PAPER 2 — Direct Applicability to Our Stock-Prediction System

### Takeaway
Regardless of which version's portfolio numbers are correct, the paper's methodological lesson is directly usable: any memorization/contamination filter we might build must be validated with (a) within-model score normalization (not raw cross-model AUC comparisons) and (b) transaction-cost-inclusive, risk-adjusted backtests — because both are exactly the steps whose absence the authors say produced their initially overstated results.

### Inferences (team-specific, not stated by the authors)
- Before building any "memorization filter" into `core/ml_signal_model.py` or `core/segment_reliability.py`, we should budget for an ablation showing the filter still helps after transaction costs and after per-model/per-feature normalization — otherwise we risk reproducing the authors' own retracted v1 result.
- The CMMD idea (cross-model disagreement based on differing training cutoffs) is conceptually appealing for an ensemble/consensus system like ours (we likely already query multiple models) — it is cheap to compute (just compare confidence/LAP-like outputs across models with different known cutoffs) even if this paper's own portfolio-level validation of it is now in doubt per v2.
- Given the author affiliation (IIT Patna, not a well-known quant-finance lab) and the rapid title/conclusion reversal, this should be weighted as a lower-confidence, actively-being-revised source — worth monitoring for a v3, but not worth hard-coding specific performance deltas into our system design docs.

### Gaps
- None beyond those already listed above.

---

## PAPER 3 — Agentic Nowcasting (arXiv 2601.11958) — Authors, Affiliation, Methodology

### Takeaway
"Autonomous Market Intelligence: Agentic AI Nowcasting Predicts Stock Returns" is by Zefeng Chen and Darcy Pu, Guanghua School of Management, Peking University, explicitly labeled "preliminary." It is an arXiv-only q-fin.GN preprint (no journal venue, no citation count found), live/forward-tested from April 2025 through at least January 2026 (~9 months), using an unnamed "leading US-based AI model" accessed through its consumer web-chat interface (not the API) so it could use the model's built-in web search over X/Twitter and financial news sites.

### Cited Findings
- Authors and affiliation: Zefeng Chen and Darcy Pu, Guanghua School of Management, Peking University; paper is labeled "preliminary" — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Submitted January 17, 2026 (08:27:53 UTC), arXiv:2601.11958v1, q-fin.GN — [arXiv abs](https://arxiv.org/abs/2601.11958)
- "Top-ranked" definition: Top-20 stocks by daily "AI attractiveness score" (N=20); ties at the cutoff broken toward larger market cap; positions value-weighted, rebalanced daily, scores collected after the 4:00pm ET close on day t−1, entered at the open on day t, exited at the open on day t+1 — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Agent/model: described only as "a leading US-based AI model," latest version, accessed via its web chat interface (not API) with its built-in online search, covering X/Twitter and financial news sites; the model generates its own search queries and filters sources — no specific model name (GPT, Gemini, Claude, etc.) is disclosed anywhere in the retrieved text — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Universe: Russell 1000 (~93% of US equity market cap) — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Study period: April 2025 through January 2026 (~9 months); exact start/end dates not given in retrieved text — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- API access note (Appendix A.2): at the study's April 2025 start, web search was available only through the web chat interface, not the API (no native web search), which is why the authors used the consumer interface — they argue this better reflects how retail users interact with AI, but acknowledge it means results depend on an un-audited built-in retrieval system — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- No journal venue or citation count found in any search; EconPapers/econpapers.repec.org lists it as a working paper only — [econpapers.repec.org](https://econpapers.repec.org/RePEc:arx:papers:2601.11958)

### Inferences
- The refusal to name the underlying model is a meaningful limitation for reproducibility; a third-party aggregator (synapsesocial.com) claims ">80% accuracy" for the agent, but this is explicitly an unverified third-party claim not found in the paper itself and should not be cited as fact.
- "Live, real-time forward-tested system running since April 2025" (per the assignment brief) is consistent with what was found — this was a genuinely prospective (not backtested) design starting April 2025, which is a meaningfully stronger evidentiary design than a retrospective backtest, assuming the authors' no-look-ahead claims hold.

### Gaps
- The specific underlying LLM (GPT-5/5.1, Gemini 2.x/3, Claude, etc.) is not disclosed in the paper and could not be found via search.
- No citation count was found for this paper (too recent / no tracking system indexed it with a count).

---

## PAPER 3 — Full Performance Table Across All Tiers and Transaction Costs

### Takeaway
Performance is strongly concentrated in the Top-20 tier and decays monotonically with rank; the bottom tier shows no significant negative alpha (the agent cannot reliably identify losers, only winners). Numbers conflict between the paper's own prose and its tables in several places — a conflict the paper itself does not resolve — so both versions are reported below. Transaction costs are small (~1.6 bps/trade, several times less than 10% of gross daily alpha) but no explicit net-of-cost Sharpe/alpha was found.

### Cited Findings
- Headline Top-20 daily alpha: 18.4 bps/day (t = 2.46) per the abstract/main text, but Table 4/Table 5 in the same paper show 33.4 bps/day (t = 2.96) for what is described as the same portfolio — an internal inconsistency not reconciled in the retrieved text — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Top-20 Sharpe ratio: 2.43 in the main text vs. 3.23 in Table 5 (same inconsistency pattern) — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Long-short Sharpe ratio: 1.46 (text) vs. 2.23 (Table 5) — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Other tiers (from figure discussion, not a full tabulated series): Top-10 ≈ 18 bps/day; Top-100 ≈ 12 bps/day; Bottom-20 ≈ −10 to −20 bps/day, not statistically significant; Table 5 separately shows Bottom-20 = −12.9 bps/day — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Multi-horizon Top-20 alphas (Table 5, bps/day): daily 33.4, weekly 23.8, monthly 23.1, quarterly 18.1 — vs. the main text's own separately stated 17, 17, and 12 bps for (apparently) the same three longer horizons — again an unreconciled internal conflict — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Bottom-20 alphas (Table 5, bps/day): weekly 3.5, monthly −3.9, quarterly −9.3 — all statistically insignificant — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Long-short alphas (Table 5, bps/day): daily 46.3, weekly 20.2, monthly 27.0, quarterly 27.4 — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Appendix tables A3/A4 (Top-N / Bottom-N factor regressions, FF6 model): Top-10 daily alpha 0.188% (t=2.21); Top-50 daily alpha 0.158% (t=2.34); Top-100 daily alpha 0.118% (t=2.00); none of the Bottom-N alphas (N=10,50,100) are statistically significant — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Transaction costs (Appendix B.4): baseline uses open-to-open execution; average effective spread for Top-20 is 1.63 bps vs. 1.48 bps for the volume-weighted market; longer-horizon (weekly/monthly/quarterly) Top-20 spreads average 2.00–2.05 bps; closing-auction spreads average ~1.50 bps (slightly tighter than at the open); the authors state costs are "less than 10% of the daily gross alpha"; turnover is ~57.4% daily and ~72.3% weekly — no explicit net-of-cost Sharpe or alpha figure was found in the retrieved text — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Signal noise disclosure: single-query signal reliability (production alignment) has Spearman correlation 0.629, versus 0.902–0.942 for internal/repeated-query reliability measures — i.e., a single live query is considerably noisier than the model's own internal consistency would suggest — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Explanatory hypothesis for the top/bottom asymmetry: positive news is more legible online, while negative news is noisier and more shaped by corporate obfuscation, which the authors argue explains why the agent can identify winners but not losers — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)

### Inferences
- The repeated, unreconciled prose-vs-table numeric conflicts (18.4 vs 33.4 bps/day; Sharpe 2.43 vs 3.23; long-short Sharpe 1.46 vs 2.23) are a genuine data-quality concern with this "preliminary" paper, not a research artifact on our end — both numbers come directly from the same retrieved full-text pass. Any citation of this paper's headline numbers should flag this explicitly and probably default to whichever number is lower (more conservative) until a non-preliminary version resolves it.
- The monotonic decay from Top-10/20 down through Top-100 to insignificant Bottom-N results is the most robust, internally consistent finding (no table-vs-text conflict was found for this pattern), and is the strongest single claim in the paper: the agent's edge is concentrated at the very top of its own ranking and does not extend to shorting predicted losers.

### Gaps
- No full decile-by-decile (10 equal buckets) table was found — only Top-10/20/50/100 and Bottom-20/50/100, which is coarser than a full breadth-of-distribution table.
- No explicit net-of-transaction-cost alpha/Sharpe number was located despite an Appendix B.4 specifically on this topic — the appendix gives cost magnitudes but not a final net figure.
- No citation count or any independent/non-author replication was found.

---

## PAPER 3 — Direct Applicability to Our Stock-Prediction System

### Takeaway
This paper is the most directly actionable of the four for a live, ranking-based LLM stock system: it validates (with real caveats) a design where an LLM with live web search ranks a broad universe daily and only the extreme top tier is traded long, while warns strongly against symmetric long/short use of the same ranking.

### Inferences (team-specific, not stated by the authors)
- If our system (`core/stock_prediction_app.py`, `core/segment_reliability.py`) currently treats "high conviction bearish" calls with the same weight as "high conviction bullish" calls, this paper's finding (negative/bottom-tier predictions carry no significant alpha) argues for asymmetric position sizing or confidence discounting on bearish/short signals specifically, pending our own validation.
- The 0.629 single-query vs. 0.902–0.942 repeated-query Spearman reliability gap is a strong, directly reusable argument for ensembling repeated queries (or multiple models) per ticker-day rather than trusting a single LLM call — this dovetails with whatever consensus/ensemble logic already exists in `core/gemini_stock_prediction_agent.py` and `core/ml_feature_extractor.py`.
- Because the exact underlying model and search sources are undisclosed, we cannot replicate this paper's setup exactly; our own live-search tooling (`core/free_news_service.py`, `core/fmp_calendar_service.py`) would need independent validation of top-tier-only alpha rather than assuming this paper's bps/Sharpe numbers transfer directly.
- Given the unresolved internal numeric conflicts, we should NOT cite "18.4 bps/day, 2.43 Sharpe" as a settled benchmark in any internal spec without flagging that the same paper's own tables show 33.4 bps/day and Sharpe 3.23 for what is presented as the identical portfolio.

### Gaps
- None beyond those noted in the methodology section above.

---

## PAPER 4 — "When Agents Disagree: The Selection Bottleneck" (arXiv 2603.20324) — Authors, Affiliation, and Publication Status

### Takeaway
Authors are Artem Maryanskyy (Uber Technologies, Sunnyvale CA — correspondence author), Dmitry Budnikov (Federal Scientific Agroengineering Center VIM, Moscow, Russia), and Alibek T. Kaliyev (Dept. of Computer Science, University of Texas at Austin). Notably, v1 of the arXiv preprint listed Maryanskyy as sole author; Budnikov and Kaliyev were added by v2 (July 21, 2026). It is an arXiv preprint (cs.MA) with 7 citations and 84 views per alphaXiv as of the research date; a claim that it was "Published in Applied Sciences (MDPI)" surfaced from one source could not be corroborated and is likely incorrect — treat the paper as arXiv-only/unpublished pending further verification.

### Cited Findings
- Authors and affiliations: Artem Maryanskyy (Uber Technologies, Sunnyvale, CA); Dmitry Budnikov (Federal Scientific Agroengineering Center VIM, Laboratories of Electrical, Thermal Technologies and Energy Saving — location given as Moscow, Russia, by the arXiv HTML read though not independently corroborated by the alphaXiv read); Alibek T. Kaliyev (Dept. of Computer Science, University of Texas at Austin) — [arXiv:2603.20324](https://arxiv.org/html/2603.20324)
- v1 (submitted March 20, 2026) listed Maryanskyy as sole author; the current v2 (revised July 21, 2026) added Budnikov and Kaliyev as co-authors — [arXiv:2603.20324](https://arxiv.org/html/2603.20324)
- arXiv primary category: cs.MA (Multiagent Systems) — [alphaXiv](https://www.alphaxiv.org/abs/2603.20324)
- alphaXiv lists 7 citations and 84 views for this paper (alphaXiv's own count, which "may not match other databases") — [alphaXiv](https://www.alphaxiv.org/abs/2603.20324)
- A conflicting claim (from one arXiv-HTML-based read) stated the paper was "Published in Applied Sciences (MDPI), 2026, with DOI 10.3390/app1010000" — a follow-up targeted web search for this exact author/venue combination found no corroborating result, and a second independent source read (alphaXiv) explicitly states the page "doesn't mention peer review, journal publication, or MDPI" and that a NeurIPS-2026 link on the page is just site navigation, not an acceptance notice — [WebSearch: no results]; [alphaXiv](https://www.alphaxiv.org/abs/2603.20324)

### Inferences
- The Applied Sciences/MDPI publication claim should be treated as unverified and probably a fetch-model hallucination (the DOI format "10.3390/app1010000" does not match MDPI's real article-numbering convention, and an explicit search for the author names plus "Applied Sciences" returned zero matching results). **Our team should treat this paper as an arXiv-only preprint, not peer-reviewed**, pending any future direct confirmation.
- The sole-author-to-three-author expansion between v1 and v2, alongside the retitling pattern seen in Papers 1 and 2 above, is a recurring pattern across this whole batch of very-recent papers: several are visibly still being actively revised (author lists changing, titles changing, framing flipping) rather than being finished, stable, peer-reviewed artifacts. This should inform how much weight the team puts on any single number from this batch.

### Gaps
- Could not independently confirm the VIM institute's location (Moscow) via a second source.
- Could not resolve the Applied Sciences/MDPI discrepancy with full certainty — it is more likely false than true given the evidence, but a direct MDPI site search was not performed due to tool-call budget.

---

## PAPER 4 — The 42 Tasks, Judge Mechanism, and Every Reported Number

### Takeaway
The 42 tasks (6 per category × 7 categories: Coding, Creative Extended, Ethics & Policy, Math & Logic, Reasoning, Science, Summarization) are entirely general-purpose reasoning/writing/coding tasks — none are finance-, trading-, or stock-prediction-related, which materially limits direct transfer to a stock-direction-consensus system. Judge-based selection used a three-model panel (Claude Sonnet, GPT-5-mini, DeepSeek-V3p2) doing randomized-order pairwise comparisons scored with Bradley-Terry, at judge temperature 0.1. The headline numbers (0.810 diverse+judge vs. 0.496 diverse+vote vs. 0.512 homogeneous+judge) are all confirmed, along with a closed-form "selection bottleneck" threshold formula and extensive significance testing; a cost multiplier (judge selection ≈2.5x the cheapest cell's cost; voting ≈1.9x) is disclosed, but no latency or raw token-count figures are given.

### Cited Findings
- 42 tasks = 6 tasks × 7 categories: Coding (streaming pipeline design, race condition debugging, multi-tenant architecture, security/performance code review, API migration, flaky test stabilization); Creative Extended (polyphonic narrative, epistolary fiction, memory-themed poetry cycle, worldbuilding charter, courtroom dialogue, myth retelling); Ethics & Policy (facial recognition policy, AI tutor data ethics, autonomous weapons export, organ allocation, ventilator triage, carbon border adjustment); Math & Logic (probability paradox, integer optimization, logic grid puzzles, Bayesian diagnostics, scheduling with dependencies, game-theoretic resource division); Reasoning (causal policy analysis, counterfactual outbreak response, argument evaluation, root cause analysis, strategic negotiation, uncertainty assessment); Science (heat dome mechanisms, memory consolidation, adaptive clinical trials, battery degradation, ecosystem restoration, epidemiological modeling); Summarization (board packet crisis brief, incident timeline, expert panel comparison, customer feedback synthesis, multi-opinion legal summary, policy roundtable digest). **None of the 42 tasks are finance, trading, or stock-prediction tasks.** — [arXiv:2603.20324](https://arxiv.org/html/2603.20324)
- Judge mechanism: a three-model judge panel — Claude Sonnet, GPT-5-mini, DeepSeek-V3p2 — reads all candidate outputs and selects the best via randomized-order pairwise comparisons scored with the Bradley-Terry model; judge temperature = 0.1; exact prompt text is not in the paper body (paper states it's in a linked GitHub repo, which was not independently accessed) — [arXiv:2603.20324](https://arxiv.org/html/2603.20324)
- Headline Bradley-Terry win rates vs. a single-Opus baseline: diverse team + judge selection = 0.810 [95% CI 0.768, 0.851]; diverse team + majority vote = 0.496 [0.425, 0.563]; homogeneous Opus×3 + judge = 0.512 [0.500, 0.530]; diverse team + MoA-style synthesis = 0.179 [0.127, 0.234]; an exploratory "diverse_mixed" + judge arm = 0.929 [0.887, 0.964] — [arXiv:2603.20324](https://arxiv.org/html/2603.20324)
- Closed-form selection-bottleneck threshold: under linear model Q(T,s) = s·O(T) + (1−s)·M(T) (O = team oracle quality, M = team mean quality), crossover point s* = (μ_best − M(T_d)) / (O(T_d) − M(T_d)); pilot Monte-Carlo calibration gives s* ≈ 0.567 [bootstrap 95% CI 0.48, 0.65] — [arXiv:2603.20324](https://arxiv.org/html/2603.20324)
- Significance tests (Holm-Bonferroni adjusted where noted): diversity effect (judge vs. homogeneous) Δ = +0.298 [0.250, 0.345], Hedges' g = 2.71, p = 7.55×10⁻¹⁵ (adjusted p < 2×10⁻¹⁴); judge vs. vote Δ = +0.313 [0.232, 0.397], g = 1.61, p = 1.06×10⁻¹⁰ (adjusted p < 2×10⁻¹⁰); selection vs. synthesis Δ = +0.631 [0.562, 0.696], g = 3.86 [3.14, 4.58], p = 1.29×10⁻¹⁵ (adjusted p < 4×10⁻¹⁵); vote vs. homogeneous Δ = −0.016, p = 0.669 (i.e., majority voting across diverse models is statistically indistinguishable from a single model — directly matching the assignment brief's framing); diverse_mixed vs. diverse_strong (exploratory, uncorrected) Δ = +0.119 [0.060, 0.179], g = 0.87 [0.42, 1.32], p = 1.18×10⁻⁴ — [arXiv:2603.20324](https://arxiv.org/html/2603.20324)
- Per-task robustness: 38 of 42 tasks favor diversity with no reversals; sign-test p ≈ 3.6×10⁻¹² (ties excluded) — [arXiv:2603.20324](https://arxiv.org/html/2603.20324)
- Regression fit: OLS R² = 0.740, F(4,205) = 172.6, p = 1.88×10⁻⁶⁴ — [arXiv:2603.20324](https://arxiv.org/html/2603.20324)
- Decoupled-evaluation robustness check: Spearman ρ = 0.90 across cell rankings using an independent judge — but that independent judge (GPT-4o-mini) was reported as "degenerate" with 99.6% ties, so this robustness check effectively rests on only two usable judges, not a fully independent third — [arXiv:2603.20324](https://arxiv.org/html/2603.20324)
- Cost disclosure: relative cost normalized to the cheapest cell — diverse_strong+judge ≈ 2.5×, diverse_strong+vote ≈ 1.9×, diverse_mixed+judge ≈ 1.0×; the paper states judge selection needs "no additional training or infrastructure, only a structured evaluation prompt," but gives no raw token counts, no latency numbers, and no absolute dollar costs — [arXiv:2603.20324](https://arxiv.org/html/2603.20324)
- Design/limitations disclosed by authors: five-cell targeted design (not full factorial, so not all interactions estimated); baseline is a single Opus call rather than the strongest individual model in the diverse pool; only one generation temperature (T=0.7) tested; LLM-as-judge is only a proxy for human judgment, with no human evaluation performed; same-family concern — Claude Sonnet is both a judge and (in some cells) a synthesizer, while the generation pool includes Claude Opus, raising self-evaluation/family-overlap concerns; single-round pipeline only (no iterative/multi-round topologies tested); the "weak-model" finding is exploratory/not pre-registered with uncorrected p-values and a confounded diverse_mixed arm — [arXiv:2603.20324](https://arxiv.org/html/2603.20324)

### Inferences
- Because all 42 tasks are general reasoning/coding/writing/ethics/science tasks with zero finance or quantitative-forecasting content, this paper's numbers (0.810 vs. 0.496/0.512) should be read as suggestive, not as a validated result for a stock-direction-prediction consensus system. Financial-forecasting tasks have ground truth that is probabilistic/noisy and resolved only after the fact (unlike most of these 42 tasks, which likely have identifiable "better" answers that a judge panel can assess immediately) — this is a structural difference the paper does not address and that our team must bridge via its own validation, not by direct transfer of these win-rate numbers.
- The core, best-supported takeaway that *does* plausibly generalize is the mechanism, not the magnitude: judge-based selection exploits the single best candidate among diverse outputs ("oracle" quality), while majority voting averages toward the mean and can even wash out a correct minority view — this logic is model-agnostic and task-agnostic in principle, which is why the authors frame it as a general "selection bottleneck" rather than a task-specific result.
- The same-family judge/generator overlap (Claude Sonnet judging outputs that include Claude Opus) is a genuine internal-validity concern the authors acknowledge; if our team builds a judge-based selector using the same model family as one of our generating/forecasting models, we should expect a similar self-evaluation-bias risk and should prefer a judge model from a different family/vendor than any of the forecasting models being judged.

### Gaps
- No finance-specific validation of the selection-bottleneck mechanism exists in this paper or (as far as this research found) anywhere else yet — this is the single biggest gap for direct applicability.
- No raw latency (wall-clock) or token-count numbers were disclosed for judge-based selection vs. voting, only relative dollar-cost multipliers — so our team cannot yet budget exact added latency for a production judge-selection step from this source alone.
- The true peer-review/publication status (arXiv-only vs. a disputed Applied Sciences/MDPI claim) remains not fully resolved, as noted in the Authors/Status section above.

---

## PAPER 4 — Direct Applicability to Our Stock-Prediction System

### Takeaway
Of all four, this paper's mechanism is the most directly transferable idea to a multi-model stock-prediction consensus system — but the lack of any finance task in its own evaluation, and the open same-family judge-bias concern, mean the team should pilot judge-based selection on our own held-out stock calls before trusting the 0.810-vs-0.5 magnitude.

### Inferences (team-specific, not stated by the authors)
- If our system currently aggregates multiple model outputs by majority vote or simple averaging (plausible given `core/ml_signal_model.py`, `core/segment_reliability.py`, `core/calibration_profile_builder.py` naming), this paper's strongest, most statistically robust finding — that majority voting across diverse models is statistically equivalent to a single model (Δ = −0.016, p = 0.669) — is a direct argument for replacing or supplementing vote-based aggregation with a judge-based selector for our own ticker-level consensus step.
- Given the paper's own same-family-bias caveat, if we build a judge, it should be a model from a different vendor/family than whichever models generate our stock-direction forecasts (e.g., if forecasts come from a Gemini-family model per `core/gemini_stock_prediction_agent.py`, the judge should be a non-Gemini model, or vice versa).
- Because financial outcomes resolve with a time delay and are probabilistic (unlike the 42 immediately-gradable tasks tested), a stock-forecasting judge would need a different evaluation basis than "does this read like the better reasoning" — e.g., scoring candidate forecasts by calibration/historical track record on similar setups rather than by a judge's immediate qualitative read. This is a necessary adaptation the paper does not address, since it never tests a domain with delayed, stochastic ground truth.
- The ~2.5x relative cost of judge-based selection (vs. ~1.0x cheapest baseline) is a tractable overhead for a trading signal system (where even modest alpha justifies extra inference cost) — more tractable than it might be in a cost-sensitive consumer application — supporting a recommendation to pilot judge-based selection in our pipeline despite the added API cost.

### Gaps
- None beyond those already listed in the methodology section above.

---

## Cross-Paper Synthesis Note (meta-observation across all four)

### Takeaway
All four papers are extremely recent (initial submission Dec 2025–Mar 2026), arXiv-first, and showing visible signs of active, ongoing revision (changing titles, changing author lists, and in MemGuard-Alpha's case a flipped headline conclusion) — none is peer-reviewed as confirmed by this research, and independent citation counts are negligible to small (0–7) given their age. This pattern should directly shape how much confidence our team places in any single number from this batch.

### Cited Findings
- Paper 1 (2512.23847): retitled between v1 and v2; EconPapers citation count 4 — [EconPapers](https://econpapers.repec.org/RePEc:arx:papers:2512.23847)
- Paper 2 (2603.26797): retitled between v1 and v2, with an apparent reversal of the headline trading-performance conclusion — [Google Search]; [alphaXiv](https://www.alphaxiv.org/abs/2603.26797)
- Paper 3 (2601.11958): explicitly self-labeled "preliminary," with internal prose-vs-table numeric inconsistencies on its own headline statistics — [arXiv:2601.11958](https://arxiv.org/html/2601.11958)
- Paper 4 (2603.20324): author list expanded from 1 to 3 between v1 and v2; publication-venue claim (MDPI Applied Sciences) found in one source but not corroborated by a second, independent source — [arXiv:2603.20324](https://arxiv.org/html/2603.20324); [alphaXiv](https://www.alphaxiv.org/abs/2603.20324)

### Inferences
- None of these four should be treated as "settled science" for production decisions. The actionable mechanisms (LAP-style leakage probes, within-model-normalized + cost-inclusive filter validation, top-tier-only long signals with asymmetric treatment of bearish calls, judge-based selection over voting) are all worth piloting internally, but the specific magnitudes (exact bps, exact Sharpe ratios, exact win-rate percentages) should not be hard-coded into our system's documentation or success criteria without our own replication.

### Gaps
- A follow-up check in 3–6 months (per EconPapers/alphaXiv citation trackers) would clarify whether any of these four papers stabilizes into a peer-reviewed, non-conflicting final version.
