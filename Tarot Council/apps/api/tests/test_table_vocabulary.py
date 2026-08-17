"""The declarative artifact vocabulary (Phase 5, ADR-030).

This is the half that makes "author a module with no code" mean something. Rule 4 demands
that every artifact have a machine-checkable invariant, and an author cannot write Python —
so an authored module declares a `TableSpec` and the engine enforces it.

The vocabulary was **extracted, not invented**: every rule below is a shape the hand-written
validators already assert for the built-in six. So the tests come in pairs — one showing the
rule accepts a good table, one showing it *rejects* a bad one. A declarative rule that never
fails is decoration, and decoration is exactly what ADR-012 exists to prevent.

There is also a test that the vocabulary can restate a real built-in invariant
(`OptionSet`'s ≥7-options-with-five-required-tags), which is the evidence that "expressive
enough" is a measurement rather than a hope.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import ProgramInvalid
from app.engine.invariants import InvariantContext, check
from app.schemas.artifacts import Artifact, Table, TableRow
from app.schemas.program import Coverage, NumericRange, Stage, SumRule, TableSpec

from .test_user_modules import make_module, make_program


def spec(**overrides) -> TableSpec:
    base = dict(columns=("precedent", "mechanism", "rate"), min_rows=2, required=("precedent",))
    base.update(overrides)
    return TableSpec(**base)


_DEFAULT_SPEC = object()
"""Sentinel, because `None` is a meaningful value here: `stage(table=None)` has to mean
"a Table stage that declared no spec", which is the case the loader must reject."""


def stage(table: TableSpec | None | object = _DEFAULT_SPEC, **overrides) -> Stage:
    base = dict(
        id="precedents",
        name="Find precedents",
        group="gather",
        reads=("context",),
        produces="Table",
        instruction="List comparable prior cases.",
        must_not=("Recommending anything.",),
        table=spec() if table is _DEFAULT_SPEC else table,
    )
    base.update(overrides)
    return Stage(**base)


def table(*rows: dict) -> Table:
    return Table(rows=tuple(TableRow(**row) for row in rows))


def problems(t: Table, s: Stage, *, prior: dict[str, Artifact] | None = None, context=None):
    ctx = InvariantContext(
        context=context,
        stage=s,
        module="historian",
        prior=prior or {},
    )
    return check("Table", t, ctx)


@pytest.fixture(autouse=True)
def _ctx(context):
    """Every test needs a DecisionContext; the universal invariants read it."""
    global _CONTEXT
    _CONTEXT = context


def check_table(t: Table, s: Stage, *, prior: dict[str, Artifact] | None = None) -> list[str]:
    return problems(t, s, prior=prior, context=_CONTEXT)


# ─────────────────────────────────────────────────────────────── min_rows ──


def test_min_rows_accepts_enough_and_rejects_too_few():
    good = table(
        {"id": "t1", "cells": {"precedent": "a", "mechanism": "m", "rate": 1}},
        {"id": "t2", "cells": {"precedent": "b", "mechanism": "m", "rate": 1}},
    )
    assert check_table(good, stage()) == []

    thin = table({"id": "t1", "cells": {"precedent": "a"}})
    assert any("at least 2" in p for p in check_table(thin, stage()))


# ──────────────────────────────────────────────────────── required columns ──


def test_a_required_column_must_be_non_empty_in_every_row():
    """The psychologist's nine dimensions, generalised: no partial rows."""
    bad = table(
        {"id": "t1", "cells": {"precedent": "a"}},
        {"id": "t2", "cells": {"precedent": "   "}},
    )
    found = check_table(bad, stage())
    assert any("t2" in p and "precedent" in p for p in found), found
    assert not any("t1" in p and "empty required" in p for p in found)


def test_an_undeclared_column_is_rejected():
    """Otherwise the model invents columns and the declared shape means nothing."""
    bad = table({"id": "t1", "cells": {"precedent": "a", "vibes": "good"}},
                {"id": "t2", "cells": {"precedent": "b"}})
    assert any("vibes" in p for p in check_table(bad, stage()))


# ──────────────────────────────────────────────────────────────── distinct ──


def test_distinct_rejects_two_rows_sharing_a_value():
    s = stage(spec(distinct=("precedent",)))
    same = table(
        {"id": "t1", "cells": {"precedent": "Same Case"}},
        {"id": "t2", "cells": {"precedent": "same case"}},
    )
    assert any("share a 'precedent'" in p for p in check_table(same, s))

    different = table(
        {"id": "t1", "cells": {"precedent": "one"}},
        {"id": "t2", "cells": {"precedent": "two"}},
    )
    assert check_table(different, s) == []


def test_duplicate_row_ids_are_rejected_because_rows_must_be_citable():
    dupes = table(
        {"id": "t1", "cells": {"precedent": "a"}},
        {"id": "t1", "cells": {"precedent": "b"}},
    )
    assert any("share an id" in p for p in check_table(dupes, stage()))


# ─────────────────────────────────────────────────────────── required_tags ──


def test_required_tags_must_each_be_carried_by_at_least_one_row():
    """`REQUIRED_OPTION_TAGS` and ADR-014's forced `reckless` option, generalised."""
    s = stage(spec(required_tags=("supports", "contradicts")))
    one_sided = table(
        {"id": "t1", "cells": {"precedent": "a"}, "tags": ["supports"]},
        {"id": "t2", "cells": {"precedent": "b"}, "tags": ["supports"]},
    )
    found = check_table(one_sided, s)
    assert any("contradicts" in p for p in found), found

    balanced = table(
        {"id": "t1", "cells": {"precedent": "a"}, "tags": ["supports"]},
        {"id": "t2", "cells": {"precedent": "b"}, "tags": ["contradicts"]},
    )
    assert check_table(balanced, s) == []


# ────────────────────────────────────────────────────────────────── ranges ──


def test_a_range_rejects_out_of_bounds_and_non_numeric_values():
    """The leaf-probability floor, generalised."""
    s = stage(spec(ranges=(NumericRange(column="rate", minimum=0.0, maximum=1.0),)))

    too_high = table(
        {"id": "t1", "cells": {"precedent": "a", "rate": 1.4}},
        {"id": "t2", "cells": {"precedent": "b", "rate": 0.5}},
    )
    assert any("above the maximum" in p for p in check_table(too_high, s))

    words = table(
        {"id": "t1", "cells": {"precedent": "a", "rate": "quite often"}},
        {"id": "t2", "cells": {"precedent": "b", "rate": 0.5}},
    )
    assert any("non-numeric" in p for p in check_table(words, s))

    fine = table(
        {"id": "t1", "cells": {"precedent": "a", "rate": 0.2}},
        {"id": "t2", "cells": {"precedent": "b", "rate": 0.9}},
    )
    assert check_table(fine, s) == []


# ───────────────────────────────────────────────────────────────── sums_to ──


def test_sums_to_enforces_a_total_within_tolerance():
    s = stage(spec(sums_to=SumRule(column="rate", total=1.0, tolerance=0.02)))
    off = table(
        {"id": "t1", "cells": {"precedent": "a", "rate": 0.5}},
        {"id": "t2", "cells": {"precedent": "b", "rate": 0.9}},
    )
    assert any("must sum to 1.0" in p for p in check_table(off, s))

    exact = table(
        {"id": "t1", "cells": {"precedent": "a", "rate": 0.4}},
        {"id": "t2", "cells": {"precedent": "b", "rate": 0.6}},
    )
    assert check_table(exact, s) == []


# ────────────────────────────────────────────────────────────────── covers ──


def prior_artifact(*values: str) -> Artifact:
    return Artifact(
        kind="Table",
        module="historian",
        stage_id="cast",
        data={"rows": [{"id": f"p{i}", "cells": {"person": v}} for i, v in enumerate(values)]},
    )


def test_covers_requires_a_row_for_every_value_in_an_earlier_stage():
    """The psychologist's hardest invariant, and the rule that makes a multi-stage
    authored module more than a sequence of unrelated prompts."""
    s = stage(
        spec(
            columns=("person", "read"),
            required=("read",),
            min_rows=1,
            covers=Coverage(stage="cast", column="person"),
        )
    )
    prior = {"cast": prior_artifact("my manager", "the recruiter")}

    incomplete = table({"id": "t1", "cells": {"person": "my manager", "read": "wants me to stay"}})
    found = check_table(incomplete, s, prior=prior)
    assert any("the recruiter" in p for p in found), found

    complete = table(
        {"id": "t1", "cells": {"person": "my manager", "read": "wants me to stay"}},
        {"id": "t2", "cells": {"person": "the recruiter", "read": "wants the placement"}},
    )
    assert check_table(complete, s, prior=prior) == []


def test_covers_also_rejects_rows_for_people_who_were_never_named():
    s = stage(
        spec(
            columns=("person", "read"),
            required=("read",),
            min_rows=1,
            covers=Coverage(stage="cast", column="person"),
        )
    )
    prior = {"cast": prior_artifact("my manager")}
    invented = table(
        {"id": "t1", "cells": {"person": "my manager", "read": "x"}},
        {"id": "t2", "cells": {"person": "a person nobody mentioned", "read": "y"}},
    )
    assert any("not in stage 'cast'" in p for p in check_table(invented, s, prior=prior))


def test_covers_is_skipped_when_the_earlier_stage_abstained():
    """There is nothing to cover, and inventing a complaint would be wrong."""
    s = stage(
        spec(
            columns=("person", "read"),
            required=("read",),
            min_rows=1,
            covers=Coverage(stage="cast", column="person"),
        )
    )
    fine = table({"id": "t1", "cells": {"person": "anyone", "read": "x"}})
    assert check_table(fine, s, prior={}) == []


# ──────────────────────────────────────── a table with no spec is refused ──


def test_a_table_stage_with_no_spec_is_refused_rather_than_waved_through():
    """The persona-with-a-prompt hole, closed at the validator as well as the loader."""
    naked = stage(table=None)
    found = check_table(table({"id": "t1", "cells": {}}), naked)
    assert any("declares no table spec" in p for p in found), found


# ───────────────────────────────────────────── the loader catches bad specs ──


def table_program(**spec_overrides):
    stages = (
        stage(spec(**spec_overrides)) if spec_overrides else stage(),
        Stage(
            id="commit",
            name="Commit",
            group="commit",
            reads=("precedents",),
            produces="Conclusion",
            instruction="State what the table implies.",
            must_not=("Citing a row that is not above.",),
            terminal=True,
        ),
    )
    return make_program("historian", stages=stages)


def test_a_table_producing_stage_without_a_spec_fails_the_loader():
    from app.programs import catalog

    stages = (stage(table=None), table_program().stages[1])
    checked = catalog.validate(make_module("historian", stages=stages))
    assert any("declares no `table:` spec" in e for e in checked.errors), checked.errors


def test_a_spec_referencing_an_undeclared_column_fails_the_loader():
    """A rule that can never fire is worse than no rule: it reads as a guarantee."""
    from app.programs import catalog

    checked = catalog.validate(
        make_module("historian", stages=table_program(required=("nonexistent",)).stages)
    )
    assert any("not in `columns`" in e for e in checked.errors), checked.errors


def test_a_spec_with_columns_but_no_constraint_fails_the_loader():
    from app.programs import catalog

    checked = catalog.validate(
        make_module(
            "historian",
            stages=table_program(min_rows=1, required=(), distinct=()).stages,
        )
    )
    assert any("no constraint" in e for e in checked.errors), checked.errors


def test_covers_pointing_forward_fails_the_loader():
    from app.programs import catalog

    checked = catalog.validate(
        make_module(
            "historian",
            stages=table_program(
                columns=("precedent", "mechanism"),
                required=("precedent",),
                covers=Coverage(stage="commit", column="precedent"),
            ).stages,
        )
    )
    assert any("not an earlier stage" in e for e in checked.errors), checked.errors


def test_a_spec_on_a_non_table_stage_fails_the_loader():
    """It would be silently ignored, which is the worst outcome."""
    from app.programs import catalog

    stages = list(make_program().stages)
    stages[0] = stages[0].model_copy(update={"table": spec()})
    checked = catalog.validate(make_module("historian", stages=tuple(stages)))
    assert any("silently ignored" in e for e in checked.errors), checked.errors


# ───────────────────────────────── the shipped example, end to end ──


async def test_the_example_module_runs_and_its_declared_rules_actually_hold(council, context):
    """`scripts/example-module.yaml` is the module Phase 5's exit criterion is measured with.

    Running it proves the whole chain: YAML → constitution merge → ten rules → the engine →
    two authored `Table` artifacts → a `Conclusion`. Nothing in `engine/` knows any of this
    is authored rather than built in.

    The coverage assertion at the end is the one that matters. The mock provider can only
    produce a `divergence` table whose `precedent` values match the earlier stage's by
    *reading that stage's validated artifact out of its prompt* — so this failing would mean
    the cross-stage rule had quietly stopped being enforced.
    """
    import yaml

    from app.programs import catalog
    from app.schemas.program import AgentProgram

    raw = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "scripts" / "example-module.yaml").read_text(
            encoding="utf-8"
        )
    )
    module = catalog.author("historian", AgentProgram.model_validate(raw))
    assert module.errors == [], module.errors

    run = await council._engine.run_program(
        module.program, context=context, depth="quick", role="primary"
    )
    assert not run.abstained, run.abstain_reason
    assert [(a.stage_id, a.kind) for a in run.artifacts] == [
        ("precedents", "Table"),
        ("divergence", "Table"),
        ("commit", "Conclusion"),
    ]

    tables = {a.stage_id: a.data["rows"] for a in run.artifacts if a.kind == "Table"}
    assert len(tables["precedents"]) >= 3, "min_rows was not enforced"

    tagged = {tag for row in tables["precedents"] for tag in row.get("tags", [])}
    assert {"ended_well", "ended_badly"} <= tagged, "required_tags was not enforced"

    for row in tables["precedents"]:
        assert 0.0 <= float(row["cells"]["outcome_rate"]) <= 1.0

    covered = {row["cells"]["precedent"] for row in tables["precedents"]}
    differentiated = {row["cells"]["precedent"] for row in tables["divergence"]}
    assert covered == differentiated, (
        "the `covers` rule did not carry across the stage boundary; every precedent must "
        "reappear in the divergence table"
    )


# ──────────────────────────────── rules that must not silently no-op ──


def test_covers_pointing_at_a_non_table_stage_fails_the_loader():
    """The quietest failure in the vocabulary, and the one hardest to notice.

    `_check_coverage` reads the covered artifact's `rows`, which only a `Table` has. Point
    `covers` at a stage producing a built-in kind — `PersonList` keeps its people under
    `people` — and the expected set comes back empty, so the check passes whatever the table
    says. A coverage rule that silently approves everything is worse than none: it reads as
    the strongest guarantee in the spec.
    """
    from app.programs import catalog

    stages = (
        Stage(
            id="cast",
            name="Name the cast",
            group="gather",
            reads=("context",),
            produces="PersonList",
            instruction="Name everyone involved.",
            must_not=("Recommending anything.",),
        ),
        stage(
            spec(
                columns=("person", "read"),
                required=("read",),
                min_rows=1,
                covers=Coverage(stage="cast", column="person"),
            ),
            id="profiles",
            group="profile",
            reads=("cast",),
        ),
        Stage(
            id="commit",
            name="Commit",
            group="commit",
            reads=("profiles",),
            produces="Conclusion",
            instruction="State it.",
            must_not=("Citing a row not above.",),
            terminal=True,
        ),
    )
    checked = catalog.validate(make_module("historian", stages=stages))
    assert any("produces 'PersonList'" in e for e in checked.errors), checked.errors


def test_the_mock_can_satisfy_distinct_and_covers_on_the_same_column():
    """A mock that cannot satisfy a legal spec makes the *module* look broken.

    Declaring `distinct` on the column you also `covers` is the natural way to write "one
    row per precedent, no double-counting". The fixup's distinct filler ran after the covered
    value and overwrote it, so coverage failed and the blame landed on the author.
    """
    from app.engine.mockfix import fix_table

    prompt = (
        '<prior stage="cast" kind="Table">\n'
        '{"rows": [{"id": "p1", "cells": {"person": "my manager"}},'
        ' {"id": "p2", "cells": {"person": "the recruiter"}}]}\n'
        "</prior>\n"
        "1. Profiles — produce `Table` under the key `profiles`\n"
        "   - columns: person, read\n"
        "   - these must be non-empty in EVERY row: read\n"
        "   - these must differ between rows: person\n"
        "   - one row for every `person` in stage `cast`, carried in `person`. No omissions.\n"
    )
    filled = fix_table({}, prompt)
    people = [row["cells"]["person"] for row in filled["rows"]]
    assert people == ["my manager", "the recruiter"], people
    assert all(row["cells"]["read"] for row in filled["rows"])


def test_sums_to_names_the_non_numeric_cell_rather_than_blaming_the_total():
    """`_number` returned None and `or 0.0` swallowed it.

    A model writing "about half" produced `'share' sums to 0.500` — which sends the repair
    pass to fix the arithmetic instead of the cell that is not a number.
    """
    s = stage(spec(columns=("item", "share"), required=("item",), min_rows=1,
                   sums_to=SumRule(column="share", total=1.0)))
    garbage = table(
        {"id": "r1", "cells": {"item": "a", "share": "about half"}},
        {"id": "r2", "cells": {"item": "b", "share": 0.5}},
    )
    found = check_table(garbage, s)
    assert any("r1" in p and "non-numeric" in p for p in found), found


# ───────────────────────── the vocabulary can restate a built-in invariant ──


def test_the_vocabulary_can_express_the_option_sets_real_invariant():
    """The claim that makes ADR-030 credible, as a test.

    `OptionSet` is the built-in with the most demanding hand-written rules: at least seven
    options, five required tags each carried by some option, and no two labels alike. If the
    declarative vocabulary can restate that and enforce it identically, it is expressive
    enough to hold an authored module to a real standard.
    """
    from app.engine.invariants import MIN_GENERATED_OPTIONS, REQUIRED_OPTION_TAGS

    restated = TableSpec(
        columns=("label", "description"),
        min_rows=MIN_GENERATED_OPTIONS,
        required=("label",),
        distinct=("label",),
        required_tags=tuple(sorted(REQUIRED_OPTION_TAGS)),
    )
    s = stage(restated)

    too_few = table(
        *[{"id": f"t{i}", "cells": {"label": f"option {i}"}, "tags": list(REQUIRED_OPTION_TAGS)}
          for i in range(MIN_GENERATED_OPTIONS - 1)]
    )
    assert any(f"at least {MIN_GENERATED_OPTIONS}" in p for p in check_table(too_few, s))

    missing_tag = table(
        *[{"id": f"t{i}", "cells": {"label": f"option {i}"}, "tags": ["obvious"]}
          for i in range(MIN_GENERATED_OPTIONS)]
    )
    assert any("reckless" in p for p in check_table(missing_tag, s))

    duplicated = table(
        *[{"id": f"t{i}", "cells": {"label": "the same label"},
           "tags": list(REQUIRED_OPTION_TAGS)}
          for i in range(MIN_GENERATED_OPTIONS)]
    )
    assert any("share a 'label'" in p for p in check_table(duplicated, s))

    good = table(
        *[{"id": f"t{i}", "cells": {"label": f"option {i}", "description": "d"},
           "tags": list(REQUIRED_OPTION_TAGS) if i == 0 else []}
          for i in range(MIN_GENERATED_OPTIONS)]
    )
    assert check_table(good, s) == []
