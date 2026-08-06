"""Stage-1 independence is structural, and this proves it in the rendered prompts.

The engine is handed `(program, context, memory)` only — there is no parameter
through which a sibling's output could arrive. But a template could in principle
leak, so the guarantee is asserted against what the model actually receives.
"""

from __future__ import annotations

import pytest

from app.schemas.council import DeliberationRequest
from app.programs import loader

from .conftest import QUESTION, RecordingRouter


@pytest.fixture
async def recorded(council):
    recorder = RecordingRouter(council._router)
    council._router = recorder
    council._engine._router = recorder
    await council.run(
        DeliberationRequest(question=QUESTION, depth="standard", preset="full")
    )
    return recorder


def _stage_calls(recorder):
    """Only stage-1 reasoning calls: `<module>:<batch>`, excluding council stages."""
    out = []
    for tag, system, user in recorder.calls:
        if ":" not in tag or tag == "intake" or tag == "synthesis":
            continue
        module, _, batch = tag.partition(":")
        if batch in ("critique", "revise") or module not in loader.programs():
            continue
        out.append((module, batch, system, user))
    return out


async def test_stage_one_prompts_never_mention_another_module(recorded):
    calls = _stage_calls(recorded)
    assert calls, "no stage-1 calls were recorded"
    modules = set(loader.programs())
    for module, batch, system, user in calls:
        for other in modules - {module}:
            assert other not in user, f"{module}:{batch} prompt leaked '{other}'"
            assert other not in system, f"{module}:{batch} system prompt leaked '{other}'"


async def test_stage_one_prompts_never_contain_another_modules_skin_name(recorded):
    skins = {m: p.skin.name for m, p in loader.programs().items()}
    for module, batch, system, user in _stage_calls(recorded):
        for other, name in skins.items():
            if other == module:
                continue
            assert name not in user, f"{module}:{batch} leaked skin '{name}'"


async def test_a_module_never_sees_its_own_biases(recorded):
    """ADR-003: told about a weakness, a module performs its absence.

    Asserted against the bias *record* — its description, its detector, and the
    backticked id form the critique template uses. A bare id is not a useful signal:
    they are ordinary English words that legitimately appear in a module's own voice
    text ("never gleeful about cynicism").
    """
    for module, batch, system, user in _stage_calls(recorded):
        program = loader.program(module)
        for bias in program.biases:
            where = f"{module}:{batch}"
            for text in (system, user):
                assert f"`{bias.id}`" not in text, f"{where} was shown bias `{bias.id}`"
                assert bias.description not in text, f"{where} was shown {bias.id}'s description"
                assert bias.watch_for.strip()[:50] not in text, (
                    f"{where} was shown {bias.id}'s detector"
                )


async def test_critique_prompts_do_carry_the_targets_biases(recorded):
    """The mirror of the rule above: the critic is told, with the detector."""
    critique_calls = [
        (tag.split(":")[0], user)
        for tag, _system, user in recorded.calls
        if tag.endswith(":critique")
    ]
    assert critique_calls
    saw_a_detector = False
    for critic, user in critique_calls:
        for target, program in loader.programs().items():
            if target == critic or f"MODULE: {target}" not in user:
                continue
            for bias in program.biases:
                assert f"`{bias.id}`" in user, f"{critic} not told about {target}/{bias.id}"
                saw_a_detector = True
    assert saw_a_detector


async def test_every_stage_prompt_carries_the_constitution(recorded):
    for module, batch, system, _user in _stage_calls(recorded):
        assert "Never claim to be a person" in system, f"{module}:{batch}"
        assert "Never advise deception" in system


async def test_the_question_is_passed_verbatim(recorded):
    """The psychologist and ethicist must quote it; a paraphrase destroys the evidence."""
    quoting = [call for call in _stage_calls(recorded) if "<question>" in call[3]]
    assert quoting, "no stage prompt carried a <question> block"
    for module, batch, _system, user in quoting:
        assert QUESTION in user, f"{module}:{batch} did not receive the question verbatim"
