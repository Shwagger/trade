"""Walk-forward validation - the only backtest that means anything.

The model is refitted on a rolling training window and then traded, once,
forward in time on data it has never seen. Between the two there is an embargo
gap at least as long as the label horizon, so a training label cannot overlap a
test bar. Equity compounds across folds: fold 3 trades the account that folds 1
and 2 left behind.

Reported side by side:

* **in-sample**     the same model traded over its own training window
* **out-of-sample** the fold's real result

A large IS/OOS gap is the signature of a memorising model, not a learning one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd

from .config import Config
from .metrics import bootstrap_expectancy, compute_metrics
from .pipeline import Dataset, fit_model, make_signals, run_backtest
from .risk import RiskManager


@dataclass
class Fold:
    index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    n_train: int
    n_test: int
    oos: Dict[str, float]
    is_: Dict[str, float]
    trades: pd.DataFrame
    equity: pd.Series
    rejections: Dict[str, int] = field(default_factory=dict)


@dataclass
class WalkForwardResult:
    folds: List[Fold]
    trades: pd.DataFrame
    equity: pd.Series
    metrics: Dict[str, float]
    bootstrap: Dict[str, float]
    fold_table: pd.DataFrame
    importance: pd.Series


def walk_forward(ds: Dataset, cfg: Config, verbose: bool = True) -> WalkForwardResult:
    wf = cfg.walk_forward
    index = ds.features.index
    n = len(index)
    embargo = max(wf.embargo_bars, cfg.labels.max_holding_bars)

    # One risk manager for the whole run: the account is continuous.
    rm = RiskManager(cfg.risk, cfg.instrument, cfg.costs, cfg.initial_equity)

    folds: List[Fold] = []
    all_trades: List[pd.DataFrame] = []
    all_equity: List[pd.Series] = []
    importances: List[pd.Series] = []

    start = 0
    fold_no = 0
    while start + wf.train_bars + embargo + wf.test_bars <= n:
        train_idx = index[start : start + wf.train_bars]
        test_lo = start + wf.train_bars + embargo
        test_idx = index[test_lo : test_lo + wf.test_bars]

        try:
            model = fit_model(ds, train_idx, cfg)
        except ValueError as exc:
            if verbose:
                print(f"  fold {fold_no}: skipped ({exc})")
            start += wf.step_bars
            fold_no += 1
            continue

        # --- out-of-sample: the real thing --------------------------------
        oos_signals = make_signals(model, ds, test_idx, cfg)
        oos_result = run_backtest(ds, oos_signals, test_idx, cfg, risk_manager=rm)
        oos_metrics = compute_metrics(
            oos_result.trades, oos_result.equity, float(oos_result.equity.iloc[0])
        )

        # --- in-sample: the same model on its own training data ------------
        is_signals = make_signals(model, ds, train_idx, cfg)
        is_rm = RiskManager(cfg.risk, cfg.instrument, cfg.costs, cfg.initial_equity)
        is_result = run_backtest(ds, is_signals, train_idx, cfg, risk_manager=is_rm)
        is_metrics = compute_metrics(is_result.trades, is_result.equity, cfg.initial_equity)

        folds.append(
            Fold(
                index=fold_no,
                train_start=train_idx[0], train_end=train_idx[-1],
                test_start=test_idx[0], test_end=test_idx[-1],
                n_train=len(train_idx), n_test=len(test_idx),
                oos=oos_metrics, is_=is_metrics,
                trades=oos_result.trades, equity=oos_result.equity,
                rejections=oos_result.rejections,
            )
        )
        if not oos_result.trades.empty:
            all_trades.append(oos_result.trades)
        all_equity.append(oos_result.equity)
        imp = model.feature_importance(top=100)
        if not imp.empty:
            importances.append(imp)

        if verbose:
            print(
                f"  fold {fold_no:>2} | test {test_idx[0].date()} -> {test_idx[-1].date()} "
                f"| trades {oos_metrics['trades']:>3} "
                f"| OOS exp {oos_metrics.get('expectancy_r', 0):+.3f} R "
                f"| IS exp {is_metrics.get('expectancy_r', 0):+.3f} R "
                f"| equity {oos_metrics['final_equity']:,.0f}"
            )
        if rm.state.halted:
            if verbose:
                print(f"  !! {rm.state.halt_reason} - walk-forward stopped")
            break

        start += wf.step_bars
        fold_no += 1

    trades = (
        pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    )
    equity = pd.concat(all_equity) if all_equity else pd.Series(dtype=float)
    equity = equity[~equity.index.duplicated(keep="last")].sort_index()

    metrics = compute_metrics(trades, equity, cfg.initial_equity) if len(equity) else {}
    boot = bootstrap_expectancy(trades) if len(trades) else {}

    rows = [
        {
            "fold": f.index,
            "test_start": f.test_start.date(),
            "test_end": f.test_end.date(),
            "trades": f.oos["trades"],
            "oos_exp_r": f.oos.get("expectancy_r", 0.0),
            "is_exp_r": f.is_.get("expectancy_r", 0.0),
            "oos_win_pct": f.oos.get("win_rate_pct", 0.0),
            "oos_pf": f.oos.get("profit_factor", 0.0),
            "oos_return_pct": f.oos.get("total_return_pct", 0.0),
            "oos_maxdd_pct": f.oos.get("max_drawdown_pct", 0.0),
        }
        for f in folds
    ]
    fold_table = pd.DataFrame(rows)

    importance = (
        pd.concat(importances, axis=1).mean(axis=1).sort_values(ascending=False)
        if importances
        else pd.Series(dtype=float)
    )
    return WalkForwardResult(
        folds=folds, trades=trades, equity=equity, metrics=metrics,
        bootstrap=boot, fold_table=fold_table, importance=importance,
    )
