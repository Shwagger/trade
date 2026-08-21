"""The risk manager - the part that keeps the account alive.

Design rule: the signal layer may only ever *propose*. This module decides.
It can veto any trade, and it alone computes position size. Even a model that
is wrong every single time cannot blow the account up if it never risks more
than ``risk_per_trade`` and always ships a stop loss.

Vetoes, in the order they are checked:

* equity kill switch (total drawdown)
* daily loss limit
* losing-streak cooldown
* maximum concurrent positions
* trading session
* spread too wide to trade
* volatility outside the tradable band
* planned reward:risk below the mandated minimum
* cost-adjusted reward:risk below the survivable minimum
* position size rounds below the broker's minimum lot
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from .config import CostConfig, InstrumentConfig, RiskConfig
from .features import session_of


@dataclass
class TradePlan:
    """A fully specified, risk-approved order. Never created without a stop."""

    approved: bool
    reason: str
    direction: int = 0
    lots: float = 0.0
    entry: float = float("nan")
    stop_loss: float = float("nan")
    take_profit: float = float("nan")
    risk_amount: float = 0.0
    risk_pips: float = 0.0
    reward_pips: float = 0.0
    planned_rr: float = 0.0
    net_rr: float = 0.0

    def __str__(self) -> str:
        if not self.approved:
            return f"REJECTED - {self.reason}"
        side = "LONG" if self.direction > 0 else "SHORT"
        return (
            f"{side} {self.lots:.2f} lots @ {self.entry:.5f} | "
            f"SL {self.stop_loss:.5f} ({self.risk_pips:.1f}p) | "
            f"TP {self.take_profit:.5f} ({self.reward_pips:.1f}p) | "
            f"risk {self.risk_amount:.2f} | RR {self.planned_rr:.2f} (net {self.net_rr:.2f})"
        )


@dataclass
class RiskState:
    equity: float
    peak_equity: float
    day_start_equity: float
    current_day: Optional[date] = None
    consecutive_losses: int = 0
    cooldown_left: int = 0
    open_positions: int = 0
    halted: bool = False
    halt_reason: str = ""
    daily_blocked: bool = False
    rejections: dict = field(default_factory=dict)


class RiskManager:
    """Stateful gatekeeper. One instance per account, per backtest run."""

    def __init__(
        self,
        cfg: RiskConfig,
        instrument: InstrumentConfig,
        costs: CostConfig,
        initial_equity: float = 10_000.0,
        min_net_reward_risk: float | None = None,
    ):
        self.cfg = cfg
        self.instrument = instrument
        self.costs = costs
        self.min_net_reward_risk = (
            getattr(cfg, "min_net_reward_risk", 1.5)
            if min_net_reward_risk is None
            else min_net_reward_risk
        )
        self.state = RiskState(
            equity=initial_equity,
            peak_equity=initial_equity,
            day_start_equity=initial_equity,
        )

    # -- bookkeeping ----------------------------------------------------
    def _reject(self, reason: str) -> TradePlan:
        self.state.rejections[reason] = self.state.rejections.get(reason, 0) + 1
        return TradePlan(approved=False, reason=reason)

    def on_new_bar(self, timestamp: pd.Timestamp) -> None:
        """Roll daily counters and burn down any cooldown. Call once per bar."""
        day = timestamp.date()
        if self.state.current_day != day:
            self.state.current_day = day
            self.state.day_start_equity = self.state.equity
            self.state.daily_blocked = False
        if self.state.cooldown_left > 0:
            self.state.cooldown_left -= 1

    def register_open(self) -> None:
        self.state.open_positions += 1

    def register_close(self, pnl: float) -> None:
        st = self.state
        st.open_positions = max(0, st.open_positions - 1)
        st.equity += pnl
        st.peak_equity = max(st.peak_equity, st.equity)

        if pnl < 0:
            st.consecutive_losses += 1
            if st.consecutive_losses >= self.cfg.max_consecutive_losses:
                st.cooldown_left = self.cfg.cooldown_bars_after_streak
                st.consecutive_losses = 0
        else:
            st.consecutive_losses = 0

        drawdown = 1.0 - st.equity / st.peak_equity if st.peak_equity > 0 else 1.0
        if drawdown >= self.cfg.max_total_drawdown:
            st.halted = True
            st.halt_reason = f"kill switch: drawdown {drawdown:.1%}"

    @property
    def daily_loss(self) -> float:
        start = self.state.day_start_equity
        if start <= 0:
            return 1.0
        return max(0.0, 1.0 - self.state.equity / start)

    # -- the gate --------------------------------------------------------
    def evaluate(
        self,
        timestamp: pd.Timestamp,
        direction: int,
        reference_price: float,
        atr: float,
        spread_pips: Optional[float] = None,
    ) -> TradePlan:
        cfg, inst, costs = self.cfg, self.instrument, self.costs
        pip = inst.pip_size
        spread_pips = costs.spread_pips if spread_pips is None else float(spread_pips)

        if direction == 0:
            return self._reject("no signal")
        if self.state.halted:
            return self._reject(self.state.halt_reason or "trading halted")
        if self.daily_loss >= cfg.max_daily_loss:
            self.state.daily_blocked = True
            return self._reject("daily loss limit reached")
        if self.state.cooldown_left > 0:
            return self._reject("cooldown after losing streak")
        if self.state.open_positions >= cfg.max_open_positions:
            return self._reject("max open positions")

        session = session_of(int(pd.Timestamp(timestamp).hour))
        if cfg.allowed_sessions and session not in tuple(cfg.allowed_sessions):
            return self._reject(f"session filter ({session})")

        if spread_pips > costs.max_tradable_spread_pips:
            return self._reject("spread too wide")

        if not np.isfinite(atr) or atr <= 0:
            return self._reject("no volatility estimate")
        atr_pips = atr / pip
        if atr_pips < cfg.min_atr_pips:
            return self._reject("volatility too low")
        if atr_pips > cfg.max_atr_pips:
            return self._reject("volatility too high")

        # --- geometry ----------------------------------------------------
        sl_dist = cfg.sl_atr_mult * atr
        tp_dist = cfg.tp_atr_mult * atr
        planned_rr = tp_dist / sl_dist if sl_dist > 0 else 0.0
        if planned_rr < cfg.min_reward_risk:
            return self._reject("planned reward:risk below minimum")

        # Costs paid on the round trip, expressed as price distance.
        friction = spread_pips * pip + 2.0 * costs.slippage_pips * pip
        net_risk_dist = sl_dist + friction
        net_reward_dist = tp_dist - friction
        if net_reward_dist <= 0:
            return self._reject("costs exceed the target")

        # --- sizing: risk_per_trade of equity, commission included --------
        risk_budget = self.state.equity * cfg.risk_per_trade
        risk_pips = net_risk_dist / pip
        reward_pips = net_reward_dist / pip
        loss_per_lot = risk_pips * inst.pip_value_per_lot + costs.commission_per_lot_roundturn
        if loss_per_lot <= 0:
            return self._reject("degenerate risk per lot")

        lots = risk_budget / loss_per_lot
        lots = np.floor(lots / inst.lot_step) * inst.lot_step
        lots = float(min(lots, inst.max_lot))
        if lots < inst.min_lot:
            return self._reject("size below minimum lot")

        gain_per_lot = reward_pips * inst.pip_value_per_lot - costs.commission_per_lot_roundturn
        net_rr = (gain_per_lot * lots) / (loss_per_lot * lots)
        if net_rr < self.min_net_reward_risk:
            return self._reject("cost-adjusted reward:risk too low")

        entry = reference_price
        stop_loss = entry - direction * sl_dist
        take_profit = entry + direction * tp_dist

        return TradePlan(
            approved=True,
            reason="approved",
            direction=int(direction),
            lots=round(lots, 2),
            entry=float(entry),
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
            risk_amount=float(loss_per_lot * lots),
            risk_pips=float(risk_pips),
            reward_pips=float(reward_pips),
            planned_rr=float(planned_rr),
            net_rr=float(net_rr),
        )
