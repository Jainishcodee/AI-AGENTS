"""The interpreter. Executes any AgentProgram; knows no module by name.

This is the piece ADR-011 is about. `engine/` must never import `programs/` — the
moment it does it stops being an interpreter and becomes a hardcoded pipeline.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from ..core.config import Depth
from ..core.errors import ArtifactInvalid, ProviderError
from ..core.logging import get_logger
from ..llm.base import LLMRequest
from ..llm.jsonio import extract_json, format_validation_error
from ..llm.registry import Router
from ..prompts import renderer
from ..schemas.artifacts import TERMINAL_KIND, Artifact, Conclusion, model_for
from ..schemas.cards import AgentMemory
from ..schemas.council import DecisionContext, ModuleRun
from ..schemas.events import Event, ev
from ..schemas.common import StageId
from ..schemas.program import AgentProgram, Role
from .invariants import InvariantContext, check, normalize
from .planner import StageBatch, batch_model, plan

log = get_logger(__name__)

Emit = Callable[[Event], Awaitable[None]]

MAX_ATTEMPTS = 2
"""One generation plus one repair. A second failure is an abstention, because
silently accepting a malformed artifact is worse than a visible gap (ADR-004)."""


class Engine:
    def __init__(self, router: Router) -> None:
        self._router = router

    async def run_program(
        self,
        program: AgentProgram,
        *,
        context: DecisionContext,
        depth: Depth,
        role: Role = "primary",
        memory: AgentMemory | None = None,
        emit: Emit | None = None,
        resume_from: StageId | None = None,
        seed: ModuleRun | None = None,
        live: Any | None = None,
    ) -> ModuleRun:
        """Execute a program, optionally resuming partway through a previous run.

        `resume_from` + `seed` is the capability ADR-011 was for: because every stage
        is a separately validated artifact, re-running the strategist's leverage stage
        against one new fact is a supported operation rather than a rebuild. Stages
        before the resume point are copied from the seed; everything from it onward is
        re-executed against the (possibly updated) context.
        """
        memory = memory or AgentMemory()
        run = ModuleRun(module=program.id, program_version=program.version, role=role)
        system = renderer.system_prompt(program)
        batches = plan(program, depth)

        start = 0
        if resume_from is not None:
            start = _batch_index_of(batches, resume_from)
            carried = {s.id for batch in batches[:start] for s in batch.stages}
            if seed is not None:
                run.artifacts = [a for a in seed.artifacts if a.stage_id in carried]
            missing = carried - {a.stage_id for a in run.artifacts}
            if missing:
                raise ArtifactInvalid(
                    program.id,
                    [
                        "cannot resume from "
                        f"'{resume_from}': no prior artifact for "
                        f"{', '.join(sorted(missing))}"
                    ],
                )
            batches = batches[start:]

        for index, batch in enumerate(batches, start=start + 1):
            # Facts a human supplied since the last batch. Checked here rather than
            # mid-batch so a stage never sees its inputs change underneath it — the
            # artifact it produces must be explicable by the context it was given.
            if live is not None:
                arriving = await live.drain()
                if arriving:
                    context = _with_facts(context, [item.fact for item in arriving])
                    if emit:
                        await emit(
                            ev(
                                "injection_applied",
                                module=program.id,
                                before_stage=batch.stages[0].id,
                                facts=[item.fact for item in arriving],
                            )
                        )

            try:
                artifacts = await self._run_batch(
                    program,
                    batch,
                    index=index,
                    total=start + len(batches),
                    system=system,
                    context=context,
                    memory=memory,
                    run=run,
                    emit=emit,
                )
            except (ArtifactInvalid, ProviderError) as exc:
                run.abstained = True
                run.abstain_reason = str(exc)
                run.abstained_at = batch.stages[0].id
                log.warning("%s abstained at %s: %s", program.id, batch.id, exc)
                if emit:
                    await emit(
                        ev(
                            "module_abstained",
                            module=program.id,
                            stage_id=batch.stages[0].id,
                            reason=str(exc),
                        )
                    )
                return run

            for artifact in artifacts:
                run.artifacts.append(artifact)
                if artifact.kind == TERMINAL_KIND:
                    run.conclusion = Conclusion.model_validate(artifact.data)
                if emit:
                    await emit(
                        ev(
                            "artifact_complete",
                            module=program.id,
                            stage_id=artifact.stage_id,
                            artifact=artifact.model_dump(mode="json"),
                        )
                    )

        if emit:
            await emit(
                ev(
                    "module_complete",
                    module=program.id,
                    conclusion=run.conclusion.model_dump(mode="json") if run.conclusion else None,
                )
            )
        return run

    # ------------------------------------------------------------------------

    async def _run_batch(
        self,
        program: AgentProgram,
        batch: StageBatch,
        *,
        index: int,
        total: int,
        system: str,
        context: DecisionContext,
        memory: AgentMemory,
        run: ModuleRun,
        emit: Emit | None,
    ) -> list[Artifact]:
        priors = {
            ref: artifact
            for ref in batch.reads
            if ref != "context"
            for artifact in [run.artifact_at(ref)]
            if artifact is not None
        }
        citable = citable_refs(run) if batch.terminal else set()
        wrapper = batch_model(batch)

        user = renderer.render(
            "stage.jinja",
            batch=batch,
            index=index,
            total=total,
            context=context,
            memory=memory,
            priors=priors,
            citable=sorted(citable),
        )

        problems: list[str] = []
        previous = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            prompt = user
            if problems:
                prompt = user + "\n\n" + renderer.render(
                    "repair.jinja", problems=problems, previous=previous
                )

            response = await self._router.complete(
                "reasoning",
                LLMRequest(
                    system=system,
                    user=prompt,
                    json_model=wrapper,
                    temperature=0.75,
                    tag=f"{program.id}:{batch.id}",
                ),
                override=program.model_override,
            )
            run.usage.add(
                model=response.route,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                repair=attempt > 1,
            )
            previous = response.text

            try:
                payload = extract_json(response.text)
            except ValueError as exc:
                problems = [f"The response was not parseable JSON: {exc}"]
                continue

            artifacts, problems = self._validate_batch(
                program, batch, payload, context=context, priors=priors, citable=citable
            )
            if not problems:
                return artifacts

            log.info(
                "%s:%s attempt %d rejected: %s",
                program.id,
                batch.id,
                attempt,
                "; ".join(problems)[:300],
            )
            if emit:
                await emit(
                    ev(
                        "artifact_invalid",
                        module=program.id,
                        stage_id=batch.stages[0].id,
                        problems=problems,
                        repairing=attempt < MAX_ATTEMPTS,
                    )
                )

        raise ArtifactInvalid(batch.id, problems, raw=previous)

    def _validate_batch(
        self,
        program: AgentProgram,
        batch: StageBatch,
        payload: Any,
        *,
        context: DecisionContext,
        priors: dict[str, Artifact],
        citable: set[str],
    ) -> tuple[list[Artifact], list[str]]:
        artifacts: list[Artifact] = []
        problems: list[str] = []
        # Later stages in a batch may read earlier ones, so validated artifacts
        # join the prior set as we go.
        available = dict(priors)

        for stage in batch.stages:
            if batch.is_single:
                raw = payload
            elif isinstance(payload, dict) and stage.id in payload:
                raw = payload[stage.id]
            else:
                keys = list(payload) if isinstance(payload, dict) else []
                problems.append(
                    f"missing key '{stage.id}' in the response object (got: "
                    f"{', '.join(keys) or 'nothing'})."
                )
                continue
            if not isinstance(raw, dict):
                problems.append(f"'{stage.id}' must be an object, got {type(raw).__name__}.")
                continue

            model = model_for(stage.produces)
            try:
                data = model.model_validate(normalize(stage.produces, dict(raw)))
            except ValidationError as exc:
                problems += [f"{stage.id}.{p}" for p in format_validation_error(exc)]
                continue

            ctx = InvariantContext(
                context=context,
                stage=stage,
                module=program.id,
                prior=available,
                citable=citable,
            )
            stage_problems = check(stage.produces, data, ctx)
            if stage_problems:
                problems += [f"{stage.id}: {p}" for p in stage_problems]
                continue

            artifact = Artifact.of(
                module=program.id,
                stage_id=stage.id,
                kind=stage.produces,
                data=data,
                title=stage.name,
            )
            artifacts.append(artifact)
            available[stage.id] = artifact

        return (artifacts, problems) if problems else (artifacts, [])


LATE_FACT_PREFIX = "[arrived mid-deliberation] "
"""Marks a fact the user supplied after reasoning began.

Labelled rather than silently merged: a module treating late information as though it
had been there from the start would produce a transcript that cannot be read back
honestly — and the earlier stages genuinely did not have it."""


def _with_facts(context: DecisionContext, facts: list[str]) -> DecisionContext:
    return context.model_copy(
        update={
            "constraints": [
                *context.constraints,
                *(f"{LATE_FACT_PREFIX}{fact}" for fact in facts),
            ]
        }
    )


def _batch_index_of(batches: list[StageBatch], stage_id: StageId) -> int:
    for index, batch in enumerate(batches):
        if stage_id in batch.produced_ids:
            return index
    raise ArtifactInvalid("resume", [f"no stage '{stage_id}' in this program"])


def citable_refs(run: ModuleRun) -> set[str]:
    """`module/stage_id/Kind#row_id` for every addressable row this module produced.

    Handed to the terminal stage so `key_claims` can cite real rows, and used by the
    Conclusion invariant to reject citations that do not resolve.
    """
    refs: set[str] = set()
    for artifact in run.artifacts:
        base = f"{artifact.module}/{artifact.stage_id}/{artifact.kind}"
        refs.add(base)
        for value in artifact.data.values():
            if not isinstance(value, list):
                continue
            for row in value:
                if isinstance(row, dict):
                    key = _row_key(row)
                    if key is not None:
                        refs.add(f"{base}#{key}")
    return refs


ROW_KEYS = ("id", "option_id", "actor_id", "person_id", "order")
"""Not every artifact keys its rows on `id`.

A sequence step is identified by `order`, a harm row by `option_id`, a profile by
`person_id`. Recognising all of them is what stops the terminal stage from being
told a real row is uncitable — which showed up immediately in live runs as a wasted
repair call.
"""


def _row_key(row: dict[str, object]) -> str | None:
    for key in ROW_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
    return None


def as_json_model(model: type[BaseModel]) -> type[BaseModel]:
    return model
