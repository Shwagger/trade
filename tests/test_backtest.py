"""Execution mechanics: fills, exits, costs and the one-bar timing gap."""

import pandas as pd
import pytest

from forexai.backtest import Backtester
from forexai.config import Config

ATR = 0.0010
PRICE = 1.1000


def make_config(**cost_overrides):
    cfg = Config()
    cfg.costs.spread_pips = cost_overrides.get("spread_pips", 0.0)
    cfg.costs.slippage_pips = cost_overrides.get("slippage_pips", 0.0)
    cfg.costs.commission_per_lot_roundturn = cost_overrides.get("commission", 0.0)
    cfg.costs.swap_pips_per_night_long = 0.0
    cfg.costs.swap_pips_per_night_short = 0.0
    cfg.labels.max_holding_bars = 10
    cfg.risk.allowed_sessions = ("asia", "london", "overlap", "newyork", "sydney")
    return cfg


def flat_bars(n=30):
    idx = pd.date_range("2024-01-02 08:00", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {"open": PRICE, "high": PRICE, "low": PRICE, "close": PRICE, "volume": 1.0},
        index=idx,
    )


def signal_frame(bars, bar, direction):
    sig = pd.DataFrame(
        {"direction": 0, "score": 0.0, "confidence": 0.0,
         "ml_score": 0.0, "ta_score": 0.0, "reason": ""},
        index=bars.index,
    )
    sig.iloc[bar, sig.columns.get_loc("direction")] = direction
    sig.iloc[bar, sig.columns.get_loc("score")] = 0.5 * direction
    sig.iloc[bar, sig.columns.get_loc("confidence")] = 0.6
    return sig


def run(bars, cfg, bar=10, direction=1):
    atr = pd.Series(ATR, index=bars.index)
    return Backtester(cfg).run(bars, signal_frame(bars, bar, direction), atr)


def test_entry_is_the_next_bar_open_not_the_signal_bar():
    bars = flat_bars()
    bars.iloc[11, bars.columns.get_loc("open")] = 1.1005   # the fill price
    bars.iloc[13, bars.columns.get_loc("high")] = 1.1050   # far past the target
    result = run(bars, make_config())
    trade = result.trades.iloc[0]
    assert trade["entry_time"] == bars.index[11]
    assert trade["entry"] == pytest.approx(1.1005)


def test_long_target_pays_exactly_the_planned_reward():
    bars = flat_bars()
    bars.iloc[13, bars.columns.get_loc("high")] = 1.10305
    result = run(bars, make_config())
    trade = result.trades.iloc[0]
    # entry 1.1000, target 1.1030 -> 30 pips on 0.33 lots at 10 per pip per lot
    assert trade["exit_reason"] == "target"
    assert trade["lots"] == pytest.approx(0.33)
    assert trade["pnl"] == pytest.approx(30 * 10 * 0.33, abs=1e-6)
    assert trade["r_multiple"] == pytest.approx(2.0, abs=1e-6)


def test_long_stop_costs_exactly_one_r():
    bars = flat_bars()
    bars.iloc[13, bars.columns.get_loc("low")] = 1.09845
    result = run(bars, make_config())
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "stop"
    assert trade["r_multiple"] == pytest.approx(-1.0, abs=1e-6)


def test_short_target():
    bars = flat_bars()
    bars.iloc[13, bars.columns.get_loc("low")] = 1.09695
    result = run(bars, make_config(), direction=-1)
    trade = result.trades.iloc[0]
    assert trade["direction"] == -1
    assert trade["exit_reason"] == "target"
    assert trade["r_multiple"] == pytest.approx(2.0, abs=1e-6)


def test_a_bar_touching_both_barriers_is_a_stop():
    bars = flat_bars()
    row = 13
    bars.iloc[row, bars.columns.get_loc("high")] = 1.10305
    bars.iloc[row, bars.columns.get_loc("low")] = 1.09845
    result = run(bars, make_config())
    assert result.trades.iloc[0]["exit_reason"] == "stop"


def test_timeout_closes_at_the_market():
    bars = flat_bars()
    bars.iloc[21, bars.columns.get_loc("close")] = 1.1012
    result = run(bars, make_config())
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "timeout"
    assert trade["bars_held"] == 10


def test_costs_reduce_the_result():
    bars = flat_bars()
    bars.iloc[13, bars.columns.get_loc("high")] = 1.1060

    free = run(bars, make_config()).trades.iloc[0]
    charged = run(
        bars, make_config(spread_pips=1.5, slippage_pips=0.3, commission=7.0)
    ).trades.iloc[0]
    assert charged["pnl"] < free["pnl"]
    assert charged["r_multiple"] < free["r_multiple"]


def test_no_signal_means_no_trade():
    bars = flat_bars()
    result = run(bars, make_config(), direction=0)
    assert result.trades.empty
    assert result.equity.iloc[-1] == pytest.approx(Config().initial_equity)


def test_equity_curve_covers_every_bar():
    bars = flat_bars()
    bars.iloc[13, bars.columns.get_loc("high")] = 1.10305
    result = run(bars, make_config())
    assert len(result.equity) == len(bars)
    assert result.equity.iloc[-1] == pytest.approx(
        Config().initial_equity + result.trades["pnl"].sum()
    )


def test_only_one_position_at_a_time():
    bars = flat_bars(n=40)
    atr = pd.Series(ATR, index=bars.index)
    sig = signal_frame(bars, 10, 1)
    for bar in range(11, 20):                       # keep shouting BUY
        sig.iloc[bar, sig.columns.get_loc("direction")] = 1
    result = Backtester(make_config()).run(bars, sig, atr)
    overlaps = (
        result.trades["entry_time"].shift(-1) < result.trades["exit_time"]
    ).fillna(False)
    assert not overlaps.any()
