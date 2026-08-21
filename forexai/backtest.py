"""Event-driven bar backtester.

Timing contract, enforced by the loop order below:

    close of bar i  ->  signal computed from bar i's features
    open  of bar i+1 ->  order filled, sized by the risk manager
    bar i+1 onwards  ->  stop / target / timeout monitored

Nothing in the decision for bar ``i`` can see bar ``i+1``. The fill price is
not known when the decision is made, exactly as in live trading.

Execution realism:

* bid/ask modelled as mid +- half the spread
* entries and stop exits pay slippage; limit exits do not
* commission charged per lot per round turn
* swap charged per rollover held
* when a single bar could have hit both the stop and the target, the stop is
  assumed to have hit first
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional

import numpy as np
import pandas as pd

from .config import Config
from .risk import RiskManager, TradePlan

ROLLOVER_HOUR = 22  # UTC


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: int
    lots: float
    entry: float
    exit: float
    stop_loss: float
    take_profit: float
    pnl: float
    r_multiple: float
    bars_held: int
    exit_reason: str
    risk_amount: float
    score: float
    confidence: float
    equity_after: float


@dataclass
class OpenPosition:
    plan: TradePlan
    entry_time: pd.Timestamp
    entry_bar: int
    entry_exec: float
    stop_loss: float
    take_profit: float
    score: float
    confidence: float


class Backtester:
    """Single-position-at-a-time bar backtester driven by a signal frame."""

    def __init__(self, cfg: Config, risk_manager: Optional[RiskManager] = None):
        self.cfg = cfg
        self.rm = risk_manager or RiskManager(
            cfg.risk, cfg.instrument, cfg.costs, cfg.initial_equity
        )

    # ------------------------------------------------------------------
    def run(
        self,
        bars: pd.DataFrame,
        signals: pd.DataFrame,
        atr: pd.Series,
    ) -> "BacktestResult":
        cfg = self.cfg
        pip = cfg.instrument.pip_size
        half_spread = 0.5 * cfg.costs.spread_pips * pip
        slip = cfg.costs.slippage_pips * pip
        max_hold = cfg.labels.max_holding_bars

        index = bars.index
        open_ = bars["open"].to_numpy(float)
        high = bars["high"].to_numpy(float)
        low = bars["low"].to_numpy(float)
        close = bars["close"].to_numpy(float)
        atr_arr = atr.reindex(index).to_numpy(float)

        sig = signals.reindex(index)
        direction_arr = sig["direction"].fillna(0).to_numpy(int)
        score_arr = sig["score"].fillna(0.0).to_numpy(float)
        conf_arr = sig["confidence"].fillna(0.0).to_numpy(float)

        trades: List[Trade] = []
        equity_curve = np.empty(len(index))
        position: Optional[OpenPosition] = None
        pending: Optional[dict] = None

        for i in range(len(index)):
            ts = index[i]
            self.rm.on_new_bar(ts)

            # -- A. fill yesterday's decision at today's open ------------
            if position is None and pending is not None:
                plan = self.rm.evaluate(
                    timestamp=ts,
                    direction=pending["direction"],
                    reference_price=open_[i],
                    atr=pending["atr"],
                )
                if plan.approved:
                    d = plan.direction
                    entry_exec = open_[i] + d * (half_spread + slip)
                    position = OpenPosition(
                        plan=plan,
                        entry_time=ts,
                        entry_bar=i,
                        entry_exec=entry_exec,
                        stop_loss=entry_exec - d * cfg.risk.sl_atr_mult * pending["atr"],
                        take_profit=entry_exec + d * cfg.risk.tp_atr_mult * pending["atr"],
                        score=pending["score"],
                        confidence=pending["confidence"],
                    )
                    self.rm.register_open()
                pending = None

            # -- B. manage the open position across this bar -------------
            if position is not None:
                d = position.plan.direction
                exit_exec: Optional[float] = None
                reason = ""

                if d > 0:
                    # long: exits execute at the bid (mid - half spread)
                    stop_touch = low[i] - half_spread <= position.stop_loss
                    target_touch = high[i] - half_spread >= position.take_profit
                    if stop_touch:                       # pessimistic ordering
                        exit_exec, reason = position.stop_loss - slip, "stop"
                    elif target_touch:
                        exit_exec, reason = position.take_profit, "target"
                else:
                    # short: exits execute at the ask (mid + half spread)
                    stop_touch = high[i] + half_spread >= position.stop_loss
                    target_touch = low[i] + half_spread <= position.take_profit
                    if stop_touch:
                        exit_exec, reason = position.stop_loss + slip, "stop"
                    elif target_touch:
                        exit_exec, reason = position.take_profit, "target"

                if exit_exec is None and (i - position.entry_bar) >= max_hold:
                    exit_exec = close[i] - d * (half_spread + slip)
                    reason = "timeout"

                if exit_exec is not None:
                    trades.append(self._close(position, ts, i, exit_exec, reason))
                    position = None

            # -- C. decide at the close of this bar ----------------------
            if position is None and pending is None and i + 1 < len(index):
                d = int(direction_arr[i])
                if d != 0 and np.isfinite(atr_arr[i]) and atr_arr[i] > 0:
                    pending = {
                        "direction": d,
                        "atr": float(atr_arr[i]),
                        "score": float(score_arr[i]),
                        "confidence": float(conf_arr[i]),
                    }

            equity_curve[i] = self.rm.state.equity

        # Force-close anything still open on the last bar.
        if position is not None:
            i = len(index) - 1
            d = position.plan.direction
            exit_exec = close[i] - d * (half_spread + slip)
            trades.append(self._close(position, index[i], i, exit_exec, "end of data"))
            equity_curve[i] = self.rm.state.equity

        return BacktestResult(
            trades=pd.DataFrame([asdict(t) for t in trades]),
            equity=pd.Series(equity_curve, index=index, name="equity"),
            initial_equity=self.cfg.initial_equity,
            rejections=dict(self.rm.state.rejections),
            halted=self.rm.state.halted,
            halt_reason=self.rm.state.halt_reason,
        )

    # ------------------------------------------------------------------
    def _rollovers(self, entry: pd.Timestamp, exit_: pd.Timestamp) -> int:
        """Number of 22:00 UTC rollovers crossed while the trade was open."""
        if exit_ <= entry:
            return 0
        first = entry.normalize() + pd.Timedelta(hours=ROLLOVER_HOUR)
        if first <= entry:
            first += pd.Timedelta(days=1)
        if first > exit_:
            return 0
        return int((exit_ - first) / pd.Timedelta(days=1)) + 1

    def _close(
        self,
        position: OpenPosition,
        ts: pd.Timestamp,
        bar: int,
        exit_exec: float,
        reason: str,
    ) -> Trade:
        cfg = self.cfg
        pip = cfg.instrument.pip_size
        plan = position.plan
        d = plan.direction

        gross_pips = d * (exit_exec - position.entry_exec) / pip
        pnl = gross_pips * cfg.instrument.pip_value_per_lot * plan.lots
        pnl -= cfg.costs.commission_per_lot_roundturn * plan.lots

        nights = self._rollovers(position.entry_time, ts)
        if nights:
            swap_pips = (
                cfg.costs.swap_pips_per_night_long if d > 0
                else cfg.costs.swap_pips_per_night_short
            )
            pnl += nights * swap_pips * cfg.instrument.pip_value_per_lot * plan.lots

        self.rm.register_close(pnl)
        risk_amount = plan.risk_amount if plan.risk_amount > 0 else float("nan")

        return Trade(
            entry_time=position.entry_time,
            exit_time=ts,
            direction=d,
            lots=plan.lots,
            entry=position.entry_exec,
            exit=float(exit_exec),
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            pnl=float(pnl),
            r_multiple=float(pnl / risk_amount) if risk_amount == risk_amount else float("nan"),
            bars_held=int(bar - position.entry_bar),
            exit_reason=reason,
            risk_amount=float(plan.risk_amount),
            score=position.score,
            confidence=position.confidence,
            equity_after=float(self.rm.state.equity),
        )


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity: pd.Series
    initial_equity: float
    rejections: dict
    halted: bool = False
    halt_reason: str = ""

    def __len__(self) -> int:
        return len(self.trades)
