"""End-to-end harness tests, run entirely offline.

The full loop -- model turn, tool dispatch, state mutation, survival logging,
verification -- is exercised against a scripted provider before any real quota
is spent. A harness bug found here costs nothing; the same bug found during the
live run costs a day of free-tier allowance and silently poisons the results.

Run: python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iab.providers import Mock                    # noqa: E402
from iab.runner import run_task                   # noqa: E402
from iab.tasks_c1 import RAIL, SCHEMES            # noqa: E402

TASKS = {t["task_id"]: t for t in RAIL + SCHEMES}


class MockRotator:
    """Stands in for Rotator, driving a scripted Mock provider."""

    def __init__(self, script, model_name="mock"):
        self.model_name = model_name
        self.p = Mock(script=script)

    def chat(self, system, messages, tools):
        return self.p.chat(system, messages, tools)


def call(_tool, /, **args):
    # positional-only: several tools take an argument literally called "name"
    return {"name": _tool, "args": args}


class TestRunnerLoop(unittest.TestCase):

    def test_correct_agent_passes_and_survival_rises(self):
        r = MockRotator([
            [call("get_booking", pnr="4501234567")],
            [call("get_train", train_no="12951")],
            [call("cancel_passengers", pnr="4501234567",
                  passenger_ids=[1, 2, 3], refund_amount=5733)],
            "Cancelled all three. You will receive Rs 5733.",
        ])
        res = run_task(TASKS["rail-001"], r)

        self.assertTrue(res["passed"])
        self.assertEqual(res["stop_reason"], "completed")
        self.assertEqual(res["survival"], [1, 2, 4])
        self.assertEqual(res["checkpoint_depth"], 4)

    def test_wrong_arithmetic_fails_but_still_reports_depth(self):
        """Partial credit must survive a final-step failure.

        This is the distinction the survival curves rest on: an agent that got
        all the way to the cancellation and then fumbled the GST is not the
        same as one that never found the booking, and a binary score cannot
        tell them apart.
        """
        r = MockRotator([
            [call("get_booking", pnr="4501234567")],
            [call("get_train", train_no="12951")],
            [call("cancel_passengers", pnr="4501234567",
                  passenger_ids=[1, 2, 3], refund_amount=5760)],
            "Done.",
        ])
        res = run_task(TASKS["rail-001"], r)

        self.assertFalse(res["passed"])
        self.assertEqual(res["checkpoint_depth"], 3)
        self.assertIn("5760", res["reasons"][0])

    def test_parallel_tool_calls_in_one_turn(self):
        r = MockRotator([
            [call("get_booking", pnr="4501234567"), call("get_train", train_no="12951")],
            [call("cancel_passengers", pnr="4501234567",
                  passenger_ids=[3], refund_amount=1911)],
            "Cancelled Aditya's ticket. Refund Rs 1911.",
        ])
        res = run_task(TASKS["rail-002"], r)
        self.assertTrue(res["passed"])
        self.assertEqual(len(res["survival"]), 3)

    def test_correct_refusal_passes(self):
        """Refusing well means naming the rule, not just declining."""
        r = MockRotator([
            [call("search_citizen", name="Sunita Devi")],
            [call("get_citizen", citizen_id="C002")],
            [call("record_decision", citizen_id="C002", scheme_code="PM-KISAN",
                  eligible=False, reason_codes=["TAXPAYER"])],
            "You are registered as an income tax payer, which excludes you from "
            "PM-KISAN, so I cannot submit an application.",
        ])
        res = run_task(TASKS["sch-002"], r)
        self.assertTrue(res["passed"])
        self.assertEqual(res["checkpoint_depth"], 4)

    def test_blind_refusal_fails(self):
        """Declining without identifying the exclusion is not a correct answer."""
        r = MockRotator(["I am sorry, I cannot apply for that scheme."])
        res = run_task(TASKS["sch-002"], r)
        self.assertFalse(res["passed"])

    def test_max_steps_is_enforced(self):
        r = MockRotator([[call("current_time")]] * 100)
        res = run_task(TASKS["rail-001"], r, max_steps=5)
        self.assertEqual(res["stop_reason"], "max_steps")
        self.assertFalse(res["passed"])

    def test_agent_that_does_nothing_fails(self):
        res = run_task(TASKS["rail-001"], MockRotator(["I cannot help with that."]))
        self.assertFalse(res["passed"])
        self.assertEqual(res["survival"], [])


class TestRunnerRobustness(unittest.TestCase):
    """Bad model output is data, not a crash."""

    def test_unknown_tool_name_is_survivable(self):
        r = MockRotator([
            [call("change_berth", pnr="4501234567", berth="lower")],
            [call("get_booking", pnr="4501234567")],
            [call("transfer_to_human", reason="berth change is not supported")],
            "There is no way to change your berth with the tools I have.",
        ])
        res = run_task(TASKS["rail-008"], r)
        self.assertTrue(res["passed"])
        self.assertIn("unknown tool", res["actions"][0]["result"]["error"])

    def test_missing_required_argument_is_survivable(self):
        r = MockRotator([
            [call("cancel_passengers", pnr="4501234567")],   # no ids, no amount
            [call("get_booking", pnr="4501234567")],
            "Sorry, I need more information.",
        ])
        res = run_task(TASKS["rail-001"], r)
        self.assertFalse(res["passed"])
        self.assertFalse(res["actions"][0]["ok"])

    def test_hallucinated_pnr_is_survivable(self):
        r = MockRotator([
            [call("get_booking", pnr="9999999999")],
            "I could not find that PNR.",
        ])
        res = run_task(TASKS["rail-001"], r)
        self.assertFalse(res["passed"])
        self.assertIn("not found", res["actions"][0]["result"]["error"])

    def test_slot_corruption_is_recorded_for_analysis(self):
        """H2 needs 'right tool, wrong entity' to be visible in the log.

        The action log keeps arguments exactly as the model emitted them, so a
        romanized-name mismatch shows up as a recoverable search failure rather
        than vanishing into a generic error.
        """
        r = MockRotator([
            [call("search_citizen", name="Rameshh Pateel")],
            "I could not find that citizen.",
        ])
        res = run_task(TASKS["sch-001"], r)
        self.assertFalse(res["passed"])
        act = res["actions"][0]
        self.assertEqual(act["tool"], "search_citizen")
        self.assertEqual(act["args"]["name"], "Rameshh Pateel")
        self.assertFalse(act["ok"])


class TestTrajectoryLogging(unittest.TestCase):

    def test_transcript_and_actions_are_complete(self):
        r = MockRotator([
            [call("get_booking", pnr="4501234569")],
            [call("get_train", train_no="16345")],
            [call("cancel_passengers", pnr="4501234569",
                  passenger_ids=[1], refund_amount=0)],
            "No refund is due as departure is within four hours.",
        ])
        res = run_task(TASKS["rail-004"], r)

        self.assertTrue(res["passed"])
        self.assertEqual(len(res["actions"]), 3)
        self.assertEqual([a["tool"] for a in res["actions"]],
                         ["get_booking", "get_train", "cancel_passengers"])
        # one assistant turn per model reply, one tool entry per call
        self.assertEqual(sum(1 for x in res["transcript"] if x["role"] == "tool"), 3)
        self.assertEqual(res["actions"][-1]["args"]["refund_amount"], 0)

    def test_result_is_json_serialisable(self):
        import json
        r = MockRotator([[call("get_booking", pnr="4501234567")], "ok"])
        res = run_task(TASKS["rail-001"], r)
        json.loads(json.dumps(res, ensure_ascii=False))   # must not raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
