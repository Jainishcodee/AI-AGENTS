"""Tests for the analysis layer.

The survival curve is the paper's headline figure, so its definition needs to be
pinned down by tests rather than left to whatever the plotting code happened to
do. In particular: a curve must be monotonically non-increasing in k, and a
trajectory that fell off early must not be counted as surviving deeper.

Run: python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iab.analyze import failure_modes, summarise, survival   # noqa: E402


def run(cond, depth, total=4, passed=False, steps=4, reasons=(), clarified=False,
        task_id=None, trial=0):
    return {"model": "m", "domain": "rail", "condition": cond, "trial": trial,
            "task_id": task_id or f"t{depth}", "passed": passed, "reasons": list(reasons),
            "checkpoint_depth": depth, "checkpoints_total": total, "steps": steps,
            "stop_reason": "completed", "asked_clarification": clarified,
            "survival": list(range(1, depth + 1)), "actions": [], "transcript": []}


class TestSummary(unittest.TestCase):

    def test_rates_are_per_group(self):
        rows = [run("C1", 4, passed=True), run("C1", 2), run("C3", 1), run("C3", 0)]
        by = {t["condition"]: t for t in summarise(rows)}
        self.assertEqual(by["C1"]["n"], 2)
        self.assertAlmostEqual(by["C1"]["pass_rate"], 0.5)
        self.assertAlmostEqual(by["C3"]["pass_rate"], 0.0)

    def test_depth_is_normalised_by_checkpoint_count(self):
        """Domains have different checkpoint counts; raw depth is not comparable."""
        rows = [run("C1", 2, total=4), run("C1", 3, total=3)]
        t = summarise(rows)[0]
        self.assertAlmostEqual(t["mean_depth"], (0.5 + 1.0) / 2)

    def test_clarification_rate_is_tracked(self):
        rows = [run("C1", 1, clarified=True), run("C1", 1)]
        self.assertAlmostEqual(summarise(rows)[0]["clarified"], 0.5)


class TestTrialStability(unittest.TestCase):
    """Repeated trials are the only way to tell a real gap from noise.

    Two identical C1 runs of gpt-oss-120b disagreed on rail-004 and sch-009 --
    generation is not deterministic even at temperature 0. A single-trial
    C1-vs-C3 difference smaller than that wobble is not evidence of anything,
    so the summary has to surface the wobble rather than hide it behind a
    point estimate.
    """

    def test_flaky_task_is_counted_as_unstable(self):
        rows = [run("C1", 4, task_id="a", trial=0, passed=True),
                run("C1", 2, task_id="a", trial=1, passed=False),
                run("C1", 4, task_id="b", trial=0, passed=True),
                run("C1", 4, task_id="b", trial=1, passed=True)]
        t = summarise(rows)[0]
        self.assertEqual(t["trials"], 2)
        self.assertEqual(t["tasks"], 2)
        self.assertAlmostEqual(t["unstable"], 0.5)        # task a flipped
        self.assertAlmostEqual(t["pass_all_trials"], 0.5)  # only b passed twice
        self.assertAlmostEqual(t["pass_rate"], 0.75)       # 3 of 4 runs

    def test_stable_results_report_zero_instability(self):
        rows = [run("C1", 4, task_id="a", trial=i, passed=True) for i in range(3)]
        t = summarise(rows)[0]
        self.assertAlmostEqual(t["unstable"], 0.0)
        self.assertAlmostEqual(t["pass_all_trials"], 1.0)

    def test_pass_all_trials_is_stricter_than_mean(self):
        """A model that passes each task half the time has pass^k of zero."""
        rows = [run("C1", 4, task_id=f"t{i}", trial=0, passed=True) for i in range(4)]
        rows += [run("C1", 1, task_id=f"t{i}", trial=1, passed=False) for i in range(4)]
        t = summarise(rows)[0]
        self.assertAlmostEqual(t["pass_rate"], 0.5)
        self.assertAlmostEqual(t["pass_all_trials"], 0.0)


class TestSurvival(unittest.TestCase):

    def rates(self, rows, g=("m", "rail", "C1")):
        return [v for _, v, _ in survival(rows)[g]]

    def test_curve_is_monotonically_non_increasing(self):
        rows = [run("C1", d) for d in (0, 1, 2, 3, 4, 4)]
        curve = self.rates(rows)
        for a, b in zip(curve, curve[1:]):
            self.assertGreaterEqual(a, b)

    def test_counts_reaching_depth_at_least_k(self):
        rows = [run("C1", 0), run("C1", 2), run("C1", 4)]
        curve = self.rates(rows)
        self.assertAlmostEqual(curve[0], 2 / 3)   # k=1: depths 2 and 4
        self.assertAlmostEqual(curve[1], 2 / 3)   # k=2
        self.assertAlmostEqual(curve[2], 1 / 3)   # k=3: only depth 4
        self.assertAlmostEqual(curve[3], 1 / 3)   # k=4

    def test_shorter_tasks_are_excluded_not_counted_as_dead(self):
        """A 3-checkpoint task that finished must not depress P(depth >= 4).

        Unconditional survival reported 50% at k=4 for two runs that both
        completed perfectly, purely because one task only had three
        checkpoints. That is an artefact that would read as deep collapse.
        """
        rows = [run("C1", 4, total=4), run("C1", 3, total=3)]
        curve = survival(rows)[("m", "rail", "C1")]
        rates = {k: v for k, v, _ in curve}
        counts = {k: n for k, _, n in curve}
        self.assertAlmostEqual(rates[3], 1.0)
        self.assertAlmostEqual(rates[4], 1.0)     # not 0.5
        self.assertEqual(counts[4], 1)            # only one task was eligible

    def test_conditions_stay_separate(self):
        rows = [run("C1", 4), run("C3", 0)]
        c = survival(rows)
        self.assertEqual(c[("m", "rail", "C1")][0][1], 1.0)
        self.assertEqual(c[("m", "rail", "C3")][0][1], 0.0)

    def test_compounding_shows_as_widening_gap(self):
        """The shape H1 predicts: equal at k=1, fanning apart by k=4.

        Two conditions can share a shallow success rate and still diverge with
        depth. If the analysis only reported k=1 or the final pass rate, this
        pattern would be invisible -- which is the whole reason the curve exists.
        """
        rows = [run("C1", 4) for _ in range(4)] + [run("C1", 1)]
        rows += [run("C3", 1) for _ in range(4)] + [run("C3", 1)]
        c = survival(rows)
        c1 = [v for _, v, _ in c[("m", "rail", "C1")]]
        c3 = [v for _, v, _ in c[("m", "rail", "C3")]]
        self.assertAlmostEqual(c1[0], c3[0])          # identical shallow
        self.assertGreater(c1[3] - c3[3], 0.5)        # far apart deep


class TestFailureModes(unittest.TestCase):

    def test_arithmetic_and_entity_errors_are_separated(self):
        rows = [
            run("C3", 3, reasons=["refund recorded as Rs 5760, rules give Rs 5733"]),
            run("C3", 1, reasons=["cancelled [1, 2, 3], expected [3]"]),
        ]
        tags = failure_modes(rows)[("m", "rail", "C3")]
        self.assertEqual(tags["arithmetic"], 1)
        self.assertEqual(tags["wrong_entity"], 1)

    def test_passing_runs_contribute_nothing(self):
        self.assertEqual(dict(failure_modes([run("C1", 4, passed=True)])), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
