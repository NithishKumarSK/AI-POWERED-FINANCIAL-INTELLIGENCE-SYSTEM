"""
market_breadth_service.py — market-wide breadth/participation signals,
adapted from claude-trading-skills' market-breadth-analyzer and
uptrend-analyzer skills (vendor/claude-trading-skills/skills/, MIT License,
Copyright (c) 2026 TraderMonty -- see vendor/claude-trading-skills/LICENSE).

Both are free, public, keyless CSV feeds TraderMonty publishes and updates
daily, confirmed live this session (2512 real daily rows through
2026-10-29 on the breadth feed; the uptrend feed's "all" worksheet through
the same date):
  - S&P 500 breadth: https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv
    (% of S&P 500 members above their 200-day and 50-day moving averages,
    already smoothed into 200MA/8MA composite indices by the source)
  - Uptrend participation: https://raw.githubusercontent.com/tradermonty/uptrend-dashboard/main/data/uptrend_ratio_timeseries.csv
    (same idea, independently computed, worksheet="all" for the whole
    market; other worksheet values are per-sector/per-industry breakdowns
    not used here)

Market-wide, NOT symbol-specific -- same category as macro_data_service.py
(fed funds rate / Treasury yield), not insider_activity_service.py/
congress_trade_service.py (single-name). Not gated by _is_index_symbol.

Cached on disk (data/market_breadth_cache.json) with the same TTL-based
reuse pattern as macro_data_service.py -- these feeds update once a day,
so re-fetching per prediction would be wasteful.

LEAKAGE SAFETY: only data points with date <= as_of_date are ever returned
-- same discipline as every other context-enrichment source in this project.

Follows the (data, error_string) tuple convention from historical_price_service.py.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "market_breadth_cache.json"
CACHE_TTL_DAYS = 1  # both source feeds update daily

BREADTH_URL = "https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv"
UPTREND_URL = "https://raw.githubusercontent.com/tradermonty/uptrend-dashboard/main/data/uptrend_ratio_timeseries.csv"


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


def _fetch_breadth() -> Tuple[Optional[list], str]:
    cache = _load_cache()
    entry = cache.get("breadth")
    if entry and (time.time() - entry.get("fetched_at", 0)) < CACHE_TTL_DAYS * 86400:
        return entry["data"], ""

    import requests
    try:
        resp = requests.get(BREADTH_URL, timeout=30)
        if resp.status_code != 200:
            if entry:
                return entry["data"], f"Using stale cache (HTTP {resp.status_code})"
            return None, f"HTTP {resp.status_code} fetching breadth CSV"
        reader = csv.DictReader(io.StringIO(resp.text.lstrip("﻿")))
        rows = []
        for r in reader:
            try:
                row = {
                    "date": r["Date"].strip(),
                    "breadth_200ma": float(r["Breadth_Index_200MA"]),
                    "breadth_8ma": float(r["Breadth_Index_8MA"]),
                    "bearish_signal": r.get("Bearish_Signal", "").strip().lower() == "true",
                }
                # Raw (unsmoothed) % of S&P 500 stocks above their 200DMA /
                # 50DMA -- the feed stores these as 0-1 fractions, scaled to
                # 0-100 here to match market-top-detector's breadth_calculator
                # convention. Breadth_50_Index_Raw wasn't documented in the
                # vendored skill's own SKILL.md but is present in the live
                # feed (confirmed this session) -- kept optional since it's
                # not guaranteed stable upstream.
                if r.get("Breadth_Index_Raw"):
                    row["breadth_200dma_pct"] = float(r["Breadth_Index_Raw"]) * 100
                if r.get("Breadth_50_Index_Raw"):
                    row["breadth_50dma_pct"] = float(r["Breadth_50_Index_Raw"]) * 100
                rows.append(row)
            except (KeyError, ValueError):
                continue
        if not rows:
            if entry:
                return entry["data"], "Using stale cache (fresh fetch had no usable rows)"
            return None, "No usable rows in breadth CSV"
        cache["breadth"] = {"data": rows, "fetched_at": time.time()}
        _save_cache(cache)
        return rows, ""
    except Exception as exc:
        if entry:
            return entry["data"], f"Using stale cache ({type(exc).__name__}: {exc})"
        return None, f"{type(exc).__name__}: {exc}"


def _fetch_uptrend() -> Tuple[Optional[list], str]:
    cache = _load_cache()
    entry = cache.get("uptrend")
    if entry and (time.time() - entry.get("fetched_at", 0)) < CACHE_TTL_DAYS * 86400:
        return entry["data"], ""

    import requests
    try:
        resp = requests.get(UPTREND_URL, timeout=30)
        if resp.status_code != 200:
            if entry:
                return entry["data"], f"Using stale cache (HTTP {resp.status_code})"
            return None, f"HTTP {resp.status_code} fetching uptrend CSV"
        reader = csv.DictReader(io.StringIO(resp.text.lstrip("﻿")))
        rows = []
        for r in reader:
            if r.get("worksheet") != "all":
                continue
            try:
                rows.append({
                    "date": r["date"].strip(),
                    "uptrend_ratio": float(r["ratio"]),
                    "uptrend_ma10": float(r["ma_10"]),
                    "uptrend_trend": r.get("trend", "").strip(),
                })
            except (KeyError, ValueError):
                continue
        if not rows:
            if entry:
                return entry["data"], "Using stale cache (fresh fetch had no usable rows)"
            return None, "No usable 'all' rows in uptrend CSV"
        cache["uptrend"] = {"data": rows, "fetched_at": time.time()}
        _save_cache(cache)
        return rows, ""
    except Exception as exc:
        if entry:
            return entry["data"], f"Using stale cache ({type(exc).__name__}: {exc})"
        return None, f"{type(exc).__name__}: {exc}"


def _value_as_of(rows: list, as_of_date: str, keys: list) -> dict:
    as_of = as_of_date[:10]
    candidates = [r for r in rows if r["date"] <= as_of]
    if not candidates:
        return {}
    latest = max(candidates, key=lambda r: r["date"])
    return {k: latest[k] for k in keys if k in latest}


def fetch_market_breadth_snapshot(as_of_date: str) -> Tuple[Optional[dict], str]:
    """Fetch S&P 500 breadth + market-wide uptrend participation as of a
    given date.

    Returns (data, error_string). data shape on success (fields present
    only if that source resolved -- a partial result is still useful):
        {"breadth_200ma": float, "breadth_8ma": float, "breadth_bearish_signal": bool,
         "uptrend_ratio": float, "uptrend_ma10": float, "uptrend_trend": "up"|"down"}
    """
    out = {}
    errors = []

    breadth_rows, breadth_err = _fetch_breadth()
    if breadth_rows:
        vals = _value_as_of(
            breadth_rows, as_of_date,
            ["breadth_200ma", "breadth_8ma", "bearish_signal", "breadth_200dma_pct", "breadth_50dma_pct"],
        )
        if vals:
            out["breadth_200ma"] = vals.get("breadth_200ma")
            out["breadth_8ma"] = vals.get("breadth_8ma")
            out["breadth_bearish_signal"] = vals.get("bearish_signal")
            if "breadth_200dma_pct" in vals:
                out["breadth_200dma_pct"] = vals["breadth_200dma_pct"]
            if "breadth_50dma_pct" in vals:
                out["breadth_50dma_pct"] = vals["breadth_50dma_pct"]
    if breadth_err:
        errors.append(f"breadth: {breadth_err}")

    uptrend_rows, uptrend_err = _fetch_uptrend()
    if uptrend_rows:
        vals = _value_as_of(uptrend_rows, as_of_date, ["uptrend_ratio", "uptrend_ma10", "uptrend_trend"])
        if vals:
            out["uptrend_ratio"] = vals.get("uptrend_ratio")
            out["uptrend_ma10"] = vals.get("uptrend_ma10")
            out["uptrend_trend"] = vals.get("uptrend_trend")
    if uptrend_err:
        errors.append(f"uptrend: {uptrend_err}")

    if not out:
        return None, "; ".join(errors) if errors else "No market breadth data resolved"
    return out, "; ".join(errors)
