"""Memory between runs, in a file a human can open.

One JSONL per lead, one line per lead, sorted by score when written. Plain text
on purpose: the operator has to be able to open it, fix a status by hand, grep
it, or delete a row without a database client.

The store owns the boundary between what the machine may overwrite and what it
may not. Score, category and price are recomputed on every run. ``status``,
``notes`` and ``first_seen`` belong to the human, and once a lead has been
touched (status is no longer ``new``) its draft is frozen too - nobody wants
the message they edited by hand replaced by the next cron run.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .lead import STATUSES, Lead

LEADS_FILE = "leads.jsonl"
RUN_FILE = "last_run.json"

HUMAN_FIELDS = ("status", "notes", "first_seen")
FROZEN_WHEN_TOUCHED = ("draft", "price_usd", "price_note", "proof")


@dataclass
class UpsertReport:
    added: int = 0
    updated: int = 0
    total: int = 0


class Store:
    def __init__(self, workdir: str) -> None:
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.path = self.workdir / LEADS_FILE
        self._leads: dict[str, Lead] = {}
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        self._leads = {}
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                lead = Lead.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError):
                continue  # a hand-edited file with one broken line still loads
            self._leads[lead.fingerprint] = lead

    def save(self) -> None:
        rows = sorted(self._leads.values(), key=lambda lead: (-lead.score, -lead.last_seen))
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            for lead in rows:
                handle.write(json.dumps(lead.to_dict(), ensure_ascii=False) + "\n")
        os.replace(temporary, self.path)

    # ------------------------------------------------------------------
    def upsert(self, leads: Iterable[Lead]) -> UpsertReport:
        report = UpsertReport()
        for lead in leads:
            existing = self._leads.get(lead.fingerprint)
            if existing is None:
                self._leads[lead.fingerprint] = lead
                report.added += 1
                continue
            for field in HUMAN_FIELDS:
                setattr(lead, field, getattr(existing, field))
            if existing.status != "new":
                for field in FROZEN_WHEN_TOUCHED:
                    setattr(lead, field, getattr(existing, field))
            lead.last_seen = time.time()
            self._leads[lead.fingerprint] = lead
            report.updated += 1
        report.total = len(self._leads)
        return report

    # ------------------------------------------------------------------
    def all(self) -> list[Lead]:
        return sorted(self._leads.values(), key=lambda lead: (-lead.score, -lead.last_seen))

    def get(self, fingerprint: str) -> Optional[Lead]:
        if fingerprint in self._leads:
            return self._leads[fingerprint]
        matches = [lead for key, lead in self._leads.items() if key.startswith(fingerprint)]
        return matches[0] if len(matches) == 1 else None

    def select(self, tier: Optional[str] = None, status: Optional[str] = None,
               category: Optional[str] = None, min_score: int = 0,
               max_age_hours: Optional[float] = None, limit: Optional[int] = None) -> list[Lead]:
        rows = self.all()
        if tier:
            rows = [lead for lead in rows if lead.tier == tier.upper()]
        if status:
            rows = [lead for lead in rows if lead.status == status]
        if category:
            rows = [lead for lead in rows if lead.category == category]
        if min_score:
            rows = [lead for lead in rows if lead.score >= min_score]
        if max_age_hours is not None:
            rows = [lead for lead in rows
                    if lead.age_hours is not None and lead.age_hours <= max_age_hours]
        return rows[:limit] if limit else rows

    def mark(self, fingerprint: str, status: str, note: str = "") -> Optional[Lead]:
        if status not in STATUSES:
            raise ValueError(f"statut inconnu: {status} (attendu: {', '.join(STATUSES)})")
        lead = self.get(fingerprint)
        if lead is None:
            return None
        lead.status = status
        if note:
            lead.notes.append({"at": time.time(), "status": status, "note": note})
        self.save()
        return lead

    # ------------------------------------------------------------------
    def funnel(self) -> dict:
        counts = {status: 0 for status in STATUSES}
        for lead in self._leads.values():
            counts[lead.status] = counts.get(lead.status, 0) + 1
        sent = counts["sent"] + counts["replied"] + counts["won"] + counts["dead"]
        replied = counts["replied"] + counts["won"]
        return {
            "counts": counts,
            "total": len(self._leads),
            "sent": sent,
            "reply_rate": round(100 * replied / sent, 1) if sent else None,
            "win_rate": round(100 * counts["won"] / sent, 1) if sent else None,
        }

    def wins(self) -> list[Lead]:
        return [lead for lead in self.all() if lead.status == "won"]

    def record_run(self, statuses: list, report: UpsertReport) -> None:
        payload = {
            "at": time.time(),
            "sources": [{"name": s.name, "ok": s.ok, "count": s.count, "detail": s.detail}
                        for s in statuses],
            "added": report.added,
            "updated": report.updated,
            "total": report.total,
        }
        (self.workdir / RUN_FILE).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def last_run(self) -> Optional[dict]:
        path = self.workdir / RUN_FILE
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
