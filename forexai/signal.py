"""Signal fusion: two opinions in, one decision out.

The ML head gives a calibrated directional edge; the technical head gives an
auditable regime-aware score. This module blends them and applies the three
gates that decide whether the setup deserves capital at all:

1. **agreement** - the two heads must not contradict each other
2. **score**     - the blended edge must clear ``min_score``
3. **confidence** - the winning-side probability must clear ``min_confidence``

Anything that fails a gate becomes WAIT. WAIT is a position too; most bars
should be WAIT.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import SignalConfig

BUY, SELL, WAIT = 1, -1, 0
_NAME = {BUY: "BUY", SELL: "SELL", WAIT: "WAIT"}


@dataclass
class Decision:
    """A single, human-readable trading decision."""

    direction: int
    score: float
    confidence: float
    ml_score: float
    ta_score: float
    reason: str

    @property
    def action(self) -> str:
        return _NAME[self.direction]

    def __str__(self) -> str:
        if self.direction == WAIT:
            return f"WAIT - {self.reason}"
        return (
            f"{self.action} - confidence {self.confidence:.0%} "
            f"(score {self.score:+.3f} | ml {self.ml_score:+.3f} | ta {self.ta_score:+.3f})"
        )


def fuse_signals(
    ml: pd.DataFrame,
    ta: pd.DataFrame,
    cfg: SignalConfig,
) -> pd.DataFrame:
    """Vectorised fusion over a whole dataset.

    ``ml`` must carry ``score``/``confidence`` columns, ``ta`` a ``ta_score``.
    """
    idx = ml.index
    ml_score = ml["score"].reindex(idx)
    ml_conf = ml["confidence"].reindex(idx)
    ta_score = ta["ta_score"].reindex(idx)

    total_w = cfg.ml_weight + cfg.technical_weight
    fused = (cfg.ml_weight * ml_score + cfg.technical_weight * ta_score) / total_w

    direction = np.sign(fused).astype(int)

    disagree = (np.sign(ml_score) * np.sign(ta_score)) < 0
    weak_score = fused.abs() < cfg.min_score
    weak_conf = ml_conf < cfg.min_confidence

    blocked = weak_score | weak_conf
    if cfg.require_agreement:
        blocked = blocked | disagree
    direction = np.where(blocked, WAIT, direction)

    reason = np.select(
        [
            weak_score.to_numpy(),
            weak_conf.to_numpy(),
            (disagree & cfg.require_agreement).to_numpy(),
        ],
        ["edge below threshold", "confidence below threshold", "heads disagree"],
        default="signal accepted",
    )

    out = pd.DataFrame(
        {
            "direction": direction,
            "score": fused,
            "confidence": ml_conf,
            "ml_score": ml_score,
            "ta_score": ta_score,
            "reason": reason,
        },
        index=idx,
    )
    return out


def decide(row: pd.Series) -> Decision:
    """Turn one row of :func:`fuse_signals` output into a Decision."""
    return Decision(
        direction=int(row["direction"]),
        score=float(row["score"]),
        confidence=float(row["confidence"]),
        ml_score=float(row["ml_score"]),
        ta_score=float(row["ta_score"]),
        reason=str(row["reason"]),
    )
