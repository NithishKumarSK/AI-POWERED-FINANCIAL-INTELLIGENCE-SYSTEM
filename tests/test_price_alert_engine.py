"""Tests for core/portfolio_tools/price_alert_engine.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from portfolio_tools.price_alert_engine import evaluate_rule


# ── above / below / stop: ring-once ───────────────────────────────────────

def test_above_does_not_ring_below_threshold():
    r = evaluate_rule({"type": "above", "price": 100}, 95, "2026-10-30")
    assert r["rings"] is False


def test_above_rings_once_crossing_threshold():
    r = evaluate_rule({"type": "above", "price": 100}, 105, "2026-10-30")
    assert r["rings"] is True


def test_above_does_not_re_ring_while_still_above_without_rearm():
    r1 = evaluate_rule({"type": "above", "price": 100}, 105, "2026-10-30")
    r2 = evaluate_rule({"type": "above", "price": 100}, 110, "2026-10-31", state=r1["state"])
    assert r2["rings"] is False


def test_below_rings_on_crossing_down():
    r = evaluate_rule({"type": "below", "price": 50}, 45, "2026-10-30")
    assert r["rings"] is True


def test_stop_behaves_like_below():
    r = evaluate_rule({"type": "stop", "price": 50}, 45, "2026-10-30")
    assert r["rings"] is True


# ── rearm ─────────────────────────────────────────────────────────────────

def test_rearm_allows_re_ringing_after_falling_back():
    rule = {"type": "above", "price": 100, "rearm": True}
    r1 = evaluate_rule(rule, 105, "2026-10-30")
    assert r1["rings"] is True
    r2 = evaluate_rule(rule, 95, "2026-10-31", state=r1["state"])
    assert r2["rings"] is False  # falling back doesn't itself ring
    r3 = evaluate_rule(rule, 105, "2026-11-01", state=r2["state"])
    assert r3["rings"] is True  # re-armed, rings again


def test_without_rearm_stays_silent_after_falling_back():
    rule = {"type": "above", "price": 100}  # no rearm
    r1 = evaluate_rule(rule, 105, "2026-10-30")
    r2 = evaluate_rule(rule, 95, "2026-10-31", state=r1["state"])
    r3 = evaluate_rule(rule, 105, "2026-11-01", state=r2["state"])
    assert r3["rings"] is False  # never re-armed, never rings again


# ── pct_move ──────────────────────────────────────────────────────────────

def test_pct_move_rings_on_large_move():
    r = evaluate_rule({"type": "pct_move", "pct": 3, "ref_price": 100}, 104, "2026-10-30")
    assert r["rings"] is True


def test_pct_move_does_not_ring_on_small_move():
    r = evaluate_rule({"type": "pct_move", "pct": 3, "ref_price": 100}, 101, "2026-10-30")
    assert r["rings"] is False


def test_pct_move_rings_on_downward_move_too():
    r = evaluate_rule({"type": "pct_move", "pct": 3, "ref_price": 100}, 96, "2026-10-30")
    assert r["rings"] is True


def test_pct_move_once_per_day_only():
    rule = {"type": "pct_move", "pct": 3, "ref_price": 100}
    r1 = evaluate_rule(rule, 110, "2026-10-30")
    r2 = evaluate_rule(rule, 120, "2026-10-30", state=r1["state"])
    assert r1["rings"] is True
    assert r2["rings"] is False  # same day, already rung


def test_pct_move_missing_ref_price_does_not_ring():
    r = evaluate_rule({"type": "pct_move", "pct": 3}, 110, "2026-10-30")
    assert r["rings"] is False


# ── opening_bell ────────────────────────────────────────────────────────

def test_opening_bell_rings_once_per_day():
    rule = {"type": "opening_bell"}
    r1 = evaluate_rule(rule, 100, "2026-10-30")
    r2 = evaluate_rule(rule, 100, "2026-10-30", state=r1["state"])
    assert r1["rings"] is True
    assert r2["rings"] is False


def test_opening_bell_rings_again_next_day():
    rule = {"type": "opening_bell"}
    r1 = evaluate_rule(rule, 100, "2026-10-30")
    r2 = evaluate_rule(rule, 100, "2026-10-31", state=r1["state"])
    assert r2["rings"] is True


# ── errors ────────────────────────────────────────────────────────────────

def test_unknown_rule_type_raises():
    import pytest
    with pytest.raises(ValueError):
        evaluate_rule({"type": "bogus"}, 100, "2026-10-30")
