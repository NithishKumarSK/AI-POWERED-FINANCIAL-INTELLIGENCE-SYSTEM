"""
ibd_distribution_day_service.py -- live orchestrator for
core/ibd_distribution_day_monitor.py (the ported claude-trading-skills
ibd-distribution-day-monitor). Fetches real daily price history for SPY
and QQQ via core/historical_price_service.py, runs the Distribution Day
detection/enrichment/risk-classification pipeline on each, and returns the
combined market risk level.

Market-wide, NOT symbol-specific -- same category as ftd_status_service.py
and macro_regime_service.py. Cached on disk for a day since Distribution
Day counts only change with each new daily bar.

LEAKAGE SAFETY: historical_price_service returns the full available
history; this module filters to bars with date <= as_of_date before any
calculation, so a historical backtest origin never sees future price bars
-- same discipline as every other context-enrichment source.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "ibd_distribution_day_cache.json"
CACHE_TTL_DAYS = 1
MIN_DAYS = 110  # covers the 80-session lookback the skill requires + 50-session SMA warmup

_TICKERS = ("SPY", "QQQ")


def _to_most_recent_first(bars: list, as_of_date: str) -> list:
    """historical_price_service returns ASC-sorted (chronological,
    oldest-first) {date,close,...} dicts; ibd_distribution_day_monitor
    expects MOST-RECENT-FIRST. Filter to on/before as_of_date
    (LEAKAGE SAFETY), then reverse."""
    as_of = as_of_date[:10]
    filtered = [b for b in bars if b.get("date", "") <= as_of]
    return list(reversed(filtered))


def _fetch_histories(as_of_date: str) -> Tuple[dict, list]:
    import datetime as _dt
    from historical_price_service import fetch_price_history_for_range

    as_of_dt = _dt.datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
    start_dt = as_of_dt - _dt.timedelta(days=MIN_DAYS + 30)

    histories = {}
    errors = []
    for ticker in _TICKERS:
        bars, err, _coverage = fetch_price_history_for_range(
            ticker, start_dt.isoformat(), as_of_dt.isoformat()
        )
        if not bars:
            errors.append(f"{ticker}: {err or 'no bars returned'}")
            histories[ticker] = []
            continue
        histories[ticker] = _to_most_recent_first(bars, as_of_date)
    return histories, errors


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass


def compute_ibd_distribution_day_status(as_of_date: str, use_cache: bool = True) -> Tuple[Optional[dict], str]:
    """IBD Distribution Day risk assessment for SPY/QQQ as of a given date.

    Returns (data, error_string). data shape on success:
        {"overall_risk_level": str, "spy_risk_level": str, "qqq_risk_level": str,
         "qqq_d5_count": int, "qqq_d15_count": int, "qqq_d25_count": int,
         "qqq_distribution_day_today": bool}
    (a trimmed view of core.ibd_distribution_day_monitor.analyze_index's
    full output per index, kept under data["_full"] for callers that want it).
    """
    import dataclasses

    from ibd_distribution_day_monitor import (
        DistributionDayRule,
        RiskThresholds,
        analyze_index,
        combine_index_risks,
    )

    cache_key = as_of_date[:10]
    if use_cache:
        cache = _load_cache()
        entry = cache.get(cache_key)
        if entry and (time.time() - entry.get("computed_at", 0)) < CACHE_TTL_DAYS * 86400:
            return entry["data"], ""

    histories, errors = _fetch_histories(as_of_date)
    if not histories.get("SPY") and not histories.get("QQQ"):
        return None, "; ".join(errors) if errors else "No price history available for SPY or QQQ"

    rule = DistributionDayRule()
    thresholds = RiskThresholds()

    full = {}
    for ticker, history in histories.items():
        if not history:
            continue
        analysis = analyze_index(ticker, history, rule, thresholds, as_of=None, required_min_sessions=80)
        # DDRecord is a dataclass (not JSON-serializable) -- convert to
        # plain dicts since this whole structure gets cached to disk below.
        analysis["active_distribution_days"] = [dataclasses.asdict(r) for r in analysis["active_distribution_days"]]
        analysis["removed_distribution_days"] = [dataclasses.asdict(r) for r in analysis["removed_distribution_days"]]
        full[ticker] = analysis

    if not full:
        return None, "; ".join(errors) if errors else "No usable history for SPY or QQQ"

    risk_by_symbol = {sym: res["risk_level"] for sym, res in full.items()}
    overall_risk = combine_index_risks(risk_by_symbol)

    qqq = full.get("QQQ")
    spy = full.get("SPY")

    result = {
        "overall_risk_level": overall_risk,
        "spy_risk_level": spy["risk_level"] if spy else None,
        "qqq_risk_level": qqq["risk_level"] if qqq else None,
        "qqq_d5_count": qqq["d5_count"] if qqq else None,
        "qqq_d15_count": qqq["d15_count"] if qqq else None,
        "qqq_d25_count": qqq["d25_count"] if qqq else None,
        "qqq_distribution_day_today": qqq["is_distribution_day_today"] if qqq else None,
        "_full": full,
    }

    if use_cache:
        cache = _load_cache()
        cache[cache_key] = {"data": result, "computed_at": time.time()}
        _save_cache(cache)

    err = "; ".join(errors) if errors else ""
    return result, err
