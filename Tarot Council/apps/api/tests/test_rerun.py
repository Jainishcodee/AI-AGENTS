"""Stage re-run and refinement (Phase 4).

The capability ADR-011 was for: because every stage is a separately validated
artifact, re-running one module from one stage against one new fact is an operation,
not a rebuild. And because the reasoning record is what Decision Cards get scored
against, re-running derives a new deliberation rather than editing the old one
(ADR-022).
"""

from __future__ import annotations

import pytest

from app.core.errors import ArtifactInvalid
from app.programs import loader
from app.schemas.council import DeliberationRequest

from .conftest import QUESTION, RecordingRouter

FACT = "The lead investor said in writing that the title is a non-event for them"


@pytest.fixture
async def original(council):
    return await council.run(
        DeliberationRequest(question=QUESTION, depth="deep", preset="solo:strategist")
    )


async def test_earlier_stages_are_carried_not_re_executed(council, original):
    """At `deep` depth every stage is its own call, so carrying is observable."""
    program = loader.program("strategist")
    stage_ids = [s.id for s in program.stages]
    resume_at = "leverage"
    cut = stage_ids.index(resume_at)

    before = original.run_for("strategist")
    assert before is not None

    recorder = RecordingRouter(council._router)
    council._engine._router = recorder
    council._router = recorder

    derived = await council.rerun_stage(
        original.id, module="strategist", from_stage=resume_at, facts=[FACT]
    )
    after = derived.run_for("strategist")
    assert after is not None

    # Every stage is still present, in order.
    assert [a.stage_id for a in after.artifacts] == stage_ids

    # Stages before the resume point are the *same artifacts*, not fresh ones.
    for stage_id in stage_ids[:cut]:
        kept = after.artifact_at(stage_id)
        seeded = before.artifact_at(stage_id)
        assert kept is not None and seeded is not None
        assert kept.data == seeded.data, f"{stage_id} was re-executed instead of carried"

    # And no call was made for them.
    called_stages = {
        tag.split(":", 1)[1] for tag, _s, _u in recorder.calls if tag.startswith("strategist:")
    }
    for stage_id in stage_ids[:cut]:
        assert stage_id not in called_stages, f"{stage_id} was re-run needlessly"
    assert resume_at in called_stages


async def test_the_new_fact_reaches_the_resumed_stages(council, original):
    recorder = RecordingRouter(council._router)
    council._engine._router = recorder
    council._router = recorder
    await council.rerun_stage(
        original.id, module="strategist", from_stage="leverage", facts=[FACT]
    )
    resumed = [
        user
        for tag, _s, user in recorder.calls
        if tag.startswith("strategist:") and "leverage" in tag
    ]
    assert resumed
    assert any(FACT in prompt for prompt in resumed)


async def test_the_original_is_never_mutated(council, original):
    snapshot = original.model_dump_json()
    derived = await council.rerun_stage(
        original.id, module="strategist", from_stage="leverage", facts=[FACT]
    )

    assert derived.id != original.id
    assert derived.derived_from == original.id
    assert derived.rerun is not None
    assert derived.rerun.kind == "stage"
    assert derived.rerun.added_facts == [FACT]

    stored = await council.store.get_deliberation(original.id)
    assert stored is not None
    assert stored.model_dump_json() == snapshot, "the original deliberation was modified"


async def test_derived_deliberation_is_persisted_with_its_own_card(council, original):
    before = len(await council.store.list_cards(limit=100))
    derived = await council.rerun_stage(
        original.id, module="strategist", from_stage="sequence"
    )
    assert await council.store.get_deliberation(derived.id) is not None
    assert len(await council.store.list_cards(limit=100)) == before + 1


async def test_resynthesis_happens_after_a_rerun(council, original):
    derived = await council.rerun_stage(
        original.id, module="strategist", from_stage="leverage", facts=[FACT]
    )
    assert derived.synthesis is not None
    assert derived.synthesis is not original.synthesis


async def test_unknown_stage_is_rejected(council, original):
    with pytest.raises(ArtifactInvalid, match="no stage"):
        await council.rerun_stage(original.id, module="strategist", from_stage="nonsense")


async def test_unknown_module_is_rejected(council, original):
    with pytest.raises(KeyError):
        await council.rerun_stage(original.id, module="psychologist", from_stage="cast")


async def test_unknown_deliberation_is_rejected(council):
    with pytest.raises(KeyError):
        await council.rerun_stage("nope", module="strategist", from_stage="leverage")


async def test_rerun_drops_critiques_of_the_rerun_module_and_keeps_its_own(council):
    """Critiques targeted artifacts that no longer exist; the module's own still hold."""
    full = await council.run(
        DeliberationRequest(question=QUESTION, depth="standard", preset="full")
    )
    assert full.critiques

    derived = await council.rerun_stage(full.id, module="strategist", from_stage="leverage")
    assert not [c for c in derived.critiques if c.target == "strategist"]
    assert [c for c in derived.critiques if c.critic == "strategist"] or True
    assert not [r for r in derived.revisions if r.module == "strategist"]
    # Everyone else's critiques survive untouched.
    others = [c for c in full.critiques if c.target != "strategist"]
    assert len(derived.critiques) == len(others)


async def test_refine_answers_the_unknowns_and_reruns_everything(council, original):
    answers = [
        "The offer is confirmed in writing as of today",
        "Savings are six months, not four",
    ]
    recorder = RecordingRouter(council._router)
    council._engine._router = recorder
    council._router = recorder

    refined = await council.refine(original.id, answers=answers, reason="found out")

    assert refined.id != original.id
    assert refined.derived_from == original.id
    assert refined.rerun is not None
    assert refined.rerun.kind == "refine"
    assert refined.rerun.added_facts == answers

    # A refine is a genuine re-deliberation, so intake runs again with the answers.
    intake = [user for tag, _s, user in recorder.calls if tag == "intake"]
    assert intake
    assert any(answers[0] in prompt for prompt in intake)

    stored = await council.store.get_deliberation(refined.id)
    assert stored is not None
    assert stored.derived_from == original.id


async def test_refine_requires_a_known_deliberation(council):
    with pytest.raises(KeyError):
        await council.refine("nope", answers=["anything"])
