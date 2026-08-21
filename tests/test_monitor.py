"""The monitor must be the backtester, running forward one bar at a time.

If these two ever disagree, every backtest number becomes a fiction: the
research says one thing and the thing watching the market does another.
"""

import json

import pandas as pd
import pytest

from forexai.config import Config
from forexai.data.synthetic import generate_ohlcv
from forexai.monitor import Monitor, MonitorState
from forexai.pipeline import build_dataset, fit_model, make_signals, run_backtest


def small_config():
    cfg = Config()
    cfg.data.bars = 9_000
    cfg.model.ensemble_weights = {"gbm": 0.0, "forest": 1.0, "linear": 0.0}
    return cfg


@pytest.fixture(scope="module")
def fitted():
    cfg = small_config()
    bars = generate_ohlcv(cfg.data.bars, seed=31)
    ds = build_dataset(bars, cfg)
    index = ds.predictable()
    train, test = index[:5_000], index[5_200:6_400]
    model = fit_model(ds, train, cfg)
    return cfg, bars, ds, model, test


def test_monitor_replay_matches_the_backtester(fitted, tmp_path):
    cfg, bars, ds, model, test = fitted

    expected = run_backtest(ds, make_signals(model, ds, test, cfg), test, cfg)

    monitor = Monitor(cfg, model, workdir=tmp_path, retrain_every=0)
    monitor.state.last_bar = str(ds.predictable()[ds.predictable() < test[0]][-1])
    # Feed history up to the end of the test window only: the monitor consumes
    # every bar it is given, so a longer frame would compare two spans.
    monitor.step(bars.loc[: test[-1]])

    live = pd.DataFrame(monitor.state.closed_trades)
    # The backtester force-closes whatever is open on its final bar; the live
    # monitor rightly leaves it open, so that trade is excluded from the
    # comparison rather than papered over.
    reference = expected.trades[expected.trades["exit_reason"] != "end of data"]
    if reference.empty:
        assert live.empty
        return

    assert len(live) == len(reference), "trade counts diverged"
    for column in ("direction", "lots", "exit_reason"):
        assert list(live[column]) == list(reference[column])
    for column in ("entry", "exit", "pnl", "bars_held"):
        assert live[column].to_numpy() == pytest.approx(
            reference[column].to_numpy(), abs=0.01
        ), f"{column} diverged between the monitor and the backtester"
    assert monitor.state.equity == pytest.approx(
        cfg.initial_equity + float(reference["pnl"].sum()), abs=0.01
    )


def test_monitor_never_replays_history_on_a_cold_start(fitted, tmp_path):
    cfg, bars, _, model, _ = fitted
    monitor = Monitor(cfg, model, workdir=tmp_path, retrain_every=0)
    monitor.step(bars)
    assert monitor.state.closed_trades == []
    assert monitor.state.equity == pytest.approx(cfg.initial_equity)


def test_monitor_is_idempotent_on_the_same_bars(fitted, tmp_path):
    cfg, bars, ds, model, test = fitted
    monitor = Monitor(cfg, model, workdir=tmp_path, retrain_every=0)
    monitor.state.last_bar = str(ds.predictable()[ds.predictable() < test[0]][-1])
    # Feed history up to the end of the test window only: the monitor consumes
    # every bar it is given, so a longer frame would compare two spans.
    monitor.step(bars.loc[: test[-1]])
    equity_after_first = monitor.state.equity
    trades = len(monitor.state.closed_trades)

    assert monitor.step(bars.loc[: test[-1]]) == []          # nothing new closed
    assert monitor.state.equity == equity_after_first
    assert len(monitor.state.closed_trades) == trades


def test_state_survives_a_restart(fitted, tmp_path):
    cfg, bars, ds, model, test = fitted
    monitor = Monitor(cfg, model, workdir=tmp_path, retrain_every=0)
    monitor.state.last_bar = str(ds.predictable()[ds.predictable() < test[0]][-1])
    # Feed history up to the end of the test window only: the monitor consumes
    # every bar it is given, so a longer frame would compare two spans.
    monitor.step(bars.loc[: test[-1]])

    revived = Monitor(cfg, model, workdir=tmp_path, retrain_every=0)
    assert revived.state.last_bar == monitor.state.last_bar
    assert revived.state.equity == pytest.approx(monitor.state.equity)
    assert len(revived.state.closed_trades) == len(monitor.state.closed_trades)
    assert revived.state.risk == monitor.state.risk


def test_journal_is_readable_jsonl(fitted, tmp_path):
    cfg, bars, ds, model, test = fitted
    monitor = Monitor(cfg, model, workdir=tmp_path, retrain_every=0)
    monitor.state.last_bar = str(ds.predictable()[ds.predictable() < test[0]][-1])
    # Feed history up to the end of the test window only: the monitor consumes
    # every bar it is given, so a longer frame would compare two spans.
    monitor.step(bars.loc[: test[-1]])

    lines = (tmp_path / cfg.instrument.symbol / "journal.jsonl").read_text().splitlines()
    assert lines
    for line in lines:
        event = json.loads(line)
        assert "ts" in event and "kind" in event


def test_drift_alert_fires_when_forward_results_undershoot(fitted, tmp_path):
    cfg, _, _, model, _ = fitted
    monitor = Monitor(
        cfg, model, workdir=tmp_path, retrain_every=0,
        backtest_expectancy={"mean_r": 0.15, "ci_low": 0.05, "ci_high": 0.25},
    )
    monitor.state.closed_trades = [
        {"pnl": -50.0, "r_multiple": -1.0} for _ in range(25)
    ]
    alert = monitor._check_drift()
    assert alert is not None and alert["kind"] == "drift_alert"


def test_no_drift_alert_before_enough_trades(fitted, tmp_path):
    cfg, _, _, model, _ = fitted
    monitor = Monitor(
        cfg, model, workdir=tmp_path, retrain_every=0,
        backtest_expectancy={"mean_r": 0.15, "ci_low": 0.05},
    )
    monitor.state.closed_trades = [{"pnl": -50.0, "r_multiple": -1.0} for _ in range(5)]
    assert monitor._check_drift() is None


def test_risk_state_is_persisted_not_reset_each_bar(fitted, tmp_path):
    """A cooldown that forgets itself on restart protects nothing."""
    cfg, _, _, model, _ = fitted
    monitor = Monitor(cfg, model, workdir=tmp_path, retrain_every=0)
    monitor.state.risk = {
        "day_start_equity": 10_000.0, "current_day": "2024-05-02",
        "consecutive_losses": 2, "cooldown_left": 7,
        "halted": False, "halt_reason": "",
    }
    rm = monitor._risk_manager()
    assert rm.state.cooldown_left == 7
    assert rm.state.consecutive_losses == 2
    assert rm.state.current_day == pd.Timestamp("2024-05-02").date()


def test_monitor_state_roundtrips_through_disk(tmp_path):
    path = tmp_path / "state.json"
    state = MonitorState(symbol="GBPUSD", equity=10_123.45, last_bar="2024-05-02 13:00:00+00:00")
    state.save(path)
    assert MonitorState.load(path) == state
