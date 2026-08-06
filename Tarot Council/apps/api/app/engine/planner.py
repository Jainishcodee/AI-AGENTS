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
