"""`app.cli checkin` and `app.cli calendar` (Phase 6, ADR-031).

The commands that exist because the loop never closes on its own. `resolve <id> --chose …
--outcome …` asks a person to remember a card id and two flags, from a terminal, months
later — and the measure of that friction is that the corpus holds zero resolved cards.

`checkin` is interactive, so `input` is stubbed. That is the only way to test it: the real
guard refuses to ask questions when stdin is not a terminal, precisely so a script cannot
hang on a prompt nobody can answer.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import pytest

from app.cli import _cmd_calendar, _cmd_checkin
from app.core.config import Settings
from app.council import Council
from app.memory.store import InMemoryStore
from app.schemas.cards import (
    DecisionCard,
    ExpectedOutcome,
    ModuleStance,
    Recommendation,
)
from app.schemas.common import Confidence

TODAY = date.today()


@pytest.fixture
async def council_with_store(tmp_path):
    settings = Settings(
        COUNCIL_MAX_CONCURRENCY=8,
        COUNCIL_MAX_RPM=0,
        COUNCIL_MAX_RETRIES=0,
        COUNCIL_STORE="memory",
        COUNCIL_STORE_DIR=str(tmp_path),
        COUNCIL_LOG_LEVEL="ERROR",
    )
    instance = Council(settings, store=InMemoryStore(), force_provider="mock")
    try:
        yield instance
    finally:
        await instance.aclose()


def make_card(card_id: str, *, days: int, question: str = "Should I take the offer?") -> DecisionCard:
    return DecisionCard(
        id=card_id,
        question=question,
        deliberation_id=f"d-{card_id}",
        preset="full",
        depth="quick",
        recommendation=Recommendation(action="a", first_action="b", why="c"),
        # Real stances, because a card with none cannot be graded — the grader has nothing
        # to score, and a test built on an ungradeable card would prove nothing.
        per_module=[
            ModuleStance(
                module=module,
                stance=f"{module} said to take it.",
                confidence=Confidence(
                    score=0.6, basis="the evidence", falsifier="the offer never arrives"
                ),
            )
            for module in ("analyst", "tactician", "strategist")
        ],
        expected_outcome=ExpectedOutcome(
            statement="The offer arrives in writing within 14 days.",
            check_on=TODAY + timedelta(days=days),
            measurable_by="a signed letter",
        ),
    )


def answers(*replies: str):
    """Stub `input`, one reply per prompt, then EOF — which the command treats as a skip."""
    queue = list(replies)

    def fake_input(_prompt: str = "") -> str:
        if not queue:
            raise EOFError
        return queue.pop(0)

    return fake_input


def as_tty(monkeypatch, *, tty: bool = True) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: tty)


# ─────────────────────────────────────────────────────────────── checkin ──


async def test_a_completed_checkin_resolves_and_grades_the_card(
    council_with_store, monkeypatch, capsys
):
    """The whole point: three answers in, a graded card out.

    Until a card is graded nothing in the system learns anything — no calibration, no
    priors, no replay. This is the single path that produces the corpus the product's
    defensibility rests on.
    """
    council = council_with_store
    await council.store.save_card(make_card("due1", days=-3))

    as_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", answers("Stayed and asked in writing", "It arrived in nine days", ""))

    code = await _cmd_checkin(council, argparse.Namespace())
    assert code == 0

    card = await council.store.get_card("due1")
    assert card is not None
    assert card.resolved, "the answers were not saved"
    assert card.resolution.chose == "Stayed and asked in writing"
    assert card.resolution.actual_outcome == "It arrived in nine days"
    assert card.graded, "a resolved card that is never graded teaches nothing"
    assert "1 of 1 closed" in capsys.readouterr().out


async def test_a_surprise_is_recorded_when_given(council_with_store, monkeypatch):
    """Its own field, not a note — it feeds a council-level prior about what the six miss."""
    council = council_with_store
    await council.store.save_card(make_card("due1", days=-1))

    as_tty(monkeypatch)
    monkeypatch.setattr(
        "builtins.input",
        answers("Stayed", "It worked out", "My manager quit the same week"),
    )
    await _cmd_checkin(council, argparse.Namespace())

    card = await council.store.get_card("due1")
    assert card.resolution.surprises == ["My manager quit the same week"]


async def test_a_blank_first_answer_skips_without_saving_anything(
    council_with_store, monkeypatch
):
    """A half-filled card is worse than an open one: it grades six modules on nothing."""
    council = council_with_store
    await council.store.save_card(make_card("due1", days=-1))

    as_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", answers(""))
    await _cmd_checkin(council, argparse.Namespace())

    card = await council.store.get_card("due1")
    assert not card.resolved, "a skipped card must stay open"


async def test_an_outcome_left_blank_does_not_resolve_the_card(
    council_with_store, monkeypatch
):
    """"What did you do" without "what happened" is not gradeable."""
    council = council_with_store
    await council.store.save_card(make_card("due1", days=-1))

    as_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", answers("Stayed", ""))
    await _cmd_checkin(council, argparse.Namespace())

    assert not (await council.store.get_card("due1")).resolved


async def test_only_due_cards_are_walked(council_with_store, monkeypatch, capsys):
    council = council_with_store
    await council.store.save_card(make_card("due1", days=-2))
    await council.store.save_card(make_card("later", days=30))

    as_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", answers("Stayed", "It worked out", ""))
    await _cmd_checkin(council, argparse.Namespace())

    assert (await council.store.get_card("due1")).resolved
    assert not (await council.store.get_card("later")).resolved
    assert "1 of 1 closed" in capsys.readouterr().out


async def test_nothing_due_says_when_the_next_one_is(council_with_store, capsys):
    """"Nothing due" alone reads as "this is broken" when you came because of a reminder."""
    council = council_with_store
    await council.store.save_card(make_card("later", days=12))

    assert await _cmd_checkin(council, argparse.Namespace()) == 0
    out = capsys.readouterr().out
    assert "Nothing is due" in out
    assert (TODAY + timedelta(days=12)).isoformat() in out


async def test_a_non_interactive_run_lists_instead_of_prompting(
    council_with_store, monkeypatch, capsys
):
    """A prompt in a pipe hangs forever, which is the worst possible failure for a cron."""
    council = council_with_store
    await council.store.save_card(make_card("due1", days=-1))

    as_tty(monkeypatch, tty=False)

    def explode(_prompt: str = "") -> str:
        raise AssertionError("a non-interactive run must never prompt")

    monkeypatch.setattr("builtins.input", explode)
    assert await _cmd_checkin(council, argparse.Namespace()) == 0

    out = capsys.readouterr().out
    assert "due1" in out and "1 decision(s) due" in out
    assert not (await council.store.get_card("due1")).resolved


# ────────────────────────────────────────────────────────────── calendar ──


async def test_calendar_writes_a_file_with_crlf_endings_intact(council_with_store, tmp_path):
    """`newline=""` matters: without it Python translates the RFC-mandated CRLF to CRCRLF
    on Windows, and some clients reject the file outright."""
    council = council_with_store
    await council.store.save_card(make_card("due1", days=20))

    target = tmp_path / "out.ics"
    assert await _cmd_calendar(council, argparse.Namespace(out=str(target))) == 0

    raw = target.read_bytes()
    assert b"\r\r\n" not in raw, "CRLF was translated on write"
    assert raw.count(b"\n") == raw.count(b"\r\n"), "a bare LF got through"
    assert b"BEGIN:VCALENDAR" in raw and b"END:VCALENDAR" in raw
    assert b"due1" in raw, "the card id is what makes the reminder actionable"


async def test_calendar_with_nothing_open_still_writes_a_valid_file(
    council_with_store, tmp_path, capsys
):
    council = council_with_store
    target = tmp_path / "out.ics"
    assert await _cmd_calendar(council, argparse.Namespace(out=str(target))) == 0

    assert b"BEGIN:VCALENDAR" in target.read_bytes()
    assert "No open check-ins" in capsys.readouterr().out


async def test_a_resolved_card_drops_off_the_calendar(council_with_store, tmp_path, monkeypatch):
    """The reminder must stop once the loop is closed, or it trains the user to ignore it."""
    council = council_with_store
    await council.store.save_card(make_card("due1", days=-1))

    as_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", answers("Stayed", "It worked out", ""))
    await _cmd_checkin(council, argparse.Namespace())

    target = tmp_path / "out.ics"
    await _cmd_calendar(council, argparse.Namespace(out=str(target)))
    assert b"BEGIN:VEVENT" not in target.read_bytes()
