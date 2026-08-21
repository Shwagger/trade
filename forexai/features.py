"""Feature engineering.

Row ``i`` of the returned matrix contains only information known at the close
of bar ``i``. The trading loop consumes row ``i`` and executes on the open of
bar ``i + 1``; that one-bar gap is what makes the backtest honest.

Features are deliberately scale-free (returns, ATR-normalised distances,
z-scores, ratios) so a model trained on 2015 prices still means something in
2025.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind

# UTC session boundaries (approximate, DST ignored on purpose - it is a feature
# bucket, not an execution rule).
SESSIONS = {
    "sydney": (21, 24),
    "asia": (0, 7),
    "london": (7, 12),
    "overlap": (12, 16),
    "newyork": (16, 21),
}


def session_of(hour: int) -> str:
    if 12 <= hour < 16:
        return "overlap"
    if 7 <= hour < 12:
        return "london"
    if 16 <= hour < 21:
        return "newyork"
    if hour >= 21:
        return "sydney"
    return "asia"


def has_volume(volume: pd.Series) -> bool:
    """True when the feed actually carries volume information.

    A constant column - all zeros, or a broker's placeholder - carries none.
    """
    clean = volume.dropna()
    if clean.empty or float(clean.abs().sum()) == 0.0:
        return False
    return float(clean.std(ddof=0)) > 0.0


def build_features(df: pd.DataFrame, atr_period: int = 14) -> pd.DataFrame:
    """Return a feature matrix aligned to ``df`` (same index, NaN warm-up)."""
    close, high, low, open_, volume = (
        df["close"], df["high"], df["low"], df["open"], df["volume"]
    )
    out = pd.DataFrame(index=df.index)

    atr = ind.atr(df, atr_period)
    atr_safe = atr.replace(0.0, np.nan)
    out["atr"] = atr

    # --- momentum -------------------------------------------------------
    logc = np.log(close)
    for h in (1, 2, 3, 6, 12, 24, 48):
        out[f"ret_{h}"] = logc.diff(h)
    # Return normalised by prevailing volatility: "how big was this move,
    # relative to what this market normally does".
    out["ret_1_atr"] = (close - close.shift(1)) / atr_safe
    out["ret_6_atr"] = (close - close.shift(6)) / atr_safe
    out["ret_24_atr"] = (close - close.shift(24)) / atr_safe

    # --- trend ----------------------------------------------------------
    ema_fast, ema_mid, ema_slow = (ind.ema(close, p) for p in (12, 26, 100))
    out["dist_ema12"] = (close - ema_fast) / atr_safe
    out["dist_ema26"] = (close - ema_mid) / atr_safe
    out["dist_ema100"] = (close - ema_slow) / atr_safe
    out["ema_stack"] = (ema_fast - ema_mid) / atr_safe
    out["ema_stack_slow"] = (ema_mid - ema_slow) / atr_safe
    out["ema12_slope"] = ema_fast.diff(3) / atr_safe
    out["ema100_slope"] = ema_slow.diff(12) / atr_safe

    # Higher-timeframe context: 4x and 24x the base timeframe.
    out["htf4_trend"] = (close - ind.ema(close, 12 * 4)) / atr_safe
    out["htf24_trend"] = (close - ind.ema(close, 12 * 24)) / atr_safe

    adx_, plus_di, minus_di = ind.adx(df, 14)
    out["adx"] = adx_
    out["di_diff"] = plus_di - minus_di

    # --- oscillators ----------------------------------------------------
    rsi14 = ind.rsi(close, 14)
    out["rsi"] = rsi14
    out["rsi_slope"] = rsi14.diff(3)
    macd_line, macd_sig, macd_hist = ind.macd(close)
    out["macd_hist"] = macd_hist / atr_safe
    out["macd_line"] = macd_line / atr_safe
    stoch_k, stoch_d = ind.stochastic(df)
    out["stoch_k"] = stoch_k
    out["stoch_kd"] = stoch_k - stoch_d

    # --- volatility -----------------------------------------------------
    _, bb_up, bb_low, bb_width, pct_b = ind.bollinger(close, 20, 2.0)
    out["bb_pct_b"] = pct_b
    out["bb_width_z"] = ind.zscore(bb_width, 100)
    rv_short, rv_long = ind.realised_vol(close, 12), ind.realised_vol(close, 96)
    out["vol_ratio"] = rv_short / rv_long.replace(0.0, np.nan)
    out["atr_ratio"] = atr / ind.sma(atr, 100).replace(0.0, np.nan)
    out["atr_pips_z"] = ind.zscore(atr, 200)

    # --- structure ------------------------------------------------------
    dc_up, dc_low, dc_mid = ind.donchian(df, 20)
    span = (dc_up - dc_low).replace(0.0, np.nan)
    out["donchian_pos"] = (close - dc_low) / span
    out["dist_dc_high"] = (dc_up - close) / atr_safe
    out["dist_dc_low"] = (close - dc_low) / atr_safe
    hh100 = high.shift(1).rolling(100, min_periods=100).max()
    ll100 = low.shift(1).rolling(100, min_periods=100).min()
    out["dist_hh100"] = (hh100 - close) / atr_safe
    out["dist_ll100"] = (close - ll100) / atr_safe

    # --- candle anatomy --------------------------------------------------
    bar_range = (high - low).replace(0.0, np.nan)
    out["body_ratio"] = (close - open_) / bar_range
    out["upper_wick"] = (high - np.maximum(close, open_)) / bar_range
    out["lower_wick"] = (np.minimum(close, open_) - low) / bar_range
    out["range_atr"] = bar_range / atr_safe
    direction = np.sign(close - open_)
    streak = direction.groupby((direction != direction.shift()).cumsum()).cumcount() + 1
    out["streak"] = (streak * direction).clip(-6, 6)

    # --- flow ------------------------------------------------------------
    # Spot FX has no central exchange, so there is no true volume. Free feeds
    # (Yahoo among them) return a column of zeros. That is a feed without
    # volume, not a broken market: derive nothing from it rather than emitting
    # NaN on every row, which would empty the training set entirely.
    if has_volume(volume):
        out["vol_z"] = ind.zscore(volume, 96)
        out["vol_trend"] = volume / ind.sma(volume, 24).replace(0.0, np.nan)
    else:
        out["vol_z"] = 0.0          # neutral z-score
        out["vol_trend"] = 1.0      # neutral ratio

    # --- clock -----------------------------------------------------------
    hour = df.index.hour.to_numpy()
    dow = df.index.dayofweek.to_numpy()
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    out["dow_sin"] = np.sin(2 * np.pi * dow / 5)
    out["dow_cos"] = np.cos(2 * np.pi * dow / 5)
    for name in ("asia", "london", "overlap", "newyork"):
        lo, hi = SESSIONS[name]
        out[f"sess_{name}"] = ((hour >= lo) & (hour < hi)).astype(float)

    return out.replace([np.inf, -np.inf], np.nan)


def feature_columns(features: pd.DataFrame) -> list[str]:
    """Model inputs = every column except the ATR passed through for risk sizing."""
    return [c for c in features.columns if c != "atr"]
