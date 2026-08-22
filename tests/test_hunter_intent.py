"""Scoring: the part that decides what a human looks at, so it gets tested hard."""

import time

import pytest

from hunter.intent import HOT, WARM, qualify
from hunter.lead import Lead
from hunter.playbook import classify


def make(title, body="", hours_old=1.0, comments=0):
    return Lead("test", title[:12], title, body,
                created_utc=time.time() - hours_old * 3600,
                extra={"num_comments": comments})


def test_a_paid_urgent_in_catalogue_request_is_hot():
    lead = qualify(make(
        "[HIRING] Need someone to scrape 4000 product pages into a CSV - budget $300-500",
        "Three competitor sites, columns name/price/sku. Paying via PayPal. Need it ASAP, DM me."))
    assert lead.tier == "HOT" and lead.score >= HOT
    assert lead.category == "scraping_data"
    assert lead.budget["usd_high"] == 500


def test_someone_selling_their_services_is_never_a_lead():
    lead = qualify(make("[FOR HIRE] Senior React developer available, $45/hr",
                        "My portfolio is in my profile. DM me for a quote."))
    assert lead.tier == "IGNORE" and lead.score == 0


def test_unpaid_work_is_rejected_however_well_written():
    lead = qualify(make("Looking for a designer to build our brand identity",
                        "Equity only for now, but it is a great portfolio piece and huge exposure."))
    assert lead.tier == "IGNORE"


def test_obvious_scams_are_rejected():
    lead = qualify(make("Make $500 a day with this simple system - telegram only",
                        "Send me your crypto wallet and I show you the method. Guaranteed profit."))
    assert lead.tier == "IGNORE"


def test_a_stale_request_loses_to_an_identical_fresh_one():
    fresh = qualify(make("[HIRING] Need a landing page built, budget $400", "launching soon", 0.5))
    stale = qualify(make("[HIRING] Need a landing page built, budget $400", "launching soon", 200))
    assert fresh.score > stale.score


def test_a_crowded_post_is_worth_less():
    quiet = qualify(make("[HIRING] Need a landing page, budget $400", "soon", 2, comments=1))
    crowded = qualify(make("[HIRING] Need a landing page, budget $400", "soon", 2, comments=40))
    assert quiet.score > crowded.score


def test_two_words_are_not_a_lead():
    assert qualify(make("need help", "asap")).tier == "IGNORE"


def test_a_real_request_without_a_price_still_gets_looked_at():
    lead = qualify(make("Looking for someone to build a landing page for my SaaS",
                        "We launch next month and I can pay. Show me something you built."))
    assert lead.tier == "WARM" and WARM <= lead.score < HOT


def test_a_budget_below_any_floor_is_penalised():
    poor = qualify(make("[HIRING] need a full website, budget $12", "wordpress, urgent"))
    assert any("trop bas" in item["name"] for item in poor.penalties)


def test_the_score_is_bounded_and_auditable():
    lead = qualify(make("[HIRING] Need someone to automate invoices with n8n, budget $1200",
                        "Email ops@acme.io, needed this week. Escrow fine."))
    assert 0 <= lead.score <= 100
    assert sum(item["points"] for item in lead.signals) > 0
    assert all(item["evidence"] for item in lead.signals)


@pytest.mark.parametrize("text,expected", [
    ("need someone to scrape a website into a csv", "scraping_data"),
    ("looking for a video editor for youtube shorts", "video"),
    ("automate my invoices with zapier and google sheets", "automation"),
    ("want a chatbot on my docs site using gpt", "ai_agent"),
    ("pitch deck for our seed round", "deck"),
    ("someone to walk my dog twice a week", "other"),
])
def test_classifier_picks_the_playbook_the_post_actually_describes(text, expected):
    classification = classify(text)
    key = classification.playbook.key if classification.confident else "other"
    assert key == expected
