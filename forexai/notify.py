"""Alerts: tell the human what to do, precisely enough to act on.

An alert that says "BUY EURUSD" is worthless - it leaves the two decisions that
actually matter (where the stop goes, how big the position is) to a human
looking at a phone. Every alert here carries the complete order: side, entry,
stop, target, lot size, money at risk, and the reward-to-risk after costs.

Formatting and transport are separate. The formatters are pure functions and
are unit-tested; the transport is a thin wrapper that never raises, because a
network hiccup must not take down the process that is watching the market.

Setup (two minutes, on your own machine):

1. In Telegram, message ``@BotFather``, send ``/newbot``, follow the prompts.
   It gives you a token that looks like ``123456789:AAF...``.
2. Message your new bot once (it cannot write to you until you do).
3. Open ``https://api.telegram.org/bot<TOKEN>/getUpdates`` in a browser and copy
   the ``chat.id`` field.
4. Export both values::

       export TELEGRAM_BOT_TOKEN="123456789:AAF..."
       export TELEGRAM_CHAT_ID="987654321"

5. ``python -m forexai monitor --interval 300 --telegram``
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional, Protocol

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

ARROW = {1: "LONG", -1: "SHORT"}


class Notifier(Protocol):
    """Anything that can deliver a line of text to the human."""

    enabled: bool

    def send(self, text: str) -> bool:
        ...


# ----------------------------------------------------------------------
# formatters (pure, tested)
# ----------------------------------------------------------------------
def format_trade_alert(
    symbol: str,
    timeframe: str,
    bar_time,
    decision,
    plan,
    equity: float,
) -> str:
    """The actionable message: everything needed to place the order by hand."""
    if decision.direction == 0:
        return (
            f"WAIT - {symbol} {timeframe}\n"
            f"bar {bar_time}\n"
            f"No setup: {decision.reason}.\n"
            f"  ml {decision.ml_score:+.2f} | rules {decision.ta_score:+.2f}\n"
            f"No order. Do nothing - most bars end here, and that is the point."
        )

    if not plan.approved:
        return (
            f"WAIT - {symbol} {timeframe}\n"
            f"bar {bar_time}\n"
            f"The model wanted {decision.action}, the risk manager refused:\n"
            f"  {plan.reason}\n"
            f"No order. Do nothing."
        )

    side = ARROW.get(plan.direction, "?")
    risk_pct = 100.0 * plan.risk_amount / equity if equity else 0.0
    return (
        f"{side} {symbol} {timeframe}\n"
        f"bar {bar_time}\n"
        f"\n"
        f"  entry     ~{plan.entry:.5f}  (market, now)\n"
        f"  stop      {plan.stop_loss:.5f}   ({plan.risk_pips:.1f} pips)\n"
        f"  target    {plan.take_profit:.5f}   ({plan.reward_pips:.1f} pips)\n"
        f"  size      {plan.lots:.2f} lots\n"
        f"  risk      {plan.risk_amount:.2f}  ({risk_pct:.2f}% of {equity:,.0f})\n"
        f"  R:R       {plan.planned_rr:.2f}  ({plan.net_rr:.2f} after costs)\n"
        f"\n"
        f"  confidence {decision.confidence:.0%} "
        f"({decision.lift:.2f}x base rate)\n"
        f"  ml {decision.ml_score:+.2f} | rules {decision.ta_score:+.2f}\n"
        f"\n"
        f"Place the stop with the order, not after. Indicative price: the\n"
        f"backtest fills at the next bar's open, you are filling now."
    )


def format_fill(symbol: str, trade_direction: int, entry: float, lots: float,
                stop_loss: float, take_profit: float) -> str:
    return (
        f"FILLED (paper) {ARROW.get(trade_direction, '?')} {symbol}\n"
        f"  entry {entry:.5f} | {lots:.2f} lots\n"
        f"  stop {stop_loss:.5f} | target {take_profit:.5f}"
    )


def format_close(symbol: str, trade: dict) -> str:
    r = trade.get("r_multiple", 0.0)
    verdict = "WIN" if trade.get("pnl", 0.0) > 0 else "LOSS"
    return (
        f"CLOSED (paper) {verdict} {symbol} - {trade.get('exit_reason', '?')}\n"
        f"  {trade.get('entry', 0):.5f} -> {trade.get('exit', 0):.5f}\n"
        f"  {trade.get('pnl', 0):+.2f}  ({r:+.2f} R) after {trade.get('bars_held', 0)} bars\n"
        f"  paper equity {trade.get('equity_after', 0):,.2f}"
    )


def format_drift(symbol: str, event: dict) -> str:
    return (
        f"DRIFT ALERT - {symbol}\n"
        f"  forward expectancy {event.get('forward_expectancy_r', 0):+.4f} R "
        f"over {event.get('trades', 0)} trades\n"
        f"  backtest lower bound {event.get('backtest_ci_low', 0):+.4f} R\n"
        f"  The live results are worse than the backtest said they could be.\n"
        f"  Stop adding risk and re-run the walk-forward on fresh data."
    )


def format_halt(symbol: str, reason: str) -> str:
    return (
        f"TRADING HALTED - {symbol}\n"
        f"  {reason}\n"
        f"  No further orders will be proposed until this is reviewed by hand."
    )


# ----------------------------------------------------------------------
# transport
# ----------------------------------------------------------------------
@dataclass
class TelegramNotifier:
    """Telegram delivery. Silent about content, loud about being misconfigured."""

    token: str = ""
    chat_id: str = ""
    endpoint: str = TELEGRAM_API
    timeout: float = 15.0
    silent: bool = False

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    @classmethod
    def from_env(cls) -> "TelegramNotifier":
        return cls(
            token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        )

    def describe(self) -> str:
        if self.enabled:
            return f"telegram: on (chat {self.chat_id})"
        missing = []
        if not self.token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.chat_id:
            missing.append("TELEGRAM_CHAT_ID")
        return f"telegram: off - set {' and '.join(missing)} (see forexai/notify.py)"

    def send(self, text: str) -> bool:
        """Deliver one message. Returns success; never raises."""
        if not self.enabled:
            return False
        payload = json.dumps(
            {
                "chat_id": self.chat_id,
                "text": text,
                "disable_notification": self.silent,
                "disable_web_page_preview": True,
            }
        ).encode()
        try:
            request = urllib.request.Request(
                self.endpoint.format(token=self.token),
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode())
            return bool(body.get("ok"))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError,
                TimeoutError, json.JSONDecodeError, ValueError):
            return False


@dataclass
class ConsoleNotifier:
    """Fallback used when Telegram is not configured: print, do not lose."""

    enabled: bool = True

    def send(self, text: str) -> bool:
        print("\n--- ALERT " + "-" * 50)
        print(text)
        print("-" * 60)
        return True


def build_notifier(use_telegram: bool) -> Optional[Notifier]:
    if not use_telegram:
        return None
    telegram = TelegramNotifier.from_env()
    print(telegram.describe())
    return telegram if telegram.enabled else ConsoleNotifier()
