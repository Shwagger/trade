"""The one record that travels through the whole pipeline.

Sources produce ``Lead`` objects with the raw fields filled in; the qualifier
adds the score; the offer engine adds the price and the draft; the store keeps
the human's decisions (status, notes) across runs. Everything is JSON-round-
trippable, because the state file is a plain JSONL a human can open and edit.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

STATUSES = ("new", "drafted", "sent", "replied", "won", "dead")


@dataclass
class Lead:
    source: str
    source_id: str
    title: str
    body: str = ""
    url: str = ""
    author: str = ""
    created_utc: float = 0.0
    fetched_utc: float = field(default_factory=time.time)
    extra: dict = field(default_factory=dict)

    # filled by qualify()
    score: int = 0
    tier: str = "IGNORE"
    signals: list = field(default_factory=list)
    penalties: list = field(default_factory=list)
    category: str = "other"
    category_label: str = ""
    budget: Optional[dict] = None
    deadline: Optional[dict] = None
    contact: str = ""
    contact_address: Optional[str] = None

    # filled by prepare()
    price_usd: Optional[float] = None
    price_note: str = ""
    draft: str = ""
    proof: str = ""

    # owned by the human
    status: str = "new"
    notes: list = field(default_factory=list)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    @property
    def fingerprint(self) -> str:
        """Stable id across runs. Same post = same row, whatever the ordering."""
        raw = f"{self.source}:{self.source_id}".encode("utf-8", "replace")
        return hashlib.sha1(raw).hexdigest()[:10]

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}".strip()

    @property
    def age_hours(self) -> Optional[float]:
        if not self.created_utc:
            return None
        return max(0.0, (time.time() - self.created_utc) / 3600.0)

    def age_label(self) -> str:
        hours = self.age_hours
        if hours is None:
            return "?"
        if hours < 1:
            return f"{int(hours * 60)}min"
        if hours < 48:
            return f"{int(hours)}h"
        return f"{int(hours / 24)}j"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Lead":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})
