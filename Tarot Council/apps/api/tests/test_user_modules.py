"""User-authored modules: validation, quarantine, and the catalog (Phase 5, ADR-030).

The single most important property here is **a broken user module cannot take the server
down**. Built-in programs are validated loudly at boot on purpose, and inheriting that
behaviour for user content would mean a half-finished draft stops the process the author
would use to fix it. So these tests are largely about a module being *rejected without
anything else breaking*.

The second property is that user modules are held to the *same rulebook*. A separate,
laxer validator for user content would make "authored module" a synonym for "persona with a
prompt" and quietly repeal ADR-012 exactly where scrutiny is thinnest.
"""

from __future__ import annotations

import pytest

from app.core.errors import ProgramInvalid
from app.memory.store import InMemoryStore
from app.programs import catalog, loader
from app.schemas.module import UserModule
from app.schemas.program import AgentProgram

SHARED = loader.SHARED_FORBIDDEN


def make_program(module_id: str = "historian", **overrides) -> AgentProgram:
    """A minimal program that satisfies all ten rules.

    Deliberately built from artifact kinds that already exist and already have invariants:
    until the declarative artifact vocabulary lands, that is the only way a user module can
    satisfy rule 4, and pretending otherwise would make these tests lie about what works.
    """
    base = dict(
        id=module_id,
        version=1,
        skin={"name": "Historian", "title": "what happened last time", "accent": "#8a7f6a"},
        summary="Finds the closest prior cases and what they cost.",
        mental_model="Most decisions are not new. The base rate is the argument.",
        stages=(
            {
                "id": "precedents",
                "name": "Find precedents",
                "group": "gather",
                "reads": ("context",),
                "produces": "BaseRateTable",
                "instruction": "List comparable prior situations and how often each ended well.",
                "must_not": ("Recommending anything. This stage only gathers.",),
            },
            {
                "id": "commit",
                "name": "Commit",
                "group": "commit",
                "reads": ("precedents",),
                "produces": "Conclusion",
                "instruction": "State what the base rates imply, and your confidence.",
                "must_not": ("Citing a precedent not in the table above.",),
                "terminal": True,
            },
        ),
        biases=(
            {
                "id": "false_analogy",
                "description": "Treats a superficially similar case as a precedent.",
                "watch_for": "A precedent whose mechanism differs from this decision's.",
                "detectable_by": ("analyst", "strategist"),
            },
        ),
        critique_lens="Whether the claim survives the base rate.",
        critics=("analyst", "tactician"),
        success_metrics=(
            {"id": "precedent_held", "question": "Did the cited base rate hold?", "horizon_days": 90},
            {"id": "was_new", "question": "Was this genuinely without precedent?", "horizon_days": 30},
        ),
        voice={"tone": "dry", "forbidden": SHARED},
    )
    base.update(overrides)
    return AgentProgram.model_validate(base)


def make_module(module_id: str = "historian", **overrides) -> UserModule:
    return UserModule(id=module_id, program=make_program(module_id, **overrides))


# ────────────────────────────────────────────────────── the same rulebook ──


def test_a_well_formed_user_module_validates_clean():
    checked = catalog.validate(make_module())
    assert checked.errors == [], checked.errors
    assert checked.status == "draft", "validation must not promote a module by itself"


def test_a_user_module_is_held_to_the_same_rules_as_a_builtin():
    """Rule 8: a module cannot critique itself. Same rule, same message, user or not."""
    broken = make_module(critics=("historian",))
    checked = catalog.validate(broken)
    assert any("rule 8" in e for e in checked.errors), checked.errors
    assert checked.status == "quarantined"


def test_every_violation_is_reported_not_just_the_first():
    """An editor that reports one error per save is an editor nobody finishes in."""
    broken = make_module(critics=(), biases=(), success_metrics=())
    checked = catalog.validate(broken)
    rules = {e.split("violates rule ")[1].split(":")[0] for e in checked.errors}
    assert len(rules) >= 3, f"only reported rules {rules}: {checked.errors}"


def test_a_module_producing_an_unknown_artifact_is_rejected():
    """Rule 4 is what stops an authored module being a persona with a prompt (ADR-012).

    An artifact nobody can validate is an artifact whose content is whatever the model felt
    like, and a module built from those has no forced structure at all.
    """
    stages = list(make_program().stages)
    stages[0] = stages[0].model_copy(update={"produces": "MyOwnMadeUpArtifact"})
    checked = catalog.validate(make_module(stages=tuple(stages)))
    assert any("rule 4" in e and "MyOwnMadeUpArtifact" in e for e in checked.errors)


def test_a_module_naming_an_unknown_critic_is_rejected():
    checked = catalog.validate(make_module(critics=("astrologer",)))
    assert any("astrologer" in e for e in checked.errors), checked.errors


def test_a_module_whose_id_disagrees_with_its_program_is_rejected():
    """Two names for one module corrupts everything downstream of the trace.

    The catalog keys on `UserModule.id`, but the engine stamps `ModuleRun.module` from
    `program.id`. Let those diverge and a preset selects `economist` while the transcript,
    the scores and the extracted memories all say `historian` — with nothing failing.
    """
    checked = catalog.validate(
        UserModule(id="economist", program=make_program("historian"))
    )
    assert any("does not match" in e for e in checked.errors), checked.errors
    assert checked.status == "quarantined"


def test_a_module_cannot_shadow_a_builtin():
    """Two modules with one id would make every past trace citing it ambiguous."""
    checked = catalog.validate(make_module("analyst"))
    assert any("collides with a built-in" in e for e in checked.errors), checked.errors


def test_a_module_with_no_stages_is_rejected_without_crashing():
    """The guard that had to become explicit once violations accumulated rather than raised.

    With `fail` collecting instead of raising, the rule-1 check fell through to
    `stages[-1]` and would have raised IndexError from inside the validator.
    """
    checked = catalog.validate(make_module(stages=()))
    assert checked.errors and "no stages" in checked.errors[0]
    assert checked.status == "quarantined"


def test_fixing_a_module_clears_quarantine_but_does_not_activate_it():
    """Whether a module influences decisions is the author's call, not the validator's."""
    broken = catalog.validate(make_module(critics=("historian",)))
    assert broken.status == "quarantined"

    fixed = catalog.validate(broken.model_copy(update={"program": make_program()}))
    assert fixed.errors == []
    assert fixed.status == "draft", "a validator must not silently put a module into play"


# ──────────────────────────────────────────── nothing breaks the council ──


def test_the_builtin_loader_is_untouched_by_user_modules():
    """The loudness that protects built-ins must survive the addition of lenient loading."""
    assert set(loader.programs()) == {
        "analyst",
        "tactician",
        "strategist",
        "psychologist",
        "optimizer",
        "ethicist",
    }


def test_a_quarantined_module_is_not_runnable_and_not_in_the_program_map():
    broken = catalog.validate(make_module(critics=("historian",)))
    assert not broken.runnable
    assert "historian" not in catalog.programs([broken])
    # The built-ins are all still there. This is the property that matters.
    assert set(catalog.programs([broken])) == set(loader.programs())


def test_a_draft_module_is_stored_but_does_not_run():
    """Otherwise saving a module would immediately change every subsequent decision."""
    drafted = catalog.validate(make_module())
    assert drafted.status == "draft"
    assert "historian" not in catalog.programs([drafted])


def test_an_activated_module_joins_the_program_map():
    active = catalog.validate(make_module()).model_copy(update={"status": "active"})
    programs = catalog.programs([active])
    assert "historian" in programs
    assert programs["historian"].stages[-1].produces == "Conclusion"


def test_a_quarantined_module_still_appears_in_the_catalog_with_its_errors():
    """Hiding it leaves an author staring at a module they saved and cannot find."""
    broken = catalog.validate(make_module(critics=("historian",)))
    entries = {e.id: e for e in catalog.entries([broken])}
    assert entries["historian"].status == "quarantined"
    assert entries["historian"].errors
    assert entries["historian"].runnable is False
    assert entries["analyst"].origin == "builtin" and entries["analyst"].runnable


# ─────────────────────────────────────────────────────────────── presets ──


def test_with_preset_adds_an_authored_module_to_the_full_council():
    """The form the Phase 5 exit criterion needs: same six, plus one, same question."""
    active = catalog.validate(make_module()).model_copy(update={"status": "active"})
    preset = catalog.preset("with:historian", [active])
    assert "historian" in preset.primary
    assert set(loader.preset("full").primary).issubset(set(preset.primary))


def test_solo_works_for_an_authored_module():
    active = catalog.validate(make_module()).model_copy(update={"status": "active"})
    preset = catalog.preset("solo:historian", [active])
    assert preset.primary == ("historian",)
    assert "analyst" in preset.critic


def test_a_preset_naming_a_non_runnable_module_is_refused():
    drafted = catalog.validate(make_module())
    with pytest.raises(ProgramInvalid, match="historian"):
        catalog.preset("with:historian", [drafted])


def test_builtin_presets_still_resolve_through_the_catalog():
    assert catalog.preset("full").id == "full"
    assert catalog.preset("solo:analyst").primary == ("analyst",)


# ───────────────────────────────────────────────────────────── storage ──


# ──────────────────────────────────────────── authoring more than one ──


async def test_two_authored_modules_may_critique_each_other(council):
    """The chicken-and-egg that made authoring a *set* of modules impossible.

    `validate` knew only the built-ins plus the module in front of it, so two authored
    modules naming each other as critics were each rejected for naming an unknown module —
    and neither could ever be saved first. Iterating on a set of modules is the normal case,
    not an edge case.
    """
    historian = UserModule(
        id="historian", program=make_program("historian", critics=("analyst", "economist"))
    )
    economist = UserModule(
        id="economist", program=make_program("economist", critics=("analyst", "historian"))
    )

    await council.save_module(historian)
    saved = await council.save_module(economist)
    assert saved.errors == [], saved.errors

    # And the first one stops being wrong once its peer exists.
    revalidated = await council.save_module(historian)
    assert revalidated.errors == [], revalidated.errors


async def test_a_peer_that_does_not_exist_at_all_is_still_rejected():
    """Widening the known set must not turn rule 8 into a no-op."""
    checked = catalog.validate(
        UserModule(id="historian", program=make_program("historian", critics=("astrologer",))),
        peers=[UserModule(id="economist", program=make_program("economist"))],
    )
    assert any("astrologer" in e for e in checked.errors), checked.errors


# ──────────────────────────────────────── the shared constitution (rule 10) ──


def test_authoring_merges_the_shared_constitution():
    """The bug that made the HTTP route incapable of ever saving a valid module.

    `_load_one` merges `SHARED_FORBIDDEN` into every built-in's `voice.forbidden`, and rule
    10 then verifies it took. A program submitted as JSON never went through that merge, so
    rule 10 fired every time — four times over, once per missing line. A client would have
    had to reproduce the constitution verbatim to save anything.
    """
    bare = make_program().model_copy(
        update={"voice": make_program().voice.model_copy(update={"forbidden": ("Be vague.",)})}
    )
    assert not set(SHARED).issubset(set(bare.voice.forbidden))

    module = catalog.author("historian", bare)
    assert set(SHARED).issubset(set(module.program.voice.forbidden))
    assert module.errors == [], module.errors
    assert "Be vague." in module.program.voice.forbidden, "the author's own line was dropped"


def test_a_missing_constitution_is_reported_once_not_once_per_line():
    """Four identical messages for one problem is a worse error report than one."""
    bare = make_program().model_copy(
        update={"program": None} if False else {"voice": make_program().voice.model_copy(update={"forbidden": ()})}
    )
    errors = loader.rule_violations(bare, source="m")
    rule_ten = [e for e in errors if "rule 10" in e]
    assert len(rule_ten) == 1, rule_ten


# ─────────────────────────────────────────── retired modules stay readable ──


def test_a_retired_module_is_not_offered_for_new_decisions():
    retired = catalog.validate(make_module()).model_copy(update={"status": "retired"})
    assert not retired.runnable
    assert "historian" not in catalog.programs([retired])


def test_a_retired_module_can_still_be_reconstructed_for_replay():
    """ADR-030 keeps retired modules precisely so old traces stay explicable.

    Replay grades each module against what actually happened, so a card decided by a
    seven-module council has to be replayable by seven modules — otherwise the comparison
    silently comes back a row short, or fails with "unknown module" on a module that is
    sitting right there in the store.
    """
    retired = catalog.validate(make_module()).model_copy(update={"status": "retired"})
    programs = catalog.programs([retired], include_retired=True)
    assert "historian" in programs
    preset = catalog.preset("with:historian", [retired], include_retired=True)
    assert "historian" in preset.primary


def test_a_deleted_module_is_not_resurrected_by_include_retired():
    """`include_retired` must widen the set to *stored* modules only, not to anything."""
    with pytest.raises(ProgramInvalid, match="historian"):
        catalog.preset("with:historian", [], include_retired=True)


# ───────────────────────────────────────────────────────────── execution ──


async def test_an_authored_module_executes_through_the_unmodified_engine(council, context):
    """The whole point of ADR-011, cashed in.

    Because an agent is already "an ordered list of stages the runtime executes", a
    user-authored module needs *no* new execution path — the engine cannot tell it from a
    built-in, and there is no branch anywhere on where the program came from. If this test
    ever needs a special case, the marketplace has stopped being a storage problem and the
    design has gone wrong.
    """
    active = catalog.validate(make_module()).model_copy(update={"status": "active"})
    program = catalog.programs([active])["historian"]

    run = await council._engine.run_program(
        program, context=context, depth="quick", role="primary"
    )

    assert not run.abstained, run.abstain_reason
    assert [(a.stage_id, a.kind) for a in run.artifacts] == [
        ("precedents", "BaseRateTable"),
        ("commit", "Conclusion"),
    ]
    assert run.conclusion is not None and run.conclusion.stance
    assert run.usage.calls == 2, "one call per stage at quick depth"


async def test_an_authored_modules_artifacts_are_really_validated(council, context):
    """Otherwise "the same rulebook" is a claim about loading, not about running.

    `BaseRateTable` has a hand-written invariant, and the authored module goes through it
    exactly as the analyst does — so a module cannot escape validation by being authored.
    """
    from app.engine.invariants import has_coverage

    active = catalog.validate(make_module()).model_copy(update={"status": "active"})
    program = catalog.programs([active])["historian"]
    assert all(has_coverage(stage.produces) for stage in program.stages)

    run = await council._engine.run_program(
        program, context=context, depth="quick", role="primary"
    )
    table = next(a for a in run.artifacts if a.kind == "BaseRateTable")
    assert table.typed(), "the artifact did not survive being parsed by its own model"


# ───────────────────────────────────────────────────────────── storage ──


def test_the_runtime_status_tuple_agrees_with_the_literal():
    """They would otherwise drift, and `model_copy` does not re-validate to catch it."""
    from typing import get_args

    from app.schemas.module import MODULE_STATUSES, ModuleStatus

    assert set(get_args(ModuleStatus)) == set(MODULE_STATUSES)


async def test_an_unknown_status_is_refused_rather_than_stored(council):
    """`model_copy(update=...)` skips validation, so this has to be checked by hand.

    Without the guard, `set_module_status(id, "banana")` wrote `banana` to the store and
    every `status == "active"` comparison silently disagreed with it — a module in a state
    no code knows about.
    """
    from app.core.errors import CognitiveOSError

    await council.save_module(make_module())
    with pytest.raises(CognitiveOSError, match="unknown module status"):
        await council.set_module_status("historian", "banana")

    stored = await council.store.get_module("historian")
    assert stored is not None and stored.status == "draft"


async def test_a_module_round_trips_through_the_store():
    store = InMemoryStore()
    await store.save_module(catalog.validate(make_module()))

    found = await store.get_module("historian")
    assert found is not None
    assert found.program.stages[0].produces == "BaseRateTable"
    assert [m.id for m in await store.list_modules()] == ["historian"]

    await store.delete_module("historian")
    assert await store.get_module("historian") is None
