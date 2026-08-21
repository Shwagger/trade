"""End-to-end: the whole stack runs, and runs the same way twice."""

import pandas as pd

from forexai.config import Config
from forexai.data.synthetic import generate_ohlcv
from forexai.metrics import compute_metrics
from forexai.pipeline import build_dataset, fit_model, make_signals, run_backtest
from forexai.report import render, verdict
from forexai.walkforward import walk_forward


def small_config():
    cfg = Config()
    cfg.data.bars = 6_000
    cfg.model.ensemble_weights = {"gbm": 0.0, "forest": 0.5, "linear": 0.5}
    cfg.walk_forward.train_bars = 2_500
    cfg.walk_forward.test_bars = 800
    cfg.walk_forward.step_bars = 800
    return cfg


def test_end_to_end_walk_forward():
    cfg = small_config()
    ds = build_dataset(generate_ohlcv(cfg.data.bars, seed=5), cfg)
    result = walk_forward(ds, cfg, verbose=False)

    assert result.folds, "no fold was produced"
    assert len(result.equity) > 0
    assert set(["trades", "expectancy_r", "max_drawdown_pct"]) <= set(result.metrics)
    label, notes = verdict(result)
    assert label in {"GO TO DEMO", "NOT YET - promising, needs more evidence", "NO-GO"}
    assert "walk-forward report" in render(result, cfg)


def test_runs_are_reproducible():
    cfg = small_config()
    bars = generate_ohlcv(cfg.data.bars, seed=5)
    a = walk_forward(build_dataset(bars, cfg), cfg, verbose=False)
    b = walk_forward(build_dataset(bars, cfg), cfg, verbose=False)
    assert a.metrics == b.metrics


def test_risk_never_exceeds_the_mandate():
    """Across a real run, no single trade may risk more than the configured %."""
    cfg = small_config()
    ds = build_dataset(generate_ohlcv(cfg.data.bars, seed=17), cfg)
    index = ds.features.index
    train, test = index[:3000], index[3200:]
    model = fit_model(ds, train, cfg)
    result = run_backtest(ds, make_signals(model, ds, test, cfg), test, cfg)

    if result.trades.empty:
        return
    equity_before = result.trades["equity_after"] - result.trades["pnl"]
    risk_fraction = result.trades["risk_amount"] / equity_before
    assert risk_fraction.max() <= cfg.risk.risk_per_trade * 1.001
    # And no trade may lose meaningfully more than its planned risk.
    assert result.trades["r_multiple"].min() >= -1.35


def test_metrics_on_an_empty_run_do_not_explode():
    cfg = Config()
    equity = pd.Series([10_000.0] * 10)
    m = compute_metrics(pd.DataFrame(), equity, 10_000.0)
    assert m["trades"] == 0 and m["total_return_pct"] == 0.0
