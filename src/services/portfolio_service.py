"""Portfolio analysis service — multi-ticker scoring, concentration, correlation."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.utils.logging_utils import get_logger
from src.utils.math_utils import herfindahl_hirschman_index

logger = get_logger(__name__)


def analyse_portfolio_concentration(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute HHI and flag over-concentrated positions."""
    weights = [float(h.get("weight", 0)) for h in holdings]
    if not weights:
        return {"status": "ERROR", "message": "No holdings provided."}

    hhi = herfindahl_hirschman_index(weights)
    top = max(weights)

    concentration_label = "LOW"
    if hhi > 0.25:
        concentration_label = "HIGH"
    elif hhi > 0.15:
        concentration_label = "MODERATE"

    warnings = []
    for h in holdings:
        w = float(h.get("weight", 0))
        if w > 0.25:
            warnings.append(f"{h.get('ticker', '?')} is {w*100:.1f}% of portfolio — consider trimming.")

    return {
        "status": "SUCCESS",
        "hhi": round(hhi, 4),
        "concentration_label": concentration_label,
        "top_holding_weight": round(top, 4),
        "num_holdings": len(holdings),
        "warnings": warnings,
    }


def compute_correlation_matrix(
    tickers: List[str],
    dataset_path: str = "data/stock_prices_daily.csv",
    lookback_days: int = 252,
) -> Dict[str, Any]:
    """Compute return correlation matrix from CSV data."""
    try:
        import pandas as pd

        df = pd.read_csv(dataset_path, parse_dates=["Date"])
        df.columns = [c.strip() for c in df.columns]
        df = df[df["Ticker"].isin([t.upper() for t in tickers])]
        df = df.sort_values("Date").tail(lookback_days * len(tickers))

        pivot = df.pivot_table(index="Date", columns="Ticker", values="Close")
        returns = pivot.pct_change().dropna()

        if returns.empty or returns.shape[1] < 2:
            return {"status": "UNAVAILABLE", "message": "Insufficient data for correlation."}

        corr = returns.corr().round(3)
        avg_corr = float(corr.values[corr.values < 1].mean()) if corr.size > 1 else 0.0

        risk_label = "LOW"
        if avg_corr > 0.7:
            risk_label = "HIGH"
        elif avg_corr > 0.4:
            risk_label = "MODERATE"

        return {
            "status": "SUCCESS",
            "matrix": corr.to_dict(),
            "tickers": list(corr.columns),
            "average_correlation": round(avg_corr, 3),
            "correlation_risk_label": risk_label,
        }
    except Exception as exc:
        logger.warning(f"[PortfolioService] Correlation matrix failed: {exc}")
        return {"status": "UNAVAILABLE", "message": str(exc)}


def build_portfolio_summary(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate BUY/HOLD/SELL signals and weighted score across holdings."""
    buy = hold = sell = 0
    weighted_score = 0.0
    total_weight = 0.0

    for h in holdings:
        signal = (h.get("signal") or "").upper()
        weight = float(h.get("weight", 0))
        score = h.get("score")

        if signal == "BUY":
            buy += 1
        elif signal == "SELL":
            sell += 1
        else:
            hold += 1

        if score is not None:
            weighted_score += float(score) * weight
            total_weight += weight

    if total_weight > 0:
        weighted_score /= total_weight

    overall_signal = "HOLD"
    if buy > hold and buy > sell:
        overall_signal = "BUY"
    elif sell > hold and sell > buy:
        overall_signal = "SELL"

    return {
        "buy_count": buy,
        "hold_count": hold,
        "sell_count": sell,
        "overall_signal": overall_signal,
        "weighted_score": round(weighted_score, 2),
        "num_holdings": len(holdings),
    }


def analyse_portfolio(
    holdings: List[Dict[str, Any]],
    dataset_path: str = "data/stock_prices_daily.csv",
) -> Dict[str, Any]:
    """Full portfolio analysis: concentration + correlation + summary."""
    if not holdings:
        return {"status": "ERROR", "message": "No holdings provided."}

    concentration = analyse_portfolio_concentration(holdings)
    tickers = [h["ticker"] for h in holdings if h.get("ticker")]
    correlation = compute_correlation_matrix(tickers, dataset_path) if len(tickers) >= 2 else {"status": "UNAVAILABLE", "message": "Need 2+ tickers."}
    summary = build_portfolio_summary(holdings)

    return {
        "status": "SUCCESS",
        "holdings": holdings,
        "concentration": concentration,
        "correlation": correlation,
        "summary": summary,
    }
