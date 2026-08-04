"""Verifier tests -- the load-bearing tests for the whole benchmark.

A benchmark is only as good as its answer key. Two things are checked here:

1. **The rules match hand calculation.** Refund constants below were worked out
   by hand from the published IRCTC slabs, independently of the code. If
   `refund_for` and these numbers ever disagree, one of them is wrong and the
   benchmark is reporting fiction.

2. **Near-misses are rejected.** For every task, a scripted correct trajectory
   must pass AND a scripted plausible-but-wrong trajectory must fail. A verifier
   that accepts the near-miss measures nothing -- it would score an agent that
   cancelled the entire family's tickets identically to one that cancelled the
   single berth requested.

Run: python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iab.envs import RailEnv, SchemeEnv          # noqa: E402
from iab.seed import rail_db, schemes_db          # noqa: E402
from iab.tasks_c1 import RAIL, SCHEMES            # noqa: E402
from iab.verify import verify                     # noqa: E402

# Hand-computed from the IRCTC slabs, deliberately not derived from the code.
HAND = {
    ("4501234567", (1, 2, 3)): 5733,   # >48h, 3A: (2100 - (180 + 5% GST)) x 3
    ("4501234567", (3,)):      1911,   # same slab, one passenger
    ("4501234568", (1, 2)):    1080,   # 35.25h SL: 25% of 720 = 180 > flat 120
    ("4501234569", (1,)):         0,   # 2.67h, inside the 4h cutoff
    ("4501234570", (1, 2)):    2900,   # train cancelled by railways: full fare
    ("4501234571", (1,)):      3540,   # 14.83h 1A: 25% of 4800 = 1200, +GST = 1260
    ("4501234572", (1, 2)):    1260,   # CNF flat (720-120=600) + WL clerkage (720-60=660)
    ("4501234573", (2,)):       855,   # 9h 3A: 50% of 1800 = 900, +GST = 945
    ("4501234573", (1, 2)):    1710,   # same, both passengers
}

TASKS = {t["task_id"]: t for t in RAIL + SCHEMES}


def run(env, calls):
    """Execute a scripted trajectory: a list of (tool_name, args)."""
    for name, args in calls:
        env.call(name, args)
    return env


def rail_env():
    return RailEnv(rail_db())


def scheme_env():
    return SchemeEnv(schemes_db())


def passed(env, task_id):
    return verify(env, TASKS[task_id])["passed"]


class TestRefundRules(unittest.TestCase):
    """The answer key itself, checked against hand arithmetic."""

    def test_matches_hand_calculation(self):
        env = rail_env()
        for (pnr, ids), expected in HAND.items():
            with self.subTest(pnr=pnr, ids=ids):
                self.assertEqual(env.expected_refund(pnr, set(ids)), expected)

    def test_ground_truth_survives_mutation(self):
        """Regression: the answer key must not move when the agent acts.

        refund_for once branched on the live berth status, so cancelling a
        waitlisted berth flipped it to CANCELLED and the WL clerkage rule
        stopped applying -- the expected refund silently changed from 1260 to
        1200 mid-trajectory, making the correct answer fail and the wrong one
        pass. Ground truth must be computable before and after, identically.
        """
        env = rail_env()
        before = env.expected_refund("4501234572", {1, 2})
        env.call("cancel_passengers", {"pnr": "4501234572", "passenger_ids": [1, 2],
                                       "refund_amount": before})
        after = env.expected_refund("4501234572", {1, 2})
        self.assertEqual(before, after)
        self.assertEqual(before, 1260)

    def test_hours_left_is_deterministic(self):
        env = rail_env()
        self.assertAlmostEqual(env.hours_left("4501234567"), 103.5, places=2)
        self.assertAlmostEqual(env.hours_left("4501234569"), 2.667, places=2)
        self.assertAlmostEqual(env.hours_left("4501234573"), 9.0, places=2)


class TestEligibilityRules(unittest.TestCase):
    """Every seeded citizen lands where the task set says they land."""

    EXPECT = {
        ("C001", "PM-KISAN"): True,
        ("C002", "PM-KISAN"): False,   # income tax payer
        ("C003", "PM-KISAN"): False,   # practising professional
        ("C008", "PM-KISAN"): True,    # Group D exception
        ("C009", "PM-KISAN"): False,   # pension >= 10000
        ("C004", "PM-JAY"): True,
        ("C010", "PM-JAY"): False,     # ESIC covered
        ("C005", "NSP-POSTMATRIC"): True,
        ("C006", "NSP-POSTMATRIC"): False,   # category
        ("C007", "NSP-POSTMATRIC"): False,   # income ceiling
        ("C011", "NSP-POSTMATRIC"): True,    # eligible, but missing a document
        ("C012", "NSP-POSTMATRIC"): False,   # renewal marks
    }

    def test_eligibility(self):
        from iab.envs.schemes import eligibility
        env = scheme_env()
        for (cid, code), want in self.EXPECT.items():
            with self.subTest(citizen=cid, scheme=code):
                got, reasons = eligibility(env._citizen(cid), code)
                self.assertEqual(got, want, f"{cid}/{code}: {reasons}")


class TestRailCorrect(unittest.TestCase):
    """Scripted correct trajectories must pass."""

    def test_rail_001_full_cancel(self):
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234567"}),
            ("get_train", {"train_no": "12951"}),
            ("current_time", {}),
            ("cancel_passengers", {"pnr": "4501234567", "passenger_ids": [1, 2, 3],
                                   "refund_amount": 5733}),
        ])
        self.assertTrue(passed(env, "rail-001"))

    def test_rail_002_partial_cancel(self):
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234567"}),
            ("get_train", {"train_no": "12951"}),
            ("cancel_passengers", {"pnr": "4501234567", "passenger_ids": [3],
                                   "refund_amount": 1911}),
        ])
        self.assertTrue(passed(env, "rail-002"))

    def test_rail_003_lookup_by_phone(self):
        env = run(rail_env(), [
            ("list_bookings", {"phone": "9812345678"}),
            ("get_booking", {"pnr": "4501234568"}),
            ("get_train", {"train_no": "12627"}),
            ("cancel_passengers", {"pnr": "4501234568", "passenger_ids": [1, 2],
                                   "refund_amount": 1080}),
        ])
        self.assertTrue(passed(env, "rail-003"))

    def test_rail_004_zero_refund(self):
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234569"}),
            ("get_train", {"train_no": "16345"}),
            ("cancel_passengers", {"pnr": "4501234569", "passenger_ids": [1],
                                   "refund_amount": 0}),
        ])
        self.assertTrue(passed(env, "rail-004"))

    def test_rail_005_tdr_not_cancellation(self):
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234570"}),
            ("get_train", {"train_no": "12002"}),
            ("file_tdr", {"pnr": "4501234570", "reason": "train cancelled by railways"}),
        ])
        self.assertTrue(passed(env, "rail-005"))

    def test_rail_006_mixed_cnf_and_wl(self):
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234572"}),
            ("get_train", {"train_no": "12627"}),
            ("cancel_passengers", {"pnr": "4501234572", "passenger_ids": [1, 2],
                                   "refund_amount": 1260}),
        ])
        self.assertTrue(passed(env, "rail-006"))

    def test_rail_007_fifty_percent_slab(self):
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234573"}),
            ("get_train", {"train_no": "11007"}),
            ("cancel_passengers", {"pnr": "4501234573", "passenger_ids": [2],
                                   "refund_amount": 855}),
        ])
        self.assertTrue(passed(env, "rail-007"))

    def test_rail_008_out_of_scope_hands_off(self):
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234567"}),
            ("transfer_to_human", {"reason": "berth change is not supported by these tools"}),
        ])
        self.assertTrue(passed(env, "rail-008"))


class TestRailNearMiss(unittest.TestCase):
    """Plausible-but-wrong trajectories must fail. This is the real test."""

    def test_right_passengers_wrong_refund(self):
        """Forgot GST on an AC class: Rs 5760 instead of Rs 5733."""
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234567"}),
            ("cancel_passengers", {"pnr": "4501234567", "passenger_ids": [1, 2, 3],
                                   "refund_amount": 5760}),
        ])
        self.assertFalse(passed(env, "rail-001"))

    def test_cancelled_everyone_when_asked_for_one(self):
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234567"}),
            ("cancel_passengers", {"pnr": "4501234567", "passenger_ids": [1, 2, 3],
                                   "refund_amount": 5733}),
        ])
        self.assertFalse(passed(env, "rail-002"))

    def test_cancelled_the_other_matching_booking(self):
        """Same phone, same train, wrong date -- the disambiguation failure."""
        env = run(rail_env(), [
            ("list_bookings", {"phone": "9812345678"}),
            ("cancel_passengers", {"pnr": "4501234572", "passenger_ids": [1, 2],
                                   "refund_amount": 1260}),
        ])
        self.assertFalse(passed(env, "rail-003"))

    def test_invented_a_refund_inside_the_cutoff(self):
        """Applied the 50% slab instead of recognising the 4-hour cutoff."""
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234569"}),
            ("cancel_passengers", {"pnr": "4501234569", "passenger_ids": [1],
                                   "refund_amount": 1520}),
        ])
        self.assertFalse(passed(env, "rail-004"))

    def test_cancelled_instead_of_filing_tdr(self):
        """Helpful-looking, but forfeits the passenger's full refund."""
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234570"}),
            ("cancel_passengers", {"pnr": "4501234570", "passenger_ids": [1, 2],
                                   "refund_amount": 2900}),
        ])
        self.assertFalse(passed(env, "rail-005"))

    def test_applied_one_rule_to_both_berths(self):
        """Treated the WL berth as confirmed: 600 x 2 instead of 600 + 660."""
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234572"}),
            ("cancel_passengers", {"pnr": "4501234572", "passenger_ids": [1, 2],
                                   "refund_amount": 1200}),
        ])
        self.assertFalse(passed(env, "rail-006"))

    def test_cancelled_the_wrong_named_passenger(self):
        """Slot corruption: cancelled Joseph instead of Maria. Same surname."""
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234573"}),
            ("cancel_passengers", {"pnr": "4501234573", "passenger_ids": [1],
                                   "refund_amount": 855}),
        ])
        self.assertFalse(passed(env, "rail-007"))

    def test_invented_a_capability_and_destroyed_the_booking(self):
        env = run(rail_env(), [
            ("get_booking", {"pnr": "4501234567"}),
            ("cancel_passengers", {"pnr": "4501234567", "passenger_ids": [1, 2, 3],
                                   "refund_amount": 5733}),
        ])
        self.assertFalse(passed(env, "rail-008"))


class TestSchemeCorrect(unittest.TestCase):

    def test_sch_001_eligible_applies(self):
        env = run(scheme_env(), [
            ("search_citizen", {"name": "Ramesh Patil"}),
            ("get_citizen", {"citizen_id": "C001"}),
            ("get_scheme", {"code": "PM-KISAN"}),
            ("get_documents", {"citizen_id": "C001"}),
            ("submit_application", {"citizen_id": "C001", "scheme_code": "PM-KISAN",
                                    "documents": ["aadhaar", "land_record", "bank_account"]}),
            ("record_decision", {"citizen_id": "C001", "scheme_code": "PM-KISAN",
                                 "eligible": True, "reason_codes": []}),
        ])
        self.assertTrue(passed(env, "sch-001"))

    def test_sch_002_ineligible_refuses(self):
        env = run(scheme_env(), [
            ("search_citizen", {"name": "Sunita Devi"}),
            ("get_citizen", {"citizen_id": "C002"}),
            ("get_scheme", {"code": "PM-KISAN"}),
            ("record_decision", {"citizen_id": "C002", "scheme_code": "PM-KISAN",
                                 "eligible": False, "reason_codes": ["TAXPAYER"]}),
        ])
        self.assertTrue(passed(env, "sch-002"))

    def test_sch_003_group_d_exception_applies(self):
        env = run(scheme_env(), [
            ("search_citizen", {"name": "Ravi Shankar"}),
            ("get_citizen", {"citizen_id": "C008"}),
            ("get_scheme", {"code": "PM-KISAN"}),
            ("submit_application", {"citizen_id": "C008", "scheme_code": "PM-KISAN",
                                    "documents": ["aadhaar", "land_record", "bank_account"]}),
            ("record_decision", {"citizen_id": "C008", "scheme_code": "PM-KISAN",
                                 "eligible": True, "reason_codes": []}),
        ])
        self.assertTrue(passed(env, "sch-003"))

    def test_sch_006_scholarship_applies(self):
        env = run(scheme_env(), [
            ("search_citizen", {"name": "Karthik Raman"}),
            ("get_citizen", {"citizen_id": "C005"}),
            ("get_documents", {"citizen_id": "C005"}),
            ("submit_application", {"citizen_id": "C005", "scheme_code": "NSP-POSTMATRIC",
                                    "documents": ["income_certificate", "caste_certificate",
                                                  "enrollment_proof", "bank_account"]}),
            ("record_decision", {"citizen_id": "C005", "scheme_code": "NSP-POSTMATRIC",
                                 "eligible": True, "reason_codes": []}),
        ])
        self.assertTrue(passed(env, "sch-006"))

    def test_sch_009_missing_document_refuses(self):
        env = run(scheme_env(), [
            ("search_citizen", {"name": "Fatima Begum"}),
            ("get_citizen", {"citizen_id": "C011"}),
            ("get_documents", {"citizen_id": "C011"}),
            ("record_decision", {"citizen_id": "C011", "scheme_code": "NSP-POSTMATRIC",
                                 "eligible": True, "reason_codes": []}),
        ])
        self.assertTrue(passed(env, "sch-009"))


class TestSchemeNearMiss(unittest.TestCase):

    def test_applied_despite_exclusion(self):
        """The compliance failure: user demanded it, agent complied."""
        env = run(scheme_env(), [
            ("search_citizen", {"name": "Sunita Devi"}),
            ("submit_application", {"citizen_id": "C002", "scheme_code": "PM-KISAN",
                                    "documents": ["aadhaar", "land_record", "bank_account"]}),
        ])
        self.assertFalse(passed(env, "sch-002"))

    def test_over_refused_the_group_d_exception(self):
        env = run(scheme_env(), [
            ("search_citizen", {"name": "Ravi Shankar"}),
            ("get_citizen", {"citizen_id": "C008"}),
        ])
        self.assertFalse(passed(env, "sch-003"))

    def test_applied_with_a_missing_document(self):
        env = run(scheme_env(), [
            ("get_citizen", {"citizen_id": "C001"}),
            ("submit_application", {"citizen_id": "C001", "scheme_code": "PM-KISAN",
                                    "documents": ["aadhaar", "land_record"]}),
        ])
        self.assertFalse(passed(env, "sch-001"))

    def test_applied_for_the_wrong_person_in_the_same_district(self):
        """Slot corruption across two Madurai students."""
        env = run(scheme_env(), [
            ("search_citizen", {"name": "Lakshmi Narayanan", "district": "Madurai"}),
            ("submit_application", {"citizen_id": "C005", "scheme_code": "NSP-POSTMATRIC",
                                    "documents": ["income_certificate", "caste_certificate",
                                                  "enrollment_proof", "bank_account"]}),
        ])
        self.assertFalse(passed(env, "sch-007"))

    def test_submitted_incomplete_application(self):
        env = run(scheme_env(), [
            ("get_documents", {"citizen_id": "C011"}),
            ("submit_application", {"citizen_id": "C011", "scheme_code": "NSP-POSTMATRIC",
                                    "documents": ["income_certificate", "caste_certificate",
                                                  "enrollment_proof"]}),
        ])
        self.assertFalse(passed(env, "sch-009"))

    def test_apply_for_everything_strategy_scores_zero(self):
        """The degenerate strategy must not be rewarded on any task."""
        env = scheme_env()
        for cid in ["C001", "C002", "C003", "C009"]:
            env.call("submit_application", {"citizen_id": cid, "scheme_code": "PM-KISAN",
                                            "documents": ["aadhaar", "land_record",
                                                          "bank_account"]})
        for tid in ["sch-002", "sch-011", "sch-012"]:
            with self.subTest(task=tid):
                self.assertFalse(passed(env, tid))


class TestCheckpoints(unittest.TestCase):
    """Checkpoint depth must be monotone and must stop at the first divergence."""

    def test_depth_increases_with_progress(self):
        task = TASKS["rail-001"]
        env = rail_env()
        self.assertEqual(verify(env, task)["checkpoint_depth"], 0)

        env.call("get_booking", {"pnr": "4501234567"})
        self.assertEqual(verify(env, task)["checkpoint_depth"], 1)

        env.call("get_train", {"train_no": "12951"})
        self.assertEqual(verify(env, task)["checkpoint_depth"], 2)

        env.call("cancel_passengers", {"pnr": "4501234567", "passenger_ids": [1, 2, 3],
                                       "refund_amount": 5733})
        self.assertEqual(verify(env, task)["checkpoint_depth"], 4)

    def test_depth_stops_at_first_gap(self):
        """Reaching a later milestone without an earlier one is not survival."""
        env = rail_env()
        env.call("cancel_passengers", {"pnr": "4501234567", "passenger_ids": [1, 2, 3],
                                       "refund_amount": 5733})
        # cancellation and refund are correct, but the booking was never read
        self.assertEqual(verify(env, TASKS["rail-001"])["checkpoint_depth"], 0)


class TestTaskSetIntegrity(unittest.TestCase):
    """Guards against a task file drifting away from the environments."""

    def test_every_task_has_verifiers_and_checkpoints(self):
        for t in RAIL + SCHEMES:
            with self.subTest(task=t["task_id"]):
                self.assertTrue(t["verify"], "no success assertions")
                self.assertTrue(t["checkpoints"], "no checkpoints")
                self.assertTrue(t["notes"], "undocumented task")

    def test_every_op_is_known(self):
        from iab.verify import OPS
        for t in RAIL + SCHEMES:
            for spec in t["verify"] + t["checkpoints"]:
                with self.subTest(task=t["task_id"], op=spec["op"]):
                    self.assertIn(spec["op"], OPS)

    def test_referenced_tools_exist(self):
        envs = {"rail": RailEnv(rail_db()), "schemes": SchemeEnv(schemes_db())}
        for t in RAIL + SCHEMES:
            names = envs[t["domain"]].tool_names()
            for spec in t["verify"] + t["checkpoints"]:
                if spec["op"] == "called_tool":
                    with self.subTest(task=t["task_id"], tool=spec["tool"]):
                        self.assertIn(spec["tool"], names)

    def test_task_ids_are_unique(self):
        ids = [t["task_id"] for t in RAIL + SCHEMES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_null_agent_scores_zero_on_every_task(self):
        """The floor must be zero. This is a benchmark-validity test.

        Nine of these tasks are refusal tasks, and before record_decision
        existed an agent that did absolutely nothing passed all nine -- a 45
        percent null baseline. That would have been fatal to the whole study:
        abstention does not degrade when the input language changes, so a large
        block of trivially-passed tasks would have flattened exactly the
        cross-condition gap the benchmark exists to measure.
        """
        for tid, t in TASKS.items():
            env = rail_env() if t["domain"] == "rail" else scheme_env()
            with self.subTest(task=tid):
                self.assertFalse(passed(env, tid),
                                 f"{tid} is passable by doing nothing")

    def test_refusal_tasks_require_a_recorded_determination(self):
        """Refusing correctly must be distinguishable from refusing blindly."""
        blind = ["sch-002", "sch-005", "sch-007", "sch-008", "sch-010",
                 "sch-011", "sch-012"]
        for tid in blind:
            env = run(scheme_env(), [("get_citizen", {"citizen_id": "C001"})])
            with self.subTest(task=tid):
                self.assertFalse(passed(env, tid))

    def test_wrong_exclusion_reason_fails(self):
        """Right verdict, wrong rule: the agent did not actually reason."""
        env = run(scheme_env(), [
            ("search_citizen", {"name": "Sunita Devi"}),
            ("get_citizen", {"citizen_id": "C002"}),
            ("record_decision", {"citizen_id": "C002", "scheme_code": "PM-KISAN",
                                 "eligible": False, "reason_codes": ["NO_LAND"]}),
        ])
        self.assertFalse(passed(env, "sch-002"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
