"""Pull the three facts that decide whether a post is worth answering.

Budget, deadline, and how to reach the person. Everything here is a pure
function over text: no network, no state, fully unit-tested. When a fact is not
in the text it comes back as ``None`` - an invented budget is worse than no
budget, because it makes a bad lead look like a good one.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Optional

# Static, deliberately approximate. Nobody quotes a client to the cent off a
# rate table, and a live FX call would add a network dependency to a pure
# function. Edit when a rate drifts enough to change a decision.
USD_RATE = {
    "USD": 1.00,
    "EUR": 1.08,
    "GBP": 1.27,
    "CAD": 0.73,
    "AUD": 0.66,
    "BRL": 0.19,
    "INR": 0.012,
    "MXN": 0.055,
}

_SYMBOL = {
    "$": "USD",
    "us$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "euros": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "r$": "BRL",
    "brl": "BRL",
    "reais": "BRL",
    "c$": "CAD",
    "cad": "CAD",
    "a$": "AUD",
    "aud": "AUD",
    "inr": "INR",
    "rs.": "INR",
    "mxn": "MXN",
}

# "$1,2k" style numbers: 1,200 / 1.2k / 800 / 50.
# The thousands separator must never match a newline: "$180\n300 rows" is two
# numbers on two lines, not one hundred and eighty thousand.
_NUM = r"\d{1,3}(?:[,\u00a0 ]\d{3})+|\d+(?:\.\d+)?"
_CUR_BEFORE = r"(?:R\$|US\$|C\$|A\$|\$|€|£|USD|EUR|GBP|BRL|CAD|AUD|INR|MXN)"
_CUR_AFTER = r"(?:USD|EUR|GBP|BRL|CAD|AUD|INR|MXN|dollars?|euros?|reais|pounds?)"
_K = r"(?:\s?[kK])?"
_PER_HOUR = r"(?:\s*(?:/|per\s+|an?\s+)\s*(?:hr|hour|h|heure|hora))"


@dataclass
class Budget:
    """What the poster said they would pay. ``None`` fields mean 'not stated'."""

    low: float
    high: float
    currency: str
    per: str = "project"  # project | hour
    raw: str = ""

    @property
    def usd_low(self) -> float:
        return round(self.low * USD_RATE.get(self.currency, 1.0), 2)

    @property
    def usd_high(self) -> float:
        return round(self.high * USD_RATE.get(self.currency, 1.0), 2)

    def describe(self) -> str:
        unit = "/h" if self.per == "hour" else ""
        if abs(self.high - self.low) < 1e-9:
            body = f"{self.currency} {self.low:,.0f}{unit}"
        else:
            body = f"{self.currency} {self.low:,.0f}-{self.high:,.0f}{unit}"
        if self.currency != "USD":
            body += f" (~${self.usd_low:,.0f}-{self.usd_high:,.0f})"
        return body

    def to_dict(self) -> dict:
        d = asdict(self)
        d["usd_low"] = self.usd_low
        d["usd_high"] = self.usd_high
        return d


@dataclass
class Deadline:
    """How fast they need it. ``days`` is a coarse estimate, never a promise."""

    raw: str
    days: Optional[float] = None

    @property
    def urgency(self) -> float:
        """0..1. Urgent work pays better and gets answered faster."""
        if self.days is None:
            return 0.4
        if self.days <= 1:
            return 1.0
        if self.days <= 3:
            return 0.8
        if self.days <= 7:
            return 0.6
        if self.days <= 30:
            return 0.3
        return 0.1

    def to_dict(self) -> dict:
        return {"raw": self.raw, "days": self.days, "urgency": round(self.urgency, 2)}


# ----------------------------------------------------------------------
# text hygiene
# ----------------------------------------------------------------------
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t ]+")
_ENTITY = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
    "&#39;": "'", "&#x27;": "'", "&nbsp;": " ", "&mdash;": "-", "&rsquo;": "'",
}


def clean_text(raw: str) -> str:
    """HTML in, readable plain text out. Reddit and HN both send markup."""
    if not raw:
        return ""
    text = raw.replace("<br>", "\n").replace("<br/>", "\n").replace("</p>", "\n")
    text = _TAG.sub(" ", text)
    for entity, char in _ENTITY.items():
        text = text.replace(entity, char)
    text = unicodedata.normalize("NFKC", text)
    text = _WS.sub(" ", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def _to_float(token: str, k_suffix: bool) -> float:
    token = token.replace(",", "").replace(" ", "").replace("\u00a0", "")
    value = float(token)
    return value * 1000 if k_suffix else value


def _currency_of(symbol: str) -> str:
    return _SYMBOL.get(symbol.strip().lower(), "USD")


# ----------------------------------------------------------------------
# budget
# ----------------------------------------------------------------------
_SEP = r"(?:-|–|—|to|and|et|a|à|e)"
_RANGE_BEFORE = re.compile(
    rf"({_CUR_BEFORE})\s?({_NUM})(\s?[kK])?{_PER_HOUR}?\s*{_SEP}\s*(?:{_CUR_BEFORE})?\s?({_NUM})(\s?[kK])?({_PER_HOUR})?",
    re.IGNORECASE,
)
_RANGE_AFTER = re.compile(
    rf"({_NUM})(\s?[kK])?\s*{_SEP}\s*({_NUM})(\s?[kK])?\s?({_CUR_AFTER})({_PER_HOUR})?",
    re.IGNORECASE,
)
_SINGLE_BEFORE = re.compile(
    rf"({_CUR_BEFORE})\s?({_NUM})(\s?[kK])?({_PER_HOUR})?", re.IGNORECASE
)
_SINGLE_AFTER = re.compile(
    rf"({_NUM})(\s?[kK])?\s?({_CUR_AFTER})({_PER_HOUR})?", re.IGNORECASE
)
_BARE_BUDGET = re.compile(
    rf"(?:budget|pay(?:ing)?|price|rate|orçamento|orcamento)\s*(?:is|:|of|=|about|around)?\s*({_NUM})(\s?[kK])?",
    re.IGNORECASE,
)


def extract_budget(text: str) -> Optional[Budget]:
    """First credible money figure in the post, or None.

    Ordered by how much the pattern tells us: an explicit range beats a single
    number, and a number next to a currency beats a bare one after the word
    'budget'. Figures under 5 or over 250k are dropped - they are years, counts
    of users, or someone's revenue, not a price.
    """
    if not text:
        return None

    match = _RANGE_BEFORE.search(text)
    if not match:
        after = _RANGE_AFTER.search(text)
        if after:
            currency = _currency_of(after.group(5))
            low = _to_float(after.group(1), bool(after.group(2)))
            high = _to_float(after.group(3), bool(after.group(4)))
            if after.group(4) and not after.group(2) and low < high / 100:
                low *= 1000
            if high < low:
                low, high = high, low
            budget = Budget(low, high, currency,
                            "hour" if after.group(6) else "project", after.group(0).strip())
            if _plausible(budget):
                return budget
    if match:
        currency = _currency_of(match.group(1))
        low = _to_float(match.group(2), bool(match.group(3)))
        # "$2-5k" means two to five thousand: a bare low number inherits the
        # high number's k.
        high = _to_float(match.group(4), bool(match.group(5)))
        if match.group(5) and not match.group(3) and low < high / 100:
            low *= 1000
        if high < low:
            low, high = high, low
        per = "hour" if match.group(6) else "project"
        budget = Budget(low, high, currency, per, match.group(0).strip())
        return budget if _plausible(budget) else None

    for pattern, cur_group, num_group, k_group, per_group in (
        (_SINGLE_BEFORE, 1, 2, 3, 4),
        (_SINGLE_AFTER, 3, 1, 2, 4),
    ):
        for match in pattern.finditer(text):
            currency = _currency_of(match.group(cur_group))
            value = _to_float(match.group(num_group), bool(match.group(k_group)))
            per = "hour" if match.group(per_group) else "project"
            budget = Budget(value, value, currency, per, match.group(0).strip())
            if _plausible(budget):
                return budget

    match = _BARE_BUDGET.search(text)
    if match:
        value = _to_float(match.group(1), bool(match.group(2)))
        budget = Budget(value, value, "USD", "project", match.group(0).strip())
        if _plausible(budget):
            return budget
    return None


def _plausible(budget: Budget) -> bool:
    if budget.per == "hour":
        return 3 <= budget.usd_low <= 500
    return 5 <= budget.usd_low <= 250_000


# ----------------------------------------------------------------------
# deadline
# ----------------------------------------------------------------------
_DEADLINE_RULES = [
    (re.compile(r"\b(asap|urgent|urgently|right now|immediately|today|aujourd'hui|"
                r"hoje|urgente|para ontem|o quanto antes|com urg[êe]ncia)\b", re.I), 1.0),
    (re.compile(r"\b(tomorrow|by tomorrow|amanh[ãa]|demain)\b", re.I), 1.5),
    (re.compile(r"\b(?:in|within|next)\s+(\d+)\s+(hours?|days?|weeks?)\b", re.I), None),
    (re.compile(r"\b(this week|by friday|by monday|end of week|cette semaine|"
                r"(?:esta|essa) semana|at[ée] sexta)\b", re.I), 4.0),
    (re.compile(r"\b(next week|semaine prochaine|pr[oó]xima semana)\b", re.I), 10.0),
    (re.compile(r"\b(this month|end of (?:the )?month|by the \d{1,2}(?:st|nd|rd|th)|"
                r"este m[êe]s|at[ée] o fim do m[êe]s)\b", re.I), 20.0),
    (re.compile(r"\b(long[- ]term|ongoing|monthly|retainer|cont[ií]nuo|"
                r"mensal|recorrente|longo prazo)\b", re.I), 45.0),
]

_UNIT_DAYS = {"hour": 1 / 24, "hours": 1 / 24, "day": 1.0, "days": 1.0, "week": 7.0, "weeks": 7.0}


def extract_deadline(text: str) -> Optional[Deadline]:
    """Earliest deadline the post mentions, as a rough number of days."""
    if not text:
        return None
    best: Optional[Deadline] = None
    for pattern, days in _DEADLINE_RULES:
        match = pattern.search(text)
        if not match:
            continue
        if days is None:
            count = float(match.group(1))
            unit = match.group(2).lower()
            estimate = count * _UNIT_DAYS.get(unit, 1.0)
        else:
            estimate = days
        candidate = Deadline(match.group(0).strip(), estimate)
        if best is None or (candidate.days or 999) < (best.days or 999):
            best = candidate
    return best


# ----------------------------------------------------------------------
# how to answer
# ----------------------------------------------------------------------
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
_CONTACT_RULES = [
    (re.compile(r"\b(dm|pm)\s+me\b|\bsend\s+(?:me\s+)?a\s+(?:dm|pm)\b|"
                r"\bme chama\b|\bme manda (?:um )?(?:dm|direct|priv)", re.I), "DM"),
    (re.compile(r"\b(email|e-mail|mail)\s+me\b|\bme manda(?:r)? um e-?mail\b", re.I), "email"),
    (re.compile(r"\b(comment|reply)\s+(?:below|here|with)\b|\bcomenta (?:aqui|a[íi])\b", re.I),
     "comment"),
    (re.compile(r"\bapply\s+(?:here|at|via|through)\b", re.I), "application form"),
    (re.compile(r"\b(discord|telegram|whatsapp|slack)\b", re.I), "chat app"),
]


def extract_contact(text: str) -> tuple[str, Optional[str]]:
    """('DM'|'email'|..., explicit address if the poster wrote one)."""
    address = None
    match = _EMAIL.search(text or "")
    if match:
        address = match.group(0)
    for pattern, label in _CONTACT_RULES:
        if pattern.search(text or ""):
            return label, address
    return ("email" if address else "reply on the post"), address
