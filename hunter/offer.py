"""Turn a qualified lead into a price and a first message.

The message is written to be *sent by a human who read it*, not to be blasted.
It follows the only structure that reliably gets answered on a public board:

    1. proof you read their post (their words, quoted back)
    2. exactly what you would deliver - three lines, no fog
    3. something free, delivered before any payment
    4. a price and a date
    5. one question, so replying is easier than ignoring

Prices come from the playbook, anchored to whatever the poster said they would
pay. Two hard rules: never quote above a stated budget, and never quote below
the walk-away floor without flagging it.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Optional

from .extract import USD_RATE
from .i18n_pt import PT
from .lead import Lead
from .playbook import BY_KEY, OTHER, Playbook

# The playbook stays the source of truth for prices and keywords; only what the
# client actually reads is translated. Adding French later = one more mapping.
TRANSLATIONS = {"pt": PT}

LANGS = ("en", "fr", "pt")

# A Brazilian buyer thinks in reais. Prices are computed in USD so leads stay
# comparable, then quoted in the currency the buyer wrote - or, when they wrote
# none, the currency of the language you are answering in.
LANG_CURRENCY = {"en": "USD", "fr": "EUR", "pt": "BRL"}
SYMBOL = {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "BRL": "R$",
          "CAD": "C$", "AUD": "A$", "INR": "\u20b9", "MXN": "MX$"}

_TAGS = re.compile(
    r"^\s*(?:\[[^\]]{0,30}\]|\([^)]{0,30}\)|(?:seeking freelancer|freelancer|hiring|remote|"
    r"task|paid)\s*[|:-])\s*", re.I)
_TRAILING = re.compile(r"\s*[-|]\s*(?:remote|worldwide|anywhere|full[- ]time|part[- ]time)\s*$", re.I)
# "I need someone to build X" -> "build X": the hook re-states the ask, so the
# asking verb has to go or the sentence stutters.
_LEAD_VERB = re.compile(
    r"^(?:i\s+|we\s+)?(?:am\s+|'m\s+|are\s+|'re\s+)?"
    r"(?:need(?:s|ed|ing)?|want(?:ed|ing)?|look(?:ing)?\s+for|look(?:ing)?\s+to\s+hire|"
    r"seek(?:ing)?|iso|in\s+search\s+of|searching\s+for|require|hiring|help\s+with|"
    # pt-BR
    r"preciso\s+de|preciso|procuro|estou\s+procurando|quero|contrato)\s+"
    r"(?:someone\s+(?:to|who\s+can|that\s+can)\s+|somebody\s+to\s+|a\s+|an\s+|the\s+|my\s+|"
    r"some\s+|algu[ée]m\s+(?:para|pra|que)\s+|algu[ée]m\s+|um\s+|uma\s+)?",
    re.I)
# Everything after the first budget/urgency/contact clause is board noise, not
# the ask: quoting it back reads like a bot.
_NOISE = re.compile(
    r"(?:\b(?:budget|asap|urgent|dm me|pm me|email me|paying|will pay|need it|"
    r"today|tomorrow|per (?:video|article|hour|page)|ongoing|remote|"
    # pt-BR
    r"or[çc]amento|urgente|me chama|pago|pagamento|hoje|amanh[ãa])\b|[$€£]\s?\d|R\$)""", re.I)


def playbook_for(lead: Lead) -> Playbook:
    return BY_KEY.get(lead.category, OTHER)


def summarize_ask(lead: Lead) -> str:
    """The poster's own request, stripped of board furniture, for quoting back."""
    candidate = _TRAILING.sub("", _TAGS.sub("", lead.title or "")).strip(" -|:")
    if len(candidate) < 25:
        for line in (lead.body or "").split("\n"):
            line = line.strip()
            if len(line) >= 40:
                candidate = line
                break
    candidate = _LEAD_VERB.sub("", candidate, count=1)
    return _trim_noise(candidate)[:160]


# Board furniture that carries no information about the work itself.
_DROP_PART = re.compile(
    r"^(?:remote|worldwide|anywhere|onsite|on[- ]site|hybrid|urgent|paid|freelance|"
    r"contract|full[- ]time|part[- ]time|usa?|us only|europe|eu|latam|asia)$", re.I)


def _trim_noise(text: str) -> str:
    """Keep the clauses that describe the work, drop the ones about the deal."""
    parts = re.split(r"\s*(?:[,.;]\s+|\s[-–—|]\s)", text)
    kept: list[str] = []
    for part in parts:
        part = part.strip()
        if not part or _DROP_PART.match(part):
            continue
        if kept and _NOISE.search(part):
            break
        kept.append(part)
    return ", ".join(kept).strip(" -|:.,")


def _band(budget: dict, low: float, high: float) -> str:
    """The budget as the poster wrote it, with the USD equivalent when needed."""
    currency = budget.get("currency", "USD")
    symbol = SYMBOL.get(currency, f"{currency} ")
    native_low, native_high = budget.get("low", low), budget.get("high", high)
    written = (f"{symbol}{native_low:,.0f}" if native_high == native_low
               else f"{symbol}{native_low:,.0f}-{native_high:,.0f}")
    if currency == "USD":
        return written
    return f"{written} (~${low:,.0f}-{high:,.0f})" if high > low else f"{written} (~${high:,.0f})"


def _round_price(value: float) -> float:
    if value <= 200:
        step = 5
    elif value <= 1000:
        step = 10
    else:
        step = 50
    return float(int(round(value / step)) * step)


def suggest_price(lead: Lead) -> tuple[Optional[float], str]:
    """(price in USD, why). Anchored to what they said, floored by the playbook."""
    book = playbook_for(lead)
    budget = lead.budget

    if not budget:
        return _round_price(book.target_usd), (
            "aucun budget annoncé - prix d'ancrage du catalogue "
            f"({book.label}, plancher ${book.floor_usd:.0f})"
        )

    if budget.get("per") == "hour":
        rate = float(budget["usd_low"])
        price = _round_price(rate * book.hours)
        return price, (
            f"{rate:.0f} $/h annoncé x {book.hours:.0f} h de travail estimées — "
            "proposé en forfait, pas en horaire (le forfait se vend mieux)"
        )

    high = float(budget["usd_high"])
    low = float(budget["usd_low"])
    if high < book.floor_usd:
        return _round_price(high), (
            f"budget annoncé {_band(budget, low, high)} sous le plancher "
            f"${book.floor_usd:.0f} — à prendre seulement comme première référence client, "
            "sinon passer"
        )
    price = _round_price(min(high, max(book.floor_usd, 0.75 * high)))
    band = _band(budget, low, high)
    if price >= high:
        return price, (f"leur budget {band} est pile au plancher {book.label.lower()} "
                       f"(${book.floor_usd:.0f}) — tu prends tout, ou tu passes")
    return price, (f"75 % du haut de leur fourchette {band} — "
                   "sous leur plafond, au-dessus du plancher")


def quote_currency(lead: Lead, lang: str) -> str:
    """What currency to put in front of the client."""
    if lead.budget and lead.budget.get("currency"):
        return lead.budget["currency"]
    return LANG_CURRENCY.get(lang, "USD")


def format_price(price_usd: Optional[float], currency: str) -> str:
    """USD price, converted and rounded again in the currency being quoted."""
    if price_usd is None:
        return "-"
    rate = USD_RATE.get(currency, 1.0)
    local = _round_price(price_usd / rate) if rate else price_usd
    symbol = SYMBOL.get(currency, f"{currency} ")
    return f"{symbol}{local:,.0f}"


# ----------------------------------------------------------------------
# the message
# ----------------------------------------------------------------------
_TEMPLATES = {
    "en": {
        "hook": "Hi - about your post: \"{ask}\". That is exactly what I do.",
        "scope_head": "What you get:",
        "proof": "Before you pay anything: {proof}. If it is not what you want, you owe me nothing.",
        "price": "Price: {price} fixed, delivered in {days} day{s}. One revision round included.",
        "question": "One question so I quote precisely: {question}",
        "cta": "If that works, reply here and I start today.",
    },
    "fr": {
        "hook": "Bonjour - au sujet de votre annonce : \u00ab {ask} \u00bb. C'est exactement ce que je fais.",
        "scope_head": "Ce que vous recevez :",
        "proof": "Avant tout paiement : {proof}. Si ca ne vous convient pas, vous ne devez rien.",
        "price": "Prix : {price} forfait, livré en {days} jour{s}. Une série de retouches incluse.",
        "question": "Une question pour chiffrer precisement : {question}",
        "cta": "Si ca vous va, repondez ici et je commence aujourd'hui.",
    },
    "pt": {
        "hook": "Ol\u00e1 - sobre o seu an\u00fancio: \"{ask}\". \u00c9 exatamente o que eu fa\u00e7o.",
        "scope_head": "O que voc\u00ea recebe:",
        "proof": "Antes de qualquer pagamento: {proof}. Se n\u00e3o for o que voc\u00ea quer, "
                 "n\u00e3o me deve nada.",
        "price": "Pre\u00e7o: {price} fechado, entregue em {days} dia{s}. "
                 "Uma rodada de ajustes inclu\u00edda.",
        "question": "Uma pergunta para or\u00e7ar com precis\u00e3o: {question}",
        "cta": "Se fizer sentido, responda aqui e eu come\u00e7o hoje.",
    },
}


def wording(book: Playbook, lang: str) -> tuple[tuple[str, ...], str, str]:
    """(scope bullets, free proof, qualifying question) in the buyer's language."""
    translated = TRANSLATIONS.get(lang, {}).get(book.key)
    if not translated:
        return book.scope, book.proof, book.question
    return tuple(translated["scope"]), translated["proof"], translated["question"]


def draft_message(lead: Lead, price: Optional[float], lang: str = "en") -> str:
    """The first message, ready for a human to read, edit and send."""
    template = _TEMPLATES.get(lang, _TEMPLATES["en"])
    book = playbook_for(lead)
    scope, proof, question = wording(book, lang)
    currency = quote_currency(lead, lang)
    ask = summarize_ask(lead)
    days = book.days
    if lead.deadline and lead.deadline.get("days") is not None:
        # Move towards their deadline, but never promise faster than half the
        # playbook's honest delivery time. A missed first deadline kills the
        # only thing this business has: a reference.
        asked = int(round(lead.deadline["days"])) or 1
        days = max(1, (book.days + 1) // 2, min(days, asked))

    lines = [
        template["hook"].format(ask=ask),
        "",
        template["scope_head"],
    ]
    lines += [f"- {item}" for item in scope]
    lines += [
        "",
        template["proof"].format(proof=proof),
        template["price"].format(price=format_price(price or book.target_usd, currency),
                                 days=days, s="s" if days > 1 else ""),
        "",
        template["question"].format(question=question),
        template["cta"],
    ]
    return "\n".join(lines)


def prepare(lead: Lead, lang: str = "en") -> Lead:
    """Attach price, rationale, proof offer and draft to a qualified lead."""
    price, note = suggest_price(lead)
    lead.price_usd = price
    lead.price_note = note
    lead.price_display = format_price(price, quote_currency(lead, lang))
    lead.proof = wording(playbook_for(lead), lang)[1]
    lead.draft = draft_message(lead, price, lang)
    return lead


# ----------------------------------------------------------------------
# optional local polish (Ollama) - never required, never fatal
# ----------------------------------------------------------------------
OLLAMA = "http://localhost:11434/api/generate"

_POLISH_RULES = (
    "Rewrite this freelance outreach message so it sounds like one competent "
    "human wrote it in two minutes. Keep every fact: the scope bullets, the free "
    "sample, the price, the deadline, the question. Max 150 words. No flattery, "
    "no 'I hope this finds you well', no emoji. Return only the message."
)


def polish(draft: str, endpoint: str = OLLAMA, model: str = "llama3.2:3b", timeout: int = 60) -> str:
    """Ask a local model to smooth the wording. Falls back to the template."""
    payload = json.dumps({
        "model": model,
        "prompt": f"{_POLISH_RULES}\n\n---\n{draft}\n---",
        "stream": False,
        "options": {"temperature": 0.4},
    }).encode()
    request = urllib.request.Request(endpoint, data=payload,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8", "replace"))
        text = (body.get("response") or "").strip()
        return text if len(text) > 60 else draft
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return draft
