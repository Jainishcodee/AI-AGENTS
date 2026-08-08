"""Typed stream events.

`POST /council/deliberate` streams these as SSE; `/deliberate/sync` drains the same
generator. One code path, so streamed and non-streamed results cannot drift.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "run_started",
    "injection_applied",
    "stage_started",
    "intake_complete",
    "module_started",
    "artifact_complete",
    "artifact_invalid",
    "module_complete",
    "module_abstained",
    "critique_complete",
    "revision_complete",
    "trace_updated",
    "synthesis_complete",
    "card_created",
    "done",
    "error",
]


class Event(BaseModel):
    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)


def sse(event: Event) -> str:
    """Serialise one event as an SSE frame.

    Kept as a function rather than a method so the schema module stays free of
    transport concerns.
    """
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def ev(type_: EventType, **payload: Any) -> Event:
    return Event(type=type_, payload=payload)
