"""Triple-barrier labelling must describe exactly the trade the engine takes."""

import numpy as np
import pandas as pd

from forexai.config import LabelConfig
from forexai.labeling import LONG, NONE, SHORT, triple_barrier_labels

ATR = 0.0010
CFG = LabelConfig(tp_atr_mult=3.0, sl_atr_mult=1.5, max_holding_bars=10)


def flat_bars(n=40, price=1.1000):
    idx = pd.date_range("2024-01-02 08:00", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {"open": price, "high": price, "low": price, "close": price, "volume": 1.0},
        index=idx,
    )


def label_at(bars, i):
    atr = pd.Series(ATR, index=bars.index)
    return triple_barrier_labels(bars, atr, CFG)["label"].iloc[i]


def test_target_first_gives_long():
    bars = flat_bars()
    # decision at bar 10 -> entry at open of bar 11 = 1.1000, target 1.1030
    bars.iloc[13, bars.columns.get_loc("high")] = 1.10305
    assert label_at(bars, 10) == LONG


def test_target_first_gives_short():
    bars = flat_bars()
    bars.iloc[13, bars.columns.get_loc("low")] = 1.09695   # entry - 3 x ATR
    assert label_at(bars, 10) == SHORT


def test_stop_wins_ties_within_a_bar():
    """A bar that spans both barriers is resolved against us, on both sides."""
    bars = flat_bars()
    row = 13
    bars.iloc[row, bars.columns.get_loc("high")] = 1.10305   # long target AND short stop
    bars.iloc[row, bars.columns.get_loc("low")] = 1.09695    # long stop AND short target
    assert label_at(bars, 10) == NONE


def test_no_movement_is_no_trade():
    assert label_at(flat_bars(), 10) == NONE


def test_move_after_the_horizon_does_not_count():
    bars = flat_bars(n=60)
    # entry at bar 11, horizon 10 bars -> bar 25 is far outside the window
    bars.iloc[25, bars.columns.get_loc("high")] = 1.2000
    assert label_at(bars, 10) == NONE


def test_stop_before_target_is_not_a_win():
    bars = flat_bars()
    bars.iloc[12, bars.columns.get_loc("low")] = 1.09849     # long stop at 1.09850
    bars.iloc[14, bars.columns.get_loc("high")] = 1.10305    # target arrives too late
    assert label_at(bars, 10) == NONE


def test_missing_atr_is_never_labelled_as_a_trade():
    bars = flat_bars()
    atr = pd.Series(np.nan, index=bars.index)
    labels = triple_barrier_labels(bars, atr, CFG)
    resolved = labels["label"].dropna()
    assert (resolved == NONE).all()
