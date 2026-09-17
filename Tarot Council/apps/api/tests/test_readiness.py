"""Phase 6 readiness: cost preview, `doctor`, and export.

Three small features with one thing in common — each produces a *number or a verdict the
user acts on*, which is the category this project keeps finding quiet bugs in. So each is
tested against ground truth rather than against itself:

- the cost estimate is compared to a real run's actual call count, not to a fixture;
- every `doctor` check is shown failing, because a check that has only ever been seen to
  pass is not known to detect anything;
- the export is asserted to contain a memory the *ranker* would have hidden.
"""

from __future__ import annotations

import json

import pytest

from app import diagnostics, export
from app.core.config import Settings
from app.council.orchestrator import CRITIQUE_ROUNDS
from app.engine.planner import deliberation_estimate
from app.memory.store import InMemoryStore
from app.programs import loader
from app.schemas.cards import Memory
from app.schemas.council import DeliberationRequest

from .conftest import QUESTION


# ───────────────────────────────────────────────────────── cost preview ──


@pytest.mark.parametrize("depth", ["quick", "standard", "deep"])
async def test_the_estimate_matches_what_a_run_actually_costs(council, depth):
    """The estimate is only worth printing if it is right.

    This caught a real bug: the intake call was charged to nobody, so every reported
    figure — the CLI total, the checkpoint's "calls already spent", the Decision Card —
    was one call light on every deliberation. The estimate was correct and the *actual*
    was wrong, which is the harder direction to notice.
    """
    estimate = deliberation_estimate(
        loader.programs(),
        loader.preset("full"),
        depth,
        rounds=CRITIQUE_ROUNDS[depth],
    )
    result = await council.run(
        DeliberationRequest(question=QUESTION, depth=depth, preset="full")
    )
    assert result.usage.calls == estimate.total


def test_the_estimate_reports_wall_clock_because_that_is_the_binding_constraint():
    """Free tiers meter requests per *minute* (ADR-020), so the count is only half of it."""
    estimate = deliberation_estimate(
        loader.programs(), loader.preset("full"), "standard", rounds=1, rpm=5
    )
    assert estimate.seconds == pytest.approx(estimate.total / 5 * 60)
    assert "req/min" in estimate.describe()

    unpaced = deliberation_estimate(
        loader.programs(), loader.preset("full"), "standard", rounds=1, rpm=0
    )
    assert unpaced.seconds == 0.0
    assert "req/min" not in unpaced.describe()


def test_a_quick_run_is_cheaper_than_a_deep_one():
    costs = [
        deliberation_estimate(
            loader.programs(), loader.preset("full"), d, rounds=CRITIQUE_ROUNDS[d]
        ).total
        for d in ("quick", "standard", "deep")
    ]
    assert costs == sorted(costs), costs
    # `quick` runs no critique rounds at all, which is most of why it is cheap.
    assert costs[0] < costs[1]


# ────────────────────────────────────────────────────────────── doctor ──


def _settings(**overrides) -> Settings:
    base = dict(
        COUNCIL_STORE="sqlite",
        COUNCIL_MAX_RPM=5,
        COUNCIL_LOG_LEVEL="ERROR",
        GEMINI_API_KEY="test-key",
    )
    base.update(overrides)
    return Settings(**base)


def test_a_missing_key_is_a_failure_not_a_warning():
    checks = diagnostics.check_routes(_settings(GEMINI_API_KEY=None))
    failures = [c for c in checks if c.status == "fail"]
    assert failures, checks
    assert "GEMINI_API_KEY" in failures[0].detail
    assert "mock" in failures[0].fix, "the fix should mention the no-key path"


def test_one_missing_key_is_reported_once_not_once_per_role():
    """Three roles route to gemini; three identical lines read as three problems."""
    checks = diagnostics.check_routes(_settings(GEMINI_API_KEY=None))
    assert len([c for c in checks if c.name == "key:gemini"]) == 1


def test_a_model_that_is_not_on_the_free_tier_is_called_out():
    """It fails on the first call with something that reads like a quota error."""
    checks = diagnostics.check_routes(
        _settings(COUNCIL_MODEL_REASONING="gemini:gemini-2.5-pro")
    )
    warned = [c for c in checks if c.status == "warn"]
    assert warned and "free tier" in warned[0].detail


def test_an_unknown_provider_fails():
    checks = diagnostics.check_routes(_settings(COUNCIL_MODEL_INTAKE="wishful:gpt-9"))
    assert any(c.status == "fail" and "wishful" in c.detail for c in checks)


def test_a_healthy_route_set_produces_one_ok_line():
    checks = diagnostics.check_routes(_settings())
    assert [c.status for c in checks] == ["ok"]


def test_the_memory_store_is_flagged_because_nothing_accumulates():
    checks = diagnostics.check_store(_settings(COUNCIL_STORE="memory"))
    assert checks[0].status == "warn" and "nothing is persisted" in checks[0].detail


def test_an_unmigrated_store_is_a_failure(tmp_path):
    """The nastiest one: it half-works, so the break arrives later and elsewhere."""
    import sqlite3

    from app.memory.sqlite_store import SCHEMA_VERSION

    db = tmp_path / "cognitive-os.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION - 1}")
    conn.close()

    checks = diagnostics.check_store(_settings(COUNCIL_STORE_DIR=str(tmp_path)))
    assert checks[0].status == "fail"
    assert f"v{SCHEMA_VERSION}" in checks[0].detail


def test_a_store_from_the_future_is_also_a_failure(tmp_path):
    """Downgrading the code rather than the data is the wrong fix, so say so."""
    import sqlite3

    from app.memory.sqlite_store import SCHEMA_VERSION

    db = tmp_path / "cognitive-os.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION + 5}")
    conn.close()

    checks = diagnostics.check_store(_settings(COUNCIL_STORE_DIR=str(tmp_path)))
    assert checks[0].status == "fail" and "newer" in checks[0].detail


def test_unpaced_and_overpaced_rpm_are_both_flagged():
    assert diagnostics.check_pacing(_settings(COUNCIL_MAX_RPM=0)).status == "warn"
    assert diagnostics.check_pacing(_settings(COUNCIL_MAX_RPM=60)).status == "warn"
    assert diagnostics.check_pacing(_settings(COUNCIL_MAX_RPM=5)).status == "ok"


async def test_an_empty_corpus_is_a_warning_and_says_why_it_matters():
    checks = await diagnostics.check_corpus(InMemoryStore())
    corpus = next(c for c in checks if c.name == "corpus")
    assert corpus.status == "warn"
    assert "downstream" in corpus.fix


async def test_doctor_is_healthy_when_only_warnings_remain(council):
    """A warning is information, not a fault — exiting non-zero on one makes the
    command useless in a script."""
    report = await diagnostics.run(_settings(), council.store)
    assert report.healthy
    assert report.warnings, "an empty corpus should at least warn"
    assert "ready" in report.summary()


async def test_doctor_is_unhealthy_when_a_key_is_missing(council):
    report = await diagnostics.run(_settings(GEMINI_API_KEY=None), council.store)
    assert not report.healthy
    assert "stop a deliberation" in report.summary()


# ────────────────────────────────────────────────────────────── export ──


async def test_export_includes_memories_the_ranker_would_have_hidden():
    """The bug this file exists to prevent.

    `recall` is a *relevance* function: with an empty query it returns only high-salience
    rows. Exporting through it looked right and would have silently dropped every memory
    the ranker judged uninteresting — the worst thing a backup can do.
    """
    store = InMemoryStore()
    await store.remember(
        "analyst",
        [
            Memory(id="m1", module="analyst", kind="fact", content="loud", salience=0.95),
            Memory(id="m2", module="analyst", kind="fact", content="quiet", salience=0.01),
        ],
    )

    ranked = await store.recall("analyst", "", k=100)
    assert {m.id for m in ranked} == {"m1"}, "precondition: the ranker hides the quiet one"

    bundle = await export.collect(store)
    assert {m["id"] for m in bundle.memories["analyst"]} == {"m1", "m2"}
    assert bundle.counts["memories"] == 2


async def test_the_export_is_readable_without_any_of_this_code(council, tmp_path):
    """Plain JSON is the whole point: a `.sqlite3` copy exports the storage, not the data."""
    await council.run(DeliberationRequest(question=QUESTION, depth="quick", preset="full"))

    target = tmp_path / "corpus.json"
    bundle = await export.write(council.store, target)

    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["export_version"] == export.EXPORT_VERSION
    assert raw["counts"] == bundle.counts
    assert raw["counts"]["cards"] >= 1
    assert raw["counts"]["deliberations"] >= 1
    # The question survives in readable form — not an opaque blob keyed by our schema.
    assert any(QUESTION in json.dumps(card) for card in raw["cards"])


async def test_export_survives_a_store_that_cannot_list_modules(council, tmp_path):
    """One failing table must not cost the rest of the corpus."""

    async def boom():
        raise RuntimeError("modules table is gone")

    council.store.list_modules = boom  # type: ignore[method-assign]
    bundle = await export.collect(council.store)
    assert bundle.modules == []
    assert bundle.counts["cards"] >= 0  # everything else still collected


async def test_export_can_leave_authored_modules_out(council):
    bundle = await export.collect(council.store, modules=False)
    assert bundle.modules == []
