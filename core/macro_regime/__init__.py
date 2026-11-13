"""
macro_regime -- 1-2 year structural macro regime detection, adapted from
claude-trading-skills' macro-regime-detector skill
(vendor/claude-trading-skills/skills/macro-regime-detector/, MIT License,
Copyright (c) 2026 TraderMonty).

Six cross-asset components, each scoring a 0-100 "transition signal
strength" from ratio/spread crossovers and momentum, combined into a
weighted composite (concentration 25%, yield_curve 20%, credit_conditions
15%, size_factor 15%, equity_bond 15%, sector_rotation 10%) and classified
into a regime (Concentration/Broadening/Contraction/Inflationary/
Transitional).

Ported faithfully line-by-line from the vendored source (pure stdlib math,
no external dependencies, independently live-verified against real
yfinance data this session) -- not re-derived from a description.
"""
