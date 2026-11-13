# Deep Dive: PLOS Complex Systems 82%-Directional-Accuracy SPY Paper (Cao, Chen, Lian & Zhang, 2025)

**Resolution status: FULL TEXT OBTAINED.** The complete paper (all 16 pages, all tables, all section text) was retrieved by fetching the publisher's printable PDF (`https://journals.plos.org/complexsystems/article/file?id=10.1371/journal.pcsy.0000037&type=printable`) and extracting it locally with `pdftotext -layout` (the WebFetch tool could not decode the embedded PDF text streams directly, but a local copy of the downloaded PDF was saved and successfully parsed). This closes the gap flagged by the prior research pass, which had access only to the IDEAS/RePEc abstract page. The methodology turns out to be considerably thinner than the title implies — see findings below, especially under Key Questions 4–6.

Primary source for all findings below unless otherwise cited: Cao H, Chen H, Lian Y, Zhang H-K. "Volatility-informed SPY forecasting: From CGR-SPY analysis to DLSTM prediction." *PLOS Complex Systems* 2025;2(8):e0000037. https://doi.org/10.1371/journal.pcsy.0000037 (full text PDF: https://journals.plos.org/complexsystems/article/file?id=10.1371/journal.pcsy.0000037&type=printable).

---

## Who are the full named authors, their institutional affiliations, and research background?

### Takeaway
The paper has four authors affiliated with Columbia University, UMass Amherst (two authors), and Carnegie Mellon University; the corresponding author is Yulong Lian. No independent evidence of these authors' broader research track record in quantitative finance was found (no Semantic Scholar citation history, no other indexed papers surfaced in search).

### Cited Findings
- Authors and affiliations as printed on the paper: "Hong Cao¹, Hao Chen², Yulong Lian³, Hong-Kun Zhang²" where ¹=Columbia University, New York, NY, USA; ²=University of Massachusetts Amherst, Amherst, MA, USA; ³=Carnegie Mellon University, Pittsburgh, PA, USA. — [Full-text PDF](https://journals.plos.org/complexsystems/article/file?id=10.1371/journal.pcsy.0000037&type=printable)
- Corresponding author is Yulong Lian; contact email given on the paper is yulongli@andrew.cmu.edu (note the email local-part "yulongli" does not exactly match the printed name "Yulong Lian" — possibly a transliteration/CMU Andrew ID quirk, not independently resolved). — [Full-text PDF](https://journals.plos.org/complexsystems/article/file?id=10.1371/journal.pcsy.0000037&type=printable)
- Author contributions breakdown (as declared in the paper): Conceptualization — Hao Chen, Yulong Lian, Hong-Kun Zhang; Data curation — Hong Cao, Hao Chen, Yulong Lian; Formal analysis — Hong Cao, Yulong Lian; Investigation — Hong Cao, Hao Chen, Yulong Lian; Methodology — Hong Cao, Yulong Lian; Software — Yulong Lian, Hong-Kun Zhang; Supervision — Hong-Kun Zhang; Validation — Hong-Kun Zhang; Visualization — Hong-Kun Zhang; Writing (draft and review) — Yulong Lian, Hong-Kun Zhang. — [Full-text PDF](https://journals.plos.org/complexsystems/article/file?id=10.1371/journal.pcsy.0000037&type=printable)
- Funding statement: "The author(s) received no specific funding for this work." Competing interests: "The authors have declared that no competing interests exist." — [Full-text PDF](https://journals.plos.org/complexsystems/article/file?id=10.1371/journal.pcsy.0000037&type=printable)
- Semantic Scholar's record for this DOI shows 0 citations and 0 influential citations, and lists no other metadata suggesting a deep publication history tied to this specific paper record. — [Semantic Scholar API](https://api.semanticscholar.org/graph/v1/paper/DOI:10.1371/journal.pcsy.0000037)

### Inferences
- The "Supervision" credit going to Hong-Kun Zhang (a UMass Amherst author) alongside Hong Cao being at Columbia and Lian at CMU suggests this reads like a cross-institution collaboration likely involving a faculty supervisor (Zhang) and students/junior researchers (Cao, Chen, Lian) rather than an established quant-finance research group; the lack of any other findable papers by these authors in finance/ML is consistent with this being an early-career output rather than work from a lab with a track record in the field.

### Gaps
- No author CVs, institutional profile pages, or Google Scholar profiles were directly pulled up, so individual research backgrounds (PhD students vs. faculty, prior publications) could not be independently confirmed beyond what's printed on the paper itself.

---

## What is PLOS Complex Systems exactly — genuine peer-reviewed PLOS journal? Impact factor/reputation? Peer review process?

### Takeaway
PLOS Complex Systems is a genuine, newly-launched (2023/2024) open-access journal published by PLOS (a reputable nonprofit OA publisher), with Hocine Cherifi as founding Editor-in-Chief; it has no Journal Impact Factor yet (too new, and PLOS explicitly deprioritizes JIF in favor of article-level metrics), and it follows standard PLOS editorial-board peer review (external academic editor + reviewers) rather than any more rigorous specialized process. This specific article went through that process — it has a named handling academic editor and explicit received/accepted/published dates spanning over a year — but PLOS's standard review does not include a dedicated quant-finance leakage/backtesting checklist, and the paper itself shows signs of light copy-editing scrutiny (see Gaps/Inferences below).

### Cited Findings
- PLOS announced in mid-2023 that it was launching PLOS Complex Systems (and PLOS Mental Health) for submissions; first articles published in 2024. Hocine Cherifi was appointed the first Editor-in-Chief. — [PLOS announcement](https://theplosblog.plos.org/2023/06/welcoming-two-new-journals-to-the-plos-portfolio/)
- The journal's scope is "research of broad significance that examines the complex systems shaping the world," covering network science, opinion dynamics, neuroscience, epidemiology, etc. — [PLOS Complex Systems journal page](https://journals.plos.org/complexsystems/)
- No Journal Impact Factor could be found for PLOS Complex Systems in any source searched; PLOS's own messaging states it is "central to its commitment to reduce reliance on the Journal Impact Factor" and instead promotes article-level metrics. — [Journal page](https://journals.plos.org/complexsystems/); [WebSearch synthesis]
- The journal is published by PLOS, a nonprofit 501(c)(3) open-access publisher based in California. — [PLOS Complex Systems journal page](https://journals.plos.org/complexsystems/)
- This specific article lists a named Academic Editor (Keith Burghardt, University of Southern California), and the standard PLOS received/accepted/published date triplet: Received January 17, 2024; Accepted February 20, 2025; Published August 5, 2025 — over a year from submission to acceptance. — [Full-text PDF](https://journals.plos.org/complexsystems/article/file?id=10.1371/journal.pcsy.0000037&type=printable)
- No named peer reviewers or review reports are shown on the article page itself (standard for PLOS unless authors opt into open review publication). — [WebFetch of article page]
- The PLOS Complex Systems article page for this paper shows "Reader Comments (0)" — no post-publication comments, corrections, or errata have been posted. — [Article comments page](https://journals.plos.org/complexsystems/article/comments?id=10.1371/journal.pcsy.0000037)

### Inferences
- A ~13-month review-to-acceptance gap plus a named external academic editor indicates the paper did go through genuine human peer review, not a rubber-stamp process — but PLOS's house peer review model focuses on methodological soundness and ethical/reporting standards generally, not finance-specific scrutiny (e.g., there is no evidence a reviewer caught the un-reconciled 90%/5% train/test split language, the "Sect 4.2" cross-reference that doesn't exist in the paper's own section numbering, or potential data-leakage issues from pre-split smoothing/scaling — see Key Question 6). This points to review quality adequate for a general complex-systems audience but not necessarily rigorous by the standards of empirical finance/econometrics journals.
- Zero citations and zero post-publication comments 15 months after submission and ~3 months after publication (as of the November 2026 research date) means the paper has not yet been externally validated, critiqued, or replicated by anyone in the literature — it is essentially unvetted outside of the original peer review.

### Gaps
- Could not determine whether PLOS Complex Systems uses single-blind, double-blind, or open peer review as a matter of journal policy (the journal's own "Editorial and Peer Review Process" sub-page exists but its substantive content did not come through in the WebFetch extraction).
- Could not find any citation-tracking source (Scopus, Web of Science, Google Scholar) beyond Semantic Scholar to corroborate the zero-citation finding; Semantic Scholar's coverage of brand-new PLOS Complex Systems articles may itself be incomplete, so the true citation count could be undercounted (though independently, no citing paper surfaced in any web search either).

---

## What EXACT train/test methodology did they use?

### Takeaway
It is a single fixed (non-walk-forward) train/test split on one continuous historical window (2012-01-01 to 2024-01-01), not a rolling or walk-forward design, and the paper's own stated percentages (90%/5%) do not reconcile with its own stated observation counts — a documentation/internal-consistency problem that calls into question how carefully the manuscript was checked.

### Cited Findings
- Dataset: SPY daily closing prices from Yahoo Finance, 2012-01-01 to 2024-01-01, smoothed with a 5-day moving average, then min-max scaled to [0,1] via `s_t = (S_t - S_min)/(S_max - S_min)`. — [Full-text PDF, Sect 3.2.1]
- Total sample size stated for the DLSTM experiment: N = 3018 closing prices "starting from 2012-1-1 which we use as our training set" (this sentence in Sect 3.1 conflates N with "training set," which is itself an internal labeling inconsistency carried from Sect 3.1 into Sect 3.2.1). — [Full-text PDF, Sect 3.1]
- Explicit split stated in Sect 3.2.1: "The first 90% of the dataset was used as the training dataset, which is 2878 observations, and we use the last 5% of our dataset, which is 140 observations as our testing dataset." — [Full-text PDF, Sect 3.2.1]
- Arithmetic check: 2878 + 140 = 3018 (matches total N), but 2878/3018 = 95.4% (not 90%) and 140/3018 = 4.6% (roughly matches "5%"). So the paper's own prose ("first 90%... last 5%") does not match its own reported counts (2878 and 140) — the real split is ~95.4% train / ~4.6% test, not 90/5 as stated in the text. No validation set is mentioned at all.
- Class balance disclosed only for the test set: "The size of the majority class (decreasing) is 79" out of 140 test observations — i.e., 79 "decreasing" vs 61 "increasing" days (56.4%/43.6%), a mild imbalance. No class balance is given for the training set or full dataset. — [Full-text PDF, Sect 3.2.1]
- No walk-forward, rolling-window, or cross-validation design is described anywhere in the paper — it is one static train/test split evaluated once. — [Full-text PDF, full read]
- Training hyperparameters: batch size 64, Adam optimizer with learning rate 0.001; the binary-classification baseline was trained for 700 epochs (epoch count for DLSTM/LSTM itself is not stated). — [Full-text PDF, Sect 3.2.1]
- The CGR (copper-gold ratio) side of the paper uses a separate, much longer dataset (Yahoo Finance daily closes/yields, January 2007–July 2022, 3,916 data points) but this part of the paper reports no train/test split at all — it is purely a rolling 5-day-window correlation/narrative analysis of four historical crisis episodes, not a predictive model with a held-out test set. — [Full-text PDF, Sect 2]

### Inferences
- Because the moving-average smoothing and min-max scaling are applied to "the dataset" as a whole before the text describes any split, and the paper never states whether `S_min`/`S_max` or the 5-day MA window were computed using only the training portion vs. the full 2012–2024 series, there is a plausible but unconfirmed **data-leakage pathway**: if scaling bounds or the moving average windows that straddle the train/test boundary used information from the test period (or from dates after the training cutoff), the model's effective test-time inputs/labels would be contaminated by future information. The paper provides no statement ruling this out.
- Separately, and arguably more importantly: because the *target* series is a 5-day moving average rather than the raw daily close, and overlapping 5-day MAs are highly autocorrelated from one day to the next by construction, predicting the *direction* of consecutive MA values is a mechanically easier task than predicting the direction of raw daily returns. This alone could substantially inflate the reported 82% figure relative to the 55–66% academic ceiling typically reported for raw next-day return/price-direction prediction, independent of any genuine forecasting skill. The paper does not address or control for this.
- The test period of 140 trading days ending 2024-01-01 corresponds to roughly mid-2023 through year-end 2023 — a period in which SPY rallied strongly and with low volatility (a trending "melt-up" market). A single short, directionally trending out-of-sample window inflates directional-accuracy metrics for almost any model with even a mild trend-following bias, and the paper evaluates on only this one window with no robustness check across other periods/regimes.

### Gaps
- The paper does not state whether min-max scaling bounds and MA smoothing were computed on the training subset only or on the full 2012–2024 series (potential leakage, unresolved).
- No validation set, no k-fold or walk-forward cross-validation, no statement of how many independent test windows were tried (if any) before settling on this one period — can't determine if 82% is the result of hyperparameter/period selection that happened to work rather than a representative out-of-sample result.
- Epoch count and early-stopping criteria for the DLSTM and baseline LSTM (as opposed to the binary classifier, which is given 700 epochs) are not stated.

---

## What does "volatility-regime-switching DLSTM" mean exactly in their paper?

### Takeaway
There is **no formal, quantified, or tested regime-switching mechanism** in the paper at all — "regime switching" is a narrative/qualitative framing describing two *separate, independently evaluated* components (a purely correlational CGR analysis for four historical crisis windows, and a single fixed-split DLSTM model evaluated once on one 140-day test window) that the authors never actually combine, switch between programmatically, or jointly backtest. This is a materially weaker claim than the paper's title and abstract imply, and weaker than how it would typically be described in a literature summary ("volatility-regime-switching DLSTM model").

### Cited Findings
- The paper's own framing (Sect 1, Introduction): "This paper suggests employing the Copper-Gold Ratio (CGR) as a market indicator during turbulent times and leveraging a novel neural network, the Difference Long Short-Term Memory (DLSTM), for more stable periods. The CGR and DLSTM methods combine to create a two-part approach for predicting the SPY." — [Full-text PDF, Sect 1]
- The CGR component (Sect 2) is evaluated only through descriptive/narrative rolling 5-day-window correlation analysis over four specific historical windows chosen by the authors: 2008 Financial Crisis (Jul–Oct 2008, SPY-CGR correlation 0.90), European Debt Crisis (Apr 2010–Jul 2012, correlation 0.78), Trade War Fears (Jun 2018–Dec 2019, correlation 0.76), 2018 Fall Selloff (Sep–Dec 2018, correlation 0.65), plus a "stable" baseline period (Jan 2007–Jan 2008, correlation 0.32) for contrast. — [Full-text PDF, Table 1, Sects 2.1–2.6]
- There is no volatility-regime *detection* rule stated anywhere (e.g., no VIX threshold, no HMM, no GARCH-based regime classifier) that would programmatically decide, at any given point in time, whether to use CGR or DLSTM. The VIX is discussed only descriptively in Table 1 (average/max VIX per historical crisis window), not as an input to any switching algorithm. — [Full-text PDF, Sect 2.6, Table 1]
- CGR is never given any predictive accuracy metric, backtest, or trading simulation of its own — only correlation coefficients with SPY during four historical windows chosen in hindsight. — [Full-text PDF, Sect 2, full read]
- The DLSTM (Sect 3) is a standalone LSTM variant evaluated on the full 2012–2024 dataset using one static train/test split — it is not restricted to, or separately tested within, any defined "stable" sub-period; the paper simply asserts in Sect 2.7 that "DLSTM is more effective in stable markets" and that "abrupt market disruptions, such as those seen during the 2008 crisis, can reduce DLSTM's effectiveness" as an unsupported claim, without testing DLSTM's accuracy during the 2008 crisis or any other high-volatility window. — [Full-text PDF, Sect 2.7, Sect 3]
- DLSTM architecture (Sect 3.1–3.2): a standard 2-layer LSTM (128 units, then 64 units) followed by two Dense layers (16 units, then 4 units), differentiated from a baseline LSTM (same 128/64 LSTM layers, Dense 16 then Dense 2) primarily by its custom loss function: `L_loss = L_MSE + L_D`, where `L_D` is an MSE-style term computed on the *first-differenced* series (`Δx_i = x_{i+1} - x_i`) rather than on raw levels, in addition to the standard MSE on raw levels. Input tensor shape for DLSTM is (6,2) vs. (5,1) for baseline LSTM, implying the DLSTM uses two input channels (likely raw price and differenced price) versus one for the plain LSTM. — [Full-text PDF, Sect 3.1, Tables 2–3]
- Base LSTM citation: the paper cites Hochreiter & Schmidhuber (1997) as the origin of the standard LSTM architecture that both baseline LSTM and DLSTM build on. — [Full-text PDF, ref. 11; Sect 3.1]

### Inferences
- "Volatility-regime-switching DLSTM" as a shorthand description (used in the user's framing and plausibly in secondary summaries) overstates what the paper actually built and tested: there is no single integrated model that switches rules by detected regime and that was backtested as a switching system. The paper is better described as "two separate, loosely related analyses under one title" — a qualitative correlation study (CGR) and a quantitative but narrowly-tested forecasting model (DLSTM) — stitched together by a conceptual narrative, not a validated regime-switching architecture.
- This means the headline finding that should be compared against the 55–66% academic ceiling is specifically: *one DLSTM model, one static train/test split, one 140-day out-of-sample window in a trending/low-volatility late-2023 market, predicting the direction of a 5-day-smoothed SPY series* — not a regime-aware ensemble validated across varying volatility conditions.

### Gaps
- No ablation or sensitivity analysis is reported for the DLSTM (e.g., performance with/without the differenced-series loss term alone), so it's not independently confirmed how much of the 82% vs. 78% (baseline LSTM) improvement is attributable specifically to the custom loss function vs. to other factors (random seed, minor architecture differences in input channels).

---

## Is the 82% figure for ALL days, or only within specific volatility regimes?

### Takeaway
82% is the *only* directional-accuracy figure reported in the entire paper — it is the DLSTM's accuracy over the single 140-day test window (not broken out by regime, by volatility level, or by any subset), and it is not compared against, or averaged with, any separate accuracy figure for the CGR approach (which has no accuracy figure at all). There is no regime-by-regime performance breakdown anywhere in the paper.

### Cited Findings
- Table 4 (the paper's only results table for predictive accuracy) reports exactly three numbers for directional accuracy: DLSTM 82%, baseline LSTM 79% (note: body text in Sect 3.3 says "78%" while Table 4 says "79%" — an internal inconsistency between the prose and the table), and Binary Classification 74%. No regime, date-range, or subset breakdown accompanies these numbers — each is a single aggregate value over the same 140-day test set. — [Full-text PDF, Sect 3.3, Table 4]
- F1 scores given alongside: DLSTM 0.8732, LSTM 0.8449, Binary Classification 0.7602 (again single aggregate values, no regime split). — [Full-text PDF, Table 4]
- The CGR section (Sect 2) reports zero accuracy/precision/recall/F1 metrics of any kind — only Pearson-style correlation coefficients between CGR and SPY during four hindsight-selected historical crisis windows (Table 1). It is therefore impossible to compare "CGR regime performance" vs. "DLSTM regime performance" on a common accuracy metric, because only one of the two legs of the paper reports an accuracy metric at all. — [Full-text PDF, Table 1, Sect 2]

### Inferences
- Because there is no regime-conditioned accuracy table, the question "is 82% an overall average or a best-case subset" is somewhat moot: 82% is simply the result on the one test window the authors chose (late 2023/early 2024), which — per the methodology section above — was itself a trending, relatively low-volatility period. In that sense it could be read as closer to a "best case" scenario for a trend-sensitive model than a stress-tested average across volatility regimes, even though the paper does not explicitly frame it that way.

### Gaps
- No data exists (in this paper) to answer how DLSTM would have performed during the 2008 crisis, the European debt crisis, the 2018 selloff, or any other high-volatility window the CGR analysis highlights — the authors assert in Sect 2.7 that DLSTM's effectiveness "can drop during abrupt disruptions" but never test or quantify this claim.

---

## Do they disclose precision/recall/F1, Sharpe ratio, or just directional accuracy? Limitations/leakage-prevention measures?

### Takeaway
Only directional accuracy and F1 are disclosed (no explicit precision/recall breakdown, no Sharpe/Sortino ratio, no comparison to a buy-and-hold benchmark); there is no dedicated "Limitations" section, and no explicit leakage-prevention statement (e.g., point-in-time data construction, no walk-forward validation, no confirmation that scaling/smoothing respected the train/test boundary).

### Cited Findings
- Reported metrics: directional accuracy and F1 score only, for all three models (DLSTM, LSTM, Binary Classification) — see Table 4 above. Precision and recall are not separately reported; the paper only states that "F1 is the harmonic mean of precision and recall... useful even when there is a class imbalance in the dataset," citing Derczynski 2016 and Lipton et al. 2014 as general methodological references, but does not print the underlying precision/recall numbers themselves. — [Full-text PDF, Sect 3.3]
- No Sharpe ratio, Sortino ratio, or any other risk-adjusted return metric is reported anywhere in the paper. — [Full-text PDF, full read]
- Simulated day-trading backtest (Sect 3.4): starting capital $500, rule-based long/short strategy driven purely by the model's directional prediction, run 10 times and averaged. Reported results: average profit of $21 (4.2% return) after 20 trading days (~1 month), and $62 (12.4% return) after 60 trading days (~3 months). No standard deviation or distribution across the 10 runs is given, no transaction costs/slippage/borrowing costs for the short-selling legs are mentioned, and — critically — there is no buy-and-hold SPY benchmark return reported for the same window for comparison. — [Full-text PDF, Sect 3.4]
- There is no section titled or functioning as "Limitations." The closest statement is a single unsupported sentence in Sect 2.7: "abrupt market disruptions, such as those seen during the 2008 crisis, can reduce DLSTM's effectiveness" — asserted, not tested. — [Full-text PDF, Sect 2.7]
- Data availability statement: "All data necessary is included in the supplemental file," referencing "S1 Data. The dataset of daily SPY closing prices from January 2012 to January 2024 used in Sect 4.2 analysis." However, the paper's own section numbering has no "Sect 4.2" — Section 4 is the one-paragraph "Conclusion" with no sub-sections — indicating a cross-reference/editing error that survived to the published version. — [Full-text PDF, Supporting information]
- No statement anywhere addresses whether moving-average smoothing or min-max scaling bounds were computed using only training data (vs. the full series spanning into the test period), and no statement explicitly confirms a walk-forward or point-in-time data-construction discipline. — [Full-text PDF, full read]

### Inferences
- The absence of a Sharpe ratio or a buy-and-hold comparison for the trading simulation makes the "12.4% return over three months" figure essentially uninterpretable in risk-adjusted or relative terms — SPY itself could easily have returned a comparable or larger amount over the same late-2023 window (which, per public market history, was a strong rally period), so the simulated strategy's apparent "edge" cannot be assessed from what's disclosed.
- The uncorrected "Sect 4.2" cross-reference error, plus the prose/table mismatch on the LSTM accuracy figure (78% vs. 79%) and the 90%/5% vs. actual 95.4%/4.6% split discrepancy, are all signs of a manuscript that did not receive careful line-by-line fact-checking during peer review or copy-editing — reinforcing the Key Question 2 finding that PLOS's general-purpose review process did not catch finance-methodology-specific or even basic internal-consistency issues.

### Gaps
- Cannot determine actual precision/recall values (not disclosed), cannot compute or verify a Sharpe ratio (insufficient data disclosed — no daily return series or volatility of the strategy returns is given), and cannot confirm or rule out leakage from preprocessing (smoothing/scaling) because the paper does not state its preprocessing scope relative to the train/test boundary.

---

## Has this paper been cited, critiqued, or replicated? Post-publication comments/errata?

### Takeaway
No — as of this research (November 2026), the paper has zero citations (Semantic Scholar), zero post-publication reader comments on the PLOS platform, and no independent replication, critique, or erratum was found anywhere in web search. It is effectively unvalidated by the broader research community since publication (August 5, 2025).

### Cited Findings
- Semantic Scholar's record for DOI 10.1371/journal.pcsy.0000037 reports `citationCount: 0` and `influentialCitationCount: 0`, with an empty citing-papers list. — [Semantic Scholar API](https://api.semanticscholar.org/graph/v1/paper/DOI:10.1371/journal.pcsy.0000037)
- The PLOS Complex Systems article page itself shows "Reader Comments (0)" — no comments, corrections, or errata have been posted on the platform. — [Article comments page](https://journals.plos.org/complexsystems/article/comments?id=10.1371/journal.pcsy.0000037)
- Targeted web searches for citations, replications, or discussion of this specific paper (by title and by author names) returned only indexing/aggregator listings of the paper itself (IDEAS/RePEc, EconPapers, Bohrium, CMU KiltHub mirror) and unrelated papers on S&P 500 volatility forecasting — no secondary discussion, critique, or replication attempt was found. — [WebSearch results, multiple queries]

### Inferences
- Given the paper was only published in August 2025, roughly three months before this research (November 2026 per the research date context — note the apparent ~15-month gap between stated publication date and "current" research date is itself unusual and worth the report writer flagging/verifying), the absence of citations is not necessarily damning on its own (citation accrual takes time), but combined with zero post-publication comments and zero independent discussion anywhere online, there is currently no external corroboration of the 82% claim from any source outside the original authors and their own peer review.

### Gaps
- Could not check Google Scholar directly (no direct tool access to scholar.google.com in this session; WebSearch did not surface a Scholar-specific citation count). Could not check Web of Science or Scopus (no access). If the report writer has access to Google Scholar directly, it would be worth a direct citation check there as the single remaining avenue not fully exhausted in this pass.

---

## Overall assessment for the report writer

The full text is now in hand and resolves the prior gap completely. The headline conclusion to carry into the final report: **this paper is not a sound exception to the 55–66% academic ceiling for daily stock direction prediction.** The 82% figure rests on (1) a single non-walk-forward train/test split with an internally inconsistent split percentage, (2) a target series that is a 5-day moving average rather than raw daily price (making the prediction task mechanically easier via induced autocorrelation — likely the single biggest driver of the apparently high number), (3) one 140-trading-day out-of-sample window coinciding with a trending, low-volatility late-2023 market rally, (4) no disclosed control for potential leakage from pre-split smoothing/scaling, (5) no Sharpe ratio or buy-and-hold benchmark for its trading-simulation claims, and (6) a "volatility-regime-switching" framing that is narrative rather than an actual tested switching mechanism — the CGR leg of the paper has no predictive accuracy metric at all. The paper also contains several uncorrected internal inconsistencies (78% vs. 79% LSTM accuracy, 90%/5% vs. actual 95.4%/4.6% split, a reference to a non-existent "Sect 4.2") that suggest light review scrutiny, consistent with PLOS Complex Systems being a brand-new (2023/2024-launched), no-impact-factor-yet journal without finance-specific review expertise. Zero citations and zero post-publication comments mean no one has yet publicly validated or challenged these results.
