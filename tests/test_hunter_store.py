"""The store owns the boundary between machine output and human decisions."""

import json
import time

import pytest

from hunter.intent import qualify
from hunter.lead import Lead
from hunter.offer import prepare
from hunter.report import market_table, render_html, render_market, render_run
from hunter.store import Store


def lead(title="[HIRING] need a scraper, budget $400", body="products into a csv", ident="1"):
    return prepare(qualify(Lead("test", ident, title, body, created_utc=time.time() - 3600)))


def test_a_lead_keeps_the_same_id_across_runs(tmp_path):
    first, second = lead(), lead()
    assert first.fingerprint == second.fingerprint


def test_upsert_adds_then_updates(tmp_path):
    store = Store(str(tmp_path))
    assert store.upsert([lead()]).added == 1
    assert store.upsert([lead()]).updated == 1
    assert len(store.all()) == 1


def test_a_human_status_survives_the_next_hunt(tmp_path):
    store = Store(str(tmp_path))
    store.upsert([lead()])
    store.save()
    fingerprint = store.all()[0].fingerprint
    store.mark(fingerprint, "sent", "envoyé en DM")

    store.upsert([lead()])
    kept = store.get(fingerprint)
    assert kept.status == "sent"
    assert kept.notes and kept.notes[-1]["note"] == "envoyé en DM"


def test_an_edited_draft_is_not_overwritten_once_the_lead_is_touched(tmp_path):
    store = Store(str(tmp_path))
    store.upsert([lead()])
    fingerprint = store.all()[0].fingerprint
    store.get(fingerprint).draft = "ma version à moi"
    store.mark(fingerprint, "drafted")

    store.upsert([lead()])
    assert store.get(fingerprint).draft == "ma version à moi"


def test_state_survives_a_restart(tmp_path):
    store = Store(str(tmp_path))
    store.upsert([lead()])
    store.save()
    assert len(Store(str(tmp_path)).all()) == 1


def test_a_broken_line_does_not_take_down_the_file(tmp_path):
    store = Store(str(tmp_path))
    store.upsert([lead()])
    store.save()
    with (tmp_path / "leads.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{ceci n'est pas du json\n")
    assert len(Store(str(tmp_path)).all()) == 1


def test_ids_can_be_typed_short(tmp_path):
    store = Store(str(tmp_path))
    store.upsert([lead()])
    fingerprint = store.all()[0].fingerprint
    assert store.get(fingerprint[:5]) is not None
    assert store.get("zzzzz") is None


def test_an_unknown_status_is_refused(tmp_path):
    store = Store(str(tmp_path))
    store.upsert([lead()])
    with pytest.raises(ValueError):
        store.mark(store.all()[0].fingerprint, "peut-etre")


def test_the_funnel_counts_what_actually_happened(tmp_path):
    store = Store(str(tmp_path))
    store.upsert([lead(ident=str(i)) for i in range(4)])
    store.save()
    ids = [row.fingerprint for row in store.all()]
    store.mark(ids[0], "sent")
    store.mark(ids[1], "won", "il voulait juste le CSV, livré en 3h")
    funnel = store.funnel()
    assert funnel["sent"] == 2 and funnel["counts"]["won"] == 1
    assert funnel["win_rate"] == 50.0
    assert store.wins()[0].notes[-1]["note"].startswith("il voulait")


def test_the_run_journal_records_source_failures(tmp_path):
    from hunter.sources import SourceStatus
    from hunter.store import UpsertReport

    store = Store(str(tmp_path))
    store.record_run([SourceStatus("reddit/forhire", False, 0, "HTTP 429")], UpsertReport(0, 0, 0))
    assert store.last_run()["sources"][0]["detail"] == "HTTP 429"


def test_market_table_refuses_to_conclude_from_a_tiny_sample(tmp_path):
    leads = [qualify(Lead("test", str(i), "[HIRING] need a scraper, budget $400", "csv",
                          created_utc=time.time() - 3600)) for i in range(3)]
    rendered = render_market(market_table(leads))
    assert "échantillon trop petit" in rendered


def test_market_table_names_a_winner_once_the_sample_is_big_enough():
    leads = []
    for index in range(16):
        title = ("[HIRING] need a scraper, budget $400" if index % 2 == 0
                 else "[HIRING] need a video editor for shorts, budget $200")
        leads.append(qualify(Lead("test", str(index), title, "details here for the job",
                                  created_utc=time.time() - 3600)))
    table = market_table(leads)
    assert table["rows"][0]["count"] >= table["rows"][-1]["count"]
    assert "marché te dit de vendre" in render_market(table) or "égalité" in render_market(table)


def test_reports_render_without_crashing_on_an_empty_run(tmp_path):
    store = Store(str(tmp_path))
    assert "0 posts lus" in render_run([], [], 0, 0)
    assert render_html([], market_table([]), store.funnel())


def test_html_escapes_hostile_content(tmp_path):
    hostile = prepare(qualify(Lead(
        "test", "x", "[HIRING] <script>alert(1)</script> need a scraper, budget $400",
        "We need every product page scraped into a clean csv file with prices and skus.",
        created_utc=time.time() - 3600)))
    assert hostile.tier != "IGNORE"  # otherwise the card is not rendered at all
    page = render_html([hostile], market_table([hostile]), Store(str(tmp_path)).funnel())
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_the_dashboard_flags_synthetic_data_by_itself(tmp_path):
    from hunter.sources import fetch_demo

    demo = [prepare(qualify(row)) for row in fetch_demo().leads]
    page = render_html(demo, market_table(demo), Store(str(tmp_path)).funnel())
    assert "DEMO" in page and "synthetiques" in page.replace("é", "e")
    real = [lead()]
    assert "DEMO" not in render_html(real, market_table(real), Store(str(tmp_path)).funnel())


def test_a_budget_stuck_on_the_floor_is_named_as_such():
    from hunter.offer import suggest_price

    tight = qualify(Lead("test", "1", "[HIRING] fix my google sheet vlookup, $40",
                         "two tabs, formula breaks", created_utc=time.time() - 3600))
    _, note = suggest_price(tight)
    assert "plancher" in note


def test_a_lead_round_trips_through_json():
    original = lead()
    restored = Lead.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored.fingerprint == original.fingerprint
    assert restored.draft == original.draft
