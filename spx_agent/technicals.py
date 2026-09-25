"""
SPX Technical Indicators
Plain pandas implementations (Wilder smoothing for RSI/ATR/ADX, standard
EMA for MACD) -- no external TA library dependency.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd


def _to_frame(bars: List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, adjust=False).mean()


def compute_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = _wilder_smooth(gain, period)
    avg_loss = _wilder_smooth(loss, period)
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return _wilder_smooth(tr, period)


def compute_adx(df: pd.DataFrame, period: int = 14) -> Dict[str, pd.Series]:
    high, low = df["high"], df["low"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move
    atr = compute_atr(df, period)
    plus_di = 100 * _wilder_smooth(plus_dm, period) / atr.replace(0, float("nan"))
    minus_di = 100 * _wilder_smooth(minus_dm, period) / atr.replace(0, float("nan"))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
    adx = _wilder_smooth(dx.fillna(0), period)
    return {"adx": adx, "plus_di": plus_di, "minus_di": minus_di}


def compute_macd(closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return {"macd": macd_line, "signal": signal_line, "hist": macd_line - signal_line}


def build_technicals(bars: List[Dict]) -> Dict:
    """Returns latest-value technical snapshot plus a directional vote/bias."""
    df = _to_frame(bars)
    closes = df["close"]

    rsi = compute_rsi(closes)
    atr = compute_atr(df)
    adx = compute_adx(df)
    macd = compute_macd(closes)
    sma20 = closes.rolling(20).mean()
    sma50 = closes.rolling(50).mean()
    sma200 = closes.rolling(200).mean()

    last_close = closes.iloc[-1]
    votes: List[Tuple[int, str]] = []

    def vote(cond_bull: bool, cond_bear: bool, reason: str) -> None:
        if cond_bull:
            votes.append((1, reason))
        elif cond_bear:
            votes.append((-1, reason))
        else:
            votes.append((0, reason))

    vote(last_close > sma20.iloc[-1], last_close < sma20.iloc[-1], "price vs SMA20")
    vote(last_close > sma50.iloc[-1], last_close < sma50.iloc[-1], "price vs SMA50")
    vote(sma20.iloc[-1] > sma50.iloc[-1], sma20.iloc[-1] < sma50.iloc[-1], "SMA20 vs SMA50 trend")
    vote(rsi.iloc[-1] > 55, rsi.iloc[-1] < 45, "RSI(14) momentum")
    vote(macd["hist"].iloc[-1] > 0, macd["hist"].iloc[-1] < 0, "MACD histogram")
    vote(adx["plus_di"].iloc[-1] > adx["minus_di"].iloc[-1],
         adx["plus_di"].iloc[-1] < adx["minus_di"].iloc[-1], "DI+/DI- direction")

    score = sum(v for v, _ in votes)
    if score >= 3:
        bias = "Bullish"
    elif score <= -3:
        bias = "Bearish"
    elif score > 0:
        bias = "Mildly Bullish"
    elif score < 0:
        bias = "Mildly Bearish"
    else:
        bias = "Neutral"

    def _safe_round(v: float, nd: int = 2):
        return round(float(v), nd) if pd.notna(v) else None

    return {
        "rsi14": _safe_round(rsi.iloc[-1], 1),
        "atr14": _safe_round(atr.iloc[-1]),
        "adx14": _safe_round(adx["adx"].iloc[-1], 1),
        "plus_di": _safe_round(adx["plus_di"].iloc[-1], 1),
        "minus_di": _safe_round(adx["minus_di"].iloc[-1], 1),
        "macd_hist": _safe_round(macd["hist"].iloc[-1]),
        "sma20": _safe_round(sma20.iloc[-1]),
        "sma50": _safe_round(sma50.iloc[-1]),
        "sma200": _safe_round(sma200.iloc[-1]),
        "trend_bias": bias,
        "bias_score": score,
        "votes": votes,
    }
