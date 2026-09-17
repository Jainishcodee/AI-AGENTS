"""Corpus export (Phase 6).

The corpus is the moat. Six programs are copyable in an afternoon; four hundred resolved
Decision Cards belonging to one person are not — which is the whole argument for this
project existing. And until now it lived in one SQLite file with no door out.

That makes "your data is yours" decorative. A claim of ownership you cannot act on is a
claim about intent, not about the artifact, so this writes the whole corpus to one JSON
file that needs none of this code to read.

**Plain JSON rather than a database copy**, deliberately. Handing back `.sqlite3` would be
easier and would export the *storage*, not the data: it needs this schema, this version,
and a SQLite client to mean anything. JSON opens in an editor, a browser, a notebook and
every language, which is the only definition of portable that survives this repo being
deleted.

Every record is dumped through its own Pydantic model, so the export is exactly what the
system believes rather than whatever the columns happen to hold.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core.logging import get_logger

log = get_logger(__name__)

EXPORT_VERSION = 1
"""Bumped when the shape changes. Present so a future reader can tell what it is holding
rather than guessing from the keys."""


@dataclass(slots=True)
class Bundle:
    """Everything the system knows about you, in one object."""

    deliberations: list[dict[str, Any]]
    cards: list[dict[str, Any]]
    memories: dict[str, list[dict[str, Any]]]
    projects: list[dict[str, Any]]
    modules: list[dict[str, Any]]
    exported_at: datetime

    @property
    def counts(self) -> dict[str, int]:
        return {
            "deliberations": len(self.deliberations),
            "cards": len(self.cards),
            "resolved": sum(1 for c in self.cards if c.get("resolution")),
            "memories": sum(len(v) for v in self.memories.values()),
            "projects": len(self.projects),
            "modules": len(self.modules),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "export_version": EXPORT_VERSION,
            "exported_at": self.exported_at.isoformat(),
            "counts": self.counts,
            "deliberations": self.deliberations,
            "cards": self.cards,
            "memories": self.memories,
            "projects": self.projects,
            "modules": self.modules,
        }

    def describe(self) -> str:
        counts = self.counts
        return (
            f"{counts['cards']} decision(s) ({counts['resolved']} resolved), "
            f"{counts['deliberations']} transcript(s), {counts['memories']} memor(ies), "
            f"{counts['projects']} project(s), {counts['modules']} authored module(s)"
        )


async def collect(store, *, modules: bool = True) -> Bundle:
    """Read the whole corpus out of any store implementation.

    Goes through the `MemoryStore` protocol rather than SQL so the file store and the
    in-memory store export identically — and so this cannot drift from the schema the way
    a hand-written `SELECT *` would.
    """
    cards = await store.list_cards(limit=100_000)
    deliberations = await store.list_deliberations(limit=100_000)
    projects = await store.list_projects()

    # `all_memories`, not `recall`. Recall is a *relevance* function — with an empty
    # query it returns only high-salience rows — so exporting through it would quietly
    # drop everything the ranker judged uninteresting. A backup that loses data silently
    # is worse than no backup.
    memories: dict[str, list[dict[str, Any]]] = {}
    for memory in await store.all_memories():
        memories.setdefault(memory.module, []).append(memory.model_dump(mode="json"))

    authored: list[dict[str, Any]] = []
    if modules:
        try:
            authored = [m.model_dump(mode="json") for m in await store.list_modules()]
        except Exception as exc:  # noqa: BLE001
            log.warning("could not export authored modules: %s", exc)

    return Bundle(
        deliberations=[d.model_dump(mode="json") for d in deliberations],
        cards=[c.model_dump(mode="json") for c in cards],
        memories=memories,
        projects=[p.model_dump(mode="json") for p in projects],
        modules=authored,
        exported_at=datetime.now(timezone.utc),
    )


async def write(store, path: Path, *, modules: bool = True) -> Bundle:
    """Collect and write. Returns the bundle so a caller can report what it wrote."""
    bundle = await collect(store, modules=modules)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bundle.to_dict(), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return bundle
