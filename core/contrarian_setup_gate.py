"""
Contrarian Setup Gate (Shapiro pipeline synthesis center), adapted from
claude-trading-skills' `contrarian-setup-gate` skill
(vendor/claude-trading-skills/skills/contrarian-setup-gate/,
references/gate-decision-table.md). MIT License, Copyright (c) 2026
TraderMonty.

Pure, offline synthesis of three Shapiro-pipeline verdicts (crowding /
news-reaction-failure / price-action) into one `setup_status`, via the
SEQUENTIAL precedence state machine the source skill's own decision
table specifies: each step fully settles before the next step's input
is even inspected, so a later step's corruption can never soften an
earlier step's definitive verdict. The full 15-row collapsed decision
table and the out-of-order price-action branch are ported exactly,
including the named precedence pins the source skill's test suite
specifically guards (e.g. a NOT_CONFIRMED news verdict at step 2 means
price-action's own corruption at step 3 is never inspected -> REJECTED,
not INSUFFICIENT_EVIDENCE).

SCOPE REDUCTION, disclosed: the source skill's `cot-contrarian-detector`
step-1 input (crowding) has no live source in this project -- that
upstream skill needs FMP Premium+ COT data (see vendor/README.md). This
gate therefore takes `crowding` as a caller-supplied dict (an explicit
`{"classification": "CROWDED_LONG"|"CROWDED_SHORT"|"NEUTRAL"}` assertion,
not derived from live data) -- exactly the same disclosed substitution
already used for `futures_position_sizer.py` Mode A and
`breakout_trade_planner.py`'s VCP-screener-sourced candidates. The two
DOWNSTREAM steps, however, are wired to this project's own real,
already-live `news_reaction_failure_service.py` and
`contrarian_confirmation_service.py` outputs -- two of the pipeline's
three steps are genuinely real here, not placeholders.

Also out of scope, disclosed: the source skill's adversarial-JSON-file
hardening (whole-file non-finite scanning, `schema_version` allowlisting,
CLI usage-error handling) is a defense against untrusted FILES read from
disk; this integration passes trusted in-memory dicts from this
project's own services, so that hardening layer doesn't apply and isn't
ported. Basic shape/type validation (missing keys, unknown verdict
values, invalid stop_reference) IS ported, since those protect against
a genuinely malformed caller input, not just a corrupted file.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

_VALID_CLASSIFICATIONS = {"CROWDED_LONG", "CROWDED_SHORT", "NEUTRAL"}
_CONFIDENCE_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def normalize_crowding(crowding: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(crowding, dict):
        return {"state": "INVALID", "reason": "detector_malformed", "classification": None}
    classification = crowding.get("classification")
    if not isinstance(classification, str) or classification not in _VALID_CLASSIFICATIONS:
        return {"state": "INVALID", "reason": "detector_unknown_classification", "classification": None}
    if classification == "NEUTRAL":
        return {"state": "NOT_CONFIRMED", "reason": "detector_not_crowded", "classification": classification}
    return {"state": "CONFIRMED", "reason": None, "classification": classification}


def _normalize_downstream(report: Optional[Dict[str, Any]], prefix: str, detector_classification: Optional[str]) -> Dict[str, Any]:
    if report is None:
        return {"state": "PENDING", "reason": None, "direction": None, "verdict_reason": None, "confidence": None}
    if not isinstance(report, dict):
        return {"state": "INVALID", "reason": f"{prefix}_malformed", "direction": None, "verdict_reason": None, "confidence": None}

    verdict = report.get("verdict")
    confidence = report.get("confidence")
    direction = report.get("direction")

    if verdict is not None and not isinstance(verdict, str):
        return {"state": "INVALID", "reason": f"{prefix}_malformed", "direction": direction, "verdict_reason": None, "confidence": None}
    if confidence is not None and not isinstance(confidence, str):
        return {"state": "INVALID", "reason": f"{prefix}_malformed", "direction": direction, "verdict_reason": None, "confidence": None}
    if direction is not None and not isinstance(direction, str):
        return {"state": "INVALID", "reason": f"{prefix}_malformed", "direction": None, "verdict_reason": None, "confidence": None}

    if detector_classification is not None and direction is not None and direction != detector_classification:
        return {"state": "INVALID", "reason": f"{prefix}_direction_mismatch", "direction": direction, "verdict_reason": None, "confidence": None}

    if confidence is not None and confidence not in _CONFIDENCE_RANK:
        return {"state": "INVALID", "reason": f"{prefix}_unknown_confidence", "direction": direction, "verdict_reason": None, "confidence": None}

    verdict_reason = report.get("verdict_reason")
    if verdict == "CONFIRMED":
        state = "CONFIRMED"
    elif verdict == "NOT_CONFIRMED":
        state = "NOT_CONFIRMED"
    elif verdict in ("INSUFFICIENT_EVIDENCE", "INSUFFICIENT_DATA", "INSUFFICIENT"):
        state = "INSUFFICIENT"
    else:
        return {"state": "INVALID", "reason": f"{prefix}_unknown_verdict", "direction": direction, "verdict_reason": verdict_reason, "confidence": confidence}

    return {"state": state, "reason": verdict_reason, "direction": direction, "verdict_reason": verdict_reason, "confidence": confidence,
            "stop_reference": (report.get("swing_levels") or {}).get("stop_reference")}


def normalize_news(news_report: Optional[Dict[str, Any]], detector_classification: Optional[str]) -> Dict[str, Any]:
    return _normalize_downstream(news_report, "news", detector_classification)


def normalize_price_action(price_report: Optional[Dict[str, Any]], detector_classification: Optional[str]) -> Dict[str, Any]:
    norm = _normalize_downstream(price_report, "price_action", detector_classification)
    if norm["state"] == "CONFIRMED":
        stop_ref = norm.get("stop_reference")
        if stop_ref is None:
            return {**norm, "state": "INVALID", "reason": "price_action_missing_stop_reference"}
        if isinstance(stop_ref, bool) or not isinstance(stop_ref, (int, float)) or not math.isfinite(stop_ref) or stop_ref <= 0:
            return {**norm, "state": "INVALID", "reason": "price_action_invalid_stop_reference"}
    return norm


def run_contrarian_setup_gate(
    crowding: Optional[Dict[str, Any]],
    news_report: Optional[Dict[str, Any]] = None,
    price_action_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Pure synthesis -- no network, no file I/O. See module docstring for
    the crowding-input scope reduction."""
    c = normalize_crowding(crowding)
    c_classification = c["classification"] if c["state"] == "CONFIRMED" else None
    n = normalize_news(news_report, c_classification)
    p = normalize_price_action(price_action_report, c_classification)

    warnings = []
    missing_confirmations = []
    direction = None
    gate_confidence = None
    entry_trigger = None
    invalidation_level = None

    if c["state"] in ("INVALID", "INSUFFICIENT"):
        setup_status = "INSUFFICIENT_EVIDENCE"
        missing_confirmations.append({"step": "crowding", "state": c["state"], "reason": c["reason"]})
    elif c["state"] == "NOT_CONFIRMED":
        setup_status = "REJECTED"
        missing_confirmations.append({"step": "crowding", "state": c["state"], "reason": c["reason"]})
    else:  # crowding CONFIRMED
        if n["state"] == "PENDING":
            # Out-of-order: price-action may still have been provided.
            if p["state"] in ("INVALID", "INSUFFICIENT"):
                setup_status = "INSUFFICIENT_EVIDENCE"
                missing_confirmations.append({"step": "price_action", "state": p["state"], "reason": p["reason"]})
            elif p["state"] == "NOT_CONFIRMED":
                setup_status = "REJECTED"
                missing_confirmations.append({"step": "price_action", "state": p["state"], "reason": p["reason"]})
            elif p["state"] == "CONFIRMED":
                setup_status = "CROWDED"
                warnings.append("out_of_order_price_action")
            else:  # both PENDING
                setup_status = "CROWDED"
            if n["state"] == "PENDING" and setup_status == "CROWDED":
                missing_confirmations.append({"step": "news", "state": "PENDING", "reason": None})
                if p["state"] == "PENDING":
                    missing_confirmations.append({"step": "price_action", "state": "PENDING", "reason": None})

        elif n["state"] in ("INVALID", "INSUFFICIENT"):
            setup_status = "INSUFFICIENT_EVIDENCE"
            missing_confirmations.append({"step": "news", "state": n["state"], "reason": n["reason"]})
        elif n["state"] == "NOT_CONFIRMED":
            setup_status = "REJECTED"
            missing_confirmations.append({"step": "news", "state": n["state"], "reason": n["reason"]})
        else:  # news CONFIRMED
            if p["state"] == "PENDING":
                setup_status = "WATCHING_PRICE"
                missing_confirmations.append({"step": "price_action", "state": "PENDING", "reason": None})
            elif p["state"] in ("INVALID", "INSUFFICIENT"):
                setup_status = "INSUFFICIENT_EVIDENCE"
                missing_confirmations.append({"step": "price_action", "state": p["state"], "reason": p["reason"]})
            elif p["state"] == "NOT_CONFIRMED":
                setup_status = "REJECTED"
                missing_confirmations.append({"step": "price_action", "state": p["state"], "reason": p["reason"]})
            else:  # price_action CONFIRMED
                setup_status = "READY_FOR_PLAN"
                direction = "SHORT" if c_classification == "CROWDED_LONG" else "LONG"  # fade the crowd
                confidences = [r["confidence"] for r in (n, p) if r.get("confidence") in _CONFIDENCE_RANK]
                if confidences:
                    gate_confidence = min(confidences, key=lambda x: _CONFIDENCE_RANK[x])
                entry_trigger = p.get("verdict_reason") or "price_action_confirmed"
                invalidation_level = p.get("stop_reference")

    return {
        "schema_version": "1.0",
        "setup_status": setup_status,
        "direction": direction,
        "gate_confidence": gate_confidence,
        "entry_trigger": entry_trigger,
        "invalidation_level": invalidation_level,
        "missing_confirmations": missing_confirmations,
        "warnings": warnings,
        "inputs": {"crowding": c, "news_failure": n, "price_action": p},
    }
