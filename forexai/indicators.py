"""Vectorised technical indicators.

Every function returns a Series aligned to the input index and uses *only*
information available at or before each bar's close. No indicator here peeks
into the future - that property is asserted in ``tests/test_no_lookahead.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's ATR."""
    return true_range(df).ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.fillna(50.0).where(avg_gain.notna(), np.nan)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(series, fast) - ema(series, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, sig, line - sig


def bollinger(series: pd.Series, period: int = 20, mult: float = 2.0):
    mid = sma(series, period)
    sd = series.rolling(period, min_periods=period).std(ddof=0)
    upper, lower = mid + mult * sd, mid - mult * sd
    width = (upper - lower) / mid.replace(0.0, np.nan)
    pct_b = (series - lower) / (upper - lower).replace(0.0, np.nan)
    return mid, upper, lower, width, pct_b


def adx(df: pd.DataFrame, period: int = 14):
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = true_range(df)

    atr_ = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    plus_di = 100.0 * pd.Series(plus_dm, index=df.index).ewm(
        alpha=1.0 / period, adjust=False, min_periods=period
    ).mean() / atr_.replace(0.0, np.nan)
    minus_di = 100.0 * pd.Series(minus_dm, index=df.index).ewm(
        alpha=1.0 / period, adjust=False, min_periods=period
    ).mean() / atr_.replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx_ = dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return adx_, plus_di, minus_di


def donchian(df: pd.DataFrame, period: int = 20):
    """Channel built from *completed* bars only (current bar excluded)."""
    upper = df["high"].shift(1).rolling(period, min_periods=period).max()
    lower = df["low"].shift(1).rolling(period, min_periods=period).min()
    mid = (upper + lower) / 2.0
    return upper, lower, mid


def stochastic(df: pd.DataFrame, period: int = 14, smooth: int = 3):
    hh = df["high"].rolling(period, min_periods=period).max()
    ll = df["low"].rolling(period, min_periods=period).min()
    k = 100.0 * (df["close"] - ll) / (hh - ll).replace(0.0, np.nan)
    return k, k.rolling(smooth, min_periods=smooth).mean()


def zscore(series: pd.Series, period: int) -> pd.Series:
    mean = series.rolling(period, min_periods=period).mean()
    sd = series.rolling(period, min_periods=period).std(ddof=0)
    return (series - mean) / sd.replace(0.0, np.nan)


def realised_vol(series: pd.Series, period: int) -> pd.Series:
    return np.log(series).diff().rolling(period, min_periods=period).std(ddof=0)
