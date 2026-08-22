"""Pricing and drafting: what the human is about to put their name on."""

import time

from hunter.intent import qualify
from hunter.lead import Lead
from hunter.offer import draft_message, prepare, suggest_price, summarize_ask
from hunter.playbook import BY_KEY


def make(title, body=""):
    return qualify(Lead("test", "1", title, body, created_utc=time.time() - 3600))


def test_never_quotes_above_a_stated_budget():
    lead = make("[HIRING] scraper needed, budget $300-500", "csv of products")
    price, _ = suggest_price(lead)
    assert price <= lead.budget["usd_high"]


def test_quotes_the_catalogue_anchor_when_no_budget_is_stated():
    lead = make("[HIRING] need a landing page for my SaaS", "launching soon, I can pay")
    price, note = suggest_price(lead)
    assert price == BY_KEY["landing_page"].target_usd
    assert "ancrage" in note


def test_flags_a_budget_under_the_walk_away_floor():
    lead = make("[HIRING] need a full landing page, budget $25", "urgent")
    price, note = suggest_price(lead)
    assert price <= 25 and "plancher" in note


def test_turns_an_hourly_rate_into_a_fixed_price():
    lead = make("[HIRING] video editor wanted, $20 per hour", "youtube shorts, ongoing")
    price, note = suggest_price(lead)
    assert price == 100  # 20 $/h x 5 h in the video playbook
    assert "forfait" in note


def test_the_draft_carries_price_deadline_proof_and_a_question():
    lead = prepare(make("[HIRING] need a scraper, budget $400", "products into a csv, this week"))
    assert f"${lead.price_usd:,.0f}" in lead.draft
    assert "day" in lead.draft
    assert BY_KEY["scraping_data"].proof.split(",")[0] in lead.draft
    assert lead.draft.rstrip().endswith("I start today.")
    assert "?" in lead.draft


def test_the_draft_quotes_the_request_without_the_board_furniture():
    lead = make("[HIRING] Need someone to scrape 4,000 pages into a CSV - budget $300-500. DM me",
                "details")
    ask = summarize_ask(lead)
    assert "scrape 4,000 pages into a CSV" in ask
    assert "$" not in ask and "HIRING" not in ask and "DM" not in ask


def test_never_promises_faster_than_half_the_playbook_time():
    lead = make("[HIRING] need a landing page ASAP, budget $400", "urgent, today if possible")
    draft = draft_message(lead, 300, "en")
    assert "in 2 days" in draft  # landing page is a 3-day job: 2 is the floor


def test_every_language_produces_a_complete_message():
    lead = make("[HIRING] need a scraper, budget $400", "products into a csv")
    for lang in ("en", "fr", "pt"):
        draft = draft_message(lead, 300, lang)
        assert "300" in draft and len(draft.splitlines()) >= 8


def test_an_uncategorised_request_still_gets_a_usable_offer():
    lead = prepare(make("[HIRING] need someone to organise my garage, paying $200", "two hours"))
    assert lead.price_usd and lead.draft and lead.category == "other"


def test_no_playbook_repeats_the_payment_clause_the_template_already_writes():
    from hunter.offer import _TEMPLATES
    from hunter.playbook import OTHER, PLAYBOOKS

    for book in list(PLAYBOOKS) + [OTHER]:
        line = _TEMPLATES["en"]["proof"].format(proof=book.proof)
        assert line.lower().count("pay") == 1, f"{book.key}: {line}"
