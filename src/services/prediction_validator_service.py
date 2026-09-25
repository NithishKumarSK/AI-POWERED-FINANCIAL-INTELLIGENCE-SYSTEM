"""Prediction validator service — leakage-safe direction accuracy evaluation."""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

_MEMORY_PATH = "decision_memory.jsonl"


def load_prediction_records(path: str = _MEMORY_PATH) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    records = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as exc:
        logger.warning(f"[PredictionValidator] Could not load {path}: {exc}")
    return records


def evaluate_prediction(
    record: Dict[str, Any],
    prices_df: Any,
) -> Dict[str, Any]:
    """Evaluate a single prediction against realised prices."""
    try:
        ticker = record.get("ticker", "")
        as_of = record.get("as_of_date", "")
        horizon = int(record.get("horizon_days", 30))
        verdict = (record.get("verdict") or record.get("decision") or "").upper()

        if not ticker or not as_of:
            return {**record, "evaluated": False, "reason": "Missing ticker or date"}

        as_of_date = date.fromisoformat(as_of[:10])
        target_date = as_of_date + timedelta(days=horizon)

        ticker_data = prices_df[prices_df["Ticker"] == ticker.upper()].sort_values("Date")
        past = ticker_data[ticker_data["Date"].dt.date <= as_of_date]
        future = ticker_data[ticker_data["Date"].dt.date <= target_date]

        if past.empty or len(future) <= len(past):
            return {**record, "evaluated": False, "reason": "No future price data"}

        price_at_decision = float(past.iloc[-1]["Close"])
        price_at_horizon = float(future.iloc[-1]["Close"])

        if price_at_decision <= 0:
            return {**record, "evaluated": False, "reason": "Entry price is zero"}

        actual_return = (price_at_horizon - price_at_decision) / price_at_decision
        actual_direction = "UP" if actual_return > 0 else "DOWN"
        predicted_direction = "UP" if verdict == "BUY" else ("DOWN" if verdict == "SELL" else "NEUTRAL")

        correct = None
        if predicted_direction in ("UP", "DOWN"):
            correct = predicted_direction == actual_direction

        return {
            **record,
            "evaluated": True,
            "price_at_decision": round(price_at_decision, 4),
            "price_at_horizon": round(price_at_horizon, 4),
            "actual_return": round(actual_return, 6),
            "actual_return_pct": round(actual_return * 100, 2),
            "actual_direction": actual_direction,
            "predicted_direction": predicted_direction,
            "correct": correct,
            "evaluation_date": str(target_date),
        }

    except Exception as exc:
        logger.warning(f"[PredictionValidator] Evaluation error: {exc}")
        return {**record, "evaluated": False, "reason": str(exc)}


def compute_accuracy_report(evaluated: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute precision, recall, accuracy from evaluated predictions."""
    scored = [e for e in evaluated if e.get("evaluated") and e.get("correct") is not None]
    if not scored:
        return {"status": "UNAVAILABLE", "message": "No evaluated predictions yet."}

    total = len(scored)
    correct = sum(1 for e in scored if e.get("correct") is True)
    accuracy = correct / total

    buy_records = [e for e in scored if (e.get("verdict") or e.get("decision") or "").upper() == "BUY"]
    sell_records = [e for e in scored if (e.get("verdict") or e.get("decision") or "").upper() == "SELL"]

    buy_acc = sum(1 for e in buy_records if e.get("correct")) / max(len(buy_records), 1)
    sell_acc = sum(1 for e in sell_records if e.get("correct")) / max(len(sell_records), 1)

    return {
        "status": "SUCCESS",
        "total_evaluated": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "buy_accuracy": round(buy_acc, 4),
        "sell_accuracy": round(sell_acc, 4),
        "buy_count": len(buy_records),
        "sell_count": len(sell_records),
        "rows": scored[:200],
    }


def run_prediction_validation(
    dataset_path: str = "data/stock_prices_daily.csv",
    memory_path: str = _MEMORY_PATH,
) -> Dict[str, Any]:
    """Load stored predictions, evaluate against CSV prices, return accuracy report."""
    records = load_prediction_records(memory_path)
    if not records:
        return {"status": "UNAVAILABLE", "message": "No prediction records found in decision_memory.jsonl."}

    try:
        import pandas as pd
        df = pd.read_csv(dataset_path, parse_dates=["Date"])
        df.columns = [c.strip() for c in df.columns]
    except Exception as exc:
        return {"status": "ERROR", "message": f"Could not load dataset: {exc}"}

    evaluated = [evaluate_prediction(r, df) for r in records]
    return compute_accuracy_report(evaluated)
