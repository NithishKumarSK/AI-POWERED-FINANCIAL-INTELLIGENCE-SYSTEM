"""Tests for core/portfolio_tools/tax_lot_optimizer.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from portfolio_tools.tax_lot_optimizer import (
    family, term, pick_lots, simulate_sale, check_wash_sale, find_harvest_candidates,
)


# ── family ────────────────────────────────────────────────────────────────

def test_family_groups_share_classes():
    assert family("GOOGL") == family("GOOG")
    assert family("BRK.A") == family("BRK.B")


def test_family_unrelated_tickers_differ():
    assert family("AAPL") != family("MSFT")


# ── term ──────────────────────────────────────────────────────────────────

def test_term_long_over_one_year():
    assert term("2025-01-01", "2026-06-01") == "long"


def test_term_short_under_one_year():
    assert term("2026-06-01", "2026-10-30") == "short"


def test_term_boundary_exactly_365_days_is_short():
    # held > 365 days is long; exactly 365 is not yet long-term.
    assert term("2025-01-01", "2026-01-01") == "short"


# ── pick_lots ─────────────────────────────────────────────────────────────

def test_fifo_picks_oldest_lots_first():
    lots = [
        {"id": "new", "date": "2026-06-01", "shares": 10, "cost": 1500},
        {"id": "old", "date": "2025-01-01", "shares": 10, "cost": 1000},
    ]
    picked = pick_lots(lots, 5, method="fifo")
    assert len(picked) == 1
    assert picked[0]["id"] == "old"


def test_hifo_picks_highest_cost_per_share_first():
    lots = [
        {"id": "cheap", "date": "2025-01-01", "shares": 10, "cost": 1000},   # $100/share
        {"id": "expensive", "date": "2026-01-01", "shares": 10, "cost": 2000},  # $200/share
    ]
    picked = pick_lots(lots, 5, method="hifo")
    assert picked[0]["id"] == "expensive"


def test_pick_lots_partial_fills_across_multiple_lots():
    lots = [
        {"id": "L1", "date": "2025-01-01", "shares": 10, "cost": 1000},
        {"id": "L2", "date": "2025-06-01", "shares": 10, "cost": 1200},
    ]
    picked = pick_lots(lots, 15, method="fifo")
    assert len(picked) == 2
    assert picked[0]["shares_sold"] == 10
    assert picked[1]["shares_sold"] == 5


def test_pick_lots_insufficient_shares_raises():
    import pytest
    lots = [{"id": "L1", "date": "2025-01-01", "shares": 5, "cost": 500}]
    with pytest.raises(ValueError):
        pick_lots(lots, 10)


def test_pick_lots_unknown_method_raises():
    import pytest
    lots = [{"id": "L1", "date": "2025-01-01", "shares": 10, "cost": 1000}]
    with pytest.raises(ValueError):
        pick_lots(lots, 5, method="lifo")


# ── simulate_sale ─────────────────────────────────────────────────────────

def test_simulate_sale_computes_gain():
    picked = [{"id": "L1", "date": "2025-01-01", "shares_sold": 10, "cost_basis_sold": 1000.0}]
    result = simulate_sale(picked, sale_price=150, sale_date="2026-10-30")
    assert result["proceeds"] == 1500
    assert result["gain_loss"] == 500.0
    assert result["long_term_gain_loss"] == 500.0
    assert result["short_term_gain_loss"] == 0.0


def test_simulate_sale_splits_long_and_short_term():
    picked = [
        {"id": "old", "date": "2025-01-01", "shares_sold": 10, "cost_basis_sold": 1000.0},
        {"id": "new", "date": "2026-10-01", "shares_sold": 10, "cost_basis_sold": 1000.0},
    ]
    result = simulate_sale(picked, sale_price=150, sale_date="2026-10-30")
    assert result["long_term_gain_loss"] == 500.0
    assert result["short_term_gain_loss"] == 500.0


# ── check_wash_sale ───────────────────────────────────────────────────────

def test_wash_sale_triggered_by_buy_within_window():
    r = check_wash_sale("AAPL", "2026-10-15", [{"ticker": "AAPL", "date": "2026-10-20", "side": "buy"}])
    assert r["disallowed"] is True
    assert len(r["triggering_transactions"]) == 1


def test_wash_sale_not_triggered_outside_window():
    r = check_wash_sale("AAPL", "2026-10-15", [{"ticker": "AAPL", "date": "2026-12-01", "side": "buy"}])
    assert r["disallowed"] is False


def test_wash_sale_ignores_sells():
    r = check_wash_sale("AAPL", "2026-10-15", [{"ticker": "AAPL", "date": "2026-10-20", "side": "sell"}])
    assert r["disallowed"] is False


def test_wash_sale_ignores_unrelated_tickers():
    r = check_wash_sale("AAPL", "2026-10-15", [{"ticker": "MSFT", "date": "2026-10-20", "side": "buy"}])
    assert r["disallowed"] is False


def test_wash_sale_triggered_by_same_family_share_class():
    r = check_wash_sale("GOOGL", "2026-10-15", [{"ticker": "GOOG", "date": "2026-10-20", "side": "buy"}])
    assert r["disallowed"] is True


# ── find_harvest_candidates ───────────────────────────────────────────────

def test_harvest_finds_unrealized_losses_only():
    positions = [
        {"ticker": "LOSER", "lots": [{"id": "1", "date": "2025-01-01", "shares": 10, "cost": 2000}]},
        {"ticker": "WINNER", "lots": [{"id": "2", "date": "2025-01-01", "shares": 10, "cost": 500}]},
    ]
    prices = {"LOSER": 150, "WINNER": 150}
    candidates = find_harvest_candidates(positions, prices)
    tickers = [c["ticker"] for c in candidates]
    assert "LOSER" in tickers
    assert "WINNER" not in tickers


def test_harvest_respects_min_loss_usd_threshold():
    positions = [{"ticker": "SMALL", "lots": [{"id": "1", "date": "2025-01-01", "shares": 10, "cost": 1010}]}]
    prices = {"SMALL": 100}  # loss = -$10
    assert find_harvest_candidates(positions, prices, min_loss_usd=50) == []
    assert len(find_harvest_candidates(positions, prices, min_loss_usd=5)) == 1


def test_harvest_skips_positions_with_no_price():
    positions = [{"ticker": "NOPRICE", "lots": [{"id": "1", "date": "2025-01-01", "shares": 10, "cost": 2000}]}]
    assert find_harvest_candidates(positions, prices={}) == []


def test_harvest_sorted_biggest_loss_first():
    positions = [
        {"ticker": "SMALL_LOSS", "lots": [{"id": "1", "date": "2025-01-01", "shares": 10, "cost": 1100}]},
        {"ticker": "BIG_LOSS", "lots": [{"id": "2", "date": "2025-01-01", "shares": 10, "cost": 2000}]},
    ]
    prices = {"SMALL_LOSS": 100, "BIG_LOSS": 100}
    candidates = find_harvest_candidates(positions, prices)
    assert candidates[0]["ticker"] == "BIG_LOSS"
