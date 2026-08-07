"""Invariant-satisfying fixups for the mock provider.

The generic synthesiser in `llm/synth.py` produces schema-valid data. It cannot
produce *invariant*-valid data — a probability tree whose branches sum to 1, an
option set carrying five required tags, a profile for every person named in an
earlier stage. These fixups close that gap so the entire pipeline runs with no API
key, which is what makes the invariant suite exercisable in CI.

They are injected into `MockProvider` rather than imported by it, so `llm/` stays
free of artifact knowledge. Each receives the rendered prompt, and reads prior
artifacts back out of the `<prior>` blocks the renderer emits — the same blocks a
real model reads.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from ..schemas.common import DO_NOTHING_ID

Fixup = Callable[[dict[str, Any], str], dict[str, Any]]

_PRIOR = re.compile(
    r'<prior\s+stage="(?P<stage>[^"]+)"\s+kind="(?P<kind>[^"]+)">\s*(?P<body>.*?)\s*</prior>',
    re.DOTALL,
)
_QUESTION = re.compile(r"<question>\s*(?P<body>.*?)\s*</question>", re.DOTALL)
_CITABLE = re.compile(r"<citable>\s*(?P<body>.*?)\s*</citable>", re.DOTALL)


def priors(prompt: str) -> dict[str, dict[str, Any]]:
    """kind -> data, for every prior artifact block in the prompt."""
    out: dict[str, dict[str, Any]] = {}
    for match in _PRIOR.finditer(prompt):
        try:
            out[match.group("kind")] = json.loads(match.group("body"))
        except json.JSONDecodeError:
            continue
    return out


def question(prompt: str) -> str:
    match = _QUESTION.search(prompt)
    return match.group("body").strip() if match else ""


def citable(prompt: str) -> list[str]:
    match = _CITABLE.search(prompt)
    if not match:
        return []
    return [line.strip() for line in match.group("body").splitlines() if line.strip()]


def _quote_from(text: str, words: int = 4) -> str:
    tokens = [t for t in re.split(r"\s+", text.strip()) if t]
    quote = " ".join(tokens[:words])
    # The verbatim-quote invariants need >= 8 characters present in the source.
    while len(quote) < 10 and len(tokens) > words:
        words += 1
        quote = " ".join(tokens[:words])
    return quote


# ═══════════════════════════════════════════════════════════════════ analyst ══


def fix_evidence_ledger(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    rows = data.get("rows") or []
    for i, row in enumerate(rows):
        row["id"] = f"e{i + 1}"
    if rows:
        rows[0]["load_bearing"] = True
        rows[0]["status"] = "given"
        rows[0]["source"] = "stated in the question"
    data["rows"] = rows
    return data


def fix_evidence_gaps(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    rows = data.get("rows") or []
    for i, row in enumerate(rows):
        row["id"] = f"g{i + 1}"
    if rows:
        rows[0]["would_change_decision"] = True
    data["rows"] = rows
    return data


def fix_probability_tree(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    def leaf(node_id: str, label: str) -> dict[str, Any]:
        return {
            "id": node_id,
            "label": label,
            "probability": 1.0,
            "outcome": {"description": f"[mock] outcome {label}", "valence": 0.2, "magnitude": 3},
            "children": [],
        }

    data["root"] = {
        "id": "root",
        "label": "[mock] the decision",
        "probability": None,
        "children": [
            {
                "id": "b1",
                "label": "[mock] act",
                "probability": 0.6,
                "condition": "[mock] if acted on",
                "children": [leaf("l1", "act works out")],
            },
            {
                "id": "b2",
                "label": "[mock] wait",
                "probability": 0.4,
                "condition": "[mock] if delayed",
                "children": [leaf("l2", "wait costs little")],
            },
        ],
    }
    return data


def fix_failure_modes(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    rows = data.get("rows") or []
    template = rows[0] if rows else {
        "scenario": "[mock] it failed",
        "trigger": "[mock] trigger",
        "early_warning_signal": "[mock] signal",
        "mitigation": "[mock] mitigation",
        "probability": 0.2,
        "severity": 3,
    }
    out = []
    for i in range(3):
        row = dict(template)
        row["id"] = f"f{i + 1}"
        row["scenario"] = f"{template.get('scenario', '[mock] failure')} #{i + 1}"
        row.setdefault("early_warning_signal", "[mock] signal")
        out.append(row)
    data["rows"] = out
    return data


# ═════════════════════════════════════════════════════════════════ tactician ══

_TAGGED_OPTIONS = (
    ("the conventional move", ["obvious", "conventional"]),
    ("the opposite of the conventional move", ["inverse"]),
    ("a step that costs nothing and is reversible", ["free"]),
    ("a deliberately over-aggressive move", ["reckless"]),
    ("changing the question instead of answering it", ["reframes"]),
    ("a hybrid of staying and preparing to leave", ["hybrid"]),
    ("waiting one defined period, then deciding", ["conventional"]),
)


def fix_option_set(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    data["options"] = [
        {
            "id": f"opt{i + 1}",
            "label": f"[mock] {label}",
            "description": f"[mock] description of {label}",
            "tags": tags,
        }
        for i, (label, tags) in enumerate(_TAGGED_OPTIONS)
    ]
    return data


def fix_asymmetry(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    option_set = priors(prompt).get("OptionSet") or {}
    ids = [o["id"] for o in option_set.get("options", [])] or ["opt1"]
    data["rows"] = [
        {
            "option_id": oid,
            "max_downside": "[mock] bounded downside",
            "realistic_upside": "[mock] plausible upside",
            "downside_cost": 2,
            "upside_value": 4,
            "ratio": 2.0,
            "reversibility": "reversible",
            "time_to_know": "[mock] two weeks",
        }
        for oid in ids
    ]
    return data


def fix_ranked(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    option_set = priors(prompt).get("OptionSet") or {}
    ids = [o["id"] for o in option_set.get("options", [])] or ["opt1"]
    data["ranking"] = [
        {
            "option_id": oid,
            "rank": i + 1,
            "rationale": "[mock] rationale",
            "score": round(1.0 - i * 0.1, 2),
        }
        for i, oid in enumerate(ids)
    ]
    data["dropped"] = []
    return data


def fix_unexpected(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    data["ethics_check"] = {
        "uses_deception": False,
        "manufactures_urgency": False,
        "exploits_crisis": False,
        "rationale": "[mock] stays inside the influence boundary",
    }
    return data


# ════════════════════════════════════════════════════════════════ strategist ══


def fix_actor_list(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    data["actors"] = [
        {"id": "me", "label": "me", "role": "the decider", "is_user": True, "inferred": False},
        {
            "id": "counterparty",
            "label": "the other side",
            "role": "counterparty",
            "is_user": False,
            "inferred": True,
        },
    ]
    return data


def fix_graph(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    actor_list = priors(prompt).get("ActorList") or {}
    actors = actor_list.get("actors") or [
        {"id": "me", "label": "me"},
        {"id": "counterparty", "label": "the other side"},
    ]
    ids = [a["id"] for a in actors]
    if "me" not in ids:
        actors = [{"id": "me", "label": "me"}, *actors]
        ids = [a["id"] for a in actors]

    data["nodes"] = [
        {
            "id": a["id"],
            "label": a.get("label", a["id"]),
            "role": a.get("role", ""),
            "formal_authority": 0.3 if a["id"] == "me" else 0.7,
            "real_influence": 0.5,
            "controls": ["[mock] something they control"],
            "fears": ["[mock] a fear"],
            "optimising_for": "[mock] what they actually want",
            "stated_position": "[mock] stated position",
            "actual_interest": "[mock] actual interest",
        }
        for a in actors
    ]
    data["edges"] = [
        {
            "src": "me",
            "dst": other,
            "kind": "depends_on",
            "weight": 0.6,
            "is_hidden": False,
            "note": "[mock] relationship",
        }
        for other in ids
        if other != "me"
    ]
    return data


def fix_incentives(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    graph = priors(prompt).get("StakeholderGraph") or {}
    ids = [n["id"] for n in graph.get("nodes", []) if n["id"] != "me"] or ["counterparty"]
    data["rows"] = [
        {
            "actor_id": aid,
            "rewarded_for": "[mock] what they are rewarded for",
            "punished_for": "[mock] what they are punished for",
            "will_never_say": "[mock] the thing they will not say out loud",
            "misalignment_with_me": "[mock] where our interests diverge",
            "severity": 3,
        }
        for aid in ids
    ]
    return data


def fix_leverage(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    data["i_control"] = [
        {
            "id": "lev1",
            "what": "[mock] something they want",
            "who_wants_it": "the other side",
            "strength": 0.5,
            "expiry": "[mock] lapses in about a month",
        }
    ]
    data["my_batna"] = {
        "actor_id": "me",
        "description": "[mock] what I do if there is no agreement",
        "strength": 0.4,
        "honest_assessment": "[mock] weaker than I would like",
    }
    return data


def fix_sequence(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    steps = data.get("steps") or []
    if not steps:
        steps = [{}]
    out = []
    for i, step in enumerate(steps):
        row = dict(step)
        row["order"] = i + 1
        row.setdefault("actor_id", "counterparty")
        row.setdefault("objective", "[mock] objective")
        row["if_it_fails"] = row.get("if_it_fails") or "[mock] fallback"
        out.append(row)
    data["steps"] = out
    return data


# ══════════════════════════════════════════════════════════════ psychologist ══


_DEFAULT_CAST: list[dict[str, Any]] = [
    {
        "id": "me",
        "label": "me",
        "relationship_to_user": "self",
        "is_user": True,
        "inferred": False,
    },
    {
        "id": "other",
        "label": "the other person",
        "relationship_to_user": "counterpart",
        "is_user": False,
        "inferred": True,
    },
]


def fix_person_list(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    data["people"] = [dict(p) for p in _DEFAULT_CAST]
    return data


def fix_profiles(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    person_list = priors(prompt).get("PersonList") or {}
    people = person_list.get("people") or _DEFAULT_CAST
    data["profiles"] = [
        {
            "person_id": p["id"],
            "driving_emotion": "[mock] driving emotion",
            "fear": "[mock] fear",
            "unmet_need": "[mock] unmet need",
            "motivation": "[mock] motivation",
            "stress_level": 3,
            "reaction_if_accepted": "[mock] reaction if it goes their way",
            "reaction_if_rejected": "[mock] reaction if it does not",
            "what_they_wont_say": "[mock] what they will not say",
            "confidence": 0.4 if p.get("inferred") else 0.6,
        }
        for p in people
    ]
    return data


def fix_self_read(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    data["evidence_from_phrasing"] = [_quote_from(question(prompt))]
    return data


# ═════════════════════════════════════════════════════════════════ optimizer ══


def fix_waste(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    rows = data.get("rows") or []
    for i, row in enumerate(rows):
        row["id"] = f"w{i + 1}"
    if rows:
        rows[0]["verdict"] = "cut"
    data["rows"] = rows
    return data


def fix_effort_return(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    data["rows"] = [
        {
            "option_id": DO_NOTHING_ID,
            "effort": 1,
            "expected_return": 2,
            "ratio": 2.0,
            "simpler_version": None,
        },
        {
            "option_id": "opt1",
            "effort": 3,
            "expected_return": 4,
            "ratio": 1.33,
            "simpler_version": "[mock] the smaller version",
        },
    ]
    return data


# ══════════════════════════════════════════════════════════════════ ethicist ══


def fix_parties(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    data["parties"] = [
        {
            "id": "me",
            "label": "me",
            "in_the_room": True,
            "can_consent": True,
            "future_self": False,
            "inferred": False,
        },
        {
            "id": "future_me",
            "label": "me in ten years",
            "in_the_room": False,
            "can_consent": False,
            "future_self": True,
            "inferred": False,
        },
    ]
    return data


def fix_values(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    quote = _quote_from(question(prompt))
    data["rows"] = [
        {
            "id": "v1",
            "value": "[mock] a value the user stated",
            "source": "stated_by_user",
            "quote": quote,
            "options_serving": ["opt1"],
            "options_violating": [DO_NOTHING_ID],
        },
        {
            "id": "v2",
            "value": "[mock] a value inferred from the user",
            "source": "inferred_from_user",
            "quote": None,
            "options_serving": [DO_NOTHING_ID],
            "options_violating": [],
        },
    ]
    return data


def fix_harm(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    data["rows"] = [
        {
            "option_id": DO_NOTHING_ID,
            "who_pays": ["me"],
            "magnitude": 2,
            "reversible": True,
            "consented": True,
            "alternative_that_avoids": None,
        },
        {
            "option_id": "opt1",
            "who_pays": ["the other person"],
            "magnitude": 3,
            "reversible": False,
            "consented": False,
            "alternative_that_avoids": "[mock] a gentler route",
        },
    ]
    return data


def fix_regret(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    data["rows"] = [
        {
            "option_id": oid,
            "regret_1y": 2,
            "regret_5y": 3,
            "regret_10y": 1,
            "tell_a_friend_test": "[mock] comfortable describing it",
            "asymmetry": "[mock] regret of inaction is worse",
        }
        for oid in (DO_NOTHING_ID, "opt1")
    ]
    return data


# ══════════════════════════════════════════════════════════════════ terminal ══


def fix_conclusion(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    refs = citable(prompt)
    key_claims = []
    for ref in refs[:2]:
        head, _, row_id = ref.partition("#")
        parts = head.split("/")
        if len(parts) != 3:
            continue
        key_claims.append(
            {
                "module": parts[0],
                "stage_id": parts[1],
                "kind": parts[2],
                "row_id": row_id or None,
            }
        )
    data["stance"] = "Take the mock action within the next two weeks."
    data["first_action"] = "[mock] send one message tomorrow morning."
    data["key_claims"] = key_claims
    confidence = data.get("confidence") or {}
    confidence["score"] = 0.55
    confidence["basis"] = "[mock] basis"
    confidence["falsifier"] = "[mock] the one observation that would flip this."
    data["confidence"] = confidence
    data["ethical_veto"] = False
    data["veto_grounds"] = None
    return data


# ═══════════════════════════════════════════════════════ council-level calls ══

_MODULE_HEADER = re.compile(r"^MODULE:?\s+(?P<module>[a-z_]+)", re.MULTILINE)


def fix_critiques(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    """Aim the synthesised critiques at modules that actually appear in the prompt.

    Without this the placeholder `target` never matches a running module and every
    critique is silently dropped — which would make the debate stage untestable.
    """
    targets = _MODULE_HEADER.findall(prompt)
    if not targets:
        data["critiques"] = []
        return data
    kinds = ["missing_factor", "unsupported", "bias_fired", "strong_agreement"]
    data["critiques"] = [
        {
            "target": target,
            "target_ref": None,
            "kind": kinds[i % len(kinds)],
            "statement": f"[mock] critique of {target}",
            "severity": 3,
            "bias_id": None,
        }
        for i, target in enumerate(dict.fromkeys(targets))
    ]
    # `bias_fired` requires a bias id; take the first one listed for that target.
    for critique in data["critiques"]:
        if critique["kind"] == "bias_fired":
            match = re.search(
                rf"MODULE:?\s+{critique['target']}\b.*?- `(?P<bias>[a-z_]+)`",
                prompt,
                re.DOTALL,
            )
            if match:
                critique["bias_id"] = match.group("bias")
            else:
                critique["kind"] = "missing_factor"
    return data


def fix_revision(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    data["stance"] = "Take the mock action within the next two weeks."
    data["delta"] = "[mock] unchanged after review"
    confidence = data.get("confidence") or {}
    confidence["score"] = 0.6
    confidence["basis"] = "[mock] basis after critique"
    confidence["falsifier"] = "[mock] the observation that would flip this."
    data["confidence"] = confidence
    data["accepted"] = []
    data["rejected"] = []
    return data


def fix_synthesis(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    modules = list(dict.fromkeys(_MODULE_HEADER.findall(prompt)))
    data["debate_summary"] = "[mock] the council disagreed about tempo versus evidence."
    data["council_blind_spot"] = (
        "[mock] no module examined whether the user actually wants the thing they are "
        "optimising for."
    )
    data["consensus"] = [
        {"point": "[mock] a point all modules supported", "modules": modules, "supported_by": []}
    ]
    data["disagreements"] = []
    data["blind_spots_fired"] = []
    data["minority_opinions"] = (
        [
            {
                "module": modules[-1],
                "position": "[mock] the dissenting position",
                "when_it_would_be_right": "[mock] if the stated savings figure is wrong",
            }
        ]
        if modules
        else []
    )
    recommendation = data.get("recommendation") or {}
    recommendation["action"] = "[mock] the recommended course of action"
    recommendation["first_action"] = "[mock] one concrete step in the next 48 hours"
    data["recommendation"] = recommendation
    confidence = data.get("confidence") or {}
    confidence["score"] = 0.55
    confidence["basis"] = "[mock] synthesis basis"
    confidence["falsifier"] = "[mock] what would overturn the recommendation."
    data["confidence"] = confidence
    data["expected_outcome"] = {
        "statement": "[mock] a falsifiable prediction about the next 90 days",
        "check_in_days": 90,
        "measurable_by": "[mock] how it would be measured",
    }
    data["long_term_prediction"] = [
        {"horizon": h, "prediction": f"[mock] prediction at {h}", "confidence": 0.5}
        for h in ("3mo", "1y", "5y")
    ]
    data["information_to_gather"] = ["[mock] the highest-value unknown"]
    data["alternative_strategy"] = {
        "action": "[mock] the second-best path",
        "trigger": "[mock] switch if this happens",
    }
    return data


def fix_intake(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    q = question(prompt)
    data["normalised"] = f"[mock] {' '.join(q.split()[:12])}"
    data["domains"] = ["career"]
    data["options"] = [
        {"id": "opt1", "label": "[mock] act", "description": "[mock] take the action"},
        {"id": "opt2", "label": "[mock] wait", "description": "[mock] hold position"},
    ]
    data["actors"] = ["my manager"]
    data["constraints"] = ["[mock] a stated constraint"]
    data["current_state"] = "[mock] what the user is doing now"
    data["stated_values"] = ["[mock] a value the user named"]
    data["missing_inputs"] = ["[mock] something the user did not supply"]
    data["is_decision"] = True
    return data


_GRADABLE = re.compile(r"^MODULE:\s+(?P<module>[a-z_]+)(?P<rest>.*)$", re.MULTILINE)


def fix_grader(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    """Grade every module the prompt lists, so the strict coverage check passes.

    The grader refuses a partial council — an absent verdict would quietly drop a
    module out of its own calibration history — so the mock has to be complete.
    Verdicts alternate so the resulting scores are not degenerate.
    """
    modules = [
        match.group("module")
        for match in _GRADABLE.finditer(prompt)
        if "ABSTAINED" not in match.group("rest")
    ]
    modules = list(dict.fromkeys(modules)) or ["analyst"]
    verdicts = ["right", "partial", "wrong", "untested"]
    data["module_verdicts"] = [
        {
            "module": module,
            "verdict": verdicts[i % len(verdicts)],
            "justification": f"[mock] how {module} fared",
            "followed": i % 2 == 0,
            "falsifier_fired": i % 3 == 0,
        }
        for i, module in enumerate(modules)
    ]
    data["metric_answers"] = []
    data["expected_outcome_met"] = "partial"
    data["chose_was_proposed"] = True
    data["unpredicted"] = ["[mock] something nobody predicted"]
    return data


_EXTRACT_TARGET = re.compile(r"^(?P<module>[a-z_]+) → kind `(?P<kind>[a-z_]+)`", re.MULTILINE)


def fix_extraction(data: dict[str, Any], prompt: str) -> dict[str, Any]:
    """One memory per module listed, salient enough to be recalled by the next run."""
    targets = _EXTRACT_TARGET.findall(prompt)
    q = question(prompt)
    subject = " ".join(q.split()[:6]) or "the situation"
    data["memories"] = [
        {
            "module": module,
            "kind": kind,
            "content": f"[mock] durable {kind} learned about {subject}",
            "salience": 0.8,
        }
        for module, kind in targets
    ]
    return data


FIXUPS: dict[str, Fixup] = {
    "IntakeResult": fix_intake,
    "GraderResult": fix_grader,
    "ExtractionResult": fix_extraction,
    "CritiqueList": fix_critiques,
    "RevisionDraft": fix_revision,
    "Synthesis": fix_synthesis,
    "EvidenceLedger": fix_evidence_ledger,
    "EvidenceGaps": fix_evidence_gaps,
    "ProbabilityTree": fix_probability_tree,
    "FailureModeTable": fix_failure_modes,
    "OptionSet": fix_option_set,
    "AsymmetryTable": fix_asymmetry,
    "RankedOptions": fix_ranked,
    "UnexpectedMove": fix_unexpected,
    "ActorList": fix_actor_list,
    "StakeholderGraph": fix_graph,
    "IncentiveTable": fix_incentives,
    "LeverageInventory": fix_leverage,
    "SequencePlan": fix_sequence,
    "PersonList": fix_person_list,
    "PersonProfileSet": fix_profiles,
    "SelfRead": fix_self_read,
    "WasteAudit": fix_waste,
    "EffortReturnRanking": fix_effort_return,
    "AffectedParties": fix_parties,
    "ValueAudit": fix_values,
    "HarmLedger": fix_harm,
    "RegretMatrix": fix_regret,
    "Conclusion": fix_conclusion,
}


def build_fixups() -> dict[str, Fixup]:
    """Wrap per-kind fixups so batched calls (an object keyed by stage id) work too.

    A batch response is `{stage_id: {...artifact...}}`; the mock has no stage map, so
    the wrapper looks for nested objects and applies whichever fixup matches by
    shape. The batch model's field names are stage ids, and its annotations name the
    artifact types, so the executor passes a mapping through `LLMRequest.extra`.
    """
    return dict(FIXUPS)
