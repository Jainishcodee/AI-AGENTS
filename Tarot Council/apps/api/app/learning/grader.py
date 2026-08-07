"""Blind outcome grading.

One LLM call per resolved card. It is shown every module's stance and falsifier, the
options that were proposed, and what actually happened — and is **never** shown any
module's confidence score (ADR-021). Calibration is arithmetic done afterwards; if
the grader could see the confidence, the arithmetic would be circular.

Everything the grader returns is a judgement about the world. Everything derived from
it is computed in `scoring.py`. That line is what makes the numbers trustworthy.
"""

from __future__ import annotations

from pydantic import ValidationError

from ..core.errors import CognitiveOSError
from ..core.logging import get_logger
from ..llm.base import LLMRequest
from ..llm.jsonio import extract_json
from ..llm.registry import Router
from ..programs import loader
from ..prompts import renderer
from ..schemas.cards import (
    CardScoring,
    DecisionCard,
    GraderResult,
    MetricAnswer,
    ModuleVerdict,
    Resolution,
)

log = get_logger(__name__)


class GradingFailed(CognitiveOSError):
    pass


async def grade(card: DecisionCard, resolution: Resolution, router: Router) -> CardScoring:
    if card.expected_outcome is None:
        log.warning("card %s has no expected_outcome; grading anyway", card.id)

    gradable = [s for s in card.per_module if not s.abstained]
    if not gradable:
        raise GradingFailed(f"card {card.id} has no module stances to grade")

    programs = loader.programs()
    metrics = {
        stance.module: list(programs[stance.module].success_metrics)
        for stance in gradable
        if stance.module in programs
    }

    prompt = renderer.render(
        "grade.jinja",
        card=card,
        resolution=resolution,
        proposed=_proposed_options(card),
        metrics=metrics,
        minority=card.minority_opinions,
    )

    try:
        response = await router.complete(
            "synthesis",
            LLMRequest(
                system=(
                    "You grade past decisions against recorded outcomes. You are "
                    "precise, and you use 'untested' whenever the advice was never "
                    "acted on."
                ),
                user=prompt,
                json_model=GraderResult,
                temperature=0.2,
                max_tokens=6144,
                tag=f"grade:{card.id}",
            ),
        )
        result = GraderResult.model_validate(extract_json(response.text))
    except (ValidationError, ValueError) as exc:
        raise GradingFailed(f"grader returned unusable output: {exc}") from exc

    expected = {s.module for s in gradable}
    returned = {v.module for v in result.module_verdicts}
    missing = expected - returned
    if missing:
        # Better to fail than to silently score a partial council: an absent verdict
        # would quietly drop that module out of its own calibration history.
        raise GradingFailed(
            f"grader skipped {', '.join(sorted(missing))}; every participating module "
            "must be graded"
        )

    valid_metrics = {
        (module, metric.id) for module, items in metrics.items() for metric in items
    }

    return CardScoring(
        expected_outcome_met=result.expected_outcome_met,
        chose_was_proposed=result.chose_was_proposed,
        module_verdicts=[
            ModuleVerdict(
                module=draft.module,
                verdict=draft.verdict,
                justification=draft.justification,
                followed=draft.followed,
                falsifier_fired=draft.falsifier_fired,
            )
            for draft in result.module_verdicts
            if draft.module in expected
        ],
        metric_answers=[
            MetricAnswer(
                module=draft.module,
                metric_id=draft.metric_id,
                answer=draft.answer,
                evidence=draft.evidence,
            )
            for draft in result.metric_answers
            if (draft.module, draft.metric_id) in valid_metrics
        ],
        unpredicted=result.unpredicted,
        grader_model=response.route,
    )


def _proposed_options(card: DecisionCard) -> list[str]:
    """What the council actually put on the table, for the off-menu check.

    Drawn from the stances rather than from the intake's option list: what matters is
    what a module *recommended*, not what was theoretically enumerated.
    """
    return [f"{s.module}: {s.stance}" for s in card.per_module if not s.abstained]
