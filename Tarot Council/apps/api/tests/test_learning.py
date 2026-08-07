"""The learning loop: grading, calibration maths, and prior generation."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.learning import priors, scoring
from app.learning.grader import GradingFailed, grade
from app.prompts import renderer
from app.schemas.cards import (
    MIN_N_FOR_PRIOR,
    CardScoring,
    DecisionCard,
    ExpectedOutcome,
    ModuleStance,
    ModuleVerdict,
    Resolution,
)
from app.schemas.common import Confidence
from app.schemas.council import DeliberationRequest, Recommendation

from .conftest import QUESTION, RecordingRouter

TODAY = date(2026, 6, 1)


def card(
    card_id: str,
    *,
    stances: dict[str, float],
    verdicts: dict[str, str],
    domains: list[str] | None = None,
    followed: set[str] | None = None,
    resolved: bool = True,
    chose_was_proposed: bool = True,
    unpredicted: list[str] | None = None,
    check_in: int = 90,
) -> DecisionCard:
    followed = followed if followed is not None else set(stances)
    built = DecisionCard(
        id=card_id,
        question=f"question {card_id}",
        deliberation_id=f"d-{card_id}",
        preset="full",
        depth="standard",
        domains=domains or ["career"],
        recommendation=Recommendation(action="do the thing", first_action="today"),
        per_module=[
            ModuleStance(
                module=module,
                stance=f"{module} says do it",
                confidence=Confidence(score=score, basis="b", falsifier="f"),
            )
            for module, score in stances.items()
        ],
        expected_outcome=ExpectedOutcome(
            statement="it works out", check_on=TODAY + timedelta(days=check_in)
        ),
    )
    if not resolved:
        return built
    built.resolution = Resolution(
        chose="did it", actual_outcome="it went like this", happened_at=TODAY
    )
    built.scoring = CardScoring(
        expected_outcome_met="yes",
        chose_was_proposed=chose_was_proposed,
        unpredicted=unpredicted or [],
        module_verdicts=[
            ModuleVerdict(
                module=module,
                verdict=verdict,  # type: ignore[arg-type]
                followed=module in followed,
            )
            for module, verdict in verdicts.items()
        ],
    )
    return built


# ───────────────────────────────────────────────────────── scoring maths ────


def test_brier_and_hit_rate():
    cards = [
        card("c1", stances={"analyst": 0.9}, verdicts={"analyst": "right"}),
        card("c2", stances={"analyst": 0.9}, verdicts={"analyst": "wrong"}),
    ]
    stats = scoring.score(scoring.observations(cards), module="analyst")
    assert stats.n == 2
    assert stats.hit_rate == 0.5
    assert stats.mean_confidence == 0.9
    # ((0.9-1)^2 + (0.9-0)^2) / 2
    assert stats.brier == pytest.approx(0.41, abs=1e-6)
    assert stats.overconfidence == pytest.approx(0.4, abs=1e-6)


def test_partial_counts_as_half():
    cards = [card("c1", stances={"analyst": 0.5}, verdicts={"analyst": "partial"})]
    stats = scoring.score(scoring.observations(cards), module="analyst")
    assert stats.hit_rate == 0.5
    assert stats.brier == pytest.approx(0.0, abs=1e-6)


def test_untested_is_excluded_from_accuracy_but_not_from_execution():
    """A module whose advice was never taken has not been tested.

    Scoring it either way would be fiction — but "you never took this" is itself a
    measurement, so it must still count against the execution rate.
    """
    cards = [
        card("c1", stances={"analyst": 0.8}, verdicts={"analyst": "right"}, followed={"analyst"}),
        card("c2", stances={"analyst": 0.8}, verdicts={"analyst": "untested"}, followed=set()),
    ]
    stats = scoring.score(scoring.observations(cards), module="analyst")
    assert stats.n == 1
    assert stats.hit_rate == 1.0
    assert stats.execution_rate == 0.5


def test_confidenceless_stance_scores_hit_rate_but_no_brier():
    built = card("c1", stances={"analyst": 0.5}, verdicts={"analyst": "right"})
    built.per_module[0].confidence = None
    stats = scoring.score(scoring.observations([built]), module="analyst")
    assert stats.hit_rate == 1.0
    assert stats.brier is None


def test_abstained_modules_are_never_scored():
    built = card("c1", stances={"analyst": 0.8}, verdicts={"analyst": "right"})
    built.per_module[0].abstained = True
    assert scoring.observations([built]) == []


def test_ungraded_cards_are_ignored():
    built = card("c1", stances={"analyst": 0.8}, verdicts={"analyst": "right"}, resolved=False)
    assert scoring.observations([built]) == []


def test_per_domain_scores_are_separated():
    cards = [
        card("c1", stances={"strategist": 0.7}, verdicts={"strategist": "right"}, domains=["negotiation"]),
        card("c2", stances={"strategist": 0.7}, verdicts={"strategist": "right"}, domains=["negotiation"]),
        card("c3", stances={"strategist": 0.7}, verdicts={"strategist": "wrong"}, domains=["finance"]),
    ]
    items = scoring.observations(cards)
    assert scoring.score(items, module="strategist", domain="negotiation").hit_rate == 1.0
    assert scoring.score(items, module="strategist", domain="finance").hit_rate == 0.0
    assert scoring.score(items, module="strategist").hit_rate == pytest.approx(2 / 3, abs=1e-4)


def test_display_threshold_withholds_small_samples():
    cards = [
        card(f"c{i}", stances={"analyst": 0.6}, verdicts={"analyst": "right"}) for i in range(3)
    ]
    stats = scoring.score(scoring.observations(cards), module="analyst")
    assert stats.n == 3
    assert stats.displayable is False


# ────────────────────────────────────────────────────────────── priors ──────


def test_no_priors_below_the_evidence_threshold():
    """Two data points is an anecdote (ADR-018)."""
    cards = [
        card("c1", stances={"analyst": 0.95}, verdicts={"analyst": "wrong"}),
        card("c2", stances={"analyst": 0.95}, verdicts={"analyst": "wrong"}),
    ]
    assert priors.build(cards) == {} or priors.for_module(cards, "analyst") == []


def test_overconfidence_prior_reports_real_numbers():
    cards = [
        card(f"c{i}", stances={"analyst": 0.9}, verdicts={"analyst": "wrong" if i else "right"})
        for i in range(4)
    ]
    built = priors.for_module(cards, "analyst")
    calibration = [p for p in built if "confidence" in p.pattern]
    assert calibration, built
    prior = calibration[0]
    assert prior.evidence_count == 4
    assert "90%" in prior.pattern  # the stated confidence
    assert "25%" in prior.pattern  # 1 right out of 4
    assert len(prior.derived_from) == 4


def test_well_calibrated_module_gets_no_calibration_prior():
    cards = [
        card(f"c{i}", stances={"analyst": 0.75}, verdicts={"analyst": "right" if i < 3 else "wrong"})
        for i in range(4)
    ]
    assert not [p for p in priors.for_module(cards, "analyst") if "confidence" in p.pattern]


def test_low_execution_prior_fires():
    cards = [
        card(
            f"c{i}",
            stances={"tactician": 0.6},
            verdicts={"tactician": "untested"},
            followed=set(),
        )
        for i in range(4)
    ]
    built = priors.for_module(cards, "tactician")
    execution = [p for p in built if "acted on" in p.pattern]
    assert execution
    assert "0 of your 4" in execution[0].pattern


def test_off_menu_prior_is_council_wide():
    cards = [
        card(
            f"c{i}",
            stances={"analyst": 0.6, "tactician": 0.6},
            verdicts={"analyst": "right", "tactician": "wrong"},
            chose_was_proposed=False,
        )
        for i in range(4)
    ]
    built = priors.build(cards)
    for module in ("analyst", "tactician"):
        off_menu = [p for p in built[module] if "no module had proposed" in p.pattern]
        assert off_menu, module
        # Provenance stays honest: it is a council-level finding, not the module's.
        assert off_menu[0].module == "council"


def test_domain_weakness_prior_names_the_domain():
    cards = [
        card(
            f"c{i}",
            stances={"strategist": 0.7},
            verdicts={"strategist": "wrong"},
            domains=["finance"],
        )
        for i in range(3)
    ]
    built = priors.for_module(cards, "strategist")
    weak = [p for p in built if p.domain == "finance"]
    assert weak
    assert "not held up" in weak[0].pattern


def test_prior_evidence_count_floor_is_enforced_by_the_schema():
    from pydantic import ValidationError

    from app.schemas.cards import Prior

    with pytest.raises(ValidationError):
        Prior(module="analyst", pattern="too thin", evidence_count=MIN_N_FOR_PRIOR - 1)


# ───────────────────────────────────────────────── the grader is blind ─────


def test_grade_prompt_never_reveals_a_confidence_score():
    """ADR-021. If the grader sees the confidence, the Brier score is circular."""
    built = card(
        "c1",
        stances={"analyst": 0.87, "tactician": 0.42},
        verdicts={"analyst": "right", "tactician": "wrong"},
    )
    prompt = renderer.render(
        "grade.jinja",
        card=built,
        resolution=built.resolution,
        proposed=["analyst: analyst says do it"],
        metrics={},
        minority=[],
    )
    for forbidden in ("0.87", "0.42", "87%", "42%"):
        assert forbidden not in prompt, f"grade prompt leaked confidence {forbidden}"
    # It must still see the falsifier — that is a claim about the world, not a
    # claim about certainty, and grading it is the point.
    assert "would be wrong if" in prompt
    assert "MODULE: analyst" in prompt


async def test_grader_refuses_a_partial_council(council):
    """A missing verdict would silently drop a module out of its own history."""
    built = card(
        "c1",
        stances={"analyst": 0.8, "tactician": 0.8},
        verdicts={"analyst": "right", "tactician": "right"},
    )
    built.scoring = None

    class OneModuleRouter:
        def __init__(self, inner):
            self._inner = inner

        async def complete(self, role, request, *, override=None):
            # Force the grader's own coverage check by returning a single verdict.
            import json

            from app.llm.base import LLMResponse

            payload = {
                "expected_outcome_met": "yes",
                "chose_was_proposed": True,
                "module_verdicts": [
                    {"module": "analyst", "verdict": "right", "justification": "x"}
                ],
            }
            return LLMResponse(text=json.dumps(payload), provider="mock", model="m")

    with pytest.raises(GradingFailed, match="tactician"):
        await grade(built, built.resolution, OneModuleRouter(council._router))  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────── end to end ───────


async def test_resolve_then_priors_reach_the_next_deliberation(council):
    """The whole loop: deliberate, resolve, grade, and see a prior arrive in a prompt."""
    ids: list[str] = []
    for index in range(4):
        result = await council.run(
            DeliberationRequest(
                question=f"{QUESTION} (round {index})", depth="quick", preset="solo:analyst"
            )
        )
        cards = await council.store.list_cards()
        ids.append(cards[0].id)
        await council.resolve(
            cards[0].id,
            Resolution(
                chose="something nobody suggested",
                actual_outcome="it went badly",
                happened_at=TODAY,
                surprises=["an actor nobody mentioned blocked it"],
            ),
        )

    assert len(set(ids)) == 4
    graded = [c for c in await council.store.list_cards() if c.graded]
    assert len(graded) == 4

    # Scores exist but are correctly withheld from display at n=4.
    scores = await council.store.scores()
    assert scores
    assert all(not s.displayable for s in scores)

    built = await council.store.priors("analyst")
    assert built, "four graded cards should have produced at least one prior"
    assert all(p.evidence_count >= MIN_N_FOR_PRIOR for p in built)
    assert all(p.derived_from for p in built), "every prior must cite its cards"

    # And the prior actually reaches the module on its next run.
    recorder = RecordingRouter(council._router)
    council._router = recorder
    council._engine._router = recorder
    await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="solo:analyst")
    )
    stage_prompts = [
        user for tag, _system, user in recorder.calls if tag.startswith("analyst:")
    ]
    assert stage_prompts
    assert any("WHAT YOU KNOW ABOUT THIS USER" in p for p in stage_prompts)
    assert any(built[0].pattern[:40] in p for p in stage_prompts), (
        "the computed prior never reached a stage prompt"
    )


async def test_resolution_survives_a_grader_failure(council):
    """The outcome is the expensive thing to collect; never lose it to a bad grade."""
    result = await council.run(
        DeliberationRequest(question="Should I ship on Friday?", depth="quick", preset="solo:optimizer")
    )
    cards = await council.store.list_cards()
    card_id = cards[0].id

    async def explode(*_args, **_kwargs):
        raise ValueError("grader is down")

    council._router.complete = explode  # type: ignore[method-assign]
    with pytest.raises(Exception):
        await council.resolve(
            card_id,
            Resolution(chose="shipped", actual_outcome="fine", happened_at=TODAY),
        )

    saved = await council.store.get_card(card_id)
    assert saved is not None
    assert saved.resolution is not None, "the resolution must be saved before grading"
    assert saved.scoring is None


async def test_verdict_can_be_overridden_by_a_human(council):
    await council.run(
        DeliberationRequest(question="Should I ship on Friday?", depth="quick", preset="solo:optimizer")
    )
    cards = await council.store.list_cards()
    card_id = cards[0].id
    await council.resolve(
        card_id, Resolution(chose="shipped", actual_outcome="fine", happened_at=TODAY)
    )

    updated = await council.override_verdict(card_id, "optimizer", "wrong", "I disagree")
    verdict = updated.scoring.verdict_for("optimizer")  # type: ignore[union-attr]
    assert verdict is not None
    assert verdict.verdict == "wrong"
    assert verdict.overridden is True
    assert verdict.justification == "I disagree"


async def test_resolution_extracts_memories_with_each_modules_own_kind(council):
    """Six modules, six extraction biases — the mechanism behind "Audrey remembers
    the emotional history while Klein remembers the facts"."""
    await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="full")
    )
    cards = await council.store.list_cards()
    await council.resolve(
        cards[0].id,
        Resolution(
            chose="stayed and asked for it in writing",
            actual_outcome="the offer arrived nine days later",
            happened_at=TODAY,
        ),
    )

    expected_kind = {
        "analyst": "fact",
        "tactician": "opportunity",
        "strategist": "power_structure",
        "psychologist": "emotional",
        "optimizer": "workflow",
        "ethicist": "promise",
    }
    for module, kind in expected_kind.items():
        remembered = await council.store.recall(module, QUESTION, k=10)
        assert remembered, f"{module} extracted nothing"
        assert all(m.kind == kind for m in remembered), (
            f"{module} should remember '{kind}' items, got "
            f"{ {m.kind for m in remembered} }"
        )
        assert all(m.source_card_id == cards[0].id for m in remembered)


async def test_memories_are_capped_per_module(council):
    """Three per module. Everything remembered means nothing is."""
    from app.learning.extraction import MAX_PER_MODULE, extract

    await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="solo:analyst")
    )
    cards = await council.store.list_cards()
    card_obj = cards[0]
    card_obj.resolution = Resolution(
        chose="x", actual_outcome="y", happened_at=TODAY
    )

    class FloodRouter:
        async def complete(self, role, request, *, override=None):
            import json

            from app.llm.base import LLMResponse

            payload = {
                "memories": [
                    {
                        "module": "analyst",
                        "kind": "fact",
                        "content": f"fact number {i}",
                        "salience": 0.9,
                    }
                    for i in range(12)
                ]
            }
            return LLMResponse(text=json.dumps(payload), provider="mock", model="m")

    got = await extract(card_obj, card_obj.resolution, FloodRouter())  # type: ignore[arg-type]
    assert len(got) == MAX_PER_MODULE


async def test_extraction_ignores_memories_for_modules_that_did_not_run(council):
    from app.learning.extraction import extract

    await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="solo:analyst")
    )
    card_obj = (await council.store.list_cards())[0]
    card_obj.resolution = Resolution(chose="x", actual_outcome="y", happened_at=TODAY)

    class WrongModuleRouter:
        async def complete(self, role, request, *, override=None):
            import json

            from app.llm.base import LLMResponse

            payload = {
                "memories": [
                    {"module": "ethicist", "kind": "promise", "content": "not in this run", "salience": 0.9},
                    {"module": "analyst", "kind": "fact", "content": "legitimate fact", "salience": 0.6},
                ]
            }
            return LLMResponse(text=json.dumps(payload), provider="mock", model="m")

    got = await extract(card_obj, card_obj.resolution, WrongModuleRouter())  # type: ignore[arg-type]
    assert [m.module for m in got] == ["analyst"]


async def test_extraction_failure_never_breaks_a_resolution(council):
    """The outcome is the expensive artefact; memory is an optimisation on top."""
    await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="solo:analyst")
    )
    card_obj = (await council.store.list_cards())[0]

    import app.council.orchestrator as orchestrator

    async def explode(*_args, **_kwargs):
        raise RuntimeError("extractor down")

    original = orchestrator.extract_memories
    orchestrator.extract_memories = explode  # type: ignore[assignment]
    try:
        graded = await council.resolve(
            card_obj.id,
            Resolution(chose="x", actual_outcome="y", happened_at=TODAY),
        )
    finally:
        orchestrator.extract_memories = original  # type: ignore[assignment]

    assert graded.resolution is not None
    assert graded.graded, "grading must still have completed"


async def test_recall_prefers_lexical_overlap_then_salience(council):
    from app.schemas.cards import Memory

    await council.store.remember(
        "analyst",
        [
            Memory(id="m1", module="analyst", kind="fact", content="runway is four months of savings", salience=0.4),
            Memory(id="m2", module="analyst", kind="fact", content="the dog is called biscuit", salience=0.4),
            Memory(id="m3", module="analyst", kind="fact", content="nothing is ever put in writing", salience=0.95),
        ],
    )
    found = await council.store.recall("analyst", "how much runway is left in savings", k=5)
    ids = [m.id for m in found]
    assert ids[0] == "m1", "the lexically matching memory should come first"
    # A highly salient memory surfaces even with no shared vocabulary.
    assert "m3" in ids
    # An irrelevant, unremarkable one does not.
    assert "m2" not in ids


async def test_recall_returns_nothing_for_an_empty_store(council):
    assert await council.store.recall("analyst", "anything") == []


def test_card_status_transitions():
    open_card = card("c1", stances={"analyst": 0.5}, verdicts={}, resolved=False, check_in=90)
    assert open_card.status(TODAY) == "open"
    assert open_card.status(TODAY + timedelta(days=91)) == "due"

    resolved = card("c2", stances={"analyst": 0.5}, verdicts={"analyst": "right"})
    assert resolved.status(TODAY + timedelta(days=999)) == "resolved"
