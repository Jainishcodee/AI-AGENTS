"""Projects and replay (Phase 2 remainder).

Replay is the more consequential of the two, and its correctness rests on one thing:
the re-run must not be able to read its own answer. Memories extracted from a card
describe what happened, and priors computed from it encode the verdict — hand a module
either and it scores well by cheating. Most of this file exists to prove that hole is
closed (ADR-025).
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.errors import CognitiveOSError
from app.memory.sqlite_store import SQLiteStore
from app.memory.store import InMemoryStore
from app.schemas.cards import Memory, Project, Resolution
from app.schemas.council import DeliberationRequest

from .conftest import QUESTION, RecordingRouter

TODAY = date.today()
OUTCOME = Resolution(
    chose="asked for it in writing", actual_outcome="it arrived nine days later", happened_at=TODAY
)


@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    """Both stores, because the exclusion logic is implemented twice.

    `recall` has a Python implementation and a SQL one; a leak guard that only holds in
    one of them is not a guard.
    """
    if request.param == "memory":
        return InMemoryStore()
    return SQLiteStore(tmp_path / f"{request.param}.sqlite3")


# ───────────────────────────────────────────────────────────── projects ─────


async def test_projects_round_trip(store):
    project = Project(id="p1", name="Leaving the internship", brief="ongoing")
    await store.save_project(project)

    loaded = await store.get_project("p1")
    assert loaded is not None
    assert loaded.name == "Leaving the internship"
    assert loaded.open is True
    assert [p.id for p in await store.list_projects()] == ["p1"]


async def test_missing_project_is_none(store):
    assert await store.get_project("nope") is None


async def test_closing_a_project_is_recorded(council):
    project = await council.create_project("Job hunt", "spring 2026")
    closed = await council.close_project(project.id)
    assert closed.closed_at is not None
    assert closed.open is False

    reloaded = await council.store.get_project(project.id)
    assert reloaded is not None and reloaded.closed_at is not None


async def test_closing_an_unknown_project_raises(council):
    with pytest.raises(KeyError):
        await council.close_project("nope")


async def test_deliberating_in_a_project_tags_the_card_and_deliberation(council):
    project = await council.create_project("Job hunt")
    result = await council.run(
        DeliberationRequest(
            question=QUESTION, depth="quick", preset="solo:analyst", project_id=project.id
        )
    )
    assert result.project_id == project.id
    card = (await council.store.list_cards())[0]
    assert card.project_id == project.id


async def test_memories_inherit_the_project_from_their_card(council):
    project = await council.create_project("Job hunt")
    await council.run(
        DeliberationRequest(
            question=QUESTION, depth="quick", preset="solo:analyst", project_id=project.id
        )
    )
    card = (await council.store.list_cards())[0]
    await council.resolve(card.id, OUTCOME)

    remembered = await council.store.recall("analyst", QUESTION, k=10)
    assert remembered
    assert all(m.project_id == project.id for m in remembered)


async def test_project_memories_outrank_merely_similar_ones(store):
    """The whole point: a salary conversation should not drag in a side project."""
    await store.remember(
        "analyst",
        [
            Memory(
                id="off",
                module="analyst",
                kind="fact",
                content="the deployment pipeline is flaky",
                salience=0.5,
                project_id="other",
            ),
            Memory(
                id="on",
                module="analyst",
                kind="fact",
                content="the deployment pipeline is flaky",
                salience=0.5,
                project_id="mine",
            ),
        ],
    )
    found = await store.recall("analyst", "deployment pipeline", k=2, project_id="mine")
    assert [m.id for m in found][0] == "on"


async def test_project_memory_surfaces_without_lexical_overlap(store):
    await store.remember(
        "analyst",
        [
            Memory(
                id="m1",
                module="analyst",
                kind="fact",
                content="nothing here shares any words",
                salience=0.2,
                project_id="mine",
            )
        ],
    )
    found = await store.recall("analyst", "completely unrelated question", project_id="mine")
    assert [m.id for m in found] == ["m1"]


# ────────────────────────────────────────────────── the replay leak guard ───


async def test_recall_excludes_memories_from_a_named_card(store):
    await store.remember(
        "analyst",
        [
            Memory(id="leak", module="analyst", kind="fact", content="the offer arrived", salience=0.9, source_card_id="c1"),
            Memory(id="fine", module="analyst", kind="fact", content="the offer arrived", salience=0.9, source_card_id="c2"),
        ],
    )
    assert {m.id for m in await store.recall("analyst", "the offer arrived", k=5)} == {"leak", "fine"}

    guarded = await store.recall(
        "analyst", "the offer arrived", k=5, exclude_cards=frozenset({"c1"})
    )
    assert [m.id for m in guarded] == ["fine"], "a memory from the excluded card leaked through"


async def test_priors_exclude_the_named_card(council):
    """Four graded cards make a prior; excluding one must change the count."""
    for index in range(4):
        await council.run(
            DeliberationRequest(
                question=f"{QUESTION} ({index})", depth="quick", preset="solo:analyst"
            )
        )
        card = (await council.store.list_cards())[0]
        await council.resolve(card.id, OUTCOME)

    cards = await council.store.list_cards(limit=10)
    everything = await council.store.priors("analyst")
    assert everything, "four graded cards should produce a prior"

    guarded = await council.store.priors(
        "analyst", exclude_cards=frozenset({cards[0].id})
    )
    counts_all = {p.pattern[:30]: p.evidence_count for p in everything}
    counts_guarded = {p.pattern[:30]: p.evidence_count for p in guarded}
    assert counts_guarded != counts_all, "excluding a card did not change the priors"
    for key, count in counts_guarded.items():
        assert count <= counts_all.get(key, count)


async def test_replay_never_sees_its_own_card(council):
    """The load-bearing test. A replay that reads its own outcome measures nothing."""
    await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="solo:analyst")
    )
    card = (await council.store.list_cards())[0]
    await council.resolve(
        card.id,
        Resolution(
            chose="asked in writing",
            actual_outcome="THE-GIVEAWAY-STRING appeared in the outcome",
            happened_at=TODAY,
        ),
    )

    # Plant a memory that would give the answer away, attributed to this card.
    await council.store.remember(
        "analyst",
        [
            Memory(
                id="leak",
                module="analyst",
                kind="fact",
                content="THE-GIVEAWAY-STRING is what happened",
                salience=0.95,
                source_card_id=card.id,
            )
        ],
    )
    # And one from a different card, which is legitimate context.
    await council.store.remember(
        "analyst",
        [
            Memory(
                id="legit",
                module="analyst",
                kind="fact",
                content="this user rarely gets anything in writing",
                salience=0.95,
                source_card_id="some-other-card",
            )
        ],
    )

    recorder = RecordingRouter(council._router)
    council._router = recorder
    council._engine._router = recorder

    result = await council.replay(card.id)

    prompts = [user for tag, _s, user in recorder.calls if tag.startswith("analyst:")]
    assert prompts
    assert not any("THE-GIVEAWAY-STRING" in p for p in prompts), (
        "the replay was shown a memory extracted from the card it was re-deciding"
    )
    assert any("rarely gets anything in writing" in p for p in prompts), (
        "legitimate memories from other cards should still be available"
    )
    assert result.excluded_memories >= 1, "the withheld count should be reported"


async def test_replay_reports_then_and_now_per_module(council):
    await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="full")
    )
    card = (await council.store.list_cards())[0]
    await council.resolve(card.id, OUTCOME)

    result = await council.replay(card.id)
    assert result.card_id == card.id
    assert result.replay_deliberation_id != result.original_deliberation_id
    assert {m.module for m in result.modules} == {
        "analyst",
        "tactician",
        "strategist",
        "psychologist",
        "optimizer",
        "ethicist",
    }
    for module in result.modules:
        assert module.then_stance, f"{module.module} has no original stance"
        assert module.then_verdict is not None, f"{module.module} has no original verdict"
    assert isinstance(result.improved, int)
    assert isinstance(result.regressed, int)


async def test_replay_records_the_program_versions_on_both_sides(council):
    """Without this, a comparison across a program change is meaningless."""
    await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="solo:strategist")
    )
    card = (await council.store.list_cards())[0]
    await council.resolve(card.id, OUTCOME)

    result = await council.replay(card.id)
    assert result.program_versions_then
    assert result.program_versions_now
    assert result.program_versions_now["strategist"] >= 1


async def test_replay_does_not_disturb_the_original(council):
    await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="solo:analyst")
    )
    card = (await council.store.list_cards())[0]
    await council.resolve(card.id, OUTCOME)

    before = (await council.store.get_card(card.id)).model_dump_json()  # type: ignore[union-attr]
    original = await council.store.get_deliberation(card.deliberation_id)
    assert original is not None
    original_json = original.model_dump_json()

    await council.replay(card.id)

    after = await council.store.get_card(card.id)
    assert after is not None and after.model_dump_json() == before, "the card was modified"
    still = await council.store.get_deliberation(card.deliberation_id)
    assert still is not None and still.model_dump_json() == original_json


async def test_replay_refuses_an_unresolved_card(council):
    await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="solo:analyst")
    )
    card = (await council.store.list_cards())[0]
    with pytest.raises(CognitiveOSError, match="not resolved"):
        await council.replay(card.id)


async def test_replay_refuses_an_unknown_card(council):
    with pytest.raises(KeyError):
        await council.replay("nope")


async def test_replay_is_linked_to_the_original(council):
    await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="solo:analyst")
    )
    card = (await council.store.list_cards())[0]
    await council.resolve(card.id, OUTCOME)
    result = await council.replay(card.id)

    replayed = await council.store.get_deliberation(result.replay_deliberation_id)
    assert replayed is not None
    assert replayed.derived_from == result.original_deliberation_id
    assert replayed.rerun is not None
    assert card.id in (replayed.rerun.reason or "")
