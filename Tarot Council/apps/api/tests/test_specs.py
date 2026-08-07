"""The prose spec and the executable YAML must agree.

`docs/agents/<module>.md` is the design record; `programs/<module>.yaml` is what
runs. Drift between them is how a system ends up documented as one thing and
behaving as another — so every stage, artifact, bias and metric that exists in
code must be findable in the doc.

Checked in the code → doc direction only. The reverse would fail on prose that
legitimately discusses a concept without naming an identifier.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.programs import loader

DOC_DIR = Path(__file__).resolve().parents[3] / "docs" / "agents"
BACKTICKED = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")

MODULES = sorted(loader.programs())


def _doc(module: str) -> str:
    path = DOC_DIR / f"{module}.md"
    if not path.is_file():
        pytest.fail(f"no prose specification at {path}")
    return path.read_text(encoding="utf-8")


def _identifiers(text: str) -> set[str]:
    return set(BACKTICKED.findall(text))


@pytest.mark.parametrize("module", MODULES)
def test_every_stage_is_documented(module):
    doc = _doc(module)
    named = _identifiers(doc)
    for stage in loader.program(module).stages:
        assert stage.id in named, f"{module}.md does not mention stage `{stage.id}`"


@pytest.mark.parametrize("module", MODULES)
def test_every_produced_artifact_is_documented(module):
    doc = _doc(module)
    for stage in loader.program(module).stages:
        assert stage.produces in doc, (
            f"{module}.md does not mention artifact {stage.produces} "
            f"(produced by stage {stage.id})"
        )


@pytest.mark.parametrize("module", MODULES)
def test_every_bias_is_documented_with_its_detectors(module):
    doc = _doc(module)
    named = _identifiers(doc)
    for bias in loader.program(module).biases:
        assert bias.id in named, f"{module}.md does not mention bias `{bias.id}`"
        for detector in bias.detectable_by:
            assert detector in doc, (
                f"{module}.md does not name {detector} as a detector of {bias.id}"
            )


@pytest.mark.parametrize("module", MODULES)
def test_every_critic_is_documented(module):
    doc = _doc(module)
    for critic in loader.program(module).critics:
        assert critic in doc, f"{module}.md does not name critic {critic}"


@pytest.mark.parametrize("module", MODULES)
def test_every_success_metric_is_documented(module):
    doc = _doc(module)
    named = _identifiers(doc)
    for metric in loader.program(module).success_metrics:
        assert metric.id in named, f"{module}.md does not mention metric `{metric.id}`"


@pytest.mark.parametrize("module", MODULES)
def test_the_doc_declares_the_right_skin(module):
    program = loader.program(module)
    assert program.skin.name in _doc(module)


@pytest.mark.parametrize("module", MODULES)
def test_the_doc_answers_all_seven_questions(module):
    """SPEC-FORMAT.md §"The seven questions" — a missing section is a spec gap."""
    doc = _doc(module).lower()
    for heading in (
        "## 1. inputs",
        "## 2. mental model",
        "## 3. reasoning stages",
        "## 4. artifacts",
        "## 5. biases",
        "## 6. critics",
        "## 7. success metrics",
    ):
        assert heading in doc, f"{module}.md is missing section '{heading}'"


def test_veto_is_declared_by_exactly_one_module():
    """Its authority depends on being rare; two vetoes would be one too many."""
    holders = [m for m, p in loader.programs().items() if p.veto_enabled]
    assert holders == ["ethicist"]
