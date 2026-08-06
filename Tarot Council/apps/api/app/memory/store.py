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
from pathlib import Path
from typing import Protocol

from ..core.logging import get_logger
from ..schemas.cards import AgentMemory, DecisionCard, Memory, ModuleScore, Prior
from ..schemas.common import ModuleId
from ..schemas.council import Deliberation

log = get_logger(__name__)


class MemoryStore(Protocol):
    async def save_deliberation(self, deliberation: Deliberation) -> None: ...

    async def get_deliberation(self, deliberation_id: str) -> Deliberation | None: ...

    async def save_card(self, card: DecisionCard) -> None: ...

    async def get_card(self, card_id: str) -> DecisionCard | None: ...

    async def list_cards(self, limit: int = 50) -> list[DecisionCard]: ...

    async def recall(self, module: ModuleId, query: str, k: int = 5) -> list[Memory]: ...

    async def remember(self, module: ModuleId, memories: list[Memory]) -> None: ...

    async def priors(self, module: ModuleId) -> list[Prior]: ...

    async def scores(self) -> list[ModuleScore]: ...

    async def agent_memory(self, module: ModuleId, query: str) -> AgentMemory: ...


class InMemoryStore:
    """Default for tests and for `--no-persist` runs."""

    def __init__(self) -> None:
        self._deliberations: dict[str, Deliberation] = {}
        self._cards: dict[str, DecisionCard] = {}
        self._memories: dict[ModuleId, list[Memory]] = {}

    async def save_deliberation(self, deliberation: Deliberation) -> None:
        self._deliberations[deliberation.id] = deliberation

    async def get_deliberation(self, deliberation_id: str) -> Deliberation | None:
        return self._deliberations.get(deliberation_id)

    async def save_card(self, card: DecisionCard) -> None:
        self._cards[card.id] = card

    async def get_card(self, card_id: str) -> DecisionCard | None:
        return self._cards.get(card_id)

    async def list_cards(self, limit: int = 50) -> list[DecisionCard]:
        ordered = sorted(self._cards.values(), key=lambda c: c.created_at, reverse=True)
        return ordered[:limit]

    async def recall(self, module: ModuleId, query: str, k: int = 5) -> list[Memory]:
        # Phase 1: no embeddings. Salience order, which is honest about being a
        # placeholder rather than pretending to be semantic search.
        items = sorted(self._memories.get(module, []), key=lambda m: m.salience, reverse=True)
        return items[:k]

    async def remember(self, module: ModuleId, memories: list[Memory]) -> None:
        self._memories.setdefault(module, []).extend(memories)

    async def priors(self, module: ModuleId) -> list[Prior]:
        # Priors require >= 3 resolved cards for this module (ADR-018). Until Phase 3
        # computes them from real outcomes, there are none — and inventing plausible
        # ones would poison the exact mechanism they exist to support.
        return []

    async def scores(self) -> list[ModuleScore]:
        return []

    async def agent_memory(self, module: ModuleId, query: str) -> AgentMemory:
        return AgentMemory(
            recalled=await self.recall(module, query),
            priors=await self.priors(module),
        )


class FileStore(InMemoryStore):
    """JSON on disk, so a restart does not lose history. Deleted in Phase 2."""

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self._deliberation_dir = root / "deliberations"
        self._card_dir = root / "cards"
        for directory in (self._deliberation_dir, self._card_dir):
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

    async def save_deliberation(self, deliberation: Deliberation) -> None:
        await super().save_deliberation(deliberation)
        self._write(self._deliberation_dir / f"{deliberation.id}.json", deliberation)

    async def save_card(self, card: DecisionCard) -> None:
        await super().save_card(card)
        self._write(self._card_dir / f"{card.id}.json", card)

    @staticmethod
    def _write(path: Path, model: Deliberation | DecisionCard) -> None:
        path.write_text(
            json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def build_store(kind: str, root: Path) -> MemoryStore:
    return FileStore(root) if kind == "file" else InMemoryStore()
