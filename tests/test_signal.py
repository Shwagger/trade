"""Fusion gates: most bars must end up as WAIT, on every timeframe."""

import numpy as np
import pandas as pd

from forexai.config import ModelConfig, SignalConfig
from forexai.models.ensemble import MLEnsemble
from forexai.signal import BUY, SELL, WAIT, decide, fuse_signals


def frames(ml_score, ta_score, confidence=0.7, lift=2.0):
    idx = pd.date_range("2024-01-02", periods=1, freq="1h", tz="UTC")
    ml = pd.DataFrame(
        {"score": [ml_score], "confidence": [confidence], "lift": [lift]}, index=idx
    )
    ta = pd.DataFrame({"ta_score": [ta_score]}, index=idx)
    return ml, ta


def direction(ml_score, ta_score, confidence=0.7, lift=2.0, cfg=None):
    ml, ta = frames(ml_score, ta_score, confidence, lift)
    return int(fuse_signals(ml, ta, cfg or SignalConfig())["direction"].iloc[0])


def test_agreeing_strong_heads_produce_a_trade():
    assert direction(0.5, 0.5) == BUY
    assert direction(-0.5, -0.5) == SELL


def test_disagreement_blocks_the_trade():
    assert direction(0.6, -0.6) == WAIT


def test_disagreement_can_be_allowed_explicitly():
    assert direction(0.9, -0.1, cfg=SignalConfig(require_agreement=False)) == BUY


def test_weak_edge_is_wait():
    assert direction(0.05, 0.05) == WAIT


def test_confidence_at_the_base_rate_is_wait():
    """Being exactly as sure as the base rate is not an edge."""
    assert direction(0.6, 0.6, lift=1.0) == WAIT


def test_absolute_confidence_floor_is_off_by_default():
    """A low probability with a high lift still trades - that is the point."""
    assert direction(0.6, 0.6, confidence=0.18, lift=1.4) == BUY


def test_absolute_confidence_floor_can_be_switched_on():
    cfg = SignalConfig(min_confidence=0.40)
    assert direction(0.6, 0.6, confidence=0.18, lift=1.4, cfg=cfg) == WAIT


def test_reasons_are_reported():
    ml, ta = frames(0.02, 0.02)
    assert fuse_signals(ml, ta, SignalConfig())["reason"].iloc[0] == "edge below threshold"

    ml, ta = frames(0.6, 0.6, lift=1.0)
    assert (
        fuse_signals(ml, ta, SignalConfig())["reason"].iloc[0]
        == "confidence no better than the base rate"
    )


def test_decision_renders_for_humans():
    ml, ta = frames(0.5, 0.5)
    d = decide(fuse_signals(ml, ta, SignalConfig()).iloc[0])
    assert d.action == "BUY"
    assert "base rate" in str(d)


def _fit_toy_ensemble(class_weights):
    """Fit on a dataset whose class priors we control exactly."""
    rng = np.random.default_rng(0)
    n = 1500
    y = rng.choice([-1, 0, 1], size=n, p=class_weights)
    X = pd.DataFrame(
        {"f0": y + rng.normal(0, 0.7, n), "f1": rng.normal(0, 1, n)},
        index=pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC"),
    )
    cfg = ModelConfig(ensemble_weights={"gbm": 0.0, "forest": 1.0, "linear": 0.0})
    return MLEnsemble(cfg).fit(X, pd.Series(y, index=X.index)), X


def test_priors_are_learned_from_the_training_set():
    model, _ = _fit_toy_ensemble([0.13, 0.74, 0.13])
    assert model.priors_[0] > 0.6
    assert 0.05 < model.priors_[1] < 0.25


def test_score_does_not_collapse_when_the_no_trade_class_dominates():
    """The failure that froze the daily configuration: a raw p_long - p_short
    shrinks with the no-trade mass, a normalised one does not."""
    balanced, X_bal = _fit_toy_ensemble([0.33, 0.34, 0.33])
    skewed, X_skew = _fit_toy_ensemble([0.13, 0.74, 0.13])

    spread_balanced = balanced.directional_score(X_bal)["score"].abs().median()
    spread_skewed = skewed.directional_score(X_skew)["score"].abs().median()
    # Same signal strength in the features, so the scores must stay comparable.
    assert spread_skewed > 0.5 * spread_balanced


def test_lift_is_relative_to_the_base_rate():
    skewed, X = _fit_toy_ensemble([0.13, 0.74, 0.13])
    out = skewed.directional_score(X)
    assert (out["lift"] > 1.0).any()          # some bars beat the base rate
    assert out["confidence"].max() < 0.9      # while staying low in absolute terms
