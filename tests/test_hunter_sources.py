"""Connectors and CLI, exercised without touching the network."""

import json
import urllib.error

import pytest

from hunter import cli, sources


REDDIT_PAYLOAD = json.dumps({"data": {"children": [
    {"data": {"id": "abc123", "title": "[HIRING] need a scraper, budget $400",
              "selftext": "products into a csv, ASAP", "permalink": "/r/forhire/comments/abc123/x/",
              "author": "someone", "created_utc": 1_755_000_000, "num_comments": 3}},
    {"data": {}},
]}}).encode()

HN_PAYLOAD = json.dumps({"hits": [
    {"objectID": "42", "comment_text": "SEEKING FREELANCER | remote | need an n8n flow, $1200",
     "story_title": "Ask HN: Freelancer? Seeking freelancer?", "author": "hn_user",
     "created_at_i": 1_755_000_000},
    {"objectID": "43", "comment_text": ""},
]}).encode()

RSS_PAYLOAD = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Need a landing page built</title><link>https://example.invalid/1</link>
<description>&lt;p&gt;budget $400&lt;/p&gt;</description>
<pubDate>Mon, 22 Aug 2026 10:00:00 +0000</pubDate><guid>ex-1</guid></item>
</channel></rss>"""


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(sources.time, "sleep", lambda *_: None)


def test_reddit_posts_become_leads(monkeypatch):
    monkeypatch.setattr(sources, "_get", lambda *a, **k: REDDIT_PAYLOAD)
    result = sources.fetch_reddit(["forhire"], rate=0)
    assert len(result.leads) == 1
    lead = result.leads[0]
    assert lead.source == "reddit/forhire"
    assert lead.url.endswith("/r/forhire/comments/abc123/x/")
    assert lead.extra["num_comments"] == 3
    assert result.statuses[0].ok


def test_a_dead_source_is_a_status_line_not_a_crash(monkeypatch):
    def boom(*_a, **_k):
        raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(sources, "_get", boom)
    result = sources.fetch_reddit(["forhire"], rate=0)
    assert result.leads == []
    assert not result.statuses[0].ok
    assert "429" in result.statuses[0].detail


def test_one_source_failing_does_not_cost_the_others(monkeypatch):
    calls = {"n": 0}

    def flaky(url, *a, **k):
        calls["n"] += 1
        if "reddit" in url:
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        return HN_PAYLOAD

    monkeypatch.setattr(sources, "_get", flaky)
    config = sources.load_config(None)
    config["remoteok"]["enabled"] = False
    config["reddit"]["subreddits"] = ["forhire"]
    config["hn"]["queries"] = ["SEEKING FREELANCER"]
    result = sources.run_sources(config, rate=0)
    assert any(status.ok for status in result.statuses)
    assert any(not status.ok for status in result.statuses)
    assert result.leads  # the HN ones survived


def test_empty_hn_comments_are_dropped(monkeypatch):
    monkeypatch.setattr(sources, "_get", lambda *a, **k: HN_PAYLOAD)
    result = sources.fetch_hn(["SEEKING FREELANCER"], rate=0)
    assert len(result.leads) == 1
    assert result.leads[0].url == "https://news.ycombinator.com/item?id=42"


def test_any_rss_feed_can_be_added_without_code(monkeypatch):
    monkeypatch.setattr(sources, "_get", lambda *a, **k: RSS_PAYLOAD)
    result = sources.fetch_rss(["https://example.invalid/feed.rss"], rate=0)
    lead = result.leads[0]
    assert lead.title == "Need a landing page built"
    assert "budget $400" in lead.body
    assert lead.created_utc == 1_787_392_800.0


def test_only_selected_sources_run(monkeypatch):
    monkeypatch.setattr(sources, "_get", lambda *a, **k: HN_PAYLOAD)
    result = sources.run_sources(sources.load_config(None), only=["hn"], rate=0)
    assert all(status.name.startswith("hn") for status in result.statuses)


def test_config_file_overrides_defaults(tmp_path):
    path = tmp_path / "hunter.json"
    path.write_text(json.dumps({"reddit": {"subreddits": ["forhire"]},
                                "hn": {"enabled": False}}), encoding="utf-8")
    config = sources.load_config(str(path))
    assert config["reddit"]["subreddits"] == ["forhire"]
    assert config["reddit"]["enabled"] is True   # untouched keys survive
    assert config["hn"]["enabled"] is False


def test_demo_fixtures_are_labelled_synthetic():
    result = sources.fetch_demo()
    assert len(result.leads) > 10
    assert all(lead.extra["synthetic"] for lead in result.leads)
    assert "synth" in result.statuses[0].name


@pytest.mark.parametrize("value,expected", [
    ("Mon, 22 Aug 2026 10:00:00 +0000", 1_787_392_800.0),
    ("2026-08-22T10:00:00Z", 1_787_392_800.0),
    (1_755_000_000, 1_755_000_000.0),
    ("pas une date", 0.0),
    (None, 0.0),
])
def test_timestamps_are_parsed_from_every_format_sources_use(value, expected):
    assert sources._epoch(value) == expected


# ----------------------------------------------------------------------
# CLI, end to end on the offline fixtures
# ----------------------------------------------------------------------
def test_the_whole_pipeline_runs_offline(tmp_path, capsys):
    work = str(tmp_path)
    assert cli.main(["--workdir", work, "hunt", "--demo",
                     "--html", str(tmp_path / "d.html")]) == 0
    out = capsys.readouterr().out
    assert "HOT" in out and "CE QUE LE MARCHÉ DEMANDE" in out
    assert (tmp_path / "leads.jsonl").exists()
    assert (tmp_path / "d.html").read_text(encoding="utf-8").startswith("<title>")

    assert cli.main(["--workdir", work, "list", "--tier", "HOT"]) == 0
    identifier = capsys.readouterr().out.splitlines()[1].split()[0]

    assert cli.main(["--workdir", work, "draft", identifier]) == 0
    sheet = capsys.readouterr().out
    assert "POURQUOI CE SCORE" in sheet and "MESSAGE" in sheet

    assert cli.main(["--workdir", work, "mark", identifier, "sent", "-n", "envoyé en DM"]) == 0
    capsys.readouterr()
    assert cli.main(["--workdir", work, "pipeline"]) == 0
    assert "envoyés        1" in capsys.readouterr().out

    assert cli.main(["--workdir", work, "sources"]) == 0
    assert "synth" in capsys.readouterr().out


def test_an_unknown_id_fails_loudly(tmp_path, capsys):
    assert cli.main(["--workdir", str(tmp_path), "draft", "nope"]) == 1
    assert "aucun lead" in capsys.readouterr().out


def test_hunting_twice_does_not_duplicate_leads(tmp_path, capsys):
    work = str(tmp_path)
    cli.main(["--workdir", work, "hunt", "--demo"])
    cli.main(["--workdir", work, "hunt", "--demo"])
    capsys.readouterr()
    cli.main(["--workdir", work, "list", "--limit", "100"])
    rows = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(rows) - 1 == len(sources.fetch_demo().leads)
