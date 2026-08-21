"""Triple-barrier labelling.

The label answers the exact question the strategy asks at execution time:

    "If I open this trade at the next bar's open, with a stop at
     ``sl_atr_mult x ATR`` and a target at ``tp_atr_mult x ATR``, and I give it
     ``max_holding_bars`` bars - does it win?"

Classes
-------
``+1`` a long taken at bar i+1 hits target before stop
``-1`` a short taken at bar i+1 hits target before stop
`` 0`` neither side resolves in favour (timeout, or both directions stopped)

Long-win and short-win are mutually exclusive by construction, so the three
classes partition the sample. When a single bar's range covers both the target
and the stop, the stop is assumed to hit first - the pessimistic assumption,
because intrabar order is unknowable from OHLC data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import LabelConfig

LONG, SHORT, NONE = 1, -1, 0


def triple_barrier_labels(
    df: pd.DataFrame,
    atr: pd.Series,
    cfg: LabelConfig,
) -> pd.DataFrame:
    """Return per-bar labels plus diagnostics (entry price, barriers, horizon)."""
    open_ = df["open"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    atr_arr = atr.to_numpy(dtype=float)
    n = len(df)

    label = np.zeros(n, dtype=np.int8)
    entry = np.full(n, np.nan)
    bars_held = np.full(n, np.nan)
    outcome_r = np.full(n, np.nan)   # realised R multiple of the winning side

    tp_mult, sl_mult = cfg.tp_atr_mult, cfg.sl_atr_mult
    horizon = cfg.max_holding_bars

    for i in range(n - 1):
        a = atr_arr[i]
        if not np.isfinite(a) or a <= 0.0:
            label[i] = NONE
            continue

        px = open_[i + 1]                    # execution happens on the NEXT open
        entry[i] = px
        long_tp, long_sl = px + tp_mult * a, px - sl_mult * a
        short_tp, short_sl = px - tp_mult * a, px + sl_mult * a

        long_done = short_done = False
        result = NONE
        held = np.nan

        stop = min(i + 1 + horizon, n)
        for j in range(i + 1, stop):
            hi, lo = high[j], low[j]

            if not long_done:
                if lo <= long_sl:            # stop checked first: pessimistic
                    long_done = True
                elif hi >= long_tp:
                    long_done = True
                    result, held = LONG, j - i
                    break
            if not short_done:
                if hi >= short_sl:
                    short_done = True
                elif lo <= short_tp:
                    short_done = True
                    result, held = SHORT, j - i
                    break
            if long_done and short_done:
                break

        label[i] = result
        if result != NONE:
            bars_held[i] = held
            outcome_r[i] = tp_mult / sl_mult

    # The final bar can never be labelled (no next open to enter on).
    label[-1] = NONE
    entry[-1] = np.nan

    out = pd.DataFrame(
        {
            "label": label,
            "entry": entry,
            "bars_held": bars_held,
            "outcome_r": outcome_r,
        },
        index=df.index,
    )
    # Bars whose forward window runs past the end of the data are unlabelled,
    # not "no trade" - drop them so they never train the model.
    out.iloc[-cfg.max_holding_bars:, out.columns.get_loc("label")] = np.nan
    return out


def label_distribution(labels: pd.Series) -> dict:
    counts = labels.value_counts(dropna=True)
    total = counts.sum()
    return {
        "long": int(counts.get(LONG, 0)),
        "short": int(counts.get(SHORT, 0)),
        "none": int(counts.get(NONE, 0)),
        "long_pct": round(100.0 * counts.get(LONG, 0) / total, 2) if total else 0.0,
        "short_pct": round(100.0 * counts.get(SHORT, 0) / total, 2) if total else 0.0,
        "none_pct": round(100.0 * counts.get(NONE, 0) / total, 2) if total else 0.0,
        "total": int(total),
    }
