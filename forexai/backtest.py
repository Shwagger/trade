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


def update_stop(
    direction: int,
    entry: float,
    stop_loss: float,
    initial_risk: float,
    atr_at_entry: float,
    high: float,
    low: float,
    breakeven_at_r: float = 0.0,
    trail_atr_mult: float = 0.0,
) -> float:
    """Advance a stop after the bar has been checked for exits.

    Order matters and is deliberate: exits are resolved against the stop as it
    stood when the bar opened, and only then is the stop moved using that same
    bar's extreme. Moving it first would let a bar that spiked in our favour
    retroactively protect a trade that the same bar had already stopped out -
    a classic way to manufacture a profitable backtest.

    Stops only ever move towards the target, never away from it.
    """
    if direction > 0:
        best = high
        if breakeven_at_r > 0 and initial_risk > 0:
            if best >= entry + breakeven_at_r * initial_risk:
                stop_loss = max(stop_loss, entry)
        if trail_atr_mult > 0 and atr_at_entry > 0:
            stop_loss = max(stop_loss, best - trail_atr_mult * atr_at_entry)
    else:
        best = low
        if breakeven_at_r > 0 and initial_risk > 0:
            if best <= entry - breakeven_at_r * initial_risk:
                stop_loss = min(stop_loss, entry)
        if trail_atr_mult > 0 and atr_at_entry > 0:
            stop_loss = min(stop_loss, best + trail_atr_mult * atr_at_entry)
    return stop_loss


def resolve_exit(
    direction: int,
    stop_loss: float,
    take_profit: float,
    high: float,
    low: float,
    close: float,
    half_spread: float,
    slippage: float,
    timed_out: bool,
) -> tuple[Optional[float], str]:
    """Decide whether an open position leaves on this bar, and at what price.

    Shared by the backtester and the live monitor so the two can never drift
    apart: a rule changed here changes both, and ``test_monitor.py`` asserts
    they still agree bar for bar.

    Exits execute on the far side of the spread (bid for a long, ask for a
    short). Stops slip, limits do not. A bar that spans both barriers is
    resolved as a stop, because OHLC data cannot say which came first.
    """
    if direction > 0:
        if low - half_spread <= stop_loss:
            return stop_loss - slippage, "stop"
        if high - half_spread >= take_profit:
            return take_profit, "target"
    else:
        if high + half_spread >= stop_loss:
            return stop_loss + slippage, "stop"
        if low + half_spread <= take_profit:
            return take_profit, "target"

    if timed_out:
        return close - direction * (half_spread + slippage), "timeout"
    return None, ""


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
    initial_risk: float = 0.0
    atr_at_entry: float = 0.0


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
                        initial_risk=cfg.risk.sl_atr_mult * pending["atr"],
                        atr_at_entry=pending["atr"],
                    )
                    self.rm.register_open()
                pending = None

            # -- B. manage the open position across this bar -------------
            if position is not None:
                exit_exec, reason = resolve_exit(
                    direction=position.plan.direction,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    high=high[i], low=low[i], close=close[i],
                    half_spread=half_spread, slippage=slip,
                    timed_out=(i - position.entry_bar) >= max_hold,
                )
                if exit_exec is not None:
                    trades.append(self._close(position, ts, i, exit_exec, reason))
                    position = None
                else:
                    position.stop_loss = update_stop(
                        direction=position.plan.direction,
                        entry=position.entry_exec,
                        stop_loss=position.stop_loss,
                        initial_risk=position.initial_risk,
                        atr_at_entry=position.atr_at_entry,
                        high=high[i], low=low[i],
                        breakeven_at_r=cfg.risk.breakeven_at_r,
                        trail_atr_mult=cfg.risk.trail_atr_mult,
                    )

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
