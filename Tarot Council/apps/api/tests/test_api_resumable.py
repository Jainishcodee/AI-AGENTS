"""The HTTP surface for resumption.

The first HTTP-level tests in the suite, and the gap is why the bug they pin existed:
everything else exercises `Council` directly, so a route that returns the wrong *status*
while calling the right method looks fine from the inside.

The specific failure: `POST /council/resumable/{id}/resume` returns a `StreamingResponse`
whose generator body — including the "no such deliberation" lookup — does not execute until
the first iteration, which is after the 200 status line has already been sent. Resuming a
nonexistent deliberation therefore *succeeded* and handed back a broken stream.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import router
from app.core.config import Settings
from app.council import Council
from app.core.errors import ProviderError
from app.memory.store import InMemoryStore
from app.schemas.council import DeliberationRequest

from .conftest import QUESTION


class FailRole:
    """Blocks one role so a run stops part-way and leaves a checkpoint behind."""

    def __init__(self, inner, role: str) -> None:
        self._inner = inner
        self._role = role

    async def complete(self, role, request, *, override=None):
        if role == self._role:
            raise ProviderError("gemini", "HTTP 429: quota exhausted", retryable=False)
        return await self._inner.complete(role, request, override=override)

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.fixture
def app_client():
    """A real ASGI app, without `main.lifespan` — no disk store, no live provider."""
    settings = Settings(
        COUNCIL_MAX_CONCURRENCY=8,
        COUNCIL_MAX_RPM=0,
        COUNCIL_MAX_RETRIES=0,
        COUNCIL_STORE="memory",
        COUNCIL_LOG_LEVEL="ERROR",
    )
    council = Council(settings, store=InMemoryStore(), force_provider="mock")
    app = FastAPI()
    app.include_router(router)
    app.state.council = council
    with TestClient(app) as client:
        yield client, council


def test_resuming_an_unknown_deliberation_is_a_404(app_client):
    client, _ = app_client
    response = client.post("/council/resumable/does-not-exist/resume")
    assert response.status_code == 404, (
        f"got {response.status_code}; a StreamingResponse validated inside its own "
        "generator reports success before it knows whether it can succeed"
    )
    assert "no such" in response.json()["detail"]


def test_the_resumable_list_is_empty_when_nothing_was_interrupted(app_client):
    client, _ = app_client
    response = client.get("/council/resumable")
    assert response.status_code == 200
    assert response.json() == []


async def _interrupt(council, role: str = "synthesis") -> str:
    """Run until `role` is blocked, and return the checkpointed deliberation id."""
    inner = council._router
    blocked = FailRole(inner, role)
    council._router = blocked
    council._engine._router = blocked
    try:
        async for _ in council.deliberate(
            DeliberationRequest(question=QUESTION, depth="quick", preset="full")
        ):
            pass
    finally:
        council._router = inner
        council._engine._router = inner
    resumable = await council.resumable()
    assert resumable, "the interruption left nothing to resume"
    return resumable[0].deliberation_id


def test_an_interrupted_run_is_listed_then_resumed_then_gone(app_client):
    client, council = app_client
    # Sync test on purpose: `TestClient` drives its own event loop, and calling it from
    # inside a running one deadlocks. The async setup gets its own loop.
    deliberation_id = asyncio.run(_interrupt(council))

    listed = client.get("/council/resumable").json()
    assert [item["deliberation_id"] for item in listed] == [deliberation_id]
    entry = listed[0]
    assert entry["question"] == QUESTION
    assert entry["artifacts_done"] > 0, "nothing banked; there is no point resuming"
    assert entry["calls_spent"] > 0
    assert entry["failure"] and "quota" in entry["failure"]

    with client.stream(
        "POST", f"/council/resumable/{deliberation_id}/resume"
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())
    assert "event: done" in body or '"type": "done"' in body or '"type":"done"' in body

    # A finished deliberation has nothing left to resume, so it must drop off the list.
    assert client.get("/council/resumable").json() == []


def test_discarding_removes_it_from_the_resumable_list(app_client):
    client, council = app_client
    deliberation_id = asyncio.run(_interrupt(council))
    assert client.get("/council/resumable").json()

    response = client.delete(f"/council/resumable/{deliberation_id}")
    assert response.status_code == 200
    assert response.json() == {"discarded": deliberation_id}
    assert client.get("/council/resumable").json() == []
