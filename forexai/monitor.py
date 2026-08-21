"""Market surveillance: watch bars close, decide, journal, learn.

This is the bridge between research and reality, and it is deliberately a
**paper** bridge: the monitor never sends an order. It watches the market bar
by bar, runs exactly the same decision path as the backtest, records what it
*would* have done, and then scores itself against what the backtest promised.

Why that matters more than an execution API: the number that tells you whether
a system is real is the gap between backtested expectancy and forward
expectancy on bars the model has never seen. The monitor measures that gap,
continuously, for free, with no capital at risk. Wiring a broker in before that
gap is known is how accounts die.

What it does on every closed bar
--------------------------------
1. fills any order pending from the previous bar, at that bar's open
2. checks the open paper position against the bar's range - same exit rules as
   the backtester, imported from it rather than reimplemented
3. asks the model for a decision on the freshly closed bar
4. puts the approved trade in the pending slot, to be filled at the next open
5. appends every event to a JSONL journal and updates a resumable state file
6. re-fits the model every ``retrain_every`` bars, so it keeps learning
7. raises a drift alert when forward results fall out of the backtest's
   confidence interval
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .backtest import ROLLOVER_HOUR, resolve_exit, update_stop
from .config import Config
from .notify import (
    Notifier,
    format_close,
    format_drift,
    format_halt,
    format_trade_alert,
)
from .pipeline import build_dataset, fit_model, make_signals
from .risk import RiskManager
from .signal import decide


# ----------------------------------------------------------------------
@dataclass
class PaperPosition:
    direction: int
    lots: float
    entry: float
    stop_loss: float
    take_profit: float
    entry_time: str
    risk_amount: float
    bars_held: int = 0
    score: float = 0.0
    confidence: float = 0.0
    initial_risk: float = 0.0
    atr_at_entry: float = 0.0


@dataclass
class PendingOrder:
    direction: int
    atr: float
    score: float
    confidence: float
    decided_at: str


@dataclass
class MonitorState:
    """Everything needed to resume after a restart, kill or crash."""

    symbol: str = "EURUSD"
    equity: float = 10_000.0
    peak_equity: float = 10_000.0
    last_bar: Optional[str] = None
    last_trained_bar: Optional[str] = None
    bars_since_train: int = 0
    position: Optional[dict] = None
    pending: Optional[dict] = None
    # Risk-engine state survives restarts: a cooldown or a daily loss limit
    # that resets every time the process is relaunched protects nothing.
    risk: dict = field(default_factory=dict)
    closed_trades: List[dict] = field(default_factory=list)
    started_at: str = ""

    @classmethod
    def load(cls, path: Path) -> "MonitorState":
        if path.exists():
            return cls(**json.loads(path.read_text()))
        return cls(started_at=datetime.now(timezone.utc).isoformat())

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, default=str))

    # -- forward performance -------------------------------------------
    def forward_metrics(self) -> Dict[str, float]:
        if not self.closed_trades:
            return {"trades": 0, "expectancy_r": 0.0, "win_rate_pct": 0.0, "pnl": 0.0}
        frame = pd.DataFrame(self.closed_trades)
        r = frame["r_multiple"].astype(float)
        return {
            "trades": len(frame),
            "expectancy_r": round(float(r.mean()), 4),
            "win_rate_pct": round(100.0 * float((frame["pnl"] > 0).mean()), 2),
            "pnl": round(float(frame["pnl"].sum()), 2),
        }


# ----------------------------------------------------------------------
class Journal:
    """Append-only event log. One JSON object per line, greppable, diffable."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, kind: str, **payload) -> dict:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            **payload,
        }
        with self.path.open("a") as handle:
            handle.write(json.dumps(event, default=str) + "\n")
        return event

    def read(self) -> pd.DataFrame:
        if not self.path.exists():
            return pd.DataFrame()
        rows = [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
        return pd.DataFrame(rows)


# ----------------------------------------------------------------------
class Monitor:
    """Stateful, resumable market watcher."""

    def __init__(
        self,
        cfg: Config,
        model,
        workdir: str | Path = "runs/monitor",
        retrain_every: int = 500,
        backtest_expectancy: Optional[Dict[str, float]] = None,
        notifier: Optional[Notifier] = None,
    ):
        self.cfg = cfg
        self.model = model
        self.notifier = notifier
        self.dir = Path(workdir) / cfg.instrument.symbol
        self.state_path = self.dir / "state.json"
        self.journal = Journal(self.dir / "journal.jsonl")
        self.retrain_every = retrain_every
        self.backtest_expectancy = backtest_expectancy or {}

        self._halt_announced = False
        self.state = MonitorState.load(self.state_path)
        self.state.symbol = cfg.instrument.symbol
        if not self.state.started_at:
            self.state.started_at = datetime.now(timezone.utc).isoformat()
            self.state.equity = cfg.initial_equity
            self.state.peak_equity = cfg.initial_equity

    # ------------------------------------------------------------------
    @property
    def _half_spread(self) -> float:
        return 0.5 * self.cfg.costs.spread_pips * self.cfg.instrument.pip_size

    @property
    def _slip(self) -> float:
        return self.cfg.costs.slippage_pips * self.cfg.instrument.pip_size

    def _rollovers(self, entry: pd.Timestamp, exit_: pd.Timestamp) -> int:
        if exit_ <= entry:
            return 0
        first = entry.normalize() + pd.Timedelta(hours=ROLLOVER_HOUR)
        if first <= entry:
            first += pd.Timedelta(days=1)
        if first > exit_:
            return 0
        return int((exit_ - first) / pd.Timedelta(days=1)) + 1

    # ------------------------------------------------------------------
    def _notify(self, text: str) -> None:
        """Deliver an alert. Never let a messaging failure stop the watch."""
        if self.notifier is None or not getattr(self.notifier, "enabled", False):
            return
        try:
            self.notifier.send(text)
        except Exception:                                # noqa: BLE001 - see docstring
            self.journal.write("notify_failed", detail="alert could not be delivered")

    def _risk_manager(self) -> RiskManager:
        """Rehydrate the risk engine from disk, so its memory is not lost."""
        rm = RiskManager(
            self.cfg.risk, self.cfg.instrument, self.cfg.costs, self.state.equity
        )
        saved = self.state.risk or {}
        rm.state.equity = self.state.equity
        rm.state.peak_equity = self.state.peak_equity
        rm.state.day_start_equity = saved.get("day_start_equity", self.state.equity)
        rm.state.current_day = (
            date.fromisoformat(saved["current_day"]) if saved.get("current_day") else None
        )
        rm.state.consecutive_losses = int(saved.get("consecutive_losses", 0))
        rm.state.cooldown_left = int(saved.get("cooldown_left", 0))
        rm.state.halted = bool(saved.get("halted", False))
        rm.state.halt_reason = saved.get("halt_reason", "")
        rm.state.open_positions = 1 if self.state.position else 0
        return rm

    def _store_risk(self, rm: RiskManager) -> None:
        self.state.equity = rm.state.equity
        self.state.peak_equity = rm.state.peak_equity
        self.state.risk = {
            "day_start_equity": rm.state.day_start_equity,
            "current_day": str(rm.state.current_day) if rm.state.current_day else None,
            "consecutive_losses": rm.state.consecutive_losses,
            "cooldown_left": rm.state.cooldown_left,
            "halted": rm.state.halted,
            "halt_reason": rm.state.halt_reason,
        }

    def step(self, bars: pd.DataFrame) -> List[dict]:
        """Process every bar that closed since the last run. Idempotent."""
        cfg = self.cfg
        events: List[dict] = []

        ds = build_dataset(bars, cfg)
        usable = ds.predictable()
        if len(usable) == 0:
            return [self.journal.write("warmup", detail="not enough history yet")]

        last_seen = pd.Timestamp(self.state.last_bar) if self.state.last_bar else None
        new_bars = usable if last_seen is None else usable[usable > last_seen]
        if len(new_bars) == 0:
            return []

        # On a cold start, do not replay years of history as live trades.
        if last_seen is None:
            new_bars = new_bars[-1:]
            events.append(
                self.journal.write(
                    "start",
                    bar=str(new_bars[0]),
                    equity=self.state.equity,
                    detail="cold start: watching from the most recent closed bar",
                )
            )

        # Signals for every new bar are computed in one batch. Per-bar model
        # calls cost milliseconds each, which is invisible when one bar closes
        # per hour and unbearable when catching up on a week of downtime.
        signals = make_signals(self.model, ds, pd.Index(new_bars), self.cfg)

        rm = self._risk_manager()
        for timestamp in new_bars:
            events.extend(self._process_bar(ds, timestamp, rm, signals))
            self._store_risk(rm)
            self.state.last_bar = str(timestamp)
            self.state.bars_since_train += 1

        if self.retrain_every and self.state.bars_since_train >= self.retrain_every:
            events.append(self._retrain(ds))

        drift = self._check_drift()
        if drift:
            events.append(drift)

        self.state.save(self.state_path)
        return events

    # ------------------------------------------------------------------
    def _process_bar(
        self,
        ds,
        timestamp: pd.Timestamp,
        rm: RiskManager,
        signals: pd.DataFrame,
    ) -> List[dict]:
        cfg = self.cfg
        events: List[dict] = []
        bar = ds.bars.loc[timestamp]
        rm.on_new_bar(timestamp)

        # -- 1. fill the order decided on the previous bar ---------------
        if self.state.position is None and self.state.pending is not None:
            pending = PendingOrder(**self.state.pending)
            plan = rm.evaluate(
                timestamp=timestamp,
                direction=pending.direction,
                reference_price=float(bar["open"]),
                atr=pending.atr,
            )
            if plan.approved:
                d = plan.direction
                entry = float(bar["open"]) + d * (self._half_spread + self._slip)
                self.state.position = asdict(
                    PaperPosition(
                        direction=d, lots=plan.lots, entry=entry,
                        stop_loss=entry - d * cfg.risk.sl_atr_mult * pending.atr,
                        take_profit=entry + d * cfg.risk.tp_atr_mult * pending.atr,
                        entry_time=str(timestamp), risk_amount=plan.risk_amount,
                        score=pending.score, confidence=pending.confidence,
                        initial_risk=cfg.risk.sl_atr_mult * pending.atr,
                        atr_at_entry=pending.atr,
                    )
                )
                rm.register_open()
                events.append(
                    self.journal.write(
                        "fill", bar=str(timestamp), direction=d, lots=plan.lots,
                        entry=round(entry, 5),
                        stop_loss=round(self.state.position["stop_loss"], 5),
                        take_profit=round(self.state.position["take_profit"], 5),
                        risk=round(plan.risk_amount, 2),
                    )
                )
            else:
                events.append(
                    self.journal.write("cancelled", bar=str(timestamp), reason=plan.reason)
                )
            self.state.pending = None

        # -- 2. manage the open position against this bar ----------------
        if self.state.position is not None:
            position = PaperPosition(**self.state.position)
            # bars_held counts bars *elapsed since entry*, so it is still 0 on
            # the entry bar itself - matching the backtester's ``i - entry_bar``.
            # Incrementing before the check would time every trade out one bar
            # early and quietly change every exit price.
            exit_exec, reason = resolve_exit(
                direction=position.direction,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                high=float(bar["high"]), low=float(bar["low"]), close=float(bar["close"]),
                half_spread=self._half_spread, slippage=self._slip,
                timed_out=position.bars_held >= cfg.labels.max_holding_bars,
            )
            if exit_exec is None:
                position.stop_loss = update_stop(
                    direction=position.direction,
                    entry=position.entry,
                    stop_loss=position.stop_loss,
                    initial_risk=position.initial_risk,
                    atr_at_entry=position.atr_at_entry,
                    high=float(bar["high"]), low=float(bar["low"]),
                    breakeven_at_r=cfg.risk.breakeven_at_r,
                    trail_atr_mult=cfg.risk.trail_atr_mult,
                )
                position.bars_held += 1
                self.state.position = asdict(position)
            else:
                events.append(self._close(position, timestamp, exit_exec, reason, rm))

        # -- 3. decide on the freshly closed bar -------------------------
        if self.state.position is None and self.state.pending is None:
            if timestamp in signals.index:
                decision = decide(signals.loc[timestamp])
                atr = float(ds.features.loc[timestamp, "atr"])
                if decision.direction != 0 and np.isfinite(atr) and atr > 0:
                    self.state.pending = asdict(
                        PendingOrder(
                            direction=decision.direction, atr=atr,
                            score=decision.score, confidence=decision.confidence,
                            decided_at=str(timestamp),
                        )
                    )
                    # Size the order against the bar that just closed so the
                    # alert is actionable *now*. The monitor's own paper fill
                    # still happens at the next open, like the backtest.
                    preview_rm = self._risk_manager()
                    preview_rm.on_new_bar(timestamp)
                    preview = preview_rm.evaluate(
                        timestamp=timestamp,
                        direction=decision.direction,
                        reference_price=float(bar["close"]),
                        atr=atr,
                    )
                    events.append(
                        self.journal.write(
                            "signal", bar=str(timestamp), action=decision.action,
                            confidence=round(decision.confidence, 4),
                            lift=round(decision.lift, 3),
                            score=round(decision.score, 4),
                            approved=preview.approved,
                            lots=preview.lots,
                            entry=round(preview.entry, 5) if preview.approved else None,
                            stop_loss=round(preview.stop_loss, 5) if preview.approved else None,
                            take_profit=(
                                round(preview.take_profit, 5) if preview.approved else None
                            ),
                            detail="will fill at the next bar open",
                        )
                    )
                    if preview.approved:
                        self._notify(
                            format_trade_alert(
                                symbol=cfg.instrument.symbol,
                                timeframe=cfg.data.timeframe,
                                bar_time=timestamp,
                                decision=decision,
                                plan=preview,
                                equity=self.state.equity,
                            )
                        )

        if rm.state.halted and not self._halt_announced:
            self._halt_announced = True
            self._notify(format_halt(cfg.instrument.symbol, rm.state.halt_reason))
        return events

    # ------------------------------------------------------------------
    def _close(
        self,
        position: PaperPosition,
        timestamp,
        exit_exec: float,
        reason: str,
        rm: RiskManager,
    ) -> dict:
        cfg = self.cfg
        pip = cfg.instrument.pip_size
        d = position.direction

        gross_pips = d * (exit_exec - position.entry) / pip
        pnl = gross_pips * cfg.instrument.pip_value_per_lot * position.lots
        pnl -= cfg.costs.commission_per_lot_roundturn * position.lots

        nights = self._rollovers(pd.Timestamp(position.entry_time), pd.Timestamp(timestamp))
        if nights:
            swap = (
                cfg.costs.swap_pips_per_night_long if d > 0
                else cfg.costs.swap_pips_per_night_short
            )
            pnl += nights * swap * cfg.instrument.pip_value_per_lot * position.lots

        # The risk engine owns the equity: it also updates the losing streak,
        # the cooldown and the drawdown kill switch from this result.
        rm.register_close(pnl)
        self.state.equity = rm.state.equity
        self.state.peak_equity = rm.state.peak_equity
        r_multiple = pnl / position.risk_amount if position.risk_amount else float("nan")

        trade = {
            "entry_time": position.entry_time, "exit_time": str(timestamp),
            "direction": d, "lots": position.lots,
            "entry": round(position.entry, 5), "exit": round(float(exit_exec), 5),
            "pnl": round(pnl, 2), "r_multiple": round(r_multiple, 4),
            "exit_reason": reason, "bars_held": position.bars_held,
            "equity_after": round(self.state.equity, 2),
        }
        self.state.closed_trades.append(trade)
        self.state.position = None
        self._notify(format_close(cfg.instrument.symbol, trade))
        return self.journal.write("close", **trade)

    # ------------------------------------------------------------------
    def _retrain(self, ds) -> dict:
        """Refit on everything known so far - the learning part of the loop."""
        try:
            self.model = fit_model(ds, ds.trainable(), self.cfg)
            self.state.bars_since_train = 0
            self.state.last_trained_bar = self.state.last_bar
            return self.journal.write(
                "retrain",
                bar=self.state.last_bar,
                rows=len(ds.trainable()),
                priors=self.model.report.priors if self.model.report else {},
            )
        except ValueError as exc:
            return self.journal.write("retrain_failed", reason=str(exc))

    # ------------------------------------------------------------------
    def _check_drift(self) -> Optional[dict]:
        """Compare forward expectancy with what the backtest promised."""
        forward = self.state.forward_metrics()
        if forward["trades"] < 20 or not self.backtest_expectancy:
            return None

        floor = self.backtest_expectancy.get("ci_low")
        if floor is None:
            return None
        if forward["expectancy_r"] < floor:
            self._notify(
                format_drift(
                    self.cfg.instrument.symbol,
                    {
                        "forward_expectancy_r": forward["expectancy_r"],
                        "backtest_ci_low": floor,
                        "trades": forward["trades"],
                    },
                )
            )
            return self.journal.write(
                "drift_alert",
                forward_expectancy_r=forward["expectancy_r"],
                backtest_ci_low=floor,
                trades=forward["trades"],
                detail=(
                    "forward results are below the backtest confidence interval. "
                    "Stop adding risk and re-run the walk-forward on fresh data."
                ),
            )
        return None

    # ------------------------------------------------------------------
    def summary(self) -> str:
        forward = self.state.forward_metrics()
        drawdown = (
            1.0 - self.state.equity / self.state.peak_equity
            if self.state.peak_equity else 0.0
        )
        lines = [
            f"  watching            {self.state.symbol}",
            f"  last closed bar     {self.state.last_bar}",
            f"  paper equity        {self.state.equity:,.2f} "
            f"(peak {self.state.peak_equity:,.2f}, drawdown {drawdown:.2%})",
            f"  forward trades      {forward['trades']}",
            f"  forward expectancy  {forward['expectancy_r']:+.4f} R  "
            f"(win rate {forward['win_rate_pct']:.1f}%)",
        ]
        if self.backtest_expectancy:
            lines.append(
                f"  backtest said       {self.backtest_expectancy.get('mean_r', 0.0):+.4f} R  "
                f"CI [{self.backtest_expectancy.get('ci_low', float('nan')):+.4f}, "
                f"{self.backtest_expectancy.get('ci_high', float('nan')):+.4f}]"
            )
        if self.state.risk.get("halted"):
            lines.append(f"  HALTED              {self.state.risk.get('halt_reason', '')}")
        elif self.state.risk.get("cooldown_left"):
            lines.append(
                f"  cooldown            {self.state.risk['cooldown_left']} bars left"
            )
        if self.state.position:
            p = self.state.position
            lines.append(
                f"  open paper position {'LONG' if p['direction'] > 0 else 'SHORT'} "
                f"{p['lots']:.2f} @ {p['entry']:.5f} "
                f"(SL {p['stop_loss']:.5f} / TP {p['take_profit']:.5f})"
            )
        if self.state.pending:
            lines.append(f"  pending order       {self.state.pending['direction']:+d} "
                         f"decided {self.state.pending['decided_at']}")
        lines.append("  NOTE: paper only. This process never sends an order.")
        return "\n".join(lines)
