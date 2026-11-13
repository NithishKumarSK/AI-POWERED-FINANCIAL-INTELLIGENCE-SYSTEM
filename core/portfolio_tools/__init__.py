"""
portfolio_tools -- portfolio/order-management utilities adapted from
trader-skill (vendor/trader-skill/, MIT License, Copyright (c) 2026 Jake
Schincariol -- see vendor/trader-skill/LICENSE).

Distinct in kind from core/*_service.py: those are leakage-safe DATA
SOURCES feeding the Gemini prediction pipeline's feature_packet. These are
standalone PORTFOLIO/ORDER utilities (position allocation, risk gating,
tax-lot harvesting, rebalancing, alerts, screening) -- real, tested,
working Python, not wired into feature_packet because this project has no
live order/portfolio execution state to hang them on (see vendor/README.md
for the full reasoning). They're available for direct use and as the
foundation if/when this project adds a live portfolio-tracking layer.
"""
