"""The orchestrator: intake → parallel fan-out → routed critique → revision →
synthesis → Decision Card.

The only module that knows what a deliberation is. It is a plain async state machine
over an explicit state object, shaped like a graph so it can become a LangGraph one
in Phase 4 without rewriting the stages (ADR-007).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import date, datetime, timedelta, timezone

from pydantic import ValidationError

from ..core.config import Depth, Settings, get_settings
from ..core.errors import ArtifactInvalid, CognitiveOSError, ProviderError
from ..core.logging import get_logger
from ..engine.executor import Engine
from ..engine.mockfix import build_fixups
from ..llm.base import LLMRequest
from ..llm.jsonio import extract_json
from ..core.errors import ProgramInvalid
from ..learning.extraction import extract as extract_memories
from ..learning.grader import grade as grade_card
from ..llm.registry import Router
from ..memory.store import MemoryStore, build_store
from ..programs import loader
from ..prompts import renderer
from ..schemas.cards import DecisionCard, ExpectedOutcome, ModuleStance, Resolution
from ..schemas.common import Verdict
from ..schemas.council import (
    Critique,
    CritiqueList,
    DecisionContext,
    Deliberation,
    DeliberationRequest,
    IntakeResult,
    ModuleRun,
    Rerun,
    Revision,
    RevisionDraft,
    Synthesis,
)
from ..schemas.common import ModuleId
from ..schemas.events import Event, ev
from ..schemas.program import AgentProgram
from ..trace import builder as trace_builder

log = get_logger(__name__)

Emit = Callable[[Event], Awaitable[None]]

CRITIQUE_ROUNDS: dict[str, int] = {"quick": 0, "standard": 1, "deep": 2}


class Council:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        store: MemoryStore | None = None,
        force_provider: str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._router = Router(
            self._settings,
            fixups=build_fixups(),
            force_provider=force_provider,
        )
        self._engine = Engine(self._router)
        self._store = store or build_store(self._settings.store, self._settings.store_dir)

    @property
    def store(self) -> MemoryStore:
        return self._store

    async def aclose(self) -> None:
        await self._router.aclose()

    # ------------------------------------------------------------- learning --

    async def resolve(
        self, card_id: str, resolution: Resolution, *, grade: bool = True
    ) -> DecisionCard:
        """Record the outcome, then score every module against it.

        The resolution is saved *before* grading, so a grader failure never costs the
        outcome the user took the trouble to write down. Re-grade with `grade()`.
        """
        card = await self._store.resolve_card(card_id, resolution)
        if not grade:
            return card
        return await self.grade(card_id)

    async def grade(self, card_id: str) -> DecisionCard:
        card = await self._store.get_card(card_id)
        if card is None:
            raise KeyError(card_id)
        if card.resolution is None:
            raise CognitiveOSError(
                f"card {card_id} has no resolution; record what happened before grading"
            )
        scoring = await grade_card(card, card.resolution, self._router)
        graded = await self._store.attach_scoring(card_id, scoring)

        # Extraction runs after grading so it can see which module was right. Its
        # failure must never cost the resolution, which is the expensive artefact.
        try:
            memories = await extract_memories(graded, card.resolution, self._router)
            for module in {m.module for m in memories}:
                await self._store.remember(module, [m for m in memories if m.module == module])
            if memories:
                log.info("extracted %d memories from card %s", len(memories), card_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("memory extraction failed for card %s: %s", card_id, exc)
        return graded

    # -------------------------------------------------------------- re-runs --

    async def rerun_stage(
        self,
        deliberation_id: str,
        *,
        module: ModuleId,
        from_stage: str,
        facts: list[str] | None = None,
        reason: str = "",
    ) -> Deliberation:
        """Re-run one module from one stage, then re-synthesise.

        Produces a **new** deliberation derived from the original; the original is
        never touched. Critiques *of* the re-run module are dropped — they targeted
        artifacts that no longer exist — while critiques *by* it are kept, since its
        reading of the others has not changed.
        """
        original = await self._store.get_deliberation(deliberation_id)
        if original is None:
            raise KeyError(deliberation_id)
        seed = original.run_for(module)
        if seed is None:
            raise KeyError(f"deliberation {deliberation_id} has no run for {module}")

        programs = loader.programs()
        if module not in programs:
            raise ProgramInvalid(f"unknown module '{module}'")

        facts = facts or []
        context = original.context.model_copy(
            update={"constraints": [*original.context.constraints, *facts]}
        )

        fresh = await self._engine.run_program(
            programs[module],
            context=context,
            depth=original.depth,  # type: ignore[arg-type]
            role=seed.role,
            memory=await self._store.agent_memory(module, context.question),
            resume_from=from_stage,
            seed=seed,
        )

        derived = original.model_copy(
            deep=True,
            update={
                "id": uuid.uuid4().hex[:12],
                "created_at": datetime.now(timezone.utc),
                "derived_from": original.id,
                "rerun": Rerun(
                    kind="stage",
                    module=module,
                    from_stage=from_stage,
                    added_facts=facts,
                    reason=reason,
                ),
                "context": context,
                "synthesis": None,
            },
        )
        derived.runs = [fresh if r.module == module else r for r in derived.runs]
        derived.critiques = [c for c in derived.critiques if c.target != module]
        derived.revisions = [r for r in derived.revisions if r.module != module]
        derived.usage.merge(fresh.usage)

        async def noop(_event: Event) -> None:
            return None

        derived.synthesis = await self._synthesise(programs, derived, noop)
        await self._finish(derived, programs)
        return derived

    async def refine(
        self, deliberation_id: str, *, answers: list[str], reason: str = ""
    ) -> Deliberation:
        """Answer the open unknowns and deliberate again, knowing them.

        Deliberately a full re-run rather than a surgical patch: once a load-bearing
        unknown is resolved, every module's reasoning downstream of it is suspect, and
        pretending otherwise would produce a record that is half-informed without
        saying which half.
        """
        original = await self._store.get_deliberation(deliberation_id)
        if original is None:
            raise KeyError(deliberation_id)

        notes = "\n".join(
            [
                "Answers to what the council could not previously determine:",
                *(f"- {answer}" for answer in answers),
            ]
        )
        request = DeliberationRequest(
            question=original.question,
            preset=original.preset,
            depth=original.depth,  # type: ignore[arg-type]
            context_notes=notes,
        )
        refined = await self.run(request)
        refined.derived_from = original.id
        refined.rerun = Rerun(kind="refine", added_facts=answers, reason=reason)
        await self._store.save_deliberation(refined)
        return refined

    async def _finish(self, deliberation: Deliberation, programs) -> None:
        """Persist a derived deliberation and its card."""
        await self._store.save_deliberation(deliberation)
        if deliberation.synthesis is not None:
            card = self._make_card(deliberation, deliberation.synthesis)
            await self._store.save_card(card)

    async def override_verdict(
        self, card_id: str, module: str, verdict: Verdict, justification: str = ""
    ) -> DecisionCard:
        card = await self._store.get_card(card_id)
        if card is None or card.scoring is None:
            raise KeyError(f"card {card_id} is not graded")
        existing = card.scoring.verdict_for(module)
        if existing is None:
            raise KeyError(f"card {card_id} has no verdict for {module}")
        existing.verdict = verdict
        existing.overridden = True
        if justification:
            existing.justification = justification
        return await self._store.attach_scoring(card_id, card.scoring)

    # ------------------------------------------------------------- streaming --

    async def deliberate(self, request: DeliberationRequest) -> AsyncIterator[Event]:
        """Stream typed events. `run()` drains this, so there is one code path."""
        queue: asyncio.Queue[Event | None] = asyncio.Queue()

        async def emit(event: Event) -> None:
            await queue.put(event)

        async def produce() -> None:
            try:
                await self._run(request, emit)
            except CognitiveOSError as exc:
                await queue.put(ev("error", message=str(exc), recoverable=False))
            except Exception as exc:  # noqa: BLE001 - the stream must always close
                log.exception("deliberation failed")
                await queue.put(ev("error", message=f"internal error: {exc}", recoverable=False))
            finally:
                await queue.put(None)

        task = asyncio.create_task(produce())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def run(self, request: DeliberationRequest) -> Deliberation:
        """Non-streaming: drain the generator and return the assembled result."""
        deliberation: Deliberation | None = None
        error: str | None = None
        async for event in self.deliberate(request):
            if event.type == "done":
                deliberation = Deliberation.model_validate(event.payload["deliberation"])
            elif event.type == "error":
                error = event.payload.get("message", "unknown error")
        if deliberation is None:
            raise CognitiveOSError(error or "deliberation produced no result")
        return deliberation

    # ------------------------------------------------------------- pipeline --

    async def _run(self, request: DeliberationRequest, emit: Emit) -> None:
        preset = loader.preset(request.preset or self._settings.default_preset)
        depth: Depth = request.depth or self._settings.default_depth
        programs = loader.programs()

        # ---- stage 0: intake -------------------------------------------------
        await emit(ev("stage_started", phase="intake", label="Reading the question"))
        context = await self._intake(request, emit)
        await emit(ev("intake_complete", context=context.model_dump(mode="json")))

        deliberation = Deliberation(
            id=uuid.uuid4().hex[:12],
            question=request.question,
            preset=preset.id,
            depth=depth,
            context=context,
            program_versions={m: programs[m].version for m in preset.participants},
        )

        # ---- stage 1: independent reasoning ---------------------------------
        running = [m for m in preset.running if m in programs]
        await emit(
            ev(
                "stage_started",
                phase="reason",
                label=f"{len(running)} modules reasoning independently",
                modules=running,
            )
        )

        async def run_module(module: str) -> ModuleRun:
            program = programs[module]
            await emit(ev("module_started", module=module, role=preset.role_of(module)))
            memory = await self._store.agent_memory(module, context.question)
            # Isolation is structural: the only arguments are the program, the
            # context, and this module's own memory. There is no parameter through
            # which a sibling's output could arrive.
            return await self._engine.run_program(
                program,
                context=context,
                depth=depth,
                role=preset.role_of(module),
                memory=memory,
                emit=emit,
            )

        results = await asyncio.gather(
            *(run_module(m) for m in running), return_exceptions=True
        )
        for module, result in zip(running, results):
            if isinstance(result, BaseException):
                log.warning("%s failed outright: %s", module, result)
                deliberation.runs.append(
                    ModuleRun(
                        module=module,
                        program_version=programs[module].version,
                        role=preset.role_of(module),
                        abstained=True,
                        abstain_reason=str(result),
                    )
                )
                await emit(ev("module_abstained", module=module, reason=str(result)))
            else:
                deliberation.runs.append(result)
                deliberation.usage.merge(result.usage)

        # ---- stages 2 & 3: critique and revision ----------------------------
        for round_index in range(CRITIQUE_ROUNDS.get(depth, 1)):
            fresh = [r for r in deliberation.runs if not r.abstained and r.conclusion]
            if len(fresh) < 2:
                break
            await emit(
                ev(
                    "stage_started",
                    phase="critique",
                    label=f"Critique round {round_index + 1}",
                )
            )
            critiques = await self._critique(preset, programs, deliberation, emit)
            deliberation.critiques.extend(critiques)
            if not critiques:
                break

            await emit(ev("stage_started", phase="revise", label="Revising confidence"))
            revisions = await self._revise(programs, deliberation, critiques, emit)
            deliberation.revisions.extend(revisions)

        # ---- stage 4: synthesis ---------------------------------------------
        await emit(ev("stage_started", phase="synthesis", label="Synthesising"))
        synthesis = await self._synthesise(programs, deliberation, emit)
        deliberation.synthesis = synthesis

        # ---- persistence, trace, card ---------------------------------------
        graph = trace_builder.build(deliberation, programs)
        await emit(ev("trace_updated", **graph.model_dump(mode="json")))

        await self._store.save_deliberation(deliberation)

        card: DecisionCard | None = None
        if synthesis is not None:
            card = self._make_card(deliberation, synthesis)
            await self._store.save_card(card)
            await emit(
                ev(
                    "card_created",
                    card_id=card.id,
                    check_on=card.expected_outcome.check_on.isoformat()
                    if card.expected_outcome
                    else None,
                )
            )

        await emit(
            ev(
                "done",
                deliberation=deliberation.model_dump(mode="json"),
                trace=graph.model_dump(mode="json"),
                card_id=card.id if card else None,
                usage=deliberation.usage.model_dump(mode="json"),
            )
        )

    # ---------------------------------------------------------------- stage 0 --

    async def _intake(self, request: DeliberationRequest, emit: Emit) -> DecisionContext:
        prompt = renderer.render(
            "intake.jinja", question=request.question, notes=request.context_notes
        )
        try:
            response = await self._router.complete(
                "intake",
                LLMRequest(
                    system="You are the intake stage of a decision system.",
                    user=prompt,
                    json_model=IntakeResult,
                    temperature=0.2,
                    max_tokens=2048,
                    tag="intake",
                ),
            )
            result = IntakeResult.model_validate(extract_json(response.text))
        except (ProviderError, ValidationError, ValueError) as exc:
            # A failed intake must not kill the deliberation: the modules can work
            # from the raw question, they just get less structure.
            log.warning("intake failed, falling back to the raw question: %s", exc)
            await emit(
                ev(
                    "error",
                    message=f"intake degraded ({exc}); modules will work from the raw question",
                    recoverable=True,
                )
            )
            return DecisionContext(question=request.question, normalised=request.question)

        return DecisionContext(question=request.question, **result.model_dump())

    # ---------------------------------------------------------------- stage 2 --

    async def _critique(
        self,
        preset,
        programs: dict[str, AgentProgram],
        deliberation: Deliberation,
        emit: Emit,
    ) -> list[Critique]:
        matrix = loader.critique_matrix()
        by_module = {r.module: r for r in deliberation.runs if not r.abstained}

        async def critique_one(critic: str) -> list[Critique]:
            targets = [t for t in matrix.get(critic, ()) if t in by_module and t != critic]
            if not targets:
                return []
            payload = [
                {
                    "module": t,
                    "summary": programs[t].summary.strip(),
                    "artifacts": by_module[t].artifacts,
                    "biases": programs[t].biases,
                    "conclusion": by_module[t].conclusion,
                }
                for t in targets
            ]
            prompt = renderer.render(
                "critique.jinja",
                context=deliberation.context,
                lens=programs[critic].critique_lens,
                targets=payload,
            )
            try:
                response = await self._router.complete(
                    "reasoning",
                    LLMRequest(
                        system=renderer.system_prompt(programs[critic]),
                        user=prompt,
                        json_model=CritiqueList,
                        temperature=0.8,
                        tag=f"{critic}:critique",
                    ),
                )
                deliberation.usage.add(
                    model=response.route,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )
                items = CritiqueList.model_validate(extract_json(response.text)).critiques
            except (ProviderError, ValidationError, ValueError) as exc:
                log.warning("%s critique failed: %s", critic, exc)
                return []

            out = [
                Critique(critic=critic, **item.model_dump())
                for item in items
                if item.target in by_module and item.target != critic
            ]
            await emit(
                ev(
                    "critique_complete",
                    module=critic,
                    critiques=[c.model_dump(mode="json") for c in out],
                )
            )
            return out

        critics = [c for c in preset.participants if c in programs]
        gathered = await asyncio.gather(
            *(critique_one(c) for c in critics), return_exceptions=True
        )
        return [c for batch in gathered if isinstance(batch, list) for c in batch]

    # ---------------------------------------------------------------- stage 3 --

    async def _revise(
        self,
        programs: dict[str, AgentProgram],
        deliberation: Deliberation,
        critiques: list[Critique],
        emit: Emit,
    ) -> list[Revision]:
        by_module = {r.module: r for r in deliberation.runs if not r.abstained}

        async def revise_one(module: str, against: list[Critique]) -> Revision | None:
            run = by_module[module]
            if run.conclusion is None:
                return None
            prompt = renderer.render(
                "revise.jinja",
                context=deliberation.context,
                conclusion=run.conclusion,
                critiques=against,
            )
            try:
                response = await self._router.complete(
                    "reasoning",
                    LLMRequest(
                        system=renderer.system_prompt(programs[module]),
                        user=prompt,
                        json_model=RevisionDraft,
                        temperature=0.6,
                        tag=f"{module}:revise",
                    ),
                )
                deliberation.usage.add(
                    model=response.route,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )
                draft = RevisionDraft.model_validate(extract_json(response.text))
            except (ProviderError, ValidationError, ValueError) as exc:
                log.warning("%s revision failed: %s", module, exc)
                return None

            revision = Revision(module=module, **draft.model_dump())
            # The revised confidence is what synthesis weighs, so it replaces the
            # stage-1 number rather than sitting alongside it.
            run.conclusion.confidence = revision.confidence
            run.conclusion.stance = revision.stance
            await emit(ev("revision_complete", revision=revision.model_dump(mode="json")))
            return revision

        grouped: dict[str, list[Critique]] = {}
        for critique in critiques:
            grouped.setdefault(critique.target, []).append(critique)

        gathered = await asyncio.gather(
            *(revise_one(m, cs) for m, cs in grouped.items() if m in by_module),
            return_exceptions=True,
        )
        return [r for r in gathered if isinstance(r, Revision)]

    # ---------------------------------------------------------------- stage 4 --

    async def _synthesise(
        self, programs: dict[str, AgentProgram], deliberation: Deliberation, emit: Emit
    ) -> Synthesis | None:
        runs = [
            {
                "module": run.module,
                "role": run.role,
                "abstained": run.abstained,
                "abstain_reason": run.abstain_reason,
                "conclusion": run.conclusion,
                "artifacts": run.artifacts,
                "biases": programs[run.module].biases if run.module in programs else [],
            }
            for run in deliberation.runs
        ]
        scores = await self._store.scores()
        calibration = [
            f"{s.module}: {s.hit_rate:.0%} over {s.n} resolved decisions "
            f"({s.horizon_days}-day horizon)"
            for s in scores
            if s.displayable and s.hit_rate is not None
        ]

        prompt = renderer.render(
            "synthesis.jinja",
            context=deliberation.context,
            runs=runs,
            critiques=deliberation.critiques,
            revisions=deliberation.revisions,
            calibration=calibration,
        )
        try:
            response = await self._router.complete(
                "synthesis",
                LLMRequest(
                    system=(
                        "You are the synthesiser of a multi-module decision system. "
                        "You commit to one recommendation without deleting the dissent."
                    ),
                    user=prompt,
                    json_model=Synthesis,
                    temperature=0.5,
                    max_tokens=12288,
                    tag="synthesis",
                ),
            )
            deliberation.usage.add(
                model=response.route,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
            )
            synthesis = Synthesis.model_validate(extract_json(response.text))
        except (ProviderError, ValidationError, ValueError) as exc:
            log.error("synthesis failed: %s", exc)
            await emit(ev("error", message=f"synthesis failed: {exc}", recoverable=False))
            return None

        synthesis = self._enforce_synthesis_rules(synthesis, deliberation)
        await emit(ev("synthesis_complete", synthesis=synthesis.model_dump(mode="json")))
        return synthesis

    @staticmethod
    def _enforce_synthesis_rules(
        synthesis: Synthesis, deliberation: Deliberation
    ) -> Synthesis:
        """Rules cheap enough to enforce in code rather than trust to the prompt."""
        dissenting = {m.module for m in synthesis.minority_opinions}
        ceiling = max(
            (
                r.conclusion.confidence.score
                for r in deliberation.runs
                if r.conclusion and r.module not in dissenting
            ),
            default=None,
        )
        if ceiling is not None and synthesis.confidence.score > ceiling:
            synthesis.confidence.score = ceiling
            synthesis.calibration_note = (
                synthesis.calibration_note
                + f" [Capped to {ceiling:.2f}: synthesis cannot exceed the confidence of "
                "the modules it follows.]"
            ).strip()

        veto = next(
            (r for r in deliberation.runs if r.conclusion and r.conclusion.ethical_veto), None
        )
        if veto is not None and not synthesis.ethical_veto_response:
            synthesis.ethical_veto_response = (
                f"UNANSWERED: {veto.module} raised a veto "
                f"({veto.conclusion.veto_grounds if veto.conclusion else 'no grounds given'}) "
                "and the synthesis did not address it. Treat this recommendation as "
                "incomplete."
            )
        return synthesis

    # ------------------------------------------------------------------ card --

    @staticmethod
    def _make_card(deliberation: Deliberation, synthesis: Synthesis) -> DecisionCard:
        drafted = synthesis.expected_outcome
        return DecisionCard(
            id=uuid.uuid4().hex[:12],
            question=deliberation.question,
            deliberation_id=deliberation.id,
            preset=deliberation.preset,
            depth=deliberation.depth,
            domains=list(deliberation.context.domains),
            program_versions=deliberation.program_versions,
            recommendation=synthesis.recommendation,
            per_module=[
                ModuleStance(
                    module=run.module,
                    stance=run.conclusion.stance if run.conclusion else "",
                    confidence=run.conclusion.confidence if run.conclusion else None,
                    abstained=run.abstained,
                    role=run.role,
                )
                for run in deliberation.runs
            ],
            expected_outcome=ExpectedOutcome(
                statement=drafted.statement,
                check_on=date.today() + timedelta(days=drafted.check_in_days),
                measurable_by=drafted.measurable_by,
            ),
            minority_opinions=synthesis.minority_opinions,
        )
