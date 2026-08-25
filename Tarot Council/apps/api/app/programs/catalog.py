"""The set of modules available to run: built-ins plus valid user-authored ones.

`loader.programs()` stays exactly as it was — YAML from the package directory, validated at
boot, fatal on error. This module wraps it rather than replacing it, so the guarantee that a
broken *built-in* refuses to start the server is untouched (ADR-030).

Everything here is a pure function of (built-ins, user modules). The catalog is not cached:
authoring changes it, `loader.programs()` is already `lru_cache`d behind it, and a stale
module list during editing would be far more confusing than the cost of rebuilding a dict.
"""

from __future__ import annotations

from ..core.logging import get_logger
from ..schemas.common import ModuleId
from ..schemas.module import ModuleCatalogEntry, UserModule
from ..schemas.program import AgentProgram, Preset
from . import loader

log = get_logger(__name__)


def author(
    module_id: ModuleId,
    program: AgentProgram,
    *,
    existing: UserModule | None = None,
    peers: list[UserModule] | None = None,
) -> UserModule:
    """Build and validate an authored module from a submitted program.

    The single entry point for authoring, and it exists because there were two: the CLI
    merged the shared constitution before validating and the HTTP route did not, so the
    route could never save a valid module — rule 10 fired on every request. One function,
    one behaviour.

    `existing` preserves what belongs to the record rather than to the program: when it is
    set, this is an edit, so the original creation time and the author's decision about
    whether the module is in play both survive.
    """
    program = loader.with_constitution(program)

    if existing is not None and program != existing.program:
        # An edit that changes the program must change the version, because the version is
        # what makes stored records interpretable: deliberations pin `program_versions`,
        # and replay compares "the program then" against "the program now". Two different
        # programs sharing a version number would make both records quietly lie. The author
        # may bump further themselves; this only refuses to let the number stand still.
        if program.version <= existing.program.version:
            program = program.model_copy(update={"version": existing.program.version + 1})

    module = UserModule(id=module_id, program=program)
    if existing is not None:
        module = module.model_copy(
            update={
                "created_at": existing.created_at,
                "status": existing.status,
                "based_on": existing.based_on,
            }
        )
    return validate(module, peers=peers)


def validate(module: UserModule, *, peers: list[UserModule] | None = None) -> UserModule:
    """Re-check a user module against the same rulebook as the built-ins.

    Returns a copy carrying the verdict. Called on save rather than on load, so authoring
    gets immediate feedback and a running deliberation never pays for validation — but also
    called on activation, because the rules can change under a stored module when the
    built-ins do (rule 8 in particular: a module whose only critic was retired is no longer
    valid).

    `peers` are the other stored modules. Without them, two authored modules naming each
    other as critics were each rejected for referencing an unknown module and neither could
    ever be saved first — a chicken-and-egg that made authoring a *set* of modules
    impossible, which is the normal case rather than an edge one.
    """
    errors = loader.rule_violations(module.program, source=f"module '{module.id}'")

    # Two names for one module corrupts everything downstream of the trace. The catalog keys
    # on `UserModule.id`; the engine stamps `ModuleRun.module` from `program.id`. Let those
    # diverge and a preset selects one name while the transcript, the calibration scores and
    # the extracted memories all record the other — with nothing failing anywhere.
    if module.program.id != module.id:
        errors.append(
            f"module '{module.id}' does not match its program id '{module.program.id}'; "
            "they key different things and would disagree in every stored record"
        )

    # Cross-program: a critic or bias detector naming a module nobody has is a real defect,
    # and it is the one the author is most likely to hit while iterating on a set of modules.
    #
    # Peers count as known even when quarantined or retired, so a set of modules can be
    # written in any order. The cost is real and worth naming: if every critic a module
    # names happens to be non-runnable, that module effectively has no critics at run time,
    # which weakens rule 7's guarantee that declared biases get caught by somebody. Blocking
    # the author outright is the worse trade — but it is a weakening, not a free lunch.
    known = set(loader.programs()) | {module.id} | {p.id for p in peers or []}
    for critic in module.program.critics:
        if critic not in known:
            errors.append(f"module '{module.id}': critic '{critic}' is not a known module")
    for bias in module.program.biases:
        for detector in bias.detectable_by:
            if detector not in known:
                errors.append(
                    f"module '{module.id}': bias '{bias.id}' names unknown detector "
                    f"'{detector}'"
                )

    if module.id in loader.programs():
        errors.append(
            f"module '{module.id}' collides with a built-in; pick another id rather than "
            "shadowing it — a deliberation citing this id would be ambiguous forever"
        )

    status = module.status
    if errors:
        status = "quarantined"
    elif status == "quarantined":
        # It was quarantined and the problems are gone. Returning it to `draft` rather than
        # `active` is deliberate: the author decides when a module starts influencing
        # decisions, not the validator.
        status = "draft"

    return module.model_copy(update={"errors": errors, "status": status})


def programs(
    user_modules: list[UserModule] | None = None, *, include_retired: bool = False
) -> dict[ModuleId, AgentProgram]:
    """Built-in programs plus every runnable user module, keyed by id.

    A quarantined or draft module is absent, so nothing downstream — the engine, the
    critique matrix, the trace — needs to know that user modules exist at all.

    `include_retired` widens the set to modules that were deliberately withdrawn but are
    still *stored*. Replay and stage re-run need it: a card decided by a seven-module council
    has to be re-decidable by seven modules, or the graded comparison silently comes back a
    row short. It never resurrects a module that was deleted — only one the author retired,
    which ADR-030 keeps precisely so old traces stay explicable.
    """
    out: dict[ModuleId, AgentProgram] = dict(loader.programs())
    for module in user_modules or []:
        eligible = module.runnable or (include_retired and module.status == "retired")
        if not eligible:
            continue
        if module.id in out:
            # Should be impossible: `validate` rejects built-in collisions. Refusing here
            # too, because silently shadowing a built-in would make an old trace unreadable.
            log.warning("user module '%s' collides with a built-in; ignoring", module.id)
            continue
        out[module.id] = module.program
    return out


def entries(user_modules: list[UserModule] | None = None) -> list[ModuleCatalogEntry]:
    """Everything authored or built in, listed uniformly — including what is broken.

    Quarantined modules appear *with* their errors. Hiding them would leave an author staring
    at a module they saved and cannot find.
    """
    out = [
        ModuleCatalogEntry(
            id=module_id,
            origin="builtin",
            status="active",
            runnable=True,
            summary=program.summary.strip(),
            stages=len(program.stages),
        )
        for module_id, program in sorted(loader.programs().items())
    ]
    out.extend(
        ModuleCatalogEntry(
            id=module.id,
            origin="user",
            status=module.status,
            runnable=module.runnable,
            summary=module.program.summary.strip(),
            stages=len(module.program.stages),
            errors=list(module.errors),
        )
        for module in sorted(user_modules or [], key=lambda m: m.id)
    )
    return out


def fork(
    source_id: ModuleId,
    new_id: ModuleId,
    user_modules: list[UserModule] | None = None,
) -> UserModule:
    """Copy a module — built-in or authored — under a new id, keeping lineage.

    Forking a built-in is the expected first authoring move: copy the analyst, change what
    you disagree with. The fork starts its own version line at 1, records `based_on`, and
    lands as a draft like anything else authored — a fork of an active module must not be
    active by inheritance, because nobody has read the copy yet.

    Any stored module can be forked, quarantined ones included: the fork inherits the
    errors and the point of forking a broken module is usually to fix it.
    """
    stored = {m.id: m for m in user_modules or []}
    if source_id in stored:
        source_program = stored[source_id].program
    elif source_id in loader.programs():
        source_program = loader.programs()[source_id]
    else:
        raise _unknown_module(source_id, programs(user_modules, include_retired=True))

    if new_id in loader.programs() or new_id in stored:
        from ..core.errors import ProgramInvalid

        raise ProgramInvalid(
            f"cannot fork to '{new_id}': a module with that id already exists"
        )

    forked = source_program.model_copy(update={"id": new_id, "version": 1})
    module = UserModule(id=new_id, program=forked, based_on=source_id)
    return validate(module, peers=list(stored.values()))


def export_yaml(program: AgentProgram) -> str:
    """A module as a file — the entire sharing mechanism (ADR-032).

    The exported document is the same YAML the module was authored in, so sharing needs no
    server, no registry and no format of its own: `--export` on one machine, `--load` on
    another. Round-tripping is pinned by a test, because an export that drops a field would
    corrupt modules silently and at a distance.
    """
    import yaml

    return yaml.safe_dump(
        program.model_dump(mode="json"),
        sort_keys=False,
        allow_unicode=True,
        width=96,
    )


def prompt_surface(program: AgentProgram) -> list[tuple[str, str]]:
    """Every prose string this module injects into a prompt, labelled with where it lands.

    This is the review step for imported modules (ADR-032). Activating a module means
    executing its prose inside system prompts, which makes an imported module a prompt
    injection with extra steps — and the two least obvious channels are the ones a reviewer
    would skip: `watch_for` is rendered into *other* modules' critique prompts, and
    `voice.forbidden` reads as safety text while being arbitrary instruction.

    Structural fields (columns, ranges, reads) are deliberately absent: they are enforced by
    validators, so lying in them fails loudly. Prose is the part that is only ever advisory,
    which is exactly why it is the part to read.
    """
    surface: list[tuple[str, str]] = [
        ("system prompt · summary", program.summary.strip()),
        ("system prompt · mental model", program.mental_model.strip()),
    ]
    if program.voice.tone:
        surface.append(("system prompt · register", program.voice.tone.strip()))
    for line in program.voice.forbidden:
        surface.append(("system prompt · never-do rule", line))
    for stage in program.stages:
        surface.append((f"stage '{stage.id}' · instruction", stage.instruction.strip()))
        for rule in stage.must_not:
            surface.append((f"stage '{stage.id}' · must-not", rule))
    surface.append(("critique prompts · lens", program.critique_lens.strip()))
    for bias in program.biases:
        surface.append(
            (f"OTHER modules' critique prompts · bias '{bias.id}'", bias.description.strip())
        )
        surface.append(
            (f"OTHER modules' critique prompts · '{bias.id}' fires when", bias.watch_for.strip())
        )
    for spec in (*program.inputs.required, *program.inputs.optional):
        surface.append((f"intake · input '{spec.id}'", spec.description.strip()))
    return [(where, text) for where, text in surface if text]


def preset(
    name: str,
    user_modules: list[UserModule] | None = None,
    *,
    include_retired: bool = False,
) -> Preset:
    """Resolve a preset, extended to accept user modules in `solo:` and `with:` forms.

    `with:<module>` is the form the Phase 5 exit criterion needs: the built-in six as primary,
    plus one authored module, on the same question — so its effect on the recommendation is
    measurable against the same council rather than against a different one.

    Named presets (`full`, `strategy`, …) are curated lists and deliberately do **not** pick
    up authored modules: activating a module must not silently change what `full` means. Use
    `with:<module>` to add one.
    """
    available = programs(user_modules, include_retired=include_retired)

    if name.startswith("with:"):
        extra = name.split(":", 1)[1]
        if extra not in available:
            raise _unknown_module(extra, available)
        base = loader.preset("full")
        if extra in base.participants:
            return base
        return Preset(
            id=name,
            name=f"Full council + {extra}",
            description=f"The built-in council, with {extra} added as a primary module.",
            primary=base.primary + (extra,),
            advisory=base.advisory,
            critic=base.critic,
        )

    if name.startswith("solo:"):
        module = name.split(":", 1)[1]
        if module not in available:
            raise _unknown_module(module, available)
        others = tuple(m for m in sorted(available) if m != module)
        return Preset(
            id=name,
            name=f"Solo - {module}",
            description=f"{module} runs its full program; the others critique only.",
            primary=(module,),
            critic=others,
        )

    return loader.preset(name)


def _unknown_module(module: ModuleId, available: dict[ModuleId, AgentProgram]):
    from ..core.errors import ProgramInvalid

    return ProgramInvalid(
        f"unknown module '{module}'. Available: {', '.join(sorted(available))}"
    )
