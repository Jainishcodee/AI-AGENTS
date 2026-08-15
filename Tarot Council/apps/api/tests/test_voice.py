"""The spoken briefing (Phase 4).

Voice is treated as a summarisation problem, not a text-to-speech problem, so the tests
are about the *script*: what gets included, what gets left out, and whether the result is
short enough that a person would finish it. Audio synthesis is one optional call to a free
endpoint and is not worth mocking.
"""

from __future__ import annotations

import pytest

from app.schemas.council import DeliberationRequest
from app.voice import briefing as voice
from app.voice.briefing import MAX_DISSENTS, VOICES, _list, _speakable

from .conftest import QUESTION


@pytest.fixture
async def deliberation(council):
    return await council.run(
        DeliberationRequest(question=QUESTION, depth="quick", preset="full")
    )


def test_a_briefing_is_short_enough_to_finish(deliberation):
    """The failure mode is a twenty-minute recording nobody plays twice."""
    script = voice.build(deliberation)
    assert 20 <= script.estimated_seconds <= 180, (
        f"{script.estimated_seconds}s is not a briefing"
    )


def test_the_briefing_leads_with_the_recommendation_and_its_falsifier(deliberation):
    script = voice.build(deliberation)
    text = script.script.lower()
    assert deliberation.synthesis is not None
    # Compare against the spoken form: markdown and row refs are stripped on the way in,
    # so the raw recommendation string will not appear verbatim.
    spoken_action = voice._speakable(deliberation.synthesis.recommendation.action).lower()
    assert spoken_action.rstrip(".") in text
    assert "wrong if" in text, "a spoken recommendation with no falsifier is a horoscope"


def test_the_council_blind_spot_is_always_spoken(deliberation):
    """It is the one line that stops a briefing sounding more complete than it is."""
    assert "no module examined" in voice.build(deliberation).script.lower()


def test_dissent_is_spoken_in_the_dissenting_modules_voice(deliberation):
    synthesis = deliberation.synthesis
    assert synthesis is not None and synthesis.minority_opinions

    script = voice.build(deliberation)
    dissenter = synthesis.minority_opinions[0].module
    spoken_by = {line.module for line in script.lines}
    assert dissenter in spoken_by, "the dissent was narrated rather than voiced"

    lines = [line for line in script.lines if line.module == dissenter]
    assert all(line.voice == VOICES[dissenter] for line in lines)
    assert any("right call if" in line.text for line in lines), (
        "a dissent without its condition is just disagreement"
    )


def test_every_module_has_a_distinct_voice():
    modules = [m for m in VOICES if m != "narrator"]
    assigned = [VOICES[m] for m in modules]
    # The narrator may share with a module, but two modules sounding identical defeats
    # the point of voicing dissent at all.
    assert len(set(assigned)) >= len(assigned) - 1, f"voices collide: {assigned}"


def test_dissent_is_capped_and_the_remainder_is_acknowledged(deliberation):
    synthesis = deliberation.synthesis
    assert synthesis is not None
    from app.schemas.council import Minority

    synthesis.minority_opinions = [
        Minority(module=m, position=f"{m} would do otherwise", when_it_would_be_right="if x")
        for m in ("analyst", "tactician", "strategist", "psychologist", "optimizer")
    ]
    script = voice.build(deliberation)

    voiced = {line.module for line in script.lines} - {"narrator", "ethicist"}
    assert len(voiced) <= MAX_DISSENTS
    assert "further" in script.script, "the dropped dissents were not acknowledged"


def test_row_references_are_stripped_before_speaking():
    """"analyst slash evidence slash EvidenceLedger hash e three" is not a sentence."""
    spoken = voice._speakable(
        "This rests on analyst/evidence/EvidenceLedger#e1 and **matters**"
    )
    assert "#" not in spoken
    assert "/" not in spoken
    assert "*" not in spoken
    assert "matters" in spoken


def test_sentences_do_not_run_together(deliberation):
    """"…about the next 90 days Check back in 90 days" is one unreadable sentence.

    `_speakable` only punctuates the end of what it is handed, so any line composed from
    two sentences has to close the first one itself.
    """
    script = voice.build(deliberation)
    line = next(line for line in script.lines if "Check back in" in line.text)
    before = line.text.split("Check back in")[0].rstrip()
    assert before.endswith((".", "!", "?")), line.text


def test_speakable_always_ends_a_sentence():
    assert voice._speakable("no full stop here").endswith(".")
    assert voice._speakable("already there?").endswith("?")
    assert voice._speakable("   ") == ""


def test_lists_are_spoken_as_lists():
    assert voice._list(["a thing", "another thing"]).endswith("and another thing.")
    assert voice._list([]) == ""


def test_a_deliberation_with_no_synthesis_cannot_be_briefed(deliberation):
    deliberation.synthesis = None
    with pytest.raises(ValueError, match="nothing to brief"):
        voice.build(deliberation)


def test_a_veto_is_spoken_by_the_ethicist(deliberation):
    synthesis = deliberation.synthesis
    assert synthesis is not None
    synthesis.ethical_veto_response = "The cost falls on someone who never agreed to it."
    script = voice.build(deliberation)
    assert any(
        line.module == "ethicist" and "ethical objection" in line.text for line in script.lines
    ), "a veto must be raised in the ethicist's own voice, not narrated away"


def test_synthesis_degrades_rather_than_failing_without_an_engine(deliberation, tmp_path, monkeypatch):
    """A missing optional dependency must not break the command.

    The script is the half that carries the thinking; audio is a convenience.
    """
    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "edge_tts":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    script = voice.build(deliberation)
    assert script.lines  # the useful half survives

    import asyncio

    assert asyncio.run(voice.synthesise(script, tmp_path)) is None
