# January-August 2026 stock prediction backtest

Each prediction receives the previous 12 calendar months of daily prices. Returns run from the preceding month-end close to the target month-end close, using the last trading day on or before each date. Returns exclude costs and dividends.

These are retrospective predictions using the current model and current code. Price inputs are time-filtered, but this does not establish that the model and its training or development history were free of knowledge of these outcomes.

| Stock | Month | Predicted return | Actual return | Direction correct |
|---|---|---:|---:|:---:|
| SPY | 2026-01 | -2.08% | +1.47% | No |
| SPY | 2026-02 | +2.33% | -0.86% | No |
| SPY | 2026-03 | +2.30% | -5.20% | No |
| SPY | 2026-04 | +4.13% | +10.51% | Yes |
| SPY | 2026-05 | -2.38% | +5.26% | No |
| SPY | 2026-06 | +2.68% | -1.28% | No |
| SPY | 2026-07 | +2.33% | +0.03% | Yes |
| SPY | 2026-08 | -2.19% | +2.68% | No |
| TSLA | 2026-01 | -10.53% | -4.29% | Yes |
| TSLA | 2026-02 | -7.94% | -6.48% | Yes |
| TSLA | 2026-03 | -7.38% | -7.64% | Yes |
| TSLA | 2026-04 | -13.66% | +2.66% | No |
| TSLA | 2026-05 | +9.53% | +14.19% | Yes |
| TSLA | 2026-06 | -7.24% | -3.49% | Yes |
| TSLA | 2026-07 | No usable forecast | — | — |
| TSLA | 2026-08 | -17.01% | +18.23% | No |

| Stock | Successful runs | Direction accuracy | Mean absolute return error | Decision agreement |
|---|---:|---:|---:|---:|
| SPY | 8 | 2/8 (25.0%) | 4.92 percentage points | 1/8 (12.5%) |
| TSLA | 7 | 5/7 (71.4%) | 9.71 percentage points | 5/7 (71.4%) |
| ALL | 15 | 7/15 (46.7%) | 7.16 percentage points | 6/15 (40.0%) |

Direction accuracy compares the sign of returns. Decision agreement compares the project's BUY/HOLD/SELL labels. The small sample does not establish future predictive performance.

- TSLA 2026-07: SKIP — INSUFFICIENT SIGNAL QUALITY: All 3 Gemini consensus calls produced conflicting directions. This means the market data is ambiguous and no reliable prediction can be made. Skipping this trade to avoid a coin-flip prediction. Votes: {'BUY': 1, 'SELL': 0, 'HOLD': 0}. Try a different date range or symbol.