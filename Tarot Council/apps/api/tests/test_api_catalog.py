"""The HTTP surface for authoring (Phase 5).

Written because the authoring routes shipped with a bug that only existed *at this layer*:
`PUT /catalog/{id}` built its `UserModule` by hand instead of going through the shared
authoring path, so the constitution was never merged and rule 10 fired on every request.
The route could not store a valid module at all, and every test passed — because every test
went through `Council` or `catalog` directly.

The lesson is the same one `test_api_resumable.py` encodes: a route that calls the right
method the wrong way is invisible from the inside.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import router
from app.core.config import Settings
from app.council import Council
from app.memory.store import InMemoryStore
from app.programs import loader

from .test_user_modules import make_program


@pytest.fixture
def client():
    settings = Settings(
        COUNCIL_MAX_CONCURRENCY=8,
        COUNCIL_MAX_RPM=0,
        COUNCIL_MAX_RETRIES=0,
        COUNCIL_STORE="memory",
        COUNCIL_LOG_LEVEL="ERROR",
    )
    app = FastAPI()
    app.include_router(router)
    app.state.council = Council(settings, store=InMemoryStore(), force_provider="mock")
    with TestClient(app) as test_client:
        yield test_client


def body(module_id: str = "historian", **overrides) -> dict:
    """A program as a client would send it — *without* the shared constitution.

    That omission is the point: no sane client restates four boilerplate lines, and the
    server merging them is what makes the route usable.
    """
    program = make_program(module_id, **overrides)
    raw = program.model_dump(mode="json")
    raw["voice"] = {"tone": "dry", "forbidden": ["Quoting a rate without its class of case."]}
    return raw


def test_a_client_does_not_have_to_restate_the_constitution(client):
    """The bug, at the layer it lived on."""
    response = client.put("/catalog/historian", json=body())
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["errors"] == [], saved["errors"]
    assert saved["status"] == "draft"
    # Merged server-side, and the author's own line survived.
    forbidden = saved["program"]["voice"]["forbidden"]
    assert set(loader.SHARED_FORBIDDEN).issubset(set(forbidden))
    assert "Quoting a rate without its class of case." in forbidden


def test_a_broken_module_is_saved_with_its_errors_not_rejected(client):
    """422 would leave the author nothing to iterate on (ADR-030)."""
    response = client.put("/catalog/historian", json=body(critics=["historian"]))
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["status"] == "quarantined"
    assert any("rule 8" in e for e in saved["errors"])

    # Stored and listed, so it can be found and fixed.
    listed = {e["id"]: e for e in client.get("/catalog").json()}
    assert listed["historian"]["status"] == "quarantined"
    assert listed["historian"]["runnable"] is False


def test_a_mismatched_id_is_a_400(client):
    assert client.put("/catalog/economist", json=body("historian")).status_code == 400


def test_the_catalog_lists_builtins_and_authored_together(client):
    client.put("/catalog/historian", json=body())
    entries = client.get("/catalog").json()
    by_id = {e["id"]: e for e in entries}
    assert by_id["analyst"]["origin"] == "builtin" and by_id["analyst"]["runnable"]
    assert by_id["historian"]["origin"] == "user"
    assert len(entries) == 7


def test_activation_is_refused_while_a_module_is_broken(client):
    client.put("/catalog/historian", json=body(critics=["historian"]))
    response = client.post("/catalog/historian/status", json={"status": "active"})
    assert response.status_code == 409
    assert "cannot be activated" in response.json()["detail"]


def test_a_module_can_be_authored_activated_and_used(client):
    client.put("/catalog/historian", json=body())
    activated = client.post("/catalog/historian/status", json={"status": "active"})
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"

    # And it actually runs, as a seventh member of the council.
    run = client.post(
        "/council/deliberate/sync",
        json={"question": "Should I take the smaller offer?", "preset": "with:historian",
              "depth": "quick"},
    )
    assert run.status_code == 200, run.text
    modules = [r["module"] for r in run.json()["runs"]]
    assert "historian" in modules
    assert len(modules) == 7


def test_activating_a_module_does_not_change_what_full_means(client):
    """Named presets are curated. Activation must not silently redefine them."""
    client.put("/catalog/historian", json=body())
    client.post("/catalog/historian/status", json={"status": "active"})

    run = client.post(
        "/council/deliberate/sync",
        json={"question": "Should I take the smaller offer?", "preset": "full",
              "depth": "quick"},
    )
    assert run.status_code == 200, run.text
    assert "historian" not in [r["module"] for r in run.json()["runs"]]


def test_an_unknown_module_is_a_404_on_read_and_status(client):
    assert client.get("/catalog/nobody").status_code == 404
    assert client.post("/catalog/nobody/status", json={"status": "active"}).status_code == 404


def test_deleting_a_module_removes_it_from_the_catalog(client):
    client.put("/catalog/historian", json=body())
    assert client.delete("/catalog/historian").json() == {"deleted": "historian"}
    assert [e["id"] for e in client.get("/catalog").json() if e["origin"] == "user"] == []


def test_export_review_and_fork_work_over_http(client):
    """The sharing loop at the HTTP layer, where a missing import only fails at request
    time — `PlainTextResponse` was referenced before it was imported, and the app imported
    cleanly anyway because annotations are lazy."""
    import yaml as yaml_lib

    exported = client.get("/catalog/analyst/export")
    assert exported.status_code == 200, exported.text
    assert "yaml" in exported.headers["content-type"]
    parsed = yaml_lib.safe_load(exported.text)
    assert parsed["id"] == "analyst"
    assert parsed["stages"], "the exported program lost its stages"

    review = client.get("/catalog/analyst/review")
    assert review.status_code == 200
    wheres = [item["where"] for item in review.json()]
    assert any("OTHER modules'" in where for where in wheres), (
        "the cross-module injection channel is not called out in the review"
    )

    forked = client.post("/catalog/analyst/fork", json={"new_id": "my_analyst"})
    assert forked.status_code == 200, forked.text
    body_json = forked.json()
    assert body_json["based_on"] == "analyst"
    assert body_json["status"] == "draft"

    # The fork is a real catalog citizen: exportable and reviewable in turn.
    assert client.get("/catalog/my_analyst/export").status_code == 200
    duplicate = client.post("/catalog/analyst/fork", json={"new_id": "my_analyst"})
    assert duplicate.status_code == 409


def test_export_and_review_of_an_unknown_module_are_404(client):
    assert client.get("/catalog/nobody/export").status_code == 404
    assert client.get("/catalog/nobody/review").status_code == 404


def test_editing_a_module_keeps_it_in_play(client):
    """Re-saving an active module must not quietly demote it to draft."""
    client.put("/catalog/historian", json=body())
    client.post("/catalog/historian/status", json={"status": "active"})

    edited = client.put("/catalog/historian", json=body(summary="A sharper summary."))
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "active", "an edit silently took the module out of play"
