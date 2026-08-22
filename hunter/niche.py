"""Repeated demand nobody has standardised yet.

``market`` answers "which of my categories is most asked for". This answers a
harder and more valuable question: **what do people keep asking for that has no
obvious supplier?** That is where an unnoticed business hides - not in a
category that already has a thousand freelancers, but in the same specific
request appearing over and over, with money attached and almost no answers.

A cluster is ranked on four things it can actually measure:

    répétition   how many separate people asked for it
    argent       the median budget they attached to it
    rareté       how few people already answered those posts
    angle mort   how often it falls outside the existing catalogue

The last one is the point. A request our playbook already covers is a job. A
request that keeps coming back and that nothing in the catalogue covers is a
product waiting to be built.

This is a counting tool, not a prophecy. Under ``MIN_SAMPLE`` qualified posts it
refuses to name anything, because three coincidences look exactly like a trend.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Iterable, Optional

from .lead import Lead

MIN_SAMPLE = 25      # qualified posts before any conclusion is allowed
MIN_COUNT = 3        # separate posts before a term is a cluster
# Deliberately lower than the answering threshold (WARM = 45): a pattern is
# built out of many weak signals, not one strong one. A terse "[HIRING] answer
# our instagram dms, $180" is thin on its own and decisive when it is the third
# one this week. Junk still cannot get in - sellers, unpaid work and two-line
# posts score in the low tens.
MIN_DEMAND = 35

_STOP = set("""
about after again all also and any are back because been before being both but can come could
did does doing done down each even every for from get gets give going good got had has have
here how into its just know like look looking made make making many more most much must need
needs new now off only other our out over own please put right same see should show since some
still such take than that the their them then there these they thing think this those through
time under until very want was way well were what when where which while who why will with
without work working would you your yours yourself into someone somebody anyone able help
project projects task tasks job jobs hire hiring freelancer freelance remote budget price paid
pay paying urgent asap week weeks day days month months hour hours experience please thanks
thank hello hey guys looking send message dm pm email contact interested details detail
com www http https reddit post posts comment comments
seeking seek wanted want someone need needed needs looking hire hiring help wanted urgent
automatically automatic simple small quick easy per day daily weekly monthly ongoing long
term one two three four five six ten via etc lot lots really actually basically
today tomorrow tonight yesterday morning evening night stuff things people someone something
""".split())

_STOP |= set("""
para com uma como mais mas dos das nos nas pelo pela por que quem qual quais isso este esta
esse essa aquele aquela sobre entre sem ser sou sao são está estou estamos tem tenho temos
preciso procuro quero fazer feito faz fazendo alguem alguém alguma algum tudo todo toda todos
todas muito muita pouco pouca aqui ali agora hoje amanha amanhã semana mes mês dia dias hora
horas valor orcamento orçamento pago pagar pagamento urgente projeto trabalho vaga freela
mensagem chama manda obrigado obrigada gente pessoal preco preço
automaticamente automatico automático sozinho sozinha simples rapido rápido facil fácil
gostaria queria seria bom bem pra pro dos das duas dois tres três uns umas cada toda todo
""".split())

# 3 characters minimum: "dms", "csv", "seo" and "bot" are exactly the words a
# niche hides behind.
_TOKEN = re.compile(r"[a-zà-öø-ÿ][a-zà-öø-ÿ0-9'-]{2,}", re.I)


@dataclass
class Cluster:
    term: str
    leads: list = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.leads)

    @property
    def hot(self) -> int:
        return sum(1 for lead in self.leads if lead.tier == "HOT")

    @property
    def budgets(self) -> list[float]:
        return [lead.budget["usd_high"] for lead in self.leads
                if lead.budget and lead.budget.get("per") == "project"]

    @property
    def median_budget(self) -> Optional[float]:
        values = self.budgets
        return round(median(values)) if values else None

    @property
    def median_replies(self) -> Optional[float]:
        values = [lead.extra.get("num_comments") for lead in self.leads
                  if isinstance(lead.extra.get("num_comments"), (int, float))]
        return median(values) if values else None

    @property
    def blind_spot(self) -> float:
        """Share of the cluster the current catalogue does not cover."""
        return sum(1 for lead in self.leads if lead.category == "other") / self.count

    @property
    def score(self) -> int:
        """0-100. The weights encode four judgements, all arguable, all explicit.

        Repetition dominates (0.35): a niche is something that comes back.
        Money is capped at $400 (0.15) so one $3k outlier cannot crown a term.
        Scarcity (0.15) prefers posts nobody answered yet.
        Blind spot (0.15) rewards demand the catalogue does not cover.
        Specificity (0.20) is the tiebreaker that matters: "instagram dms" names
        a business, "questions" names a topic you cannot sell.
        """
        repetition = min(self.count, 10) / 10
        budget = self.median_budget
        money = min(budget, 400) / 400 if budget else 0.15
        replies = self.median_replies
        scarcity = 1 / (1 + (replies or 0) / 5)
        novelty = 0.5 + 0.5 * self.blind_spot
        specificity = 1.0 if " " in self.term else 0.3
        return int(round(100 * (0.35 * repetition + 0.15 * money + 0.15 * scarcity +
                                0.15 * novelty + 0.20 * specificity)))

    def to_dict(self) -> dict:
        return {"term": self.term, "count": self.count, "hot": self.hot,
                "median_budget": self.median_budget, "median_replies": self.median_replies,
                "blind_spot": round(self.blind_spot, 2), "score": self.score,
                "examples": [lead.title[:90] for lead in self.leads[:3]],
                "ids": [lead.fingerprint for lead in self.leads[:5]]}


def _terms(lead: Lead) -> set[str]:
    """Words and adjacent pairs worth counting, from the part people write first."""
    text = f"{lead.title} {lead.body[:300]}".lower()
    words = [word for word in _TOKEN.findall(text) if word not in _STOP]
    terms = set(words)
    terms |= {f"{first} {second}" for first, second in zip(words, words[1:])}
    return terms


def clusters(leads: Iterable[Lead], days: float = 14.0,
             min_count: int = MIN_COUNT) -> tuple[list[Cluster], int]:
    """(ranked clusters, number of qualified posts analysed)."""
    import time

    cutoff = time.time() - days * 86400
    rows = [lead for lead in leads
            if (lead.demand_score or lead.score) >= MIN_DEMAND
            and (not lead.created_utc or lead.created_utc >= cutoff)]

    buckets: dict[str, list[Lead]] = defaultdict(list)
    for lead in rows:
        for term in _terms(lead):
            buckets[term].append(lead)

    kept = {term: group for term, group in buckets.items() if len(group) >= min_count}

    # Pairs carry the meaning. "questions" is a word everybody uses; "instagram
    # dms" is a business. So a pair always wins over the words inside it, and a
    # lone word has to clear a higher bar to be counted as a signal at all.
    pairs = [term for term in kept if " " in term]
    inside_a_pair = {word for pair in pairs for word in pair.split()}
    for word in [term for term in kept if " " not in term]:
        if word in inside_a_pair:
            kept.pop(word, None)

    ranked = [Cluster(term, group) for term, group in kept.items()]
    ranked.sort(key=lambda cluster: (-cluster.score, -cluster.count))
    return ranked, len(rows)


BAR = "=" * 78


def render(ranked: list[Cluster], analysed: int, days: float, show: int = 8) -> str:
    lines = [BAR,
             f"DEMANDE RÉPÉTÉE QUE PERSONNE NE SERT  -  {analysed} demandes qualifiées "
             f"sur {days:.0f} jours",
             BAR]
    if analysed < MIN_SAMPLE:
        lines += [f"  Pas encore de quoi conclure : {analysed} demandes analysées, il en faut "
                  f"au moins {MIN_SAMPLE}.",
                  "  Trois coïncidences ressemblent exactement à une tendance — c'est comme ça",
                  "  qu'on invente un marché qui n'existe pas.",
                  "",
                  f"  Lance encore quelques chasses ({MIN_SAMPLE - analysed} demandes qualifiées "
                  "à trouver), puis reviens ici."]
        return "\n".join(lines)
    if not ranked:
        lines.append("  Aucune demande ne revient au moins 3 fois. Rien à standardiser pour "
                     "l'instant.")
        return "\n".join(lines)

    for index, cluster in enumerate(ranked[:show], 1):
        budget = f"${cluster.median_budget:,}" if cluster.median_budget else "n/c"
        replies = f"{cluster.median_replies:.0f}" if cluster.median_replies is not None else "?"
        lines += ["",
                  f"  {index}. « {cluster.term} »   score {cluster.score}/100",
                  f"     {cluster.count} demandes ({cluster.hot} chaudes) · budget médian {budget}"
                  f" · {replies} réponses par annonce"
                  f" · {cluster.blind_spot * 100:.0f} % hors catalogue"]
        for lead in cluster.leads[:3]:
            lines.append(f"       {lead.fingerprint}  {lead.title[:60]}")

    top = ranked[0]
    lines += ["", "  CE QUE ÇA VEUT DIRE"]
    if top.blind_spot >= 0.5:
        lines.append(f"  « {top.term} » revient {top.count} fois et ton catalogue ne le couvre pas.")
        lines.append("  C'est l'angle mort : écris l'offre standardisée, puis reprends ces "
                     f"{top.count} annonces une par une.")
    else:
        lines.append(f"  « {top.term} » revient {top.count} fois et rentre déjà dans ton catalogue.")
        lines.append("  Ce n'est pas un angle mort, c'est ta prochaine offre à répéter telle quelle.")
    if (top.median_replies or 0) <= 3:
        lines.append(f"  Peu de réponses par annonce ({top.median_replies:.0f} en médiane) : "
                     "tu n'arrives pas 40e.")
    lines += ["  Ne construis rien tant qu'une de ces annonces n'a pas payé.",
              "",
              "  python -m hunter draft <id>   pour attaquer une de ces annonces"]
    return "\n".join(lines)
