"""A checkpoint is worthless unless it outlives the process that wrote it.

`tests/test_resume.py` covers the resume *logic*, but it runs against `InMemoryStore`, so
it says nothing about durability. That gap hid a real bug: `FileStore` inherited
`save_checkpoint` from `InMemoryStore`, so under the legacy JSON store every checkpoint
lived in RAM and vanished on restart — silently, because `list_checkpoints` simply came
back empty and looked like "nothing was interrupted".

It was found by resuming in a genuinely separate OS process (`scripts/phase4_exit.py`),
not by a test, which is the lesson these tests encode: the durable stores are re-opened
over the same directory and asked again.
"""

from __future__ import annotations

import pytest

from app.memory.sqlite_store import SQLiteStore
from app.memory.store import FileStore, InMemoryStore
from app.schemas.cards import Project
from app.schemas.checkpoint import Checkpoint
from app.schemas.council import DeliberationRequest

QUESTION = "Should I take the smaller offer with equity?"


def make_checkpoint(deliberation_id: str, *, phase: str = "reason") -> Checkpoint:
    return Checkpoint(
        deliberation_id=deliberation_id,
        request=DeliberationRequest(question=QUESTION, depth="quick", preset="full"),
        preset="full",
        depth="quick",
        phase=phase,
    )


def reopen(store):
    """A second store instance over the same storage — the stand-in for a restart."""
    if isinstance(store, SQLiteStore):
        return SQLiteStore(store._path)
    if isinstance(store, FileStore):
        return FileStore(store._root)
    raise TypeError(f"{type(store).__name__} is not durable")


@pytest.fixture(params=["sqlite", "file"])
def durable(request, tmp_path):
    """Both stores that claim to survive a restart. `memory` is excluded by definition."""
    if request.param == "sqlite":
        return SQLiteStore(tmp_path / "test.sqlite3")
    return FileStore(tmp_path / "var")


async def test_a_checkpoint_survives_a_restart(durable):
    await durable.save_checkpoint(make_checkpoint("d1"))

    revived = reopen(durable)
    found = await revived.get_checkpoint("d1")
    assert found is not None, "the checkpoint did not outlive the process"
    assert found.deliberation_id == "d1"
    assert found.request.question == QUESTION
    assert found.phase == "reason"


async def test_an_unfinished_checkpoint_is_listed_after_a_restart(durable):
    """The silent form of the bug: `list_checkpoints` returning nothing reads as
    "nothing was interrupted" rather than as "the checkpoint was lost"."""
    await durable.save_checkpoint(make_checkpoint("d1"))
    await durable.save_checkpoint(make_checkpoint("d2"))

    revived = reopen(durable)
    assert {c.deliberation_id for c in await revived.list_checkpoints()} == {"d1", "d2"}


async def test_a_finished_checkpoint_is_not_offered_for_resume(durable):
    await durable.save_checkpoint(make_checkpoint("d1", phase="done"))
    assert await reopen(durable).list_checkpoints() == []


async def test_discarding_a_checkpoint_survives_a_restart_too(durable):
    """Otherwise a discarded deliberation reappears on the next boot."""
    await durable.save_checkpoint(make_checkpoint("d1"))
    await durable.delete_checkpoint("d1")

    revived = reopen(durable)
    assert await revived.get_checkpoint("d1") is None
    assert await revived.list_checkpoints() == []


async def test_a_resaved_checkpoint_advances_rather_than_duplicating(durable):
    await durable.save_checkpoint(make_checkpoint("d1", phase="reason"))
    await durable.save_checkpoint(make_checkpoint("d1", phase="critique"))

    revived = reopen(durable)
    listed = await revived.list_checkpoints()
    assert len(listed) == 1, "a deliberation must not accumulate one row per phase"
    assert listed[0].phase == "critique"


async def test_projects_survive_a_restart(durable):
    """The same inherited-from-InMemoryStore gap, found in the same place."""
    await durable.save_project(Project(id="p1", name="Leaving the internship"))

    revived = reopen(durable)
    found = await revived.get_project("p1")
    assert found is not None and found.name == "Leaving the internship"
    assert [p.id for p in await revived.list_projects()] == ["p1"]


async def test_user_modules_survive_a_restart(durable):
    """A module you authored and cannot find after a restart is worse than no builder."""
    from tests.test_user_modules import make_module

    await durable.save_module(make_module("historian"))

    revived = reopen(durable)
    found = await revived.get_module("historian")
    assert found is not None
    assert found.program.stages[0].produces == "BaseRateTable"
    assert [m.id for m in await revived.list_modules()] == ["historian"]

    await revived.delete_module("historian")
    assert await reopen(revived).get_module("historian") is None


async def test_the_in_memory_store_is_the_only_one_that_forgets():
    """Stated as a test so `memory` being non-durable stays a deliberate choice.

    If `InMemoryStore` ever gains persistence, this fails and the fixture above should
    grow a third parameter rather than the exclusion being silently wrong.
    """
    store = InMemoryStore()
    await store.save_checkpoint(make_checkpoint("d1"))
    assert await store.get_checkpoint("d1") is not None
    assert not hasattr(store, "_root"), "InMemoryStore is not expected to have storage"


async def test_file_store_overrides_every_write_path_it_inherits():
    """The class of bug, not the instance.

    `FileStore` subclasses `InMemoryStore`, so any *new* write method added to the parent
    is inherited as a RAM-only no-op and loses data silently. This fails the moment that
    happens, naming the method that needs an override.
    """
    written = {
        name
        for name in vars(InMemoryStore)
        if name.startswith(("save_", "delete_", "remember", "resolve_", "attach_"))
    }
    overridden = set(vars(FileStore))
    # `resolve_card` and `attach_scoring` go through `save_card`, so they are durable
    # without their own override.
    delegating = {"resolve_card", "attach_scoring"}
    missing = written - overridden - delegating
    assert not missing, (
        f"FileStore inherits RAM-only write path(s) {sorted(missing)} — "
        "each one silently loses data on restart"
    )
