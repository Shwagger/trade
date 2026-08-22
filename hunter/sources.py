"""Where the demand is, and how to read it without paying anyone.

Every connector here talks to a public, read-only endpoint that costs nothing
and needs no API key. They only ever GET. Nothing in this file posts, replies,
votes, follows or logs in - that is both the ethical line and the line that
keeps the accounts alive.

Rules every connector follows:

* one polite User-Agent, one request at a time, a configurable delay between
  calls (``--rate``, default 1.5 s);
* a failing source is a status line in the report, never an exception that
  kills the run - a Reddit outage must not cost you the HN leads;
* raw text in, :class:`Lead` out, no scoring (that is ``intent.py``'s job).

Adding a source without touching this file: put an RSS/Atom URL in
``config/hunter.json``. A Google Alerts feed for "need a freelancer to" is a
legitimate, free demand radar and plugs straight in.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

from .extract import clean_text
from .lead import Lead

USER_AGENT = "ai-demand-hunter/0.1 (personal freelance lead reader; contact: via GitHub)"
TIMEOUT = 20

DEFAULT_CONFIG = {
    "reddit": {
        "enabled": True,
        # Anglophones first (the volume), then the Brazilian ones. A subreddit
        # that does not exist shows up as one FAIL line in the report and costs
        # nothing else - delete the ones that never answer.
        "subreddits": ["forhire", "hiring", "slavelabour", "DoneDirtCheap",
                       "freelance_forhire", "jobbit",
                       "brdev", "empreendedorismo"],
        "limit": 100,
    },
    "hn": {
        "enabled": True,
        "queries": ["SEEKING FREELANCER", "looking for a freelancer", "need someone to build"],
        "limit": 60,
    },
    "remoteok": {"enabled": True, "contract_only": True},
    "rss": {
        "enabled": False,
        # Examples that work as-is; a Google Alerts feed URL fits here too.
        "feeds": ["https://weworkremotely.com/catégories/remote-programming-jobs.rss"],
    },
}


@dataclass
class SourceStatus:
    name: str
    ok: bool
    count: int = 0
    detail: str = ""


@dataclass
class FetchResult:
    leads: list = field(default_factory=list)
    statuses: list = field(default_factory=list)


# ----------------------------------------------------------------------
# http
# ----------------------------------------------------------------------
def _get(url: str, accept: str = "application/json") -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept,
                      "Accept-Language": "en-US,en;q=0.9"})
    last: Optional[Exception] = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            # 429/5xx are worth one more try; 403/404 are not.
            last = error
            if error.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, OSError) as error:
            last = error
        time.sleep(1.5 * (attempt + 1))
    raise last if last else RuntimeError("unreachable")


def _get_json(url: str):
    return json.loads(_get(url).decode("utf-8", "replace"))


# ----------------------------------------------------------------------
# reddit: the densest free source of "I will pay someone to do X"
# ----------------------------------------------------------------------
def fetch_reddit(subreddits: Iterable[str], limit: int = 100, rate: float = 1.5) -> FetchResult:
    result = FetchResult()
    for sub in subreddits:
        url = f"https://www.reddit.com/r/{sub}/new.json?limit={min(int(limit), 100)}"
        try:
            payload = _get_json(url)
            children = payload.get("data", {}).get("children", [])
            leads = [_reddit_lead(child.get("data", {}), sub) for child in children]
            leads = [lead for lead in leads if lead]
            result.leads.extend(leads)
            result.statuses.append(SourceStatus(f"reddit/{sub}", True, len(leads)))
        except Exception as error:  # noqa: BLE001 - one bad source must not stop the hunt
            result.statuses.append(SourceStatus(f"reddit/{sub}", False, 0, _why(error)))
        time.sleep(rate)
    return result


def _reddit_lead(data: dict, sub: str) -> Optional[Lead]:
    if not data.get("id"):
        return None
    return Lead(
        source=f"reddit/{sub}",
        source_id=str(data["id"]),
        title=clean_text(data.get("title", "")),
        body=clean_text(data.get("selftext", "")),
        url=f"https://www.reddit.com{data.get('permalink', '')}",
        author=str(data.get("author", "")),
        created_utc=float(data.get("created_utc") or 0),
        extra={"num_comments": data.get("num_comments"), "flair": data.get("link_flair_text")},
    )


# ----------------------------------------------------------------------
# hacker news: the monthly "Freelancer? Seeking freelancer?" thread, live
# ----------------------------------------------------------------------
def fetch_hn(queries: Iterable[str], limit: int = 60, rate: float = 1.5) -> FetchResult:
    result = FetchResult()
    for query in queries:
        url = ("https://hn.algolia.com/api/v1/search_by_date?tags=comment"
               f"&query={urllib.parse.quote(query)}&hitsPerPage={int(limit)}")
        try:
            payload = _get_json(url)
            leads = [_hn_lead(hit) for hit in payload.get("hits", [])]
            leads = [lead for lead in leads if lead]
            result.leads.extend(leads)
            result.statuses.append(SourceStatus(f"hn:{query[:24]}", True, len(leads)))
        except Exception as error:  # noqa: BLE001
            result.statuses.append(SourceStatus(f"hn:{query[:24]}", False, 0, _why(error)))
        time.sleep(rate)
    return result


def _hn_lead(hit: dict) -> Optional[Lead]:
    object_id = hit.get("objectID")
    if not object_id:
        return None
    body = clean_text(hit.get("comment_text") or hit.get("story_text") or "")
    if not body:
        return None
    return Lead(
        source="hn",
        source_id=str(object_id),
        title=clean_text(hit.get("story_title") or body[:90]),
        body=body,
        url=f"https://news.ycombinator.com/item?id={object_id}",
        author=str(hit.get("author", "")),
        created_utc=float(hit.get("created_at_i") or 0),
        extra={"story": hit.get("story_title")},
    )


# ----------------------------------------------------------------------
# remoteok: mostly salaried roles, occasionally a paid contract
# ----------------------------------------------------------------------
def fetch_remoteok(contract_only: bool = True, rate: float = 1.5) -> FetchResult:
    result = FetchResult()
    try:
        payload = _get_json("https://remoteok.com/api")
        rows = [row for row in payload if isinstance(row, dict) and row.get("id")]
        leads = []
        for row in rows:
            tags = " ".join(str(tag) for tag in (row.get("tags") or []))
            blob = f"{row.get('position','')} {tags}".lower()
            if contract_only and not any(
                word in blob for word in ("contract", "freelance", "part time", "part-time", "temporary")
            ):
                continue
            leads.append(Lead(
                source="remoteok",
                source_id=str(row["id"]),
                title=clean_text(f"{row.get('company','')} - {row.get('position','')}"),
                body=clean_text(row.get("description", ""))[:4000],
                url=row.get("url", ""),
                author=str(row.get("company", "")),
                created_utc=_epoch(row.get("date")),
                extra={"tags": row.get("tags"), "salary": row.get("salary")},
            ))
        result.leads.extend(leads)
        result.statuses.append(SourceStatus("remoteok", True, len(leads)))
    except Exception as error:  # noqa: BLE001
        result.statuses.append(SourceStatus("remoteok", False, 0, _why(error)))
    time.sleep(rate)
    return result


# ----------------------------------------------------------------------
# generic rss/atom: any board, any Google Alert, no code change
# ----------------------------------------------------------------------
def fetch_rss(feeds: Iterable[str], rate: float = 1.5) -> FetchResult:
    result = FetchResult()
    for feed in feeds:
        name = f"rss:{urllib.parse.urlparse(feed).netloc}"
        try:
            root = ET.fromstring(_get(feed, accept="application/rss+xml, application/xml"))
            leads = [lead for lead in (_rss_lead(item, name) for item in _rss_items(root)) if lead]
            result.leads.extend(leads)
            result.statuses.append(SourceStatus(name, True, len(leads)))
        except Exception as error:  # noqa: BLE001
            result.statuses.append(SourceStatus(name, False, 0, _why(error)))
        time.sleep(rate)
    return result


_ATOM = "{http://www.w3.org/2005/Atom}"


def _rss_items(root: ET.Element) -> list:
    items = root.findall(".//item")
    return items or root.findall(f".//{_ATOM}entry")


def _rss_lead(item: ET.Element, source: str) -> Optional[Lead]:
    def text(*names: str) -> str:
        for name in names:
            node = item.find(name)
            if node is not None:
                if name.endswith("link") and node.text is None:
                    return node.attrib.get("href", "")
                return clean_text(node.text or "")
        return ""

    title = text("title", f"{_ATOM}title")
    if not title:
        return None
    link = text("link", f"{_ATOM}link")
    body = text("description", "content:encoded", f"{_ATOM}summary", f"{_ATOM}content")
    stamp = text("pubDate", "published", f"{_ATOM}published", f"{_ATOM}updated")
    return Lead(
        source=source,
        source_id=text("guid", f"{_ATOM}id") or link or title[:60],
        title=title,
        body=body,
        url=link,
        created_utc=_epoch(stamp),
    )


# ----------------------------------------------------------------------
# offline demo: the same pipeline, on bundled synthetic posts
# ----------------------------------------------------------------------
FIXTURES = Path(__file__).with_name("fixtures") / "demo.json"


def fetch_demo(path: Path = FIXTURES) -> FetchResult:
    """Synthetic posts, clearly labelled. For testing the pipeline offline.

    Ages are stored relative to now so a demo run always looks like a live one.
    These are *not* real people: never send anything to them.
    """
    result = FetchResult()
    try:
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        now = time.time()
        for index, row in enumerate(rows):
            result.leads.append(Lead(
                source=f"demo/{row.get('board', 'board')}",
                source_id=f"demo-{index:03d}",
                title=row["title"],
                body=row.get("body", ""),
                url=row.get("url", "https://example.invalid/demo"),
                author=row.get("author", "demo_user"),
                created_utc=now - float(row.get("age_hours", 3)) * 3600,
                extra={"num_comments": row.get("num_comments", 0), "synthetic": True},
            ))
        result.statuses.append(SourceStatus("démo (synthétique)", True, len(result.leads)))
    except Exception as error:  # noqa: BLE001
        result.statuses.append(SourceStatus("demo", False, 0, _why(error)))
    return result


# ----------------------------------------------------------------------
# orchestration
# ----------------------------------------------------------------------
def load_config(path: Optional[str]) -> dict:
    """Defaults, overridden by a JSON file if the operator wrote one."""
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if path and Path(path).exists():
        override = json.loads(Path(path).read_text(encoding="utf-8"))
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
            else:
                config[key] = value
    return config


def run_sources(config: dict, only: Optional[list[str]] = None, rate: float = 1.5) -> FetchResult:
    """Fetch every enabled source. Failures become status lines, not crashes."""
    combined = FetchResult()
    plan: list[tuple[str, Callable[[], FetchResult]]] = [
        ("reddit", lambda: fetch_reddit(config["reddit"]["subreddits"],
                                        config["reddit"].get("limit", 100), rate)),
        ("hn", lambda: fetch_hn(config["hn"]["queries"], config["hn"].get("limit", 60), rate)),
        ("remoteok", lambda: fetch_remoteok(config["remoteok"].get("contract_only", True), rate)),
        ("rss", lambda: fetch_rss(config["rss"].get("feeds", []), rate)),
    ]
    for name, runner in plan:
        section = config.get(name, {})
        if only:
            if name not in only:
                continue
        elif not section.get("enabled", False):
            continue
        result = runner()
        combined.leads.extend(result.leads)
        combined.statuses.extend(result.statuses)
    return combined


def _epoch(value) -> float:
    """Best-effort timestamp parsing across RFC822, ISO 8601 and epoch ints."""
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.isdigit():
        return float(text)
    try:
        return parsedate_to_datetime(text).timestamp()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        cleaned = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return 0.0


def _why(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        hint = {403: " (bloqué — réessaie depuis ta machine, pas un datacenter)",
                429: " (trop de requêtes — augmente --rate)"}.get(error.code, "")
        return f"HTTP {error.code}{hint}"
    return f"{type(error).__name__}: {error}"[:120]
