"""Check-in dates as an iCalendar feed (ADR-031).

Every Decision Card is written with a falsifiable prediction and a `check_on` date, and
until this existed **nothing ever read that date out loud**. The CLI nudge prints only if
you already ran a command; the nav badge shows only if you already opened the app. Both
assume you are already there, which is exactly the assumption that fails sixty days later —
and a learning loop nobody is reminded to close does not learn.

So the reminder rides on the calendar the user already has open on their phone. No daemon to
die silently, no mail to land in spam, no push infrastructure for one person.

RFC 5545 is unforgiving in a way that fails *quietly*: a calendar handed a malformed file
usually drops the event rather than complaining. The three rules that actually bite — CRLF
endings, folding at 75 octets, and escaping inside TEXT values — are implemented here and
tested against the format rather than trusted.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from ..schemas.cards import DecisionCard

PRODID = "-//Cognitive OS//Decision check-ins//EN"
CALENDAR_NAME = "Decision check-ins"

ALARM_TRIGGER = "-PT9H"
"""Fire the alarm 9 hours before the all-day event starts — 3pm the day before.

An all-day event begins at 00:00, so an alarm "at" the event is a notification in the middle
of the night that is gone by morning. The afternoon before is when a person can still act.
"""

MAX_LINE_OCTETS = 75


@dataclass(slots=True)
class Reminder:
    card_id: str
    question: str
    on: date
    prediction: str = ""
    measurable_by: str = ""
    overdue: bool = False


@dataclass(slots=True)
class Calendar:
    reminders: list[Reminder] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.reminders


def build(cards: list[DecisionCard], *, today: date | None = None) -> Calendar:
    """One reminder per unresolved card that has a check-in date.

    Resolved cards are excluded: the loop is closed, and an event that fires anyway trains
    the user to ignore the calendar — which costs more than the missing reminder.
    """
    today = today or date.today()
    out: list[Reminder] = []
    for card in cards:
        if card.resolved or card.expected_outcome is None:
            continue
        outcome = card.expected_outcome
        out.append(
            Reminder(
                card_id=card.id,
                question=card.question,
                on=outcome.check_on,
                prediction=outcome.statement,
                measurable_by=outcome.measurable_by,
                overdue=outcome.check_on < today,
            )
        )
    out.sort(key=lambda r: (r.on, r.card_id))
    return Calendar(reminders=out)


def render(calendar: Calendar, *, now: datetime | None = None) -> str:
    """Serialise to an .ics document.

    `now` is injectable because `DTSTAMP` is required and would otherwise make the output
    non-deterministic — untestable, and every regeneration would look like a change to
    anything diffing it.
    """
    stamp = _utc(now or datetime.now(timezone.utc))
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        # X- properties are non-standard but universally understood, and without a name the
        # feed shows up in a phone's calendar list as a bare URL.
        f"X-WR-CALNAME:{_escape(CALENDAR_NAME)}",
    ]
    for reminder in calendar.reminders:
        lines.extend(_event(reminder, stamp))
    lines.append("END:VCALENDAR")

    # A trailing CRLF is required; joining alone would leave the last line unterminated.
    return "\r\n".join(fold(line) for line in lines) + "\r\n"


def _event(reminder: Reminder, stamp: str) -> list[str]:
    summary = _summary(reminder)
    return [
        "BEGIN:VEVENT",
        f"UID:{uid_for(reminder.card_id)}",
        f"DTSTAMP:{stamp}",
        # All-day: DTEND is exclusive, so a one-day event ends on the following day.
        f"DTSTART;VALUE=DATE:{reminder.on:%Y%m%d}",
        f"DTEND;VALUE=DATE:{reminder.on + timedelta(days=1):%Y%m%d}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(_description(reminder))}",
        # Free, not busy: a check-in is a nudge, not an appointment, and marking it busy
        # would make a month of decisions look like a full calendar.
        "TRANSP:TRANSPARENT",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"TRIGGER:{ALARM_TRIGGER}",
        f"DESCRIPTION:{_escape(summary)}",
        "END:VALARM",
        "END:VEVENT",
    ]


def _summary(reminder: Reminder) -> str:
    prefix = "Overdue check-in" if reminder.overdue else "Check in"
    return f"{prefix}: {_clip(reminder.question, 70)}"


def _description(reminder: Reminder) -> str:
    """What the council predicted, before it knew — and how to record the answer.

    The prediction is the whole point of the reminder. "Check in on your decision" prompts
    nothing; the dated, falsifiable claim is what makes the check-in take thirty seconds and
    produce a gradeable row.
    """
    parts = [f"Decision: {reminder.question}", ""]
    if reminder.prediction:
        parts += ["What the council predicted, before it knew:", reminder.prediction, ""]
    if reminder.measurable_by:
        parts += [f"Measured by: {reminder.measurable_by}", ""]
    parts += [
        "Record what actually happened:",
        f"  python -m app.cli checkin      (walks every due card)",
        f"  python -m app.cli resolve {reminder.card_id} --chose ... --outcome ...",
        "",
        "Every module gets graded against what it said. Until this is recorded, nothing "
        "in the system learns anything.",
    ]
    return "\n".join(parts)


def uid_for(card_id: str) -> str:
    """Stable, unique, and derived from the card.

    Stability is the difference between a calendar that stays clean and one the user deletes
    after the third import: re-importing must *update* an event, and calendars match on UID
    alone. A random UID would duplicate every event on every refresh.
    """
    digest = hashlib.sha256(card_id.encode("utf-8")).hexdigest()[:16]
    return f"{digest}@cognitive-os"


def fold(line: str) -> str:
    """Fold to 75 octets per RFC 5545, continuing with a leading space.

    Counted in **octets, not characters**: a question with an em-dash or an accent is
    multi-byte in UTF-8, and folding on character count produces over-length lines that look
    legal and get silently truncated by some parsers. A multi-byte character is never split
    across a fold, which is why this walks characters while measuring bytes.
    """
    if len(line.encode("utf-8")) <= MAX_LINE_OCTETS:
        return line

    chunks: list[str] = []
    current = bytearray()
    limit = MAX_LINE_OCTETS
    for char in line:
        encoded = char.encode("utf-8")
        if len(current) + len(encoded) > limit:
            chunks.append(current.decode("utf-8"))
            current = bytearray()
            # Continuation lines carry a leading space, which counts against the limit.
            limit = MAX_LINE_OCTETS - 1
        current += encoded
    if current:
        chunks.append(current.decode("utf-8"))
    return "\r\n ".join(chunks)


_SPECIALS = re.compile(r"([;,])")


def _escape(text: str) -> str:
    """Escape a TEXT value. Backslash first, or the escapes themselves get escaped."""
    cleaned = (text or "").replace("\\", "\\\\")
    cleaned = _SPECIALS.sub(r"\\\1", cleaned)
    return cleaned.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def _clip(text: str, limit: int) -> str:
    collapsed = " ".join((text or "").split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1].rstrip() + "…"


def _utc(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
