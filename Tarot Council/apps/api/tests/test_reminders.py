"""Check-in reminders as an iCalendar feed (Phase 6, ADR-031).

These tests are mostly about the *format*, which is unusual for this suite and deliberate.
RFC 5545 fails quietly: a calendar handed a malformed file drops the event rather than
complaining, so a bug here looks exactly like "the reminder never came" — which is
indistinguishable from the problem the feature exists to solve.

So the file is parsed back rather than eyeballed: unfolded, unescaped, and compared to what
went in.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.reminders import build, fold, render, uid_for
from app.reminders.ics import MAX_LINE_OCTETS
from app.schemas.cards import (
    DecisionCard,
    ExpectedOutcome,
    Recommendation,
    Resolution,
)

TODAY = date(2026, 8, 20)
NOW = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)


def make_card(
    card_id: str = "abc123",
    *,
    question: str = "Should I take the smaller offer with equity?",
    check_on: date | None = None,
    statement: str = "The offer arrives in writing within 14 days.",
    measurable_by: str = "a signed letter",
    resolved: bool = False,
    outcome: bool = True,
) -> DecisionCard:
    card = DecisionCard(
        id=card_id,
        question=question,
        deliberation_id=f"d-{card_id}",
        preset="full",
        depth="quick",
        recommendation=Recommendation(action="a", first_action="b", why="c"),
        expected_outcome=(
            ExpectedOutcome(
                statement=statement,
                check_on=check_on or TODAY + timedelta(days=30),
                measurable_by=measurable_by,
            )
            if outcome
            else None
        ),
    )
    if resolved:
        card.resolution = Resolution(
            chose="stayed", actual_outcome="it worked", happened_at=TODAY
        )
    return card


def ics(*cards: DecisionCard, today: date = TODAY) -> str:
    return render(build(list(cards), today=today), now=NOW)


def unfold(document: str) -> list[str]:
    """Reverse RFC 5545 folding: a line beginning with a space continues the previous one."""
    lines: list[str] = []
    for raw in document.split("\r\n"):
        if raw.startswith(" ") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def field_value(document: str, name: str) -> str:
    """The first value for a property, unfolded and unescaped."""
    for line in unfold(document):
        key, _, value = line.partition(":")
        if key.split(";")[0] == name:
            return (
                value.replace("\\n", "\n")
                .replace("\\,", ",")
                .replace("\\;", ";")
                .replace("\\\\", "\\")
            )
    raise AssertionError(f"{name} not found in:\n{document}")


# ───────────────────────────────────────────────── what gets a reminder ──


def test_an_open_card_with_a_check_in_date_gets_one_reminder():
    calendar = build([make_card()], today=TODAY)
    assert [r.card_id for r in calendar.reminders] == ["abc123"]


def test_a_resolved_card_gets_no_reminder():
    """The loop is closed. An event that fires anyway teaches the user to ignore the
    calendar, which costs more than the reminder is worth."""
    assert build([make_card(resolved=True)], today=TODAY).empty


def test_a_card_with_no_expected_outcome_gets_no_reminder():
    assert build([make_card(outcome=False)], today=TODAY).empty


def test_an_overdue_card_is_labelled_as_overdue():
    past = ics(make_card(check_on=TODAY - timedelta(days=5)))
    assert field_value(past, "SUMMARY").startswith("Overdue check-in:")

    future = ics(make_card(check_on=TODAY + timedelta(days=5)))
    assert field_value(future, "SUMMARY").startswith("Check in:")


def test_reminders_are_ordered_by_date():
    calendar = build(
        [
            make_card("late", check_on=TODAY + timedelta(days=60)),
            make_card("soon", check_on=TODAY + timedelta(days=2)),
        ],
        today=TODAY,
    )
    assert [r.card_id for r in calendar.reminders] == ["soon", "late"]


# ─────────────────────────────────────────────────────── the format ──


def test_every_line_ends_with_crlf_and_nothing_else():
    """A bare LF is the single most common reason a feed imports as nothing."""
    document = ics(make_card())
    assert document.endswith("\r\n"), "the last line was left unterminated"
    assert document.replace("\r\n", "").count("\n") == 0, "a bare LF got through"


def test_no_line_exceeds_seventy_five_octets():
    long_question = "Should I " + "take the offer with equity and relocate " * 6 + "?"
    document = ics(make_card(question=long_question, statement=long_question))
    over = [
        line for line in document.split("\r\n") if len(line.encode("utf-8")) > MAX_LINE_OCTETS
    ]
    assert not over, f"{len(over)} line(s) over the limit: {over[:1]}"


def test_folding_round_trips_to_the_original_line():
    original = "DESCRIPTION:" + "the same sentence repeated at length. " * 8
    assert unfold(fold(original) + "\r\n") == [original]


def test_folding_never_splits_a_multi_byte_character():
    """Folding on character count instead of octets produces over-length lines; folding on
    octets naively can cut a UTF-8 sequence in half and make the file undecodable."""
    original = "SUMMARY:" + "café — naïve résumé — " * 8
    folded = fold(original)
    folded.encode("utf-8").decode("utf-8")  # would raise if a sequence were split
    assert unfold(folded + "\r\n") == [original]
    assert all(len(line.encode("utf-8")) <= MAX_LINE_OCTETS for line in folded.split("\r\n"))


def test_text_values_escape_the_characters_that_would_break_parsing():
    """Unescaped, a comma silently splits one value into two and the rest is dropped."""
    document = ics(
        make_card(
            question="Do I stay, leave; or wait?",
            statement="Path: C:\\offers\\2026, decided; and signed",
        )
    )
    raw = "\r\n".join(unfold(document))
    assert "\\," in raw and "\\;" in raw and "\\\\" in raw

    # And it survives the round trip.
    assert "Do I stay, leave; or wait?" in field_value(document, "SUMMARY")
    assert "C:\\offers\\2026, decided; and signed" in field_value(document, "DESCRIPTION")


def test_a_newline_inside_a_value_becomes_an_escaped_n():
    document = ics(make_card())
    description = next(
        line for line in unfold(document) if line.startswith("DESCRIPTION:")
    )
    assert "\\n" in description, "the multi-line description was not escaped"
    assert "\n" not in description, "a literal newline would end the property early"


def test_the_required_properties_are_all_present():
    document = ics(make_card())
    lines = unfold(document)
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-1] == "END:VCALENDAR"
    for required in ("VERSION:2.0", "BEGIN:VEVENT", "END:VEVENT", "BEGIN:VALARM"):
        assert required in lines, f"missing {required}"
    assert any(line.startswith("DTSTAMP:") for line in lines), "DTSTAMP is required"
    assert any(line.startswith("PRODID:") for line in lines), "PRODID is required"


def test_an_all_day_event_ends_on_the_following_day():
    """DTEND is exclusive. Same-day DTEND makes a zero-length event that some clients drop."""
    document = ics(make_card(check_on=date(2026, 11, 18)))
    assert "DTSTART;VALUE=DATE:20261118" in unfold(document)
    assert "DTEND;VALUE=DATE:20261119" in unfold(document)


# ───────────────────────────────────────────────────────── stability ──


def test_the_uid_is_stable_for_a_card():
    """Re-importing must update the event, not duplicate it — calendars match on UID."""
    assert uid_for("abc123") == uid_for("abc123")
    assert uid_for("abc123") != uid_for("abc124")
    assert "@" in uid_for("abc123"), "a UID needs a domain-ish suffix to be well formed"


def test_rendering_twice_produces_an_identical_document():
    """Otherwise every refresh looks like a change to anything diffing or syncing it."""
    cards = [make_card("a"), make_card("b")]
    assert ics(*cards) == ics(*cards)


def test_the_calendar_has_a_display_name():
    """Without one it appears in a phone's calendar list as a bare URL."""
    assert field_value(ics(make_card()), "X-WR-CALNAME") == "Decision check-ins"


# ──────────────────────────────────────────── the reminder is actionable ──


def test_the_description_carries_the_prediction_and_how_to_record_the_answer():
    """"Check in on your decision" prompts nothing.

    The dated falsifiable claim is what makes the check-in take thirty seconds, and the
    command is what stops it needing a memory of the CLI.
    """
    document = ics(make_card(statement="The offer arrives in writing within 14 days."))
    description = field_value(document, "DESCRIPTION")
    assert "The offer arrives in writing within 14 days." in description
    assert "a signed letter" in description
    assert "abc123" in description, "the card id is what makes the command runnable"
    assert "checkin" in description


def test_an_empty_calendar_is_still_a_valid_document():
    """A user with nothing due must get a parseable feed, not a truncated one — otherwise
    the subscription errors and never recovers when a card is finally created."""
    document = render(build([], today=TODAY), now=NOW)
    lines = unfold(document)
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-1] == "END:VCALENDAR"
    assert "BEGIN:VEVENT" not in lines
