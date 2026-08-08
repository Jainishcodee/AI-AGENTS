"""The web client's hand-maintained type mirror must not drift from the API.

`apps/web/lib/types.ts` restates the wire contract by hand — a deliberate choice, since
generating it would add a build step to a boundary that changes rarely. The cost of that
choice is exactly this failure: two new stream events were added to the Python schema and
the client's union was not updated, so a `switch` on them stopped compiling.

These tests make that failure loud and cheap instead of a surprise during a UI change.
Skipped when the web app is not checked out.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

from app.schemas.artifacts import ARTIFACT_MODELS
from app.schemas.events import EventType
from app.schemas.trace import EdgeKind, NodeKind

WEB_TYPES = Path(__file__).resolve().parents[3] / "apps" / "web" / "lib" / "types.ts"
RENDERERS = (
    Path(__file__).resolve().parents[3] / "apps" / "web" / "components" / "artifacts" / "index.tsx"
)

pytestmark = pytest.mark.skipif(not WEB_TYPES.is_file(), reason="web app not present")


def union_members(source: str, name: str) -> set[str]:
    """Pull the string literals out of `export type <name> = "a" | "b" …`."""
    match = re.search(rf"export type {name} =(.*?);", source, re.DOTALL)
    assert match, f"no `export type {name}` in types.ts"
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def test_every_stream_event_is_in_the_client_union():
    declared = set(get_args(EventType))
    mirrored = union_members(WEB_TYPES.read_text(encoding="utf-8"), "EventType")
    assert declared <= mirrored, (
        "these events exist in the API but not in apps/web/lib/types.ts: "
        f"{sorted(declared - mirrored)}"
    )


def test_the_client_does_not_invent_events():
    declared = set(get_args(EventType))
    mirrored = union_members(WEB_TYPES.read_text(encoding="utf-8"), "EventType")
    assert mirrored <= declared, (
        f"the client expects events the API never emits: {sorted(mirrored - declared)}"
    )


def test_trace_node_and_edge_kinds_match():
    source = WEB_TYPES.read_text(encoding="utf-8")
    assert set(get_args(NodeKind)) == union_members(source, "TraceNodeKind")
    assert set(get_args(EdgeKind)) == union_members(source, "TraceEdgeKind")


def test_every_artifact_kind_renders_or_falls_back_deliberately():
    """A kind with no renderer must still display — the fallback is the contract.

    Not a demand that all 37 have bespoke renderers: a Phase 5 module will produce kinds
    this build has never heard of, and the generic view is the designed answer. This
    asserts the *terminal* and structural kinds are handled, and that the fallback exists.
    """
    if not RENDERERS.is_file():
        pytest.skip("renderer registry not present")
    source = RENDERERS.read_text(encoding="utf-8")
    assert "function Generic(" in source, "the generic artifact fallback was removed"

    handled = set(re.findall(r"^  (\w+): \(", source, re.MULTILINE))
    # The forced artifacts are the product's argument; each earns a real renderer.
    load_bearing = {
        "EvidenceLedger",
        "ProbabilityTree",
        "OptionSet",
        "AsymmetryTable",
        "StakeholderGraph",
        "PersonProfileSet",
        "ConstraintAnalysis",
        "HarmLedger",
        "RegretMatrix",
        "InactionHarm",
    }
    missing = load_bearing - handled
    assert not missing, f"these forced artifacts have no dedicated renderer: {sorted(missing)}"
    assert handled <= set(ARTIFACT_MODELS), (
        f"the client renders kinds the API cannot produce: {sorted(handled - set(ARTIFACT_MODELS))}"
    )
