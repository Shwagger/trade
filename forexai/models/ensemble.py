"""The machine-learning head.

Three learners with genuinely different inductive biases vote on the same
three-class problem (short-win / no-trade / long-win):

* ``gbm``    - histogram gradient boosting: non-linear interactions, handles NaN
* ``forest`` - random forest: variance reduction, robust to noisy features
* ``linear`` - scaled logistic regression: the sanity check; when the trees beat
               it by a mile on train and lose to it out-of-sample, we were fitting noise

Probabilities are calibrated on a time-ordered tail of the training window
(never on the test window), then blended with fixed weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ..config import ModelConfig

CLASSES = [-1, 0, 1]  # short-win, no-trade, long-win

try:  # scikit-learn >= 1.6 replaced cv="prefit" with an explicit wrapper
    from sklearn.frozen import FrozenEstimator

    def _freeze(estimator):
        return CalibratedClassifierCV(FrozenEstimator(estimator), method="sigmoid")

except ImportError:  # pragma: no cover - older scikit-learn

    def _freeze(estimator):
        return CalibratedClassifierCV(estimator, method="sigmoid", cv="prefit")


def _make_estimators(cfg: ModelConfig) -> Dict[str, object]:
    rs = cfg.random_state
    return {
        "gbm": HistGradientBoostingClassifier(
            max_iter=250,
            learning_rate=0.05,
            max_depth=4,
            min_samples_leaf=40,
            l2_regularization=1.0,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=25,
            random_state=rs,
        ),
        "forest": RandomForestClassifier(
            n_estimators=300,
            max_depth=8,
            min_samples_leaf=40,
            max_features="sqrt",
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=rs,
        ),
        "linear": Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        C=0.25,
                        max_iter=2000,
                        class_weight="balanced",
                        random_state=rs,
                    ),
                ),
            ]
        ),
    }


@dataclass
class EnsembleReport:
    n_train: int
    n_calibration: int
    class_counts: Dict[int, int]
    fitted: List[str]


class MLEnsemble:
    """Weighted soft-voting ensemble producing calibrated class probabilities."""

    def __init__(self, cfg: ModelConfig | None = None):
        self.cfg = cfg or ModelConfig()
        self.models: Dict[str, object] = {}
        self.weights: Dict[str, float] = {}
        self.feature_names: List[str] = []
        self.classes_ = np.array(CLASSES)
        self.report: EnsembleReport | None = None

    # ------------------------------------------------------------------
    def fit(self, X: pd.DataFrame, y: pd.Series) -> "MLEnsemble":
        if len(X) < self.cfg.min_train_samples:
            raise ValueError(
                f"need at least {self.cfg.min_train_samples} training rows, got {len(X)}"
            )
        self.feature_names = list(X.columns)
        X_arr = X.to_numpy(dtype=float)
        y_arr = y.to_numpy(dtype=int)

        # Time-ordered calibration split: the calibrator only ever sees data
        # that comes *after* what the base learner was fitted on.
        frac = float(np.clip(self.cfg.calibration_fraction, 0.0, 0.4))
        n_cal = int(len(X_arr) * frac)
        can_calibrate = n_cal >= 150 and len(np.unique(y_arr[-n_cal:])) == len(CLASSES)
        if can_calibrate:
            X_base, y_base = X_arr[:-n_cal], y_arr[:-n_cal]
            X_cal, y_cal = X_arr[-n_cal:], y_arr[-n_cal:]
        else:
            n_cal = 0
            X_base, y_base = X_arr, y_arr
            X_cal = y_cal = None

        self.models, self.weights, fitted = {}, {}, []
        for name, est in _make_estimators(self.cfg).items():
            weight = float(self.cfg.ensemble_weights.get(name, 0.0))
            if weight <= 0.0:
                continue
            est.fit(X_base, y_base)
            if can_calibrate:
                est = _freeze(est)
                est.fit(X_cal, y_cal)
            self.models[name] = est
            self.weights[name] = weight
            fitted.append(name)

        total = sum(self.weights.values())
        if total <= 0:
            raise ValueError("no model has a positive ensemble weight")
        self.weights = {k: v / total for k, v in self.weights.items()}

        self.report = EnsembleReport(
            n_train=len(X_base),
            n_calibration=int(n_cal),
            class_counts={int(c): int((y_arr == c).sum()) for c in CLASSES},
            fitted=fitted,
        )
        return self

    # ------------------------------------------------------------------
    def predict_proba(self, X: pd.DataFrame) -> pd.DataFrame:
        """Return P(short), P(none), P(long) as a DataFrame indexed like X."""
        if not self.models:
            raise RuntimeError("ensemble is not fitted")
        X_arr = X[self.feature_names].to_numpy(dtype=float)
        blended = np.zeros((len(X_arr), len(CLASSES)))

        for name, model in self.models.items():
            proba = model.predict_proba(X_arr)
            aligned = np.zeros_like(blended)
            for col, cls in enumerate(getattr(model, "classes_", CLASSES)):
                aligned[:, CLASSES.index(int(cls))] = proba[:, col]
            blended += self.weights[name] * aligned

        blended /= blended.sum(axis=1, keepdims=True)
        return pd.DataFrame(
            blended, index=X.index, columns=["p_short", "p_none", "p_long"]
        )

    def directional_score(self, X: pd.DataFrame) -> pd.DataFrame:
        """Signed edge in [-1, 1] plus the winning-side probability."""
        proba = self.predict_proba(X)
        proba["score"] = proba["p_long"] - proba["p_short"]
        proba["confidence"] = proba[["p_long", "p_short"]].max(axis=1)
        return proba

    # ------------------------------------------------------------------
    def feature_importance(self, top: int = 20) -> pd.Series:
        """Impurity importance from the forest, when it is part of the blend."""
        forest = self.models.get("forest")
        if forest is None:
            return pd.Series(dtype=float)
        base = forest
        if isinstance(base, CalibratedClassifierCV):
            base = base.calibrated_classifiers_[0].estimator
        base = getattr(base, "estimator", base)   # unwrap FrozenEstimator
        if not hasattr(base, "feature_importances_"):
            return pd.Series(dtype=float)
        return (
            pd.Series(base.feature_importances_, index=self.feature_names)
            .sort_values(ascending=False)
            .head(top)
        )
