"""The single most important property: no feature may know the future.

If truncating the data changes a past feature value, the backtest is a lie.
"""

import numpy as np
import pandas as pd

from forexai.config import LabelConfig
from forexai.data.synthetic import generate_ohlcv
from forexai.features import build_features
from forexai.labeling import triple_barrier_labels
from forexai.models.technical import technical_score


def test_features_are_causal():
    bars = generate_ohlcv(1200, seed=101)
    cut = 900

    full = build_features(bars)
    truncated = build_features(bars.iloc[:cut])

    common = truncated.index
    a = full.loc[common]
    b = truncated
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9, atol=1e-12)


def test_features_ignore_mutated_future():
    """Corrupting bar 800 onwards must not move a single feature before bar 800."""
    bars = generate_ohlcv(1000, seed=7)
    mutated = bars.copy()
    mutated.iloc[800:] *= 1.05

    base = build_features(bars).iloc[:800]
    after = build_features(mutated).iloc[:800]
    pd.testing.assert_frame_equal(base, after, check_exact=False, rtol=1e-9, atol=1e-12)


def test_technical_score_is_causal():
    bars = generate_ohlcv(900, seed=13)
    full = technical_score(build_features(bars))
    truncated = technical_score(build_features(bars.iloc[:700]))
    pd.testing.assert_frame_equal(
        full.loc[truncated.index], truncated, check_exact=False, rtol=1e-9, atol=1e-12
    )


def test_labels_at_the_tail_are_unresolved():
    """Bars whose forward window runs past the data end must not be labelled."""
    bars = generate_ohlcv(600, seed=21)
    features = build_features(bars)
    cfg = LabelConfig()
    labels = triple_barrier_labels(bars, features["atr"], cfg)
    assert labels["label"].iloc[-cfg.max_holding_bars :].isna().all()


def test_labels_use_the_next_open_as_entry():
    bars = generate_ohlcv(400, seed=33)
    features = build_features(bars)
    labels = triple_barrier_labels(bars, features["atr"], LabelConfig())
    entries = labels["entry"].dropna()
    expected = bars["open"].shift(-1).loc[entries.index]
    np.testing.assert_allclose(entries.to_numpy(), expected.to_numpy(), rtol=0, atol=1e-12)
