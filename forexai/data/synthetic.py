"""Synthetic but *honest* FX bar generator.

The point of this module is to exercise the whole pipeline (features, labels,
model, risk, backtest) without a data feed. It deliberately produces a series
that is close to a random walk: regime-switching drift, volatility clustering
and intraday seasonality, with no hidden deterministic pattern planted in it.

If a strategy shows a huge edge on this data, the bug is in the strategy, not
in the market.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Rough EURUSD hourly volatility profile (UTC). Low in the Asian session,
# peaking during the London/New-York overlap.
_HOUR_VOL_PROFILE = np.array(
    [0.55, 0.45, 0.45, 0.50, 0.60, 0.70, 0.85, 1.05,
     1.25, 1.35, 1.30, 1.15, 1.10, 1.45, 1.60, 1.55,
     1.35, 1.15, 0.95, 0.80, 0.70, 0.65, 0.60, 0.55]
)


def _trading_index(bars: int, start: str = "2015-01-05 00:00", freq: str = "1h") -> pd.DatetimeIndex:
    """Business-hour index that skips the FX weekend (Fri 21:00 -> Sun 22:00 UTC)."""
    raw = pd.date_range(start=start, periods=int(bars * 1.55) + 500, freq=freq, tz="UTC")
    dow, hour = raw.dayofweek, raw.hour
    closed = (
        (dow == 5)
        | ((dow == 4) & (hour >= 21))
        | ((dow == 6) & (hour < 22))
    )
    return raw[~closed][:bars]


def generate_ohlcv(
    bars: int = 30_000,
    seed: int = 42,
    start_price: float = 1.1000,
    pip_size: float = 0.0001,
    substeps: int = 12,
    return_regimes: bool = False,
):
    """Generate `bars` OHLCV rows with realistic microstructure."""
    rng = np.random.default_rng(seed)
    index = _trading_index(bars)
    n = len(index)

    # --- regime chain: 0 = range, 1 = up-trend, 2 = down-trend ----------
    transition = np.array(
        [[0.985, 0.0075, 0.0075],
         [0.010, 0.9880, 0.0020],
         [0.010, 0.0020, 0.9880]]
    )
    drift_per_bar = np.array([0.0, 0.28, -0.28]) * pip_size   # pips of drift / bar
    mean_reversion = np.array([0.045, 0.010, 0.010])          # pull back to anchor

    regimes = np.empty(n, dtype=int)
    regimes[0] = 0
    for i in range(1, n):
        regimes[i] = rng.choice(3, p=transition[regimes[i - 1]])

    # --- GARCH(1,1)-like volatility in pips -----------------------------
    omega, alpha, beta = 1.8, 0.09, 0.88
    base_var = omega / max(1e-9, (1.0 - alpha - beta))
    var = base_var
    hourly_mult = _HOUR_VOL_PROFILE[index.hour.to_numpy()]

    opens = np.empty(n)
    highs = np.empty(n)
    lows = np.empty(n)
    closes = np.empty(n)
    volumes = np.empty(n)

    price = start_price
    anchor = start_price
    sub_scale = 1.0 / np.sqrt(substeps)

    for i in range(n):
        r = regimes[i]
        sigma_pips = np.sqrt(var) * hourly_mult[i]
        sigma = sigma_pips * pip_size

        # Anchor drifts slowly towards price; range regimes revert to it.
        anchor += (price - anchor) * 0.02
        mu = drift_per_bar[r] + mean_reversion[r] * (anchor - price)

        steps = rng.standard_normal(substeps) * sigma * sub_scale + mu / substeps
        # Fat tails: occasional jump (news).
        if rng.random() < 0.004:
            steps[rng.integers(substeps)] += rng.standard_normal() * sigma * 3.5

        path = price + np.cumsum(steps)
        opens[i] = price
        highs[i] = max(price, path.max())
        lows[i] = min(price, path.min())
        closes[i] = path[-1]
        volumes[i] = max(1.0, rng.gamma(4.0, 1.0) * 250 * hourly_mult[i] * (sigma_pips / 3.0))

        realised = (closes[i] - opens[i]) / pip_size
        var = omega + alpha * realised**2 + beta * var
        var = float(np.clip(var, 0.2, 400.0))
        price = closes[i]

    df = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=index,
    )
    df.index.name = "time"
    if return_regimes:
        return df, pd.Series(regimes, index=index, name="regime")
    return df
