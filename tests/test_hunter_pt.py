"""Brazilian Portuguese: a lead in pt-BR has to score, price and read like one."""

import time

import pytest

from hunter.intent import qualify
from hunter.lead import Lead
from hunter.offer import format_price, prepare, quote_currency, summarize_ask, wording
from hunter.playbook import BY_KEY, PLAYBOOKS, OTHER, classify
from hunter.i18n_pt import PT


def make(title, body="", hours_old=1.0):
    return qualify(Lead("brdev", title[:12], title, body,
                        created_utc=time.time() - hours_old * 3600))


def test_a_brazilian_request_scores_like_its_english_twin():
    br = make("Preciso de alguém para raspar 4000 páginas de produtos em um CSV",
              "Orçamento R$800, pago via Pix, urgente. Me chama no DM.")
    en = make("[HIRING] Need someone to scrape 4000 product pages into a CSV",
              "Budget $300, paying via PayPal, ASAP. DM me.")
    assert br.tier == en.tier == "HOT"
    assert abs(br.score - en.score) <= 10
    assert br.category == "scraping_data"


def test_a_brazilian_seller_is_still_not_a_buyer():
    lead = make("Sou desenvolvedor front-end, aceito freelas",
                "Meu portfólio está no perfil, me chama pra orçamento")
    assert lead.tier == "IGNORE" and lead.score == 0


def test_permuta_and_profit_sharing_are_unpaid_work():
    lead = make("Procuro designer para identidade visual",
                "Sem orçamento agora, permuta ou divisão de lucros")
    assert lead.tier == "IGNORE"


def test_a_clt_job_posting_is_not_a_freelance_lead():
    lead = make("Vaga CLT desenvolvedor Python", "Salário e benefícios, carteira assinada")
    assert lead.tier == "IGNORE"


def test_pix_counts_as_a_seriousness_signal():
    lead = make("Preciso de uma planilha que junte 3 relatórios",
                "Orçamento R$350, pago metade adiantado no Pix, essa semana")
    assert any("sérieux" in item["name"] for item in lead.signals)
    assert lead.deadline["days"] == 4.0


def test_the_ask_is_quoted_without_the_portuguese_asking_verb():
    lead = make("Preciso de alguém para raspar 4000 páginas - orçamento R$800")
    ask = summarize_ask(lead)
    assert ask.startswith("raspar")
    assert "R$" not in ask and "Preciso" not in ask


def test_a_real_is_quoted_in_reais_not_dollars():
    lead = prepare(make("Preciso de alguém para raspar 4000 páginas, orçamento R$800",
                        "produtos em um csv"), "pt")
    assert lead.price_display.startswith("R$")
    assert lead.price_display in lead.draft
    assert "$" in lead.price_note  # the operator still sees the USD equivalent


def test_with_no_stated_budget_the_currency_follows_the_language():
    lead = make("Procuro alguém para montar uma página de vendas", "lançamento mês que vem")
    assert quote_currency(lead, "pt") == "BRL"
    assert quote_currency(lead, "en") == "USD"
    assert format_price(100, "BRL").startswith("R$")


def test_the_whole_message_is_in_portuguese():
    lead = prepare(make("Preciso de alguém para raspar 4000 páginas, orçamento R$800",
                        "produtos em um csv"), "pt")
    assert "Olá" in lead.draft and "O que você recebe" in lead.draft
    # no English scope bullet leaked through
    assert "What you get" not in lead.draft
    for bullet in BY_KEY["scraping_data"].scope:
        assert bullet not in lead.draft


@pytest.mark.parametrize("text,expected", [
    ("preciso de alguém para raspar um site e gerar um csv", "scraping_data"),
    ("procuro editor de vídeo para cortes para reels", "video"),
    ("quero automatizar meu processo com n8n", "automation"),
    ("arrumar minha planilha do excel, fórmula quebrada", "spreadsheet"),
    ("preciso de um chatbot no site da empresa", "ai_agent"),
])
def test_the_classifier_reads_portuguese(text, expected):
    classification = classify(text)
    assert classification.confident and classification.playbook.key == expected


def test_every_playbook_has_a_portuguese_version():
    for book in list(PLAYBOOKS) + [OTHER]:
        translated = PT[book.key]
        assert len(translated["scope"]) == 3
        assert translated["proof"] and translated["question"][-1] in "?."
        assert wording(book, "pt")[0] != book.scope
