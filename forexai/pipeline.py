"""Glue: raw bars -> features -> labels -> signals -> backtest.

Two entry points:

``build_dataset``   deterministic transformation of OHLCV into everything the
                    model and the risk engine need.
``run_backtest``    fit on a train slice, trade a test slice, return the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .backtest import Backtester, BacktestResult
from .config import Config
from .features import build_features, feature_columns
from .labeling import triple_barrier_labels
from .models.ensemble import MLEnsemble
from .models.technical import technical_score
from .risk import RiskManager
from .signal import fuse_signals


@dataclass
class Dataset:
    bars: pd.DataFrame
    features: pd.DataFrame
    labels: pd.DataFrame
    technical: pd.DataFrame
    feature_names: list
    # Row masks are pure functions of the frames above and are asked for once
    # per bar by the live monitor, so they are computed once and kept.
    _trainable: Optional[pd.Index] = None
    _predictable: Optional[pd.Index] = None

    @property
    def atr(self) -> pd.Series:
        return self.features["atr"]

    def _complete_rows(self) -> pd.Series:
        return self.features[self.feature_names].notna().all(axis=1)

    def trainable(self) -> pd.Index:
        """Rows with complete features *and* a resolved label."""
        if self._trainable is None:
            ok = self._complete_rows() & self.labels["label"].notna()
            self._trainable = self.features.index[ok]
        return self._trainable

    def predictable(self) -> pd.Index:
        """Rows with complete features (labels not required)."""
        if self._predictable is None:
            self._predictable = self.features.index[self._complete_rows()]
        return self._predictable


def build_dataset(bars: pd.DataFrame, cfg: Config) -> Dataset:
    features = build_features(bars, atr_period=cfg.labels.atr_period)
    labels = triple_barrier_labels(bars, features["atr"], cfg.labels)
    technical = technical_score(features)
    return Dataset(
        bars=bars,
        features=features,
        labels=labels,
        technical=technical,
        feature_names=feature_columns(features),
    )


def fit_model(ds: Dataset, train_index: pd.Index, cfg: Config) -> MLEnsemble:
    idx = train_index.intersection(ds.trainable())
    X = ds.features.loc[idx, ds.feature_names]
    y = ds.labels.loc[idx, "label"].astype(int)
    return MLEnsemble(cfg.model).fit(X, y)


def make_signals(model: MLEnsemble, ds: Dataset, index: pd.Index, cfg: Config) -> pd.DataFrame:
    idx = index.intersection(ds.predictable())
    if len(idx) == 0:
        return pd.DataFrame(
            columns=["direction", "score", "confidence", "ml_score", "ta_score", "reason"]
        )
    ml = model.directional_score(ds.features.loc[idx, ds.feature_names])
    ta = ds.technical.loc[idx]
    return fuse_signals(ml, ta, cfg.signal)


def run_backtest(
    ds: Dataset,
    signals: pd.DataFrame,
    index: pd.Index,
    cfg: Config,
    risk_manager: Optional[RiskManager] = None,
) -> BacktestResult:
    bars = ds.bars.loc[index]
    bt = Backtester(cfg, risk_manager)
    return bt.run(bars, signals.reindex(index), ds.atr.loc[index])
