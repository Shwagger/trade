"""Alerts must be actionable and must never crash the watcher.

The transport cannot be exercised offline, so what is pinned here is the part
that matters to a human at 3am: does the message contain the whole order.
"""

import pandas as pd
import pytest

from forexai.config import CostConfig, InstrumentConfig, RiskConfig
from forexai.notify import (
    ConsoleNotifier,
    TelegramNotifier,
    format_close,
    format_drift,
    format_halt,
    format_trade_alert,
)
from forexai.risk import RiskManager
from forexai.signal import Decision


def a_plan(approved=True):
    rm = RiskManager(RiskConfig(), InstrumentConfig(), CostConfig(), 10_000.0)
    ts = pd.Timestamp("2024-05-02 13:00", tz="UTC")
    rm.on_new_bar(ts)
    return rm.evaluate(ts, 1 if approved else 0, 1.08000, 0.0010)


def a_decision():
    return Decision(
        direction=1, score=0.42, confidence=0.31, lift=1.35,
        ml_score=0.5, ta_score=0.3, reason="signal accepted",
    )


def test_trade_alert_carries_the_whole_order():
    text = format_trade_alert(
        "EURUSD", "1h", pd.Timestamp("2024-05-02 13:00", tz="UTC"),
        a_decision(), a_plan(), equity=10_000.0,
    )
    for token in ("LONG", "EURUSD", "entry", "stop", "target", "size", "risk", "R:R"):
        assert token in text
    plan = a_plan()
    assert f"{plan.stop_loss:.5f}" in text, "a stop price must be in the message"
    assert f"{plan.lots:.2f}" in text, "a lot size must be in the message"


def test_trade_alert_says_do_nothing_when_risk_refuses():
    """The model wanted in, the risk engine said no: say which, and why."""
    text = format_trade_alert(
        "EURUSD", "1h", pd.Timestamp("2024-05-02 03:00", tz="UTC"),
        a_decision(), a_plan(approved=False), equity=10_000.0,
    )
    assert "WAIT" in text and "Do nothing" in text
    assert "risk manager refused" in text


def test_wait_alert_reports_the_signal_reason_not_the_risk_reason():
    """When no setup fired at all, blaming the risk manager is misleading."""
    quiet = Decision(
        direction=0, score=0.02, confidence=0.30, lift=1.01,
        ml_score=0.03, ta_score=0.01, reason="edge below threshold",
    )
    text = format_trade_alert(
        "EURUSD", "1h", pd.Timestamp("2024-05-02 13:00", tz="UTC"),
        quiet, a_plan(approved=False), equity=10_000.0,
    )
    assert "edge below threshold" in text
    assert "risk manager refused" not in text


def test_risk_percentage_is_shown_and_respects_the_mandate():
    plan = a_plan()
    text = format_trade_alert(
        "EURUSD", "1h", pd.Timestamp("2024-05-02 13:00", tz="UTC"),
        a_decision(), plan, equity=10_000.0,
    )
    assert "0.4" in text or "0.5" in text        # ~0.5% of equity
    assert plan.risk_amount <= 50.0 + 1e-9


def test_close_alert_reports_the_result_in_r():
    text = format_close("EURUSD", {
        "r_multiple": -1.0, "pnl": -49.5, "entry": 1.08, "exit": 1.0785,
        "bars_held": 4, "equity_after": 9_950.5, "exit_reason": "stop",
    })
    assert "LOSS" in text and "-1.00 R" in text and "stop" in text


def test_drift_and_halt_alerts_tell_the_human_what_to_do():
    drift = format_drift("EURUSD", {
        "forward_expectancy_r": -0.4, "backtest_ci_low": 0.05, "trades": 30,
    })
    assert "Stop adding risk" in drift
    halt = format_halt("EURUSD", "kill switch: drawdown 21.0%")
    assert "HALTED" in halt and "drawdown" in halt


def test_telegram_is_disabled_without_credentials():
    notifier = TelegramNotifier()
    assert not notifier.enabled
    assert notifier.send("anything") is False
    assert "TELEGRAM_BOT_TOKEN" in notifier.describe()


def test_telegram_reports_a_partial_configuration():
    assert "TELEGRAM_CHAT_ID" in TelegramNotifier(token="123:abc").describe()


def test_telegram_never_raises_on_a_dead_endpoint():
    notifier = TelegramNotifier(
        token="123:abc", chat_id="42",
        endpoint="http://127.0.0.1:9/bot{token}/sendMessage", timeout=0.2,
    )
    assert notifier.enabled
    assert notifier.send("hello") is False          # unreachable, but no exception


def test_console_notifier_always_delivers(capsys):
    assert ConsoleNotifier().send("test message") is True
    assert "test message" in capsys.readouterr().out


def test_monitor_survives_a_broken_notifier(tmp_path):
    """A messaging outage must not stop the thing watching the market."""
    from forexai.config import Config
    from forexai.monitor import Monitor

    class Exploding:
        enabled = True

        def send(self, text):
            raise RuntimeError("network on fire")

    monitor = Monitor(Config(), model=None, workdir=tmp_path, notifier=Exploding())
    monitor._notify("anything")                     # must not raise
    journal = monitor.journal.read()
    assert (journal["kind"] == "notify_failed").any()
