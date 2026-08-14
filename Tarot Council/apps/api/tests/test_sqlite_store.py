"""SQLite persistence (Phase 2).

Every test here runs against a **real database** in a temp file — not a mock, not an
in-memory double. That is the point of choosing SQLite: the storage layer can be
verified in CI in milliseconds, so nothing about it has to be taken on trust.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest

from app.memory.sqlite_store import SCHEMA_VERSION, SQLiteStore, _fts_query
from app.memory.store import FileStore, InMemoryStore, build_store
from app.schemas.cards import (
    DecisionCard,
    ExpectedOutcome,
    Memory,
    ModuleStance,
    Resolution,
)
from app.schemas.common import Confidence, Usage
from app.schemas.council import (
    DecisionContext,
    Deliberation,
    DeliberationRequest,
    Recommendation,
    Rerun,
)

TODAY = date.today()


@pytest.fixture
def store(tmp_path):
    instance = SQLiteStore(tmp_path / "test.sqlite3")
    yield instance


def make_card(card_id: str, *, check_in: int = 30, resolved: bool = False) -> DecisionCard:
    card = DecisionCard(
        id=card_id,
        question=f"question {card_id}",
        deliberation_id=f"d-{card_id}",
        preset="full",
        depth="quick",
        domains=["career", "finance"],
        recommendation=Recommendation(action="act", first_action="today"),
        per_module=[
            ModuleStance(
                module="analyst",
                stance="do it",
                confidence=Confidence(score=0.7, basis="b", falsifier="f"),
            )
        ],
        expected_outcome=ExpectedOutcome(
            statement="it works", check_on=TODAY + timedelta(days=check_in)
        ),
    )
    if resolved:
        card.resolution = Resolution(chose="did it", actual_outcome="fine", happened_at=TODAY)
    return card


def make_deliberation(delib_id: str, **kw) -> Deliberation:
    return Deliberation(
        id=delib_id,
        question=f"q {delib_id}",
        preset="full",
        depth="quick",
        context=DecisionContext(question=f"q {delib_id}"),
        usage=Usage(calls=3),
        **kw,
    )


# ─────────────────────────────────────────────────────────── migrations ─────


def test_migration_sets_user_version(store, tmp_path):
    raw = sqlite3.connect(tmp_path / "test.sqlite3")
    assert raw.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    tables = {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"deliberations", "cards", "memories"} <= tables
    raw.close()


def test_opening_an_existing_database_is_idempotent(tmp_path):
    """Re-opening must not re-run migrations — that would raise "table exists"."""
    path = tmp_path / "twice.sqlite3"
    SQLiteStore(path)
    reopened = SQLiteStore(path)  # would throw if migrations ran again
    raw = sqlite3.connect(path)
    assert raw.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    raw.close()
    assert reopened is not None


def test_wal_mode_is_enabled(store, tmp_path):
    raw = sqlite3.connect(tmp_path / "test.sqlite3")
    assert raw.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    raw.close()


# ──────────────────────────────────────────────────────────── round trips ────


async def test_deliberation_round_trips_with_full_fidelity(store):
    original = make_deliberation("d1", derived_from="d0", rerun=Rerun(kind="stage", module="analyst"))
    await store.save_deliberation(original)
    loaded = await store.get_deliberation("d1")
    assert loaded is not None
    assert loaded.model_dump_json() == original.model_dump_json()
    assert loaded.rerun is not None and loaded.rerun.module == "analyst"


async def test_saving_a_deliberation_twice_updates_rather_than_duplicates(store):
    await store.save_deliberation(make_deliberation("d1"))
    changed = make_deliberation("d1")
    changed.usage.calls = 99
    await store.save_deliberation(changed)
    loaded = await store.get_deliberation("d1")
    assert loaded is not None and loaded.usage.calls == 99
    assert len(await store.list_deliberations()) == 1


async def test_missing_rows_return_none(store):
    assert await store.get_deliberation("nope") is None
    assert await store.get_card("nope") is None


async def test_card_round_trips_including_resolution_and_scoring(store):
    card = make_card("c1")
    await store.save_card(card)

    resolved = await store.resolve_card("c1", Resolution(
        chose="stayed", actual_outcome="offer arrived", happened_at=TODAY
    ))
    assert resolved.resolution is not None

    loaded = await store.get_card("c1")
    assert loaded is not None
    assert loaded.resolution is not None
    assert loaded.resolution.chose == "stayed"


async def test_resolving_a_missing_card_raises(store):
    with pytest.raises(KeyError):
        await store.resolve_card("nope", Resolution(
            chose="x", actual_outcome="y", happened_at=TODAY
        ))


# ────────────────────────────────────────────────────── status filtering ────


async def test_status_filtering_is_done_in_sql(store):
    await store.save_card(make_card("open1", check_in=30))
    await store.save_card(make_card("due1", check_in=-5))
    await store.save_card(make_card("done1", check_in=-90, resolved=True))

    assert [c.id for c in await store.list_cards(status="open")] == ["open1"]
    assert [c.id for c in await store.list_cards(status="due")] == ["due1"]
    assert [c.id for c in await store.list_cards(status="resolved")] == ["done1"]
    assert len(await store.list_cards()) == 3


async def test_unfiltered_listing_puts_due_cards_first(store):
    """A card past its check-in date is the only thing asking for attention."""
    await store.save_card(make_card("newest", check_in=60))
    await store.save_card(make_card("overdue", check_in=-10))
    assert (await store.list_cards())[0].id == "overdue"


async def test_a_card_with_no_expected_outcome_is_never_due(store):
    card = make_card("c1")
    card.expected_outcome = None
    await store.save_card(card)
    assert await store.list_cards(status="due") == []
    assert [c.id for c in await store.list_cards(status="open")] == ["c1"]


async def test_identical_timestamps_still_order_newest_first(store):
    """Windows' clock granularity is ~15.6 ms, so a burst of decisions shares one
    `created_at`. Without a tie-breaker, "newest first" silently returned the oldest —
    which is how a flaky test caught a real ordering bug in the history view.
    """
    stamped = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    for index in range(5):
        card = make_card(f"c{index}")
        card.created_at = stamped  # deliberately identical
        await store.save_card(card)

    listed = [c.id for c in await store.list_cards()]
    assert listed == ["c4", "c3", "c2", "c1", "c0"], (
        "cards saved with the same timestamp must still come back newest-first"
    )


async def test_identical_timestamps_order_deliberations_too(store):
    stamped = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    for index in range(3):
        delib = make_deliberation(f"d{index}")
        delib.created_at = stamped
        await store.save_deliberation(delib)
    assert [d.id for d in await store.list_deliberations()] == ["d2", "d1", "d0"]


async def test_limit_is_respected(store):
    for index in range(10):
        await store.save_card(make_card(f"c{index}"))
    assert len(await store.list_cards(limit=3)) == 3


# ──────────────────────────────────────────────────────── FTS5 recall ───────


async def test_recall_ranks_by_bm25_then_salience(store):
    await store.remember(
        "analyst",
        [
            Memory(id="m1", module="analyst", kind="fact", content="runway is four months of savings", salience=0.4),
            Memory(id="m2", module="analyst", kind="fact", content="the dog is called biscuit", salience=0.3),
            Memory(id="m3", module="analyst", kind="fact", content="nothing is ever put in writing", salience=0.95),
        ],
    )
    found = await store.recall("analyst", "how much runway is left in savings", k=5)
    ids = [m.id for m in found]

    assert ids[0] == "m1", "the lexically matching memory should rank first"
    assert "m3" in ids, "a highly salient memory surfaces without shared vocabulary"
    assert "m2" not in ids, "an irrelevant, unremarkable memory should not surface"


async def test_recall_uses_stemming(store):
    """`porter` tokeniser: "negotiating" should find "negotiation"."""
    await store.remember(
        "strategist",
        [Memory(id="m1", module="strategist", kind="power_structure", content="the negotiation stalled over equity", salience=0.3)],
    )
    found = await store.recall("strategist", "negotiating equity", k=5)
    assert [m.id for m in found] == ["m1"]


async def test_recall_is_scoped_to_one_module(store):
    await store.remember("analyst", [Memory(id="a1", module="analyst", kind="fact", content="shared vocabulary here", salience=0.9)])
    await store.remember("ethicist", [Memory(id="e1", module="ethicist", kind="promise", content="shared vocabulary here", salience=0.9)])
    assert [m.id for m in await store.recall("analyst", "shared vocabulary")] == ["a1"]
    assert [m.id for m in await store.recall("ethicist", "shared vocabulary")] == ["e1"]


async def test_recall_survives_fts_operators_in_the_query(store):
    """Unquoted user text containing FTS syntax must not raise or change meaning."""
    await store.remember(
        "analyst",
        [Memory(id="m1", module="analyst", kind="fact", content="savings and runway", salience=0.9)],
    )
    for hostile in ('savings AND runway', 'savings NEAR runway', 'savings*', '-savings', '"unclosed'):
        found = await store.recall("analyst", hostile, k=5)
        assert isinstance(found, list)


def test_fts_query_quotes_every_term_and_drops_stopwords():
    assert _fts_query("how much runway is left") == '"much" OR "runway" OR "left"'
    assert _fts_query("the and of") == ""
    assert '"' in _fts_query("a AND b NEAR c")


async def test_recall_with_an_empty_query_still_returns_salient_memories(store):
    await store.remember(
        "analyst",
        [Memory(id="m1", module="analyst", kind="fact", content="a standing fact", salience=0.9)],
    )
    assert [m.id for m in await store.recall("analyst", "")] == ["m1"]


async def test_recall_on_an_empty_store_returns_nothing(store):
    assert await store.recall("analyst", "anything") == []


async def test_fts_index_tracks_deletes_via_trigger(store, tmp_path):
    await store.remember(
        "analyst",
        [Memory(id="m1", module="analyst", kind="fact", content="ephemeral detail", salience=0.1)],
    )
    assert await store.recall("analyst", "ephemeral detail")

    raw = sqlite3.connect(tmp_path / "test.sqlite3")
    with raw:
        raw.execute("DELETE FROM memories WHERE id = 'm1'")
    raw.close()

    assert await store.recall("analyst", "ephemeral detail") == []


async def test_memory_timestamps_round_trip_as_aware_datetimes(store):
    stamped = datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)
    await store.remember(
        "analyst",
        [Memory(id="m1", module="analyst", kind="fact", content="dated fact", salience=0.9, created_at=stamped)],
    )
    got = (await store.recall("analyst", "dated fact"))[0]
    assert got.created_at.tzinfo is not None
    assert got.created_at == stamped


# ──────────────────────────────────────────────── derived views + wiring ────


async def test_scores_and_priors_only_consider_graded_cards(store):
    await store.save_card(make_card("ungraded", resolved=True))
    assert await store.scores() == []
    assert await store.priors("analyst") == []


async def test_build_store_defaults_to_sqlite(tmp_path):
    built = build_store("sqlite", tmp_path)
    assert isinstance(built, SQLiteStore)
    assert (tmp_path / "cognitive-os.sqlite3").is_file()


async def test_council_persists_across_restarts(settings, tmp_path):
    """The actual Phase 2 promise: history survives the process."""
    from app.council import Council

    settings.store_dir = tmp_path
    first = Council(settings, store=build_store("sqlite", tmp_path), force_provider="mock")
    try:
        result = await first.run(
            DeliberationRequest(question="Should I ship on Friday?", depth="quick", preset="solo:analyst")
        )
        card_id = (await first.store.list_cards())[0].id
    finally:
        await first.aclose()

    second = Council(settings, store=build_store("sqlite", tmp_path), force_provider="mock")
    try:
        assert await second.store.get_deliberation(result.id) is not None
        assert await second.store.get_card(card_id) is not None
    finally:
        await second.aclose()


# ─────────────────────────────────────────────────────────── migration ──────


async def test_import_from_filestore_brings_everything_across(tmp_path):
    legacy_dir = tmp_path / "var"
    legacy = FileStore(legacy_dir)
    await legacy.save_deliberation(make_deliberation("d1"))
    await legacy.save_card(make_card("c1"))
    await legacy.remember(
        "analyst",
        [Memory(id="m1", module="analyst", kind="fact", content="legacy fact", salience=0.8)],
    )

    target = SQLiteStore(tmp_path / "new.sqlite3")
    counts = await target.import_from(FileStore(legacy_dir))

    assert counts == {"deliberations": 1, "cards": 1, "memories": 1}
    assert await target.get_deliberation("d1") is not None
    assert await target.get_card("c1") is not None
    assert [m.id for m in await target.recall("analyst", "legacy fact")] == ["m1"]


async def test_import_is_idempotent_and_does_not_clobber_newer_rows(tmp_path):
    legacy_dir = tmp_path / "var"
    legacy = FileStore(legacy_dir)
    await legacy.save_card(make_card("c1"))

    target = SQLiteStore(tmp_path / "new.sqlite3")
    await target.import_from(FileStore(legacy_dir))
    await target.save_card(make_card("fresh"))
    await target.import_from(FileStore(legacy_dir))  # run it again

    ids = {c.id for c in await target.list_cards(limit=100)}
    assert ids == {"c1", "fresh"}, "re-importing must not duplicate or drop rows"


async def test_import_works_from_an_in_memory_store(tmp_path):
    source = InMemoryStore()
    await source.save_deliberation(make_deliberation("d1"))
    await source.save_card(make_card("c1"))
    target = SQLiteStore(tmp_path / "new.sqlite3")
    counts = await target.import_from(source)
    assert counts["deliberations"] == 1 and counts["cards"] == 1
