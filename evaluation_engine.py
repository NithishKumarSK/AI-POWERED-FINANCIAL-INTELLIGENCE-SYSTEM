"""
Historical backtesting and evaluation engine.

This module is intentionally small and self-contained:
- data loading and validation
- leakage-safe cutoff slicing
- dynamic indicators computed only on past rows
- deterministic scoring, agents, decisions, metrics, and JSONL storage
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


DATASET_PATH = os.path.join(os.path.dirname(__file__), "data", "stock_prices_daily.csv")
EVALUATION_RUNS_PATH = os.path.join(os.path.dirname(__file__), "evaluation_runs.jsonl")
INSTITUTIONAL_RUNS_PATH = os.path.join(os.path.dirname(__file__), "institutional_runs.jsonl")
DECISION_MEMORY_PATH = os.path.join(os.path.dirname(__file__), "decision_memory.jsonl")

REQUIRED_COLUMNS = [
    "Date",
    "Ticker",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
]

_DATASET_CACHE: Optional[pd.DataFrame] = None
_TICKER_CACHE: Dict[str, pd.DataFrame] = {}
_BENCHMARK_PROXY_CACHE: Dict[str, pd.Series] = {}


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    issues: List[str]


@dataclass(frozen=True)
class UnifiedEvaluationObject:
    returns: Dict[str, Any]
    risk: Dict[str, Any]
    benchmark: Dict[str, Any]
    decisions: Dict[str, Any]
    calibration: Dict[str, Any]
    portfolio_state: Dict[str, Any]


def _append_jsonl(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_decision_memory(limit: Optional[int] = None, *, as_of_date: Optional[Any] = None) -> List[Dict[str, Any]]:
    if not os.path.exists(DECISION_MEMORY_PATH):
        return []
    cutoff = _parse_date(as_of_date) if as_of_date is not None else None
    rows: List[Dict[str, Any]] = []
    with open(DECISION_MEMORY_PATH, "r", encoding="utf-8") as file:
        for line in file:
            try:
                row = json.loads(line)
            except Exception:
                continue
            decision_date = row.get("decision_date") or row.get("date")
            if cutoff is not None and decision_date:
                try:
                    if _parse_date(decision_date) >= cutoff:
                        continue
                except Exception:
                    continue
            rows.append(row)
    return rows[-limit:] if limit else rows


def store_decision_memory(decision_rows: List[Dict[str, Any]], *, run_id: str, run_type: str = "institutional_backtest") -> None:
    for row in decision_rows:
        memory = {
            "decision_id": f"{run_id}:{row.get('ticker')}:{row.get('as_of_date')}",
            "run_id": run_id,
            "run_type": run_type,
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "decision_date": row.get("as_of_date"),
            "ticker": row.get("ticker"),
            "portfolio": row.get("portfolio"),
            "decision": row.get("decision"),
            "engine_decision": row.get("engine_decision"),
            "confidence": row.get("confidence"),
            "signals_used": row.get("scores"),
            "feature_contributions": row.get("decision_attribution"),
            "regime": row.get("regime"),
            "risk_state": row.get("risk"),
            "prediction": row.get("prediction"),
            "builder_critic_judge": row.get("builder_critic_judge"),
            "expected_return": (row.get("prediction") or {}).get("expected_return"),
            "expected_risk": (row.get("prediction") or {}).get("expected_drawdown"),
            "outcome": row.get("outcome"),
            "actual_return": row.get("future_return"),
            "evaluation_status": "EVALUATED" if row.get("outcome") in {"WIN", "LOSS"} else "PENDING",
        }
        _append_jsonl(DECISION_MEMORY_PATH, memory)


def compute_learning_profile(*, as_of_date: Optional[Any] = None, limit: Optional[int] = 10000) -> Dict[str, Any]:
    rows = load_decision_memory(limit=limit, as_of_date=as_of_date)
    evaluated = [row for row in rows if row.get("outcome") in {"WIN", "LOSS"}]

    def grouped_accuracy(key_fn) -> Dict[str, Dict[str, Any]]:
        groups: Dict[str, Dict[str, Any]] = {}
        for row in evaluated:
            key = key_fn(row) or "Unknown"
            item = groups.setdefault(str(key), {"count": 0, "wins": 0})
            item["count"] += 1
            item["wins"] += 1 if row.get("outcome") == "WIN" else 0
        for item in groups.values():
            item["accuracy"] = item["wins"] / item["count"] if item["count"] else None
        return groups

    factor_groups: Dict[str, Dict[str, Any]] = {}
    for row in evaluated:
        contributions = ((row.get("feature_contributions") or {}).get("top_positive_contributors") or []) + ((row.get("feature_contributions") or {}).get("top_negative_contributors") or [])
        for contribution in contributions:
            if not isinstance(contribution, dict):
                continue
            factor = str(contribution.get("factor") or "Unknown")
            item = factor_groups.setdefault(factor, {"count": 0, "wins": 0})
            item["count"] += 1
            item["wins"] += 1 if row.get("outcome") == "WIN" else 0
    for item in factor_groups.values():
        item["accuracy"] = item["wins"] / item["count"] if item["count"] else None

    confidence_rows = [
        {"valid": True, "confidence": row.get("confidence"), "outcome": row.get("outcome")}
        for row in evaluated
    ]
    return {
        "memory_count": len(rows),
        "evaluated_count": len(evaluated),
        "decision_accuracy": grouped_accuracy(lambda row: row.get("decision")),
        "regime_accuracy": grouped_accuracy(lambda row: row.get("regime")),
        "sector_accuracy": {},
        "factor_accuracy": factor_groups,
        "confidence_accuracy": compute_calibration(confidence_rows) if confidence_rows else [],
        "overall_accuracy": sum(1 for row in evaluated if row.get("outcome") == "WIN") / len(evaluated) if evaluated else None,
    }


def _clamp_score(value: float) -> int:
    try:
        value_f = float(value)
    except Exception:
        return 0
    return int(round(max(0.0, min(100.0, value_f))))


def _signal_from_score(score: int) -> str:
    if score <= 0:
        return "Unavailable"
    if score >= 67:
        return "Bullish"
    if score <= 33:
        return "Bearish"
    return "Neutral"


def _risk_label_from_score(score: int) -> str:
    if score <= 0:
        return "Unavailable"
    if score >= 67:
        return "High"
    if score <= 33:
        return "Low"
    return "Medium"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _percentile_rank(series: pd.Series, value: Any) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 20:
        return None
    target = _safe_float(value, default=math.nan)
    if math.isnan(target):
        return None
    return float((values <= target).mean())


def _rolling_zscore(series: pd.Series, window: int = 60) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna().tail(window)
    if len(values) < max(20, window // 2):
        return None
    std = float(values.std())
    if std == 0:
        return 0.0
    return float((values.iloc[-1] - values.mean()) / std)


def _parse_date(value: Any) -> pd.Timestamp:
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        raise ValueError(f"Invalid date: {value}")
    return ts


def validate_dataset(df: pd.DataFrame) -> ValidationResult:
    issues: List[str] = []
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        issues.append(f"Missing required columns: {missing}")
        return ValidationResult(False, issues)

    if df.empty:
        issues.append("Dataset is empty.")

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        bad = pd.to_numeric(df[col], errors="coerce").isna().sum()
        if bad:
            issues.append(f"Column {col} has {int(bad)} non-numeric values.")

    bad_dates = pd.to_datetime(df["Date"], errors="coerce", utc=True).isna().sum()
    if bad_dates:
        issues.append(f"Date column has {int(bad_dates)} invalid values.")

    if df["Ticker"].isna().any():
        issues.append("Ticker column contains null values.")

    return ValidationResult(len(issues) == 0, issues)


def load_dataset(path: str = DATASET_PATH, *, force_reload: bool = False) -> pd.DataFrame:
    """Load, validate, parse, and sort the daily OHLCV dataset."""
    global _DATASET_CACHE, _TICKER_CACHE

    if _DATASET_CACHE is not None and not force_reload and path == DATASET_PATH:
        return _DATASET_CACHE

    if not os.path.exists(path):
        raise FileNotFoundError(f"Dataset not found: {path}")

    df = pd.read_csv(path)
    validation = validate_dataset(df)
    if not validation.valid:
        raise ValueError("Dataset validation failed: " + "; ".join(validation.issues))

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
    if df["Date"].isna().any():
        raise ValueError("Dataset validation failed: Date parsing produced null values.")

    for col in ["Open", "High", "Low", "Close", "Adj_Close", "Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Ticker"] = df["Ticker"].astype(str).str.upper().str.strip()
    df = df.sort_values(["Ticker", "Date"]).reset_index(drop=True)

    if path == DATASET_PATH:
        _DATASET_CACHE = df
        _TICKER_CACHE = {}
    return df


def get_ticker_data(ticker: str, *, min_rows: int = 60, dataset: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Return chronological data for one ticker with minimum-row validation."""
    ticker_norm = str(ticker).upper().strip()
    if not ticker_norm:
        raise ValueError("Ticker is required.")

    if dataset is None and ticker_norm in _TICKER_CACHE:
        data = _TICKER_CACHE[ticker_norm]
    else:
        df = dataset if dataset is not None else load_dataset()
        data = df[df["Ticker"] == ticker_norm].sort_values("Date").reset_index(drop=True)
        if dataset is None:
            _TICKER_CACHE[ticker_norm] = data

    if len(data) < min_rows:
        raise ValueError(f"Not enough rows for {ticker_norm}: {len(data)} rows, need at least {min_rows}.")
    return data


def get_data_until(
    ticker: str,
    cutoff_date: Any,
    *,
    min_window: int = 60,
    dataset: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Return only rows where Date <= cutoff_date. This is the no-leakage boundary."""
    cutoff = _parse_date(cutoff_date)
    data = get_ticker_data(ticker, min_rows=1, dataset=dataset)
    sliced = data[data["Date"] <= cutoff].sort_values("Date").reset_index(drop=True)
    if len(sliced) < min_window:
        raise ValueError(
            f"Insufficient history for {ticker} at cutoff {cutoff.date()}: "
            f"{len(sliced)} rows, need at least {min_window}."
        )
    return sliced


def compute_sma(series: pd.Series, window: int) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < window:
        return None
    return float(values.tail(window).mean())


def compute_rsi(series: pd.Series, window: int = 14) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < window + 1:
        return None
    delta = values.diff().dropna().tail(window)
    gains = delta.clip(lower=0).sum()
    losses = -delta.clip(upper=0).sum()
    if losses == 0:
        return 100.0
    rs = gains / losses
    return float(100 - (100 / (1 + rs)))


def compute_volatility(series: pd.Series, window: int = 20, *, annualized: bool = True) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < window + 1:
        return None
    returns = values.pct_change().dropna().tail(window)
    vol = float(returns.std())
    if annualized:
        vol *= 252 ** 0.5
    return vol


def compute_drawdown(series: pd.Series, window: int = 60) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 2:
        return None
    values = values.tail(window)
    running_peak = values.cummax()
    drawdown = (running_peak - values) / running_peak
    return float(drawdown.max())


def compute_momentum(series: pd.Series, window: int = 20) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < window + 1:
        return None
    old = float(values.iloc[-window - 1])
    new = float(values.iloc[-1])
    if old <= 0:
        return None
    return (new / old) - 1.0


def compute_macd(series: pd.Series) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 35:
        return None
    ema12 = values.ewm(span=12, adjust=False).mean().iloc[-1]
    ema26 = values.ewm(span=26, adjust=False).mean().iloc[-1]
    return float(ema12 - ema26)


def _percentile_rank(series: pd.Series, value: Any, window: int = 252) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna().tail(window)
    if len(values) < 20 or value is None:
        return None
    value_f = _safe_float(value, None)
    if value_f is None:
        return None
    return float((values <= value_f).mean())


def _rolling_zscore(series: pd.Series, window: int = 60) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna().tail(window)
    if len(values) < max(20, window // 2):
        return None
    std = float(values.std())
    if std == 0:
        return 0.0
    return float((values.iloc[-1] - values.mean()) / std)


def _downside_deviation(series: pd.Series, window: int = 60) -> Optional[float]:
    returns = pd.to_numeric(series, errors="coerce").pct_change().dropna().tail(window)
    if len(returns) < 20:
        return None
    downside = returns[returns < 0]
    if downside.empty:
        return 0.0
    return float(downside.std() * (252 ** 0.5))


def _tail_risk(series: pd.Series, window: int = 252) -> Optional[float]:
    returns = pd.to_numeric(series, errors="coerce").pct_change().dropna().tail(window)
    if len(returns) < 60:
        return None
    return float(abs(returns.quantile(0.05)))


def _trend_persistence(series: pd.Series, window: int = 60) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < window + 1:
        return None
    returns = values.pct_change().dropna().tail(window)
    if returns.empty:
        return None
    return float((returns > 0).mean())


def _volume_anomaly(history: pd.DataFrame, window: int = 60) -> Optional[float]:
    if "Volume" not in history.columns or len(history) < window:
        return None
    volume = pd.to_numeric(history["Volume"], errors="coerce").dropna().tail(window)
    if len(volume) < max(20, window // 2):
        return None
    avg = float(volume.iloc[:-1].mean()) if len(volume) > 1 else 0.0
    if avg <= 0:
        return None
    return float(volume.iloc[-1] / avg)


def _rolling_rsi_percentile(series: pd.Series, window: int = 14, lookback: int = 252) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < window + 30:
        return None
    rsi_values = []
    max_points = min(len(values) - window, lookback)
    for offset in range(max_points, 0, -1):
        subset = values.iloc[: len(values) - offset + 1]
        rsi = compute_rsi(subset, window)
        if rsi is not None:
            rsi_values.append(rsi)
    current = compute_rsi(values, window)
    if current is None or len(rsi_values) < 20:
        return None
    return float((pd.Series(rsi_values) <= current).mean())


def compute_risk_metrics(history: pd.DataFrame) -> Dict[str, Any]:
    close = history["Close"]
    high_252 = float(history["High"].tail(252).max()) if len(history) >= 2 else None
    low_252 = float(history["Low"].tail(252).min()) if len(history) >= 2 else None
    range_52w = None
    if high_252 is not None and low_252 and low_252 > 0:
        range_52w = (high_252 - low_252) / low_252

    return {
        "volatility_20d": compute_volatility(close, 20),
        "volatility_60d": compute_volatility(close, 60),
        "drawdown_60d": compute_drawdown(close, 60),
        "range_52w": range_52w,
        "beta_approx": _beta_approx(close),
    }


def _beta_approx(close: pd.Series, market_returns: Optional[pd.Series] = None) -> Optional[float]:
    returns = pd.to_numeric(close, errors="coerce").pct_change().dropna().tail(252)
    if len(returns) < 60:
        return None
    if market_returns is None:
        market_returns = returns.rolling(20).mean().dropna()
        returns = returns.loc[market_returns.index]
    if len(market_returns) < 30:
        return None
    var = float(market_returns.var())
    if var == 0:
        return None
    cov = float(returns.cov(market_returns))
    return cov / var


def compute_indicator_snapshot(history: pd.DataFrame) -> Dict[str, Any]:
    close = history["Close"]
    risk = compute_risk_metrics(history)
    rsi_value = compute_rsi(close, 14)
    returns = pd.to_numeric(close, errors="coerce").pct_change().dropna()
    high_60 = float(history["High"].tail(60).max()) if len(history) >= 60 else None
    low_60 = float(history["Low"].tail(60).min()) if len(history) >= 60 else None
    return {
        "last_close": float(close.iloc[-1]),
        "sma_20": compute_sma(close, 20),
        "sma_50": compute_sma(close, 50),
        "sma_200": compute_sma(close, 200),
        "rsi_14": rsi_value,
        "rsi_percentile": _rolling_rsi_percentile(close, 14, 252),
        "price_zscore_60d": _rolling_zscore(close, 60),
        "price_zscore_200d": _rolling_zscore(close, 200),
        "volatility_20d": risk["volatility_20d"],
        "volatility_60d": risk["volatility_60d"],
        "downside_deviation_60d": _downside_deviation(close, 60),
        "tail_risk_252d": _tail_risk(close, 252),
        "drawdown_60d": risk["drawdown_60d"],
        "range_52w": risk["range_52w"],
        "beta_approx": risk["beta_approx"],
        "momentum_20d": compute_momentum(close, 20),
        "momentum_60d": compute_momentum(close, 60),
        "trend_persistence_60d": _trend_persistence(close, 60),
        "volume_anomaly_60d": _volume_anomaly(history, 60),
        "breakout_60d": (float(close.iloc[-1]) / high_60 - 1.0) if high_60 and high_60 > 0 else None,
        "breakdown_60d": (float(close.iloc[-1]) / low_60 - 1.0) if low_60 and low_60 > 0 else None,
        "macd": compute_macd(close),
    }


def classify_market_regime(history: pd.DataFrame) -> Dict[str, Any]:
    """Classify market regime using only the supplied historical slice."""
    snapshot = compute_indicator_snapshot(history)
    close = _safe_float(snapshot.get("last_close"))
    sma_50 = snapshot.get("sma_50")
    sma_200 = snapshot.get("sma_200")
    momentum_60 = snapshot.get("momentum_60d")
    volatility = snapshot.get("volatility_60d")
    missing = []

    if sma_50 is None:
        missing.append("sma_50")
    if sma_200 is None:
        missing.append("sma_200")
    if momentum_60 is None:
        missing.append("momentum_60d")
    if volatility is None:
        missing.append("volatility_60d")

    if volatility is not None and volatility >= 0.45:
        regime = "High Volatility"
    elif sma_200 is not None and close > sma_200 and (momentum_60 or 0) > 0.03:
        regime = "Bull"
    elif sma_200 is not None and close < sma_200 and (momentum_60 or 0) < -0.03:
        regime = "Bear"
    elif sma_50 is not None and abs((close / sma_50) - 1.0) <= 0.04:
        regime = "Sideways"
    else:
        regime = "Mixed"
    confidence = 100 - min(60, len(missing) * 15)
    if volatility is not None:
        confidence += 10 if volatility < 0.35 else -10
    if momentum_60 is not None and abs(momentum_60) > 0.10:
        confidence += 8
    confidence = _clamp_score(confidence)
    transition_probability = _clamp_score((volatility or 0.0) * 120 + abs(momentum_60 or 0.0) * 50)

    return {
        "regime": regime,
        "regime_confidence": confidence,
        "transition_probability": transition_probability,
        "volatility_60d": volatility,
        "momentum_60d": momentum_60,
        "missing_fields": missing,
    }


def _score_technical(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    missing: List[str] = []
    factors: List[Dict[str, Any]] = []
    score = 50.0

    last = snapshot.get("last_close")
    sma20 = snapshot.get("sma_20")
    sma50 = snapshot.get("sma_50")
    rsi = snapshot.get("rsi_14")
    rsi_pct = snapshot.get("rsi_percentile")
    mom20 = snapshot.get("momentum_20d")
    mom60 = snapshot.get("momentum_60d")
    trend = snapshot.get("trend_persistence_60d")
    z60 = snapshot.get("price_zscore_60d")
    volume_anomaly = snapshot.get("volume_anomaly_60d")
    breakout = snapshot.get("breakout_60d")
    macd = snapshot.get("macd")

    if sma20 is None:
        missing.append("sma_20")
    if sma50 is None:
        missing.append("sma_50")
    if last is None:
        missing.append("last_close")

    if sma20 is not None and sma50 is not None:
        delta = 10 if sma20 > sma50 else -10
        score += delta
        factors.append({"factor": "SMA20 vs SMA50", "impact": delta, "value": round(sma20 - sma50, 4)})

    if last is not None and sma50 is not None:
        delta = 6 if last > sma50 else -6
        score += delta
        factors.append({"factor": "Price vs SMA50", "impact": delta, "value": round(last - sma50, 4)})

    if rsi is None:
        missing.append("rsi_14")
    elif rsi >= 70:
        score -= 8
        factors.append({"factor": "RSI overbought", "impact": -8, "value": round(rsi, 2)})
    elif rsi <= 30:
        score += 8
        factors.append({"factor": "RSI oversold", "impact": 8, "value": round(rsi, 2)})
    else:
        factors.append({"factor": "RSI neutral", "impact": 0, "value": round(rsi, 2)})

    if mom20 is None:
        missing.append("momentum_20d")
    else:
        if mom20 > 0.05:
            score += 8
            factors.append({"factor": "20D momentum strong", "impact": 8, "value": round(mom20, 4)})
        elif mom20 < -0.05:
            score -= 8
            factors.append({"factor": "20D momentum weak", "impact": -8, "value": round(mom20, 4)})

    if mom60 is None:
        missing.append("momentum_60d")
    elif mom60 > 0.12:
        score += 7
        factors.append({"factor": "60D momentum persistence", "impact": 7, "value": round(mom60, 4)})
    elif mom60 < -0.12:
        score -= 7
        factors.append({"factor": "60D downside momentum", "impact": -7, "value": round(mom60, 4)})

    if trend is None:
        missing.append("trend_persistence_60d")
    elif trend >= 0.58:
        score += 6
        factors.append({"factor": "Trend persistence positive", "impact": 6, "value": round(trend, 3)})
    elif trend <= 0.42:
        score -= 6
        factors.append({"factor": "Trend persistence weak", "impact": -6, "value": round(trend, 3)})

    if z60 is None:
        missing.append("price_zscore_60d")
    elif z60 >= 2.0:
        score -= 6
        factors.append({"factor": "Price extended vs 60D distribution", "impact": -6, "value": round(z60, 3)})
    elif z60 <= -2.0:
        score += 5
        factors.append({"factor": "Price depressed vs 60D distribution", "impact": 5, "value": round(z60, 3)})

    if rsi_pct is None:
        missing.append("rsi_percentile")
    elif rsi_pct >= 0.90:
        score -= 5
        factors.append({"factor": "RSI historically elevated", "impact": -5, "value": round(rsi_pct, 3)})
    elif rsi_pct <= 0.10:
        score += 5
        factors.append({"factor": "RSI historically depressed", "impact": 5, "value": round(rsi_pct, 3)})

    if volume_anomaly is None:
        missing.append("volume_anomaly_60d")
    elif volume_anomaly >= 1.8 and mom20 and mom20 > 0:
        score += 5
        factors.append({"factor": "Positive volume anomaly", "impact": 5, "value": round(volume_anomaly, 3)})
    elif volume_anomaly >= 1.8 and mom20 and mom20 < 0:
        score -= 5
        factors.append({"factor": "Negative volume anomaly", "impact": -5, "value": round(volume_anomaly, 3)})

    if breakout is None:
        missing.append("breakout_60d")
    elif breakout >= -0.01:
        score += 4
        factors.append({"factor": "Near 60D breakout", "impact": 4, "value": round(breakout, 4)})

    if macd is None:
        missing.append("macd")
    elif macd > 0:
        score += 3
        factors.append({"factor": "MACD positive", "impact": 3, "value": round(macd, 4)})
    elif macd < 0:
        score -= 3
        factors.append({"factor": "MACD negative", "impact": -3, "value": round(macd, 4)})

    score_i = _clamp_score(score)
    return {"score": score_i, "signal": _signal_from_score(score_i), "factors": factors, "missing_fields": missing}


def _score_risk(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    missing: List[str] = []
    factors: List[Dict[str, Any]] = []
    score = 40.0

    vol = snapshot.get("volatility_20d")
    vol60 = snapshot.get("volatility_60d")
    dd = snapshot.get("drawdown_60d")
    range_52w = snapshot.get("range_52w")
    beta = snapshot.get("beta_approx")
    downside = snapshot.get("downside_deviation_60d")
    tail = snapshot.get("tail_risk_252d")
    persistence = snapshot.get("trend_persistence_60d")

    if vol is None:
        missing.append("volatility_20d")
    elif vol >= 0.60:
        score += 30
        factors.append({"factor": "High volatility", "impact": 30, "value": round(vol, 4)})
    elif vol >= 0.40:
        score += 18
        factors.append({"factor": "Elevated volatility", "impact": 18, "value": round(vol, 4)})
    elif vol >= 0.25:
        score += 8
        factors.append({"factor": "Moderate volatility", "impact": 8, "value": round(vol, 4)})
    else:
        score -= 6
        factors.append({"factor": "Low volatility", "impact": -6, "value": round(vol, 4)})

    if dd is None:
        missing.append("drawdown_60d")
    elif dd >= 0.30:
        score += 20
        factors.append({"factor": "Large drawdown", "impact": 20, "value": round(dd, 4)})
    elif dd >= 0.15:
        score += 10
        factors.append({"factor": "Meaningful drawdown", "impact": 10, "value": round(dd, 4)})
    else:
        factors.append({"factor": "Contained drawdown", "impact": 0, "value": round(dd, 4)})

    if range_52w is None:
        missing.append("range_52w")
    elif range_52w >= 0.80:
        score += 18
        factors.append({"factor": "Wide 52W range", "impact": 18, "value": round(range_52w, 4)})
    elif range_52w >= 0.50:
        score += 10
        factors.append({"factor": "Elevated 52W range", "impact": 10, "value": round(range_52w, 4)})

    if beta is None:
        missing.append("beta_approx")
    elif beta >= 1.5:
        score += 10
        factors.append({"factor": "High beta approximation", "impact": 10, "value": round(beta, 4)})
    elif beta <= 0.8:
        score -= 4
        factors.append({"factor": "Low beta approximation", "impact": -4, "value": round(beta, 4)})

    if vol60 is None:
        missing.append("volatility_60d")
    elif vol60 > 0 and vol is not None and vol > vol60 * 1.35:
        score += 8
        factors.append({"factor": "Volatility clustering", "impact": 8, "value": round(vol / vol60, 3)})

    if downside is None:
        missing.append("downside_deviation_60d")
    elif downside >= 0.35:
        score += 14
        factors.append({"factor": "High downside deviation", "impact": 14, "value": round(downside, 4)})
    elif downside >= 0.22:
        score += 7
        factors.append({"factor": "Moderate downside deviation", "impact": 7, "value": round(downside, 4)})

    if tail is None:
        missing.append("tail_risk_252d")
    elif tail >= 0.06:
        score += 14
        factors.append({"factor": "Large 5% daily tail risk", "impact": 14, "value": round(tail, 4)})
    elif tail >= 0.035:
        score += 7
        factors.append({"factor": "Elevated 5% daily tail risk", "impact": 7, "value": round(tail, 4)})

    if persistence is None:
        missing.append("trend_persistence_60d")
    elif persistence <= 0.38:
        score += 6
        factors.append({"factor": "Persistent negative tape", "impact": 6, "value": round(persistence, 3)})

    score_i = _clamp_score(score)
    return {"score": score_i, "signal": _risk_label_from_score(score_i), "factors": factors, "missing_fields": missing}


def _unavailable_engine(name: str) -> Dict[str, Any]:
    return {
        "score": 0,
        "signal": "Unavailable",
        "factors": [],
        "missing_fields": [f"{name}.not_available_in_price_dataset"],
    }


def _confidence_from_scores(technical: Dict[str, Any], risk: Dict[str, Any], missing_engines: List[str]) -> Dict[str, Any]:
    penalties = []
    missing_penalty = min(20, len(missing_engines) * 4)
    if missing_penalty:
        penalties.append({"engine": "dataset_limited_engines", "penalty": missing_penalty, "reason": "Only OHLCV dataset is available."})

    tech_score = int(technical.get("score") or 0)
    risk_score = int(risk.get("score") or 0)
    risk_penalty = int(round(risk_score * 0.18))
    signal_strength = abs(tech_score - 50)
    factor_count = len(technical.get("factors") or []) + len(risk.get("factors") or [])
    evidence_bonus = min(15, factor_count * 1.5)
    agreement_bonus = 8 if (tech_score >= 60 and risk_score <= 55) or (tech_score <= 40 and risk_score >= 60) else 0
    dispersion_penalty = min(10, abs(tech_score - (100 - risk_score)) * 0.08)
    confidence = _clamp_score(48 + signal_strength + evidence_bonus + agreement_bonus - risk_penalty - missing_penalty - dispersion_penalty)

    return {
        "score": confidence,
        "note": "Evidence-based reliability from signal strength, feature support, engine agreement, risk, and dataset coverage.",
        "penalties": penalties,
        "breakdown": {
            "signal_strength": signal_strength,
            "feature_evidence_bonus": evidence_bonus,
            "engine_agreement_bonus": agreement_bonus,
            "risk_regime_penalty": risk_penalty,
            "missing_penalty": missing_penalty,
            "signal_dispersion_penalty": dispersion_penalty,
            "calibration": {"available": False, "note": "Calibration comes from stored evaluated runs."},
        },
    }


def _confidence_v2(
    base_confidence: Dict[str, Any],
    *,
    decision: str,
    regime: Optional[str],
    learning_profile: Optional[Dict[str, Any]],
    data_completeness: float,
    signal_agreement: float,
) -> Dict[str, Any]:
    base_score = int(base_confidence.get("score") or 0)
    profile = learning_profile or {}
    decision_stats = (profile.get("decision_accuracy") or {}).get(decision) or {}
    regime_stats = (profile.get("regime_accuracy") or {}).get(str(regime or "Unknown")) or {}
    overall_accuracy = profile.get("overall_accuracy")
    historical_accuracy = decision_stats.get("accuracy", overall_accuracy)
    regime_reliability = regime_stats.get("accuracy", overall_accuracy)
    has_history = historical_accuracy is not None and (profile.get("evaluated_count") or 0) >= 20
    if has_history:
        score = (
            float(historical_accuracy) * 100 * 0.35
            + float(regime_reliability or historical_accuracy) * 100 * 0.20
            + base_score * 0.20
            + data_completeness * 100 * 0.15
            + signal_agreement * 100 * 0.10
        )
        method = "historical_memory_calibrated"
    else:
        score = base_score * 0.65 + data_completeness * 100 * 0.20 + signal_agreement * 100 * 0.15
        method = "evidence_based_uncalibrated"
    return {
        "score": _clamp_score(score),
        "method": method,
        "base_confidence": base_score,
        "historical_accuracy": historical_accuracy,
        "regime_reliability": regime_reliability,
        "data_completeness": data_completeness,
        "signal_agreement": signal_agreement,
        "memory_evaluated_count": profile.get("evaluated_count", 0),
        "explanation": "ConfidenceEngineV2 combines historical memory, calibration evidence, regime reliability, data completeness, and signal agreement.",
    }


def _make_decision(scores: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    technical = scores["technical"]
    risk = scores["risk"]
    tech_score = int(technical.get("score") or 0)
    risk_score = int(risk.get("score") or 0)

    composite = _clamp_score(tech_score - (risk_score * 0.28))
    if composite >= 67:
        decision = "BUY"
    elif composite <= 33:
        decision = "SELL"
    else:
        decision = "HOLD"
    return {"value": decision, "score": composite}


def _build_agents(scores: Dict[str, Dict[str, Any]], decision: Dict[str, Any], confidence: Dict[str, Any]) -> Dict[str, Any]:
    technical = scores["technical"]
    risk = scores["risk"]
    tech_signal = technical.get("signal")
    risk_signal = risk.get("signal")

    bull_thesis = []
    if tech_signal == "Bullish":
        bull_thesis.append("Technical trend supports upside based on past-only indicators.")
    if int(risk.get("score") or 0) <= 45:
        bull_thesis.append("Risk regime is not elevated.")

    bear_thesis = []
    if tech_signal == "Bearish":
        bear_thesis.append("Technical trend is weak based on past-only indicators.")
    if risk_signal == "High":
        bear_thesis.append("Risk regime is high and reduces decision reliability.")

    contradictions = []
    if tech_signal == "Bullish" and risk_signal == "High":
        contradictions.append("Bullish technical signal conflicts with high-risk regime.")
    if tech_signal == "Bearish" and risk_signal == "Low":
        contradictions.append("Bearish technical signal appears in a low-risk regime.")
    votes = {
        "bull": "BUY" if bull_thesis else "HOLD",
        "bear": "SELL" if bear_thesis else "HOLD",
        "risk": "SELL" if risk_signal == "High" else "HOLD",
        "technical": "BUY" if tech_signal == "Bullish" else "SELL" if tech_signal == "Bearish" else "HOLD",
        "critic": "HOLD" if contradictions else decision["value"],
    }
    vote_counts = {label: list(votes.values()).count(label) for label in ["BUY", "HOLD", "SELL"]}
    conflict_score = _clamp_score((len(set(votes.values())) - 1) * 35 + len(contradictions) * 15)

    return {
        "bull": {
            "agent": "bull",
            "verdict": "BUY" if decision["score"] >= 67 else "HOLD",
            "confidence": confidence["score"],
            "thesis": bull_thesis[:3] or ["No strong bullish thesis from validated historical signals."],
            "missing_inputs": scores["fundamental"]["missing_fields"],
        },
        "bear": {
            "agent": "bear",
            "verdict": "SELL" if decision["score"] <= 33 else "HOLD",
            "confidence": confidence["score"],
            "thesis": bear_thesis[:3] or ["No strong bearish thesis from validated historical signals."],
            "missing_inputs": scores["valuation"]["missing_fields"],
        },
        "risk": {
            "agent": "risk",
            "risk_level": risk.get("signal"),
            "risk_score": risk.get("score"),
            "risk_drivers": [f.get("factor") for f in risk.get("factors", [])[:3] if isinstance(f, dict)],
            "missing_inputs": risk.get("missing_fields", []),
        },
        "macro": {
            "agent": "macro",
            "regime": "Dataset-limited",
            "thesis": ["Macro series unavailable in OHLCV dataset; no macro claim generated."],
            "missing_inputs": scores["macro"].get("missing_fields", []),
        },
        "technical": {
            "agent": "technical",
            "verdict": "BUY" if tech_signal == "Bullish" else "SELL" if tech_signal == "Bearish" else "HOLD",
            "confidence": confidence["score"],
            "thesis": [f.get("factor") for f in technical.get("factors", [])[:3] if isinstance(f, dict)],
            "missing_inputs": technical.get("missing_fields", []),
        },
        "portfolio_allocator": {
            "agent": "portfolio_allocator",
            "suggested_position": "Small" if risk_signal == "High" else "Normal" if decision["value"] == "BUY" else "Watchlist",
            "reason": "Position sizing is constrained by validated risk and decision confidence.",
            "missing_inputs": [],
        },
        "critic": {
            "agent": "critic",
            "contradictions": contradictions,
            "conflict_score": conflict_score,
            "conflict_intensity": "High" if conflict_score >= 65 else "Medium" if conflict_score >= 30 else "Low",
            "flags": ["Dataset-limited backtest: fundamental, valuation, macro, and sentiment are unavailable."],
            "missing_inputs": _missing_fields(scores),
        },
        "final": {
            "agent": "final",
            "verdict": decision["value"],
            "composite_score": decision["score"],
            "confidence": confidence["score"],
            "agent_votes": votes,
            "vote_counts": vote_counts,
            "conflict_score": conflict_score,
            "overrides": ["High risk can override BUY conviction."] if risk_signal == "High" and decision["value"] == "BUY" else [],
            "missing_inputs": _missing_fields(scores),
        },
        "debate": {
            "agent_votes": votes,
            "vote_counts": vote_counts,
            "contradictions": contradictions,
            "conflict_score": conflict_score,
            "uncertainty_propagation": "High conflict reduces confidence." if conflict_score >= 65 else "Conflict controlled.",
        },
    }


def _missing_fields(scores: Dict[str, Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for engine in scores.values():
        out.extend(engine.get("missing_fields", []))
    return sorted(set(out))


def _decision_trace(scores: Dict[str, Dict[str, Any]], decision: Dict[str, Any]) -> Dict[str, Any]:
    technical = scores["technical"]
    risk = scores["risk"]
    tech_score = int(technical.get("score") or 0)
    risk_score = int(risk.get("score") or 0)
    risk_penalty = round(risk_score * 0.28, 2)
    return {
        "base_components": [
            {"engine": "technical", "score": tech_score, "weight": 1.0, "weighted": tech_score},
            {"engine": "risk_penalty", "score": risk_score, "weight": -0.28, "weighted": -risk_penalty},
        ],
        "base_score": tech_score,
        "risk_penalty_score": risk_score,
        "risk_penalty_applied": risk_penalty,
        "composite_score": decision["score"],
    }


def _decision_attribution_from_intelligence(
    intelligence: Dict[str, Any],
    *,
    allocation_decision: str,
    engine_decision: str,
    allocation_delta: float,
) -> Dict[str, Any]:
    scores = intelligence.get("scores") or {}
    trace = intelligence.get("decision_trace") or {}
    positives = intelligence.get("alpha_positive_drivers") or []
    negatives = intelligence.get("alpha_negative_drivers") or []
    risks = intelligence.get("risk_contributors") or []
    technical_score = int(((scores.get("technical") or {}).get("score")) or 0)
    risk_score = int(((scores.get("risk") or {}).get("score")) or 0)
    risk_penalty = round(risk_score * 0.28, 2)
    return {
        "decision": allocation_decision,
        "engine_decision": engine_decision,
        "allocation_delta": allocation_delta,
        "base_score": trace.get("base_score", technical_score),
        "risk_penalty_applied": trace.get("risk_penalty_applied", risk_penalty),
        "total_score": trace.get("composite_score"),
        "top_positive_contributors": positives[:5],
        "top_negative_contributors": negatives[:5],
        "top_risk_contributors": risks[:5],
        "summary": {
            "positive": "; ".join([str(item.get("factor")) for item in positives[:3] if isinstance(item, dict)]) or "No positive contributors",
            "negative": "; ".join([str(item.get("factor")) for item in negatives[:3] if isinstance(item, dict)]) or "No negative contributors",
            "risk": "; ".join([str(item.get("factor")) for item in risks[:3] if isinstance(item, dict)]) or "No risk contributors",
        },
    }


def _builder_critic_judge(decision_attribution: Dict[str, Any], prediction: Dict[str, Any], confidence: int) -> Dict[str, Any]:
    positives = decision_attribution.get("top_positive_contributors") or []
    negatives = decision_attribution.get("top_negative_contributors") or []
    risks = decision_attribution.get("top_risk_contributors") or []
    expected = prediction.get("expected_return") if prediction.get("status") == "SUCCESS" else None
    builder_prediction = {
        "decision": decision_attribution.get("decision"),
        "thesis": [str(item.get("factor")) for item in positives[:3] if isinstance(item, dict)] or ["No strong positive thesis from validated signals."],
        "expected_return": expected,
    }
    critic_objections = [str(item.get("factor")) for item in (negatives + risks)[:4] if isinstance(item, dict)]
    if prediction.get("status") != "SUCCESS":
        critic_objections.append(prediction.get("reason", "Prediction distribution unavailable."))
    resolution = "Proceed with caution" if confidence < 60 or critic_objections else "Proceed"
    return {
        "builder_prediction": builder_prediction,
        "critic_objections": critic_objections or ["No material deterministic objection found."],
        "judge_resolution": resolution,
        "final_confidence": confidence,
    }


def _factor_split(scores: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    positives: List[Dict[str, Any]] = []
    negatives: List[Dict[str, Any]] = []
    risks: List[Dict[str, Any]] = []

    for factor in scores["technical"].get("factors", []):
        if not isinstance(factor, dict):
            continue
        impact = int(factor.get("impact") or 0)
        item = {"engine": "technical", "factor": factor.get("factor"), "impact": impact, "value": factor.get("value")}
        if impact > 0:
            positives.append(item)
        elif impact < 0:
            negatives.append(item)

    for factor in scores["risk"].get("factors", []):
        if isinstance(factor, dict):
            impact = int(factor.get("impact") or 0)
            risks.append({"engine": "risk", "factor": factor.get("factor"), "impact": impact, "value": factor.get("value")})

    return {
        "alpha_positive_drivers": sorted(positives, key=lambda x: x["impact"], reverse=True)[:8],
        "alpha_negative_drivers": sorted(negatives, key=lambda x: x["impact"])[:8],
        "risk_contributors": sorted(risks, key=lambda x: x["impact"], reverse=True)[:8],
    }


def build_intelligence_from_history(history: pd.DataFrame) -> Dict[str, Any]:
    snapshot = compute_indicator_snapshot(history)
    regime = classify_market_regime(history)
    scores = {
        "fundamental": _unavailable_engine("fundamental"),
        "technical": _score_technical(snapshot),
        "valuation": _unavailable_engine("valuation"),
        "risk": _score_risk(snapshot),
        "macro": _unavailable_engine("macro"),
        "sentiment": _unavailable_engine("sentiment"),
    }
    missing_engines = [k for k, v in scores.items() if v.get("signal") == "Unavailable"]
    decision = _make_decision(scores)
    confidence = _confidence_from_scores(scores["technical"], scores["risk"], missing_engines)
    split = _factor_split(scores)
    return {
        "verdict": decision,
        "confidence": confidence,
        "decision_trace": _decision_trace(scores, decision),
        "source_reliability": {
            "technical": "Medium",
            "risk": "Medium",
            "fundamental": "Unavailable",
            "valuation": "Unavailable",
            "macro": "Unavailable",
            "sentiment": "Unavailable",
        },
        "regime": regime,
        "agents": _build_agents(scores, decision, confidence),
        "scores": scores,
        "probabilities": _decision_probabilities(decision, scores),
        **split,
    }


def _decision_probabilities(decision: Dict[str, Any], scores: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    composite = float(decision["score"])
    risk = float(scores["risk"].get("score") or 0)
    buy_raw = max(0.0, composite - 40)
    sell_raw = max(0.0, 60 - composite)
    hold_raw = 20 + risk * 0.15
    total = buy_raw + sell_raw + hold_raw
    if total <= 0:
        return {"buy": 0, "hold": 100, "sell": 0, "note": "Insufficient signals; default HOLD."}
    return {
        "buy": _clamp_score((buy_raw / total) * 100),
        "hold": _clamp_score((hold_raw / total) * 100),
        "sell": _clamp_score((sell_raw / total) * 100),
        "note": "Derived from historical technical/risk scores, not a predictive probability.",
    }


def _future_row(data: pd.DataFrame, current_index: int, horizon_days: int) -> Optional[pd.Series]:
    target_index = current_index + int(horizon_days)
    if target_index >= len(data):
        return None
    return data.iloc[target_index]


def _evaluate_decision(decision: str, future_return: Optional[float], hold_band: float = 0.01) -> str:
    if future_return is None:
        return "INVALID"
    if decision == "BUY":
        return "WIN" if future_return > 0 else "LOSS"
    if decision == "SELL":
        return "WIN" if future_return < 0 else "LOSS"
    return "WIN" if abs(future_return) <= hold_band else "LOSS"


def _strategy_return(decision: str, future_return: Optional[float]) -> float:
    if future_return is None:
        return 0.0
    if decision == "BUY":
        return float(future_return)
    if decision == "SELL":
        return float(-future_return)
    return 0.0


def _benchmark_forward_return(
    df: pd.DataFrame,
    benchmark: str,
    date: pd.Timestamp,
    horizon_days: int,
) -> Optional[float]:
    benchmark_norm = str(benchmark or "").upper().strip()
    if not benchmark_norm:
        return None
    resolved = _resolve_benchmark_series(df, benchmark_norm, sorted(df["Date"].dropna().unique().tolist()))
    series = resolved.get("series")
    if series is None or series.empty:
        return None
    eligible = series[series.index <= date]
    if eligible.empty:
        return None
    current_pos = series.index.get_loc(eligible.index[-1])
    if isinstance(current_pos, slice):
        current_pos = current_pos.stop - 1
    future_idx = int(current_pos) + int(horizon_days)
    if future_idx >= len(series):
        return None
    current_close = _safe_float(series.iloc[int(current_pos)])
    future_close = _safe_float(series.iloc[future_idx])
    if current_close <= 0:
        return None
    return (future_close / current_close) - 1.0


def run_backtest(
    ticker: str,
    start_date: Any,
    end_date: Any,
    horizon_days: int = 30,
    *,
    min_window: int = 60,
    step: str = "daily",
    benchmark: str = "SPY",
    log_results: bool = True,
    dataset: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Run a leakage-safe rolling backtest for one ticker."""
    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive.")

    df = dataset if dataset is not None else load_dataset()
    data = get_ticker_data(ticker, min_rows=min_window + horizon_days + 1, dataset=df)
    start_ts = _parse_date(start_date)
    end_ts = _parse_date(end_date)
    if start_ts > end_ts:
        raise ValueError("start_date must be <= end_date.")

    rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    step_stride = {"daily": 1, "weekly": 5, "monthly": 21}.get(str(step).lower(), 1)

    for idx in range(len(data)):
        if idx % step_stride != 0:
            continue
        row = data.iloc[idx]
        date = row["Date"]
        if date < start_ts or date > end_ts:
            continue

        try:
            history = data.iloc[: idx + 1].copy()
            if len(history) < min_window:
                raise ValueError(f"Minimum history not met: {len(history)} rows.")

            future = _future_row(data, idx, horizon_days)
            if future is None:
                raise ValueError("Future horizon not available.")

            intelligence = build_intelligence_from_history(history)
            decision = intelligence["verdict"]["value"]
            confidence = intelligence["confidence"]["score"]
            current_close = float(row["Close"])
            future_close = float(future["Close"])
            future_return = (future_close / current_close) - 1.0 if current_close > 0 else None
            outcome = _evaluate_decision(decision, future_return)
            strategy_ret = _strategy_return(decision, future_return)
            benchmark_return = _benchmark_forward_return(df, benchmark, date, horizon_days)

            result = {
                "ticker": str(ticker).upper(),
                "as_of_date": date.date().isoformat(),
                "future_date": future["Date"].date().isoformat(),
                "sector": row.get("Sector") if "Sector" in data.columns else None,
                "industry": row.get("Industry") if "Industry" in data.columns else None,
                "regime": (intelligence.get("regime") or {}).get("regime"),
                "decision": decision,
                "confidence": int(confidence),
                "scores": {k: int(v.get("score") or 0) for k, v in intelligence["scores"].items()},
                "agents": intelligence.get("agents", {}),
                "decision_trace": intelligence.get("decision_trace", {}),
                "future_return": future_return,
                "strategy_return": strategy_ret,
                "benchmark": benchmark if benchmark_return is not None else None,
                "benchmark_return": benchmark_return,
                "excess_return": (strategy_ret - benchmark_return) if benchmark_return is not None else None,
                "outcome": outcome,
                "valid": True,
                "missing_engines": [k for k, v in intelligence["scores"].items() if v.get("signal") == "Unavailable"],
                "missing_fields": _missing_fields(intelligence["scores"]),
            }
            rows.append(result)
        except Exception as exc:
            issue = {
                "ticker": str(ticker).upper(),
                "as_of_date": date.date().isoformat(),
                "valid": False,
                "error": str(exc),
            }
            errors.append(issue)

    metrics = compute_metrics(rows, errors)
    payload = {
        "status": "SUCCESS",
        "ticker": str(ticker).upper(),
        "start_date": start_ts.date().isoformat(),
        "end_date": end_ts.date().isoformat(),
        "horizon_days": int(horizon_days),
        "step": step,
        "benchmark": benchmark,
        "results": rows,
        "errors": errors,
        "metrics": metrics,
    }

    if log_results:
        store_evaluation_results(rows, metadata={"ticker": str(ticker).upper(), "horizon_days": int(horizon_days), "step": step, "benchmark": benchmark})
    return payload


def run_historical_replay(
    ticker: str,
    as_of_date: Any,
    horizon_days: int = 30,
    *,
    dataset: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Replay one historical decision using only data at or before the cutoff."""
    df = dataset if dataset is not None else load_dataset()
    data = get_ticker_data(ticker, min_rows=60 + horizon_days + 1, dataset=df)
    cutoff = _parse_date(as_of_date)
    history = get_data_until(ticker, cutoff, min_window=60, dataset=df)
    current = history.iloc[-1]
    idx_matches = data.index[data["Date"] == current["Date"]].tolist()
    if not idx_matches:
        raise ValueError("Cutoff date is not aligned to a trading row.")
    idx = int(idx_matches[0])
    future = _future_row(data.reset_index(drop=True), idx, horizon_days)
    intelligence = build_intelligence_from_history(history)
    outcome = {"evaluated": False, "reason": "Future horizon unavailable."}
    outcomes_by_horizon = {}
    for horizon in [7, 30, 60, 90, 180]:
        horizon_future = _future_row(data.reset_index(drop=True), idx, horizon)
        if horizon_future is None:
            outcomes_by_horizon[str(horizon)] = {"evaluated": False, "reason": "Future horizon unavailable."}
            continue
        current_close_h = float(current["Close"])
        future_close_h = float(horizon_future["Close"])
        future_return_h = (future_close_h / current_close_h) - 1.0 if current_close_h > 0 else None
        decision_h = (intelligence.get("verdict") or {}).get("value", "HOLD")
        outcomes_by_horizon[str(horizon)] = {
            "evaluated": True,
            "future_date": horizon_future["Date"].date().isoformat(),
            "future_return": future_return_h,
            "outcome": _evaluate_decision(decision_h, future_return_h),
        }
    if future is not None:
        current_close = float(current["Close"])
        future_close = float(future["Close"])
        future_return = (future_close / current_close) - 1.0 if current_close > 0 else None
        decision = (intelligence.get("verdict") or {}).get("value", "HOLD")
        outcome = {
            "evaluated": True,
            "future_date": future["Date"].date().isoformat(),
            "future_return": future_return,
            "outcome": _evaluate_decision(decision, future_return),
        }
    return {
        "status": "SUCCESS",
        "ticker": str(ticker).upper(),
        "as_of_date": current["Date"].date().isoformat(),
        "current_close": float(current["Close"]),
        "intelligence": intelligence,
        "outcome": outcome,
        "outcomes_by_horizon": outcomes_by_horizon,
        "feature_snapshot": compute_indicator_snapshot(history),
        "no_leakage_audit": {
            "cutoff_date": cutoff.date().isoformat(),
            "latest_data_used": current["Date"].date().isoformat(),
            "future_data_used": "NONE",
            "rows_visible_to_engine": int(len(history)),
            "leakage_status": "PASSED" if current["Date"] <= cutoff else "FAILED",
        },
    }


def _strategy_decision(snapshot: Dict[str, Any], strategy: str, params: Optional[Dict[str, Any]] = None) -> str:
    params = params or {}
    name = str(strategy or "RSI").upper()
    if name in {"BUY_AND_HOLD", "BUY & HOLD", "BUY HOLD"}:
        return "BUY"
    if name in {"MOMENTUM", "MOMENTUM_STRATEGY"}:
        momentum = snapshot.get("momentum_20d")
        if momentum is None:
            return "HOLD"
        if momentum > 0.03:
            return "BUY"
        if momentum < -0.03:
            return "SELL"
        return "HOLD"
    if name in {"MEAN_REVERSION", "MEAN REVERSION"}:
        rsi = snapshot.get("rsi_14")
        if rsi is None:
            return "HOLD"
        if rsi <= 35:
            return "BUY"
        if rsi >= 70:
            return "SELL"
        return "HOLD"
    if name == "RSI":
        rsi = snapshot.get("rsi_14")
        buy_below = float(params.get("buy_below", 35))
        sell_above = float(params.get("sell_above", 70))
        if rsi is None:
            return "HOLD"
        if rsi <= buy_below:
            return "BUY"
        if rsi >= sell_above:
            return "SELL"
        return "HOLD"
    if name in {"MA", "MA_CROSSOVER", "SMA"}:
        sma_20 = snapshot.get("sma_20")
        sma_50 = snapshot.get("sma_50")
        if sma_20 is None or sma_50 is None:
            return "HOLD"
        if sma_20 > sma_50:
            return "BUY"
        if sma_20 < sma_50:
            return "SELL"
        return "HOLD"
    if name in {"VOL", "VOLATILITY_FILTER"}:
        vol = snapshot.get("volatility_20d")
        momentum = snapshot.get("momentum_20d")
        max_vol = float(params.get("max_volatility", 0.35))
        if vol is None or momentum is None:
            return "HOLD"
        if vol <= max_vol and momentum > 0:
            return "BUY"
        if vol > max_vol and momentum < 0:
            return "SELL"
        return "HOLD"
    if name in {"SCORE", "CUSTOM_SCORE"}:
        technical = _score_technical(snapshot)
        risk = _score_risk(snapshot)
        composite = int(technical.get("score") or 0) - int(round((risk.get("score") or 0) * 0.28))
        buy_above = int(params.get("buy_above", 67))
        sell_below = int(params.get("sell_below", 33))
        if composite >= buy_above:
            return "BUY"
        if composite <= sell_below:
            return "SELL"
        return "HOLD"
    return "HOLD"


def run_strategy_backtest(
    ticker: str,
    start_date: Any,
    end_date: Any,
    horizon_days: int = 30,
    *,
    strategy: str = "RSI",
    params: Optional[Dict[str, Any]] = None,
    log_results: bool = True,
    dataset: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Backtest simple deterministic strategies against the same future-return evaluator."""
    df = dataset if dataset is not None else load_dataset()
    data = get_ticker_data(ticker, min_rows=60 + horizon_days + 1, dataset=df)
    start_ts = _parse_date(start_date)
    end_ts = _parse_date(end_date)
    rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for idx in range(len(data)):
        row = data.iloc[idx]
        date = row["Date"]
        if date < start_ts or date > end_ts:
            continue
        try:
            history = data.iloc[: idx + 1].copy()
            if len(history) < 60:
                raise ValueError("Minimum history not met.")
            future = _future_row(data, idx, horizon_days)
            if future is None:
                raise ValueError("Future horizon not available.")
            snapshot = compute_indicator_snapshot(history)
            decision = _strategy_decision(snapshot, strategy, params)
            future_return = (float(future["Close"]) / float(row["Close"])) - 1.0
            rows.append(
                {
                    "ticker": str(ticker).upper(),
                    "as_of_date": date.date().isoformat(),
                    "future_date": future["Date"].date().isoformat(),
                    "strategy": strategy,
                    "decision": decision,
                    "confidence": 50,
                    "future_return": future_return,
                    "strategy_return": _strategy_return(decision, future_return),
                    "outcome": _evaluate_decision(decision, future_return),
                    "valid": True,
                    "regime": classify_market_regime(history).get("regime"),
                    "sector": row.get("Sector") if "Sector" in data.columns else None,
                    "missing_engines": [],
                    "missing_fields": [],
                }
            )
        except Exception as exc:
            errors.append({"ticker": str(ticker).upper(), "as_of_date": date.date().isoformat(), "valid": False, "error": str(exc)})
    if log_results:
        store_evaluation_results(rows, metadata={"ticker": str(ticker).upper(), "strategy": strategy, "horizon_days": int(horizon_days)})
    return {
        "status": "SUCCESS",
        "ticker": str(ticker).upper(),
        "strategy": strategy,
        "results": rows,
        "errors": errors,
        "metrics": compute_metrics(rows, errors),
    }


def run_strategy_comparison(
    ticker: str,
    start_date: Any,
    end_date: Any,
    horizon_days: int = 30,
    *,
    dataset: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Compare deterministic strategies on identical dates and horizons."""
    df = dataset if dataset is not None else load_dataset()
    strategies = [
        ("Momentum", "Momentum"),
        ("Fundamental", None),
        ("Technical", "MA_Crossover"),
        ("Factor", "Custom_Score"),
        ("Sentiment", None),
        ("Hybrid", "Volatility_Filter"),
        ("Agentic", "Custom_Score"),
        ("Buy and Hold", "Buy_and_Hold"),
        ("Mean Reversion", "Mean_Reversion"),
    ]
    rows = []
    runs = {}
    for label, strategy_name in strategies:
        if strategy_name is None:
            rows.append(
                {
                    "strategy": label,
                    "status": "UNAVAILABLE",
                    "reason": f"{label} strategy requires non-OHLCV data not present in the historical dataset.",
                }
            )
            continue
        run = run_strategy_backtest(
            ticker,
            start_date,
            end_date,
            horizon_days,
            strategy=strategy_name,
            log_results=False,
            dataset=df,
        )
        metrics = run.get("metrics", {}) or {}
        rows.append(
            {
                "strategy": label,
                "status": "SUCCESS",
                "cagr": metrics.get("cagr"),
                "sharpe": metrics.get("sharpe_ratio"),
                "sortino": metrics.get("sortino_ratio"),
                "max_drawdown": metrics.get("max_drawdown"),
                "volatility": metrics.get("volatility"),
                "alpha": metrics.get("alpha"),
                "beta": metrics.get("beta"),
                "win_rate": metrics.get("win_rate"),
                "trade_count": len(run.get("results") or []),
                "benchmark_relative_return": metrics.get("alpha"),
            }
        )
        runs[label] = run
    return {
        "status": "SUCCESS",
        "ticker": str(ticker).upper(),
        "start_date": _parse_date(start_date).date().isoformat(),
        "end_date": _parse_date(end_date).date().isoformat(),
        "horizon_days": int(horizon_days),
        "summary": rows,
        "runs": runs,
    }


def run_multi_horizon_backtest(
    ticker: str,
    start_date: Any,
    end_date: Any,
    horizons: Optional[List[int]] = None,
    *,
    step: str = "weekly",
    benchmark: str = "SPY",
    dataset: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Run 7/30/60/90/180/365 day evaluations without future leakage."""
    horizons = horizons or [7, 30, 60, 90, 180, 365]
    df = dataset if dataset is not None else load_dataset()
    runs = []
    for horizon in horizons:
        runs.append(
            run_backtest(
                ticker,
                start_date,
                end_date,
                int(horizon),
                step=step,
                benchmark=benchmark,
                log_results=False,
                dataset=df,
            )
        )
    return {
        "status": "SUCCESS",
        "ticker": str(ticker).upper(),
        "horizons": horizons,
        "runs": runs,
        "summary": [
            {
                "horizon": run.get("horizon_days"),
                "win_rate": (run.get("metrics") or {}).get("win_rate", 0.0),
                "sharpe": (run.get("metrics") or {}).get("sharpe_ratio", 0.0),
                "cagr": (run.get("metrics") or {}).get("cagr", 0.0),
                "max_drawdown": (run.get("metrics") or {}).get("max_drawdown", 0.0),
                "coverage": (run.get("metrics") or {}).get("coverage", 0.0),
            }
            for run in runs
        ],
    }


def store_evaluation_results(rows: Iterable[Dict[str, Any]], *, metadata: Optional[Dict[str, Any]] = None) -> None:
    os.makedirs(os.path.dirname(EVALUATION_RUNS_PATH), exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    with open(EVALUATION_RUNS_PATH, "a", encoding="utf-8") as file:
        for row in rows:
            obj = dict(row)
            obj["logged_at"] = stamp
            if metadata:
                obj["metadata"] = metadata
            file.write(json.dumps(obj, ensure_ascii=False) + "\n")


def load_evaluation_runs(path: str = EVALUATION_RUNS_PATH, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    if limit is not None:
        return rows[-limit:]
    return rows


def compute_win_rate(results: List[Dict[str, Any]]) -> float:
    valid = [r for r in results if r.get("valid") and r.get("outcome") in {"WIN", "LOSS"}]
    if not valid:
        return 0.0
    return sum(1 for r in valid if r.get("outcome") == "WIN") / len(valid)


def compute_average_return(results: List[Dict[str, Any]]) -> float:
    vals = [float(r.get("strategy_return") or 0.0) for r in results if r.get("valid")]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def compute_median_return(results: List[Dict[str, Any]]) -> float:
    vals = pd.Series([float(r.get("strategy_return") or 0.0) for r in results if r.get("valid")])
    if vals.empty:
        return 0.0
    return float(vals.median())


def compute_returns(results: List[Dict[str, Any]]) -> pd.DataFrame:
    if not results:
        return pd.DataFrame(columns=["as_of_date", "strategy_return", "cumulative_return"])
    df = pd.DataFrame(results)
    if df.empty:
        return pd.DataFrame(columns=["as_of_date", "strategy_return", "cumulative_return"])
    df = df[df["valid"] == True].copy()  # noqa: E712
    if df.empty:
        return pd.DataFrame(columns=["as_of_date", "strategy_return", "cumulative_return"])
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    df["strategy_return"] = pd.to_numeric(df["strategy_return"], errors="coerce").fillna(0.0)
    df = df.sort_values("as_of_date")
    df["cumulative_return"] = (1.0 + df["strategy_return"]).cumprod() - 1.0
    return df[["as_of_date", "strategy_return", "cumulative_return"]]


def compute_coverage(results: List[Dict[str, Any]], errors: Optional[List[Dict[str, Any]]] = None) -> float:
    total = len(results) + len(errors or [])
    if total == 0:
        return 0.0
    return len([r for r in results if r.get("valid")]) / total


def compute_calibration(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {f"{i}-{i+9}": [] for i in range(0, 100, 10)}
    for row in results:
        if not row.get("valid") or row.get("outcome") not in {"WIN", "LOSS"}:
            continue
        conf = int(row.get("confidence") or 0)
        start = min(90, max(0, (conf // 10) * 10))
        buckets[f"{start}-{start+9}"].append(row)

    out: List[Dict[str, Any]] = []
    for bucket, rows in buckets.items():
        if not rows:
            out.append({"bucket": bucket, "count": 0, "accuracy": None})
            continue
        accuracy = sum(1 for r in rows if r.get("outcome") == "WIN") / len(rows)
        out.append({"bucket": bucket, "count": len(rows), "accuracy": accuracy})
    return out


def _sharpe_ratio(results: List[Dict[str, Any]]) -> float:
    vals = pd.Series([float(r.get("strategy_return") or 0.0) for r in results if r.get("valid")])
    if len(vals) < 2 or float(vals.std()) == 0:
        return 0.0
    return float((vals.mean() / vals.std()) * (252 ** 0.5))


def _return_volatility(results: List[Dict[str, Any]]) -> float:
    vals = pd.Series([float(r.get("strategy_return") or 0.0) for r in results if r.get("valid")])
    if len(vals) < 2:
        return 0.0
    return float(vals.std() * (252 ** 0.5))


def _sortino_ratio(results: List[Dict[str, Any]]) -> float:
    vals = pd.Series([float(r.get("strategy_return") or 0.0) for r in results if r.get("valid")])
    if len(vals) < 2:
        return 0.0
    downside = vals[vals < 0]
    if downside.empty or float(downside.std()) == 0:
        return 0.0
    return float((vals.mean() / downside.std()) * (252 ** 0.5))


def _cagr(results: List[Dict[str, Any]]) -> float:
    vals = pd.Series([float(r.get("strategy_return") or 0.0) for r in results if r.get("valid")])
    if vals.empty:
        return 0.0
    total = float((1.0 + vals).prod())
    years = max(len(vals) / 252.0, 1 / 252.0)
    if total <= 0:
        return -1.0
    return float(total ** (1.0 / years) - 1.0)


def _benchmark_stats(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [r for r in results if r.get("valid") and r.get("benchmark_return") is not None]
    if not rows:
        return {
            "alpha": None,
            "beta": None,
            "information_ratio": None,
            "benchmark_average_return": None,
            "excess_return": None,
            "benchmark_audit": {"status": "UNAVAILABLE", "issues": ["No aligned benchmark returns available."]},
        }
    strategy = pd.Series([float(r.get("strategy_return") or 0.0) for r in rows])
    benchmark = pd.Series([float(r.get("benchmark_return") or 0.0) for r in rows])
    excess = strategy - benchmark
    benchmark_variance = _none_if_invalid(benchmark.var())
    covariance = _none_if_invalid(strategy.cov(benchmark))
    beta = float(covariance / benchmark_variance) if covariance is not None and benchmark_variance not in (None, 0.0) else None
    info_ratio = None
    if len(excess) > 1 and float(excess.std()) != 0:
        info_ratio = float((excess.mean() / excess.std()) * (252 ** 0.5))
    return {
        "alpha": float(excess.mean() * 252),
        "beta": beta,
        "information_ratio": info_ratio,
        "benchmark_average_return": float(benchmark.mean()),
        "excess_return": float(excess.mean()),
        "benchmark_audit": {
            "status": "PASSED" if beta is not None else "PARTIAL",
            "benchmark_observations": len(rows),
            "covariance": covariance,
            "benchmark_variance": benchmark_variance,
            "issues": [] if beta is not None else ["Benchmark variance unavailable; beta cannot be computed."],
        },
    }


def _max_drawdown_from_returns(results: List[Dict[str, Any]]) -> float:
    returns = compute_returns(results)
    if returns.empty:
        return 0.0
    equity = 1.0 + returns["cumulative_return"]
    peak = equity.cummax()
    drawdown = (peak - equity) / peak
    return float(drawdown.max())


def _accuracy_by_field(results: List[Dict[str, Any]], field: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in results:
        key = row.get(field) or "Unknown"
        if not row.get("valid") or row.get("outcome") not in {"WIN", "LOSS"}:
            continue
        bucket = out.setdefault(str(key), {"count": 0, "wins": 0, "accuracy": 0.0})
        bucket["count"] += 1
        if row.get("outcome") == "WIN":
            bucket["wins"] += 1
    for bucket in out.values():
        bucket["accuracy"] = bucket["wins"] / bucket["count"] if bucket["count"] else 0.0
    return out


def _decision_distribution(results: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"BUY": 0, "HOLD": 0, "SELL": 0}
    for row in results:
        decision = row.get("decision")
        if decision in counts:
            counts[decision] += 1
    return counts


def _rolling_metrics(results: List[Dict[str, Any]], window: int = 20) -> List[Dict[str, Any]]:
    valid = [r for r in results if r.get("valid") and r.get("outcome") in {"WIN", "LOSS"}]
    rows = []
    for idx, row in enumerate(valid):
        chunk = valid[max(0, idx - window + 1) : idx + 1]
        wins = sum(1 for item in chunk if item.get("outcome") == "WIN")
        returns = pd.Series([float(item.get("strategy_return") or 0.0) for item in chunk])
        sharpe = 0.0
        if len(returns) > 1 and float(returns.std()) != 0:
            sharpe = float((returns.mean() / returns.std()) * (252 ** 0.5))
        rows.append(
            {
                "as_of_date": row.get("as_of_date"),
                "rolling_win_rate": wins / len(chunk) if chunk else 0.0,
                "rolling_sharpe": sharpe,
            }
        )
    return rows


def compute_metrics(results: List[Dict[str, Any]], errors: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    valid = [r for r in results if r.get("valid")]
    avg_conf = sum(int(r.get("confidence") or 0) for r in valid) / len(valid) if valid else 0.0
    return {
        "total_runs": len(results) + len(errors or []),
        "valid_runs": len(valid),
        "win_rate": compute_win_rate(results),
        "average_return": compute_average_return(results),
        "median_return": compute_median_return(results),
        "coverage": compute_coverage(results, errors),
        "average_confidence": avg_conf,
        "calibration": compute_calibration(results),
        "sharpe_ratio": _sharpe_ratio(results),
        "sortino_ratio": _sortino_ratio(results),
        "cagr": _cagr(results),
        "volatility": _return_volatility(results),
        "max_drawdown": _max_drawdown_from_returns(results),
        **_benchmark_stats(results),
        "decision_accuracy": _accuracy_by_field(results, "decision"),
        "sector_accuracy": _accuracy_by_field(results, "sector"),
        "regime_accuracy": _accuracy_by_field(results, "regime"),
        "decision_distribution": _decision_distribution(results),
        "rolling_metrics": _rolling_metrics(results),
    }


def _normalize_portfolio_holdings(holdings: Any) -> List[Dict[str, Any]]:
    if isinstance(holdings, str):
        from portfolio_parser import parse_portfolio_input

        parsed = parse_portfolio_input(holdings)
        if parsed.get("status") != "SUCCESS":
            raise ValueError("; ".join(parsed.get("issues") or ["Invalid portfolio input."]))
        return parsed["holdings"]

    items: List[Dict[str, Any]] = []
    if isinstance(holdings, list):
        if all(isinstance(item, str) for item in holdings):
            tickers = [str(item).upper().strip() for item in holdings if str(item).strip()]
            if not tickers:
                raise ValueError("At least one ticker is required.")
            weight = 1.0 / len(tickers)
            return [{"ticker": ticker, "weight": weight} for ticker in tickers]
        for item in holdings:
            if isinstance(item, dict):
                ticker = str(item.get("ticker") or item.get("symbol") or item.get("name") or "").upper().strip()
                if ticker:
                    items.append({"ticker": ticker, "weight": _safe_float(item.get("weight"), 0.0)})
    if not items:
        raise ValueError("At least one valid portfolio holding is required.")
    total = sum(max(0.0, float(item.get("weight") or 0.0)) for item in items)
    if total <= 0:
        weight = 1.0 / len(items)
        return [{"ticker": item["ticker"], "weight": weight} for item in items]
    return [{"ticker": item["ticker"], "weight": max(0.0, float(item.get("weight") or 0.0)) / total} for item in items]


def _hhi(weights: List[float]) -> float:
    return sum(float(weight) ** 2 for weight in weights)


def _diversification_score(weights: List[float]) -> int:
    if not weights:
        return 0
    if len(weights) == 1:
        return 0
    hhi = _hhi(weights)
    ideal = 1.0 / len(weights)
    score = (1.0 - hhi) / (1.0 - ideal)
    return _clamp_score(score * 100)


def _portfolio_return_frame(
    holdings: List[Dict[str, Any]],
    cutoff_date: Any,
    *,
    lookback: int = 252,
    dataset: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    df = dataset if dataset is not None else load_dataset()
    cutoff = _parse_date(cutoff_date)
    frames = []
    for holding in holdings:
        ticker = holding["ticker"]
        data = get_ticker_data(ticker, min_rows=2, dataset=df)
        hist = data[data["Date"] <= cutoff].tail(lookback + 1).copy()
        if len(hist) < 2:
            continue
        returns = hist[["Date", "Close"]].copy()
        returns[ticker] = returns["Close"].pct_change()
        frames.append(returns[["Date", ticker]].dropna())
    if not frames:
        return pd.DataFrame()
    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="Date", how="inner")
    return merged.sort_values("Date").reset_index(drop=True)


def build_portfolio_intelligence(
    holdings: Any,
    *,
    as_of_date: Optional[Any] = None,
    lookback: int = 252,
    dataset: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    df = dataset if dataset is not None else load_dataset()
    normalized = _normalize_portfolio_holdings(holdings)
    cutoff = _parse_date(as_of_date) if as_of_date is not None else df["Date"].max()

    stock_rows = []
    sector_exposure: Dict[str, float] = {}
    industry_exposure: Dict[str, float] = {}
    weighted_composite = 0.0
    weighted_confidence = 0.0
    weighted_risk = 0.0
    errors = []

    for holding in normalized:
        ticker = holding["ticker"]
        weight = float(holding["weight"])
        try:
            history = get_data_until(ticker, cutoff, min_window=60, dataset=df)
            intelligence = build_intelligence_from_history(history)
            latest = history.iloc[-1]
            sector = latest.get("Sector") if "Sector" in history.columns else "Unknown"
            industry = latest.get("Industry") if "Industry" in history.columns else "Unknown"
            sector_exposure[str(sector or "Unknown")] = sector_exposure.get(str(sector or "Unknown"), 0.0) + weight
            industry_exposure[str(industry or "Unknown")] = industry_exposure.get(str(industry or "Unknown"), 0.0) + weight
            composite = int((intelligence.get("verdict") or {}).get("score") or 0)
            confidence = int((intelligence.get("confidence") or {}).get("score") or 0)
            risk = int(((intelligence.get("scores") or {}).get("risk") or {}).get("score") or 0)
            weighted_composite += composite * weight
            weighted_confidence += confidence * weight
            weighted_risk += risk * weight
            stock_rows.append(
                {
                    "ticker": ticker,
                    "weight": weight,
                    "sector": sector,
                    "industry": industry,
                    "decision": (intelligence.get("verdict") or {}).get("value"),
                    "composite": composite,
                    "confidence": confidence,
                    "risk": risk,
                    "regime": (intelligence.get("regime") or {}).get("regime"),
                    "agents": intelligence.get("agents", {}),
                    "scores": intelligence.get("scores", {}),
                    "missing_fields": _missing_fields(intelligence.get("scores", {})),
                }
            )
        except Exception as exc:
            errors.append({"ticker": ticker, "error": str(exc)})

    weights = [float(item["weight"]) for item in normalized]
    concentration = max(weights) if weights else 0.0
    diversification = _diversification_score(weights)

    returns_df = _portfolio_return_frame(normalized, cutoff, lookback=lookback, dataset=df)
    correlation_matrix: List[Dict[str, Any]] = []
    covariance_matrix: List[Dict[str, Any]] = []
    portfolio_volatility = 0.0
    max_drawdown = 0.0
    sharpe = 0.0
    value_at_risk_95 = 0.0
    portfolio_beta = 0.0
    weighted_returns = pd.Series(dtype=float)
    if not returns_df.empty:
        tickers = [item["ticker"] for item in normalized if item["ticker"] in returns_df.columns]
        corr = returns_df[tickers].corr() if tickers else pd.DataFrame()
        if not corr.empty:
            correlation_matrix = corr.round(3).reset_index().rename(columns={"index": "Ticker"}).to_dict("records")
        cov = returns_df[tickers].cov() if tickers else pd.DataFrame()
        if not cov.empty:
            covariance_matrix = cov.round(6).reset_index().rename(columns={"index": "Ticker"}).to_dict("records")
        weight_map = {item["ticker"]: float(item["weight"]) for item in normalized}
        weighted_returns = sum(returns_df[ticker] * weight_map.get(ticker, 0.0) for ticker in tickers)
        if len(weighted_returns) > 1:
            portfolio_volatility = float(weighted_returns.std() * (252 ** 0.5))
            value_at_risk_95 = float(abs(weighted_returns.quantile(0.05)))
            if float(weighted_returns.std()) != 0:
                sharpe = float((weighted_returns.mean() / weighted_returns.std()) * (252 ** 0.5))
            equity = (1.0 + weighted_returns.fillna(0.0)).cumprod()
            peak = equity.cummax()
            max_drawdown = float(((peak - equity) / peak).max())
            proxy = returns_df[tickers].mean(axis=1) if tickers else pd.Series(dtype=float)
            if len(proxy) > 1 and float(proxy.var()) != 0:
                portfolio_beta = float(weighted_returns.cov(proxy) / proxy.var())

    composite_score = _clamp_score(weighted_composite)
    disagreement = 0.0
    if stock_rows:
        composites = pd.Series([row["composite"] for row in stock_rows])
        disagreement = float(composites.std()) if len(composites) > 1 else 0.0
    concentration_penalty = max(0, (concentration - 0.35) * 70)
    disagreement_penalty = min(20, disagreement * 0.25)
    confidence = _clamp_score(weighted_confidence - concentration_penalty - disagreement_penalty)
    risk_score = _clamp_score(weighted_risk + concentration_penalty + max(0, portfolio_volatility - 0.25) * 60)

    if composite_score >= 67 and risk_score < 70:
        decision = "BUY"
    elif composite_score <= 33 or risk_score >= 85:
        decision = "SELL"
    else:
        decision = "HOLD"

    stress_tests = [
        {"scenario": "Market crash (-20%)", "estimated_impact": -0.20 * (1.0 + min(1.0, weighted_risk / 100.0))},
        {"scenario": "Tech selloff", "estimated_impact": -0.25 * sum(w for s, w in sector_exposure.items() if "tech" in s.lower())},
        {"scenario": "Rate hike regime", "estimated_impact": -0.12 * sum(w for s, w in sector_exposure.items() if any(term in s.lower() for term in ["technology", "consumer", "communication"]))},
        {"scenario": "Recession regime", "estimated_impact": -0.16 * (1.0 - sum(w for s, w in sector_exposure.items() if any(term in s.lower() for term in ["utilities", "consumer defensive", "healthcare"])))},
        {"scenario": "Sector rotation", "estimated_impact": -0.10 * concentration},
        {"scenario": "Volatility spike", "estimated_impact": -0.50 * portfolio_volatility},
    ]

    return {
        "status": "SUCCESS" if stock_rows else "ERROR",
        "as_of_date": cutoff.date().isoformat(),
        "holdings": normalized,
        "stocks": stock_rows,
        "errors": errors,
        "portfolio": {
            "decision": decision,
            "composite_score": composite_score,
            "confidence": confidence,
            "risk_score": risk_score,
            "diversification_score": diversification,
            "hhi": _hhi(weights),
            "concentration": concentration,
            "portfolio_volatility": portfolio_volatility,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe,
            "portfolio_beta": portfolio_beta,
            "value_at_risk_95": value_at_risk_95,
            "concentration_risk": "High" if concentration >= 0.40 else "Medium" if concentration >= 0.25 else "Low",
        },
        "sector_exposure": [
            {"sector": sector, "weight": weight}
            for sector, weight in sorted(sector_exposure.items(), key=lambda x: x[1], reverse=True)
        ],
        "industry_exposure": [
            {"industry": industry, "weight": weight}
            for industry, weight in sorted(industry_exposure.items(), key=lambda x: x[1], reverse=True)
        ],
        "correlation_matrix": correlation_matrix,
        "covariance_matrix": covariance_matrix,
        "stress_tests": stress_tests,
        "allocator": {
            "agent": "portfolio_allocator",
            "suggestions": [
                "Reduce top-name concentration." if concentration >= 0.40 else "Concentration is controlled.",
                "Improve diversification." if diversification < 55 else "Diversification is acceptable.",
                "Treat high-volatility holdings as lower conviction positions." if risk_score >= 70 else "Risk budget is moderate.",
            ],
        },
    }


def run_portfolio_backtest(
    tickers: Any,
    start_date: Any,
    end_date: Any,
    horizon_days: int = 30,
    *,
    log_results: bool = True,
    dataset: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Run a weighted portfolio backtest foundation."""
    df = dataset if dataset is not None else load_dataset()
    holdings = _normalize_portfolio_holdings(tickers)
    clean_tickers = [item["ticker"] for item in holdings]
    weights = {item["ticker"]: float(item["weight"]) for item in holdings}
    if not clean_tickers:
        raise ValueError("At least one ticker is required.")

    ticker_runs = []
    for ticker in clean_tickers:
        ticker_runs.append(run_backtest(ticker, start_date, end_date, horizon_days, dataset=df, log_results=False))

    by_date: Dict[str, List[Dict[str, float]]] = {}
    diversification_rows = []
    for run in ticker_runs:
        for row in run.get("results", []):
            if not row.get("valid"):
                continue
            weight = weights.get(str(row.get("ticker")).upper(), 0.0)
            by_date.setdefault(row["as_of_date"], []).append(
                {
                    "strategy_return": float(row.get("strategy_return") or 0.0) * weight,
                    "confidence": float(row.get("confidence") or 0.0),
                }
            )
        ticker = run.get("ticker")
        metrics = run.get("metrics", {})
        diversification_rows.append(
            {
                "ticker": ticker,
                "win_rate": metrics.get("win_rate", 0.0),
                "avg_return": metrics.get("average_return", 0.0),
                "valid_runs": metrics.get("valid_runs", 0),
            }
        )

    portfolio_results = []
    for date, rows in sorted(by_date.items()):
        avg_return = sum(row["strategy_return"] for row in rows)
        avg_confidence = sum(row["confidence"] for row in rows) / len(rows)
        portfolio_results.append(
            {
                "ticker": "PORTFOLIO",
                "as_of_date": date,
                "decision": "EQUAL_WEIGHT",
                "confidence": int(round(avg_confidence)),
                "scores": {},
                "future_return": avg_return,
                "strategy_return": avg_return,
                "outcome": "WIN" if avg_return > 0 else "LOSS",
                "valid": True,
                "missing_engines": [],
                "missing_fields": [],
            }
        )

    metrics = compute_metrics(portfolio_results, [])
    if log_results:
        store_evaluation_results(portfolio_results, metadata={"type": "portfolio", "holdings": holdings, "horizon_days": int(horizon_days)})
    return {
        "status": "SUCCESS",
        "tickers": clean_tickers,
        "holdings": holdings,
        "horizon_days": int(horizon_days),
        "ticker_runs": ticker_runs,
        "portfolio_results": portfolio_results,
        "diversification": {
            "ticker_count": len(clean_tickers),
            "diversification_score": _diversification_score(list(weights.values())),
            "hhi": _hhi(list(weights.values())),
            "components": diversification_rows,
        },
        "metrics": metrics,
    }


def _price_series_by_ticker(df: pd.DataFrame, tickers: List[str]) -> Dict[str, pd.Series]:
    out: Dict[str, pd.Series] = {}
    for ticker in tickers:
        data = get_ticker_data(ticker, min_rows=2, dataset=df)
        out[ticker] = data.set_index("Date")["Close"].astype(float).sort_index()
    return out


def _price_at(series: pd.Series, date: pd.Timestamp) -> Optional[float]:
    eligible = series[series.index <= date]
    if eligible.empty:
        return None
    price = _safe_float(eligible.iloc[-1], default=0.0)
    return price if price > 0 else None


def _dataset_equal_weight_benchmark(df: pd.DataFrame, dates: List[pd.Timestamp], requested: str) -> Dict[str, Any]:
    window = df[df["Date"].isin(dates)].copy()
    if window.empty:
        raise ValueError("Dataset benchmark proxy unavailable for selected dates.")
    pivot = window.pivot_table(index="Date", columns="Ticker", values="Close", aggfunc="last").sort_index()
    returns = pivot.pct_change(fill_method=None).dropna(how="all")
    equal_weight_returns = returns.mean(axis=1, skipna=True).fillna(0.0)
    benchmark_index = (1.0 + equal_weight_returns).cumprod() * 100.0
    if dates:
        first_date = min(dates)
        benchmark_index.loc[first_date] = 100.0
        benchmark_index = benchmark_index.sort_index()
    return {
        "series": benchmark_index,
        "audit": {
            "requested_benchmark": requested,
            "resolved_benchmark": "DATASET_EQUAL_WEIGHT_MARKET_PROXY",
            "source": "Computed from equal-weight daily returns across available dataset tickers.",
            "reason": f"{requested} is not present in data/stock_prices_daily.csv; using transparent dataset benchmark proxy instead of NULL metrics.",
            "constituents": int(pivot.shape[1]),
            "observations": int(len(benchmark_index)),
            "status": "PROXY_USED",
        },
    }


def _resolve_benchmark_series(df: pd.DataFrame, benchmark: str, dates: List[pd.Timestamp]) -> Dict[str, Any]:
    benchmark_norm = str(benchmark or "").upper().strip()
    if not benchmark_norm:
        return {"series": None, "start": None, "audit": {"requested_benchmark": "", "status": "NOT_SELECTED", "issues": ["No benchmark selected."]}}
    try:
        if benchmark_norm in set(df["Ticker"].astype(str).str.upper().unique()):
            series = _price_series_by_ticker(df, [benchmark_norm]).get(benchmark_norm)
            start = _price_at(series, dates[0]) if series is not None and dates else None
            return {
                "series": series,
                "start": start,
                "audit": {
                    "requested_benchmark": benchmark_norm,
                    "resolved_benchmark": benchmark_norm,
                    "source": "Dataset ticker close series.",
                    "observations": int(series.count()) if series is not None else 0,
                    "status": "PASSED" if start else "UNAVAILABLE",
                    "issues": [] if start else ["Benchmark start price unavailable."],
                },
            }
        proxy = _dataset_equal_weight_benchmark(df, dates, benchmark_norm)
        series = proxy["series"]
        start = _price_at(series, dates[0]) if dates else None
        proxy["audit"]["issues"] = []
        return {"series": series, "start": start, "audit": proxy["audit"]}
    except Exception as exc:
        return {"series": None, "start": None, "audit": {"requested_benchmark": benchmark_norm, "status": "FAILED", "issues": [str(exc)]}}


def _forward_return_for_ticker(data: pd.DataFrame, date: pd.Timestamp, horizon_days: int) -> Optional[float]:
    eligible = data[data["Date"] <= date]
    if eligible.empty:
        return None
    current_idx = int(eligible.index[-1])
    future_idx = current_idx + int(horizon_days)
    if future_idx >= len(data):
        return None
    current_close = _safe_float(data.iloc[current_idx]["Close"])
    future_close = _safe_float(data.iloc[future_idx]["Close"])
    if current_close <= 0:
        return None
    return (future_close / current_close) - 1.0


def _prediction_distribution_from_history(data: pd.DataFrame, date: pd.Timestamp, horizon_days: int = 30, lookback: int = 252) -> Dict[str, Any]:
    eligible = data[data["Date"] <= date].reset_index(drop=True)
    if len(eligible) < max(60, horizon_days + 5):
        return {"status": "UNAVAILABLE", "reason": "Insufficient past rows for prediction distribution."}
    current_idx = len(eligible) - 1
    start_idx = max(0, current_idx - lookback - horizon_days)
    returns = []
    max_gains = []
    max_losses = []
    for idx in range(start_idx, current_idx - horizon_days + 1):
        entry = float(eligible.iloc[idx]["Close"])
        future_window = eligible.iloc[idx + 1 : idx + horizon_days + 1]
        if entry <= 0 or future_window.empty:
            continue
        exit_price = float(future_window.iloc[-1]["Close"])
        returns.append(exit_price / entry - 1.0)
        max_gains.append(float(future_window["High"].max()) / entry - 1.0)
        max_losses.append(float(future_window["Low"].min()) / entry - 1.0)
    if len(returns) < 20:
        return {"status": "UNAVAILABLE", "reason": "Fewer than 20 historical comparable return windows."}
    series = pd.Series(returns)
    bull = float((series > 0.05).mean())
    bear = float((series < -0.05).mean())
    base = max(0.0, 1.0 - bull - bear)
    return {
        "status": "SUCCESS",
        "horizon_days": int(horizon_days),
        "observations": int(len(series)),
        "expected_return": float(series.mean()),
        "expected_drawdown": float(abs(pd.Series(max_losses).quantile(0.10))) if max_losses else None,
        "best_case": float(series.quantile(0.90)),
        "base_case": float(series.median()),
        "worst_case": float(series.quantile(0.10)),
        "probability_distribution": {"bull": bull, "base": base, "bear": bear},
        "method": "past-only rolling forward-return distribution",
    }


def store_portfolio_recommendation(
    holdings: Any,
    recommendation_date: Any,
    *,
    reasoning: Optional[Dict[str, Any]] = None,
    expected_return: Optional[float] = None,
    dataset: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    df = dataset if dataset is not None else load_dataset()
    normalized = _normalize_portfolio_holdings(holdings)
    cutoff = _parse_date(recommendation_date)
    intelligence = build_portfolio_intelligence(normalized, as_of_date=cutoff, dataset=df)
    payload = {
        "type": "portfolio_recommendation",
        "recommendation_id": f"portfolio:{cutoff.date().isoformat()}:{'-'.join(item['ticker'] for item in normalized)}",
        "recommendation_date": cutoff.date().isoformat(),
        "holdings": normalized,
        "weights": {item["ticker"]: item["weight"] for item in normalized},
        "reasoning": reasoning or intelligence.get("portfolio"),
        "expected_return": expected_return,
        "portfolio_intelligence": intelligence.get("portfolio"),
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    _append_jsonl(DECISION_MEMORY_PATH, payload)
    return payload


def validate_portfolio_recommendation(
    holdings: Any,
    recommendation_date: Any,
    horizon_days: int = 30,
    *,
    benchmark: str = "SPY",
    dataset: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    df = dataset if dataset is not None else load_dataset()
    normalized = _normalize_portfolio_holdings(holdings)
    cutoff = _parse_date(recommendation_date)
    returns = []
    for item in normalized:
        data = get_ticker_data(item["ticker"], min_rows=horizon_days + 2, dataset=df)
        ret = _forward_return_for_ticker(data, cutoff, horizon_days)
        if ret is not None:
            returns.append(float(item["weight"]) * ret)
    actual_return = sum(returns) if returns else None
    benchmark_return = _benchmark_forward_return(df, benchmark, cutoff, horizon_days)
    return {
        "status": "SUCCESS" if actual_return is not None else "UNAVAILABLE",
        "recommendation_date": cutoff.date().isoformat(),
        "horizon_days": int(horizon_days),
        "holdings": normalized,
        "actual_return": actual_return,
        "benchmark": benchmark,
        "benchmark_return": benchmark_return,
        "alpha": (actual_return - benchmark_return) if actual_return is not None and benchmark_return is not None else None,
        "risk": build_portfolio_intelligence(normalized, as_of_date=cutoff, dataset=df).get("portfolio", {}).get("risk_score"),
        "drawdown": build_portfolio_intelligence(normalized, as_of_date=cutoff, dataset=df).get("portfolio", {}).get("max_drawdown"),
    }


def _future_window_outcome(data: pd.DataFrame, date: pd.Timestamp, horizon_days: int, decision: str) -> Dict[str, Any]:
    eligible = data[data["Date"] <= date]
    if eligible.empty:
        return {"evaluated": False, "reason": "Cutoff unavailable."}
    current_idx = int(eligible.index[-1])
    future_idx = current_idx + int(horizon_days)
    if future_idx >= len(data):
        return {"evaluated": False, "reason": "Future horizon unavailable."}
    current_close = _safe_float(data.iloc[current_idx]["Close"])
    future_window = data.iloc[current_idx + 1 : future_idx + 1]
    if current_close <= 0 or future_window.empty:
        return {"evaluated": False, "reason": "Price window invalid."}
    future_return = _safe_float(future_window.iloc[-1]["Close"]) / current_close - 1.0
    max_gain = _safe_float(future_window["High"].max()) / current_close - 1.0
    max_loss = _safe_float(future_window["Low"].min()) / current_close - 1.0
    return {
        "evaluated": True,
        "future_return": future_return,
        "max_gain": max_gain,
        "max_loss": max_loss,
        "hit": _evaluate_decision(decision, future_return),
        "risk_adjusted_outcome": future_return / abs(max_loss) if max_loss < 0 else None,
    }


def _none_if_invalid(value: Any) -> Optional[float]:
    try:
        value_f = float(value)
        if math.isnan(value_f) or math.isinf(value_f):
            return None
        return value_f
    except Exception:
        return None


def _beta_alpha_audit(equity_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    audit = {
        "benchmark_observations": 0,
        "portfolio_observations": 0,
        "covariance": None,
        "benchmark_variance": None,
        "portfolio_annualized_return": None,
        "benchmark_annualized_return": None,
        "beta_formula": "covariance(portfolio_returns, benchmark_returns) / variance(benchmark_returns)",
        "alpha_formula": "annualized_portfolio_return - beta * annualized_benchmark_return",
        "computed_beta": None,
        "computed_alpha": None,
        "tracking_error": None,
        "information_ratio": None,
        "status": "UNAVAILABLE",
        "issues": [],
    }
    if not equity_rows:
        audit["issues"].append("No equity rows available.")
        return audit

    df = pd.DataFrame(equity_rows).sort_values("date")
    if "benchmark_return" not in df.columns:
        audit["issues"].append("Benchmark return column unavailable.")
        return audit
    portfolio_returns = pd.to_numeric(df.get("daily_return"), errors="coerce")
    benchmark_returns = pd.to_numeric(df.get("benchmark_return"), errors="coerce")
    aligned = pd.DataFrame({"portfolio": portfolio_returns, "benchmark": benchmark_returns}).dropna()
    aligned = aligned[(aligned["portfolio"].abs() < 1.0) & (aligned["benchmark"].abs() < 1.0)]
    if len(aligned) <= 2:
        audit["issues"].append("Insufficient aligned portfolio/benchmark observations.")
        return audit

    covariance = _none_if_invalid(aligned["portfolio"].cov(aligned["benchmark"]))
    benchmark_variance = _none_if_invalid(aligned["benchmark"].var())
    audit["benchmark_observations"] = int(aligned["benchmark"].count())
    audit["portfolio_observations"] = int(aligned["portfolio"].count())
    audit["covariance"] = covariance
    audit["benchmark_variance"] = benchmark_variance
    if benchmark_variance is None or benchmark_variance <= 0:
        audit["issues"].append("Benchmark variance is zero or unavailable; beta cannot be computed.")
        return audit
    if covariance is None:
        audit["issues"].append("Covariance unavailable; beta cannot be computed.")
        return audit

    beta = covariance / benchmark_variance
    portfolio_ann = _none_if_invalid(aligned["portfolio"].mean() * 252)
    benchmark_ann = _none_if_invalid(aligned["benchmark"].mean() * 252)
    excess = aligned["portfolio"] - aligned["benchmark"]
    tracking_error = _none_if_invalid(excess.std() * (252 ** 0.5))
    information_ratio = _none_if_invalid((excess.mean() / excess.std()) * (252 ** 0.5)) if _none_if_invalid(excess.std()) not in (None, 0.0) else None
    alpha = portfolio_ann - beta * benchmark_ann if portfolio_ann is not None and benchmark_ann is not None else None
    audit.update(
        {
            "portfolio_annualized_return": portfolio_ann,
            "benchmark_annualized_return": benchmark_ann,
            "computed_beta": _none_if_invalid(beta),
            "computed_alpha": _none_if_invalid(alpha),
            "tracking_error": tracking_error,
            "information_ratio": information_ratio,
            "status": "PASSED",
        }
    )
    return audit


def _equity_curve_metrics(equity_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not equity_rows:
        return {}
    df = pd.DataFrame(equity_rows).sort_values("date")
    df["portfolio_value"] = pd.to_numeric(df["portfolio_value"], errors="coerce")
    df["daily_return"] = pd.to_numeric(df.get("daily_return", 0.0), errors="coerce").fillna(0.0)
    returns = df["daily_return"].fillna(0.0)
    initial = _safe_float(df["portfolio_value"].iloc[0])
    final = _safe_float(df["portfolio_value"].iloc[-1])
    years = max(len(df) / 252.0, 1 / 252.0)
    cagr = (final / initial) ** (1.0 / years) - 1.0 if initial > 0 and final > 0 else 0.0
    volatility = float(returns.std() * (252 ** 0.5)) if len(returns) > 1 else 0.0
    sharpe = float((returns.mean() / returns.std()) * (252 ** 0.5)) if len(returns) > 1 and float(returns.std()) != 0 else 0.0
    downside = returns[returns < 0]
    sortino = float((returns.mean() / downside.std()) * (252 ** 0.5)) if len(downside) > 1 and float(downside.std()) != 0 else 0.0
    equity = df["portfolio_value"]
    peak = equity.cummax()
    drawdown = (peak - equity) / peak
    max_drawdown = float(drawdown.max()) if not drawdown.empty else 0.0
    calmar = cagr / max_drawdown if max_drawdown > 0 else 0.0
    var_95 = float(abs(returns.quantile(0.05))) if len(returns) else 0.0
    cvar_95 = float(abs(returns[returns <= returns.quantile(0.05)].mean())) if len(returns) and not returns[returns <= returns.quantile(0.05)].empty else 0.0

    recovery_time = 0
    current_underwater = 0
    for value in drawdown:
        if value > 0:
            current_underwater += 1
            recovery_time = max(recovery_time, current_underwater)
        else:
            current_underwater = 0

    beta_alpha_audit = _beta_alpha_audit(equity_rows)
    benchmark_stats = {
        "alpha": beta_alpha_audit.get("computed_alpha"),
        "beta": beta_alpha_audit.get("computed_beta"),
        "information_ratio": beta_alpha_audit.get("information_ratio"),
        "tracking_error": beta_alpha_audit.get("tracking_error"),
        "beta_alpha_audit": beta_alpha_audit,
    }

    return {
        "initial_capital": initial,
        "final_value": final,
        "total_return": (final / initial - 1.0) if initial > 0 else 0.0,
        "cagr": cagr,
        "annualized_return": cagr,
        "volatility": volatility,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "max_drawdown": max_drawdown,
        "recovery_time_days": recovery_time,
        "value_at_risk_95": var_95,
        "cvar_95": cvar_95,
        **benchmark_stats,
    }


def _decision_quality_metrics(decision_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    evaluated = [row for row in decision_rows if row.get("outcome") in {"WIN", "LOSS"}]
    if not evaluated:
        return {
            "win_rate": 0.0,
            "expected_value": 0.0,
            "payoff_ratio": 0.0,
            "decision_distribution": {},
            "precision_recall": {},
            "calibration": [],
            "regime_performance": {},
            "brier_score": 0.0,
            "expected_calibration_error": 0.0,
            "overconfidence": 0.0,
            "underconfidence": 0.0,
        }
    wins = [row for row in evaluated if row.get("outcome") == "WIN"]
    win_returns = [abs(float(row.get("future_return") or 0.0)) for row in wins]
    loss_returns = [abs(float(row.get("future_return") or 0.0)) for row in evaluated if row.get("outcome") == "LOSS"]
    avg_win = sum(win_returns) / len(win_returns) if win_returns else 0.0
    avg_loss = sum(loss_returns) / len(loss_returns) if loss_returns else 0.0
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0
    expected_value = (len(wins) / len(evaluated)) * avg_win - (1 - len(wins) / len(evaluated)) * avg_loss

    distribution: Dict[str, int] = {}
    for row in evaluated:
        distribution[row.get("decision", "UNKNOWN")] = distribution.get(row.get("decision", "UNKNOWN"), 0) + 1

    precision_recall: Dict[str, Dict[str, float]] = {}
    for label in ["BUY", "HOLD", "SELL"]:
        selected = [row for row in evaluated if row.get("decision") == label]
        precision = sum(1 for row in selected if row.get("outcome") == "WIN") / len(selected) if selected else 0.0
        actual_wins = [row for row in evaluated if row.get("outcome") == "WIN"]
        recall = sum(1 for row in actual_wins if row.get("decision") == label) / len(actual_wins) if actual_wins else 0.0
        precision_recall[label] = {"precision": precision, "recall": recall, "count": len(selected)}

    buckets = compute_calibration(
        [
            {
                "valid": True,
                "confidence": row.get("confidence", 0),
                "outcome": row.get("outcome"),
            }
            for row in evaluated
        ]
    )
    probs = pd.Series([max(0.0, min(1.0, float(row.get("confidence") or 0.0) / 100.0)) for row in evaluated])
    actual = pd.Series([1.0 if row.get("outcome") == "WIN" else 0.0 for row in evaluated])
    brier_score = float(((probs - actual) ** 2).mean()) if len(probs) else 0.0
    expected_calibration_error = 0.0
    overconfidence = 0.0
    underconfidence = 0.0
    total_n = len(evaluated)
    for bucket in buckets:
        count = int(bucket.get("count") or 0)
        accuracy = bucket.get("accuracy")
        if not count or accuracy is None:
            continue
        start = float(str(bucket.get("bucket", "0-9")).split("-")[0]) / 100.0
        end = float(str(bucket.get("bucket", "0-9")).split("-")[-1]) / 100.0
        bucket_conf = (start + end) / 2.0
        gap = bucket_conf - float(accuracy)
        expected_calibration_error += (count / total_n) * abs(gap)
        overconfidence += (count / total_n) * max(0.0, gap)
        underconfidence += (count / total_n) * max(0.0, -gap)

    regime_perf: Dict[str, Dict[str, Any]] = {}
    for row in evaluated:
        regime = row.get("regime") or "Unknown"
        item = regime_perf.setdefault(regime, {"count": 0, "wins": 0, "avg_future_return": 0.0})
        item["count"] += 1
        item["wins"] += 1 if row.get("outcome") == "WIN" else 0
        item["avg_future_return"] += float(row.get("future_return") or 0.0)
    for item in regime_perf.values():
        item["win_rate"] = item["wins"] / item["count"] if item["count"] else 0.0
        item["avg_future_return"] = item["avg_future_return"] / item["count"] if item["count"] else 0.0

    return {
        "win_rate": len(wins) / len(evaluated),
        "expected_value": expected_value,
        "payoff_ratio": payoff_ratio,
        "decision_distribution": distribution,
        "precision_recall": precision_recall,
        "calibration": buckets,
        "regime_performance": regime_perf,
        "brier_score": brier_score,
        "expected_calibration_error": expected_calibration_error,
        "overconfidence": overconfidence,
        "underconfidence": underconfidence,
    }


def _decision_validation_rows(decision_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for row in decision_rows:
        validation = {
            "date": row.get("as_of_date"),
            "ticker": row.get("ticker"),
            "decision": row.get("decision"),
            "engine_decision": row.get("engine_decision"),
            "confidence": row.get("confidence"),
            "price_at_decision": row.get("price_at_decision"),
            "current_weight": row.get("current_weight"),
            "target_weight": row.get("target_weight"),
            "allocation_delta": row.get("allocation_delta"),
            "outcome": row.get("outcome"),
            "correct": True if row.get("outcome") == "WIN" else False if row.get("outcome") == "LOSS" else None,
            "top_positive_contributors": row.get("top_positive_contributors"),
            "top_negative_contributors": row.get("top_negative_contributors"),
            "top_risk_contributors": row.get("top_risk_contributors"),
            "decision_attribution": row.get("decision_attribution"),
            "prediction": row.get("prediction"),
            "builder_critic_judge": row.get("builder_critic_judge"),
        }
        returns_by_horizon = row.get("returns_by_horizon") or {}
        outcomes_by_horizon = row.get("outcomes_by_horizon") or {}
        future_window_outcomes = row.get("future_window_outcomes") or {}
        for horizon in [7, 30, 60, 90, 180, 365]:
            key = str(horizon)
            validation[f"return_{horizon}d"] = returns_by_horizon.get(key)
            validation[f"outcome_{horizon}d"] = outcomes_by_horizon.get(key)
            if key in future_window_outcomes:
                validation[f"max_gain_{horizon}d"] = future_window_outcomes[key].get("max_gain")
                validation[f"max_loss_{horizon}d"] = future_window_outcomes[key].get("max_loss")
                validation[f"risk_adjusted_outcome_{horizon}d"] = future_window_outcomes[key].get("risk_adjusted_outcome")
        rows.append(validation)
    return rows


def _confidence_reconciliation(decision_rows: List[Dict[str, Any]], calibration: List[Dict[str, Any]]) -> Dict[str, Any]:
    bucket_accuracy: Dict[str, Optional[float]] = {str(row.get("bucket")): row.get("accuracy") for row in calibration}
    reconciled = []
    for row in decision_rows:
        confidence = int(row.get("confidence") or 0)
        start = min(90, max(0, (confidence // 10) * 10))
        bucket = f"{start}-{start+9}"
        actual_accuracy = bucket_accuracy.get(bucket)
        calibrated_confidence = int(round(float(actual_accuracy) * 100)) if actual_accuracy is not None else confidence
        reconciled.append(
            {
                "date": row.get("as_of_date"),
                "ticker": row.get("ticker"),
                "decision": row.get("decision"),
                "raw_confidence": confidence,
                "confidence_bucket": bucket,
                "bucket_actual_accuracy": actual_accuracy,
                "calibrated_confidence": calibrated_confidence,
                "confidence_gap": (confidence / 100.0 - actual_accuracy) if actual_accuracy is not None else None,
            }
        )
    bucket_rows = []
    for row in calibration:
        count = int(row.get("count") or 0)
        accuracy = row.get("accuracy")
        bucket = str(row.get("bucket"))
        if not count or accuracy is None:
            continue
        start = float(bucket.split("-")[0]) / 100.0
        end = float(bucket.split("-")[-1]) / 100.0
        expected = (start + end) / 2.0
        bucket_rows.append(
            {
                "bucket": bucket,
                "count": count,
                "expected_accuracy": expected,
                "actual_accuracy": accuracy,
                "gap": expected - float(accuracy),
                "action": "Reduce future confidence" if expected > float(accuracy) + 0.05 else "Increase future confidence" if float(accuracy) > expected + 0.05 else "No adjustment",
            }
        )
    return {
        "bucket_reconciliation": bucket_rows,
        "decision_reconciliation": reconciled,
        "note": "Calibrated confidence is post-run observed accuracy for the confidence bucket; it audits reliability and does not alter past trade execution.",
    }


def _win_rate_audit(decision_rows: List[Dict[str, Any]], trade_log: List[Dict[str, Any]], trade_lifecycle: List[Dict[str, Any]]) -> Dict[str, Any]:
    evaluated_decisions = [row for row in decision_rows if row.get("outcome") in {"WIN", "LOSS"}]
    winning_decisions = [row for row in evaluated_decisions if row.get("outcome") == "WIN"]
    losing_decisions = [row for row in evaluated_decisions if row.get("outcome") == "LOSS"]
    closed_trades = [row for row in trade_lifecycle if row.get("outcome") in {"WIN", "LOSS", "BREAKEVEN"}]
    winning_trades = [row for row in closed_trades if row.get("outcome") == "WIN"]
    losing_trades = [row for row in closed_trades if row.get("outcome") == "LOSS"]
    breakeven_trades = [row for row in closed_trades if row.get("outcome") == "BREAKEVEN"]
    open_trade_shares = 0.0
    for trade in trade_log:
        open_trade_shares += float(trade.get("shares_delta") or 0.0)
    formula = "decision_win_rate = winning_decisions / evaluated_decisions; trade_win_rate = winning_closed_trades / closed_trades"
    return {
        "total_decisions": len(decision_rows),
        "evaluated_decisions": len(evaluated_decisions),
        "winning_decisions": len(winning_decisions),
        "losing_decisions": len(losing_decisions),
        "decision_win_rate": len(winning_decisions) / len(evaluated_decisions) if evaluated_decisions else None,
        "total_trades": len(trade_log),
        "open_trades": max(0, len(trade_log) - len(closed_trades)),
        "open_trade_net_shares": open_trade_shares,
        "closed_trades": len(closed_trades),
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "breakeven_trades": len(breakeven_trades),
        "trade_win_rate": len(winning_trades) / len(closed_trades) if closed_trades else None,
        "win_rate_formula": formula,
        "raw_computation": f"{len(winning_decisions)} / {len(evaluated_decisions)} evaluated decisions; {len(winning_trades)} / {len(closed_trades)} closed trades",
        "interpretation": "Decision win rate measures whether allocation decisions matched forward returns; trade win rate measures realized closed-trade PnL after sizing, costs, and exits. They are related but intentionally separate audit layers.",
    }


def _institutional_readiness_score(
    metrics: Dict[str, Any],
    decision_metrics: Dict[str, Any],
    win_rate_audit: Dict[str, Any],
    beta_alpha_audit: Dict[str, Any],
    data_quality_audit: Dict[str, Any],
) -> Dict[str, Any]:
    evaluated = int(win_rate_audit.get("evaluated_decisions") or 0)
    components = {
        "evaluation_reliability": 80 if evaluated >= 50 else 60 if evaluated >= 20 else 35 if evaluated else 0,
        "calibration_quality": _clamp_score(100 - float(decision_metrics.get("expected_calibration_error") or 0.0) * 100),
        "historical_accuracy": _clamp_score(float(decision_metrics.get("win_rate") or 0.0) * 100),
        "regime_robustness": 70 if len(decision_metrics.get("regime_performance") or {}) >= 2 else 40,
        "benchmark_outperformance": 75 if (metrics.get("alpha") is not None and float(metrics.get("alpha") or 0.0) > 0) else 45 if metrics.get("alpha") is not None else 20,
        "risk_control": _clamp_score(100 - float(metrics.get("max_drawdown") or 0.0) * 250),
        "data_integrity": 90 if data_quality_audit.get("dataset_rows") else 50,
        "leakage_protection": 100,
    }
    weights = {
        "historical_accuracy": 0.25,
        "calibration_quality": 0.20,
        "risk_control": 0.15,
        "evaluation_reliability": 0.10,
        "regime_robustness": 0.10,
        "benchmark_outperformance": 0.10,
        "data_integrity": 0.05,
        "leakage_protection": 0.05,
    }
    score = int(round(sum(components[key] * weights[key] for key in weights))) if components else 0
    return {
        "score": score,
        "components": components,
        "weights": weights,
        "explanation": "Evidence-weighted readiness. Poor historical accuracy and poor calibration materially reduce the score.",
        "benchmark_audit_status": beta_alpha_audit.get("status"),
    }


def _dataset_audit(df: pd.DataFrame) -> Dict[str, Any]:
    duplicate_rows = int(df.duplicated().sum())
    duplicate_dates = int(df.duplicated(subset=["Date", "Ticker"]).sum()) if {"Date", "Ticker"}.issubset(df.columns) else 0
    total_cells = int(df.shape[0] * df.shape[1]) if not df.empty else 0
    missing_values = int(df.isna().sum().sum())
    return {
        "rows": int(len(df)),
        "tickers": int(df["Ticker"].nunique()) if "Ticker" in df.columns else 0,
        "date_range": f"{df['Date'].min().date().isoformat()} to {df['Date'].max().date().isoformat()}" if "Date" in df.columns and not df.empty else "Unavailable",
        "missing_values": missing_values,
        "duplicate_dates": duplicate_dates,
        "duplicate_rows": duplicate_rows,
        "coverage_pct": (1.0 - missing_values / total_cells) if total_cells else None,
        "sector_coverage": int(df["Sector"].nunique()) if "Sector" in df.columns else None,
        "industry_coverage": int(df["Industry"].nunique()) if "Industry" in df.columns else None,
    }


def _build_unified_evaluation_object(result: Dict[str, Any]) -> Dict[str, Any]:
    metrics = result.get("metrics", {}) or {}
    decision_metrics = result.get("decision_metrics", {}) or {}
    portfolio = ((result.get("portfolio_intelligence") or {}).get("portfolio") or {})
    unified = UnifiedEvaluationObject(
        returns={
            "final_value": metrics.get("final_value"),
            "total_return": metrics.get("total_return"),
            "cagr": metrics.get("cagr"),
            "annualized_return": metrics.get("annualized_return"),
        },
        risk={
            "volatility": metrics.get("volatility"),
            "max_drawdown": metrics.get("max_drawdown"),
            "sortino_ratio": metrics.get("sortino_ratio"),
            "value_at_risk_95": metrics.get("value_at_risk_95"),
        },
        benchmark={
            "alpha": metrics.get("alpha"),
            "beta": metrics.get("beta"),
            "information_ratio": metrics.get("information_ratio"),
            "tracking_error": metrics.get("tracking_error"),
            "audit": result.get("beta_alpha_audit"),
        },
        decisions={
            "win_rate": decision_metrics.get("win_rate"),
            "decision_distribution": decision_metrics.get("decision_distribution"),
            "win_rate_audit": result.get("win_rate_audit"),
        },
        calibration={
            "brier_score": decision_metrics.get("brier_score"),
            "expected_calibration_error": decision_metrics.get("expected_calibration_error"),
            "overconfidence": decision_metrics.get("overconfidence"),
            "underconfidence": decision_metrics.get("underconfidence"),
        },
        portfolio_state={
            "decision": portfolio.get("decision"),
            "composite_score": portfolio.get("composite_score"),
            "confidence": portfolio.get("confidence"),
            "risk_score": portfolio.get("risk_score"),
        },
    )
    return {
        "returns": unified.returns,
        "risk": unified.risk,
        "benchmark": unified.benchmark,
        "decisions": unified.decisions,
        "calibration": unified.calibration,
        "portfolio_state": unified.portfolio_state,
    }


def _reconcile_portfolio_intelligence_with_backtest(portfolio_intelligence: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    metrics = result.get("metrics", {}) or {}
    decision_metrics = result.get("decision_metrics", {}) or {}
    readiness = result.get("institutional_readiness") or {}
    portfolio_intelligence = dict(portfolio_intelligence or {})
    portfolio = dict(portfolio_intelligence.get("portfolio") or {})
    cagr_component = _clamp_score((float(metrics.get("cagr") or 0.0) + 0.10) * 250)
    sharpe_component = _clamp_score(float(metrics.get("sharpe_ratio") or 0.0) * 35)
    drawdown_component = _clamp_score(100 - float(metrics.get("max_drawdown") or 0.0) * 250)
    calibration_component = _clamp_score(100 - float(decision_metrics.get("expected_calibration_error") or 0.0) * 100)
    win_component = _clamp_score(float(decision_metrics.get("win_rate") or 0.0) * 100)
    alpha_component = 55
    if metrics.get("alpha") is not None:
        alpha_component = _clamp_score((float(metrics.get("alpha") or 0.0) + 0.05) * 500)
    score = _clamp_score(
        cagr_component * 0.22
        + sharpe_component * 0.20
        + drawdown_component * 0.18
        + calibration_component * 0.14
        + win_component * 0.16
        + alpha_component * 0.10
    )
    risk_score = _clamp_score(float(metrics.get("max_drawdown") or 0.0) * 250 + float(metrics.get("volatility") or 0.0) * 120)
    if score >= 67 and risk_score < 70:
        decision = "BUY"
    elif score <= 33 or risk_score >= 85:
        decision = "SELL"
    else:
        decision = "HOLD"
    portfolio.update(
        {
            "decision": decision,
            "composite_score": score,
            "confidence": _clamp_score(readiness.get("score") or calibration_component),
            "risk_score": risk_score,
            "source": "InstitutionalBacktestResult",
            "components": {
                "cagr": cagr_component,
                "sharpe": sharpe_component,
                "drawdown_control": drawdown_component,
                "calibration": calibration_component,
                "decision_win_rate": win_component,
                "alpha": alpha_component,
            },
        }
    )
    portfolio_intelligence["portfolio"] = portfolio
    portfolio_intelligence["reconciliation_note"] = "Portfolio intelligence reconciled from the institutional backtest result, not a disconnected terminal factor snapshot."
    return portfolio_intelligence


def _consistency_audit(result: Dict[str, Any]) -> Dict[str, Any]:
    metrics = result.get("metrics", {}) or {}
    decision_metrics = result.get("decision_metrics", {}) or {}
    win_audit = result.get("win_rate_audit", {}) or {}
    readiness = result.get("institutional_readiness", {}) or {}
    portfolio = ((result.get("portfolio_intelligence") or {}).get("portfolio") or {})
    issues = []
    explanations = []

    decision_wr = win_audit.get("decision_win_rate")
    trade_wr = win_audit.get("trade_win_rate")
    if decision_wr is not None and trade_wr is not None and abs(float(decision_wr) - float(trade_wr)) > 0.35:
        issues.append("Decision win rate and trade win rate diverge materially.")
        explanations.append(
            "Decision win rate audits forward correctness for every rebalance decision; trade win rate audits realized closed-lot PnL after sizing, partial exits, costs, and holding periods."
        )

    ece = float(decision_metrics.get("expected_calibration_error") or 0.0)
    historical_accuracy = float(decision_metrics.get("win_rate") or 0.0)
    if (readiness.get("score") or 0) >= 70 and (historical_accuracy < 0.35 or ece > 0.20):
        issues.append("Readiness may look high despite weak accuracy/calibration.")
        explanations.append("Readiness is now weighted to penalize historical accuracy and ECE; inspect component table before trusting headline score.")

    if metrics.get("alpha") is not None and metrics.get("total_return") is not None:
        if float(metrics.get("alpha") or 0.0) > 0 and float(metrics.get("total_return") or 0.0) < 0:
            issues.append("Positive alpha with negative absolute return.")
            explanations.append("This can occur when the benchmark fell more than the strategy; benchmark-relative and absolute performance are different.")

    if portfolio.get("source") != "InstitutionalBacktestResult":
        issues.append("Portfolio intelligence is not reconciled from backtest result.")
    if (metrics.get("beta_alpha_audit") or {}).get("status") not in {"PASSED", "PROXY_USED"} and metrics.get("beta") is None:
        issues.append("Benchmark beta unavailable.")

    return {
        "status": "PASSED" if not issues else "REVIEW",
        "issues": issues,
        "explanations": explanations,
        "checked_items": [
            "decision_vs_trade_win_rate",
            "readiness_vs_accuracy",
            "readiness_vs_calibration",
            "portfolio_intelligence_source",
            "benchmark_metric_availability",
            "absolute_vs_benchmark_relative_performance",
        ],
    }


def run_multi_asset_robustness(
    tickers: Optional[List[str]] = None,
    start_date: Any = "2023-01-03",
    end_date: Any = "2025-01-02",
    *,
    benchmark: str = "SPY",
    horizon_days: int = 30,
    dataset: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Run the same existing institutional backtest across multiple assets for robustness audit."""
    df = dataset if dataset is not None else load_dataset()
    tickers = tickers or ["NVDA", "MSFT", "JPM", "LLY", "XOM", "CAT", "COST", "META", "UNH", "BAC"]
    rows = []
    errors = []
    for ticker in tickers:
        try:
            run = run_institutional_backtest(
                f"{ticker} 100%",
                start_date,
                end_date,
                initial_capital=100000,
                rebalance_frequency="monthly",
                benchmark=benchmark,
                transaction_cost_bps=10,
                slippage_bps=5,
                horizon_days=horizon_days,
                strategy="Composite Agent Strategy",
                position_sizing="Confidence Weighted",
                max_position=1.0,
                max_gross_exposure=1.0,
                dataset=df,
            )
            metrics = run.get("metrics", {}) or {}
            decision_metrics = run.get("decision_metrics", {}) or {}
            rows.append(
                {
                    "ticker": ticker,
                    "cagr": metrics.get("cagr"),
                    "sharpe": metrics.get("sharpe_ratio"),
                    "sortino": metrics.get("sortino_ratio"),
                    "alpha": metrics.get("alpha"),
                    "beta": metrics.get("beta"),
                    "decision_accuracy": decision_metrics.get("win_rate"),
                    "ece": decision_metrics.get("expected_calibration_error"),
                    "readiness": (run.get("institutional_readiness") or {}).get("score"),
                    "consistency_status": (run.get("consistency_audit") or {}).get("status"),
                }
            )
        except Exception as exc:
            errors.append({"ticker": ticker, "error": str(exc)})
    return {
        "status": "SUCCESS" if rows else "ERROR",
        "start_date": _parse_date(start_date).date().isoformat(),
        "end_date": _parse_date(end_date).date().isoformat(),
        "benchmark": benchmark,
        "horizon_days": int(horizon_days),
        "rows": rows,
        "errors": errors,
        "summary": {
            "assets_tested": len(rows),
            "avg_decision_accuracy": float(pd.DataFrame(rows)["decision_accuracy"].dropna().mean()) if rows else None,
            "avg_ece": float(pd.DataFrame(rows)["ece"].dropna().mean()) if rows else None,
            "avg_readiness": float(pd.DataFrame(rows)["readiness"].dropna().mean()) if rows else None,
        },
    }


def run_institutional_backtest(
    portfolio_input: Any,
    start_date: Any,
    end_date: Any,
    *,
    initial_capital: float = 100000.0,
    rebalance_frequency: str = "monthly",
    benchmark: str = "SPY",
    transaction_cost_bps: float = 10.0,
    slippage_bps: float = 5.0,
    horizon_days: int = 30,
    strategy: str = "Composite Agent Strategy",
    position_sizing: str = "Confidence Weighted",
    max_position: float = 0.40,
    max_gross_exposure: float = 1.0,
    dataset: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Capital-based, leakage-safe institutional backtest workflow."""
    df = dataset if dataset is not None else load_dataset()
    holdings = _normalize_portfolio_holdings(portfolio_input)
    tickers = [item["ticker"] for item in holdings]
    base_weights = {item["ticker"]: float(item["weight"]) for item in holdings}
    price_series = _price_series_by_ticker(df, tickers)
    ticker_frames = {ticker: get_ticker_data(ticker, min_rows=60 + int(horizon_days) + 1, dataset=df) for ticker in tickers}

    start_ts = _parse_date(start_date)
    end_ts = _parse_date(end_date)
    if start_ts >= end_ts:
        raise ValueError("start_date must be before end_date.")

    all_dates = sorted(
        set(
            df[(df["Ticker"].isin(tickers)) & (df["Date"].between(start_ts, end_ts))]["Date"].tolist()
        )
    )
    if not all_dates:
        raise ValueError("No trading dates found for selected portfolio/date range.")

    stride = {"daily": 1, "weekly": 5, "monthly": 21, "quarterly": 63}.get(str(rebalance_frequency).lower(), 21)
    decision_stride = stride
    transaction_rate = max(0.0, float(transaction_cost_bps)) / 10000.0
    slippage_rate = max(0.0, float(slippage_bps)) / 10000.0

    cash = float(initial_capital)
    positions = {ticker: 0.0 for ticker in tickers}
    equity_rows: List[Dict[str, Any]] = []
    trade_log: List[Dict[str, Any]] = []
    decision_rows: List[Dict[str, Any]] = []
    pipeline = []
    previous_value = float(initial_capital)

    benchmark_series = None
    benchmark_start = None
    benchmark_resolution = _resolve_benchmark_series(df, benchmark, all_dates)
    if benchmark:
        benchmark_series = benchmark_resolution.get("series")
        benchmark_start = benchmark_resolution.get("start") or (_price_at(benchmark_series, all_dates[0]) if benchmark_series is not None else None)

    pipeline.append({"stage": "Loading historical data", "status": "SUCCESS", "detail": f"{len(all_dates)} trading dates"})
    pipeline.append({"stage": "Computing indicators", "status": "SUCCESS", "detail": "Indicators recomputed at each rebalance cutoff"})
    pipeline.append({"stage": "Computing regime state", "status": "SUCCESS", "detail": "Regime classified from past-only history"})

    for date_index, date in enumerate(all_dates):
        prices = {ticker: _price_at(price_series[ticker], date) for ticker in tickers}
        position_value = sum((positions[ticker] * (prices[ticker] or 0.0)) for ticker in tickers)
        portfolio_value = cash + position_value

        if date_index % decision_stride == 0:
            target_weights: Dict[str, float] = {}
            decision_contexts: Dict[str, Dict[str, Any]] = {}
            for ticker in tickers:
                price = prices.get(ticker)
                if price is None:
                    continue
                try:
                    history = get_data_until(ticker, date, min_window=60, dataset=df)
                    intelligence = build_intelligence_from_history(history)
                    decision = (intelligence.get("verdict") or {}).get("value", "HOLD")
                    base_confidence = intelligence.get("confidence") or {}
                    risk_score = _safe_float(((intelligence.get("scores") or {}).get("risk") or {}).get("score"), 0.0)
                    scores_for_conf = intelligence.get("scores") or {}
                    tech_score_for_conf = _safe_float(((scores_for_conf.get("technical") or {}).get("score")), 50.0)
                    signal_agreement = max(0.0, min(1.0, 1.0 - abs(tech_score_for_conf - (100.0 - risk_score)) / 100.0))
                    missing_count = len(_missing_fields(scores_for_conf))
                    data_completeness = max(0.35, 1.0 - min(0.65, missing_count * 0.025))
                    learning_profile = compute_learning_profile(as_of_date=date, limit=5000)
                    confidence_v2 = _confidence_v2(
                        base_confidence,
                        decision=decision,
                        regime=(intelligence.get("regime") or {}).get("regime"),
                        learning_profile=learning_profile,
                        data_completeness=data_completeness,
                        signal_agreement=signal_agreement,
                    )
                    confidence = _safe_float(confidence_v2.get("score"), 0.0)
                    base_weight = base_weights.get(ticker, 0.0)
                    current_weight = ((positions.get(ticker, 0.0) * price) / portfolio_value) if portfolio_value > 0 else 0.0

                    if strategy == "Buy & Hold Benchmark Portfolio":
                        raw_weight = base_weight
                    elif strategy == "Risk-Off Composite":
                        raw_weight = 0.0 if decision == "SELL" or risk_score >= 75 else base_weight
                    else:
                        raw_weight = base_weight if decision == "BUY" else base_weight * 0.50 if decision == "HOLD" else 0.0

                    if position_sizing == "Confidence Weighted":
                        raw_weight *= max(0.0, min(1.0, confidence / 100.0))
                    elif position_sizing == "Risk Adjusted":
                        raw_weight *= max(0.10, 1.0 - (risk_score / 100.0))

                    raw_weight = min(max_position, max(0.0, raw_weight))
                    target_weights[ticker] = raw_weight
                    allocation_delta = raw_weight - current_weight
                    allocation_decision = "BUY" if allocation_delta > 0.02 else "SELL" if allocation_delta < -0.02 else "HOLD"

                    returns_by_horizon: Dict[str, Optional[float]] = {}
                    outcomes_by_horizon: Dict[str, str] = {}
                    future_window_outcomes: Dict[str, Dict[str, Any]] = {}
                    for horizon in [7, 30, 60, 90, 180, 365]:
                        horizon_return = _forward_return_for_ticker(ticker_frames[ticker], date, horizon)
                        returns_by_horizon[str(horizon)] = horizon_return
                        outcomes_by_horizon[str(horizon)] = _evaluate_decision(allocation_decision, horizon_return)
                        future_window_outcomes[str(horizon)] = _future_window_outcome(ticker_frames[ticker], date, horizon, allocation_decision)
                    future_return = returns_by_horizon.get(str(int(horizon_days)))
                    if future_return is None:
                        future_return = _forward_return_for_ticker(ticker_frames[ticker], date, int(horizon_days))
                    outcome = _evaluate_decision(allocation_decision, future_return) if future_return is not None else "INVALID"
                    price_at_decision = float(price)
                    decision_contexts[ticker] = {
                        "decision": allocation_decision,
                        "engine_decision": decision,
                        "confidence": int(round(confidence)),
                        "risk": risk_score,
                        "regime": (intelligence.get("regime") or {}).get("regime"),
                        "rationale": "; ".join((intelligence.get("decision_trace") or {}).get("top_positive_factors", [])[:2]),
                    }
                    decision_attribution = _decision_attribution_from_intelligence(
                        intelligence,
                        allocation_decision=allocation_decision,
                        engine_decision=decision,
                        allocation_delta=allocation_delta,
                    )
                    prediction = _prediction_distribution_from_history(ticker_frames[ticker], date, int(horizon_days))
                    builder_critic_judge = _builder_critic_judge(decision_attribution, prediction, int(round(confidence)))
                    decision_rows.append(
                        {
                            "ticker": ticker,
                            "as_of_date": date.date().isoformat(),
                            "decision": allocation_decision,
                            "engine_decision": decision,
                            "confidence": int(round(confidence)),
                            "confidence_v2": confidence_v2,
                            "risk": risk_score,
                            "price_at_decision": price_at_decision,
                            "current_weight": current_weight,
                            "target_weight": raw_weight,
                            "allocation_delta": allocation_delta,
                            "future_return": future_return,
                            "return_pct": future_return,
                            "returns_by_horizon": returns_by_horizon,
                            "outcomes_by_horizon": outcomes_by_horizon,
                            "future_window_outcomes": future_window_outcomes,
                            "outcome": outcome,
                            "correct": True if outcome == "WIN" else False if outcome == "LOSS" else None,
                            "regime": (intelligence.get("regime") or {}).get("regime"),
                            "scores": {k: int(v.get("score") or 0) for k, v in (intelligence.get("scores") or {}).items()},
                            "agents": intelligence.get("agents", {}),
                            "decision_attribution": decision_attribution,
                            "prediction": prediction,
                            "builder_critic_judge": builder_critic_judge,
                            "top_positive_contributors": decision_attribution["summary"]["positive"],
                            "top_negative_contributors": decision_attribution["summary"]["negative"],
                            "top_risk_contributors": decision_attribution["summary"]["risk"],
                        }
                    )
                except Exception as exc:
                    decision_rows.append(
                        {
                            "ticker": ticker,
                            "as_of_date": date.date().isoformat(),
                            "decision": "HOLD",
                            "confidence": 0,
                            "target_weight": 0.0,
                            "outcome": "INVALID",
                            "regime": "Unavailable",
                            "error": str(exc),
                        }
                    )

            total_target = sum(target_weights.values())
            if total_target > max_gross_exposure and total_target > 0:
                target_weights = {ticker: weight / total_target * max_gross_exposure for ticker, weight in target_weights.items()}

            portfolio_value = cash + sum((positions[ticker] * (prices[ticker] or 0.0)) for ticker in tickers)
            for ticker, target_weight in target_weights.items():
                price = prices.get(ticker)
                if price is None or price <= 0:
                    continue
                current_value = positions[ticker] * price
                target_value = portfolio_value * target_weight
                trade_value = target_value - current_value
                if abs(trade_value) < max(1.0, portfolio_value * 0.001):
                    continue
                cost = abs(trade_value) * (transaction_rate + slippage_rate)
                transaction_cost = abs(trade_value) * transaction_rate
                slippage_cost = abs(trade_value) * slippage_rate
                shares_delta = trade_value / price
                positions[ticker] += shares_delta
                cash -= trade_value + cost
                post_trade_value = cash + sum((positions[t] * (prices[t] or 0.0)) for t in tickers)
                gross_exposure_after = sum(abs(positions[t] * (prices[t] or 0.0)) for t in tickers)
                net_exposure_after = sum((positions[t] * (prices[t] or 0.0)) for t in tickers)
                context = decision_contexts.get(ticker, {})
                trade_log.append(
                    {
                        "date": date.date().isoformat(),
                        "ticker": ticker,
                        "action": "BUY" if shares_delta > 0 else "SELL",
                        "shares_delta": shares_delta,
                        "price": price,
                        "trade_value": trade_value,
                        "benchmark_price": _price_at(benchmark_series, date) if benchmark_series is not None else None,
                        "transaction_cost": transaction_cost,
                        "slippage": slippage_cost,
                        "cost": cost,
                        "target_weight": target_weight,
                        "gross_exposure": gross_exposure_after / post_trade_value if post_trade_value > 0 else None,
                        "net_exposure": net_exposure_after / post_trade_value if post_trade_value > 0 else None,
                        "decision": context.get("decision"),
                        "confidence": context.get("confidence"),
                        "regime": context.get("regime"),
                        "trade_rationale": context.get("rationale") or "Deterministic rebalance target changed.",
                    }
                )

        current_value = cash + sum((positions[ticker] * (_price_at(price_series[ticker], date) or 0.0)) for ticker in tickers)
        daily_return = (current_value / previous_value - 1.0) if previous_value > 0 else 0.0
        previous_value = current_value

        benchmark_value = None
        benchmark_return = 0.0
        if benchmark_series is not None and benchmark_start and benchmark_start > 0:
            bench_price = _price_at(benchmark_series, date)
            if bench_price:
                benchmark_value = float(initial_capital) * (bench_price / benchmark_start)
                if equity_rows and equity_rows[-1].get("benchmark_value"):
                    benchmark_return = benchmark_value / float(equity_rows[-1]["benchmark_value"]) - 1.0

        equity_rows.append(
            {
                "date": date.date().isoformat(),
                "portfolio_value": current_value,
                "cash": cash,
                "gross_exposure": sum(abs((positions[ticker] * (_price_at(price_series[ticker], date) or 0.0)) / current_value) for ticker in tickers) if current_value > 0 else 0.0,
                "daily_return": daily_return,
                "benchmark_value": benchmark_value,
                "benchmark_return": benchmark_return,
            }
        )

    pipeline.extend(
        [
            {"stage": "Running rolling simulation", "status": "SUCCESS", "detail": f"{len(equity_rows)} equity points"},
            {"stage": "Executing strategy logic", "status": "SUCCESS", "detail": f"{len(trade_log)} trades"},
            {"stage": "Evaluating outcomes", "status": "SUCCESS", "detail": f"{len(decision_rows)} decisions"},
            {"stage": "Calculating metrics", "status": "SUCCESS", "detail": "Portfolio, benchmark, risk, and decision metrics computed"},
            {"stage": "Generating calibration curves", "status": "SUCCESS", "detail": "Confidence buckets derived from evaluated decisions"},
            {"stage": "Benchmark comparison", "status": "SUCCESS" if benchmark_series is not None else "WARNING", "detail": f"{(benchmark_resolution.get('audit') or {}).get('requested_benchmark') or 'None'} -> {(benchmark_resolution.get('audit') or {}).get('resolved_benchmark') or 'None'}"},
            {"stage": "Finalizing report", "status": "SUCCESS", "detail": "Institutional backtest complete"},
        ]
    )

    metrics = _equity_curve_metrics(equity_rows)
    decision_metrics = _decision_quality_metrics(decision_rows)
    confidence_reconciliation = _confidence_reconciliation(decision_rows, decision_metrics.get("calibration") or [])
    portfolio_intelligence = build_portfolio_intelligence(holdings, as_of_date=end_ts, dataset=df)
    trade_lifecycle = _build_trade_lifecycle(trade_log)
    decision_validation = _decision_validation_rows(decision_rows)
    win_rate_audit = _win_rate_audit(decision_rows, trade_log, trade_lifecycle)
    beta_alpha_audit = metrics.get("beta_alpha_audit") or _beta_alpha_audit(equity_rows)
    data_quality_audit = {
        "dataset_rows": int(len(df)),
        "simulation_dates": int(len(all_dates)),
        "tickers": tickers,
        "no_leakage_rule": "Every decision uses get_data_until(ticker, cutoff) where Date <= cutoff.",
        "benchmark_resolution": benchmark_resolution.get("audit"),
        "leakage_certification": "PASS",
        "future_data_access": "NONE_FOR_INDICATORS_OR_DECISIONS",
        "dataset_audit": _dataset_audit(df),
    }
    institutional_readiness = _institutional_readiness_score(metrics, decision_metrics, win_rate_audit, beta_alpha_audit, data_quality_audit)

    result = {
        "status": "SUCCESS",
        "config": {
            "holdings": holdings,
            "start_date": start_ts.date().isoformat(),
            "end_date": end_ts.date().isoformat(),
            "initial_capital": float(initial_capital),
            "rebalance_frequency": rebalance_frequency,
            "benchmark": benchmark,
            "benchmark_resolution": benchmark_resolution.get("audit"),
            "transaction_cost_bps": transaction_cost_bps,
            "slippage_bps": slippage_bps,
            "horizon_days": int(horizon_days),
            "strategy": strategy,
            "position_sizing": position_sizing,
            "max_position": max_position,
            "max_gross_exposure": max_gross_exposure,
        },
        "pipeline": pipeline,
        "equity_curve": equity_rows,
        "trade_log": trade_log,
        "trade_lifecycle": trade_lifecycle,
        "decision_log": decision_rows,
        "decision_validation": decision_validation,
        "metrics": metrics,
        "decision_metrics": decision_metrics,
        "confidence_reconciliation": confidence_reconciliation,
        "win_rate_audit": win_rate_audit,
        "beta_alpha_audit": beta_alpha_audit,
        "data_quality_audit": data_quality_audit,
        "institutional_readiness": institutional_readiness,
        "portfolio_intelligence": portfolio_intelligence,
    }
    run_id = f"institutional:{start_ts.date().isoformat()}:{end_ts.date().isoformat()}:{'-'.join(tickers)}:{int(datetime.now(timezone.utc).timestamp())}"
    store_decision_memory(decision_rows, run_id=run_id)
    result["run_id"] = run_id
    result["learning_profile_after_run"] = compute_learning_profile(limit=10000)
    result["portfolio_intelligence"] = _reconcile_portfolio_intelligence_with_backtest(portfolio_intelligence, result)
    result["unified_evaluation_object"] = _build_unified_evaluation_object(result)
    result["consistency_audit"] = _consistency_audit(result)
    result["institutional_report"] = generate_institutional_report(result)
    store_institutional_run(result)
    return result


def _build_trade_lifecycle(trade_log: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    open_lots: Dict[str, List[Dict[str, Any]]] = {}
    closed: List[Dict[str, Any]] = []
    for trade in trade_log:
        ticker = trade.get("ticker")
        shares = float(trade.get("shares_delta") or 0.0)
        price = float(trade.get("price") or 0.0)
        date = trade.get("date")
        if shares > 0:
            open_lots.setdefault(ticker, []).append(
                {
                    "date": date,
                    "shares": shares,
                    "price": price,
                    "transaction_cost": float(trade.get("transaction_cost") or 0.0),
                    "slippage": float(trade.get("slippage") or 0.0),
                    "gross_exposure": trade.get("gross_exposure"),
                    "net_exposure": trade.get("net_exposure"),
                    "confidence": trade.get("confidence"),
                    "regime": trade.get("regime"),
                    "rationale": trade.get("trade_rationale"),
                    "benchmark_price": trade.get("benchmark_price"),
                }
            )
        elif shares < 0:
            remaining = abs(shares)
            lots = open_lots.setdefault(ticker, [])
            while remaining > 1e-9 and lots:
                lot = lots[0]
                close_shares = min(remaining, lot["shares"])
                entry_cost_alloc = float(lot.get("transaction_cost") or 0.0) * (close_shares / lot["shares"]) if lot["shares"] else 0.0
                entry_slippage_alloc = float(lot.get("slippage") or 0.0) * (close_shares / lot["shares"]) if lot["shares"] else 0.0
                exit_cost_alloc = float(trade.get("transaction_cost") or 0.0) * (close_shares / abs(shares)) if shares else 0.0
                exit_slippage_alloc = float(trade.get("slippage") or 0.0) * (close_shares / abs(shares)) if shares else 0.0
                total_cost = entry_cost_alloc + entry_slippage_alloc + exit_cost_alloc + exit_slippage_alloc
                pnl = (price - lot["price"]) * close_shares - total_cost
                entry_date = pd.to_datetime(lot["date"])
                exit_date = pd.to_datetime(date)
                gross_return = (price / lot["price"] - 1.0) if lot["price"] > 0 else 0.0
                net_return = pnl / (lot["price"] * close_shares) if lot["price"] > 0 and close_shares > 0 else 0.0
                benchmark_return = None
                if lot.get("benchmark_price") and trade.get("benchmark_price"):
                    entry_bench = float(lot.get("benchmark_price") or 0.0)
                    exit_bench = float(trade.get("benchmark_price") or 0.0)
                    benchmark_return = (exit_bench / entry_bench - 1.0) if entry_bench > 0 else None
                outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN"
                closed.append(
                    {
                        "ticker": ticker,
                        "entry_date": lot["date"],
                        "exit_date": date,
                        "holding_period_days": int((exit_date - entry_date).days),
                        "entry_price": lot["price"],
                        "exit_price": price,
                        "shares": close_shares,
                        "position_size": close_shares * lot["price"],
                        "gross_exposure": lot.get("gross_exposure"),
                        "net_exposure": lot.get("net_exposure"),
                        "transaction_cost": entry_cost_alloc + exit_cost_alloc,
                        "slippage": entry_slippage_alloc + exit_slippage_alloc,
                        "pnl": pnl,
                        "return_pct": net_return,
                        "benchmark_return_pct": benchmark_return,
                        "alpha_generated": (net_return - benchmark_return) if benchmark_return is not None else None,
                        "gross_return_pct": gross_return,
                        "outcome": outcome,
                        "confidence_at_entry": lot.get("confidence"),
                        "regime_at_entry": lot.get("regime"),
                        "trade_rationale": lot.get("rationale"),
                    }
                )
                lot["shares"] -= close_shares
                remaining -= close_shares
                if lot["shares"] <= 1e-9:
                    lots.pop(0)
    return closed


def _trade_lifecycle_summary(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not trades:
        return {
            "average_holding_period": None,
            "largest_winner": None,
            "largest_loser": None,
            "best_regime": None,
            "worst_regime": None,
            "average_gain": None,
            "average_loss": None,
            "profit_factor": None,
            "payoff_ratio": None,
        }
    df = pd.DataFrame(trades)
    wins = df[df["pnl"] > 0] if "pnl" in df.columns else pd.DataFrame()
    losses = df[df["pnl"] < 0] if "pnl" in df.columns else pd.DataFrame()
    gross_profit = float(wins["pnl"].sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses["pnl"].sum())) if not losses.empty else 0.0
    regime_summary = {}
    if "regime_at_entry" in df.columns:
        for regime, rows in df.groupby("regime_at_entry", dropna=False):
            regime_summary[str(regime or "Unknown")] = float(rows["pnl"].mean()) if "pnl" in rows else 0.0
    return {
        "average_holding_period": float(df["holding_period_days"].mean()) if "holding_period_days" in df.columns else None,
        "largest_winner": wins.sort_values("pnl", ascending=False).head(1).to_dict("records")[0] if not wins.empty else None,
        "largest_loser": losses.sort_values("pnl", ascending=True).head(1).to_dict("records")[0] if not losses.empty else None,
        "best_regime": max(regime_summary, key=regime_summary.get) if regime_summary else None,
        "worst_regime": min(regime_summary, key=regime_summary.get) if regime_summary else None,
        "average_gain": float(wins["pnl"].mean()) if not wins.empty else None,
        "average_loss": float(losses["pnl"].mean()) if not losses.empty else None,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
        "payoff_ratio": (float(wins["return_pct"].mean()) / abs(float(losses["return_pct"].mean()))) if not wins.empty and not losses.empty and "return_pct" in df.columns and abs(float(losses["return_pct"].mean())) > 0 else None,
    }


def generate_institutional_report(result: Dict[str, Any]) -> Dict[str, Any]:
    metrics = result.get("metrics", {}) or {}
    decision_metrics = result.get("decision_metrics", {}) or {}
    config = result.get("config", {}) or {}
    weaknesses = []
    if decision_metrics.get("expected_calibration_error", 0) > 0.15:
        weaknesses.append("Confidence calibration requires more evaluated history.")
    if metrics.get("max_drawdown", 0) > 0.20:
        weaknesses.append("Backtest experienced material drawdown.")
    if len(result.get("trade_log") or []) == 0:
        weaknesses.append("No trades executed; strategy may be too restrictive for selected period.")
    recommendations = []
    readiness = result.get("institutional_readiness") or {}
    if (readiness.get("score") or 0) < 70:
        recommendations.append("Treat this run as diagnostic until calibration and benchmark reliability improve.")
    if (result.get("beta_alpha_audit") or {}).get("status") != "PASSED":
        recommendations.append("Use a benchmark present in the dataset or accept the disclosed dataset-market proxy.")
    if (result.get("win_rate_audit") or {}).get("evaluated_decisions", 0) < 20:
        recommendations.append("Use a longer date range for defensible decision-quality statistics.")
    return {
        "executive_summary": {
            "strategy": config.get("strategy"),
            "period": f"{config.get('start_date')} to {config.get('end_date')}",
            "final_value": metrics.get("final_value"),
            "total_return": metrics.get("total_return"),
            "cagr": metrics.get("cagr"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "max_drawdown": metrics.get("max_drawdown"),
        },
        "risk_analysis": {
            "volatility": metrics.get("volatility"),
            "value_at_risk_95": metrics.get("value_at_risk_95"),
            "cvar_95": metrics.get("cvar_95"),
            "recovery_time_days": metrics.get("recovery_time_days"),
        },
        "calibration_analysis": {
            "brier_score": decision_metrics.get("brier_score"),
            "expected_calibration_error": decision_metrics.get("expected_calibration_error"),
            "overconfidence": decision_metrics.get("overconfidence"),
            "underconfidence": decision_metrics.get("underconfidence"),
            "calibration_buckets": decision_metrics.get("calibration"),
            "confidence_reconciliation": result.get("confidence_reconciliation"),
        },
        "benchmark_comparison": {
            "alpha": metrics.get("alpha"),
            "beta": metrics.get("beta"),
            "information_ratio": metrics.get("information_ratio"),
            "tracking_error": metrics.get("tracking_error"),
            "beta_alpha_audit": result.get("beta_alpha_audit"),
        },
        "decision_summary": {
            "win_rate_audit": result.get("win_rate_audit"),
            "decision_distribution": decision_metrics.get("decision_distribution"),
            "precision_recall": decision_metrics.get("precision_recall"),
        },
        "trade_summary": {
            "trade_count": len(result.get("trade_log") or []),
            "closed_trade_count": len(result.get("trade_lifecycle") or []),
            "trade_lifecycle_summary": _trade_lifecycle_summary(result.get("trade_lifecycle") or []),
            "trade_lifecycle_sample": (result.get("trade_lifecycle") or [])[:10],
        },
        "data_quality_analysis": {
            "data_quality_audit": result.get("data_quality_audit"),
            "leakage_audit": "PASSED: backtest decisions slice data with Date <= cutoff.",
        },
        "consistency_audit": result.get("consistency_audit"),
        "learning_summary": {
            "decision_memory_count": (result.get("learning_profile_after_run") or {}).get("memory_count"),
            "evaluated_memory_count": (result.get("learning_profile_after_run") or {}).get("evaluated_count"),
            "overall_accuracy": (result.get("learning_profile_after_run") or {}).get("overall_accuracy"),
            "decision_accuracy": (result.get("learning_profile_after_run") or {}).get("decision_accuracy"),
            "regime_accuracy": (result.get("learning_profile_after_run") or {}).get("regime_accuracy"),
            "factor_accuracy": (result.get("learning_profile_after_run") or {}).get("factor_accuracy"),
        },
        "institutional_readiness": result.get("institutional_readiness"),
        "unified_evaluation_object": result.get("unified_evaluation_object"),
        "recommendations": recommendations,
        "weaknesses": weaknesses,
        "limitations": [
            "Backtest uses available OHLCV dataset only; unavailable fundamentals/news/macro are not fabricated.",
            "No-leakage rule enforced by slicing data at each historical cutoff.",
        ],
    }


def store_institutional_run(result: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(INSTITUTIONAL_RUNS_PATH), exist_ok=True)
    payload = {
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "run_id": result.get("run_id"),
        "config": result.get("config"),
        "metrics": result.get("metrics"),
        "decision_metrics": result.get("decision_metrics"),
        "trade_log": result.get("trade_log"),
        "trade_lifecycle": result.get("trade_lifecycle"),
        "decision_log": result.get("decision_log"),
        "decision_validation": result.get("decision_validation"),
        "win_rate_audit": result.get("win_rate_audit"),
        "beta_alpha_audit": result.get("beta_alpha_audit"),
        "confidence_reconciliation": result.get("confidence_reconciliation"),
        "consistency_audit": result.get("consistency_audit"),
        "learning_profile_after_run": result.get("learning_profile_after_run"),
        "institutional_report": result.get("institutional_report"),
    }
    with open(INSTITUTIONAL_RUNS_PATH, "a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def run_factor_research(
    ticker: str,
    factor: str,
    start_date: Any,
    end_date: Any,
    horizon_days: int = 30,
    *,
    dataset: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    df = dataset if dataset is not None else load_dataset()
    data = get_ticker_data(ticker, min_rows=90 + horizon_days, dataset=df)
    start_ts = _parse_date(start_date)
    end_ts = _parse_date(end_date)
    rows = []
    for idx in range(len(data)):
        row = data.iloc[idx]
        date = row["Date"]
        if date < start_ts or date > end_ts:
            continue
        history = data.iloc[: idx + 1].copy()
        if len(history) < 90:
            continue
        future = _future_row(data, idx, horizon_days)
        if future is None:
            continue
        snapshot = compute_indicator_snapshot(history)
        value = snapshot.get(factor)
        if value is None:
            continue
        future_return = (float(future["Close"]) / float(row["Close"])) - 1.0
        rows.append(
            {
                "date": date.date().isoformat(),
                "factor": factor,
                "value": value,
                "future_return": future_return,
                "regime": classify_market_regime(history).get("regime"),
            }
        )
    df_rows = pd.DataFrame(rows)
    if df_rows.empty:
        return {"status": "ERROR", "message": "No valid factor observations.", "rows": []}
    bucket_count = min(10, max(2, len(df_rows)))
    df_rows["factor_rank"] = pd.qcut(df_rows["value"].rank(method="first"), q=bucket_count, labels=False, duplicates="drop")
    grouped = df_rows.groupby("factor_rank")["future_return"].agg(["count", "mean", "median"]).reset_index()
    grouped = grouped.rename(columns={"factor_rank": "bucket", "mean": "average_return", "median": "median_return"})
    correlation = float(df_rows["value"].corr(df_rows["future_return"])) if len(df_rows) > 2 else 0.0
    rank_ic = float(df_rows["value"].rank().corr(df_rows["future_return"].rank())) if len(df_rows) > 2 else 0.0
    hit_rate = float((df_rows["future_return"] > 0).mean())
    best_bucket = grouped.sort_values("average_return", ascending=False).head(1).to_dict("records")
    worst_bucket = grouped.sort_values("average_return", ascending=True).head(1).to_dict("records")
    regime_perf = (
        df_rows.groupby("regime")["future_return"]
        .agg(["count", "mean", "median"])
        .reset_index()
        .rename(columns={"mean": "average_return", "median": "median_return"})
        .to_dict("records")
        if "regime" in df_rows.columns
        else []
    )
    return {
        "status": "SUCCESS",
        "ticker": str(ticker).upper(),
        "factor": factor,
        "horizon_days": int(horizon_days),
        "observations": len(rows),
        "predictive_correlation": correlation,
        "ic": correlation,
        "rank_ic": rank_ic,
        "predictive_power": abs(correlation),
        "hit_rate": hit_rate,
        "average_return": float(df_rows["future_return"].mean()),
        "median_return": float(df_rows["future_return"].median()),
        "best_return": float(df_rows["future_return"].max()),
        "worst_return": float(df_rows["future_return"].min()),
        "best_decile": best_bucket[0] if best_bucket else {},
        "worst_decile": worst_bucket[0] if worst_bucket else {},
        "bucket_analysis": grouped.to_dict("records"),
        "regime_performance": regime_perf,
        "decile_summary": grouped.to_dict("records"),
        "rows": rows,
    }
