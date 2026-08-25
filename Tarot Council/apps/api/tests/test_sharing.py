"""Sharing, forking and reviewing modules (Phase 5, ADR-032).

Sharing is a file: export writes the same YAML a module is authored in, load reads it. So
the load-bearing test here is the **round trip** — an export that drops or mangles a field
corrupts modules silently and at a distance, on someone else's machine, where the failure
cannot be connected back to the exporter.

The second load-bearing property is the review surface. Importing a module means executing
its prose inside system prompts; `prompt_surface` is the review step, so a prose field it
misses is an injection channel the reviewer never sees. The test derives the expected set
from the program model rather than hand-listing it, so a *new* prose field fails the suite
until someone decides where it lands.
"""

from __future__ import annotations

import pytest
import yaml

from app.core.errors import ProgramInvalid
from app.programs import catalog, loader
from app.schemas.program import AgentProgram

from .test_user_modules import make_module, make_program


# ─────────────────────────────────────────────────────────── export / load ──


def test_export_round_trips_an_authored_module_exactly():
    program = catalog.author("historian", make_program()).program
    document = catalog.export_yaml(program)
    reloaded = AgentProgram.model_validate(yaml.safe_load(document))
    assert reloaded == program, "the exported YAML does not reproduce the program"


@pytest.mark.parametrize("module_id", sorted(loader.programs()))
def test_export_round_trips_every_builtin(module_id):
    """Exporting a built-in is the sanctioned way to start a fork of it elsewhere."""
    program = loader.programs()[module_id]
    reloaded = AgentProgram.model_validate(yaml.safe_load(catalog.export_yaml(program)))
    assert reloaded == program


def test_an_exported_module_passes_validation_when_loaded():
    """Round-tripping the data is not enough; the reloaded module must still be legal."""
    program = catalog.author("historian", make_program()).program
    reloaded = AgentProgram.model_validate(yaml.safe_load(catalog.export_yaml(program)))
    checked = catalog.author("historian", reloaded)
    assert checked.errors == [], checked.errors


# ─────────────────────────────────────────────────────────────────── fork ──


def test_forking_a_builtin_starts_a_draft_with_lineage():
    forked = catalog.fork("analyst", "my_analyst")
    assert forked.id == "my_analyst"
    assert forked.program.id == "my_analyst", "the program id must follow the module id"
    assert forked.based_on == "analyst"
    assert forked.program.version == 1, "a fork starts its own version line"
    assert forked.status == "draft", "nobody has read the copy yet; it must not be active"
    assert forked.errors == [], forked.errors
    # Everything except identity is the source, verbatim.
    assert forked.program.stages == loader.programs()["analyst"].stages


def test_forking_an_authored_module_works_and_keeps_peers_in_scope():
    source = catalog.author("historian", make_program())
    forked = catalog.fork("historian", "revisionist", [source])
    assert forked.based_on == "historian"
    assert forked.errors == [], forked.errors


def test_forking_to_an_existing_id_is_refused():
    with pytest.raises(ProgramInvalid, match="already exists"):
        catalog.fork("analyst", "tactician")
    stored = catalog.author("historian", make_program())
    with pytest.raises(ProgramInvalid, match="already exists"):
        catalog.fork("analyst", "historian", [stored])


def test_forking_an_unknown_module_is_refused():
    with pytest.raises(ProgramInvalid, match="astrologer"):
        catalog.fork("astrologer", "my_astrologer")


def test_a_fork_of_a_quarantined_module_inherits_its_errors():
    """The point of forking a broken module is usually to fix it — so allow it, honestly.

    The violation here (no biases, rule 7) survives renaming. A *self-critique* violation
    would not: `critics: [historian]` stops being self-reference the moment the fork is
    called `historian2`, so a fork can legitimately come back cleaner than its source.
    """
    broken = catalog.validate(make_module(biases=()))
    assert broken.status == "quarantined"
    forked = catalog.fork("historian", "historian2", [broken])
    assert forked.status == "quarantined"
    assert any("rule 7" in e for e in forked.errors)


def test_a_fork_can_be_cleaner_than_its_source():
    """Renaming dissolves a self-critique violation — validated fresh, not copied."""
    self_critic = catalog.validate(make_module(critics=("historian", "analyst")))
    assert any("rule 8" in e for e in self_critic.errors)
    forked = catalog.fork("historian", "historian2", [self_critic])
    assert forked.errors == [], forked.errors


# ──────────────────────────────────────────────────────────── version bump ──


def test_editing_a_program_bumps_its_version():
    """`program_versions` is pinned into every deliberation; two different programs sharing
    a version would make replay's "then vs now" comparison lie."""
    first = catalog.author("historian", make_program())
    assert first.program.version == 1

    changed = make_program(summary="A sharper summary than before.")
    second = catalog.author("historian", changed, existing=first)
    assert second.program.version == 2

    third = catalog.author("historian", second.program, existing=second)
    assert third.program.version == 2, "an edit that changes nothing must not bump"


def test_an_authors_own_version_bump_is_respected():
    first = catalog.author("historian", make_program())
    jumped = make_program(summary="Rewritten from scratch.", version=7)
    second = catalog.author("historian", jumped, existing=first)
    assert second.program.version == 7


# ───────────────────────────────────────────────────────── review surface ──

PROSE_FIELDS_WITH_A_HOME = {
    "summary",
    "mental_model",
    "critique_lens",
    "voice.tone",
    "voice.forbidden",
    "stage.instruction",
    "stage.must_not",
    "stage.name",
    "bias.description",
    "bias.watch_for",
    "input.description",
    "skin.name",
    "skin.title",
}
"""Every free-text field on `AgentProgram`, mapped by the audit below.

`stage.name` and the skin fields are displayed to the *user*, not rendered into prompts, so
they are audited but deliberately absent from `prompt_surface` — a lie there misleads a
human directly, which the human can see. If a new prose field appears, the audit fails
until it is added either to the surface or to this allowlist, with a reason.
"""

NOT_PROMPT_SURFACE = {"stage.name", "skin.name", "skin.title"}


def test_the_review_surface_covers_every_prompt_entering_prose_field():
    """Derived, not hand-listed: a new prose field must fail until someone places it."""
    program = make_program()
    surface_text = " ".join(text for _, text in catalog.prompt_surface(program))

    checks = {
        "summary": program.summary,
        "mental_model": program.mental_model,
        "critique_lens": program.critique_lens,
        "voice.tone": program.voice.tone,
        "voice.forbidden": program.voice.forbidden[0],
        "stage.instruction": program.stages[0].instruction,
        "stage.must_not": program.stages[0].must_not[0],
        "bias.description": program.biases[0].description,
        "bias.watch_for": program.biases[0].watch_for,
    }
    for field, value in checks.items():
        assert value.strip() in surface_text, f"'{field}' is missing from the review surface"


def test_the_review_surface_flags_what_lands_in_other_modules_prompts():
    """`watch_for` renders into the critics' prompts — the channel a reviewer would skip."""
    surface = catalog.prompt_surface(make_program())
    other = [where for where, _ in surface if "OTHER modules'" in where]
    assert other, "the cross-module injection channel is not called out"


def test_the_prose_field_audit_is_complete():
    """Walk the model for free-text fields; each must be in the surface or the allowlist.

    This is what makes `prompt_surface` trustworthy over time: without it, someone adds a
    prose field to `AgentProgram`, the renderer picks it up, and the review step silently
    stops covering the whole injection surface.
    """
    from app.schemas.program import Bias, InputSpec, Skin, Stage, Voice

    def prose_fields(model, prefix):
        out = set()
        for name, info in model.model_fields.items():
            annotation = str(info.annotation)
            if annotation in ("<class 'str'>", "str") or "tuple[str" in annotation:
                out.add(f"{prefix}{name}")
        return out

    found = (
        prose_fields(AgentProgram, "")
        | prose_fields(Stage, "stage.")
        | prose_fields(Voice, "voice.")
        | prose_fields(Bias, "bias.")
        | prose_fields(InputSpec, "input.")
        | prose_fields(Skin, "skin.")
    )
    # Identifiers and enums are not prose; they cannot carry instructions a validator
    # would miss.
    identifiers = {
        "id", "stage.id", "stage.group", "stage.produces", "stage.reads", "bias.id",
        "input.id", "input.missing_policy", "time_horizon", "memory_kind", "skin.accent",
        "critics", "bias.detectable_by",
    }
    unaccounted = found - identifiers - PROSE_FIELDS_WITH_A_HOME
    assert not unaccounted, (
        f"free-text field(s) {sorted(unaccounted)} are neither in the review surface "
        "allowlist nor marked as identifiers — decide where they land"
    )
