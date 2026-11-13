"""
market_top_detector -- 6-component market-top risk composite, ported from
claude-trading-skills' market-top-detector skill
(vendor/claude-trading-skills/skills/market-top-detector/scripts/,
MIT License, Copyright (c) 2026 TraderMonty).

Components: distribution_days (25%), leading_stocks (20%), defensive_rotation
(15%), breadth_divergence (15%), index_technical (15%), sentiment (10%).

Only the pure calculators + scorer are ported -- the skill's own
fmp_client.py, breadth_csv_client.py, _market_calendar.py, and
report_generator.py are NOT ported; core/market_top_detector_service.py
(the live orchestrator) reuses this project's existing
historical_price_service.py and market_breadth_service.py instead.

Three of the sentiment component's four sub-inputs (put/call ratio, VIX
term structure, margin debt YoY) have no free, keyless, programmatic data
source -- the source skill itself only gets them via a human running
WebSearch and passing them as CLI args. They're left as None here (the
calculator already handles missing inputs gracefully), an honest gap
carried over unchanged, not hidden.
"""
