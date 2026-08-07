"""Prior generation.

Priors are the only thing that flows from outcomes back into reasoning, so they are
built under three rules (ADR-018):

1. The **numbers are computed here, in Python**. An LLM never phrases a count. Every
   sentence below is a template filled from real arithmetic, which is why a module can
   be told "3 of 8" and trust it.
2. **`evidence_count >= 3`**, and every prior cites the cards it came from. Two data
   points is an anecdote, and an anecdote injected as a prior is how a system becomes
   confidently wrong about one specific person.
3. Priors **never modify a program**. They arrive as memory the module may argue with.

Each rule below earns its place by being actionable: a module that learns "you decline
one-way moves" changes what it proposes, and one that learns "your 80% happens 55% of
the time" changes what it claims.
"""

from __future__ import annotations

from ..core.logging import get_logger
from ..programs import loader
from ..schemas.cards import MIN_N_FOR_PRIOR, DecisionCard, Prior
from ..schemas.common import ModuleId
from .scoring import metric_tally, observations, score

log = get_logger(__name__)

OVERCONFIDENCE_THRESHOLD = 0.15
LOW_EXECUTION_THRESHOLD = 0.5
DOMAIN_STRENGTH = 0.75
DOMAIN_WEAKNESS = 0.4
METRIC_FAILURE_RATIO = 0.5


def build(cards: list[DecisionCard]) -> dict[ModuleId, list[Prior]]:
    """All priors, keyed by the module that should be told about them."""
    graded = [c for c in cards if c.graded]
    if not graded:
        return {}

    items = observations(graded)
    modules = sorted({o.module for o in items})
    out: dict[ModuleId, list[Prior]] = {m: [] for m in modules}

    for module in modules:
        out[module].extend(_calibration(items, module))
        out[module].extend(_execution(items, module))
        out[module].extend(_domains(items, module))
        out[module].extend(_metrics(graded, module))

    # Council-level findings go to everyone: they are facts about what the whole
    # council keeps missing, and no single module owns them.
    shared = [*_off_menu(graded), *_unpredicted(graded)]
    for module in modules:
        out[module].extend(shared)

    return {module: priors for module, priors in out.items() if priors}


def for_module(cards: list[DecisionCard], module: ModuleId) -> list[Prior]:
    return build(cards).get(module, [])


# ─────────────────────────────────────────────────────────────────── rules ──


def _calibration(items, module: ModuleId) -> list[Prior]:
    stats = score(items, module=module)
    gap = stats.overconfidence
    if stats.n < MIN_N_FOR_PRIOR or gap is None or stats.mean_confidence is None:
        return []
    if abs(gap) < OVERCONFIDENCE_THRESHOLD:
        return []

    direction = "higher than" if gap > 0 else "lower than"
    return [
        Prior(
            module=module,
            pattern=(
                f"Your stated confidence has run {direction} your accuracy on this "
                f"user's decisions: you averaged {stats.mean_confidence:.0%} confident "
                f"and were right {stats.hit_rate:.0%} of the time across "
                f"{stats.n} tested decisions."
            ),
            evidence_count=stats.n,
            derived_from=_cards_for(items, module),
            confidence=min(0.9, 0.4 + stats.n * 0.05),
        )
    ]


def _execution(items, module: ModuleId) -> list[Prior]:
    relevant = [o for o in items if o.module == module]
    if len(relevant) < MIN_N_FOR_PRIOR:
        return []
    taken = sum(1 for o in relevant if o.followed)
    rate = taken / len(relevant)
    if rate >= LOW_EXECUTION_THRESHOLD:
        return []
    return [
        Prior(
            module=module,
            pattern=(
                f"This user has acted on {taken} of your {len(relevant)} "
                f"recommendations. Advice they will not take has no effect on their "
                f"life, however sound it is — account for what they will actually do."
            ),
            evidence_count=len(relevant),
            derived_from=[o.card_id for o in relevant],
            confidence=min(0.9, 0.4 + len(relevant) * 0.05),
        )
    ]


def _domains(items, module: ModuleId) -> list[Prior]:
    domains = {domain for o in items if o.module == module for domain in o.domains}
    out: list[Prior] = []
    for domain in sorted(domains):
        stats = score(items, module=module, domain=domain)
        if stats.n < MIN_N_FOR_PRIOR or stats.hit_rate is None:
            continue
        if stats.hit_rate >= DOMAIN_STRENGTH:
            verdict = "held up well"
        elif stats.hit_rate <= DOMAIN_WEAKNESS:
            verdict = "not held up"
        else:
            continue
        out.append(
            Prior(
                module=module,
                pattern=(
                    f"On {domain} decisions your reasoning has {verdict} for this user: "
                    f"right in {stats.hit_rate:.0%} of {stats.n} tested cases."
                ),
                evidence_count=stats.n,
                derived_from=[
                    o.card_id for o in items if o.module == module and domain in o.domains
                ],
                confidence=min(0.85, 0.35 + stats.n * 0.05),
                domain=domain,
            )
        )
    return out


def _metrics(cards: list[DecisionCard], module: ModuleId) -> list[Prior]:
    """Priors from a module's own declared success questions.

    The most on-spec kind: the module wrote these questions itself, so an answer of
    "no, repeatedly" is a failure it already agreed was worth measuring.
    """
    programs = loader.programs()
    if module not in programs:
        return []
    questions = {m.id: m.question.strip() for m in programs[module].success_metrics}
    tally = metric_tally(cards)

    out: list[Prior] = []
    for (tallied_module, metric_id), counts in sorted(tally.items()):
        if tallied_module != module or metric_id not in questions:
            continue
        answered = counts["yes"] + counts["no"]
        if answered < MIN_N_FOR_PRIOR:
            continue
        if counts["no"] / answered <= METRIC_FAILURE_RATIO:
            continue
        out.append(
            Prior(
                module=module,
                pattern=(
                    f'On your own measure "{questions[metric_id]}" the answer has been '
                    f"no in {counts['no']} of {answered} resolved decisions."
                ),
                evidence_count=answered,
                derived_from=_cards_with_metric(cards, module, metric_id),
                confidence=min(0.85, 0.35 + answered * 0.05),
            )
        )
    return out


def _off_menu(cards: list[DecisionCard]) -> list[Prior]:
    """How often the user did something no module proposed.

    A direct measurement of the council's option-generation blindness, and the reason
    `Resolution.chose` is free text rather than an option id.
    """
    judged = [c for c in cards if c.scoring is not None]
    if len(judged) < MIN_N_FOR_PRIOR:
        return []
    off = [c for c in judged if c.scoring and not c.scoring.chose_was_proposed]
    if not off or len(off) / len(judged) < 0.3:
        return []
    return [
        Prior(
            module="council",
            pattern=(
                f"In {len(off)} of {len(judged)} resolved decisions this user did "
                f"something no module had proposed. Widen the option set before "
                f"ranking it."
            ),
            evidence_count=len(judged),
            derived_from=[c.id for c in off],
            confidence=0.7,
        )
    ]


def _unpredicted(cards: list[DecisionCard]) -> list[Prior]:
    with_surprises = [
        c for c in cards if c.scoring and c.scoring.unpredicted
    ]
    if len(with_surprises) < MIN_N_FOR_PRIOR:
        return []
    examples = [
        item
        for card in with_surprises[-3:]
        for item in (card.scoring.unpredicted[:1] if card.scoring else [])
    ]
    return [
        Prior(
            module="council",
            pattern=(
                f"In {len(with_surprises)} resolved decisions something occurred that "
                f"no module anticipated. Recent examples: {'; '.join(examples)}."
            ),
            evidence_count=len(with_surprises),
            derived_from=[c.id for c in with_surprises],
            confidence=0.65,
        )
    ]


def _cards_for(items, module: ModuleId) -> list[str]:
    return [o.card_id for o in items if o.module == module]


def _cards_with_metric(cards: list[DecisionCard], module: ModuleId, metric_id: str) -> list[str]:
    return [
        card.id
        for card in cards
        if card.scoring
        and any(
            a.module == module and a.metric_id == metric_id and a.answer in ("yes", "no")
            for a in card.scoring.metric_answers
        )
    ]
