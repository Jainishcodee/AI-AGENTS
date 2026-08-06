"""Program and preset loading, with the ten rules from SPEC-FORMAT.md.

Every rule is checked at import time and raises `ProgramInvalid`, so a malformed
program refuses to let the server start rather than failing halfway through
someone's deliberation.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..core.errors import ProgramInvalid
from ..engine.invariants import has_coverage
from ..schemas.artifacts import ARTIFACT_MODELS, TERMINAL_KIND
from ..schemas.common import ModuleId
from ..schemas.program import CONTEXT_REF, AgentProgram, Preset

PROGRAM_DIR = Path(__file__).parent
PRESET_FILE = PROGRAM_DIR / "presets.yaml"

SHARED_FORBIDDEN: tuple[str, ...] = (
    "Referencing fiction, mysticism, tarot, divination, or any in-world vocabulary.",
    "Claiming to be a person, or referring to a biography you do not have.",
    "Advising deception, fabricated leverage, or manufactured urgency.",
    "Stating a number or fact you cannot source.",
)
"""Merged into every program's `voice.forbidden`. A spec cannot opt out."""

MIN_SUCCESS_METRICS = 2


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProgramInvalid(f"{path.name}: invalid YAML — {exc}") from exc


def _validate(program: AgentProgram, source: str) -> None:
    def fail(rule: int, message: str) -> None:
        raise ProgramInvalid(f"{source} violates rule {rule}: {message}")

    # 1 — exactly one terminal stage, and it is last.
    terminals = [s for s in program.stages if s.terminal]
    if len(terminals) != 1:
        fail(1, f"expected exactly one terminal stage, found {len(terminals)}")
    if not program.stages[-1].terminal:
        fail(1, f"the terminal stage must be last, but '{program.stages[-1].id}' is")

    # 2 — only the terminal stage may produce a Conclusion.
    for stage in program.stages:
        if stage.produces == TERMINAL_KIND and not stage.terminal:
            fail(2, f"stage '{stage.id}' produces {TERMINAL_KIND} but is not terminal")
        if stage.terminal and stage.produces != TERMINAL_KIND:
            fail(2, f"terminal stage '{stage.id}' must produce {TERMINAL_KIND}")

    # 3 — reads reference `context` or an earlier stage. No forward refs, no cycles.
    seen: set[str] = set()
    for stage in program.stages:
        for ref in stage.reads:
            if ref != CONTEXT_REF and ref not in seen:
                fail(
                    3,
                    f"stage '{stage.id}' reads '{ref}', which is not 'context' and not "
                    "an earlier stage",
                )
        if not stage.reads:
            fail(3, f"stage '{stage.id}' reads nothing")
        seen.add(stage.id)

    if len({s.id for s in program.stages}) != len(program.stages):
        fail(3, "duplicate stage ids")

    # 4 — every produced type is registered and has invariant coverage.
    for stage in program.stages:
        if stage.produces not in ARTIFACT_MODELS:
            fail(4, f"stage '{stage.id}' produces unknown artifact '{stage.produces}'")
        if not has_coverage(stage.produces):
            fail(
                4,
                f"artifact '{stage.produces}' has no invariant validator; add one in "
                "engine/invariants.py or list it in NO_EXTRA_INVARIANTS",
            )

    # 5 — group keys are contiguous. A group cannot be interleaved, because grouped
    # stages become one call.
    order: list[str] = []
    for stage in program.stages:
        if not order or order[-1] != stage.group:
            if stage.group in order:
                fail(5, f"group '{stage.group}' is not contiguous")
            order.append(stage.group)

    # 6 — every stage forbids something. A stage with nothing it may not do is not a
    # distinct stage.
    for stage in program.stages:
        if not stage.must_not:
            fail(6, f"stage '{stage.id}' has an empty must_not")
        if not stage.instruction.strip():
            fail(6, f"stage '{stage.id}' has an empty instruction")

    # 7 — biases need a detector, and cannot be self-detected.
    for bias in program.biases:
        if not bias.watch_for.strip():
            fail(7, f"bias '{bias.id}' has no watch_for detector")
        if not bias.detectable_by:
            fail(7, f"bias '{bias.id}' has an empty detectable_by")
        if program.id in bias.detectable_by:
            fail(7, f"bias '{bias.id}' lists its own module as a detector")
    if not program.biases:
        fail(7, "no biases declared; every module has failure modes")

    # 8 — critics are non-empty and exclude self.
    if not program.critics:
        fail(8, "no critics declared")
    if program.id in program.critics:
        fail(8, "a module cannot critique itself")

    # 9 — at least two scoreable success metrics.
    if len(program.success_metrics) < MIN_SUCCESS_METRICS:
        fail(
            9,
            f"needs at least {MIN_SUCCESS_METRICS} success metrics; a module whose "
            "advice cannot be scored cannot be trusted with a confidence number",
        )

    # 10 — the shared constitution is merged in by `_load_one`; verify it took.
    for line in SHARED_FORBIDDEN:
        if line not in program.voice.forbidden:
            fail(10, "shared constitution was not merged into voice.forbidden")


def _load_one(path: Path) -> AgentProgram:
    raw = _read_yaml(path)
    if not isinstance(raw, dict):
        raise ProgramInvalid(f"{path.name}: expected a mapping at the top level")

    voice = dict(raw.get("voice") or {})
    forbidden = list(voice.get("forbidden") or [])
    for line in SHARED_FORBIDDEN:
        if line not in forbidden:
            forbidden.append(line)
    voice["forbidden"] = forbidden
    raw["voice"] = voice

    try:
        program = AgentProgram.model_validate(raw)
    except ValidationError as exc:
        raise ProgramInvalid(f"{path.name}: {exc}") from exc

    if program.id != path.stem:
        raise ProgramInvalid(f"{path.name}: id '{program.id}' does not match the filename")

    _validate(program, path.name)
    return program


@lru_cache(maxsize=1)
def programs() -> dict[ModuleId, AgentProgram]:
    found = {
        path.stem: _load_one(path)
        for path in sorted(PROGRAM_DIR.glob("*.yaml"))
        if path.name != PRESET_FILE.name
    }
    if not found:
        raise ProgramInvalid(f"no program YAML files found in {PROGRAM_DIR}")

    # Cross-program: every critic and detector must name a module that exists.
    for program in found.values():
        for critic in program.critics:
            if critic not in found:
                raise ProgramInvalid(
                    f"{program.id}: critic '{critic}' is not a known module"
                )
        for bias in program.biases:
            for detector in bias.detectable_by:
                if detector not in found:
                    raise ProgramInvalid(
                        f"{program.id}: bias '{bias.id}' names unknown detector '{detector}'"
                    )
    return found


def program(module: ModuleId) -> AgentProgram:
    try:
        return programs()[module]
    except KeyError as exc:
        known = ", ".join(sorted(programs()))
        raise ProgramInvalid(f"unknown module '{module}'. Known: {known}") from exc


@lru_cache(maxsize=1)
def presets() -> dict[str, Preset]:
    raw = _read_yaml(PRESET_FILE)
    if not isinstance(raw, list):
        raise ProgramInvalid("presets.yaml must be a list of presets")

    known = set(programs())
    out: dict[str, Preset] = {}
    for entry in raw:
        try:
            preset = Preset.model_validate(entry)
        except ValidationError as exc:
            raise ProgramInvalid(f"presets.yaml: {exc}") from exc
        if not preset.primary:
            raise ProgramInvalid(f"preset '{preset.id}' has no primary modules")
        participants = list(preset.participants)
        if len(participants) != len(set(participants)):
            raise ProgramInvalid(
                f"preset '{preset.id}' assigns a module to more than one role"
            )
        unknown = set(participants) - known
        if unknown:
            raise ProgramInvalid(
                f"preset '{preset.id}' names unknown modules: {', '.join(sorted(unknown))}"
            )
        out[preset.id] = preset
    return out


def preset(name: str) -> Preset:
    """Resolve a preset name, including the dynamic `solo:<module>` form."""
    if name.startswith("solo:"):
        module = name.split(":", 1)[1]
        if module not in programs():
            raise ProgramInvalid(f"unknown module '{module}' in preset '{name}'")
        others = tuple(m for m in sorted(programs()) if m != module)
        return Preset(
            id=name,
            name=f"Solo - {module}",
            description=f"{module} runs its full program; the others critique only.",
            primary=(module,),
            critic=others,
        )
    try:
        return presets()[name]
    except KeyError as exc:
        known = ", ".join(sorted(presets())) + ", solo:<module>"
        raise ProgramInvalid(f"unknown preset '{name}'. Known: {known}") from exc


def critique_matrix() -> dict[ModuleId, tuple[ModuleId, ...]]:
    """critic -> targets, derived from each program's own `critics` list.

    Routing is not configured separately; it falls out of the specs. Module M
    critiques T exactly when M appears in T.critics.
    """
    out: dict[ModuleId, list[ModuleId]] = {m: [] for m in programs()}
    for target, program_ in programs().items():
        for critic in program_.critics:
            out[critic].append(target)
    return {critic: tuple(sorted(targets)) for critic, targets in out.items()}
