"""The divergence harness.

The product claims these are six algorithms rather than six voices. That is falsifiable,
so it should be measured rather than asserted — and it is also the gate a Phase 5
marketplace module must pass, because "sounds different" is not a contribution.

Split by cost:

- `structural()` reads only the specs. Artifact distinctness and critique topology are
  properties of the YAML, so this runs instantly and belongs in CI.
- `measure()` runs the council over a fixed battery. Opt-in: on a free tier it is minutes
  and real quota.

The live measurement deliberately **reuses what synthesis already produces** —
`minority_opinions` for dissent, `disagreements` for named conflict, `Revision.accepted`
for critique yield — rather than inventing a second disagreement detector. A second
detector could contradict the first, and then neither would be trustworthy. The cost of
that choice is named in `LIMITATION` below.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from itertools import combinations
from pathlib import Path

import yaml

from ..core.logging import get_logger
from ..programs import loader
from ..schemas.council import Deliberation, DeliberationRequest
from ..schemas.divergence import (
    MAX_STANCE_SIMILARITY,
    MIN_ACCEPTED_CRITIQUES,
    MIN_DISSENTS,
    BatteryItem,
    LiveReport,
    ModuleDivergence,
    ModuleStructure,
    StructuralReport,
)

log = get_logger(__name__)

BATTERY_FILE = Path(__file__).resolve().parent / "battery.yaml"
"""Lives beside the harness, not in `programs/`.

`programs/*.yaml` means "this is a module" — the loader validates every file it finds
there against the ten rules and refuses to start if one does not comply. That rule is
worth more than the convenience of co-locating data, and it caught this file the moment
it was put in the wrong place."""

LIMITATION = (
    "Dissent is counted from the synthesiser's own minority_opinions and disagreements. "
    "That avoids a second, competing disagreement detector, but it means a lazy "
    "synthesis under-reports divergence. Stance similarity is the independent check: it "
    "is computed from the text and needs no judgement."
)

STOPWORDS = frozenset(
    """a an and are as at be been but by can do does for from get give had has have how i
    if in into is it its me my no not of on or our out should so than that the their them
    then there they this to until was we were what when which who will with would you
    your now next week weeks month months day days first""".split()
)


# ═══════════════════════════════════════════════════════════════ structural ══


def structural(programs: dict | None = None) -> StructuralReport:
    """Distinctness and topology, straight from the specs. No model involved.

    `programs` is injectable so the harness can be pointed at a deliberately bad module
    set. An instrument that has only ever been tried on a passing case is not known to
    detect anything.
    """
    programs = programs if programs is not None else loader.programs()

    owners: dict[str, list[str]] = {}
    for module, program in programs.items():
        for stage in program.stages:
            if stage.terminal:
                continue  # every module ends in a Conclusion; that is not a difference
            owners.setdefault(stage.produces, []).append(module)

    matrix = _critique_matrix(programs)
    critiqued_by: dict[str, list[str]] = {m: [] for m in programs}
    for critic, targets in matrix.items():
        for target in targets:
            critiqued_by[target].append(critic)

    modules: list[ModuleStructure] = []
    problems: list[str] = []

    for module, program in sorted(programs.items()):
        produced = {s.produces for s in program.stages if not s.terminal}
        unique = sorted(k for k in produced if owners.get(k) == [module])
        shared = sorted(k for k in produced if len(owners.get(k, [])) > 1)

        detected_elsewhere = sum(
            1
            for other, other_program in programs.items()
            if other != module
            for bias in other_program.biases
            if module in bias.detectable_by
        )

        structure = ModuleStructure(
            module=module,
            unique_artifacts=unique,
            shared_artifacts=shared,
            critiques=sorted(matrix.get(module, ())),
            critiqued_by=sorted(critiqued_by[module]),
            biases_detected_elsewhere=detected_elsewhere,
        )
        modules.append(structure)

        if not structure.distinct:
            problems.append(
                f"{module} produces no artifact type that nothing else produces — it "
                "represents the problem the same way as another module, and will "
                "converge with it however differently it is phrased (ADR-002)."
            )
        if not structure.critiqued_by:
            problems.append(
                f"nothing critiques {module}: its declared biases can never be caught, "
                "because a module is never shown its own (ADR-003)."
            )
        if not structure.critiques:
            problems.append(f"{module} critiques nothing, so it only ever defends itself.")

    return StructuralReport(
        modules=modules,
        artifact_owners={k: sorted(v) for k, v in sorted(owners.items())},
        problems=problems,
    )


def _critique_matrix(programs) -> dict[str, tuple[str, ...]]:
    """critic -> targets, derived from each program's own `critics` list.

    Recomputed here rather than calling `loader.critique_matrix()` so an injected module
    set is honoured — the loader's version reads the global registry.
    """
    out: dict[str, list[str]] = {m: [] for m in programs}
    for target, program in programs.items():
        for critic in program.critics:
            if critic in out:
                out[critic].append(target)
    return {critic: tuple(sorted(targets)) for critic, targets in out.items()}


# ═════════════════════════════════════════════════════════════════════ live ══


def battery(limit: int | None = None) -> list[BatteryItem]:
    raw = yaml.safe_load(BATTERY_FILE.read_text(encoding="utf-8")) or []
    items = [BatteryItem.model_validate(entry) for entry in raw]
    return items[:limit] if limit else items


async def measure(
    council,
    *,
    limit: int | None = None,
    depth: str = "standard",
    preset: str = "full",
) -> LiveReport:
    """Run the battery and measure how differently the modules actually behave."""
    items = battery(limit)
    results: list[Deliberation] = []

    for item in items:
        question = item.question.strip()
        log.info("battery: %s", item.id)
        results.append(
            await council.run(
                DeliberationRequest(
                    question=question,
                    context_notes=item.notes.strip(),
                    depth=depth,  # type: ignore[arg-type]
                    preset=preset,
                )
            )
        )

    return report(items, results)


def report(items: Iterable[BatteryItem], results: list[Deliberation]) -> LiveReport:
    """Pure function over finished deliberations, so it is testable without a council."""
    tallies: dict[str, ModuleDivergence] = {}

    def tally(module: str) -> ModuleDivergence:
        if module not in tallies:
            tallies[module] = ModuleDivergence(module=module)
        return tallies[module]

    similarity_samples: dict[str, list[float]] = {}
    all_pairs: list[float] = []
    no_disagreement = 0

    for deliberation in results:
        for run in deliberation.runs:
            entry = tally(run.module)
            entry.decisions += 1
            if run.abstained:
                entry.abstentions += 1

        for critique in deliberation.critiques:
            tally(critique.critic).critiques_raised += 1
        for revision in deliberation.revisions:
            for accepted in revision.accepted:
                tally(accepted.from_module).critiques_accepted += 1

        synthesis = deliberation.synthesis
        if synthesis is None:
            continue
        if not synthesis.disagreements:
            no_disagreement += 1
        for minority in synthesis.minority_opinions:
            tally(minority.module).dissents += 1
        for disagreement in synthesis.disagreements:
            for position in disagreement.positions:
                tally(position.module).disagreements += 1

        # Stance similarity: the independent signal. If six modules return near-identical
        # text, they have collapsed into one voice regardless of what synthesis reported.
        stances = {
            run.module: run.conclusion.stance
            for run in deliberation.runs
            if run.conclusion and run.conclusion.stance.strip()
        }
        for left, right in combinations(sorted(stances), 2):
            score = _similarity(stances[left], stances[right])
            all_pairs.append(score)
            similarity_samples.setdefault(left, []).append(score)
            similarity_samples.setdefault(right, []).append(score)

    for module, samples in similarity_samples.items():
        tally(module).stance_similarity = round(sum(samples) / len(samples), 3)

    for entry in tallies.values():
        _judge(entry, len(results))

    return LiveReport(
        battery=[item.id for item in items],
        modules=[tallies[m] for m in sorted(tallies)],
        mean_stance_similarity=(
            round(sum(all_pairs) / len(all_pairs), 3) if all_pairs else None
        ),
        decisions_with_no_disagreement=no_disagreement,
        notes=[LIMITATION]
        + (
            [
                f"{no_disagreement} of {len(results)} battery decisions produced no named "
                "disagreement at all. The battery is chosen to have tradeoffs, so that "
                "points at the modules or the synthesiser, not the questions."
            ]
            if no_disagreement
            else []
        ),
    )


def _judge(entry: ModuleDivergence, decisions: int) -> None:
    """Apply the SPEC-FORMAT thresholds, and say why rather than just failing."""
    tested = entry.decisions - entry.abstentions

    if tested == 0:
        entry.problems.append(
            f"{entry.module} abstained on every battery decision, so nothing about it was "
            "measured. Check its required inputs against the battery's context."
        )
        return

    if entry.dissents < MIN_DISSENTS and entry.disagreements == 0:
        entry.problems.append(
            f"opposed the recommendation on {entry.dissents} of {tested} decisions and was "
            f"never named in a disagreement (needs {MIN_DISSENTS} dissents or one named "
            "disagreement). A module that always agrees is a voice, not a mind."
        )

    if entry.critiques_raised and entry.critiques_accepted < MIN_ACCEPTED_CRITIQUES:
        entry.problems.append(
            f"raised {entry.critiques_raised} critiques and none were accepted. Attacks "
            "nobody concedes to are noise."
        )

    if entry.stance_similarity is not None and entry.stance_similarity > MAX_STANCE_SIMILARITY:
        entry.problems.append(
            f"its stances average {entry.stance_similarity:.2f} word overlap with the other "
            f"modules (limit {MAX_STANCE_SIMILARITY}). At that similarity it is restating "
            "the others rather than reaching its own conclusion."
        )


def _similarity(left: str, right: str) -> float:
    """Jaccard overlap on content words.

    Crude, and that is the point: it is a floor that catches the degenerate case, not a
    semantic judgement. A cheap check that cannot be gamed by phrasing beats an expensive
    one that needs its own calibration.
    """
    a, b = _words(left), _words(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _words(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9']+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    }
