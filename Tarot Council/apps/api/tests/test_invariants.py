"""Every invariant that carries architectural weight, in both directions.

A validator that never fires is decoration, so each case asserts the *rejection* as
well as the acceptance.
"""

from __future__ import annotations

import pytest

from app.engine.invariants import InvariantContext, check, normalize
from app.programs import loader
from app.schemas.artifacts import (
    Artifact,
    Conclusion,
    ConstraintAnalysis,
    EvidenceLedger,
    OptionSet,
    PersonList,
    PersonProfileSet,
    ProbabilityTree,
    SelfRead,
    StakeholderGraph,
    model_for,
)
from app.schemas.common import DO_NOTHING_ID


def ctx(module: str, stage_id: str, context, **kw) -> InvariantContext:
    program = loader.program(module)
    return InvariantContext(
        context=context, stage=program.stage(stage_id), module=module, **kw
    )


def problems(kind: str, data: dict, c: InvariantContext) -> list[str]:
    typed = model_for(kind).model_validate(normalize(kind, dict(data)))
    return check(kind, typed, c)


# ─────────────────────────────────────────────── probability tree arithmetic ──


def _tree(p1: float, p2: float, *, leaf_outcome=True) -> dict:
    leaf = {"description": "it worked", "valence": 0.4, "magnitude": 3}
    return {
        "root": {
            "id": "root",
            "label": "the choice",
            "children": [
                {
                    "id": "b1",
                    "label": "leave",
                    "probability": p1,
                    "children": [
                        {
                            "id": "l1",
                            "label": "works",
                            "probability": 1.0,
                            "outcome": leaf if leaf_outcome else None,
                        }
                    ],
                },
                {
                    "id": "b2",
                    "label": "stay",
                    "probability": p2,
                    "children": [
                        {"id": "l2", "label": "fine", "probability": 1.0, "outcome": leaf}
                    ],
                },
            ],
        }
    }


def test_probability_tree_must_sum_to_one(context):
    c = ctx("analyst", "tree", context)
    assert problems("ProbabilityTree", _tree(0.6, 0.4), c) == []
    bad = problems("ProbabilityTree", _tree(0.6, 0.9), c)
    assert any("summing to 1.500" in p for p in bad)


def test_probability_tree_tolerates_rounding(context):
    c = ctx("analyst", "tree", context)
    assert problems("ProbabilityTree", _tree(0.33, 0.67), c) == []


def test_probability_tree_leaf_needs_outcome(context):
    c = ctx("analyst", "tree", context)
    bad = problems("ProbabilityTree", _tree(0.5, 0.5, leaf_outcome=False), c)
    assert any("no outcome" in p for p in bad)


def test_probability_tree_must_be_two_deep(context):
    shallow = {
        "root": {
            "id": "root",
            "label": "x",
            "children": [
                {
                    "id": "a",
                    "label": "a",
                    "probability": 1.0,
                    "outcome": {"description": "o", "valence": 0, "magnitude": 1},
                }
            ],
        }
    }
    bad = problems("ProbabilityTree", shallow, ctx("analyst", "tree", context))
    assert any("shallower" in p for p in bad)


# ───────────────────────────────────────────────────── stakeholder graph ──────


def _graph(edges: list[dict], nodes: list[str]) -> dict:
    return {
        "nodes": [
            {"id": n, "label": n, "formal_authority": 0.5, "real_influence": 0.5}
            for n in nodes
        ],
        "edges": edges,
    }


def test_graph_requires_me_node(context):
    c = ctx("strategist", "graph", context)
    bad = problems(
        "StakeholderGraph",
        _graph([{"src": "a", "dst": "b", "kind": "reports_to"}], ["a", "b"]),
        c,
    )
    assert any("id 'me'" in p for p in bad)


def test_graph_must_be_connected(context):
    c = ctx("strategist", "graph", context)
    bad = problems(
        "StakeholderGraph",
        _graph([{"src": "me", "dst": "boss", "kind": "reports_to"}], ["me", "boss", "orphan"]),
        c,
    )
    assert any("no path to the rest" in p and "orphan" in p for p in bad)


def test_graph_valid_case_passes(context):
    c = ctx("strategist", "graph", context)
    assert (
        problems(
            "StakeholderGraph",
            _graph([{"src": "me", "dst": "boss", "kind": "reports_to"}], ["me", "boss"]),
            c,
        )
        == []
    )


def test_power_gap_is_computed_server_side():
    data = normalize(
        "StakeholderGraph",
        {
            "nodes": [
                {"id": "me", "label": "me", "formal_authority": 0.9, "real_influence": 0.2},
                {"id": "b", "label": "b", "formal_authority": 0.5, "real_influence": 0.5},
            ],
            "edges": [],
        },
    )
    graph = StakeholderGraph.model_validate(data)
    assert graph.nodes[0].power_gap is True
    assert graph.nodes[1].power_gap is False


# ──────────────────────────────────────────────── profile-set completeness ───


def test_every_person_needs_a_full_profile(context):
    cast = PersonList.model_validate(
        {
            "people": [
                {"id": "me", "label": "me", "is_user": True},
                {"id": "mgr", "label": "my manager", "inferred": True},
            ]
        }
    )
    prior = {
        "cast": Artifact.of(
            module="psychologist", stage_id="cast", kind="PersonList", data=cast
        )
    }
    c = ctx("psychologist", "profiles", context, prior=prior)

    def profile(pid: str, **over):
        base = {
            "person_id": pid,
            "driving_emotion": "fear of wasting a year",
            "fear": "being strung along",
            "unmet_need": "a decision",
            "motivation": "build the thing",
            "stress_level": 4,
            "reaction_if_accepted": "relief",
            "reaction_if_rejected": "withdrawal",
            "what_they_wont_say": "they already decided",
            "confidence": 0.4,
        }
        base.update(over)
        return base

    assert problems("PersonProfileSet", {"profiles": [profile("me"), profile("mgr")]}, c) == []

    partial = problems("PersonProfileSet", {"profiles": [profile("me")]}, c)
    assert any("Missing a profile for: mgr" in p for p in partial)

    empty_field = problems(
        "PersonProfileSet",
        {"profiles": [profile("me"), profile("mgr", what_they_wont_say="  ")]},
        c,
    )
    assert any("empty fields" in p for p in empty_field)

    overconfident = problems(
        "PersonProfileSet",
        {"profiles": [profile("me"), profile("mgr", confidence=0.9)]},
        c,
    )
    assert any("inferred person" in p for p in overconfident)


# ─────────────────────────────────────────────────────── verbatim quoting ────


def test_self_read_must_quote_the_user(context):
    c = ctx("psychologist", "self_read", context)
    base = {
        "stated_feeling": "stuck",
        "likely_real_feeling": "afraid of being strung along",
        "what_is_being_avoided": "asking directly",
        "question_behind_the_question": "will they ever commit",
        "confidence": 0.5,
    }
    invented = problems(
        "SelfRead", {**base, "evidence_from_phrasing": ["they never valued me"]}, c
    )
    assert any("verbatim quote" in p for p in invented)

    quoted = problems(
        "SelfRead", {**base, "evidence_from_phrasing": ["nothing is in writing"]}, c
    )
    assert quoted == []


# ────────────────────────────────────────────────────── the option quota ─────


def test_option_set_quota_and_required_tags(context):
    c = ctx("tactician", "generate", context)
    kinds = ["obvious", "inverse", "free", "reckless", "reframes", "conventional", "hybrid"]
    full = {
        "options": [
            {"id": f"o{i}", "label": f"option {i}", "tags": [k]} for i, k in enumerate(kinds)
        ]
    }
    assert problems("OptionSet", full, c) == []

    too_few = {"options": full["options"][:4]}
    bad = problems("OptionSet", too_few, c)
    assert any("at least 7" in p for p in bad)
    assert any("missing required kinds" in p for p in bad)

    no_reckless = {
        "options": [
            {**o, "tags": ["conventional"] if o["tags"] == ["reckless"] else o["tags"]}
            for o in full["options"]
        ]
    }
    assert any("reckless" in p for p in problems("OptionSet", no_reckless, c))


def test_duplicate_option_labels_rejected(context):
    c = ctx("tactician", "generate", context)
    kinds = ["obvious", "inverse", "free", "reckless", "reframes", "conventional", "hybrid"]
    dupes = {"options": [{"id": f"o{i}", "label": "same", "tags": [k]} for i, k in enumerate(kinds)]}
    assert any("same label" in p for p in problems("OptionSet", dupes, c))


# ──────────────────────────────────────────────── the influence boundary ─────


def test_unexpected_move_ethics_gate(context):
    c = ctx("tactician", "unexpected", context)
    move = {
        "move": "ask for the offer in writing by Friday",
        "why_available": "nobody has asked",
        "what_it_forces": "a yes or a no",
        "cost_if_wrong": "an awkward week",
        "ethics_check": {
            "uses_deception": False,
            "manufactures_urgency": False,
            "exploits_crisis": False,
            "rationale": "a direct honest request",
        },
    }
    assert problems("UnexpectedMove", move, c) == []

    move["ethics_check"]["manufactures_urgency"] = True
    bad = problems("UnexpectedMove", move, c)
    assert any("influence boundary" in p and "manufactures_urgency" in p for p in bad)


# ───────────────────────────────────────────────── single binding constraint ─


def test_constraint_must_be_singular(context):
    c = ctx("optimizer", "constraint", context)
    ok = {
        "binding_constraint": "runway measured in months",
        "evidence": ["four months of savings"],
        "if_relieved": "the decision stops being urgent",
    }
    assert problems("ConstraintAnalysis", ok, c) == []
    two = {**ok, "binding_constraint": "runway and the missing written offer"}
    assert any("more than one thing" in p for p in problems("ConstraintAnalysis", two, c))


def test_effort_ranking_must_price_doing_nothing(context):
    c = ctx("optimizer", "effort_return", context)
    without = {"rows": [{"option_id": "opt1", "effort": 3, "expected_return": 4}]}
    assert any(DO_NOTHING_ID in p for p in problems("EffortReturnRanking", without, c))
    with_row = {
        "rows": [
            {"option_id": DO_NOTHING_ID, "effort": 1, "expected_return": 2},
            {"option_id": "opt1", "effort": 3, "expected_return": 4},
        ]
    }
    assert problems("EffortReturnRanking", with_row, c) == []


def test_ratios_are_recomputed_not_trusted():
    data = normalize(
        "EffortReturnRanking",
        {"rows": [{"option_id": "x", "effort": 2, "expected_return": 5, "ratio": 99.0}]},
    )
    assert data["rows"][0]["ratio"] == 2.5


def test_do_nothing_is_inserted_into_the_decision_frame():
    data = normalize(
        "DecisionFrame",
        {
            "options": [{"id": "opt1", "label": "leave"}],
            "the_actual_choice": "leave now or wait for writing",
            "reversibility": "costly",
        },
    )
    assert any(o["id"] == DO_NOTHING_ID for o in data["options"])


# ────────────────────────────────────────────────────── evidence discipline ──


def test_evidence_ledger_discipline(context):
    c = ctx("analyst", "evidence", context)
    rows = [
        {
            "id": "e1",
            "statement": "four months of savings",
            "status": "given",
            "source": "stated in the question",
            "load_bearing": True,
            "confidence": 0.9,
        }
    ]
    assert problems("EvidenceLedger", {"rows": rows}, c) == []

    nothing_load_bearing = [{**rows[0], "load_bearing": False}]
    assert any(
        "load_bearing" in p for p in problems("EvidenceLedger", {"rows": nothing_load_bearing}, c)
    )

    unsourced = [{**rows[0], "source": ""}]
    assert any(
        "requires a non-empty source" in p
        for p in problems("EvidenceLedger", {"rows": unsourced}, c)
    )

    overconfident_assumption = [{**rows[0], "status": "assumed", "confidence": 0.95}]
    assert any(
        "too high for status" in p
        for p in problems("EvidenceLedger", {"rows": overconfident_assumption}, c)
    )


# ─────────────────────────────────────────────── no premature recommendation ─


def test_non_terminal_stage_cannot_recommend(context):
    c = ctx("analyst", "evidence", context)
    rows = [
        {
            "id": "e1",
            "statement": "you should quit now and not look back",
            "status": "inferred",
            "source": "n/a",
            "load_bearing": True,
            "confidence": 0.5,
        }
    ]
    bad = problems("EvidenceLedger", {"rows": rows}, c)
    assert any("not the terminal stage" in p for p in bad)


def test_terminal_stage_may_recommend(context):
    c = ctx("analyst", "recommend", context, citable=set())
    conclusion = {
        "stance": "Ask for the offer in writing this week.",
        "first_action": "Send the email tomorrow morning.",
        "reasoning": "You should do this because the ledger supports it.",
        "confidence": {"score": 0.6, "basis": "one strong row", "falsifier": "a written offer arrives"},
    }
    assert problems("Conclusion", conclusion, c) == []


# ────────────────────────────────────────────────── confidence is auditable ──


def test_conclusion_needs_a_falsifier(context):
    c = ctx("analyst", "recommend", context)
    bad = problems(
        "Conclusion",
        {
            "stance": "Ask for it in writing.",
            "first_action": "Email tomorrow.",
            "reasoning": "because",
            "confidence": {"score": 0.5, "basis": "b", "falsifier": "  "},
        },
        c,
    )
    assert any("falsifier" in p for p in bad)


def test_stance_must_start_with_a_verb(context):
    c = ctx("analyst", "recommend", context)
    bad = problems(
        "Conclusion",
        {
            "stance": "I think the internship is probably worth keeping.",
            "first_action": "Email tomorrow.",
            "reasoning": "because",
            "confidence": {"score": 0.5, "basis": "b", "falsifier": "f"},
        },
        c,
    )
    assert any("must be an instruction beginning with a verb" in p for p in bad)


def test_key_claims_must_resolve(context):
    citable = {"analyst/evidence/EvidenceLedger#e1"}
    c = ctx("analyst", "recommend", context, citable=citable)
    base = {
        "stance": "Ask for the offer in writing.",
        "first_action": "Email tomorrow.",
        "reasoning": "because",
        "confidence": {"score": 0.5, "basis": "b", "falsifier": "f"},
    }
    assert any("'key_claims' is empty" in p for p in problems("Conclusion", base, c))

    bogus = {
        **base,
        "key_claims": [
            {"module": "analyst", "stage_id": "evidence", "kind": "EvidenceLedger", "row_id": "e9"}
        ],
    }
    assert any("do not match any citable row" in p for p in problems("Conclusion", bogus, c))

    good = {
        **base,
        "key_claims": [
            {"module": "analyst", "stage_id": "evidence", "kind": "EvidenceLedger", "row_id": "e1"}
        ],
    }
    assert problems("Conclusion", good, c) == []


def test_high_confidence_is_unavailable_over_assumptions(context):
    """The mechanical form of "never hallucinate confidence"."""
    ledger = EvidenceLedger.model_validate(
        {
            "rows": [
                {
                    "id": "e1",
                    "statement": "the offer is coming",
                    "status": "assumed",
                    "source": "the user's manager",
                    "load_bearing": True,
                    "confidence": 0.5,
                }
            ]
        }
    )
    prior = {
        "evidence": Artifact.of(
            module="analyst", stage_id="evidence", kind="EvidenceLedger", data=ledger
        )
    }
    citable = {"analyst/evidence/EvidenceLedger#e1"}
    c = ctx("analyst", "recommend", context, prior=prior, citable=citable)
    conclusion = {
        "stance": "Wait for the written offer.",
        "first_action": "Do nothing until Friday.",
        "reasoning": "resting on the assumption",
        "confidence": {"score": 0.92, "basis": "strong", "falsifier": "no offer by Friday"},
        "key_claims": [
            {"module": "analyst", "stage_id": "evidence", "kind": "EvidenceLedger", "row_id": "e1"}
        ],
    }
    bad = problems("Conclusion", conclusion, c)
    assert any("requires no assumed or speculative claims" in p for p in bad)

    conclusion["confidence"]["score"] = 0.65
    assert problems("Conclusion", conclusion, c) == []


# ───────────────────────────────────────────── the ethicist's inaction gate ──


def test_inaction_harm_is_mandatory_and_complete(context):
    c = ctx("ethicist", "inaction", context)
    complete = {
        "harm_of_delay": "another quarter of ambiguity",
        "harm_of_status_quo": "savings erode and resentment builds",
        "who_pays_for_inaction": ["me"],
        "decay": "the product idea gets less differentiated",
    }
    assert problems("InactionHarm", complete, c) == []
    bad = problems("InactionHarm", {**complete, "harm_of_status_quo": " "}, c)
    assert any("price inaction before concluding" in p for p in bad)


def test_value_audit_requires_a_real_quote(context):
    c = ctx("ethicist", "values", context)
    invented = {
        "rows": [
            {
                "id": "v1",
                "value": "loyalty",
                "source": "stated_by_user",
                "quote": "loyalty matters most to me",
            }
        ]
    }
    assert any("does not appear in the user's words" in p for p in problems("ValueAudit", invented, c))

    real = {
        "rows": [
            {
                "id": "v1",
                "value": "keeping the relationship",
                "source": "stated_by_user",
                "quote": "not burning the bridge",
            }
        ]
    }
    assert problems("ValueAudit", real, c) == []


def test_notes_are_length_capped(context):
    c = ctx("analyst", "gaps", context)
    bad = problems(
        "EvidenceGaps",
        {"rows": [], "notes": "x" * 500},
        c,
    )
    assert any("keep it under" in p for p in bad)
