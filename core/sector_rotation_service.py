"""
Live orchestrator for core/sector_rotation_analyzer.py -- fetches
TraderMonty's free, keyless sector_summary.csv (confirmed live this
session, same GitHub-hosted family as market_breadth_service.py's
breadth/uptrend CSVs) and parses it into the rows analyze_sector_rotation()
expects.

Market-wide, NOT symbol-specific -- same category as
market_breadth_service.py/macro_data_service.py. Cached on disk for a
day, same TTL convention used throughout this project for daily-updated
free feeds.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sector_rotation_analyzer import analyze_sector_rotation

SECTOR_SUMMARY_URL = "https://raw.githubusercontent.com/tradermonty/uptrend-dashboard/main/data/sector_summary.csv"
CACHE_PATH = ROOT / "data" / "sector_rotation_cache.json"
CACHE_TTL_DAYS = 1
TIMEOUT_SECONDS = 20


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


def _parse_sector_summary_csv(text: str) -> List[Dict[str, Any]]:
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for r in reader:
        try:
            rows.append({
                "sector": r["Sector"].strip(),
                "ratio": float(r["Ratio"]),
                "ma10": float(r["10MA"]),
                "trend": r.get("Trend", "").strip(),
                "slope": float(r["Slope"]),
                "status": r.get("Status", "").strip(),
            })
        except (KeyError, ValueError):
            continue
    return rows


def fetch_sector_summary(use_cache: bool = True) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    cache = _load_cache()
    entry = cache.get("sector_summary")
    if use_cache and entry and (time.time() - entry.get("fetched_at", 0)) < CACHE_TTL_DAYS * 86400:
        return entry["rows"], ""

    try:
        resp = requests.get(SECTOR_SUMMARY_URL, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return None, f"network_error: {type(exc).__name__}: {exc}"
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code} fetching sector_summary.csv"

    rows = _parse_sector_summary_csv(resp.text)
    if not rows:
        return None, "No usable rows in sector_summary.csv"

    cache["sector_summary"] = {"rows": rows, "fetched_at": time.time()}
    _save_cache(cache)
    return rows, ""


def fetch_sector_rotation_analysis(use_cache: bool = True) -> Tuple[Optional[Dict[str, Any]], str]:
    rows, err = fetch_sector_summary(use_cache=use_cache)
    if err or not rows:
        return None, err or "no_sector_data"
    return analyze_sector_rotation(rows), ""
