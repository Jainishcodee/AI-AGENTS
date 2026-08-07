"""Per-module memory extraction.

Six modules, six biases about what is worth keeping. That is the mechanism behind
"Audrey remembers the emotional history while Klein remembers the facts" — not a
shared index queried six ways, but six stores filled by six different rules.

Extraction runs at **resolution**, not at deliberation time. Before the outcome you
only know what the user claimed; afterwards you know which of it mattered. A fact that
looked central and turned out to be irrelevant should not be remembered as central.
"""

from __future__ import annotations

import uuid

from pydantic import ValidationError

from ..core.logging import get_logger
from ..llm.base import LLMRequest
from ..llm.jsonio import extract_json
from ..llm.registry import Router
from ..programs import loader
from ..prompts import renderer
from ..schemas.cards import DecisionCard, ExtractionResult, Memory, Resolution
from ..schemas.common import MemoryKind, ModuleId

log = get_logger(__name__)

MAX_PER_MODULE = 3

EXTRACTION_RULES: dict[MemoryKind, str] = {
    "fact": (
        "Durable facts about the user's situation, and which of their beliefs turned "
        "out to be true or false. Anything that would move a future claim from "
        "'assumed' to 'given'."
    ),
    "opportunity": (
        "Openings that existed, what they were worth, and which kinds of move this "
        "user is actually willing to make. What they declined matters as much as what "
        "they took."
    ),
    "power_structure": (
        "Who really decided, who could block, and where formal authority and real "
        "influence turned out to differ. Obligations and alliances that proved real."
    ),
    "emotional": (
        "How people actually reacted, what they feared, and what the user turned out "
        "to be avoiding. Reaction patterns that will repeat."
    ),
    "workflow": (
        "What the user's effort actually bought, which constraint really bound, and "
        "whether any rule or system they adopted survived contact with their life."
    ),
    "promise": (
        "Commitments made or broken, to whom, and what the user later said they "
        "regretted or stood by. Their values as demonstrated rather than stated."
    ),
}


async def extract(
    card: DecisionCard, resolution: Resolution, router: Router
) -> list[Memory]:
    programs = loader.programs()
    kinds: dict[ModuleId, MemoryKind] = {
        stance.module: programs[stance.module].memory_kind
        for stance in card.per_module
        if stance.module in programs and not stance.abstained
    }
    if not kinds:
        return []

    prompt = renderer.render(
        "extract.jinja",
        card=card,
        resolution=resolution,
        kinds=kinds,
        rules=EXTRACTION_RULES,
        verdicts=card.scoring.module_verdicts if card.scoring else [],
    )

    try:
        response = await router.complete(
            "intake",  # cheap role: this is classification, not reasoning
            LLMRequest(
                system=(
                    "You extract durable memories from resolved decisions. You are "
                    "strict about what counts as durable, and comfortable returning "
                    "nothing."
                ),
                user=prompt,
                json_model=ExtractionResult,
                temperature=0.3,
                max_tokens=2048,
                tag=f"extract:{card.id}",
            ),
        )
        result = ExtractionResult.model_validate(extract_json(response.text))
    except (ValidationError, ValueError) as exc:
        # Never fail a resolution over memory extraction. The card and its scoring are
        # the durable record; memories are an optimisation on top of them.
        log.warning("memory extraction failed for card %s: %s", card.id, exc)
        return []

    out: list[Memory] = []
    per_module: dict[ModuleId, int] = {}
    for draft in result.memories:
        if draft.module not in kinds or not draft.content.strip():
            continue
        seen = per_module.get(draft.module, 0)
        if seen >= MAX_PER_MODULE:
            continue
        per_module[draft.module] = seen + 1
        out.append(
            Memory(
                id=uuid.uuid4().hex[:12],
                module=draft.module,
                # The kind comes from the module's spec, not from the model: a module's
                # memory type is a property of the module, not a per-item choice.
                kind=kinds[draft.module],
                content=draft.content.strip(),
                salience=draft.salience,
                source_card_id=card.id,
            )
        )
    return out
