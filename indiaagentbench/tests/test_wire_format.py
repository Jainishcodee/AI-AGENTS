"""Wire-format tests -- the regression guard for a bug that hid behind 53 green tests.

The runner keeps history in an internal format; each provider must translate it
to its vendor's wire format. Originally OpenAICompat forwarded the internal
format verbatim, so assistant tool calls had no `id`/`type`/`function` wrapper
and tool results had no `tool_call_id`. Every real provider would have rejected
the first tool result with a 400 -- meaning every task in the benchmark, since
all of them require tool use.

Nothing caught it because the Mock provider ignores history. So these tests
stub the HTTP layer and assert on the payload that would actually go over the
wire, including the cross-reference that every tool result answers a real call.

Run: python -m unittest discover -s tests -v
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iab.envs import RailEnv                                       # noqa: E402
from iab.providers import Gemini, OpenAICompat, to_gemini, to_openai, _declare  # noqa: E402
from iab.runner import run_task                                    # noqa: E402
from iab.seed import rail_db                                       # noqa: E402
from iab.tasks_c1 import RAIL                                      # noqa: E402

TASKS = {t["task_id"]: t for t in RAIL}

HISTORY = [
    {"role": "user", "content": "cancel PNR 4501234567"},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "name": "get_booking", "args": {"pnr": "4501234567"}},
        {"id": "c2", "name": "get_train", "args": {"train_no": "12951"}},
    ]},
    {"role": "tool", "tool_call_id": "c1", "name": "get_booking", "content": '{"pnr": "x"}'},
    {"role": "tool", "tool_call_id": "c2", "name": "get_train", "content": '{"departure": "16:30"}'},
]


def validate_openai(payload):
    """Assert a payload satisfies the parts of the OpenAI contract we rely on."""
    seen_ids = set()
    for m in payload["messages"]:
        if m["role"] == "assistant":
            for tc in m.get("tool_calls") or []:
                assert tc["type"] == "function", "tool_call missing type=function"
                assert isinstance(tc["id"], str) and tc["id"], "tool_call missing id"
                args = tc["function"]["arguments"]
                assert isinstance(args, str), f"arguments must be a JSON string, got {type(args)}"
                json.loads(args)
                seen_ids.add(tc["id"])
        elif m["role"] == "tool":
            assert "tool_call_id" in m, "tool message missing tool_call_id"
            assert m["tool_call_id"] in seen_ids, \
                f"tool result {m['tool_call_id']} answers no prior call"
    return True


class TestOpenAITranslation(unittest.TestCase):

    def test_shape_is_valid(self):
        p = OpenAICompat("m", api_key="k", base_url="http://x")
        payload = p.payload("policy", HISTORY, RailEnv(rail_db()).tools())
        self.assertTrue(validate_openai(payload))

    def test_arguments_are_json_strings_not_objects(self):
        out = to_openai(HISTORY)
        args = out[1]["tool_calls"][0]["function"]["arguments"]
        self.assertIsInstance(args, str)
        self.assertEqual(json.loads(args), {"pnr": "4501234567"})

    def test_every_tool_result_carries_its_call_id(self):
        out = to_openai(HISTORY)
        tools = [m for m in out if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in tools], ["c1", "c2"])

    def test_system_prompt_leads_the_payload(self):
        p = OpenAICompat("m", api_key="k", base_url="http://x")
        payload = p.payload("POLICY TEXT", HISTORY, [])
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "POLICY TEXT"})

    def test_unicode_arguments_survive(self):
        """Devanagari and Tamil will ride in tool arguments from C2 onward."""
        hist = [{"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "name": "search_citizen", "args": {"name": "रमेश पाटील"}}]}]
        args = to_openai(hist)[0]["tool_calls"][0]["function"]["arguments"]
        self.assertEqual(json.loads(args)["name"], "रमेश पाटील")


class TestGeminiTranslation(unittest.TestCase):

    def test_parallel_tool_results_group_into_one_content(self):
        out = to_gemini(HISTORY)
        # user turn, model turn, then ONE user turn holding both responses
        self.assertEqual([c["role"] for c in out], ["user", "model", "user"])
        self.assertEqual(len(out[2]["parts"]), 2)
        self.assertIn("functionResponse", out[2]["parts"][0])

    def test_model_turn_carries_function_calls(self):
        out = to_gemini(HISTORY)
        calls = [p["functionCall"]["name"] for p in out[1]["parts"] if "functionCall" in p]
        self.assertEqual(calls, ["get_booking", "get_train"])

    def test_thought_signature_round_trips(self):
        """Gemini thinking models reject a history that lost the signature.

        Live failure was HTTP 400 "Function call is missing a thought_signature
        in functionCall parts", which killed every trajectory at the second
        model turn.
        """
        hist = [{"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "name": "get_booking", "args": {"pnr": "1"},
             "thought_signature": "SIGNATURE_ABC"}]}]
        part = to_gemini(hist)[0]["parts"][0]
        self.assertEqual(part["thoughtSignature"], "SIGNATURE_ABC")

    def test_signature_is_captured_from_a_response(self):
        import json as _json
        from unittest import mock as _mock

        def fake_post(url, headers=None, json=None, timeout=None):
            resp = _mock.Mock(status_code=200)
            resp.json.return_value = {"candidates": [{"content": {"parts": [
                {"functionCall": {"name": "get_booking", "args": {"pnr": "1"}},
                 "thoughtSignature": "SIG123"}]}}]}
            return resp

        with mock.patch("iab.providers.requests.post", side_effect=fake_post):
            out = Gemini("gemini-3.5-flash", api_key="k").chat("s", [], [])
        self.assertEqual(out["tool_calls"][0]["thought_signature"], "SIG123")
        # and it must not leak into the OpenAI wire format as a bogus field
        wire = to_openai([{"role": "assistant", "content": "",
                           "tool_calls": out["tool_calls"]}])
        self.assertEqual(set(wire[0]["tool_calls"][0]), {"id", "type", "function"})
        _json.dumps(wire)

    def test_no_argument_tools_omit_parameters(self):
        """An empty properties map is rejected by Gemini."""
        tools = {t["name"]: t for t in RailEnv(rail_db()).tools()}
        self.assertNotIn("parameters", _declare(tools["current_time"]))
        self.assertIn("parameters", _declare(tools["get_booking"]))

    def test_payload_builds_without_error(self):
        p = Gemini("gemini-2.5-flash", api_key="k")
        payload = p.payload("policy", HISTORY, RailEnv(rail_db()).tools())
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], "policy")
        self.assertTrue(payload["tools"][0]["functionDeclarations"])


class TestLiveLoopPayloads(unittest.TestCase):
    """Drive a real multi-turn trajectory through a stubbed transport.

    This is the test that would have caught the original bug: it exercises the
    runner's own history, not a hand-written fixture, and validates every
    request the loop makes.
    """

    def test_every_request_in_a_trajectory_is_valid_openai(self):
        script = [
            {"tool_calls": [{"id": "a1", "function": {
                "name": "get_booking", "arguments": '{"pnr": "4501234567"}'}}]},
            {"tool_calls": [{"id": "a2", "function": {
                "name": "get_train", "arguments": '{"train_no": "12951"}'}}]},
            {"tool_calls": [{"id": "a3", "function": {
                "name": "cancel_passengers",
                "arguments": '{"pnr": "4501234567", "passenger_ids": [1,2,3], "refund_amount": 5733}'}}]},
            {"content": "Cancelled. Refund Rs 5733."},
        ]
        sent = []

        def fake_post(url, headers=None, json=None, timeout=None):
            sent.append(json)
            validate_openai(json)
            turn = script[len(sent) - 1]
            resp = mock.Mock(status_code=200)
            resp.json.return_value = {"choices": [{"message": turn}]}
            return resp

        class R:
            model_name = "stub"

            def __init__(self):
                self.p = OpenAICompat("stub", api_key="k", base_url="http://x")

            def chat(self, system, messages, tools):
                return self.p.chat(system, messages, tools)

        with mock.patch("iab.providers.requests.post", side_effect=fake_post):
            res = run_task(TASKS["rail-001"], R())

        self.assertTrue(res["passed"])
        self.assertEqual(len(sent), 4)
        # by the final request the history holds all three call/result pairs
        last = sent[-1]["messages"]
        self.assertEqual(sum(1 for m in last if m["role"] == "tool"), 3)

    def test_malformed_arguments_do_not_crash_the_loop(self):
        def fake_post(url, headers=None, json=None, timeout=None):
            resp = mock.Mock(status_code=200)
            resp.json.return_value = {"choices": [{"message": {"tool_calls": [
                {"id": "z", "function": {"name": "get_booking", "arguments": "{not json"}}]}}]}
            return resp

        class R:
            model_name = "stub"

            def __init__(self):
                self.p = OpenAICompat("stub", api_key="k", base_url="http://x")

            def chat(self, system, messages, tools):
                return self.p.chat(system, messages, tools)

        with mock.patch("iab.providers.requests.post", side_effect=fake_post):
            res = run_task(TASKS["rail-001"], R(), max_steps=2)

        self.assertFalse(res["passed"])
        self.assertFalse(res["actions"][0]["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
