"""Persistence behind a protocol (ADR-008).

Phase 1 ships in-memory and JSON-file implementations. Phase 2 adds
`PostgresStore` with pgvector for `recall`, and deletes `FileStore`. The
orchestrator only ever sees the protocol, so that swap touches one line of wiring.

The interface shape is the expensive thing to retrofit — in particular `recall`
being *per module*, because six modules with six extraction biases is not the same
as one shared index.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Protocol

from ..core.logging import get_logger
from ..learning.priors import for_module as priors_for_module
from ..learning.scoring import all_scores
from ..schemas.cards import (
    AgentMemory,
    CardScoring,
    CardStatus,
    DecisionCard,
    Memory,
    ModuleScore,
    Prior,
    Project,
    Resolution,
)
from ..schemas.checkpoint import Checkpoint
from ..schemas.common import ModuleId
from ..schemas.council import Deliberation

log = get_logger(__name__)


class MemoryStore(Protocol):
    async def save_deliberation(self, deliberation: Deliberation) -> None: ...

    async def get_deliberation(self, deliberation_id: str) -> Deliberation | None: ...

    async def list_deliberations(self, limit: int = 50) -> list[Deliberation]: ...

    async def save_card(self, card: DecisionCard) -> None: ...

    async def get_card(self, card_id: str) -> DecisionCard | None: ...

    async def list_cards(
        self, limit: int = 50, status: CardStatus | None = None
    ) -> list[DecisionCard]: ...

    async def recall(
        self,
        module: ModuleId,
        query: str,
        k: int = 5,
        *,
        project_id: str | None = None,
        exclude_cards: frozenset[str] = frozenset(),
    ) -> list[Memory]: ...

    async def remember(self, module: ModuleId, memories: list[Memory]) -> None: ...

    async def priors(
        self, module: ModuleId, *, exclude_cards: frozenset[str] = frozenset()
    ) -> list[Prior]: ...

    async def scores(self) -> list[ModuleScore]: ...

    async def agent_memory(
        self,
        module: ModuleId,
        query: str,
        *,
        project_id: str | None = None,
        exclude_cards: frozenset[str] = frozenset(),
    ) -> AgentMemory: ...

    async def save_project(self, project: Project) -> None: ...

    async def get_project(self, project_id: str) -> Project | None: ...

    async def list_projects(self) -> list[Project]: ...

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None: ...

    async def get_checkpoint(self, deliberation_id: str) -> Checkpoint | None: ...

    async def list_checkpoints(self, limit: int = 20) -> list[Checkpoint]: ...

    async def delete_checkpoint(self, deliberation_id: str) -> None: ...


class InMemoryStore:
    """Default for tests and for `--no-persist` runs."""

    def __init__(self) -> None:
        self._deliberations: dict[str, Deliberation] = {}
        self._cards: dict[str, DecisionCard] = {}
        self._memories: dict[ModuleId, list[Memory]] = {}
        self._projects: dict[str, Project] = {}
        self._checkpoints: dict[str, Checkpoint] = {}

    async def save_deliberation(self, deliberation: Deliberation) -> None:
        self._deliberations[deliberation.id] = deliberation

    async def get_deliberation(self, deliberation_id: str) -> Deliberation | None:
        return self._deliberations.get(deliberation_id)

    async def list_deliberations(self, limit: int = 50) -> list[Deliberation]:
        # Insertion order breaks timestamp ties — see `list_cards`.
        indexed = sorted(
            enumerate(self._deliberations.values()),
            key=lambda pair: (-pair[1].created_at.timestamp(), -pair[0]),
        )
        return [item for _index, item in indexed[:limit]]

    async def save_card(self, card: DecisionCard) -> None:
        self._cards[card.id] = card

    async def get_card(self, card_id: str) -> DecisionCard | None:
        return self._cards.get(card_id)

    async def list_cards(
        self, limit: int = 50, status: CardStatus | None = None
    ) -> list[DecisionCard]:
        today = date.today()
        # Insertion order is the tie-breaker, and it is not optional: Windows' clock
        # granularity is ~15.6 ms, so several decisions taken in one burst share an
        # identical `created_at`. Sorting on the timestamp alone leaves those ties
        # unbroken, and a stable sort then returns the *oldest* first — which is the
        # opposite of what "newest" means.
        indexed = list(enumerate(self._cards.values()))
        if status is not None:
            indexed = [(i, c) for i, c in indexed if c.status(today) == status]
        # Due first, then newest. A card whose check-in date has passed is the only
        # thing in here actively asking for attention, so it goes to the top.
        indexed.sort(key=lambda pair: (pair[1].status(today) != "due", -pair[1].created_at.timestamp(), -pair[0]))
        return [card for _index, card in indexed[:limit]]

    async def recall(
        self,
        module: ModuleId,
        query: str,
        k: int = 5,
        *,
        project_id: str | None = None,
        exclude_cards: frozenset[str] = frozenset(),
    ) -> list[Memory]:
        """Lexical overlap, weighted by salience, recency and project match.

        Not embeddings, deliberately (ADR-023). `exclude_cards` is what keeps replay
        honest: a memory extracted from the very card being re-decided would hand the
        module its own answer (ADR-025).
        """
        items = [
            m
            for m in self._memories.get(module, [])
            if m.source_card_id not in exclude_cards
        ]
        if not items:
            return []
        terms = _terms(query)
        newest = max((m.created_at for m in items), default=None)

        def rank(memory: Memory) -> float:
            overlap = len(terms & _terms(memory.content))
            score = overlap * 1.0 + memory.salience * 1.5
            if project_id and memory.project_id == project_id:
                score += 2.0  # same ongoing situation beats a merely similar one
            if newest is not None:
                age_days = (newest - memory.created_at).total_seconds() / 86400
                score += max(0.0, 1.0 - age_days / 365) * 0.5
            return score

        ranked = sorted(items, key=rank, reverse=True)
        # A memory with no lexical overlap still surfaces if it is highly salient, or
        # if it belongs to the same project — "this user never puts anything in
        # writing" is relevant to decisions that share none of its words.
        return [
            m
            for m in ranked
            if _terms(m.content) & terms
            or m.salience >= 0.7
            or (project_id and m.project_id == project_id)
        ][:k]

    async def remember(self, module: ModuleId, memories: list[Memory]) -> None:
        self._memories.setdefault(module, []).extend(memories)

    async def priors(
        self, module: ModuleId, *, exclude_cards: frozenset[str] = frozenset()
    ) -> list[Prior]:
        """Computed from graded cards on demand (ADR-018).

        Recomputing per call rather than caching: the corpus is small, and a cached
        prior that outlives the card it cites is worse than a cheap recount.
        """
        cards = [c for c in self._cards.values() if c.id not in exclude_cards]
        return priors_for_module(cards, module)

    async def scores(self) -> list[ModuleScore]:
        return all_scores(list(self._cards.values()))

    async def resolve_card(self, card_id: str, resolution: Resolution) -> DecisionCard:
        card = self._cards.get(card_id)
        if card is None:
            raise KeyError(card_id)
        card.resolution = resolution
        await self.save_card(card)
        return card

    async def attach_scoring(self, card_id: str, card_scoring: CardScoring) -> DecisionCard:
        card = self._cards.get(card_id)
        if card is None:
            raise KeyError(card_id)
        card.scoring = card_scoring
        await self.save_card(card)
        return card

    async def agent_memory(
        self,
        module: ModuleId,
        query: str,
        *,
        project_id: str | None = None,
        exclude_cards: frozenset[str] = frozenset(),
    ) -> AgentMemory:
        return AgentMemory(
            recalled=await self.recall(
                module, query, project_id=project_id, exclude_cards=exclude_cards
            ),
            priors=await self.priors(module, exclude_cards=exclude_cards),
        )

    async def save_project(self, project: Project) -> None:
        self._projects[project.id] = project

    async def get_project(self, project_id: str) -> Project | None:
        return self._projects.get(project_id)

    async def list_projects(self) -> list[Project]:
        return sorted(self._projects.values(), key=lambda p: p.created_at, reverse=True)

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        self._checkpoints[checkpoint.deliberation_id] = checkpoint

    async def get_checkpoint(self, deliberation_id: str) -> Checkpoint | None:
        return self._checkpoints.get(deliberation_id)

    async def list_checkpoints(self, limit: int = 20) -> list[Checkpoint]:
        live = [c for c in self._checkpoints.values() if c.phase != "done"]
        return sorted(live, key=lambda c: c.updated_at, reverse=True)[:limit]

    async def delete_checkpoint(self, deliberation_id: str) -> None:
        self._checkpoints.pop(deliberation_id, None)


class FileStore(InMemoryStore):
    """JSON on disk, so a restart does not lose history. Superseded by `SQLiteStore`.

    Kept only for migrating an existing `var/` directory (ADR-024). Every write path here
    must be overridden explicitly: anything left inherited from `InMemoryStore` persists to
    RAM and is silently gone on restart, which is a worse failure than not supporting it —
    checkpoints and projects were exactly that until it was caught by resuming in a second
    process rather than in a test.
    """

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self._deliberation_dir = root / "deliberations"
        self._card_dir = root / "cards"
        self._memory_file = root / "memories.json"
        self._checkpoint_dir = root / "checkpoints"
        self._project_dir = root / "projects"
        for directory in (
            self._deliberation_dir,
            self._card_dir,
            self._checkpoint_dir,
            self._project_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        for path in self._deliberation_dir.glob("*.json"):
            try:
                self._deliberations[path.stem] = Deliberation.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except Exception as exc:  # noqa: BLE001 - a stale file must not block boot
                log.warning("skipping unreadable deliberation %s: %s", path.name, exc)
        for path in self._card_dir.glob("*.json"):
            try:
                self._cards[path.stem] = DecisionCard.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("skipping unreadable card %s: %s", path.name, exc)
        for path in self._checkpoint_dir.glob("*.json"):
            try:
                self._checkpoints[path.stem] = Checkpoint.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("skipping unreadable checkpoint %s: %s", path.name, exc)
        for path in self._project_dir.glob("*.json"):
            try:
                self._projects[path.stem] = Project.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("skipping unreadable project %s: %s", path.name, exc)
        if self._memory_file.is_file():
            try:
                raw = json.loads(self._memory_file.read_text(encoding="utf-8"))
                self._memories = {
                    module: [Memory.model_validate(item) for item in items]
                    for module, items in raw.items()
                }
            except Exception as exc:  # noqa: BLE001
                log.warning("skipping unreadable memories: %s", exc)

    async def save_deliberation(self, deliberation: Deliberation) -> None:
        await super().save_deliberation(deliberation)
        self._write(self._deliberation_dir / f"{deliberation.id}.json", deliberation)

    async def save_card(self, card: DecisionCard) -> None:
        await super().save_card(card)
        self._write(self._card_dir / f"{card.id}.json", card)

    async def remember(self, module: ModuleId, memories: list[Memory]) -> None:
        await super().remember(module, memories)
        self._write_memories()

    async def save_project(self, project: Project) -> None:
        await super().save_project(project)
        self._write(self._project_dir / f"{project.id}.json", project)

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        await super().save_checkpoint(checkpoint)
        self._write(
            self._checkpoint_dir / f"{checkpoint.deliberation_id}.json", checkpoint
        )

    async def delete_checkpoint(self, deliberation_id: str) -> None:
        await super().delete_checkpoint(deliberation_id)
        (self._checkpoint_dir / f"{deliberation_id}.json").unlink(missing_ok=True)

    def _write_memories(self) -> None:
        self._memory_file.write_text(
            json.dumps(
                {
                    module: [m.model_dump(mode="json") for m in items]
                    for module, items in self._memories.items()
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _write(path: Path, model: Deliberation | DecisionCard | Project | Checkpoint) -> None:
        path.write_text(
            json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def build_store(kind: str, root: Path) -> MemoryStore:
    """`sqlite` is the default (ADR-024). `file` and `memory` remain for migration
    and for tests that want no I/O at all."""
    if kind == "sqlite":
        from .sqlite_store import SQLiteStore

        return SQLiteStore(root / "cognitive-os.sqlite3")
    if kind == "file":
        return FileStore(root)
    return InMemoryStore()


STOPWORDS = frozenset(
    """a an and are as at be been but by can do does for from had has have how i if in
    into is it its me my no not of on or our out should so than that the their them then
    there they this to was we were what when which who will with would you your""".split()
)


def _terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9']+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    }
