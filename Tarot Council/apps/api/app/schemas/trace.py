"""Thinking Trace — derived from the execution record, never generated (ADR-015).

Nodes reference real validated artifacts. `derives_from` edges come from each
stage's declared `reads`; `critiques` edges come from `Critique.target_ref`. No LLM
call produces any part of this, so the map cannot disagree with the territory.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .common import ModuleId, StageId

NodeKind = Literal[
    "question",
    "context",
    "stage_artifact",
    "conclusion",
    "critique",
    "revision",
    "conflict",
    "consensus",
    "recommendation",
    "abstention",
]

EdgeKind = Literal[
    "derives_from",
    "critiques",
    "revises",
    "conflicts_with",
    "supports",
    "concludes",
]


class TraceNode(BaseModel):
    id: str
    kind: NodeKind
    label: str
    module: ModuleId | None = None
    stage_id: StageId | None = None
    artifact_kind: str | None = None
    depth: int = 0
    """Layer index for client-side layout. Computed from `derives_from` distance
    to the question node — no LLM decides where boxes go, so the same
    deliberation always renders identically."""
    status: Literal["ok", "repaired", "failed"] = "ok"
    detail: str = ""


class TraceEdge(BaseModel):
    src: str
    dst: str
    kind: EdgeKind
    label: str = ""


class TraceGraph(BaseModel):
    nodes: list[TraceNode] = Field(default_factory=list)
    edges: list[TraceEdge] = Field(default_factory=list)

    def add_node(self, node: TraceNode) -> TraceNode:
        self.nodes.append(node)
        return node

    def add_edge(self, src: str, dst: str, kind: EdgeKind, label: str = "") -> None:
        ids = {n.id for n in self.nodes}
        if src in ids and dst in ids:
            self.edges.append(TraceEdge(src=src, dst=dst, kind=kind, label=label))

    def node(self, node_id: str) -> TraceNode | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def assign_depths(self, root_id: str) -> None:
        """Longest-path layering over `derives_from` and `concludes` edges.

        Longest rather than shortest path: a stage that reads both `context` and a
        stage-5 artifact belongs after stage 5, not beside the context.
        """
        structural = [e for e in self.edges if e.kind in ("derives_from", "concludes")]
        adjacency: dict[str, list[str]] = {}
        for e in structural:
            adjacency.setdefault(e.src, []).append(e.dst)

        depth = {n.id: 0 for n in self.nodes}
        # Iterate to a fixed point; graphs here are tiny (<400 nodes) and acyclic
        # by construction, so bounded iteration is simpler than a topo sort.
        for _ in range(len(self.nodes) + 1):
            changed = False
            for src, dsts in adjacency.items():
                for dst in dsts:
                    if depth[dst] < depth[src] + 1:
                        depth[dst] = depth[src] + 1
                        changed = True
            if not changed:
                break

        for n in self.nodes:
            n.depth = depth.get(n.id, 0)
