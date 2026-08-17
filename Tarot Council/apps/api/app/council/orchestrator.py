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
from ..core.errors import (
    CognitiveOSError,
    ProviderError,
    ProviderUnavailable,
)
from ..core.logging import get_logger
from ..engine.executor import Engine, with_late_facts
from ..engine.mockfix import build_fixups
from ..llm.base import LLMRequest
from ..llm.jsonio import extract_json
from ..core.errors import ProgramInvalid
from ..learning.extraction import extract as extract_memories
from ..learning.grader import grade as grade_card
from ..llm.registry import Router
from ..memory.store import MemoryStore, build_store
from ..programs import catalog, loader
from ..prompts import renderer
from ..schemas.cards import (
    DecisionCard,
    ExpectedOutcome,
    ModuleReplay,
    ModuleStance,
    Project,
    ReplayResult,
    Resolution,
)
from ..schemas.checkpoint import Checkpoint
from ..schemas.module import (
    MODULE_STATUSES,
    ModuleCatalogEntry,
    ModuleStatus,
    UserModule,
)
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
from .live import LiveRegistry, LiveRun
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
        self._live = LiveRegistry()

    @property
    def store(self) -> MemoryStore:
        return self._store

    @property
    def live(self) -> LiveRegistry:
        return self._live

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
            for memory in memories:
                # Inherited, not asked for: a memory belongs to the situation its
                # decision belonged to, and that is a fact about the card.
                memory.project_id = graded.project_id
            for module in {m.module for m in memories}:
                await self._store.remember(module, [m for m in memories if m.module == module])
            if memories:
                log.info("extracted %d memories from card %s", len(memories), card_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("memory extraction failed for card %s: %s", card_id, exc)
        return graded

    # ------------------------------------------------------------- projects --

    async def create_project(self, name: str, brief: str = "") -> Project:
        project = Project(id=uuid.uuid4().hex[:12], name=name, brief=brief)
        await self._store.save_project(project)
        return project

    async def close_project(self, project_id: str) -> Project:
        project = await self._store.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        project.closed_at = datetime.now(timezone.utc)
        await self._store.save_project(project)
        return project

    # -------------------------------------------------------- module authoring --

    async def modules(self) -> list[ModuleCatalogEntry]:
        """Everything runnable or authored, built-in and user, including what is broken."""
        return catalog.entries(await self._store.list_modules())

    async def save_module(self, module: UserModule) -> UserModule:
        """Validate, then store whatever comes back — valid or quarantined.

        Storing an invalid module is the point rather than an oversight (ADR-030): a draft
        that will not save is a draft that cannot be worked on, and the author is the only
        person who can fix it. The verdict travels with the module so nothing downstream has
        to re-derive it.
        """
        peers = [m for m in await self._store.list_modules() if m.id != module.id]
        checked = catalog.validate(module, peers=peers).model_copy(
            update={"updated_at": datetime.now(timezone.utc)}
        )
        await self._store.save_module(checked)
        if checked.errors:
            log.info("module '%s' quarantined: %d violation(s)", checked.id, len(checked.errors))
        return checked

    async def set_module_status(self, module_id: ModuleId, status: ModuleStatus) -> UserModule:
        """Put a module into play, or take it out.

        Activation is re-validated rather than trusted: the rules can change under a stored
        module when the built-ins do — a module whose only critic was retired is no longer
        valid, and it must not slip into a council on a stale verdict.
        """
        # `model_copy(update=...)` below does *not* re-validate, so an unknown status would be
        # written to the store verbatim and every `status == "active"` check would quietly
        # disagree with it. The HTTP layer constrains this via its request model; this method
        # is also called directly, so it checks for itself.
        if status not in MODULE_STATUSES:
            raise CognitiveOSError(
                f"unknown module status '{status}'. Known: {', '.join(MODULE_STATUSES)}"
            )

        stored = await self._store.get_module(module_id)
        if stored is None:
            raise KeyError(module_id)

        peers = [m for m in await self._store.list_modules() if m.id != module_id]
        checked = catalog.validate(stored, peers=peers)
        if status == "active" and checked.errors:
            raise CognitiveOSError(
                f"module '{module_id}' cannot be activated; it breaks "
                f"{len(checked.errors)} rule(s): {checked.errors[0]}"
            )
        updated = checked.model_copy(
            update={"status": status, "updated_at": datetime.now(timezone.utc)}
        )
        await self._store.save_module(updated)
        return updated

    async def delete_module(self, module_id: ModuleId) -> None:
        await self._store.delete_module(module_id)

    # --------------------------------------------------------------- replay --

    async def replay(self, card_id: str) -> ReplayResult:
        """Re-decide a resolved card against the current programs, then grade it.

        This is what turns the resolved corpus into a test set for the council itself:
        with the outcome already known, re-running an old decision measures whether a
        changed program would have done better. It is the only way to improve the six
        on evidence rather than on taste — and the counterpart to ADR-018's rule that
        the system never tunes itself.

        The correctness problem is leakage, and it is severe. Memories extracted from
        this very card describe what happened, and priors computed from it encode the
        verdict. Handed those, a module would score well by reading the answer. So both
        are withheld for the duration (ADR-025), and the count of what was withheld is
        reported so the result cannot be quietly trusted more than it deserves.
        """
        card = await self._store.get_card(card_id)
        if card is None:
            raise KeyError(card_id)
        if card.resolution is None or card.scoring is None:
            raise CognitiveOSError(
                f"card {card_id} is not resolved and graded; there is nothing to "
                "measure a replay against"
            )

        original = await self._store.get_deliberation(card.deliberation_id)
        if original is None:
            raise CognitiveOSError(f"card {card_id} has no stored deliberation to replay")

        # Through the catalog: a card written with an authored module in the council must
        # stay replayable, and if that module has since been deleted the failure should say
        # so rather than silently replaying a different council than the one being scored.
        user_modules = await self._store.list_modules()
        programs = catalog.programs(user_modules, include_retired=True)
        preset = catalog.preset(card.preset, user_modules, include_retired=True)
        blocked = frozenset({card.id})

        withheld_memories = 0
        withheld_priors = 0
        runs: list[ModuleRun] = []

        async def run_module(module: ModuleId) -> ModuleRun:
            nonlocal withheld_memories, withheld_priors
            everything = await self._store.agent_memory(
                module, original.context.question, project_id=original.project_id
            )
            clean = await self._store.agent_memory(
                module,
                original.context.question,
                project_id=original.project_id,
                exclude_cards=blocked,
            )
            withheld_memories += len(everything.recalled) - len(clean.recalled)
            withheld_priors += len(everything.priors) - len(clean.priors)
            return await self._engine.run_program(
                programs[module],
                context=original.context,
                depth=original.depth,  # type: ignore[arg-type]
                role=preset.role_of(module),
                memory=clean,
            )

        running = [m for m in preset.running if m in programs]
        results = await asyncio.gather(
            *(run_module(m) for m in running), return_exceptions=True
        )
        for module, result in zip(running, results):
            if isinstance(result, BaseException):
                log.warning("replay of %s failed: %s", module, result)
                runs.append(
                    ModuleRun(
                        module=module,
                        program_version=programs[module].version,
                        role=preset.role_of(module),
                        abstained=True,
                        abstain_reason=str(result),
                    )
                )
            else:
                runs.append(result)

        replayed = Deliberation(
            id=uuid.uuid4().hex[:12],
            question=original.question,
            preset=original.preset,
            depth=original.depth,
            project_id=original.project_id,
            context=original.context,
            derived_from=original.id,
            rerun=Rerun(kind="refine", reason=f"replay of card {card.id}"),
            runs=runs,
            program_versions={m: programs[m].version for m in running},
        )

        async def noop(_event: Event) -> None:
            return None

        replayed.synthesis = await self._synthesise(programs, replayed, noop)
        await self._store.save_deliberation(replayed)

        # Grade the replay against the outcome that actually happened. A throwaway
        # card is used so the original's scoring history is never overwritten.
        shadow = self._make_card(replayed, replayed.synthesis) if replayed.synthesis else None
        now_verdicts: dict[ModuleId, str] = {}
        if shadow is not None:
            shadow.resolution = card.resolution
            try:
                scoring = await grade_card(shadow, card.resolution, self._router)
                now_verdicts = {v.module: v.verdict for v in scoring.module_verdicts}
            except CognitiveOSError as exc:
                log.warning("grading the replay failed: %s", exc)

        then_stance = {m.module: m for m in card.per_module}
        then_verdict = {v.module: v.verdict for v in card.scoring.module_verdicts}

        return ReplayResult(
            card_id=card.id,
            original_deliberation_id=original.id,
            replay_deliberation_id=replayed.id,
            program_versions_then=dict(card.program_versions),
            program_versions_now={m: programs[m].version for m in running},
            excluded_memories=withheld_memories,
            excluded_priors=withheld_priors,
            modules=[
                ModuleReplay(
                    module=run.module,
                    then_stance=then_stance.get(run.module).stance
                    if then_stance.get(run.module)
                    else "",
                    now_stance=run.conclusion.stance if run.conclusion else "",
                    then_verdict=then_verdict.get(run.module),
                    now_verdict=now_verdicts.get(run.module),
                    then_confidence=(
                        then_stance[run.module].confidence.score
                        if then_stance.get(run.module) and then_stance[run.module].confidence
                        else None
                    ),
                    now_confidence=run.conclusion.confidence.score if run.conclusion else None,
                )
                for run in runs
            ],
        )

    # ----------------------------------------------------------- resumption --

    async def _checkpoint(self, checkpoint: Checkpoint, live: LiveRun | None = None) -> bool:
        """Persist progress. Returns whether it actually landed.

        Never let bookkeeping kill a live deliberation: a lost checkpoint costs a replay,
        a crashed deliberation costs the whole run. The boolean matters because callers
        announce the checkpoint to the user — claiming "saved, resume later" when the write
        failed is worse than saying nothing.

        Injected facts are swept off `live` here rather than at the point they are consumed:
        they are drained deep inside the executor, and one sweep on the way to storage
        cannot be bypassed by a later edit adding another checkpoint call.
        """
        if live is not None and live.facts:
            checkpoint.injected = list(dict.fromkeys([*checkpoint.injected, *live.facts]))
        checkpoint.updated_at = datetime.now(timezone.utc)
        try:
            await self._store.save_checkpoint(checkpoint)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("could not write checkpoint %s: %s", checkpoint.deliberation_id, exc)
            return False

    async def resumable(self, limit: int = 20) -> list[Checkpoint]:
        return [c for c in await self._store.list_checkpoints(limit) if c.resumable]

    async def resume(self, deliberation_id: str) -> AsyncIterator[Event]:
        """Continue a deliberation that stopped part-way, reusing what it already paid for.

        The motivating case is mundane and constant: on a free tier a `standard` run is
        ~26 calls at 5 requests a minute, so a quota window or a closed laptop ends it
        mid-flight. Before this, all of that work was lost.

        Everything already produced is kept — finished modules, and finished *stages* of
        unfinished modules. Intake is not re-run, because a fresh intake could yield a
        different context and the existing artifacts were built against the old one.
        """
        checkpoint = await self._store.get_checkpoint(deliberation_id)
        if checkpoint is None:
            raise KeyError(deliberation_id)
        if not checkpoint.resumable:
            raise CognitiveOSError(
                f"deliberation {deliberation_id} stopped in '{checkpoint.phase}', which is "
                "not resumable"
            )
        log.info("resuming %s: %s", deliberation_id, checkpoint.describe())
        async for event in self._stream(checkpoint.request, resume=checkpoint):
            yield event

    async def discard(self, deliberation_id: str) -> None:
        await self._store.delete_checkpoint(deliberation_id)

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

        programs = catalog.programs(await self._store.list_modules(), include_retired=True)
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
        async for event in self._stream(request):
            yield event

    async def _stream(
        self, request: DeliberationRequest, *, resume: Checkpoint | None = None
    ) -> AsyncIterator[Event]:
        """The one streaming path. A fresh run and a resumed one differ only in whether
        a checkpoint is handed in, so they cannot drift apart."""
        queue: asyncio.Queue[Event | None] = asyncio.Queue()

        async def emit(event: Event) -> None:
            await queue.put(event)

        async def produce() -> None:
            try:
                await self._run(request, emit, resume=resume)
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

    async def _run(
        self,
        request: DeliberationRequest,
        emit: Emit,
        resume: Checkpoint | None = None,
    ) -> None:
        # On resume, the preset and depth come from the checkpoint, never from the request
        # or the current settings. A request that named no preset falls back to the default,
        # so changing `COUNCIL_DEFAULT_PRESET` between the crash and the resume would
        # continue the deliberation with a different set of modules than the banked
        # artifacts were built by — the same reason intake is not re-run.
        # Resolved through the catalog so an authored module can take part (ADR-030). The
        # engine below is handed a plain `AgentProgram` either way and never learns where it
        # came from — that indifference is the whole reason the marketplace is a storage
        # problem rather than an engine one.
        user_modules = await self._store.list_modules()
        if resume is not None:
            preset = catalog.preset(resume.preset, user_modules)
            depth: Depth = resume.depth  # type: ignore[assignment]
        else:
            preset = catalog.preset(
                request.preset or self._settings.default_preset, user_modules
            )
            depth = request.depth or self._settings.default_depth
        programs = catalog.programs(user_modules)

        # A live run is addressable for interjection from the first event, so a client
        # can answer an unknown the moment it sees one raised.
        run_id = uuid.uuid4().hex[:12]
        live = self._live.open(run_id, request.question)
        await emit(ev("run_started", run_id=run_id, preset=preset.id, depth=depth))

        # The deliberation id is minted here so the checkpoint and the finished
        # transcript share it: resuming continues the same run rather than starting a
        # lookalike.
        checkpoint = resume or Checkpoint(
            deliberation_id=uuid.uuid4().hex[:12],
            request=request,
            preset=preset.id,
            depth=depth,
            project_id=request.project_id,
        )

        try:
            await self._pipeline(request, preset, depth, programs, live, emit, checkpoint)
        except Exception as exc:  # noqa: BLE001 - record where it stopped, then re-raise
            checkpoint.failure = str(exc)
            # Via `_checkpoint`, so a failing store cannot replace the real error with its
            # own and swallow the `raise` below: the caller must hear about the quota, not
            # about the disk. Only announce the checkpoint if it was genuinely written.
            if checkpoint.resumable and await self._checkpoint(checkpoint, live):
                await emit(
                    ev(
                        "checkpointed",
                        deliberation_id=checkpoint.deliberation_id,
                        phase=checkpoint.phase,
                        artifacts=checkpoint.artifacts_done,
                        calls=checkpoint.usage.calls,
                        detail=checkpoint.describe(),
                    )
                )
            raise
        finally:
            self._live.close(run_id)

    async def _pipeline(
        self,
        request: DeliberationRequest,
        preset,
        depth: Depth,
        programs,
        live: LiveRun,
        emit: Emit,
        checkpoint: Checkpoint,
    ) -> None:
        # ---- stage 0: intake -------------------------------------------------
        # Skipped on resume: it is one cheap call, but re-running it could produce a
        # different context, and then the artifacts already paid for would have been
        # built against a context that no longer exists.
        if checkpoint.context is None:
            await emit(ev("stage_started", phase="intake", label="Reading the question"))
            checkpoint.context = await self._intake(request, emit)
            checkpoint.phase = "reason"
            await self._checkpoint(checkpoint, live)
        context = checkpoint.context

        # Facts a person injected during an earlier attempt. They were folded into the
        # executor's *local* context, so without this they reached only the modules running
        # at the time and the resumed ones would be handed a context that never mentions
        # them — the person answered the council's unknown and the resume behaves as though
        # they had not. Applied once, here, still labelled as late (earlier stages genuinely
        # did not have them).
        if checkpoint.injected:
            context = with_late_facts(context, checkpoint.injected)
            log.info(
                "resuming with %d fact(s) injected before the interruption",
                len(checkpoint.injected),
            )

        await emit(ev("intake_complete", context=context.model_dump(mode="json")))

        deliberation = Deliberation(
            id=checkpoint.deliberation_id,
            question=request.question,
            preset=preset.id,
            depth=depth,
            project_id=request.project_id,
            context=context,
            program_versions={m: programs[m].version for m in preset.participants},
        )

        # ---- stage 1: independent reasoning ---------------------------------
        running = [m for m in preset.running if m in programs]
        already = {r.module for r in checkpoint.completed}
        todo = [m for m in running if m not in already]
        if already:
            log.info("resuming: %s already finished", ", ".join(sorted(already)))
        await emit(
            ev(
                "stage_started",
                phase="reason",
                label=(
                    f"{len(todo)} modules reasoning independently"
                    if not already
                    else f"resuming {len(todo)} of {len(running)} modules"
                ),
                modules=todo,
                resumed=sorted(already),
            )
        )

        async def run_module(module: str) -> ModuleRun:
            program = programs[module]
            await emit(ev("module_started", module=module, role=preset.role_of(module)))
            memory = await self._store.agent_memory(
                module, context.question, project_id=request.project_id
            )
            # Pick up mid-program where a previous attempt stopped. Only possible because
            # every stage is a separately validated artifact (ADR-011) — otherwise a
            # resume would have to redo the whole module.
            partial = checkpoint.partial.get(module)
            stage_ids = [stage.id for stage in program.stages]
            resume_from = checkpoint.next_stage_for(module, stage_ids) if partial else None
            if resume_from and resume_from != stage_ids[0]:
                log.info("%s resuming from stage %s", module, resume_from)
            else:
                resume_from, partial = None, None

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
                live=live,
                resume_from=resume_from,
                seed=partial,
            )

        # Modules finished by an earlier attempt come back verbatim — that is the point
        # of the checkpoint, and their usage is carried so the reported call count is the
        # true cost of the decision rather than of this attempt.
        deliberation.runs.extend(checkpoint.completed)
        for finished in checkpoint.completed:
            deliberation.usage.merge(finished.usage)

        results = await asyncio.gather(*(run_module(m) for m in todo), return_exceptions=True)

        # Bank *everything* the provider let us finish before deciding whether to stop —
        # modules that completed as well as the partial stages of ones that did not.
        # Order matters: raising before banking the successes would throw away exactly
        # the work resumption exists to preserve.
        #
        # This loop is the *only* place a success is banked into the checkpoint. It used to
        # be banked here and again in the loop below, which double-counted usage and put
        # every module into `checkpoint.completed` twice — invisible on a fresh run, because
        # `deliberation.runs` is built below, and then duplicated across the transcript the
        # moment anyone resumed.
        outage: ProviderUnavailable | None = None
        for module, result in zip(todo, results):
            if isinstance(result, ProviderUnavailable):
                partial = result.run
                if getattr(partial, "artifacts", None):
                    checkpoint.partial[module] = partial  # type: ignore[assignment]
                    checkpoint.usage.merge(partial.usage)  # type: ignore[union-attr]
                outage = outage or result
            elif isinstance(result, ModuleRun):
                checkpoint.completed.append(result)
                checkpoint.partial.pop(module, None)
                checkpoint.usage.merge(result.usage)

        if outage is not None:
            await self._checkpoint(checkpoint, live)
            raise outage

        for module, result in zip(todo, results):
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
                # An abstention is a result, and the loop above skipped it (it banks only
                # ProviderUnavailable and ModuleRun). Recording it stops a resume from
                # retrying a module that has already failed twice at the same stage.
                checkpoint.completed.append(deliberation.runs[-1])
                checkpoint.partial.pop(module, None)
            else:
                deliberation.runs.append(result)
                deliberation.usage.merge(result.usage)
        await self._checkpoint(checkpoint, live)

        # ---- stages 2 & 3: critique and revision ----------------------------
        checkpoint.phase = "critique"
        await self._checkpoint(checkpoint, live)

        # Critique history banked by an earlier attempt is copied in exactly once, here,
        # *before* the loop. Inside the loop it was replayed every round — so a `deep` run
        # duplicated round one across round two — and it was skipped entirely whenever the
        # loop body did not execute, which is precisely the resume-into-synthesis case:
        # every round already done, `range` empty, and the banked critiques silently
        # dropped from the transcript so the run looked uncritiqued.
        deliberation.critiques.extend(checkpoint.critiques)
        deliberation.revisions.extend(checkpoint.revisions)

        for round_index in range(checkpoint.rounds_done, CRITIQUE_ROUNDS.get(depth, 1)):
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
            checkpoint.critiques.extend(critiques)
            await self._checkpoint(checkpoint, live)
            if not critiques:
                break

            await emit(ev("stage_started", phase="revise", label="Revising confidence"))
            checkpoint.phase = "revise"
            revisions = await self._revise(programs, deliberation, critiques, emit)
            deliberation.revisions.extend(revisions)
            checkpoint.revisions.extend(revisions)
            checkpoint.rounds_done = round_index + 1
            await self._checkpoint(checkpoint, live)

        # ---- stage 4: synthesis ---------------------------------------------
        checkpoint.phase = "synthesis"
        await self._checkpoint(checkpoint, live)
        await emit(ev("stage_started", phase="synthesis", label="Synthesising"))
        synthesis = await self._synthesise(programs, deliberation, emit)
        deliberation.synthesis = synthesis

        # ---- persistence, trace, card ---------------------------------------
        graph = trace_builder.build(deliberation, programs)
        await emit(ev("trace_updated", **graph.model_dump(mode="json")))

        await self._store.save_deliberation(deliberation)

        # Finished, so there is nothing to resume. Deleting rather than marking done
        # keeps `list_checkpoints` honest about what is genuinely unfinished. Guarded for
        # the same reason as the write: a store hiccup here would abort a deliberation that
        # has already been paid for and saved, and lose the Decision Card below with it.
        checkpoint.phase = "done"
        try:
            await self._store.delete_checkpoint(checkpoint.deliberation_id)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "could not clear checkpoint %s: %s", checkpoint.deliberation_id, exc
            )

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

        if live.consumed:
            deliberation.rerun = Rerun(
                kind="refine",
                added_facts=live.facts,
                reason="supplied mid-deliberation",
            )
            await self._store.save_deliberation(deliberation)

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
        except ProviderError as exc:
            # The same distinction ADR-027 drew for the reasoning phase, which was still
            # missing here — and this is the most expensive place to get it wrong. By now
            # every module has run (~26 calls at `standard`), so swallowing the outage and
            # returning `None` completes the deliberation with no synthesis, writes no
            # Decision Card, and *deletes the checkpoint* — discarding the entire run at
            # the last step with no resume offered. Raising lets `_run` checkpoint it.
            log.warning("synthesis stopped by the provider: %s", exc)
            raise ProviderUnavailable("synthesis", None, exc) from exc
        except (ValidationError, ValueError) as exc:
            # A malformed or unparseable synthesis genuinely is a synthesis failure: the
            # provider answered, the answer was unusable. Degrading is right, because the
            # six analyses still stand on their own.
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
            project_id=deliberation.project_id,
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
