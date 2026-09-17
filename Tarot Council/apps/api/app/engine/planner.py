"""Program → execution plan (ADR-013).

The program never changes; only the plan does. `quick` collapses a whole program
into a couple of calls, `standard` runs one call per declared group, `deep` runs one
call per stage. Artifacts are validated individually at every depth, so nothing is
*skipped* when depth drops — the probability tree still gets built, it just gets
built in the same breath as the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import create_model

from ..core.config import Depth
from ..schemas.artifacts import ARTIFACT_MODELS, ArtifactData
from ..schemas.program import CONTEXT_REF, AgentProgram, Stage


@dataclass(slots=True, frozen=True)
class StageBatch:
    """One LLM call. Usually one stage; several when the plan batches a group."""

    stages: tuple[Stage, ...]

    @property
    def id(self) -> str:
        return "+".join(s.id for s in self.stages)

    @property
    def label(self) -> str:
        return " → ".join(s.name for s in self.stages)

    @property
    def is_single(self) -> bool:
        return len(self.stages) == 1

    @property
    def terminal(self) -> bool:
        return any(s.terminal for s in self.stages)

    @property
    def produced_ids(self) -> frozenset[str]:
        return frozenset(s.id for s in self.stages)

    @property
    def reads(self) -> tuple[str, ...]:
        """External dependencies: what this batch needs that it does not produce."""
        internal = self.produced_ids
        seen: list[str] = []
        for stage in self.stages:
            for ref in stage.reads:
                if ref not in internal and ref not in seen:
                    seen.append(ref)
        return tuple(seen)

    @property
    def reads_context(self) -> bool:
        return CONTEXT_REF in self.reads


def plan(program: AgentProgram, depth: Depth) -> list[StageBatch]:
    keys = [_batch_key(stage, depth, index) for index, stage in enumerate(program.stages)]

    batches: list[StageBatch] = []
    current: list[Stage] = []
    current_key: str | None = None
    for stage, key in zip(program.stages, keys):
        if current and key == current_key:
            current.append(stage)
        else:
            if current:
                batches.append(StageBatch(tuple(current)))
            current = [stage]
            current_key = key
    if current:
        batches.append(StageBatch(tuple(current)))
    return batches


def _batch_key(stage: Stage, depth: Depth, index: int) -> str:
    # A stage that must not share context with its neighbour, and the terminal
    # stage (which needs every prior artifact in view), always stand alone.
    if stage.isolate or stage.terminal:
        return f"__solo_{index}"
    if depth == "deep":
        return f"__stage_{index}"
    if depth == "standard":
        return f"group:{stage.group}"
    return "all"


def batch_model(batch: StageBatch) -> type:
    """The Pydantic model one call must return.

    Single-stage batches ask for the artifact model directly — a flatter shape
    produces better output. Multi-stage batches ask for an object keyed by stage id,
    which is then split back into individual artifacts and validated separately.
    """
    if batch.is_single:
        return ARTIFACT_MODELS[batch.stages[0].produces]

    fields: dict[str, tuple[type[ArtifactData], object]] = {
        stage.id: (ARTIFACT_MODELS[stage.produces], ...) for stage in batch.stages
    }
    return create_model(
        "Batch_" + "_".join(s.id for s in batch.stages),
        **fields,  # type: ignore[arg-type]
    )


def call_estimate(program: AgentProgram, depth: Depth) -> int:
    return len(plan(program, depth))


@dataclass(slots=True)
class CostEstimate:
    """What a deliberation will cost before you spend it.

    Exists because the number that actually decides whether you press go is invisible
    until after it has been spent: `call_estimate` has always been per-program, and a
    free tier meters *requests per minute* (ADR-020), so the wall-clock wait matters as
    much as the count. A `standard` full-council run is ~26 calls, which at 5 RPM is five
    minutes of staring at a terminal.
    """

    intake: int
    reasoning: int
    critique: int
    revise: int
    synthesis: int
    rounds: int
    rpm: int

    @property
    def total(self) -> int:
        return self.intake + self.reasoning + self.critique + self.revise + self.synthesis

    @property
    def seconds(self) -> float:
        """Wall clock at the configured pace. `rpm = 0` means unpaced (mock, or a paid key)."""
        return 0.0 if self.rpm <= 0 else self.total / self.rpm * 60.0

    def describe(self) -> str:
        parts = [
            f"intake {self.intake}",
            f"reasoning {self.reasoning}",
        ]
        if self.rounds:
            parts.append(f"critique {self.critique}")
            parts.append(f"revise {self.revise}")
        parts.append(f"synthesis {self.synthesis}")
        line = f"~{self.total} calls ({', '.join(parts)})"
        if self.seconds >= 1:
            minutes, seconds = divmod(int(self.seconds), 60)
            clock = f"{minutes}m {seconds:02d}s" if minutes else f"{seconds}s"
            line += f", about {clock} at {self.rpm} req/min"
        return line


def deliberation_estimate(
    programs: dict[str, AgentProgram],
    preset,
    depth: Depth,
    *,
    rounds: int,
    rpm: int = 0,
) -> CostEstimate:
    """Estimate the whole pipeline, not one program.

    Counted against how the orchestrator actually issues calls, which is not obvious from
    the outside and is the reason this lives next to `plan` rather than being guessed in
    the CLI:

    - **critique is one call per *critic***, not per critic-target pair — each critic
      reviews all of its targets in a single request.
    - **revise is one call per critiqued *module***, for the same reason.

    Assumes nobody abstains, so it is an upper bound on the reasoning phase and an
    accurate figure for the common case. An abstention makes the real run cheaper, and a
    quote that came in *under* is the harmless direction to be wrong in.
    """
    running = [m for m in preset.running if m in programs]
    participants = [m for m in preset.participants if m in programs]

    reasoning = sum(call_estimate(programs[m], depth) for m in running)

    # Routing is derived from each program's own `critics` list: M critiques T exactly
    # when M appears in T.critics. Rebuilt here over the *given* programs so an authored
    # module is costed like any other.
    live = set(running)
    targets_of: dict[str, set[str]] = {m: set() for m in participants}
    for target in running:
        for critic in programs[target].critics:
            if critic in targets_of and critic != target:
                targets_of[critic].add(target)

    critics = [c for c, targets in targets_of.items() if targets & live]
    critiqued = {t for targets in targets_of.values() for t in targets}

    return CostEstimate(
        intake=1,
        reasoning=reasoning,
        critique=len(critics) * rounds,
        revise=len(critiqued) * rounds,
        synthesis=1,
        rounds=rounds,
        rpm=rpm,
    )
