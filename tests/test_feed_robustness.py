"""A real feed is not a clean feed.

Yahoo returns spot FX with no volume at all - every bar zero. That is normal:
spot FX has no central exchange, so there is nothing to count. The failure it
caused was not the missing volume, it was that two derived features became NaN
on every row and, since a model row needs every feature, silently reduced
12 319 real bars to zero usable ones.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from forexai.config import Config
from forexai.data.synthetic import generate_ohlcv
from forexai.features import build_features, has_volume
from forexai.pipeline import build_dataset, explain_empty_dataset


@pytest.fixture(scope="module")
def bars():
    return generate_ohlcv(3_000, seed=5)


def test_has_volume_detects_a_feed_that_carries_none():
    index = pd.date_range("2024-01-02", periods=50, freq="1h", tz="UTC")
    assert not has_volume(pd.Series(0.0, index=index))
    assert not has_volume(pd.Series(1.0, index=index))          # constant placeholder
    assert not has_volume(pd.Series(np.nan, index=index))
    assert has_volume(pd.Series(np.arange(50, dtype=float), index=index))


@pytest.mark.parametrize("filler", [0.0, 1.0])
def test_a_feed_without_volume_still_produces_a_dataset(bars, filler):
    """The exact Yahoo case: this used to leave zero trainable rows."""
    flat = bars.copy()
    flat["volume"] = filler

    ds = build_dataset(flat, Config())
    assert len(ds.trainable()) > 2_000
    assert not ds.dropped_features
    features = ds.features[ds.feature_names]
    assert features["vol_z"].notna().all()
    assert features["vol_trend"].notna().all()


def test_volume_features_are_neutral_when_there_is_no_volume(bars):
    flat = bars.copy()
    flat["volume"] = 0.0
    features = build_features(flat)
    assert (features["vol_z"] == 0.0).all()          # neutral z-score
    assert (features["vol_trend"] == 1.0).all()      # neutral ratio


def test_a_real_volume_feed_is_still_used(bars):
    features = build_features(bars)
    assert features["vol_z"].std() > 0, "genuine volume must still inform the model"


def test_one_dead_column_cannot_empty_the_dataset(bars, monkeypatch):
    """Safety net behind the volume fix: any future all-NaN column is dropped."""
    import forexai.pipeline as pipeline

    original = pipeline.build_features

    def with_a_dead_column(df, atr_period=14):
        features = original(df, atr_period=atr_period)
        features["broken_feature"] = np.nan
        return features

    monkeypatch.setattr(pipeline, "build_features", with_a_dead_column)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ds = build_dataset(bars, Config())

    assert "broken_feature" in ds.dropped_features
    assert "broken_feature" not in ds.feature_names
    assert len(ds.trainable()) > 2_000, "the dataset must survive a dead column"
    assert any("broken_feature" in str(w.message) for w in caught), "the drop must be announced"


def test_the_diagnostic_names_the_guilty_columns(bars, monkeypatch):
    """Reporting zero rows without saying why is what left a user stuck."""
    import forexai.pipeline as pipeline

    original = pipeline.build_features

    def with_a_mostly_missing_column(df, atr_period=14):
        features = original(df, atr_period=atr_period)
        column = np.full(len(features), np.nan)
        column[:5] = 1.0                       # not entirely NaN, so it is kept
        features["patchy_feature"] = column
        return features

    monkeypatch.setattr(pipeline, "build_features", with_a_mostly_missing_column)
    ds = build_dataset(bars, Config())

    assert len(ds.trainable()) < 10
    explanation = explain_empty_dataset(ds)
    assert "patchy_feature" in explanation


def test_yahoo_style_frame_survives_the_whole_pipeline(bars):
    """End to end on a frame shaped exactly like the free feed's output."""
    from forexai.pipeline import fit_model, make_signals, run_backtest

    feed = bars.copy()
    feed["volume"] = 0.0
    cfg = Config()
    cfg.model.ensemble_weights = {"gbm": 0.0, "forest": 1.0, "linear": 0.0}

    ds = build_dataset(feed, cfg)
    index = ds.predictable()
    train, test = index[:1_800], index[1_900:]
    model = fit_model(ds, train, cfg)
    result = run_backtest(ds, make_signals(model, ds, test, cfg), test, cfg)
    assert len(result.equity) == len(test)
