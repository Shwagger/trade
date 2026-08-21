"""The risk manager is the last line of defence. Every veto is tested."""

import pandas as pd
import pytest

from forexai.config import CostConfig, InstrumentConfig, RiskConfig
from forexai.risk import RiskManager

LONDON = pd.Timestamp("2024-05-02 13:00", tz="UTC")   # inside the overlap session
TOKYO = pd.Timestamp("2024-05-02 03:00", tz="UTC")    # outside the allowed sessions
ATR = 0.0010


def manager(equity=10_000.0, **risk_overrides):
    cfg = RiskConfig(**risk_overrides)
    rm = RiskManager(cfg, InstrumentConfig(), CostConfig(), equity)
    rm.on_new_bar(LONDON)
    return rm


def test_risk_per_trade_is_respected():
    rm = manager()
    plan = rm.evaluate(LONDON, 1, 1.08000, ATR)
    assert plan.approved
    # Lot rounding can only ever round the risk *down*, never above the budget.
    assert plan.risk_amount <= 10_000 * 0.005 + 1e-9
    assert plan.risk_amount > 10_000 * 0.005 * 0.9


def test_position_size_scales_inversely_with_volatility():
    rm = manager()
    calm = rm.evaluate(LONDON, 1, 1.08000, 0.0008)
    wild = rm.evaluate(LONDON, 1, 1.08000, 0.0030)
    assert calm.approved and wild.approved
    assert wild.lots < calm.lots


def test_every_approved_plan_carries_a_stop_and_a_target():
    rm = manager()
    for direction in (1, -1):
        plan = rm.evaluate(LONDON, direction, 1.08000, ATR)
        assert plan.approved
        assert plan.stop_loss == pytest.approx(1.08000 - direction * 1.5 * ATR)
        assert plan.take_profit == pytest.approx(1.08000 + direction * 3.0 * ATR)
        assert plan.planned_rr >= 2.0


def test_session_filter():
    rm = manager()
    rm.on_new_bar(TOKYO)
    assert not rm.evaluate(TOKYO, 1, 1.08000, ATR).approved


def test_wide_spread_is_refused():
    cfg = RiskConfig()
    costs = CostConfig(spread_pips=1.0, max_tradable_spread_pips=2.5)
    rm = RiskManager(cfg, InstrumentConfig(), costs, 10_000.0)
    rm.on_new_bar(LONDON)
    assert not rm.evaluate(LONDON, 1, 1.08000, ATR, spread_pips=9.0).approved


def test_volatility_band():
    rm = manager()
    assert not rm.evaluate(LONDON, 1, 1.08000, 0.00001).approved   # dead market
    assert not rm.evaluate(LONDON, 1, 1.08000, 0.0200).approved    # chaos


def test_daily_loss_limit_stops_trading():
    rm = manager()
    rm.register_open()
    rm.register_close(-250.0)          # 2.5% of equity, above the 2% daily cap
    assert not rm.evaluate(LONDON, 1, 1.08000, ATR).approved
    assert rm.state.daily_blocked


def test_daily_limit_resets_on_the_next_day():
    rm = manager()
    rm.register_open()
    rm.register_close(-250.0)
    next_day = LONDON + pd.Timedelta(days=1)
    rm.on_new_bar(next_day)
    assert rm.evaluate(next_day, 1, 1.08000, ATR).approved


def test_drawdown_kill_switch_is_permanent():
    rm = manager(max_daily_loss=1.0)
    rm.register_open()
    rm.register_close(-2_500.0)        # 25% > 20% cap
    assert rm.state.halted
    later = LONDON + pd.Timedelta(days=5)
    rm.on_new_bar(later)
    assert not rm.evaluate(later, 1, 1.08000, ATR).approved


def test_losing_streak_triggers_a_cooldown():
    rm = manager(max_consecutive_losses=3, cooldown_bars_after_streak=5, max_daily_loss=1.0)
    for _ in range(3):
        rm.register_open()
        rm.register_close(-50.0)
    assert not rm.evaluate(LONDON, 1, 1.08000, ATR).approved
    for _ in range(5):
        rm.on_new_bar(LONDON)
    assert rm.evaluate(LONDON, 1, 1.08000, ATR).approved


def test_one_position_at_a_time():
    rm = manager()
    rm.register_open()
    assert not rm.evaluate(LONDON, 1, 1.08000, ATR).approved


def test_account_too_small_to_respect_the_risk_rule():
    """Better to refuse the trade than to break the 0.5% rule."""
    rm = manager(equity=100.0)
    assert not rm.evaluate(LONDON, 1, 1.08000, ATR).approved


def test_no_signal_is_no_trade():
    rm = manager()
    assert not rm.evaluate(LONDON, 0, 1.08000, ATR).approved


def test_costs_can_make_a_2to1_trade_unworthy():
    """A 2:1 plan on a tiny stop is not 2:1 once the broker is paid."""
    costs = CostConfig(spread_pips=3.0, slippage_pips=0.5, commission_per_lot_roundturn=7.0,
                       max_tradable_spread_pips=5.0)
    rm = RiskManager(RiskConfig(), InstrumentConfig(), costs, 10_000.0)
    rm.on_new_bar(LONDON)
    plan = rm.evaluate(LONDON, 1, 1.08000, 0.00055)
    assert not plan.approved
    assert "reward:risk" in plan.reason
