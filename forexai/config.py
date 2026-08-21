"""Configuration objects for the FOREX AI v2 stack.

Everything that can change the behaviour of a run lives here, so a run can be
reproduced from a single YAML file.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields, is_dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass
class InstrumentConfig:
    """Contract specification of the traded symbol."""

    symbol: str = "EURUSD"
    pip_size: float = 0.0001          # 1 pip expressed in price units
    contract_size: float = 100_000.0  # units per 1.0 lot
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 50.0
    # Quote currency == account currency is assumed (EURUSD on a USD account).
    # For other pairs, set pip_value_per_lot explicitly.
    pip_value_per_lot: float = 10.0


@dataclass
class CostConfig:
    """Execution frictions. Ignoring these is the fastest way to fake an edge."""

    spread_pips: float = 1.0            # typical retail EURUSD spread
    slippage_pips: float = 0.2          # per side
    commission_per_lot_roundturn: float = 7.0
    swap_pips_per_night_long: float = -0.3
    swap_pips_per_night_short: float = -0.1
    max_tradable_spread_pips: float = 2.5


@dataclass
class LabelConfig:
    """Triple-barrier labelling parameters."""

    tp_atr_mult: float = 3.0
    sl_atr_mult: float = 1.5
    max_holding_bars: int = 48
    atr_period: int = 14


@dataclass
class ModelConfig:
    ensemble_weights: Dict[str, float] = field(
        default_factory=lambda: {"gbm": 0.5, "forest": 0.3, "linear": 0.2}
    )
    calibration_fraction: float = 0.2   # tail of the train window kept for calibration
    min_train_samples: int = 400
    random_state: int = 7


@dataclass
class SignalConfig:
    """How the ML head and the technical head are fused into one decision."""

    ml_weight: float = 0.65
    technical_weight: float = 0.35
    min_score: float = 0.12             # |fused score| needed to act at all
    min_confidence: float = 0.40        # directional probability floor
    require_agreement: bool = True      # both heads must point the same way


@dataclass
class RiskConfig:
    risk_per_trade: float = 0.005       # 0.5% of equity, hard rule
    min_reward_risk: float = 2.0
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 3.0
    min_net_reward_risk: float = 1.5   # after spread, slippage and commission
    max_open_positions: int = 1
    max_daily_loss: float = 0.02        # 2% of start-of-day equity
    max_total_drawdown: float = 0.20    # kill switch
    max_consecutive_losses: int = 4
    cooldown_bars_after_streak: int = 12
    allowed_sessions: tuple = ("london", "newyork", "overlap")
    min_atr_pips: float = 5.0           # skip dead markets
    max_atr_pips: float = 60.0          # skip news chaos


@dataclass
class DataConfig:
    source: str = "synthetic"           # synthetic | csv | yahoo
    path: str = ""
    timeframe: str = "1h"
    bars: int = 30_000
    seed: int = 42


@dataclass
class WalkForwardConfig:
    train_bars: int = 6_000
    test_bars: int = 1_500
    step_bars: int = 1_500
    embargo_bars: int = 96              # >= max_holding_bars, kills label leakage


@dataclass
class Config:
    instrument: InstrumentConfig = field(default_factory=InstrumentConfig)
    costs: CostConfig = field(default_factory=CostConfig)
    labels: LabelConfig = field(default_factory=LabelConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    data: DataConfig = field(default_factory=DataConfig)
    walk_forward: WalkForwardConfig = field(default_factory=WalkForwardConfig)
    initial_equity: float = 10_000.0

    # ------------------------------------------------------------------
    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        raw = yaml.safe_load(Path(path).read_text()) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Config":
        cfg = cls()
        for f in fields(cls):
            if f.name not in raw:
                continue
            value = raw[f.name]
            current = getattr(cfg, f.name)
            if is_dataclass(current) and isinstance(value, dict):
                for key, val in value.items():
                    if hasattr(current, key):
                        setattr(current, key, val)
            else:
                setattr(cfg, f.name, value)
        return cfg

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def dump(self, path: str | Path) -> None:
        Path(path).write_text(yaml.safe_dump(self.to_dict(), sort_keys=False))
