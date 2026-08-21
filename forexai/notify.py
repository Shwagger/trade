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


def format_start(symbol: str, timeframe: str, bar_time, equity: float) -> str:
    """Sent once, when the watcher starts on a fresh account.

    Its job is to prove the plumbing works. Without it the first run is silent -
    no setup fires on a single bar - and silence is indistinguishable from a
    broken token.
    """
    return (
        f"MONITOR STARTED - {symbol} {timeframe}\n"
        f"  watching from bar {bar_time}\n"
        f"  paper equity {equity:,.2f}\n"
        f"\n"
        f"Telegram is wired correctly. From now on you get a message only when\n"
        f"a setup actually fires - most bars are WAIT, so expect quiet stretches.\n"
        f"Paper only: this never sends an order to a broker."
    )


def format_test(symbol: str, timeframe: str) -> str:
    """On-demand proof that the credentials and the network path work.

    The start message only fires on a fresh account, so once a watcher has
    state there is otherwise no way to check the wiring without corrupting it.
    """
    return (
        "TEST ALERT\n"
        f"  watcher: {symbol} {timeframe}\n"
        "\n"
        "If you are reading this, the token and chat id are correct and the\n"
        "alerts will reach you. Nothing was traded and no state was changed."
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
        # Deliberately prints neither the token nor the chat id: this line ends
        # up in CI logs, which are far more visible than people expect.
        if self.enabled:
            return "telegram: on"
        missing = []
        if not self.token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.chat_id:
            missing.append("TELEGRAM_CHAT_ID")
        return f"telegram: off - set {' and '.join(missing)} (see forexai/notify.py)"

    @staticmethod
    def explain(body: dict, status: int | None = None) -> str:
        """Turn Telegram's refusal into the thing to actually go and fix."""
        code = int(body.get("error_code") or status or 0)
        description = str(body.get("description") or "").strip()
        detail = f"{code} {description}".strip() or "unknown error"

        if code == 401:
            return (
                f"{detail}\n"
                "  -> The token is not valid. Most often it was revoked: asking\n"
                "     BotFather for /revoke kills the previous token instantly,\n"
                "     so a secret holding the old one stops working.\n"
                "     Fix: BotFather -> /mybots -> your bot -> API Token, then\n"
                "     paste THAT value into the TELEGRAM_BOT_TOKEN secret."
            )
        if code == 404:
            return (
                f"{detail}\n"
                "  -> The token is malformed. It must look like 123456789:AA...\n"
                "     with the numeric part, the colon and the long part, and no\n"
                "     spaces or newlines around it."
            )
        if "chat not found" in description.lower():
            return (
                f"{detail}\n"
                "  -> The chat id is wrong, or you have never written to the bot.\n"
                "     A bot cannot open a conversation: send it any message from\n"
                "     Telegram first, then read the id from\n"
                "     https://api.telegram.org/bot<TOKEN>/getUpdates"
            )
        if code == 403:
            return (
                f"{detail}\n"
                "  -> The bot is blocked or was never started. Open the chat in\n"
                "     Telegram and press Start (or unblock it)."
            )
        if code == 429:
            return f"{detail}\n  -> Rate limited by Telegram. Wait and retry."
        return detail

    def deliver(self, text: str) -> tuple[bool, str]:
        """Send, and say precisely why if it did not work. Never raises.

        ``send`` returns only a boolean, which is all the watcher needs; when a
        human is debugging their setup, the boolean is useless and Telegram's
        own error message is the whole answer.
        """
        if not self.enabled:
            return False, self.describe()

        payload = json.dumps(
            {
                "chat_id": self.chat_id,
                "text": text,
                "disable_notification": self.silent,
                "disable_web_page_preview": True,
            }
        ).encode()
        request = urllib.request.Request(
            self.endpoint.format(token=self.token),
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode())
            if body.get("ok"):
                return True, "delivered"
            return False, self.explain(body)
        except urllib.error.HTTPError as exc:
            # Telegram puts the reason in the body even on a 4xx.
            try:
                body = json.loads(exc.read().decode())
            except (OSError, ValueError):
                body = {}
            return False, self.explain(body, status=exc.code)
        except (urllib.error.URLError, TimeoutError) as exc:
            return False, f"could not reach api.telegram.org: {exc}"
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return False, f"unexpected failure talking to Telegram: {exc}"

    def send(self, text: str) -> bool:
        """Deliver one message. Returns success; never raises."""
        return self.deliver(text)[0]


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
