"""The ten loader rules, and cross-program consistency."""

from __future__ import annotations

import copy

import pytest
import yaml

from app.core.errors import ProgramInvalid
from app.engine.invariants import has_coverage
from app.programs import loader
from app.schemas.artifacts import ARTIFACT_MODELS
from app.schemas.program import AgentProgram


def _raw(module: str = "strategist") -> dict:
    path = loader.PROGRAM_DIR / f"{module}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    voice = data.setdefault("voice", {})
    voice["forbidden"] = list(voice.get("forbidden") or []) + list(loader.SHARED_FORBIDDEN)
    return data


def _expect_invalid(mutate, rule: int) -> None:
    data = _raw()
    mutate(data)
    program = AgentProgram.model_validate(data)
    with pytest.raises(ProgramInvalid, match=f"rule {rule}"):
        loader._validate(program, "test.yaml")


def test_all_six_programs_load():
    programs = loader.programs()
    assert set(programs) == {
        "analyst",
        "tactician",
        "strategist",
        "psychologist",
        "optimizer",
        "ethicist",
    }


def test_baseline_program_is_valid():
    loader._validate(AgentProgram.model_validate(_raw()), "test.yaml")


def test_rule_1_terminal_must_be_last():
    def mutate(data):
        data["stages"].append(copy.deepcopy(data["stages"][0]))
        data["stages"][-1]["id"] = "extra"

    _expect_invalid(mutate, 1)


def test_rule_1_exactly_one_terminal():
    def mutate(data):
        data["stages"][0]["terminal"] = True

    _expect_invalid(mutate, 1)


def test_rule_2_only_terminal_produces_conclusion():
    def mutate(data):
        data["stages"][0]["produces"] = "Conclusion"

    _expect_invalid(mutate, 2)


def test_rule_2_terminal_must_produce_conclusion():
    def mutate(data):
        data["stages"][-1]["produces"] = "EvidenceLedger"

    _expect_invalid(mutate, 2)


def test_rule_3_no_forward_reads():
    def mutate(data):
        data["stages"][0]["reads"] = ["sequence"]

    _expect_invalid(mutate, 3)


def test_rule_4_unknown_artifact():
    def mutate(data):
        data["stages"][0]["produces"] = "NotAThing"

    _expect_invalid(mutate, 4)


def test_rule_5_groups_must_be_contiguous():
    def mutate(data):
        # survey … analyse … survey again
        data["stages"][2]["group"] = "analyse"
        data["stages"][3]["group"] = "survey"

    _expect_invalid(mutate, 5)


def test_rule_6_every_stage_forbids_something():
    def mutate(data):
        data["stages"][0]["must_not"] = []

    _expect_invalid(mutate, 6)


def test_rule_7_bias_cannot_detect_itself():
    def mutate(data):
        data["biases"][0]["detectable_by"] = ["strategist"]

    _expect_invalid(mutate, 7)


def test_rule_8_cannot_critique_self():
    def mutate(data):
        data["critics"] = ["strategist"]

    _expect_invalid(mutate, 8)


def test_rule_9_needs_two_success_metrics():
    def mutate(data):
        data["success_metrics"] = data["success_metrics"][:1]

    _expect_invalid(mutate, 9)


def test_rule_10_constitution_cannot_be_opted_out_of():
    def mutate(data):
        data["voice"]["forbidden"] = ["only my own rule"]

    _expect_invalid(mutate, 10)


def test_constitution_is_merged_on_load():
    for program in loader.programs().values():
        for line in loader.SHARED_FORBIDDEN:
            assert line in program.voice.forbidden, program.id


def test_every_produced_artifact_has_invariant_coverage():
    for program in loader.programs().values():
        for stage in program.stages:
            assert stage.produces in ARTIFACT_MODELS, (program.id, stage.id)
            assert has_coverage(stage.produces), (program.id, stage.produces)


def test_critique_matrix_is_derived_from_specs():
    """Routing is not configured separately; M critiques T iff M is in T.critics."""
    programs = loader.programs()
    matrix = loader.critique_matrix()
    for target, program in programs.items():
        for critic in program.critics:
            assert target in matrix[critic], f"{critic} should critique {target}"
    for critic, targets in matrix.items():
        for target in targets:
            assert critic in programs[target].critics
        assert critic not in targets


def test_every_module_has_at_least_two_critics():
    for program in loader.programs().values():
        assert len(program.critics) >= 2, program.id


def test_presets_only_name_known_modules():
    known = set(loader.programs())
    for preset in loader.presets().values():
        assert set(preset.participants) <= known
        assert preset.primary


def test_solo_preset_makes_everyone_else_a_critic():
    preset = loader.preset("solo:strategist")
    assert preset.primary == ("strategist",)
    assert set(preset.critic) == set(loader.programs()) - {"strategist"}
    assert preset.role_of("strategist") == "primary"
    assert preset.role_of("psychologist") == "critic"


def test_unknown_preset_raises():
    with pytest.raises(ProgramInvalid, match="unknown preset"):
        loader.preset("nope")
