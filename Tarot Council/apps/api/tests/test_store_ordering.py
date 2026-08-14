"""Listing order, in both store implementations.

Split out because the bug this guards against was found by a *flaky* test rather than a
failing one, and it was real: on Windows the clock advances in ~15.6 ms steps, so several
decisions taken in one burst share an identical `created_at`. With the tie unbroken,
`list_cards()[0]` returned the oldest card while claiming to return the newest.

Parameterised over both stores because the ordering is implemented twice — once as a
Python sort and once as SQL — and a guarantee that holds in only one of them is not a
guarantee.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.memory.sqlite_store import SQLiteStore
from app.memory.store import FileStore, InMemoryStore

from .test_sqlite_store import make_card, make_deliberation

STAMP = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(params=["memory", "file", "sqlite"])
def store(request, tmp_path):
    if request.param == "memory":
        return InMemoryStore()
    if request.param == "file":
        return FileStore(tmp_path / "var")
    return SQLiteStore(tmp_path / "s.sqlite3")


async def test_cards_with_one_timestamp_come_back_newest_first(store):
    for index in range(5):
        card = make_card(f"c{index}")
        card.created_at = STAMP
        await store.save_card(card)
    assert [c.id for c in await store.list_cards()] == ["c4", "c3", "c2", "c1", "c0"]


async def test_distinct_timestamps_still_order_correctly(store):
    """The tie-breaker must not override a genuine timestamp difference."""
    for index in range(4):
        card = make_card(f"c{index}")
        # Saved in ascending time order, so the last saved is genuinely newest.
        card.created_at = STAMP + timedelta(minutes=index)
        await store.save_card(card)
    assert [c.id for c in await store.list_cards()] == ["c3", "c2", "c1", "c0"]


async def test_out_of_order_inserts_respect_the_timestamp(store):
    """Insertion order is only a tie-breaker, never the primary key of the sort."""
    newest = make_card("newest")
    newest.created_at = STAMP + timedelta(hours=1)
    oldest = make_card("oldest")
    oldest.created_at = STAMP

    await store.save_card(newest)  # inserted first, but genuinely newer
    await store.save_card(oldest)
    assert [c.id for c in await store.list_cards()] == ["newest", "oldest"]


async def test_deliberations_with_one_timestamp_order_newest_first(store):
    for index in range(4):
        delib = make_deliberation(f"d{index}")
        delib.created_at = STAMP
        await store.save_deliberation(delib)
    assert [d.id for d in await store.list_deliberations()] == ["d3", "d2", "d1", "d0"]


async def test_resaving_a_card_does_not_move_it_to_the_front(store):
    """An update is not a creation. Resolving an old card must not reorder history."""
    for index in range(3):
        card = make_card(f"c{index}")
        card.created_at = STAMP + timedelta(minutes=index)
        await store.save_card(card)

    stale = await store.get_card("c0")
    assert stale is not None
    await store.save_card(stale)  # e.g. after recording an outcome

    assert [c.id for c in await store.list_cards()] == ["c2", "c1", "c0"]
