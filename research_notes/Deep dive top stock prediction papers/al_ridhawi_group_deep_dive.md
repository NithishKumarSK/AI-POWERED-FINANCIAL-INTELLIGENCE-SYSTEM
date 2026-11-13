# Deep Dive: Al Ridhawi / Haj Ali / Al Osman (University of Ottawa) — IEEE Access (65% DA) and Applied Intelligence preprint (72% DA)

## Who are the authors, their affiliations, and prior publication history in this area?

### Takeaway
Both papers share the identical three-author team — Mohammad Al Ridhawi (first/corresponding author), Mahtab Haj Ali, and Hussein Al Osman — all affiliated with the School of Electrical Engineering and Computer Science (EECS), University of Ottawa, Canada. Al Osman is an established Associate Professor whose entire prior research record is in affective computing, multimedia systems, and HCI — not finance or NLP for markets — strongly suggesting this is a side project/student-led effort (the preprint's acknowledgment thanks him only for "mentorship and feedback," phrasing typical of a student-first-author relationship) rather than a continuation of the group's core research program. No independent public profile, CV, or prior publication record could be found for Mohammad Al Ridhawi or Mahtab Haj Ali outside these two papers.

### Cited Findings
- Both arXiv abstract pages list the same three authors: Mohammad Al Ridhawi, Mahtab Haj Ali, Hussein Al Osman — [arXiv:2603.05917](https://arxiv.org/abs/2603.05917); [arXiv:2603.19136](https://arxiv.org/abs/2603.19136)
- The IEEE Access published version (Crossref metadata) confirms affiliation for all three authors as "School of Electrical Engineering and Computer Science, University of Ottawa, Ottawa, ON, Canada," with ORCIDs: Al Ridhawi 0009-0009-3549-8842, Haj Ali 0009-0005-7359-9063, Al Osman 0000-0002-7189-5644 — [Crossref DOI 10.1109/ACCESS.2026.3691980](https://api.crossref.org/works/10.1109%2FACCESS.2026.3691980)
- The full-text HTML of the IEEE Access paper lists only one author email: malri039@uottawa.ca (Mohammad Al Ridhawi), a University of Ottawa student-style email address — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- The preprint's acknowledgment section states: "The first author thanks Dr. Hussein Al Osman for mentorship and feedback" — no funding statement is given — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Hussein Al Osman is a Professor/Associate Professor at the University of Ottawa's Faculty of Engineering, completed his BSc, MSc, and PhD all at the University of Ottawa, and leads the Multimedia Processing and Interaction Group; his listed research interests are affective computing, human-computer interaction, serious gaming, and multimedia systems — [uOttawa faculty directory](https://www.uottawa.ca/faculty-engineering/school-electrical-engineering-computer-science/directory/hussein-al-osman)
- A third-party academic-profile aggregator (csauthors.net / a Google Scholar mirror) lists Al Osman with roughly 71 papers (2008–2025), ~1,698 citations, and an h-index of 21 — [web search result citing csauthors.net and a Google Scholar mirror](https://www.csauthors.net/hussein-al-osman) — none of these prior papers, per the search summary, relate to stock prediction, time-series forecasting, or financial NLP; his body of work is in affective computing/multimedia/HCI.
- Both the IEEE Access full text and the preprint full text list only Reference list entries for this one line of work; the preprint self-cites the IEEE Access paper as reference [5], described there as "submitted to IEEE Access, under review" — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Targeted web searches for "Mohammad Al Ridhawi" + uottawa and "Mahtab Haj Ali" + University of Ottawa returned no matching personal pages, LinkedIn profiles, or prior publications — only unrelated namesakes (e.g., a UNHCR refugee-resettlement story about an unrelated "Mohammed Al Karad") — [web search: "Mohammad Al Ridhawi" uottawa](https://unhcr.org/node/18686); [web search: "Mahtab Haj Ali" University of Ottawa](https://www.uottawa.ca/faculte-sciences/professeurs/ali-karimnezhad)
- A Semantic Scholar API query for "Al Ridhawi stock market prediction" returned HTTP 429 (rate-limited) and could not be completed; a general web search for the two surnames together surfaced only the one arXiv/RePEc listing of the IEEE Access paper itself, with no citation count returned — [web search: "Al Ridhawi" "Al Osman" stock prediction citations](https://ideas.repec.org/p/arx/papers/2603.05917.html)

### Inferences
- The pattern (single student email listed, "mentorship" framing, Al Osman's unrelated core research area, no prior co-authored work in finance/NLP by any of the three) strongly suggests this is a graduate or senior-undergraduate student project (Al Ridhawi, likely with Haj Ali as a second student collaborator) supervised informally or formally by Al Osman, rather than output of an established "stock prediction lab." This matters for assessing credibility: the team has no track record in financial ML specifically, and the IEEE Access paper itself is framed by the authors as "integration of existing components rather than a new learning primitive" and "a proof of concept" — their own words, not ours (see next section).
- The complete absence of any findable public profile for Al Ridhawi or Haj Ali (no Google Scholar page, no LinkedIn, no departmental bio) is consistent with early-career/student status but could not be independently confirmed.

### Gaps
- Could not confirm Mohammad Al Ridhawi's or Mahtab Haj Ali's degree program (MASc/PhD/undergrad), year of study, or whether either has defended or published a thesis on this topic — no departmental thesis listing or LinkedIn profile was found.
- Could not verify any prior publication history for Al Ridhawi or Haj Ali in stock prediction, time-series forecasting, or NLP — searches found none, but this is an absence-of-evidence finding, not a confirmed "zero prior publications."
- Semantic Scholar API was rate-limited (HTTP 429); a full citation-network check for Al Osman's complete bibliography (to rule out any earlier finance-adjacent work) was not completed.

---

## Published paper (IEEE Access, 65% directional accuracy): full methodology, metrics, and venue reputation

### Takeaway
"Stock Market Prediction Using Node Transformer Architecture Integrated With BERT Sentiment Analysis" (arXiv:2603.05917; IEEE Access vol. 14, pp. 72613–72631, DOI 10.1109/ACCESS.2026.3691980) combines a graph/node-transformer over 20 S&P 500 stocks with a fine-tuned BERT sentiment module, fused via volatility-gated attention; it reports 0.80% 1-day MAPE and 65% 1-day directional accuracy (95% CI [63.2, 66.8]) against a chronological 1982–2010/2011–2016/2017–2025 split, with the full metrics table, ablations, and an unusually candid limitations section (survivorship bias explicitly flagged as "the most consequential concern"). IEEE Access is a broad-scope, gold-open-access IEEE "megajournal" with a moderate impact factor (~3.6, 2024 JCR) and a binary (not multi-round) review model; sources disagree sharply on its acceptance rate (20%–50% depending on source), and it is sometimes informally characterized as "pay to publish" — a mischaracterization of its APC-funded gold-OA model, but one reflecting real community concern about its combination of very high volume and comparatively rapid (4–6 week) review relative to IEEE Transactions journals.

### Cited Findings
**Authors/venue/dates:**
- arXiv:2603.05917 v1 submitted 6 Mar 2026; v2 3 Apr 2026; v3 (current) 14 May 2026 — [arXiv abstract page](https://arxiv.org/abs/2603.05917)
- Journal reference: IEEE Access, vol. 14, pp. 72613–72631, 2026; DOI 10.1109/ACCESS.2026.3691980 — [arXiv abstract page](https://arxiv.org/abs/2603.05917); confirmed independently via Crossref, created 2026-05-12, deposited 2026-05-19 — [Crossref metadata](https://api.crossref.org/works/10.1109%2FACCESS.2026.3691980)

**Architecture:**
- Models 20 stocks as a fully-connected graph (N=20 nodes) with a learnable N×N edge-weight matrix, initialized as e_ij = α·δ_sector + (1−α)·max(0, ρ_ij) (α=0.5, δ_sector = shared GICS sector indicator, ρ_ij = Pearson correlation of training-period returns) — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- "Node Transformer": graph-aware multi-head self-attention with causal masking, edge matrix E added as a structural bias: softmax(QKᵀ/√d_k + M + E)V; 8 heads, d_k=d_v=64, d_model=512, 6 layers, feed-forward 512→2048→512, dropout 0.1, residual + layer norm — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- BERT module: bert-base-uncased (12 layers/768 hidden/12 heads) fine-tuned in 3 progressive-unfreezing stages (3 epochs top layers, 5 epochs gradual unfreeze, full fine-tune at lower LR), with focal loss (γ=2) and a 3-class (neg/neutral/pos) head producing sentiment score s = p_pos − p_neg ∈ [−1,1]; BERT is frozen during the forecasting stage — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Sentiment fused via: multi-scale (1/5/20-day) EMA of sentiment; sentiment-guided attention keys K′=K·(1+β·S_t); an adaptive sigmoid gate α_t (from rolling volatility + mean |sentiment|) blending ŷ = α_t·ŷ_node + (1−α_t)·ŷ_sent — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Proposed model ≈21.3M parameters vs. ~4.2M (Simple Transformer), ~1.1M (BERT+LSTM, excluding frozen BERT), ~0.5M (LSTM) — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Combined loss: ℒ = λ1·MSE + λ2·Directional-BCE + λ3·(1−Pearson correlation) + λ4·L2, with λ1=1.0, λ2=0.5, λ3=0.2, λ4=1e-4 — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)

**Data:**
- "Financial Market Dataset (FMD)": 20 S&P 500 stocks (AAPL, MSFT, CRM, NFLX, JPM, V, JNJ, UNH, PFE, WMT, HD, MCD, XOM, CVX, PG, KO, NKE, VZ, BA, CAT), Jan 1, 1982 – Mar 31, 2025, OHLCV + 11 technical indicators = 17-dim feature vector/stock-day; ~10,300 trading days, ~206,000 observations — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Sentiment: "Market Sentiment Evaluation" dataset (public, expert-annotated) for BERT fine-tuning; "Comprehensive Stock Sentiment" dataset — ~4.2 million X/Twitter posts via cashtags, Jan 2007–Mar 2025 (sentiment set to zero pre-2007) — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Chronological split: Train 1982–2010 (stated 70%), Validation 2011–2016 (stated 15%), Test 2017–Mar 2025 (stated 15%); the WebFetch summary flags that these stated percentages are inconsistent with actual year-spans — the ~8.25-year test window is closer to ~19% of the 1982–2025 range than the stated 15% — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917) (internal inconsistency noted by the fetch tool's close reading of the paper's own numbers)
- Imputation/normalization: linear interpolation for 1–2 day training gaps, forward-fill only for val/test; expanding-window z-score computed on training data only, applied frozen to val/test — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)

**Full metrics tables (1-day horizon, test period 2017–2025):**

| Model | MAPE (%) | Directional Accuracy (%) | 95% CI (DA) |
|---|---|---|---|
| Naïve Random Walk | 1.35 | — | — |
| ARIMA | 1.20 | 55.0 | [53.2, 56.8] |
| VAR | 1.15 | 56.0 | [54.2, 57.8] |
| Random Forest | 1.10 | 57.0 | [55.2, 58.8] |
| SVR | 1.05 | — | — |
| LSTM | 1.00 | 58.0 | [56.2, 59.8] |
| XGBoost | 0.95 | 60.0 | [58.2, 61.8] |
| Simple Transformer | 0.90 | 62.0 | [60.2, 63.8] |
| BERT + LSTM | 0.88 | 63.0 | [61.2, 64.8] |
| **Proposed (Integrated NF-BERT)** | **0.80** | **65.0** | **[63.2, 66.8]** |
— [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)

- Also reported: 5-day MAPE 1.80%, 20-day MAPE 2.80% (proposed, vs. 3.80%/5.80% random walk); Theil's U 0.59 (proposed) vs. 1.00 (random walk); MAE (return-based) 0.81% 1-day / 1.82% 5-day / 2.85% 20-day — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Sharpe ratio IS reported for this paper (in Section V-E7, outside the first 100k characters fetched): net Sharpe 0.84, gross Sharpe 1.35 — [arXiv HTML 2603.05917, offset fetch](https://arxiv.org/html/2603.05917)
- Sentiment classifier performance (precision/recall/F1 on the MSE test set): Negative P=0.83/R=0.80/F1=0.81; Neutral P=0.89/R=0.92/F1=0.90; Positive P=0.85/R=0.82/F1=0.83; macro avg P=0.86/R=0.85/F1=0.85; overall accuracy 0.87; Cohen's κ=0.79 — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Ablations (1-day MAPE): Full 0.80%; w/o sentiment 0.88% (+10.0%); w/o graph structure 0.92% (+15.0%); w/o temporal encoding 0.95% (+18.8%); w/o feature gating 0.84% (+5.0%); price-only 1.02% (+27.5%) — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Volatility regimes: proposed MAPE rises from ~0.70% (low vol) to 1.50% (high vol) vs. 1.60–2.10% for baselines in high vol — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Paired t-tests reported p<0.05 for all comparisons — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)

**Stated limitations (Section VI-C, the authors' own words/paraphrase):**
- "The most consequential concern is survivorship bias in stock selection" — current S&P 500 constituents only, reported performance "likely inflated" — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Single fixed temporal split (no rolling/walk-forward retraining) explicitly acknowledged as a limitation — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Backtest uses a flat 10bp transaction cost, ignoring market impact/slippage; with 32% daily turnover, net returns are described by the authors as "an upper bound" — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Sentiment fusion trained on only ~4 years of sentiment-labeled data (2007–2010 overlap with training window); 10% error-reduction figure explicitly called a "lower bound" by the authors — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- ~18 hours training time per run on an A100 GPU, flagged by authors as a barrier to real-time use — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Same 20 stocks used for development and evaluation (external validity concern), and non-stationary correlations (edge weights initialized on 1982–2010 data may not hold by 2017–2025) — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- The authors explicitly frame the work as "preliminary evidence" and describe it as "integration of existing components rather than a new learning primitive" / "a proof of concept" — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)

**IEEE Access venue reputation:**
- IEEE Access's own page states a 27% average acceptance rate; third-party sources disagree, citing figures from ~20% to ~50%, with one commercial author-services site citing 40–45% — [web search summary of ieeeaccess.ieee.org and manusights.com guides](https://ieeeaccess.ieee.org/about/)
- Impact factor reported as 3.6 (2024 JCR, Q2, ranked 128/366 in Electrical & Electronic Engineering); one source cites 4.2 (2025) and another 3.4, indicating year-to-year/source variance — [web search summary](https://manusights.com/blog/ieee-access-impact-factor)
- Article processing charge (gold open access, pay-on-acceptance, not pay-on-submission): ~$1,995–$2,160 depending on year/source — [web search summary](https://manusights.com/blog/ieee-access-submission-process)
- Review model: binary (single round, not iterative Transactions-style multi-round peer review); IEEE states 4–6 weeks submission-to-publication, much faster than a typical IEEE Transactions journal (3–12 months) — [web search summary](https://ieeeaccess.ieee.org/about/)
- One source explicitly argues the "pay to publish" label conflates the APC gold-OA funding model (used by every gold-OA journal) with genuine quality concerns, but notes the real critique is "the combination of high volume, a binary review model, and a relatively high acceptance rate" — [web search summary citing manusights.com](https://manusights.com/blog/ieee-access-acceptance-rate)

### Inferences
- IEEE Access is best characterized as a moderate-rigor, high-volume, gold-OA "megajournal" — not a top-tier, highly selective finance/ML venue (compare: it is not NeurIPS, ICML, Journal of Finance, or even a highly selective IEEE Transactions journal). A 65% headline DA from this venue should be read as having undergone a single binary round of peer review rather than the sustained, multi-round scrutiny of a top ML or finance journal. This context matters directly for the "why does the preprint report higher accuracy" question below: IEEE Access's faster, less adversarial review process is less likely to have forced rigorous walk-forward/robustness revisions than a more demanding target venue would.
- The authors' own admission that the 70/15/15 split percentages don't match the literal year spans (train 29 years / val 6 years / test ~8.25 years out of ~43 years total — val years ≈14%, test years ≈19%, not 15%/15%) suggests either (a) "70/15/15" refers to weighted-by-trading-days-with-full-feature-availability rather than raw calendar span, or (b) a labeling imprecision in the paper. This was not resolved in the available text and should be flagged to the team as a documentation ambiguity, not a proven error.
- The paper's own Limitations section is unusually forthright for this literature (explicit survivorship-bias admission, explicit "upper bound" framing on both sentiment lift and net returns, explicit single-split limitation) — this candor is itself notable and should be weighed positively relative to the field's norm in both papers under review.

### Gaps
- Could not confirm from the fetched text whether precision/recall/F1 are reported for the directional-accuracy classification task itself (price up/down), as opposed to the 3-class sentiment classifier (which IS reported in detail). Only MAPE/DA/Theil's U/MAE/Sharpe appear to be the reported forecast-quality metrics.
- Could not retrieve the full reference list cross-checked against the published IEEE Access version beyond what Crossref returned (DOI-only entries without full bibliographic text for ~20 of 32 references).
- No specific reviewer comments, post-publication critiques, or replication attempts were found (see dedicated section below) — the paper was published only ~6 months before this research (May 2026 vs. November 2026), which likely explains the thin citation/commentary trail to date.

---

## Preprint (AE-NodeFormer+SAC, 72% directional accuracy): architecture, leakage controls, and peer-review status

### Takeaway
"Adaptive Regime-Aware Stock Price Prediction Using Autoencoder-Gated Dual Node Transformers with Reinforcement Learning Control" (arXiv:2603.19136, v2 dated 2 Apr 2026) extends the IEEE Access architecture with (1) an autoencoder-based regime detector that routes each trading day to one of two specialized NodeFormer pathways (stable vs. event-driven) based on reconstruction error, and (2) a Soft Actor-Critic (SAC) reinforcement-learning controller that tunes the regime threshold τ and the pathway-blending weight α — explicitly as a meta-controller, not a trading agent. It reports 0.59% 1-day MAPE and 72% 1-day directional accuracy on the same 20-stock, 1982–2025 universe as the IEEE Access paper, with substantially more thorough disclosed leakage controls (frozen normalization statistics, causal masking, training-only edge priors, forward-fill-only imputation in val/test). As of this research (Nov 2026), it remains preprint-only — v1 (19 Mar 2026) and v2 (2 Apr 2026), no v3, no journal reference, comments field reads only "Submitted to Applied Intelligence (Springer)" with no indication of acceptance, review outcome, or desk rejection.

### Cited Findings
**Submission/venue status:**
- arXiv:2603.19136: v1 submitted 19 Mar 2026 (16:55:33 UTC); v2 submitted 2 Apr 2026 (06:40:40 UTC); no v3 exists as of this research — [arXiv abstract page, directly verified](https://arxiv.org/abs/2603.19136)
- Comments field on the arXiv abstract page reads exactly: "Submitted to Applied Intelligence (Springer). 17 pages, 9 figures, 10 tables" — no journal-ref field is populated — [arXiv abstract page, directly quoted](https://arxiv.org/abs/2603.19136)
- Note on a conflicting signal: one AI-generated web-search summary (not a primary source) claimed the arXiv abstract page said the paper was submitted to "IEEE Transactions on Computational Social Systems" rather than Applied Intelligence; this was directly checked against the actual arXiv abstract page text and found to be false — the only venue named anywhere on the primary page is Applied Intelligence (Springer). This is flagged explicitly because it is exactly the kind of secondary-source error the team should discount — [arXiv abstract page, direct verification](https://arxiv.org/abs/2603.19136) vs. [web search summary containing the erroneous claim](https://arxiv.deeppaper.ai/papers/2603.19136v1)
- Authors/affiliation identical to the IEEE Access paper: Mohammad Al Ridhawi, Mahtab Haj Ali, Hussein Al Osman, School of EECS, University of Ottawa; only Al Ridhawi's email (malri039@uottawa.ca) is listed — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- The preprint self-cites the IEEE Access paper (reference [5]) as "submitted to IEEE Access, under review" — meaning this preprint's v1/v2 text was written/last-touched before (or without updating for) the sibling paper's formal acceptance — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)

**Architecture (AE-NodeFormer):**
- Autoencoder "regime detector": encoder with hidden layers of 64/32 units, latent dim 32, ReLU; trained with Adam (lr=1e-3, batch 64, ≤20 epochs, early stopping) only on "stable" days (VIX below the training-period 75th percentile); reconstruction error = anomaly/regime score — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Router: days with reconstruction error ≥ threshold τ (initialized at the 95th percentile of training reconstruction errors) go to the "event" pathway, others to "normal"; router features = 5-/20-day rolling volatility, ΔVIX, change in average pairwise correlation, |sentiment|, and X-post crisis-keyword velocity — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Two parallel NodeFormer pathways ("Normal" and "Event"), architecturally identical to the IEEE Access node-transformer (6 layers, 8 heads, d_model=512, FFN=2048, dropout 0.1, causal masking, same sector+correlation edge-weight initialization), except the Event pathway's input is widened with a 12-dim context vector (4-dim regime embedding, 2-dim sentiment spike, 4-dim earnings-event features, 2-dim cross-asset error mean/std) — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Blending: ŷ = α·y_normal + (1−α)·y_event — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)

**SAC controller:**
- Explicitly a meta-controller over τ and α, not a trading-decision agent — state = current reconstruction error, 5-day error history, volatility, previous-day RMSE/DA, previous α/τ; action = [Δτ, Δα] each clipped to [−0.1, 0.1]; reward r = −RMSE − 0.5(1−DA) − 0.1|Δτ| — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Actor + twin critics, each 2×256-unit layers; lr 3e-4, soft update 0.005, replay buffer 1e5, automatic entropy tuning, 50 epochs × 1,000 steps — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- At inference, ALL weights including the SAC policy are frozen — the authors state this explicitly and position it against HMM/Markov-switching routing as alternatives — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- 4-stage training pipeline: (1) autoencoder on stable data, 20 epochs; (2) both NodeFormers, 60 epochs; (3) SAC with frozen predictors, 50 epochs; (4) end-to-end fine-tune at reduced LR, 20 epochs — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)

**Dataset — confirms it is the SAME 20 stocks and same date range as the IEEE Access paper:**
- AAPL, MSFT, CRM, JPM, V, JNJ, UNH, PFE, WMT, HD, XOM, CVX, PG, KO, NKE, MCD, NFLX, VZ, BA, CAT (9 GICS sectors) — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Daily OHLCV from Yahoo Finance, Jan 1982–Mar 2025, 11 technical indicators; sentiment from the same BERT classifier fine-tuned on the same Market Sentiment Evaluation dataset, applied to the same ~4.2M X posts (2007–2025); sentiment zero before 2007 — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Identical chronological split: Train 1982–2010 (~70%), Validation 2011–2016 (~15%), Test 2017–Mar 2025 (~15%) — matching exactly the split described in the task's framing — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)

**Disclosed leakage-prevention methodology (explicit list from the paper):**
- Expanding-window z-score normalization computed on training data only; frozen stats applied to validation and test — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Training uses linear interpolation for 1–2 day gaps; validation/test use forward-fill ONLY (no interpolation that could look ahead) — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Technical indicators computed after imputation (avoiding indicator leakage through imputed future values) — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Causal masking in all attention layers — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Graph edge priors (sector/correlation) computed on training data only — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- SAC's previous-day metrics use only realized prices available at market open (avoiding same-day lookahead in the RL state) — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)

**Full metrics table (1-day horizon):**

| Model | MAPE | RMSE | DA | Theil's U | CTR |
|---|---|---|---|---|---|
| ARIMA | 1.20% | 1.35 | 55% | 0.98 | 51% |
| XGBoost | 1.00% | 1.15 | 59% | 0.85 | 55% |
| Simple Transformer | 0.90% | 1.10 | 61% | 0.80 | 57% |
| HMM-LSTM | 0.87% | 1.02 | 64% | 0.76 | 60% |
| iTransformer | 0.82% | 0.97 | 64% | 0.73 | 61% |
| Integrated NF-BERT (= the sibling IEEE Access model) | 0.80% | 0.95 | 65% | 0.72 | 62% |
| AE-NodeFormer (no SAC) | 0.68% | 0.88 | 69% | 0.68 | 64% |
| **AE-NodeFormer + SAC (full)** | **0.59%** | **0.82** | **72%** | **0.64** | **67%** |
— table is a subset of a reported 17-model Table III; a naive always-up strategy achieves 54% DA over the test period — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)

- Multi-horizon: 5-day MAPE 1.05%/DA 67% (full model) vs. 1.30%/61% (Integrated NF-BERT); 20-day MAPE 1.55%/DA 63% vs. 1.90%/57% — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Per-stock: MAPE ranges 0.42% (WMT) to 1.10% (XOM); DA ranges 63% (XOM) to 78% (WMT); energy stocks are the weakest performers — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Ablations (1-day MAPE): Full 0.59%; No SAC 0.68% (+15.3%, abstract rounds to "15%"); No dual paths 0.63% (+6.8%, abstract rounds to "7%"); No autoencoder (single NodeFormer+BERT) 0.80% (+35.6%, abstract rounds to "36%") — the removal of the autoencoder/regime-routing causes by far the largest degradation — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Volatility regimes (1-day MAPE): Low VIX — full 0.52% vs. iTransformer 0.72%; Medium VIX — 0.65% vs. 0.92%; High VIX — 0.85% vs. 1.42% — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Diebold-Mariano tests report p<0.001 for improvements over iTransformer, PatchTST, HMM-LSTM; paired t-tests across stock-day predictions give p<0.01 for each ablated component — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Explicitly stated: NO Sharpe ratio, precision/recall/F1 are reported anywhere in this preprint (confirmed by direct fetch of the back half of the document) — the only trading-economics figures are the 72% vs. 65% DA comparison and a "43% relative improvement in high-volatility periods" — [arXiv HTML 2603.19136, offset fetch](https://arxiv.org/html/2603.19136)

**Stated limitations (Section V-C):**
- Same survivorship-bias admission as the sibling paper ("may inflate predictability") — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Edge weights from 1982–2010 correlations "may weaken by the 2017–2025 test period" — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Sentiment zero for 1982–2006 (same gap as sibling) — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- "The SAC controller is sensitive to reward weights, temperature, and architecture, and regime learning is partly circular, though staged pre-training mitigates this" — explicit author admission that regime-detection and performance gains are intertwined — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Training takes ~33% longer than the sibling baseline — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- "Frozen SAC routing is still state-dependent, so gains are partly architectural, not purely from accuracy" — an explicit caveat that some of the reported gain is from flexible routing capacity rather than genuinely better forecasting — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Transaction costs/market impact/execution excluded from backtests; same 20 stocks used for backtesting as for development — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Future work explicitly proposed by the authors: historical (point-in-time) index constituents to reduce survivorship bias, meta-learning for SAC hyperparameters, more efficient real-time architectures, strictly online regime detection, multiple autoencoders for different anomaly types, portfolio optimization, transfer learning — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)

### Inferences
- The preprint is a direct architectural extension of the published sibling, built on the IDENTICAL dataset, stocks, date range, and chronological split — it is not a different dataset or different time period driving the accuracy gap (see dedicated comparison section below).
- Because the preprint's SAC controller is frozen at inference and the authors themselves flag that "gains are partly architectural, not purely from accuracy" and that "regime learning is partly circular," there is a disclosed risk that some of the reported improvement reflects the model's added capacity/flexibility (two specialized pathways + adaptive blending) fitting the single fixed test window, rather than a generalizable forecasting improvement. This is the authors' own caveat, not an external critique.
- As of November 2026, roughly 7 months after v2, the preprint shows no sign of journal acceptance (no v3, no journal-ref, self-citation in the sibling paper still describes the IEEE Access paper as "under review" at the time this preprint was last touched, which itself is now stale text since IEEE Access has since published). This strongly suggests the preprint has NOT undergone any formal peer review to date — it remains exactly what arXiv says it is: a submitted manuscript awaiting Springer's Applied Intelligence review outcome, decision unknown or pending.

### Gaps
- Could not determine, from any available source, the current status of the Applied Intelligence submission (under review / rejected / revise-and-resubmit / accepted) — Springer does not publicly expose manuscript status for in-review papers, and no public statement by the authors was found.
- Could not retrieve the full 41-entry reference list in detail (only a high-level topical summary was returned by the fetch tool) to check what prior SAC/RL-for-trading or regime-detection work the authors are building on most closely.

---

## Why does the preprint (72%) differ from the published sibling (65%)? Disclosed facts vs. inference

### Takeaway
This is NOT a case of a different dataset, different stocks, or a different time period — both papers use the identical 20-stock universe, identical 1982–2025 date range, and identical chronological 70/15/15 (1982–2010/2011–2016/2017–2025) split. The entirety of the reported 7-point directional-accuracy gap (65%→72%) is attributable to disclosed ARCHITECTURAL additions in the preprint (autoencoder-based regime routing to two specialized transformer pathways, plus a SAC controller tuning the routing threshold and blend weight) layered on top of the published model, which the preprint's own ablation table identifies as the "Integrated NF-BERT" baseline scoring exactly 65% DA / 0.80% MAPE — i.e., the preprint reproduces the published paper's own number as its starting point and adds ~7 points of DA through two additional mechanisms. Both papers use the SAME single fixed (non-walk-forward) split methodology — this is not a point of difference between them, though it is a shared methodological caveat for both.

### Cited Findings
- The preprint's own results table lists "Integrated NF-BERT" — matching the architecture, MAPE (0.80%), and DA (65%) of the published IEEE Access paper exactly — as one row among 8 shown (of a stated 17 total), directly beneath the preprint's own two best configurations (AE-NodeFormer no-SAC: 69% DA/0.68% MAPE; AE-NodeFormer+SAC: 72% DA/0.59% MAPE) — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Both papers explicitly state the identical dataset: 20 named S&P 500 stocks, Jan 1982–Mar 2025, same OHLCV source, same 11 technical indicators, same sentiment pipeline/corpus (Market Sentiment Evaluation + ~4.2M X posts 2007–2025), same chronological 1982–2010/2011–2016/2017–2025 split — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917); [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Preprint ablation directly attributes the gain: removing the autoencoder/regime-routing (reverting to a single NodeFormer+BERT, i.e., essentially the published architecture) costs +35.6% relative MAPE (0.59%→0.80%) — the single largest ablation effect in the paper, and notably it lands the model back at exactly the published model's 0.80% MAPE — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Removing SAC alone (keeping dual-path+autoencoder) costs +15.3% relative MAPE (0.59%→0.68%, DA 72%→69%) — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Removing the dual-path design alone (keeping AE+SAC but single pathway) costs +6.8% relative MAPE (0.59%→0.63%) — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Both papers use a SINGLE fixed chronological split with no rolling/walk-forward re-training — both papers' own Limitations sections admit this explicitly as a shared weakness, not something unique to one or the other: IEEE Access paper's Section VI-C states "a single temporal split rather than rolling retraining"; the preprint's results are evaluated on the identical fixed 2017–2025 test window — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917); [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Both papers use the SAME narrow 20-stock, survivorship-biased universe — neither paper's accuracy gap is attributable to a difference in universe breadth, since they are identical — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917); [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- The preprint's own Limitations section explicitly flags that some of its gain over the published model may not be purely from better forecasting: "Frozen SAC routing is still state-dependent, so gains are partly architectural, not purely from accuracy" and "regime learning is partly circular, though staged pre-training mitigates this" — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)

### Inferences
- Given that both papers hold the dataset, stock universe, date range, and train/val/test split fully constant, the 65%→72% DA gap is best explained as a genuine (within-paper, disclosed) architectural improvement — regime-aware routing plus RL-tuned blending — evaluated on the exact same held-out window as the published model, rather than as an artifact of a different/easier dataset or a differently-favorable split. This is the most load-bearing finding for the user's core question: the two numbers are NOT explained by "a different time period" or "a different, narrower universe" (both are literally identical across papers) — they are explained by added model capacity and the preprint authors' own disclosed caveat that some of that capacity's benefit may be regime-overfitting to characteristics of this one fixed test window rather than a fully generalizable gain.
- That said, "single-fixed-split, non-walk-forward" is a real methodological limitation shared by BOTH papers (not a preprint-specific inflation device relative to the published paper) — the team should not conclude the published 65% is "the more conservative, walk-forward-validated" number and the preprint's 72% is "the less rigorous, single-split" number; both share the identical evaluation protocol. If anything, the preprint's leakage controls (frozen normalization, causal masking, forward-fill-only in val/test, training-only edge priors) are described in more explicit, itemized detail in the preprint than in the published paper's text as fetched — though the published paper does also disclose frozen normalization and causal masking, just with less itemization in the sections retrieved.
- The disclosed "partly circular" regime-learning caveat and the fact that the autoencoder threshold/routing was tuned (via SAC) against validation-period reward signals that are mechanically similar to the test-period evaluation criteria (RMSE, DA) is the single most plausible route by which the preprint's reported 72% could be inflated relative to a true out-of-sample generalization number — but this is the authors' own flagged concern, not an independently discovered flaw, and no external replication exists yet to confirm or refute it (see next section).

### Gaps
- No independent replication of either paper's numbers exists yet (see below), so it is not possible to externally confirm whether the 72% figure survives walk-forward re-evaluation or a point-in-time (non-survivorship-biased) universe — this remains the authors' own stated open question for future work, not a resolved external critique.
- Could not determine whether the SAC controller's validation-period reward tuning constitutes a subtle form of test-period information leakage (via repeated validation-set reward optimization influencing a threshold applied later to the test set) — the paper describes standard train/val/test discipline (SAC trained with "frozen predictors" during stage 3, implying it's tuned on validation data only) but a truly rigorous audit of this would require inspecting code, which was not available.

---

## Disclosed metrics (Sharpe, precision/recall/F1) and limitations sections — direct comparison

### Takeaway
The published IEEE Access paper discloses MORE financial-performance metrics than the preprint: it reports a net Sharpe ratio of 0.84 and gross Sharpe of 1.35 (Section V-E7), plus full precision/recall/F1 for its BERT sentiment classifier. The preprint discloses NO Sharpe ratio and NO precision/recall/F1 anywhere — its only performance metrics are MAPE, RMSE, directional accuracy, Theil's U, and a "Confidence Tracking Rate" (CTR), a metric not defined in the published sibling. Both papers have substantive, author-written Limitations sections that explicitly flag survivorship bias as the single biggest caveat.

### Cited Findings
- Published paper (2603.05917) Sharpe ratios: net 0.84, gross 1.35, found in Section V-E7 — [arXiv HTML 2603.05917, offset fetch](https://arxiv.org/html/2603.05917)
- Published paper sentiment-classifier precision/recall/F1 reported in full (see table in prior section) — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917)
- Preprint (2603.19136): "Sharpe ratio, precision/recall/F1, and return-based metrics: None are reported in this section. The only quantitative trading-related figures are the 72% vs. 65% directional accuracy and a 43% relative improvement in high-volatility periods" — direct confirmation from a full-text fetch of the paper's back half — [arXiv HTML 2603.19136, offset fetch](https://arxiv.org/html/2603.19136)
- Preprint instead reports a "Confidence Tracking Rate (CTR)" metric (67% for the full model vs. 62% for the Integrated NF-BERT baseline) that does not appear to be defined or used anywhere in the published sibling paper's retrieved text — [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)
- Both papers' Limitations sections independently state survivorship bias is a central concern ("the most consequential concern," published paper; "may inflate predictability," preprint) — [arXiv HTML 2603.05917](https://arxiv.org/html/2603.05917); [arXiv HTML 2603.19136](https://arxiv.org/html/2603.19136)

### Inferences
- The absence of a Sharpe ratio or any trading-economics metric in the higher-accuracy (72% DA) preprint, combined with its presence in the lower-accuracy (65% DA) published paper, means the team cannot directly compare the two papers' real-world trading viability — only directional/error metrics are comparable. A team aiming to "build to match or exceed this work" should treat the preprint's 72% DA as a pure forecasting-accuracy claim with no disclosed risk-adjusted-return evidence, whereas the published paper's 65% DA comes with a modest disclosed Sharpe (0.84 net) that at least gestures at (gross, cost-naive) economic viability.

### Gaps
- The CTR metric's exact definition was not retrieved in the fetched text (noted only as a named column); its methodology could not be verified.
- Could not determine why the preprint, despite being the more recent and more elaborate paper, drops the Sharpe-ratio reporting present in its own predecessor — no explanation was found in the retrieved text.

---

## Post-publication commentary, replication, or critique

### Takeaway
No evidence of any post-publication peer commentary, replication attempt, critique, or citation-network discussion of either paper was found. This is very plausibly simply because both papers are extremely recent relative to the November 2026 research date — the IEEE Access paper was published in May 2026 (~6 months prior) and the preprint has existed since March/April 2026 (~7-8 months prior) — not enough time has elapsed for a citation network, PubPeer-style critique, or independent replication to plausibly have emerged, especially for a mid-tier megajournal paper and a still-unpublished preprint.

### Cited Findings
- A targeted web search for the two authors' surnames together combined with "citations" returned no citation count and no citing papers — only the primary RePEc/IDEAS mirror listing of the IEEE Access preprint itself — [web search: "Al Ridhawi" "Al Osman" stock prediction citations](https://ideas.repec.org/p/arx/papers/2603.05917.html)
- A Semantic Scholar API query for citation/author data returned HTTP 429 (rate-limited) and could not be completed within the available tool budget — [Semantic Scholar API attempt](https://api.semanticscholar.org/graph/v1/paper/search)
- No PubPeer, retraction-watch, or academic-Twitter/X discussion of either paper was surfaced by any search performed.
- The published paper's Crossref record shows it was only "created" 2026-05-12 and "deposited" 2026-05-19, i.e., indexed roughly 6 months before this research was conducted — [Crossref metadata](https://api.crossref.org/works/10.1109%2FACCESS.2026.3691980)

### Inferences
- The complete absence of findable commentary is most parsimoniously explained by recency, not by the work being obscure or by critiques having been suppressed — a megajournal paper six months old and a Springer-submission-pending preprint seven-eight months old would not typically have accumulated visible citations or critique yet even for well-regarded work.

### Gaps
- Citation-network analysis is incomplete due to the Semantic Scholar rate-limit; a follow-up check (after a cooldown period, or via Google Scholar directly with a non-rate-limited method) would be needed to definitively confirm zero citations rather than merely "none found within this search budget."
- No access to IEEE Access's own "cited by" counter or a Scopus/Web of Science citation check was attempted beyond the above — a more exhaustive check was out of scope given the ~15-tool-call budget for this research pass.
