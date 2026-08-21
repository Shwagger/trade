"""The rule-based head.

A transparent, regime-aware score in [-1, 1] built from classic technical
analysis. It exists for two reasons: it is auditable when the ML head does
something strange, and it gives the fusion layer a second opinion that was not
fitted to the same data.

The market gets classified into *trending* (ADX high) or *ranging* (ADX low),
and each regime uses the rules that make sense there: follow momentum in a
trend, fade extremes in a range.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TREND_ADX = 22.0


def _squash(x: pd.Series, scale: float) -> pd.Series:
    """Map an unbounded indicator onto [-1, 1] smoothly."""
    return np.tanh(x / scale)


def technical_score(features: pd.DataFrame) -> pd.DataFrame:
    """Return the fused technical score plus its components, per bar."""
    f = features
    out = pd.DataFrame(index=f.index)

    # --- trend-following block ------------------------------------------
    trend = (
        0.40 * _squash(f["ema_stack"], 1.0)
        + 0.25 * _squash(f["htf4_trend"], 3.0)
        + 0.20 * _squash(f["di_diff"], 25.0)
        + 0.15 * _squash(f["ema12_slope"], 0.6)
    )
    momentum = (
        0.5 * _squash(f["macd_hist"], 0.5)
        + 0.3 * _squash((f["rsi"] - 50.0), 18.0)
        + 0.2 * _squash(f["ret_6_atr"], 2.0)
    )
    breakout = _squash((f["donchian_pos"] - 0.5) * 2.0, 0.8)
    trend_signal = 0.45 * trend + 0.35 * momentum + 0.20 * breakout

    # --- mean-reversion block --------------------------------------------
    stretched = -_squash((f["bb_pct_b"] - 0.5) * 2.0, 0.55)
    rsi_fade = -_squash((f["rsi"] - 50.0), 14.0)
    wick_rejection = _squash(f["lower_wick"] - f["upper_wick"], 0.35)
    range_signal = 0.45 * stretched + 0.35 * rsi_fade + 0.20 * wick_rejection

    # --- regime blending --------------------------------------------------
    # Smooth transition instead of a hard switch, so the score does not flip
    # on an ADX tick around the threshold.
    trendiness = 1.0 / (1.0 + np.exp(-(f["adx"] - TREND_ADX) / 4.0))
    raw = trendiness * trend_signal + (1.0 - trendiness) * range_signal

    # --- volatility sanity gate -------------------------------------------
    # Dead markets and volatility explosions both degrade rule quality.
    vol_gate = np.exp(-((np.log(f["atr_ratio"].clip(lower=0.05)) / 0.85) ** 2))
    score = (raw * vol_gate).clip(-1.0, 1.0)

    out["ta_trend"] = trend_signal
    out["ta_range"] = range_signal
    out["ta_trendiness"] = trendiness
    out["ta_vol_gate"] = vol_gate
    out["ta_score"] = score
    return out
