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


# ----------------------------------------------------------------------
# stop management
# ----------------------------------------------------------------------
from forexai.backtest import update_stop  # noqa: E402


def test_stops_never_move_away_from_the_target():
    for direction in (1, -1):
        moved = update_stop(
            direction=direction, entry=1.1000,
            stop_loss=1.1000 - direction * 0.0015,
            initial_risk=0.0015, atr_at_entry=0.0010,
            high=1.0990, low=1.0990,          # price went against us
            breakeven_at_r=1.0, trail_atr_mult=1.0,
        )
        original = 1.1000 - direction * 0.0015
        assert (moved >= original) if direction > 0 else (moved <= original)


def test_breakeven_moves_the_stop_to_entry_after_one_r():
    stop = update_stop(
        direction=1, entry=1.1000, stop_loss=1.0985,
        initial_risk=0.0015, atr_at_entry=0.0010,
        high=1.1016, low=1.1000,              # +1.07R excursion
        breakeven_at_r=1.0,
    )
    assert stop == pytest.approx(1.1000)


def test_breakeven_does_not_trigger_early():
    stop = update_stop(
        direction=1, entry=1.1000, stop_loss=1.0985,
        initial_risk=0.0015, atr_at_entry=0.0010,
        high=1.1010, low=1.1000,              # only +0.67R
        breakeven_at_r=1.0,
    )
    assert stop == pytest.approx(1.0985)


def test_trailing_stop_follows_the_best_price():
    stop = update_stop(
        direction=1, entry=1.1000, stop_loss=1.0985,
        initial_risk=0.0015, atr_at_entry=0.0010,
        high=1.1040, low=1.1000, trail_atr_mult=1.5,
    )
    assert stop == pytest.approx(1.1040 - 1.5 * 0.0010)


def test_trailing_stop_is_mirrored_for_shorts():
    stop = update_stop(
        direction=-1, entry=1.1000, stop_loss=1.1015,
        initial_risk=0.0015, atr_at_entry=0.0010,
        high=1.1000, low=1.0960, trail_atr_mult=1.5,
    )
    assert stop == pytest.approx(1.0960 + 1.5 * 0.0010)


def test_breakeven_turns_a_loss_into_a_scratch():
    """The whole point: give back the excursion, not the risk."""
    bars = flat_bars(n=40)
    bars.iloc[13, bars.columns.get_loc("high")] = 1.1020    # +1.3R excursion
    bars.iloc[16, bars.columns.get_loc("low")] = 1.0980     # would have been -1R

    plain = run(bars, make_config()).trades.iloc[0]
    cfg = make_config()
    cfg.risk.breakeven_at_r = 1.0
    protected = run(bars, cfg).trades.iloc[0]

    assert plain["r_multiple"] == pytest.approx(-1.0, abs=1e-6)
    assert protected["r_multiple"] == pytest.approx(0.0, abs=1e-6)


def test_a_bar_that_stops_us_out_cannot_be_saved_by_its_own_spike():
    """Intrabar order is unknowable, so the favourable extreme must not
    retroactively protect a trade the same bar already stopped."""
    bars = flat_bars(n=40)
    row = 13
    bars.iloc[row, bars.columns.get_loc("high")] = 1.1030    # big spike up
    bars.iloc[row, bars.columns.get_loc("low")] = 1.0980     # and a stop-out
    cfg = make_config()
    cfg.risk.breakeven_at_r = 1.0
    trade = run(bars, cfg).trades.iloc[0]
    assert trade["exit_reason"] == "stop"
    assert trade["r_multiple"] == pytest.approx(-1.0, abs=1e-6)


# ----------------------------------------------------------------------
# cost accounting
# ----------------------------------------------------------------------
def test_a_free_market_costs_nothing():
    bars = flat_bars()
    bars.iloc[13, bars.columns.get_loc("high")] = 1.10305
    trade = run(bars, make_config()).trades.iloc[0]
    assert trade["cost"] == pytest.approx(0.0, abs=1e-9)
    assert trade["cost_r"] == pytest.approx(0.0, abs=1e-9)


def test_recorded_cost_is_the_friction_the_broker_charged():
    """Commission, spread and slippage, in account currency, per lot."""
    bars = flat_bars()
    bars.iloc[13, bars.columns.get_loc("high")] = 1.1060
    charged = run(
        bars, make_config(spread_pips=1.5, slippage_pips=0.3, commission=7.0)
    ).trades.iloc[0]

    # Target exit: full spread plus one side of slippage, plus commission.
    expected_per_lot = (1.5 + 0.3) * 10.0 + 7.0
    assert charged["cost"] / charged["lots"] == pytest.approx(expected_per_lot, rel=1e-6)


def test_spread_does_not_shrink_a_winner_it_moves_the_levels():
    """Why gross expectancy cannot be reconstructed by adding the cost back.

    Stops and targets are set from the executed entry, so a trade that reaches
    its target still travels exactly the planned distance. The spread makes
    reaching it less likely; it does not reduce the win.
    """
    bars = flat_bars()
    bars.iloc[13, bars.columns.get_loc("high")] = 1.1060

    free = run(bars, make_config()).trades.iloc[0]
    charged = run(bars, make_config(spread_pips=1.5, slippage_pips=0.3)).trades.iloc[0]

    pips_free = (free["exit"] - free["entry"]) / 0.0001
    pips_charged = (charged["exit"] - charged["entry"]) / 0.0001
    assert pips_charged == pytest.approx(pips_free, rel=1e-6)
    assert charged["entry"] > free["entry"], "the spread shifts where the trade begins"


def test_a_target_exit_pays_less_slippage_than_a_stop():
    """A limit order fills at its price or not at all; a stop is a market order."""
    cfg = make_config(spread_pips=1.0, slippage_pips=0.5, commission=0.0)

    won = flat_bars()
    won.iloc[13, won.columns.get_loc("high")] = 1.1060
    target = run(won, cfg).trades.iloc[0]
    assert target["exit_reason"] == "target"

    lost = flat_bars()
    lost.iloc[13, lost.columns.get_loc("low")] = 1.09845
    stop = run(lost, cfg).trades.iloc[0]

    assert stop["cost"] / stop["lots"] > target["cost"] / target["lots"]


def test_metrics_report_friction_without_inventing_a_gross_figure():
    from forexai.metrics import compute_metrics

    bars = flat_bars(n=60)
    bars.iloc[13, bars.columns.get_loc("high")] = 1.1060
    result = run(bars, make_config(spread_pips=1.5, slippage_pips=0.3, commission=7.0))
    metrics = compute_metrics(result.trades, result.equity, 10_000.0)

    assert metrics["cost_r_per_trade"] > 0
    assert metrics["cost_currency_per_trade"] > 0
    assert "expectancy_r_gross" not in metrics, (
        "a gross expectancy cannot be reconstructed by adding the cost back"
    )
