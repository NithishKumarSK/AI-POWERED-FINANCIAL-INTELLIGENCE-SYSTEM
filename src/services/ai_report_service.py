"""AI report service — Gemini-powered narrative with deterministic fallback.

AI output is ONLY used for narrative/summary text. It CANNOT override:
- BUY/HOLD/SELL decisions (always from scoring engine)
- confidence scores (always deterministic)
- risk labels (always deterministic)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.config.settings import settings
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def _build_stock_prompt(symbol: str, data: Dict[str, Any]) -> str:
    verdict = data.get("verdict", {}) or {}
    scores = data.get("scores", {}) or {}
    return f"""You are an AI Financial Analyst. Summarise the analysis for {symbol}.

Decision: {verdict.get('value', 'N/A')} (score {verdict.get('score', 'N/A')}/100)
Confidence: {verdict.get('confidence', 'N/A')}%
Risk: {verdict.get('risk_label', 'N/A')}
Fundamental score: {scores.get('fundamental', 'N/A')}
Technical score: {scores.get('technical', 'N/A')}
Valuation score: {scores.get('valuation', 'N/A')}
Macro score: {scores.get('macro', 'N/A')}
Sentiment score: {scores.get('sentiment', 'N/A')}

Write 3–4 concise sentences: key strengths, key risks, and what drives the decision.
Do NOT override the decision or confidence values. Plain prose, no markdown headers."""


def _build_portfolio_prompt(data: Dict[str, Any]) -> str:
    summary = data.get("summary", {}) or {}
    holdings = data.get("holdings", []) or []
    tickers = [h.get("ticker", "") for h in holdings[:10]]
    return f"""You are an AI Financial Analyst. Summarise this portfolio analysis.

Holdings ({len(holdings)}): {', '.join(tickers)}
Overall signal: {summary.get('overall_signal', 'N/A')}
Weighted score: {summary.get('weighted_score', 'N/A')}
BUY: {summary.get('buy_count', 0)} | HOLD: {summary.get('hold_count', 0)} | SELL: {summary.get('sell_count', 0)}
Concentration risk: {data.get('concentration', {}).get('concentration_label', 'N/A')}

Write 3–4 sentences: portfolio strength, risks, and a recommended action priority. Plain prose."""


def _build_backtest_prompt(data: Dict[str, Any]) -> str:
    return f"""You are an AI Financial Analyst. Summarise this backtest.

Ticker: {data.get('ticker', data.get('symbol', 'N/A'))}
Strategy: {data.get('strategy', 'N/A')}
Total return: {data.get('total_return_pct', 'N/A')}%
CAGR: {data.get('cagr', 'N/A')}
Max drawdown: {data.get('max_drawdown', 'N/A')}
Sharpe: {data.get('sharpe', data.get('sharpe_ratio', 'N/A'))}
Win rate: {data.get('win_rate', 'N/A')}
Num trades: {data.get('num_trades', 'N/A')}

Write 2–3 sentences: performance quality, risk-adjusted view, whether strategy appears viable. Plain prose."""


def _deterministic_fallback(report_type: str, data: Dict[str, Any]) -> str:
    if report_type == "stock":
        verdict = (data.get("verdict") or {}).get("value", "HOLD")
        symbol = data.get("symbol", "this stock")
        score = (data.get("verdict") or {}).get("score", "N/A")
        return (
            f"The analysis engine rates {symbol} as {verdict} with a composite score of {score}/100. "
            "The decision is derived from fundamental, technical, valuation, macro, and sentiment intelligence engines. "
            "Review the full factor breakdown for detailed attribution."
        )
    if report_type == "portfolio":
        summary = data.get("summary", {}) or {}
        signal = summary.get("overall_signal", "HOLD")
        n = summary.get("num_holdings", "N/A")
        return (
            f"Portfolio analysis of {n} holdings yields an overall signal of {signal}. "
            "Review concentration and correlation metrics for risk management insights."
        )
    if report_type == "backtest":
        tr = data.get("total_return_pct", "N/A")
        strategy = data.get("strategy", "the strategy")
        return f"Backtest of {strategy} returned {tr}%. Review drawdown and Sharpe for risk-adjusted performance."
    return "Analysis complete. Review the detailed metrics above."


def generate_report(
    report_type: str,
    data: Dict[str, Any],
    extra_context: str = "",
) -> Dict[str, Any]:
    """Generate an AI narrative report with deterministic fallback.

    report_type: 'stock' | 'portfolio' | 'backtest'
    Returns {"status", "report", "source"} where source is "gemini" or "deterministic".
    """
    if not settings.has_gemini:
        fallback = _deterministic_fallback(report_type, data)
        return {"status": "SUCCESS", "report": fallback, "source": "deterministic"}

    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.agent_model)

        if report_type == "stock":
            prompt = _build_stock_prompt(data.get("symbol", ""), data)
        elif report_type == "portfolio":
            prompt = _build_portfolio_prompt(data)
        elif report_type == "backtest":
            prompt = _build_backtest_prompt(data)
        else:
            prompt = f"Summarise this financial data in 3 sentences: {str(data)[:1000]}"

        if extra_context:
            prompt += f"\n\nAdditional context: {extra_context}"

        response = model.generate_content(
            prompt,
            generation_config={"temperature": settings.agent_temperature, "max_output_tokens": 400},
        )
        text = response.text.strip() if response.text else ""

        if not text:
            raise ValueError("Empty response from Gemini")

        logger.info(f"[AIReport] Gemini report generated for {report_type}.")
        return {"status": "SUCCESS", "report": text, "source": "gemini"}

    except Exception as exc:
        logger.warning(f"[AIReport] Gemini failed, using fallback: {exc}")
        fallback = _deterministic_fallback(report_type, data)
        return {"status": "SUCCESS", "report": fallback, "source": "deterministic"}
