"""The divergence harness — the instrument for the product's central claim.

`SPEC-FORMAT.md` §"Authoring a new module" promises this file, and it is the gate a
Phase 5 marketplace module has to pass. Two things are being tested:

1. That the six built-in modules pass.
2. That the harness **fails a module that deserves to fail**. An instrument only ever
   pointed at a passing case is not known to detect anything, so most of this file
   constructs bad module sets and degenerate councils on purpose.
"""

from __future__ import annotations

import pytest
import yaml

from app.learning import divergence
from app.learning.divergence import BATTERY_FILE, _similarity, report, structural
from app.programs import loader
from app.schemas.council import (
    AcceptedCritique,
    Critique,
    DecisionContext,
    Deliberation,
    Minority,
    Recommendation,
    Revision,
    Synthesis,
)
from app.schemas.council import Disagreement, ExpectedOutcomeDraft, ModuleRun, Position
from app.schemas.artifacts import Conclusion
from app.schemas.common import Confidence
from app.schemas.divergence import (
    MAX_STANCE_SIMILARITY,
    MIN_DISSENTS,
    BatteryItem,
)

from .conftest import QUESTION


# ─────────────────────────────────────────────────── the six built-ins pass ──


def test_the_six_modules_are_structurally_distinct():
    result = structural()
    assert result.problems == [], result.problems
    assert result.ok


def test_no_artifact_kind_is_produced_by_two_modules():
    """Two modules with the same representation converge however they are phrased."""
    shared = {k: v for k, v in structural().artifact_owners.items() if len(v) > 1}
    assert shared == {}, f"shared representations: {shared}"


def test_every_module_owns_at_least_one_artifact_type():
    for module in structural().modules:
        assert module.distinct, f"{module.module} has no unique artifact"
        assert module.unique_artifacts


def test_every_module_is_critiqued_and_critiques():
    for module in structural().modules:
        assert module.critiqued_by, f"nothing critiques {module.module}"
        assert module.critiques, f"{module.module} critiques nothing"


def test_every_modules_biases_are_watched_by_someone():
    for module in structural().modules:
        assert module.biases_detected_elsewhere > 0, (
            f"none of {module.module}'s biases are listed as detectable by another module"
        )


# ─────────────────────────────────── the harness fails what it should fail ──


def _twin_of(module: str, new_id: str):
    """A module that reasons identically to an existing one under a different name."""
    original = loader.program(module)
    return original.model_copy(update={"id": new_id})


def test_structural_rejects_a_module_with_no_unique_representation():
    programs = dict(loader.programs())
    programs["mimic"] = _twin_of("analyst", "mimic")
    result = structural(programs)

    assert not result.ok
    assert any("mimic" in p and "no artifact type" in p for p in result.problems)
    # And the module it copied now also loses its uniqueness — correctly.
    assert any("analyst" in p and "no artifact type" in p for p in result.problems)


def test_structural_rejects_a_module_nobody_critiques():
    """`critics` reads "who critiques *this* module", so an empty tuple means nobody does.

    That is the state ADR-003 makes dangerous: a module is never shown its own biases, so
    if nothing critiques it, its declared failure modes can never be caught by anyone.
    """
    programs = dict(loader.programs())
    programs["lonely"] = loader.program("analyst").model_copy(
        update={"id": "lonely", "critics": ()}
    )
    result = structural(programs)
    assert any("nothing critiques lonely" in p for p in result.problems)


def test_structural_rejects_a_module_that_critiques_nothing():
    programs = dict(loader.programs())
    # A module listed as nobody's critic critiques nothing, so it only defends itself.
    passive = loader.program("optimizer").model_copy(update={"id": "passive"})
    programs["passive"] = passive
    result = structural(programs)
    assert any("passive critiques nothing" in p for p in result.problems)


# ───────────────────────────────────────────────────── the live measurement ──

MODULES = ["analyst", "tactician", "strategist"]


def _conclusion(stance: str) -> Conclusion:
    return Conclusion(
        stance=stance,
        first_action="do the thing tomorrow",
        reasoning="because",
        confidence=Confidence(score=0.6, basis="b", falsifier="f"),
    )


def _deliberation(
    stances: dict[str, str],
    *,
    minority: list[str] = (),
    disagreeing: list[str] = (),
    critiques: list[tuple[str, str]] = (),
    accepted: list[tuple[str, str]] = (),
    abstained: list[str] = (),
    delib_id: str = "d1",
) -> Deliberation:
    return Deliberation(
        id=delib_id,
        question=QUESTION,
        preset="full",
        depth="quick",
        context=DecisionContext(question=QUESTION),
        runs=[
            ModuleRun(
                module=module,
                program_version=1,
                role="primary",
                conclusion=None if module in abstained else _conclusion(stance),
                abstained=module in abstained,
            )
            for module, stance in stances.items()
        ],
        critiques=[
            Critique(critic=critic, target=target, kind="missing_factor", statement="x")
            for critic, target in critiques
        ],
        revisions=[
            Revision(
                module=target,
                accepted=[
                    AcceptedCritique(from_module=critic, what="x", how_it_changes_my_view="y")
                ],
                stance="revised",
                confidence=Confidence(score=0.6, basis="b", falsifier="f"),
            )
            for critic, target in accepted
        ],
        synthesis=Synthesis(
            debate_summary="s",
            expected_outcome=ExpectedOutcomeDraft(statement="it works"),
            council_blind_spot="something nobody looked at",
            recommendation=Recommendation(action="a", first_action="b"),
            confidence=Confidence(score=0.6, basis="b", falsifier="f"),
            minority_opinions=[
                Minority(module=m, position="p", when_it_would_be_right="w") for m in minority
            ],
            disagreements=[
                Disagreement(
                    issue="the real question",
                    positions=[Position(module=m, position="p") for m in disagreeing],
                    why_it_matters="m",
                    what_would_resolve_it="r",
                )
            ]
            if disagreeing
            else [],
        ),
    )


ITEMS = [BatteryItem(id="b1", question="q1"), BatteryItem(id="b2", question="q2")]


def test_identical_stances_are_flagged_as_one_voice():
    """The failure the whole architecture exists to prevent."""
    same = "Ask for the offer in writing before Friday and hold the line"
    results = [
        _deliberation({m: same for m in MODULES}, minority=["analyst"], delib_id=f"d{i}")
        for i in range(2)
    ]
    result = report(ITEMS, results)

    assert result.mean_stance_similarity == 1.0
    for module in result.modules:
        assert any("word overlap" in p for p in module.problems), module.module


def test_genuinely_different_stances_and_dissent_pass():
    results = []
    for index in range(2):
        results.append(
            _deliberation(
                {
                    "analyst": "Gather the missing salary data before committing to anything",
                    "tactician": "Make the reversible move this week and force a reply",
                    "strategist": "Talk to the person who can quietly block this, first",
                },
                minority=["tactician", "strategist"],
                disagreeing=["analyst", "tactician"],
                critiques=[("tactician", "analyst")],
                accepted=[("tactician", "analyst")],
                delib_id=f"d{index}",
            )
        )
    result = report(ITEMS, results)

    assert result.mean_stance_similarity is not None
    assert result.mean_stance_similarity < MAX_STANCE_SIMILARITY
    tactician = next(m for m in result.modules if m.module == "tactician")
    assert tactician.dissents == MIN_DISSENTS
    assert tactician.critiques_accepted == 2
    assert tactician.passes, tactician.problems


def test_a_module_that_never_dissents_is_flagged():
    results = [
        _deliberation(
            {
                "analyst": "Gather the missing salary data first",
                "tactician": "Make the reversible move this week",
                "strategist": "Speak to the quiet blocker before anyone else",
            },
            minority=["tactician"],
            delib_id=f"d{i}",
        )
        for i in range(2)
    ]
    result = report(ITEMS, results)
    strategist = next(m for m in result.modules if m.module == "strategist")
    assert not strategist.passes
    assert any("always agrees is a voice" in p for p in strategist.problems)


def test_critiques_nobody_accepts_are_flagged_as_noise():
    results = [
        _deliberation(
            {
                "analyst": "Gather the missing salary data first",
                "tactician": "Make the reversible move this week",
                "strategist": "Speak to the quiet blocker before anyone else",
            },
            minority=["analyst", "tactician", "strategist"],
            critiques=[("strategist", "analyst")],
            delib_id=f"d{i}",
        )
        for i in range(2)
    ]
    result = report(ITEMS, results)
    strategist = next(m for m in result.modules if m.module == "strategist")
    assert any("none were accepted" in p for p in strategist.problems)


def test_a_module_that_always_abstains_is_reported_as_unmeasured():
    """Not the same as failing: nothing about it was measured, and saying so matters."""
    results = [
        _deliberation(
            {"analyst": "a", "tactician": "b", "strategist": "c"},
            abstained=["strategist"],
            delib_id=f"d{i}",
        )
        for i in range(2)
    ]
    result = report(ITEMS, results)
    strategist = next(m for m in result.modules if m.module == "strategist")
    assert strategist.abstentions == 2
    assert any("nothing about it was measured" in p for p in strategist.problems)


def test_decisions_with_no_disagreement_are_counted_and_explained():
    results = [
        _deliberation({"analyst": "a", "tactician": "b", "strategist": "c"}, delib_id=f"d{i}")
        for i in range(2)
    ]
    result = report(ITEMS, results)
    assert result.decisions_with_no_disagreement == 2
    assert any("no named disagreement" in note for note in result.notes)


def test_the_limitation_is_always_reported():
    """Reusing synthesis for dissent is a real trade-off; the report must say so."""
    result = report(ITEMS, [_deliberation({"analyst": "a"})])
    assert any("under-reports divergence" in note for note in result.notes)


def test_similarity_is_symmetric_and_bounded():
    assert _similarity("", "anything") == 0.0
    assert _similarity("quit the internship now", "quit the internship now") == 1.0
    left = _similarity("ask for it in writing", "wait for the offer to arrive")
    right = _similarity("wait for the offer to arrive", "ask for it in writing")
    assert left == right
    assert 0.0 <= left < 1.0


def test_stopwords_do_not_manufacture_similarity():
    """Two unrelated stances share only filler; that must not read as agreement."""
    score = _similarity(
        "You should be able to do this if it is what you want",
        "There will not be a way to have that when they are here",
    )
    assert score == 0.0


# ─────────────────────────────────────────────────────────────── the battery ──


def test_battery_is_well_formed():
    items = divergence.battery()
    assert len(items) >= 6, "too small a battery to measure anything"
    assert len({item.id for item in items}) == len(items), "duplicate battery ids"
    for item in items:
        assert len(item.question.split()) >= 12, f"{item.id} is too thin to have a tradeoff"
        assert item.notes.strip(), (
            f"{item.id} has no context, so modules with required inputs will abstain — "
            "and an abstention is not a disagreement"
        )
        assert item.domains, f"{item.id} has no domains, so per-domain divergence is invisible"


def test_battery_spans_several_domains():
    domains = {d for item in divergence.battery() for d in item.domains}
    assert len(domains) >= 5, f"battery covers only {domains}"


def test_battery_lives_outside_the_programs_directory():
    """`programs/*.yaml` means "this is a module"; the loader validates everything there."""
    assert BATTERY_FILE.is_file()
    assert BATTERY_FILE.parent.name == "learning"
    assert yaml.safe_load(BATTERY_FILE.read_text(encoding="utf-8"))


def test_limit_truncates_the_battery():
    assert len(divergence.battery(3)) == 3


# ──────────────────────────────────────────────────────── end to end on mock ──


@pytest.mark.asyncio
async def test_the_harness_detects_that_the_mock_council_is_degenerate(council):
    """The proof that the instrument works.

    Every module gets the same synthesised stance from the mock provider, so the mock
    council really *is* six voices. A harness that passed it would be measuring nothing.
    """
    result = await divergence.measure(council, limit=2, depth="quick", preset="full")

    assert result.mean_stance_similarity == 1.0
    assert set(result.failing) == {
        "analyst",
        "tactician",
        "strategist",
        "psychologist",
        "optimizer",
        "ethicist",
    }
    assert all(
        any("word overlap" in p for p in module.problems) for module in result.modules
    )


@pytest.mark.asyncio
async def test_measure_records_which_battery_items_it_ran(council):
    result = await divergence.measure(council, limit=2, depth="quick", preset="solo:analyst")
    assert result.battery == [item.id for item in divergence.battery(2)]
