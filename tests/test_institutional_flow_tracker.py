"""
Tests for core/institutional_flow_tracker.py -- pure classification/
aggregation logic, synthetic data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from institutional_flow_tracker import classify_filer_flow, compute_flow_score


def test_classify_filer_flow_no_position():
    assert classify_filer_flow(0, None) == "NO_POSITION"
    assert classify_filer_flow(0, 0) == "NO_POSITION"


def test_classify_filer_flow_new_position():
    assert classify_filer_flow(1_000_000, None) == "NEW_POSITION"
    assert classify_filer_flow(1_000_000, 0) == "NEW_POSITION"


def test_classify_filer_flow_exited():
    assert classify_filer_flow(0, 1_000_000) == "EXITED"


def test_classify_filer_flow_accumulation():
    assert classify_filer_flow(1_200_000, 1_000_000) == "ACCUMULATION"


def test_classify_filer_flow_distribution():
    assert classify_filer_flow(800_000, 1_000_000) == "DISTRIBUTION"


def test_classify_filer_flow_flat():
    assert classify_filer_flow(1_050_000, 1_000_000) == "FLAT"


def test_compute_flow_score_no_signal_when_all_flat():
    flows = [{"flow": "FLAT"}, {"flow": "NO_POSITION"}]
    result = compute_flow_score(flows)
    assert result["classification"] == "NO_SIGNAL"
    assert result["flow_score"] == 0.0


def test_compute_flow_score_smart_money_accumulation():
    flows = [{"flow": "ACCUMULATION"}, {"flow": "NEW_POSITION"}, {"flow": "ACCUMULATION"}, {"flow": "FLAT"}]
    result = compute_flow_score(flows)
    assert result["classification"] == "SMART_MONEY_ACCUMULATION"
    assert result["active_filers"] == 3


def test_compute_flow_score_smart_money_distribution():
    flows = [{"flow": "DISTRIBUTION"}, {"flow": "EXITED"}, {"flow": "DISTRIBUTION"}]
    result = compute_flow_score(flows)
    assert result["classification"] == "SMART_MONEY_DISTRIBUTION"
    assert result["flow_score"] == -100.0


def test_compute_flow_score_mixed():
    flows = [{"flow": "ACCUMULATION"}, {"flow": "DISTRIBUTION"}]
    result = compute_flow_score(flows)
    assert result["classification"] == "MIXED"
    assert result["flow_score"] == 0.0


def test_compute_flow_score_empty_list():
    result = compute_flow_score([])
    assert result["classification"] == "NO_SIGNAL"
    assert result["active_filers"] == 0
