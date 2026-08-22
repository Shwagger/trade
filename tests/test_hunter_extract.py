"""Budget, deadline and contact extraction: the facts that decide a lead."""

from hunter.extract import clean_text, extract_budget, extract_contact, extract_deadline


def test_reads_a_range_in_dollars():
    budget = extract_budget("landing page, budget $300-500, starts monday")
    assert (budget.low, budget.high, budget.currency, budget.per) == (300, 500, "USD", "project")


def test_reads_a_range_written_with_k():
    budget = extract_budget("we can go $2-5k for the right person")
    assert (budget.low, budget.high) == (2000, 5000)


def test_reads_a_currency_written_after_the_number():
    budget = extract_budget("paying 300 to 450 usd on delivery")
    assert (budget.low, budget.high, budget.currency) == (300, 450, "USD")


def test_converts_other_currencies_to_usd():
    budget = extract_budget("orçamento de R$800 para o scraper")
    assert budget.currency == "BRL"
    assert 140 < budget.usd_low < 170


def test_recognises_an_hourly_rate():
    budget = extract_budget("rate is $25 per hour, ongoing")
    assert budget.per == "hour" and budget.low == 25


def test_ignores_numbers_that_are_not_prices():
    assert extract_budget("we raised 2000000 in 2019 and have 50000 users") is None


def test_a_number_on_the_next_line_is_not_a_thousands_separator():
    # "$180.\n300 SKUs" used to parse as $180,300.
    budget = extract_budget("Paying $180 on delivery.\n300 SKUs need cleaning.")
    assert budget.high == 180


def test_no_money_means_no_budget():
    assert extract_budget("looking for someone to help with my site") is None


def test_asap_is_a_one_day_deadline():
    deadline = extract_deadline("need this ASAP please")
    assert deadline.days == 1.0 and deadline.urgency == 1.0


def test_keeps_the_earliest_deadline_mentioned():
    deadline = extract_deadline("ideally this week, next month at the very latest")
    assert deadline.days == 4.0


def test_reads_an_explicit_horizon():
    assert extract_deadline("within 3 days").days == 3.0


def test_finds_the_reply_channel_and_the_address():
    assert extract_contact("DM me with examples") == ("DM", None)
    assert extract_contact("email me at bob@acme.io")[1] == "bob@acme.io"


def test_defaults_to_answering_on_the_post():
    assert extract_contact("we need a scraper")[0] == "reply on the post"


def test_strips_html_from_a_feed_body():
    # </p> becomes a line break: paragraph structure survives, markup does not.
    assert clean_text("<p>need a <b>scraper</b></p>&amp; fast") == "need a scraper\n& fast"
