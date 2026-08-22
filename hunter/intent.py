"""Buyer intent, scored from what the poster wrote - not from a hunch.

The score answers one question: *how likely is it that this person will pay
someone, soon, for something we can deliver?* It is a weighted sum of
explicit textual signals, so every number can be traced back to the words that
produced it. ``python -m hunter draft <id>`` prints that trace.

Three ideas do most of the work:

1. **A seller is not a buyer.** Half of every freelance board is people
   advertising themselves. "[FOR HIRE] senior dev available" scores zero, on
   purpose, however well written it is.
2. **Money on the page beats enthusiasm.** "Budget $400" is worth more than
   three paragraphs about an exciting opportunity.
3. **Old is dead.** A 4-day-old request has twenty replies already. Recency is
   part of the score, not a display column.

Tiers: HOT >= 70 (answer today), WARM >= 45 (answer if HOT is empty),
IGNORE below (never look at it again).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .extract import extract_budget, extract_contact, extract_deadline
from .lead import Lead
from .playbook import OTHER, classify

HOT = 70
WARM = 45

# The raw weights add up to ~125 for a perfect post. Scaling before the clamp
# keeps the top of the range usable: without it every strong lead lands on 100
# and the ranking stops discriminating between good and outstanding.
SCALE = 0.9


@dataclass
class Signal:
    name: str
    points: float
    evidence: str

    def to_dict(self) -> dict:
        return {"name": self.name, "points": round(self.points, 1), "evidence": self.evidence[:120]}


# (name, pattern, points). Positive signals: someone is trying to buy.
POSITIVE = [
    ("demande explicite", re.compile(
        r"\b(?:i (?:need|want|am looking for|'m looking for)|looking (?:for|to hire)|"
        r"we (?:need|are looking for|'re looking for)|seeking|"
        r"need(?:s|ed)?\s+(?:a|an|the|some|someone|help|two|\d)|"
        r"anyone (?:who can|able to)|can someone|in search of|iso|"
        # pt-BR
        r"preciso de|procuro|estou procurando|estou atr[áa]s de|algu[ée]m que|"
        r"quem (?:faz|consegue)|preciso que)\b", re.I), 22),
    ("recrute", re.compile(
        r"\[?\s*(hiring|task|for ?hire\s*-\s*seeking)\s*\]?|"
        r"\bwe(?:'re| are) hiring\b|\bhiring\b|\bseeking freelancer\b|\bfreelancer\?\b|"
        # pt-BR
        r"\bcontratando\b|\bvaga (?:de )?freela\w*\b|\bfreela\b|\bcontrato um\b", re.I), 18),
    ("paiement annoncé", re.compile(
        r"\b(?:(?:can|could|will|would|happy to|ready to|willing to|able to)\s+pay|"
        r"paid (?:gig|task|work|project|hourly)|budget|compensation|payment|"
        r"i pay|we pay|paying|per (?:article|hour|video|page)|rate is|"
        # pt-BR
        r"or[çc]amento|posso pagar|pago (?:bem|[àa] vista|por|no)|quanto (?:cobra|custa)|"
        r"valor a combinar|pagamento|remunera[çc][ãa]o)\b", re.I), 16),
    ("montant chiffré", None, 18),          # filled from the budget extractor
    ("urgence", None, 10),                  # filled from the deadline extractor
    ("chemin de réponse", None, 6),         # filled from the contact extractor
    ("catalogue", None, 12),                # filled from the playbook classifier
    ("scope decrit", re.compile(
        r"\b(deliverable|requirements?|scope|specs?|must have|the (?:site|app|script|file) "
        r"(?:should|must)|attached|here is what|steps?:|"
        # pt-BR
        r"requisitos|escopo|entreg[áa]vel|em anexo|segue o que)", re.I), 6),
    ("preuve de sérieux", re.compile(
        r"\b(escrow|milestone|contract|nda|invoice|paypal|wise|stripe|upfront|deposit|"
        # pt-BR
        r"pix|nota fiscal|mercado pago|adiantamento|metade adiantado)\b", re.I), 8),
]

# Negative signals: things that make a post worthless however loud it is.
NEGATIVE = [
    ("vend ses services", re.compile(
        r"\[\s*for ?hire\s*\]|\b(i am|i'm|im)\s+(?:a|an)\s+\w+\s+(?:developer|designer|writer|editor|"
        r"marketer|freelancer)\b|\b(my portfolio|hire me|available for (?:work|hire)|"
        r"offering my|my services|dm me for a quote)\b|"
        # pt-BR
        r"\b(?:sou|somos)\s+(?:um|uma)?\s*(?:desenvolvedor|designer|redator|editor|programador|"
        r"freelancer)\b|\b(?:meu portf[óo]lio|presto servi[çc]o|me chama pra or[çc]amento|"
        r"estou dispon[íi]vel para trabalhos?)\b", re.I), -60),
    ("non payé", re.compile(
        r"\b(unpaid|for free|no budget|equity only|revenue share|rev ?share|profit share|"
        r"exposure|portfolio piece|volunteer|non ?paid)\b|"
        # pt-BR
        r"\b(?:sem or[çc]amento|sem verba|permuta|divis[ãa]o de lucros|participa[çc][ãa]o nos lucros|"
        r"troca de divulga[çc][ãa]o|volunt[áa]ri[oa]|de gra[çc]a)\b", re.I), -45),
    ("arnaque probable", re.compile(
        r"\b(crypto wallet|send (?:me )?(?:your )?(?:wallet|seed phrase)|investment opportunity|"
        r"make \$\d+ (?:a|per) day|guaranteed profit|telegram only|wire transfer first)\b|"
        # pt-BR
        r"\b(?:ganhe r?\$? ?\d+ por dia|lucro garantido|renda extra garantida|s[óo] no telegram)\b",
        re.I), -40),
    ("poste salarié", re.compile(
        r"\b(full[- ]time (?:role|position|employee)|salary|benefits package|401k|"
        r"visa sponsorship|permanent position)\b|"
        # pt-BR
        r"\b(?:clt|carteira assinada|vaga efetiva|sal[áa]rio|vale refei[çc][ãa]o|benef[íi]cios)\b",
        re.I), -12),
    ("concours / spéculatif", re.compile(
        r"\b(contest|competition entry|spec work|pitch for free|whoever does it best)\b", re.I), -25),
]

_VAGUE_MIN_CHARS = 80


def qualify(lead: Lead) -> Lead:
    """Fill in score, tier, category, budget, deadline and contact on the lead."""
    text = lead.text
    signals: list[Signal] = []
    penalties: list[Signal] = []
    total = 0.0

    for name, pattern, points in POSITIVE:
        if pattern is None:
            continue
        match = pattern.search(text)
        if match:
            total += points
            signals.append(Signal(name, points, match.group(0)))

    # money on the page
    budget = extract_budget(text)
    if budget:
        lead.budget = budget.to_dict()
        points = 18.0
        # A stated budget under the cheapest playbook floor is a signal too -
        # just not a good one.
        if budget.per == "project" and budget.usd_high < 30:
            points = -10.0
        elif budget.per == "hour" and budget.usd_low < 8:
            points = -10.0
        (signals if points > 0 else penalties).append(
            Signal("montant chiffré" if points > 0 else "budget trop bas", points, budget.describe())
        )
        total += points

    # urgency
    deadline = extract_deadline(text)
    if deadline:
        lead.deadline = deadline.to_dict()
        points = 10.0 * deadline.urgency
        total += points
        signals.append(Signal("urgence", points, deadline.raw))

    # how to answer
    contact, address = extract_contact(text)
    lead.contact, lead.contact_address = contact, address
    if contact != "reply on the post":
        total += 6
        signals.append(Signal("chemin de réponse", 6, contact))

    # do we sell this?
    classification = classify(text)
    confident = classification.confident
    lead.category = classification.playbook.key if confident else "other"
    lead.category_label = classification.playbook.label if confident else OTHER.label
    catalogue_delta = 12 if confident else -10
    total += catalogue_delta
    if confident:
        signals.append(Signal("catalogue", 12, "+".join(classification.hits[:3])))
    else:
        penalties.append(Signal("hors catalogue", -10, "aucun mot-clé métier"))

    # freshness
    age = lead.age_hours
    if age is not None:
        if age <= 2:
            points, label = 12.0, "moins de 2h"
        elif age <= 6:
            points, label = 8.0, "moins de 6h"
        elif age <= 24:
            points, label = 4.0, "moins de 24h"
        elif age <= 72:
            points, label = 0.0, "2-3 jours"
        else:
            points, label = -12.0, "plus de 3 jours"
        total += points
        if points:
            (signals if points > 0 else penalties).append(Signal("fraîcheur", points, label))

    # crowding: an offer that arrives 40th is not an offer
    replies = _int(lead.extra.get("num_comments"))
    if replies is not None and replies >= 15:
        total -= 8
        penalties.append(Signal("déjà saturée", -8, f"{replies} réponses"))

    # too short to answer seriously
    if len(text) < _VAGUE_MIN_CHARS:
        total -= 10
        penalties.append(Signal("trop vague", -10, f"{len(text)} caractères"))

    for name, pattern, points in NEGATIVE:
        match = pattern.search(text)
        if match:
            total += points
            penalties.append(Signal(name, points, match.group(0)))

    lead.score = int(max(0, min(100, round(total * SCALE))))
    lead.demand_score = int(max(0, min(100, round((total - catalogue_delta) * SCALE))))
    lead.tier = "HOT" if lead.score >= HOT else "WARM" if lead.score >= WARM else "IGNORE"
    lead.signals = [s.to_dict() for s in signals]
    lead.penalties = [p.to_dict() for p in penalties]
    return lead


def _int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def explain(lead: Lead) -> str:
    """The score, broken down. Never trust a number you cannot audit."""
    lines = [f"score {lead.score}/100 -> {lead.tier}"]
    for item in lead.signals:
        lines.append(f"  +{item['points']:>5} {item['name']:<20} « {item['evidence']} »")
    for item in lead.penalties:
        lines.append(f"  {item['points']:>6} {item['name']:<20} « {item['evidence']} »")
    return "\n".join(lines)
