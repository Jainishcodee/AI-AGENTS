"""SQLite persistence (ADR-024, superseding the Postgres plan in ADR-008).

Shape of the design: **filter in SQL, hydrate with Pydantic.** The fields we actually
query on — `check_on`, `resolved`, `module`, `created_at` — are denormalised into
columns; the whole validated model lives in a `doc` JSON column. Same principle as the
artifact envelope keeping `data` as a dict: the schema that matters is the Pydantic
one, and duplicating it in DDL would give two definitions that drift.

Recall uses FTS5 with BM25 ranking, blended with salience and recency. That is a real
upgrade on the hand-rolled term overlap it replaces, and it is still lexical — which is
what ADR-023 argued for.

`sqlite3` is synchronous, so every call runs through `asyncio.to_thread`. At this
workload (a handful of queries per deliberation) that costs nothing and keeps the
dependency list empty.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

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
    Resolution,
)
from ..schemas.common import ModuleId
from ..schemas.council import Deliberation

log = get_logger(__name__)

SCHEMA_VERSION = 1

MIGRATIONS: dict[int, list[str]] = {
    1: [
        """
        CREATE TABLE deliberations (
            id           TEXT PRIMARY KEY,
            created_at   TEXT NOT NULL,
            question     TEXT NOT NULL,
            preset       TEXT NOT NULL,
            depth        TEXT NOT NULL,
            derived_from TEXT,
            doc          TEXT NOT NULL
        )
        """,
        "CREATE INDEX ix_delib_created ON deliberations (created_at DESC)",
        "CREATE INDEX ix_delib_derived ON deliberations (derived_from)",
        """
        CREATE TABLE cards (
            id              TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL DEFAULT 'local',
            created_at      TEXT NOT NULL,
            question        TEXT NOT NULL,
            deliberation_id TEXT NOT NULL,
            preset          TEXT NOT NULL,
            depth           TEXT NOT NULL,
            domains         TEXT NOT NULL DEFAULT '',
            check_on        TEXT,
            resolved        INTEGER NOT NULL DEFAULT 0,
            graded          INTEGER NOT NULL DEFAULT 0,
            doc             TEXT NOT NULL
        )
        """,
        "CREATE INDEX ix_cards_created ON cards (created_at DESC)",
        # The due query is the one the reminder path runs constantly.
        "CREATE INDEX ix_cards_due ON cards (resolved, check_on)",
        "CREATE INDEX ix_cards_delib ON cards (deliberation_id)",
        """
        CREATE TABLE memories (
            id             TEXT PRIMARY KEY,
            module         TEXT NOT NULL,
            kind           TEXT NOT NULL,
            content        TEXT NOT NULL,
            salience       REAL NOT NULL,
            source_card_id TEXT,
            created_at     TEXT NOT NULL
        )
        """,
        "CREATE INDEX ix_mem_module ON memories (module, salience DESC)",
        # External-content FTS: the text lives once, in `memories`.
        """
        CREATE VIRTUAL TABLE memories_fts USING fts5(
            content,
            content='memories',
            content_rowid='rowid',
            tokenize='porter unicode61'
        )
        """,
        """
        CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts (rowid, content) VALUES (new.rowid, new.content);
        END
        """,
        """
        CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts (memories_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
        END
        """,
        """
        CREATE TRIGGER memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts (memories_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
            INSERT INTO memories_fts (rowid, content) VALUES (new.rowid, new.content);
        END
        """,
    ]
}

STOPWORDS = frozenset(
    """a an and are as at be been but by can do does for from had has have how i if in
    into is it its me my no not of on or our out should so than that the their them then
    there they this to was we were what when which who will with would you your""".split()
)

SALIENCE_FLOOR = 0.7
"""A memory this salient surfaces even with no lexical overlap (ADR-023): "this user
never gets anything in writing" is relevant to decisions sharing none of its words."""


class SQLiteStore:
    """The default store. Single file, no service, real transactions."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL so a reader never blocks the writer; NORMAL because losing the last
        # transaction on a hard power cut is acceptable here and FULL is slow.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = asyncio.Lock()
        self._migrate()

    # ----------------------------------------------------------- migrations --

    def _migrate(self) -> None:
        current = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if current >= SCHEMA_VERSION:
            return
        with self._conn:  # one transaction for the whole upgrade
            for version in range(current + 1, SCHEMA_VERSION + 1):
                for statement in MIGRATIONS[version]:
                    self._conn.execute(statement)
            self._conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        log.info("migrated %s from schema v%d to v%d", self._path.name, current, SCHEMA_VERSION)

    async def close(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._conn.close)

    async def _run(self, fn, *args: Any) -> Any:
        async with self._lock:
            return await asyncio.to_thread(fn, *args)

    # -------------------------------------------------------- deliberations --

    async def save_deliberation(self, deliberation: Deliberation) -> None:
        def write() -> None:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO deliberations
                        (id, created_at, question, preset, depth, derived_from, doc)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        doc=excluded.doc, derived_from=excluded.derived_from
                    """,
                    (
                        deliberation.id,
                        deliberation.created_at.isoformat(),
                        deliberation.question,
                        deliberation.preset,
                        deliberation.depth,
                        deliberation.derived_from,
                        deliberation.model_dump_json(),
                    ),
                )

        await self._run(write)

    async def get_deliberation(self, deliberation_id: str) -> Deliberation | None:
        def read() -> Deliberation | None:
            row = self._conn.execute(
                "SELECT doc FROM deliberations WHERE id = ?", (deliberation_id,)
            ).fetchone()
            return Deliberation.model_validate_json(row["doc"]) if row else None

        return await self._run(read)

    async def list_deliberations(self, limit: int = 50) -> list[Deliberation]:
        def read() -> list[Deliberation]:
            rows = self._conn.execute(
                "SELECT doc FROM deliberations ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [Deliberation.model_validate_json(r["doc"]) for r in rows]

        return await self._run(read)

    # ----------------------------------------------------------------- cards --

    async def save_card(self, card: DecisionCard) -> None:
        def write() -> None:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO cards
                        (id, user_id, created_at, question, deliberation_id, preset, depth,
                         domains, check_on, resolved, graded, doc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        resolved=excluded.resolved,
                        graded=excluded.graded,
                        check_on=excluded.check_on,
                        domains=excluded.domains,
                        doc=excluded.doc
                    """,
                    (
                        card.id,
                        card.user_id,
                        card.created_at.isoformat(),
                        card.question,
                        card.deliberation_id,
                        card.preset,
                        card.depth,
                        ",".join(card.domains),
                        card.expected_outcome.check_on.isoformat()
                        if card.expected_outcome
                        else None,
                        int(card.resolved),
                        int(card.graded),
                        card.model_dump_json(),
                    ),
                )

        await self._run(write)

    async def get_card(self, card_id: str) -> DecisionCard | None:
        def read() -> DecisionCard | None:
            row = self._conn.execute("SELECT doc FROM cards WHERE id = ?", (card_id,)).fetchone()
            return DecisionCard.model_validate_json(row["doc"]) if row else None

        return await self._run(read)

    async def list_cards(
        self, limit: int = 50, status: CardStatus | None = None
    ) -> list[DecisionCard]:
        today = date.today().isoformat()

        # `status` is a Literal, never user text, so it selects a branch rather than
        # being interpolated. `today` is always a bound parameter.
        DUE = "(resolved = 0 AND check_on IS NOT NULL AND check_on <= ?)"

        if status == "resolved":
            sql = "SELECT doc FROM cards WHERE resolved = 1 ORDER BY created_at DESC LIMIT ?"
            params: list[Any] = [limit]
        elif status == "due":
            sql = f"SELECT doc FROM cards WHERE {DUE} ORDER BY check_on ASC LIMIT ?"
            params = [today, limit]
        elif status == "open":
            sql = f"SELECT doc FROM cards WHERE resolved = 0 AND NOT {DUE} ORDER BY created_at DESC LIMIT ?"
            params = [today, limit]
        else:
            # Due first, then newest — what both the card list and the reminder path
            # want, ordered in SQL rather than sorted in Python.
            sql = f"SELECT doc FROM cards ORDER BY {DUE} DESC, created_at DESC LIMIT ?"
            params = [today, limit]

        def read() -> list[DecisionCard]:
            rows = self._conn.execute(sql, params).fetchall()
            return [DecisionCard.model_validate_json(r["doc"]) for r in rows]

        return await self._run(read)

    async def resolve_card(self, card_id: str, resolution: Resolution) -> DecisionCard:
        card = await self.get_card(card_id)
        if card is None:
            raise KeyError(card_id)
        card.resolution = resolution
        await self.save_card(card)
        return card

    async def attach_scoring(self, card_id: str, card_scoring: CardScoring) -> DecisionCard:
        card = await self.get_card(card_id)
        if card is None:
            raise KeyError(card_id)
        card.scoring = card_scoring
        await self.save_card(card)
        return card

    # ------------------------------------------------------------- memories --

    async def remember(self, module: ModuleId, memories: list[Memory]) -> None:
        if not memories:
            return

        def write() -> None:
            with self._conn:
                self._conn.executemany(
                    """
                    INSERT INTO memories
                        (id, module, kind, content, salience, source_card_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        content=excluded.content, salience=excluded.salience
                    """,
                    [
                        (
                            m.id,
                            m.module,
                            m.kind,
                            m.content,
                            m.salience,
                            m.source_card_id,
                            m.created_at.isoformat(),
                        )
                        for m in memories
                    ],
                )

        await self._run(write)

    async def recall(self, module: ModuleId, query: str, k: int = 5) -> list[Memory]:
        """BM25 over FTS5, blended with salience and recency.

        Two queries rather than one: the FTS match, and a salience floor for memories
        that matter regardless of vocabulary. Merging in Python is clearer than an
        `OR` that would defeat the FTS index.
        """
        match = _fts_query(query)

        def read() -> list[Memory]:
            found: dict[str, tuple[float, sqlite3.Row]] = {}

            if match:
                rows = self._conn.execute(
                    """
                    SELECT m.*, bm25(memories_fts) AS bm
                    FROM memories_fts
                    JOIN memories m ON m.rowid = memories_fts.rowid
                    WHERE memories_fts MATCH ? AND m.module = ?
                    ORDER BY bm
                    LIMIT ?
                    """,
                    (match, module, k * 4),
                ).fetchall()
                # bm25() is negative and lower is better, so negate it into a score.
                for row in rows:
                    found[row["id"]] = (-float(row["bm"]) + row["salience"] * 1.5, row)

            floor = self._conn.execute(
                """
                SELECT * FROM memories
                WHERE module = ? AND salience >= ?
                ORDER BY salience DESC, created_at DESC
                LIMIT ?
                """,
                (module, SALIENCE_FLOOR, k),
            ).fetchall()
            for row in floor:
                if row["id"] not in found:
                    found[row["id"]] = (row["salience"], row)

            ordered = sorted(found.values(), key=lambda pair: pair[0], reverse=True)[:k]
            return [_memory_of(row) for _score, row in ordered]

        return await self._run(read)

    async def all_memories(self, module: ModuleId | None = None) -> list[Memory]:
        def read() -> list[Memory]:
            if module:
                rows = self._conn.execute(
                    "SELECT * FROM memories WHERE module = ? ORDER BY created_at DESC",
                    (module,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM memories ORDER BY created_at DESC"
                ).fetchall()
            return [_memory_of(r) for r in rows]

        return await self._run(read)

    # -------------------------------------------------------------- derived --

    async def priors(self, module: ModuleId) -> list[Prior]:
        return priors_for_module(await self._graded_cards(), module)

    async def scores(self) -> list[ModuleScore]:
        return all_scores(await self._graded_cards())

    async def agent_memory(self, module: ModuleId, query: str) -> AgentMemory:
        return AgentMemory(
            recalled=await self.recall(module, query),
            priors=await self.priors(module),
        )

    async def _graded_cards(self) -> list[DecisionCard]:
        """Only graded cards feed calibration, so the query filters in SQL.

        This is the reason `graded` is a column and not a JSON lookup: it is the hot
        filter for every score and prior computation."""

        def read() -> list[DecisionCard]:
            rows = self._conn.execute("SELECT doc FROM cards WHERE graded = 1").fetchall()
            return [DecisionCard.model_validate_json(r["doc"]) for r in rows]

        return await self._run(read)

    # --------------------------------------------------------------- import --

    async def import_from(self, other: Any) -> dict[str, int]:
        """Copy everything out of another store. Used by the FileStore migration.

        Idempotent: every write is an upsert keyed on id, so running it twice is safe.
        """
        counts = {"deliberations": 0, "cards": 0, "memories": 0}

        for deliberation in await _all_deliberations(other):
            await self.save_deliberation(deliberation)
            counts["deliberations"] += 1
        for card in await other.list_cards(limit=100_000):
            await self.save_card(card)
            counts["cards"] += 1

        memories = getattr(other, "_memories", {}) or {}
        for module, items in memories.items():
            await self.remember(module, items)
            counts["memories"] += len(items)
        return counts


# ------------------------------------------------------------------ helpers --


def _memory_of(row: sqlite3.Row) -> Memory:
    return Memory(
        id=row["id"],
        module=row["module"],
        kind=row["kind"],
        content=row["content"],
        salience=row["salience"],
        source_card_id=row["source_card_id"],
        created_at=_parse_dt(row["created_at"]),
    )


def _parse_dt(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _fts_query(query: str) -> str:
    """Build a safe FTS5 MATCH expression from free text.

    Every term is quoted and OR-ed. Quoting matters for correctness as well as
    safety: unquoted user text containing `AND`, `NEAR`, `*` or `-` is interpreted as
    FTS syntax, so an innocent question could raise a syntax error or silently mean
    something else.
    """
    terms = [
        token
        for token in re.findall(r"[A-Za-z0-9']+", query.lower())
        if len(token) > 2 and token not in STOPWORDS
    ]
    return " OR ".join(f'"{term}"' for term in dict.fromkeys(terms))


async def _all_deliberations(store: Any) -> list[Deliberation]:
    lister = getattr(store, "list_deliberations", None)
    if lister is not None:
        return await lister(limit=100_000)
    return list(getattr(store, "_deliberations", {}).values())
