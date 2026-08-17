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

from pydantic import ValidationError

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
from ..schemas.module import UserModule
from ..schemas.common import ModuleId
from ..schemas.council import Deliberation

log = get_logger(__name__)

SCHEMA_VERSION = 4

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
    ],
    2: [
        # Projects: real decisions arrive in chains, and grouping them is what stops
        # recall dragging a side project into a salary conversation.
        """
        CREATE TABLE projects (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL DEFAULT 'local',
            name       TEXT NOT NULL,
            brief      TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            closed_at  TEXT
        )
        """,
        "ALTER TABLE deliberations ADD COLUMN project_id TEXT",
        "ALTER TABLE cards ADD COLUMN project_id TEXT",
        "ALTER TABLE memories ADD COLUMN project_id TEXT",
        "CREATE INDEX ix_cards_project ON cards (project_id)",
        "CREATE INDEX ix_mem_project ON memories (project_id, module)",
    ],
    3: [
        # Resumable runs. A free tier meters requests per minute, so a deliberation can
        # outlive its quota window; without this, everything already paid for is lost.
        """
        CREATE TABLE checkpoints (
            deliberation_id TEXT PRIMARY KEY,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            phase           TEXT NOT NULL,
            question        TEXT NOT NULL,
            calls           INTEGER NOT NULL DEFAULT 0,
            doc             TEXT NOT NULL
        )
        """,
        "CREATE INDEX ix_ckpt_phase ON checkpoints (phase, updated_at DESC)",
    ],
    4: [
        # User-authored modules (ADR-030). Stored rather than dropped in the package
        # directory so a half-finished draft cannot stop the server booting, and so
        # `status`/`errors` can be queried without parsing every program.
        """
        CREATE TABLE user_modules (
            id          TEXT PRIMARY KEY,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            status      TEXT NOT NULL,
            author      TEXT NOT NULL DEFAULT 'local',
            based_on    TEXT,
            error_count INTEGER NOT NULL DEFAULT 0,
            doc         TEXT NOT NULL
        )
        """,
        "CREATE INDEX ix_user_modules_status ON user_modules (status, updated_at DESC)",
    ],
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
                        (id, created_at, question, preset, depth, derived_from,
                         project_id, doc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        doc=excluded.doc,
                        derived_from=excluded.derived_from,
                        project_id=excluded.project_id
                    """,
                    (
                        deliberation.id,
                        deliberation.created_at.isoformat(),
                        deliberation.question,
                        deliberation.preset,
                        deliberation.depth,
                        deliberation.derived_from,
                        deliberation.project_id,
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
                "SELECT doc FROM deliberations ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,),
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
                         domains, check_on, resolved, graded, project_id, doc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        resolved=excluded.resolved,
                        graded=excluded.graded,
                        check_on=excluded.check_on,
                        domains=excluded.domains,
                        project_id=excluded.project_id,
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
                        card.project_id,
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
        #
        # Every ordering carries `rowid DESC` as a tie-breaker. Windows' clock
        # granularity is ~15.6 ms, so a burst of decisions shares one `created_at`,
        # and SQLite breaks such ties however it likes — which made "newest first"
        # silently return the oldest.
        DUE = "(resolved = 0 AND check_on IS NOT NULL AND check_on <= ?)"

        if status == "resolved":
            sql = (
                "SELECT doc FROM cards WHERE resolved = 1 "
                "ORDER BY created_at DESC, rowid DESC LIMIT ?"
            )
            params: list[Any] = [limit]
        elif status == "due":
            sql = f"SELECT doc FROM cards WHERE {DUE} ORDER BY check_on ASC, rowid DESC LIMIT ?"
            params = [today, limit]
        elif status == "open":
            sql = (
                f"SELECT doc FROM cards WHERE resolved = 0 AND NOT {DUE} "
                "ORDER BY created_at DESC, rowid DESC LIMIT ?"
            )
            params = [today, limit]
        else:
            # Due first, then newest — what both the card list and the reminder path
            # want, ordered in SQL rather than sorted in Python.
            sql = (
                f"SELECT doc FROM cards ORDER BY {DUE} DESC, created_at DESC, rowid DESC "
                "LIMIT ?"
            )
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
                        (id, module, kind, content, salience, source_card_id,
                         project_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                            m.project_id,
                            m.created_at.isoformat(),
                        )
                        for m in memories
                    ],
                )

        await self._run(write)

    async def recall(
        self,
        module: ModuleId,
        query: str,
        k: int = 5,
        *,
        project_id: str | None = None,
        exclude_cards: frozenset[str] = frozenset(),
    ) -> list[Memory]:
        """BM25 over FTS5, blended with salience, recency and project match.

        Three queries rather than one: the FTS match, a salience floor for memories
        that matter regardless of vocabulary, and — when scoped to a project — that
        project's own memories. Merging in Python is clearer than an `OR` that would
        defeat the FTS index.

        `exclude_cards` is what keeps replay honest: a memory extracted from the very
        card being re-decided would hand the module its own answer (ADR-025).
        """
        match = _fts_query(query)
        blocked = set(exclude_cards)

        def read() -> list[Memory]:
            found: dict[str, tuple[float, sqlite3.Row]] = {}

            def offer(row: sqlite3.Row, score: float) -> None:
                if row["source_card_id"] in blocked:
                    return
                bonus = 2.0 if project_id and row["project_id"] == project_id else 0.0
                current = found.get(row["id"])
                if current is None or score + bonus > current[0]:
                    found[row["id"]] = (score + bonus, row)

            if match:
                for row in self._conn.execute(
                    """
                    SELECT m.*, bm25(memories_fts) AS bm
                    FROM memories_fts
                    JOIN memories m ON m.rowid = memories_fts.rowid
                    WHERE memories_fts MATCH ? AND m.module = ?
                    ORDER BY bm
                    LIMIT ?
                    """,
                    (match, module, k * 4),
                ).fetchall():
                    # bm25() is negative and lower is better, so negate it.
                    offer(row, -float(row["bm"]) + row["salience"] * 1.5)

            for row in self._conn.execute(
                """
                SELECT * FROM memories
                WHERE module = ? AND salience >= ?
                ORDER BY salience DESC, created_at DESC
                LIMIT ?
                """,
                (module, SALIENCE_FLOOR, k),
            ).fetchall():
                offer(row, row["salience"])

            if project_id:
                for row in self._conn.execute(
                    """
                    SELECT * FROM memories
                    WHERE module = ? AND project_id = ?
                    ORDER BY salience DESC, created_at DESC
                    LIMIT ?
                    """,
                    (module, project_id, k),
                ).fetchall():
                    offer(row, row["salience"])

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

    async def priors(
        self, module: ModuleId, *, exclude_cards: frozenset[str] = frozenset()
    ) -> list[Prior]:
        cards = [c for c in await self._graded_cards() if c.id not in exclude_cards]
        return priors_for_module(cards, module)

    async def scores(self) -> list[ModuleScore]:
        return all_scores(await self._graded_cards())

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

    # ---------------------------------------------------------- checkpoints --

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """One upsert per artifact. Negligible against an LLM call, which is what makes
        checkpointing at artifact granularity affordable at all."""

        def write() -> None:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO checkpoints
                        (deliberation_id, created_at, updated_at, phase, question, calls, doc)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(deliberation_id) DO UPDATE SET
                        updated_at=excluded.updated_at,
                        phase=excluded.phase,
                        calls=excluded.calls,
                        doc=excluded.doc
                    """,
                    (
                        checkpoint.deliberation_id,
                        checkpoint.created_at.isoformat(),
                        checkpoint.updated_at.isoformat(),
                        checkpoint.phase,
                        checkpoint.request.question,
                        checkpoint.usage.calls,
                        checkpoint.model_dump_json(),
                    ),
                )

        await self._run(write)

    async def get_checkpoint(self, deliberation_id: str) -> Checkpoint | None:
        def read() -> Checkpoint | None:
            row = self._conn.execute(
                "SELECT doc FROM checkpoints WHERE deliberation_id = ?", (deliberation_id,)
            ).fetchone()
            return Checkpoint.model_validate_json(row["doc"]) if row else None

        return await self._run(read)

    async def list_checkpoints(self, limit: int = 20) -> list[Checkpoint]:
        def read() -> list[Checkpoint]:
            rows = self._conn.execute(
                """
                SELECT doc FROM checkpoints
                WHERE phase != 'done'
                ORDER BY updated_at DESC, rowid DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [Checkpoint.model_validate_json(r["doc"]) for r in rows]

        return await self._run(read)

    async def delete_checkpoint(self, deliberation_id: str) -> None:
        def write() -> None:
            with self._conn:
                self._conn.execute(
                    "DELETE FROM checkpoints WHERE deliberation_id = ?", (deliberation_id,)
                )

        await self._run(write)

    # -------------------------------------------------------- user modules --

    async def save_module(self, module: UserModule) -> None:
        """Upsert. `status` and `error_count` are denormalised so the catalog can list
        what is broken without deserialising every stored program."""

        def write() -> None:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO user_modules
                        (id, created_at, updated_at, status, author, based_on,
                         error_count, doc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        updated_at=excluded.updated_at,
                        status=excluded.status,
                        based_on=excluded.based_on,
                        error_count=excluded.error_count,
                        doc=excluded.doc
                    """,
                    (
                        module.id,
                        module.created_at.isoformat(),
                        module.updated_at.isoformat(),
                        module.status,
                        module.author,
                        module.based_on,
                        len(module.errors),
                        module.model_dump_json(),
                    ),
                )

        await self._run(write)

    async def get_module(self, module_id: ModuleId) -> UserModule | None:
        def read() -> UserModule | None:
            row = self._conn.execute(
                "SELECT doc FROM user_modules WHERE id = ?", (module_id,)
            ).fetchone()
            return UserModule.model_validate_json(row["doc"]) if row else None

        return await self._run(read)

    async def list_modules(self) -> list[UserModule]:
        def read() -> list[UserModule]:
            rows = self._conn.execute("SELECT doc FROM user_modules ORDER BY id").fetchall()
            out: list[UserModule] = []
            for row in rows:
                try:
                    out.append(UserModule.model_validate_json(row["doc"]))
                except ValidationError as exc:
                    # A stored module that no longer parses must not take the catalog with
                    # it. The author needs the rest of their modules to keep working while
                    # they fix or delete this one — the same argument as quarantine.
                    log.warning("skipping unreadable stored module: %s", exc)
            return out

        return await self._run(read)

    async def delete_module(self, module_id: ModuleId) -> None:
        def write() -> None:
            with self._conn:
                self._conn.execute("DELETE FROM user_modules WHERE id = ?", (module_id,))

        await self._run(write)

    # ------------------------------------------------------------- projects --

    async def save_project(self, project: Project) -> None:
        def write() -> None:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO projects (id, user_id, name, brief, created_at, closed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        brief=excluded.brief,
                        closed_at=excluded.closed_at
                    """,
                    (
                        project.id,
                        project.user_id,
                        project.name,
                        project.brief,
                        project.created_at.isoformat(),
                        project.closed_at.isoformat() if project.closed_at else None,
                    ),
                )

        await self._run(write)

    async def get_project(self, project_id: str) -> Project | None:
        def read() -> Project | None:
            row = self._conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            return _project_of(row) if row else None

        return await self._run(read)

    async def list_projects(self) -> list[Project]:
        def read() -> list[Project]:
            # Open projects first: a closed one is history, not something to add to.
            rows = self._conn.execute(
                "SELECT * FROM projects ORDER BY closed_at IS NOT NULL, created_at DESC"
            ).fetchall()
            return [_project_of(r) for r in rows]

        return await self._run(read)

    async def cards_in_project(self, project_id: str, limit: int = 200) -> list[DecisionCard]:
        def read() -> list[DecisionCard]:
            rows = self._conn.execute(
                "SELECT doc FROM cards WHERE project_id = ? "
                "ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
            return [DecisionCard.model_validate_json(r["doc"]) for r in rows]

        return await self._run(read)

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
        project_id=row["project_id"],
        created_at=_parse_dt(row["created_at"]),
    )


def _project_of(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        brief=row["brief"],
        created_at=_parse_dt(row["created_at"]),
        closed_at=_parse_dt(row["closed_at"]) if row["closed_at"] else None,
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
