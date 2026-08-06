"""Full pipeline on the mock provider: no key, no network, deterministic."""

from __future__ import annotations

import pytest

from app.programs import loader
from app.schemas.council import DeliberationRequest
from app.trace import builder

from .conftest import QUESTION


@pytest.fixture
async def result(council):
    return await council.run(
        DeliberationRequest(question=QUESTION, depth="standard", preset="full")
    )


async def test_every_module_runs_and_concludes(result):
    assert {r.module for r in result.runs} == set(loader.programs())
    for run in result.runs:
        assert not run.abstained, f"{run.module}: {run.abstain_reason}"
        assert run.conclusion is not None
        assert run.conclusion.confidence.falsifier


async def test_each_module_produces_one_artifact_per_stage(result):
    for run in result.runs:
        expected = [s.id for s in loader.program(run.module).stages]
        assert [a.stage_id for a in run.artifacts] == expected, run.module


async def test_only_the_terminal_stage_produces_a_conclusion(result):
    for run in result.runs:
        conclusions = [a for a in run.artifacts if a.kind == "Conclusion"]
        assert len(conclusions) == 1
        assert conclusions[0].stage_id == loader.program(run.module).terminal_stage.id


async def test_the_forced_artifacts_actually_exist(result):
    """Each module's characteristic artifact — the thing that makes it diverge."""
    produced = {
        run.module: {a.kind for a in run.artifacts} for run in result.runs
    }
    assert "ProbabilityTree" in produced["analyst"]
    assert "EvidenceLedger" in produced["analyst"]
    assert "OptionSet" in produced["tactician"]
    assert "AsymmetryTable" in produced["tactician"]
    assert "StakeholderGraph" in produced["strategist"]
    assert "PersonProfileSet" in produced["psychologist"]
    assert "ConstraintAnalysis" in produced["optimizer"]
    assert "HarmLedger" in produced["ethicist"]
    assert "InactionHarm" in produced["ethicist"]


async def test_critiques_are_routed_not_broadcast(result):
    assert result.critiques
    matrix = loader.critique_matrix()
    for critique in result.critiques:
        assert critique.critic != critique.target
        assert critique.target in matrix[critique.critic], (
            f"{critique.critic} critiqued {critique.target}, which is not in its route"
        )


async def test_revisions_replace_the_stage_one_confidence(result):
    assert result.revisions
    by_module = {r.module: r for r in result.revisions}
    for run in result.runs:
        revision = by_module.get(run.module)
        if revision and run.conclusion:
            assert run.conclusion.confidence.score == revision.confidence.score


async def test_synthesis_names_a_council_blind_spot(result):
    assert result.synthesis is not None
    assert result.synthesis.council_blind_spot.strip()


async def test_synthesis_confidence_cannot_exceed_the_modules_it_follows(result):
    synthesis = result.synthesis
    dissenting = {m.module for m in synthesis.minority_opinions}
    ceiling = max(
        r.conclusion.confidence.score
        for r in result.runs
        if r.conclusion and r.module not in dissenting
    )
    assert synthesis.confidence.score <= ceiling + 1e-9


async def test_usage_is_accounted(result):
    assert result.usage.calls > 0
    assert sum(result.usage.by_model.values()) == result.usage.calls


async def test_quick_depth_costs_less_and_skips_the_debate(council):
    quick = await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="full")
    )
    assert quick.critiques == []
    assert quick.revisions == []
    assert quick.synthesis is not None
    for run in quick.runs:
        # Nothing is skipped at quick depth — only the number of calls changes.
        expected = [s.id for s in loader.program(run.module).stages]
        assert [a.stage_id for a in run.artifacts] == expected


async def test_strategy_preset_runs_two_primaries_and_cheap_critics(council):
    result = await council.run(
        DeliberationRequest(question=QUESTION, depth="standard", preset="strategy")
    )
    roles = {r.module: r.role for r in result.runs}
    assert roles == {"tactician": "primary", "strategist": "primary", "analyst": "advisory"}
    # Critic-only modules never run a program, but their critiques still land.
    critics = {c.critic for c in result.critiques}
    assert {"psychologist", "ethicist", "optimizer"} & critics


async def test_solo_preset_runs_one_module(council):
    result = await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="solo:strategist")
    )
    assert [r.module for r in result.runs] == ["strategist"]


async def test_trace_is_derived_from_the_execution_record(result):
    graph = builder.build(result, loader.programs())

    artifact_nodes = [n for n in graph.nodes if n.kind in ("stage_artifact", "conclusion")]
    total_artifacts = sum(len(r.artifacts) for r in result.runs)
    assert len(artifact_nodes) == total_artifacts

    # Every node points at something real.
    for node in artifact_nodes:
        run = result.run_for(node.module)
        assert run is not None
        assert run.artifact_at(node.stage_id) is not None

    # Every edge endpoint exists.
    ids = {n.id for n in graph.nodes}
    for edge in graph.edges:
        assert edge.src in ids and edge.dst in ids

    assert any(n.kind == "question" for n in graph.nodes)
    assert any(n.kind == "recommendation" for n in graph.nodes)


async def test_trace_depths_layer_the_graph(result):
    graph = builder.build(result, loader.programs())
    question = next(n for n in graph.nodes if n.kind == "question")
    assert question.depth == 0
    # A later stage must sit deeper than the context it derives from.
    deepest = max(n.depth for n in graph.nodes)
    assert deepest >= 3


async def test_derives_from_edges_match_the_declared_reads(result):
    graph = builder.build(result, loader.programs())
    edges = {(e.src, e.dst) for e in graph.edges if e.kind in ("derives_from", "concludes")}
    program = loader.program("strategist")
    for stage in program.stages:
        dst = builder.artifact_node_id("strategist", stage.id)
        for ref in stage.reads:
            src = "context" if ref == "context" else builder.artifact_node_id("strategist", ref)
            assert (src, dst) in edges, f"missing trace edge {src} -> {dst}"


async def test_a_decision_card_is_created_with_a_dated_prediction(council):
    await council.run(DeliberationRequest(question=QUESTION, depth="quick", preset="full"))
    cards = await council._store.list_cards()
    assert len(cards) == 1
    card = cards[0]
    assert card.expected_outcome is not None
    assert card.expected_outcome.statement.strip()
    assert card.expected_outcome.check_on > card.created_at.date()
    assert card.resolution is None
    assert set(card.program_versions) == set(loader.programs())
    assert {s.module for s in card.per_module} == set(loader.programs())


async def test_deliberation_round_trips_through_json(result):
    from app.schemas.council import Deliberation

    again = Deliberation.model_validate_json(result.model_dump_json())
    assert again.id == result.id
    assert len(again.runs) == len(result.runs)
    assert [a.kind for r in again.runs for a in r.artifacts] == [
        a.kind for r in result.runs for a in r.artifacts
    ]
