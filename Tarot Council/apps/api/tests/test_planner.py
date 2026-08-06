"""Program → plan. Depth changes the plan, never the program (ADR-013)."""

from __future__ import annotations

import pytest

from app.engine.planner import batch_model, call_estimate, plan
from app.programs import loader


@pytest.mark.parametrize("module", sorted(loader.programs()))
def test_every_stage_appears_exactly_once_at_every_depth(module):
    program = loader.program(module)
    expected = [s.id for s in program.stages]
    for depth in ("quick", "standard", "deep"):
        planned = [s.id for batch in plan(program, depth) for s in batch.stages]
        assert planned == expected, (module, depth)


@pytest.mark.parametrize("module", sorted(loader.programs()))
def test_deep_runs_one_call_per_stage(module):
    program = loader.program(module)
    assert call_estimate(program, "deep") == len(program.stages)


@pytest.mark.parametrize("module", sorted(loader.programs()))
def test_quick_is_never_more_calls_than_standard(module):
    program = loader.program(module)
    assert call_estimate(program, "quick") <= call_estimate(program, "standard")
    assert call_estimate(program, "standard") <= call_estimate(program, "deep")


@pytest.mark.parametrize("module", sorted(loader.programs()))
def test_terminal_stage_is_always_alone(module):
    program = loader.program(module)
    for depth in ("quick", "standard", "deep"):
        batches = plan(program, depth)
        terminal = [b for b in batches if b.terminal]
        assert len(terminal) == 1
        assert terminal[0].is_single, (module, depth)
        assert terminal[0] == batches[-1], (module, depth)


def test_isolated_stage_is_never_batched():
    """`tactician.generate` must not share a call with evaluation, at any depth.

    Divergence collapses the moment ranking is in the same context, which is the
    entire mechanism of that module.
    """
    program = loader.program("tactician")
    for depth in ("quick", "standard", "deep"):
        batches = [b for b in plan(program, depth) if "generate" in b.produced_ids]
        assert len(batches) == 1
        assert batches[0].is_single, depth


def test_standard_batches_by_declared_group():
    program = loader.program("analyst")
    batches = plan(program, "standard")
    ids = [b.id for b in batches]
    assert "frame+evidence+gaps" in ids
    assert "base_rates+tree" in ids
    assert ids[-1] == "recommend"


def test_batch_reads_exclude_what_the_batch_produces():
    program = loader.program("analyst")
    batch = next(b for b in plan(program, "standard") if b.id == "frame+evidence+gaps")
    # `evidence` reads `frame`, produced inside the batch, so it is not an
    # external dependency.
    assert "frame" not in batch.reads
    assert "context" in batch.reads


def test_batch_model_is_keyed_by_stage_id():
    program = loader.program("analyst")
    batch = next(b for b in plan(program, "standard") if not b.is_single)
    model = batch_model(batch)
    assert set(model.model_fields) == {s.id for s in batch.stages}


def test_single_batch_model_is_the_artifact_itself():
    program = loader.program("analyst")
    batch = next(b for b in plan(program, "deep") if b.stages[0].id == "tree")
    assert batch_model(batch).__name__ == "ProbabilityTree"
