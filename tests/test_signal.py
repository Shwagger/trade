"""Fusion gates: most bars must end up as WAIT."""

import pandas as pd

from forexai.config import SignalConfig
from forexai.signal import BUY, SELL, WAIT, decide, fuse_signals


def frames(ml_score, ta_score, confidence=0.7):
    idx = pd.date_range("2024-01-02", periods=1, freq="1h", tz="UTC")
    ml = pd.DataFrame({"score": [ml_score], "confidence": [confidence]}, index=idx)
    ta = pd.DataFrame({"ta_score": [ta_score]}, index=idx)
    return ml, ta


def direction(ml_score, ta_score, confidence=0.7, cfg=None):
    ml, ta = frames(ml_score, ta_score, confidence)
    out = fuse_signals(ml, ta, cfg or SignalConfig())
    return int(out["direction"].iloc[0])


def test_agreeing_strong_heads_produce_a_trade():
    assert direction(0.5, 0.5) == BUY
    assert direction(-0.5, -0.5) == SELL


def test_disagreement_blocks_the_trade():
    assert direction(0.6, -0.6) == WAIT


def test_disagreement_can_be_allowed_explicitly():
    cfg = SignalConfig(require_agreement=False)
    assert direction(0.9, -0.1, cfg=cfg) == BUY


def test_weak_edge_is_wait():
    assert direction(0.05, 0.05) == WAIT


def test_low_confidence_is_wait():
    assert direction(0.6, 0.6, confidence=0.2) == WAIT


def test_reason_is_reported():
    ml, ta = frames(0.02, 0.02)
    out = fuse_signals(ml, ta, SignalConfig())
    assert out["reason"].iloc[0] == "edge below threshold"


def test_decision_renders_for_humans():
    ml, ta = frames(0.5, 0.5)
    d = decide(fuse_signals(ml, ta, SignalConfig()).iloc[0])
    assert d.action == "BUY"
    assert "confidence" in str(d)
