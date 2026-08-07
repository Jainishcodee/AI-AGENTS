"""MCP protocol surface.

Tested at the JSON-RPC layer rather than through a client SDK: the wire format *is*
the contract, and asserting against it catches the mistakes that actually break
clients (a missing `isError`, an answered notification, a tool schema that does not
match the handler).
"""

from __future__ import annotations

import json

import pytest

from app.mcp.server import PROTOCOL_VERSION, TOOLS, MCPServer

from .conftest import QUESTION


@pytest.fixture
def server(council):
    return MCPServer(council)


def request(method: str, params: dict | None = None, request_id: int | str = 1) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}


def payload_of(response: dict) -> dict:
    """Unwrap the JSON an MCP tool returns as text content."""
    content = response["result"]["content"]
    assert content[0]["type"] == "text"
    return json.loads(content[0]["text"])


async def test_initialize_reports_protocol_and_capabilities(server):
    response = await server.handle(request("initialize"))
    assert response is not None
    assert response["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert "tools" in response["result"]["capabilities"]
    assert response["result"]["serverInfo"]["name"] == "cognitive-os"


async def test_notifications_are_never_answered(server):
    """A JSON-RPC message with no id is a notification; replying to one is a protocol bug."""
    assert await server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


async def test_unknown_method_returns_method_not_found(server):
    response = await server.handle(request("nope"))
    assert response is not None
    assert response["error"]["code"] == -32601


async def test_tools_list_matches_the_handlers(server):
    response = await server.handle(request("tools/list"))
    assert response is not None
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert names == {
        "consult",
        "list_modules",
        "get_deliberation",
        "record_outcome",
        "track_record",
        "pending_checkins",
    }
    for tool in response["result"]["tools"]:
        assert tool["description"].strip()
        assert tool["inputSchema"]["type"] == "object"
        # Every required field must exist in properties, or clients cannot call it.
        for field in tool["inputSchema"].get("required", []):
            assert field in tool["inputSchema"]["properties"], (tool["name"], field)


def test_tool_descriptions_say_when_not_to_use_the_council():
    """An agent needs to know this is for tradeoffs, not lookups."""
    consult = next(t for t in TOOLS if t["name"] == "consult")
    assert "not for factual lookups" in consult["description"]


async def test_unknown_tool_is_a_tool_error_not_a_protocol_error(server):
    """The model should be able to read the message and recover, not see a transport fault."""
    response = await server.handle(request("tools/call", {"name": "nope", "arguments": {}}))
    assert response is not None
    assert "error" not in response
    assert response["result"]["isError"] is True


async def test_consult_rejects_a_non_question(server):
    response = await server.handle(
        request("tools/call", {"name": "consult", "arguments": {"question": "hi"}})
    )
    assert response is not None
    assert response["result"]["isError"] is True


async def test_consult_returns_the_answer_and_the_dissent(server):
    response = await server.handle(
        request(
            "tools/call",
            {
                "name": "consult",
                "arguments": {"question": QUESTION, "preset": "full", "depth": "quick"},
            },
        )
    )
    assert response is not None
    assert response["result"]["isError"] is False
    body = payload_of(response)

    assert body["recommendation"]["action"]
    assert body["wrong_if"], "a recommendation with no falsifier is not auditable"
    assert body["what_no_module_examined"], "the council blind spot must always be present"
    assert body["minority_opinions"] is not None
    assert set(body["per_module"]) == {
        "analyst",
        "tactician",
        "strategist",
        "psychologist",
        "optimizer",
        "ethicist",
    }
    for module, summary in body["per_module"].items():
        assert summary["wrong_if"], f"{module} returned no falsifier"
    assert body["deliberation_id"]
    assert body["card_id"], "consulting should leave a scoreable card behind"


async def test_consult_returns_a_summary_not_the_transcript(server):
    """An agent's context is finite; the transcript is available by id instead."""
    response = await server.handle(
        request(
            "tools/call",
            {"name": "consult", "arguments": {"question": QUESTION, "preset": "solo:analyst"}},
        )
    )
    assert response is not None
    summary = response["result"]["content"][0]["text"]
    body = payload_of(response)

    full = await server.handle(
        request(
            "tools/call",
            {"name": "get_deliberation", "arguments": {"deliberation_id": body["deliberation_id"]}},
        )
    )
    assert full is not None
    transcript = full["result"]["content"][0]["text"]
    assert len(summary) * 3 < len(transcript), (
        "the consult summary is not meaningfully smaller than the transcript"
    )
    assert "artifacts" not in body


async def test_get_deliberation_404s_cleanly(server):
    response = await server.handle(
        request("tools/call", {"name": "get_deliberation", "arguments": {"deliberation_id": "x"}})
    )
    assert response is not None
    assert response["result"]["isError"] is True


async def test_list_modules_exposes_forced_artifacts_and_failure_modes(server):
    response = await server.handle(request("tools/call", {"name": "list_modules"}))
    assert response is not None
    modules = payload_of(response)
    assert len(modules) == 6
    by_id = {m["id"]: m for m in modules}
    assert "ProbabilityTree" in by_id["analyst"]["produces"]
    assert "StakeholderGraph" in by_id["strategist"]["produces"]
    assert by_id["ethicist"]["holds_ethical_veto"] is True
    assert all(m["known_failure_modes"] for m in modules)


async def test_record_outcome_grades_every_module(server):
    consulted = await server.handle(
        request(
            "tools/call",
            {"name": "consult", "arguments": {"question": QUESTION, "preset": "full", "depth": "quick"}},
        )
    )
    assert consulted is not None
    card_id = payload_of(consulted)["card_id"]

    recorded = await server.handle(
        request(
            "tools/call",
            {
                "name": "record_outcome",
                "arguments": {
                    "card_id": card_id,
                    "chose": "did something else entirely",
                    "outcome": "it worked out",
                    "surprises": ["an unlisted actor mattered"],
                },
            },
        )
    )
    assert recorded is not None
    assert recorded["result"]["isError"] is False
    body = payload_of(recorded)
    assert len(body["verdicts"]) == 6
    for module, verdict in body["verdicts"].items():
        assert verdict["verdict"] in ("right", "wrong", "partial", "untested"), module
        assert "you_acted_on_it" in verdict
        assert "its_falsifier_fired" in verdict


async def test_record_outcome_on_a_missing_card_is_a_tool_error(server):
    response = await server.handle(
        request(
            "tools/call",
            {"name": "record_outcome", "arguments": {"card_id": "x", "chose": "a", "outcome": "b"}},
        )
    )
    assert response is not None
    assert response["result"]["isError"] is True


async def test_track_record_withholds_small_samples_and_says_so(server):
    await server.handle(
        request(
            "tools/call",
            {"name": "consult", "arguments": {"question": QUESTION, "preset": "solo:analyst"}},
        )
    )
    cards = await server._council.store.list_cards(limit=1)
    await server.handle(
        request(
            "tools/call",
            {
                "name": "record_outcome",
                "arguments": {"card_id": cards[0].id, "chose": "a", "outcome": "b"},
            },
        )
    )

    response = await server.handle(request("tools/call", {"name": "track_record"}))
    assert response is not None
    body = payload_of(response)
    assert body["scores"] == [], "n=1 must not be reported as a measurement"
    assert body["withheld_for_small_sample"] >= 1
    assert "not a measurement" in body["note"]


async def test_pending_checkins_is_empty_for_a_fresh_decision(server):
    await server.handle(
        request(
            "tools/call",
            {"name": "consult", "arguments": {"question": QUESTION, "preset": "solo:analyst"}},
        )
    )
    response = await server.handle(request("tools/call", {"name": "pending_checkins"}))
    assert response is not None
    assert payload_of(response) == []


async def test_a_failing_tool_does_not_kill_the_server(server, monkeypatch):
    async def explode(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(server, "_list_modules", explode)
    broken = await server.handle(request("tools/call", {"name": "list_modules"}))
    assert broken is not None
    assert broken["error"]["code"] == -32603

    # And the next call still works.
    ok = await server.handle(request("ping"))
    assert ok is not None
    assert ok["result"] == {}
