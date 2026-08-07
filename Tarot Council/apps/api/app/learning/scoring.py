"""Calibration maths. Pure functions over resolved cards — no LLM anywhere in here.

The split is the point (ADR-021): a model judges *what happened*, and this module
computes *what that means about confidence*. Keeping the arithmetic out of the model
is what makes a claim like "your stated 80% has occurred 55% of the time" worth
printing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..schemas.cards import DecisionCard, ModuleScore
from ..schemas.common import ModuleId, Verdict

CORRECTNESS: dict[Verdict, float | None] = {
    "right": 1.0,
    "wrong": 0.0,
    "partial": 0.5,
    # Excluded from every rate. A module whose advice was never acted on has not
    # been tested, and scoring it either way would be fiction.
    "untested": None,
}

CHANCE_BRIER = 0.25
"""What you score by always saying 50%. A module above this is worse than a coin."""


@dataclass(slots=True)
class Observation:
    """One module's performance on one resolved decision."""

    module: ModuleId
    domains: tuple[str, ...]
    role: str
    confidence: float | None
    correctness: float | None
    followed: bool
    falsifier_fired: bool
    card_id: str


def observations(cards: list[DecisionCard]) -> list[Observation]:
    out: list[Observation] = []
    for card in cards:
        if not card.graded or card.scoring is None:
            continue
        stances = {s.module: s for s in card.per_module}
        for verdict in card.scoring.module_verdicts:
            stance = stances.get(verdict.module)
            if stance is None or stance.abstained:
                continue
            out.append(
                Observation(
                    module=verdict.module,
                    domains=tuple(card.domains),
                    role=stance.role,
                    confidence=stance.confidence.score if stance.confidence else None,
                    correctness=CORRECTNESS[verdict.verdict],
                    followed=verdict.followed,
                    falsifier_fired=verdict.falsifier_fired,
                    card_id=card.id,
                )
            )
    return out


def score(
    items: list[Observation], *, module: ModuleId, domain: str | None = None
) -> ModuleScore:
    """Aggregate one module's observations, optionally restricted to a domain.

    `n` counts *tested* observations. Execution and falsifier rates are computed over
    the wider set, because "you never took this advice" is itself a measurement and
    excluding it would flatter the module.
    """
    relevant = [o for o in items if o.module == module]
    if domain is not None:
        relevant = [o for o in relevant if domain in o.domains]
    if not relevant:
        return ModuleScore(module=module, domain=domain, n=0)

    tested = [o for o in relevant if o.correctness is not None]
    scored = [o for o in tested if o.confidence is not None]

    hit_rate = _mean([o.correctness for o in tested]) if tested else None
    mean_confidence = _mean([o.confidence for o in scored]) if scored else None
    brier = (
        _mean([(o.confidence - o.correctness) ** 2 for o in scored])  # type: ignore[operator]
        if scored
        else None
    )

    return ModuleScore(
        module=module,
        domain=domain,
        n=len(tested),
        brier=brier,
        hit_rate=hit_rate,
        mean_confidence=mean_confidence,
        execution_rate=_mean([1.0 if o.followed else 0.0 for o in relevant]),
        falsifier_hit_rate=_mean([1.0 if o.falsifier_fired else 0.0 for o in relevant]),
    )


def all_scores(cards: list[DecisionCard], *, include_domains: bool = True) -> list[ModuleScore]:
    items = observations(cards)
    modules = sorted({o.module for o in items})
    out = [score(items, module=module) for module in modules]

    if include_domains:
        pairs: set[tuple[ModuleId, str]] = set()
        for observation in items:
            for domain in observation.domains:
                pairs.add((observation.module, domain))
        out += [score(items, module=module, domain=domain) for module, domain in sorted(pairs)]

    return [s for s in out if s.n or s.execution_rate is not None]


def metric_tally(cards: list[DecisionCard]) -> dict[tuple[ModuleId, str], dict[str, int]]:
    """Answers to each module's own declared `success_metrics`, counted."""
    tally: dict[tuple[ModuleId, str], dict[str, int]] = defaultdict(
        lambda: {"yes": 0, "no": 0, "unclear": 0}
    )
    for card in cards:
        if card.scoring is None:
            continue
        for answer in card.scoring.metric_answers:
            tally[(answer.module, answer.metric_id)][answer.answer] += 1
    return dict(tally)


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 4)
