"""TraceGraph construction (ADR-015).

Pure functions over the execution record. Nothing here calls a model; every node
references a real validated artifact and every edge comes from a declared `reads`, a
critique's `target_ref`, or an accepted critique. The map cannot disagree with the
territory because it is made of the territory.
"""

from __future__ import annotations

from ..schemas.council import Critique, Deliberation, ModuleRun, Revision
from ..schemas.program import CONTEXT_REF, AgentProgram
from ..schemas.trace import TraceGraph, TraceNode

QUESTION_ID = "question"
CONTEXT_ID = "context"


def artifact_node_id(module: str, stage_id: str) -> str:
    return f"a:{module}:{stage_id}"


def critique_node_id(index: int) -> str:
    return f"c:{index}"


def revision_node_id(module: str) -> str:
    return f"r:{module}"


def build(
    deliberation: Deliberation, programs: dict[str, AgentProgram]
) -> TraceGraph:
    graph = TraceGraph()

    graph.add_node(
        TraceNode(
            id=QUESTION_ID,
            kind="question",
            label=_clip(deliberation.question, 120),
            detail=deliberation.question,
        )
    )
    graph.add_node(
        TraceNode(
            id=CONTEXT_ID,
            kind="context",
            label=_clip(deliberation.context.normalised or "decision context", 120),
            detail=", ".join(deliberation.context.domains),
        )
    )
    graph.add_edge(QUESTION_ID, CONTEXT_ID, "derives_from")

    for run in deliberation.runs:
        _add_run(graph, run, programs.get(run.module))

    for index, critique in enumerate(deliberation.critiques):
        _add_critique(graph, index, critique)

    for revision in deliberation.revisions:
        _add_revision(graph, revision, deliberation.critiques)

    if deliberation.synthesis is not None:
        _add_synthesis(graph, deliberation)

    graph.assign_depths(QUESTION_ID)
    return graph


def _add_run(graph: TraceGraph, run: ModuleRun, program: AgentProgram | None) -> None:
    for artifact in run.artifacts:
        node_id = artifact_node_id(run.module, artifact.stage_id)
        graph.add_node(
            TraceNode(
                id=node_id,
                kind="conclusion" if artifact.kind == "Conclusion" else "stage_artifact",
                label=artifact.title or artifact.stage_id,
                module=run.module,
                stage_id=artifact.stage_id,
                artifact_kind=artifact.kind,
                detail=artifact.notes or "",
            )
        )

    # Data-flow edges come straight from the program's declared `reads`.
    if program is not None:
        for stage in program.stages:
            dst = artifact_node_id(run.module, stage.id)
            if graph.node(dst) is None:
                continue
            for ref in stage.reads:
                src = CONTEXT_ID if ref == CONTEXT_REF else artifact_node_id(run.module, ref)
                graph.add_edge(src, dst, "concludes" if stage.terminal else "derives_from")

    if run.abstained:
        node_id = f"x:{run.module}"
        graph.add_node(
            TraceNode(
                id=node_id,
                kind="abstention",
                label=f"{run.module} abstained",
                module=run.module,
                stage_id=run.abstained_at,
                status="failed",
                detail=run.abstain_reason or "",
            )
        )
        last = run.artifacts[-1] if run.artifacts else None
        src = artifact_node_id(run.module, last.stage_id) if last else CONTEXT_ID
        graph.add_edge(src, node_id, "derives_from")


def _add_critique(graph: TraceGraph, index: int, critique: Critique) -> None:
    node_id = critique_node_id(index)
    graph.add_node(
        TraceNode(
            id=node_id,
            kind="critique",
            label=f"{critique.critic} → {critique.target}",
            module=critique.critic,
            detail=critique.statement,
            status="ok" if critique.kind != "strong_agreement" else "repaired",
        )
    )
    # Point at the row it targets when it named one; otherwise at the conclusion.
    target_stage = critique.target_ref.stage_id if critique.target_ref else None
    dst = (
        artifact_node_id(critique.target, target_stage)
        if target_stage
        else _conclusion_node(graph, critique.target)
    )
    if dst:
        graph.add_edge(node_id, dst, "critiques", critique.kind)


def _add_revision(graph: TraceGraph, revision: Revision, critiques: list[Critique]) -> None:
    node_id = revision_node_id(revision.module)
    graph.add_node(
        TraceNode(
            id=node_id,
            kind="revision",
            label=f"{revision.module} revised",
            module=revision.module,
            detail=revision.delta,
        )
    )
    conclusion = _conclusion_node(graph, revision.module)
    if conclusion:
        graph.add_edge(conclusion, node_id, "derives_from")
    accepted_from = {a.from_module for a in revision.accepted}
    for index, critique in enumerate(critiques):
        if critique.target == revision.module and critique.critic in accepted_from:
            graph.add_edge(critique_node_id(index), node_id, "revises")


def _add_synthesis(graph: TraceGraph, deliberation: Deliberation) -> None:
    synthesis = deliberation.synthesis
    assert synthesis is not None

    for index, disagreement in enumerate(synthesis.disagreements):
        node_id = f"conflict:{index}"
        graph.add_node(
            TraceNode(
                id=node_id,
                kind="conflict",
                label=_clip(disagreement.issue, 90),
                detail=disagreement.why_it_matters,
            )
        )
        for position in disagreement.positions:
            src = _conclusion_node(graph, position.module)
            if src:
                graph.add_edge(src, node_id, "conflicts_with", position.module)

    for index, point in enumerate(synthesis.consensus):
        node_id = f"consensus:{index}"
        graph.add_node(
            TraceNode(id=node_id, kind="consensus", label=_clip(point.point, 90))
        )
        for ref in point.supported_by:
            graph.add_edge(
                artifact_node_id(ref.module, ref.stage_id), node_id, "supports", ref.row_id or ""
            )
        for module in point.modules:
            src = _conclusion_node(graph, module)
            if src:
                graph.add_edge(src, node_id, "supports", module)

    graph.add_node(
        TraceNode(
            id="recommendation",
            kind="recommendation",
            label=_clip(synthesis.recommendation.action, 140),
            detail=synthesis.recommendation.first_action,
        )
    )
    for node in list(graph.nodes):
        if node.kind in ("consensus", "conflict") or (
            node.kind == "revision" or node.kind == "conclusion"
        ):
            graph.add_edge(node.id, "recommendation", "derives_from")


def _conclusion_node(graph: TraceGraph, module: str) -> str | None:
    for node in graph.nodes:
        if node.module == module and node.kind == "conclusion":
            return node.id
    return None


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
