"""What we can actually deliver, and what it is worth.

A category is not a label for a report. It is a promise: a fixed scope, a
delivery time, and a price floor under which the job is not worth taking. The
classifier reads the post and picks the playbook; the offer engine reads the
playbook and writes the price.

Two rules keep this honest:

1. Only categories a single person can deliver in a few days, with AI doing the
   grunt work, are listed here. "Build my marketplace" is not on the list.
2. ``floor_usd`` is a walk-away number, not an opening price. Below it the job
   costs more in messages than it pays.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Playbook:
    key: str
    label: str            # shown in reports (French: the operator reads it)
    phrases: tuple[str, ...]   # multi-word, worth 3 points each
    words: tuple[str, ...]     # single tokens, worth 1 point each
    floor_usd: float
    target_usd: float
    hours: float          # realistic hands-on hours, used for hourly quotes
    days: int             # promised delivery, calendar days
    scope: tuple[str, ...]     # what the first message promises, exactly
    proof: str            # the free sample that gets a reply
    question: str         # the one qualifying question to ask back


PLAYBOOKS: tuple[Playbook, ...] = (
    Playbook(
        key="automation",
        label="Automatisation / intégration",
        # "google sheets" alone is not automation - it is where half the world
        # keeps its data. The verbs and the tools carry the signal.
        phrases=("automate", "automation", "zapier", "make.com", "n8n",
                 "connect my", "sync data", "workflow", "airtable",
                 "no code", "nocode", "integrate with", "api integration",
                 # pt-BR
                 "automatizar", "automação", "integrar com",
                 "fluxo automático", "sem código"),
        words=("integration", "webhook", "crm", "hubspot", "notion", "sheets", "automatize",
               "automatização", "integração"),
        floor_usd=80, target_usd=250, hours=6, days=2,
        scope=("map the current manual steps into one automated flow",
               "build and connect it end to end (form -> logic -> destination -> notification)",
               "hand over a 3-minute Loom + the flow, running in your own account"),
        proof="a one-screen diagram of the exact flow, so you see what you are buying",
        question="Which tools does the data have to land in, and who needs to be notified?",
    ),
    Playbook(
        key="ai_agent",
        label="Agent IA / chatbot",
        phrases=("ai agent", "chat bot", "chatbot", "gpt", "openai", "llm", "rag",
                 "ai assistant", "langchain", "claude api", "fine tune", "prompt engineer",
                 # pt-BR
                 "agente de ia", "assistente virtual", "chatbot no site", "inteligência artificial"),
        words=("ai", "bot", "assistant", "embeddings", "vector"),
        floor_usd=120, target_usd=350, hours=8, days=3,
        scope=("define the exact questions the agent must answer and the ones it must refuse",
               "build it on your data with a tested prompt + guardrails",
               "deploy where your users already are (site widget, WhatsApp, Slack) with a usage log"),
        proof="the agent answering three of your real questions, in a screen recording",
        question="What are the three questions your customers ask most, word for word?",
    ),
    Playbook(
        key="scraping_data",
        label="Scraping / listes de données",
        phrases=("web scraping", "scrape", "scraper", "data extraction", "lead list",
                 "email list", "crawl", "extract data", "collect data", "build a list",
                 "data entry", "csv file",
                 # pt-BR
                 "raspagem", "raspar", "extrair dados", "coleta de dados", "lista de leads"),
        words=("scraping", "dataset", "csv", "database", "listing", "directory",
               "raspagem"),
        floor_usd=60, target_usd=180, hours=5, days=2,
        scope=("agree the exact columns and the source pages",
               "run the extraction with deduplication and a validity check on every row",
               "deliver a clean CSV/Sheet + the script, so you can re-run it yourself"),
        proof="the first 20 rows, so you can check the quality yourself",
        question="Which columns do you actually use once the file lands on your desk?",
    ),
    Playbook(
        key="landing_page",
        label="Landing page",
        phrases=("landing page", "one page site", "squeeze page", "sales page",
                 "webflow", "framer", "carrd", "web page",
                 # pt-BR
                 "página de vendas", "página de captura", "site de uma página"),
        words=("landing", "website", "site", "webpage", "homepage",
               "landing"),
        floor_usd=90, target_usd=250, hours=7, days=3,
        scope=("one page written around a single action (the copy is included, not extra)",
               "responsive build, live on your domain, loading under 2 seconds",
               "form/analytics wired up so you can see whether it converts"),
        proof="the headline and the above-the-fold section, drafted first",
        question="What is the single action a visitor must take on that page?",
    ),
    Playbook(
        key="web_dev",
        label="Dev web / correctif",
        phrases=("bug fix", "fix my site", "fix my app", "fix my code", "fix my script",
                 "react app", "next js", "nextjs", "front end",
                 "backend", "shopify", "wordpress site", "wordpress plugin", "site migration",
                 "api endpoint", "python script",
                 # pt-BR
                 "corrigir um bug", "meu site quebrou", "erro no site", "desenvolvedor para"),
        words=("react", "javascript", "typescript", "django", "flask", "php", "sql", "script",
               "wordpress", "hosting", "migration",
               "desenvolvedor", "programador"),
        floor_usd=100, target_usd=300, hours=8, days=3,
        scope=("reproduce the problem first, on your codebase, and show you the cause",
               "fix it with a test that fails before and passes after",
               "a pull request you can read, not a zip file"),
        proof="a written diagnosis of the likely cause, from the error you already have",
        question="Can you share the repo (or the error trace) so I confirm the cause before quoting?",
    ),
    Playbook(
        key="content",
        label="Rédaction / contenu",
        phrases=("blog post", "seo article", "copywriting", "write content", "ghostwrite",
                 "newsletter", "product description", "landing copy", "case study",
                 # pt-BR
                 "escrever artigos", "texto para blog", "redação de", "descrição de produto"),
        words=("writer", "writing", "article", "copy", "blog", "content", "editor",
               "redator", "redação", "artigos"),
        floor_usd=40, target_usd=120, hours=4, days=2,
        scope=("one piece, researched against your actual competitors, not a generic outline",
               "written in your voice from two samples you send me",
               "delivered in your CMS or as a clean doc, with the meta description"),
        proof="the outline plus the opening paragraph, free",
        question="Send me two pieces you like the voice of - who is the reader?",
    ),
    Playbook(
        key="video",
        label="Montage vidéo / shorts",
        phrases=("video editing", "video editor", "edit my video", "youtube shorts",
                 "tiktok video", "reels", "subtitles", "captions", "podcast clips",
                 # pt-BR
                 "edição de vídeo", "editor de vídeo", "cortes para reels", "legendas para"),
        words=("video", "editing", "shorts", "reels", "clips", "premiere", "capcut",
               "vídeo", "cortes"),
        floor_usd=50, target_usd=150, hours=5, days=2,
        scope=("cut for retention: cold open, no dead air, hook in the first 3 seconds",
               "burned-in captions, sound levelling, 2 aspect ratios (9:16 + 16:9)",
               "one round of revisions included"),
        proof="the first 15 seconds, edited",
        question="What is the one clip in your footage that must survive the cut?",
    ),
    Playbook(
        key="design",
        label="Design / visuels",
        phrases=("logo design", "ui design", "figma", "brand identity", "thumbnail",
                 "banner design", "social media graphics", "presentation design",
                 # pt-BR
                 "identidade visual", "criação de logo", "arte para", "design de"),
        words=("logo", "design", "designer", "graphic", "mockup", "branding",
               "logotipo", "arte"),
        floor_usd=50, target_usd=150, hours=5, days=2,
        scope=("three directions, not fifty variations of the same idea",
               "final files in every format you will need (svg, png, favicon)",
               "one revision round on the chosen direction"),
        proof="one rough direction, sketched",
        question="Name one brand whose look you want to be mistaken for.",
    ),
    Playbook(
        key="research",
        label="Recherche / veille",
        phrases=("market research", "competitor analysis", "find me", "compile a list",
                 "research report", "due diligence", "summarize", "literature review",
                 # pt-BR
                 "pesquisa de mercado", "análise de concorrentes", "levantamento de"),
        words=("research", "analysis", "report", "insights", "benchmark",
               "pesquisa", "levantamento"),
        floor_usd=50, target_usd=150, hours=5, days=2,
        scope=("a defined question with a defined answer format, agreed before I start",
               "sourced findings - every claim carries the link it came from",
               "a one-page decision summary on top of the raw findings"),
        proof="the source list I would use, sent up front",
        question="What decision are you going to make with this research?",
    ),
    Playbook(
        key="deck",
        label="Présentation / pitch deck",
        phrases=("pitch deck", "slide deck", "powerpoint", "google slides", "keynote",
                 "investor deck", "presentation for",
                 # pt-BR
                 "apresentação de slides", "slides para", "deck de investidores"),
        words=("deck", "slides", "presentation", "pptx",
               "apresentação", "slides"),
        floor_usd=60, target_usd=200, hours=5, days=2,
        scope=("story first: one message per slide, in the order an investor reads",
               "designed slides in your template, editable, not flattened images",
               "a speaker note under each slide"),
        proof="the slide-by-slide storyline, written out",
        question="Who is in the room when this deck is shown, and what do they decide?",
    ),
    Playbook(
        key="spreadsheet",
        label="Tableur / dashboard",
        phrases=("excel spreadsheet", "google sheet formula", "pivot table", "excel formula",
                 "financial model", "dashboard in", "clean up my data", "vlookup",
                 # pt-BR
                 "planilha do excel", "fórmula do excel", "tabela dinâmica", "arrumar minha planilha"),
        words=("excel", "spreadsheet", "formula", "macro", "vba", "dashboard",
               "planilha", "fórmula"),
        floor_usd=40, target_usd=120, hours=3, days=1,
        scope=("the calculation, working, on your real file",
               "no manual steps left: it updates when the data changes",
               "a short note explaining every formula, so you are not locked in"),
        proof="the formula solving your example row, in the reply itself",
        question="Can you send an anonymised copy of the file with 10 real rows?",
    ),
    Playbook(
        key="seo",
        label="SEO",
        phrases=("seo audit", "keyword research", "backlinks", "rank on google",
                 "technical seo", "google search console",
                 # pt-BR
                 "auditoria de seo", "palavras-chave", "aparecer no google"),
        words=("seo", "keywords", "serp", "ranking",
               "palavras-chave"),
        floor_usd=60, target_usd=180, hours=5, days=2,
        scope=("a crawl of the site with issues ranked by traffic impact, not by count",
               "the 20 keywords you can realistically win this quarter",
               "a fix list your developer can execute without me"),
        proof="the three biggest issues, found and sent first",
        question="Which page do you most want ranking, and for which search?",
    ),
)

BY_KEY = {p.key: p for p in PLAYBOOKS}

OTHER = Playbook(
    key="other",
    label="Autre / hors catalogue",
    phrases=(), words=(),
    floor_usd=60, target_usd=150, hours=5, days=3,
    scope=("scope agreed in writing before anything starts",
           "one deliverable, one deadline, one price",
           "a revision round included"),
    proof="a written plan of how I would do it",
    question="What does 'done' look like for you?",
)


@dataclass
class Classification:
    playbook: Playbook
    score: float
    hits: tuple[str, ...] = field(default_factory=tuple)

    @property
    def confident(self) -> bool:
        return self.score >= 3


# Word boundaries on every term, phrases included. Without them "garage"
# contains "rag" and a request to tidy a garage becomes an AI project.
_PATTERNS = {
    playbook.key: (
        tuple((term, re.compile(rf"\b{re.escape(term)}\b", re.I)) for term in playbook.phrases),
        tuple((term, re.compile(rf"\b{re.escape(term)}\b", re.I)) for term in playbook.words),
    )
    for playbook in PLAYBOOKS
}


def classify(text: str) -> Classification:
    """Pick the playbook whose vocabulary the post actually uses.

    Phrases outweigh single words on purpose: "video" alone appears in half the
    posts on the internet, "video editing" appears in the ones that pay for it.
    """
    haystack = text or ""
    best: Optional[Classification] = None
    for playbook in PLAYBOOKS:
        phrases, words = _PATTERNS[playbook.key]
        score = 0.0
        hits: list[str] = []
        for term, pattern in phrases:
            if pattern.search(haystack):
                score += 3
                hits.append(term)
        for term, pattern in words:
            if pattern.search(haystack):
                score += 1
                hits.append(term)
        if score and (best is None or score > best.score):
            best = Classification(playbook, score, tuple(hits[:6]))
    return best or Classification(OTHER, 0.0, ())
