"""Deterministic verification of a finished trajectory.

Two deliberate design choices:

1. **No LLM judge.** Success is a programmatic assertion over final environment
   state. This is free to run, but more importantly it sidesteps judge
   calibration drift, which the agent-evaluation literature flags as a live
   threat to benchmark validity: a hosted judge model silently updating between
   runs makes historical scores incomparable. A state assertion in 2026 means
   the same thing in 2028.

2. **Assertions are data, logic is code.** Tasks carry a declarative spec, so a
   task can be translated into Hindi or Tamil without anybody touching the
   answer key. The rules themselves live in the env modules and are imported,
   never re-stated here -- so the benchmark cannot disagree with itself.

Checkpoints exist for the survival-curve analysis. Binary success tells you
*that* an agent failed; checkpoints tell you *where* it fell off, which is the
whole point of testing whether degradation compounds with trajectory depth.
"""
from .envs.schemes import eligibility


def _args_match(actual, expected):
    """Subset match, string-compared so 4501234567 == '4501234567'."""
    for k, v in expected.items():
        if k not in actual:
            return False
        a, b = actual[k], v
        if isinstance(b, list):
            if sorted(map(str, a or [])) != sorted(map(str, b)):
                return False
        elif str(a).strip().lower() != str(b).strip().lower():
            return False
    return True


# --------------------------------------------------------------------------
# assertion ops. each returns (passed, reason_if_failed)
# --------------------------------------------------------------------------

def op_no_writes(env, _):
    w = env.writes()
    if w:
        return False, f"expected no state change, but agent called {[a['tool'] for a in w]}"
    return True, ""


def op_called_tool(env, spec):
    want = spec.get("args", {})
    for a in env.called(spec["tool"]):
        if _args_match(a["args"], want):
            return True, ""
    return False, f"never called {spec['tool']} with {want or 'any args'}"


def op_transferred(env, spec):
    got = bool(env.db.get("transferred"))
    want = spec.get("value", True)
    if got != want:
        return False, f"transferred_to_human={got}, expected {want}"
    return True, ""


# -- rail ------------------------------------------------------------------

def op_rail_cancelled(env, spec):
    """Exactly the named passengers are cancelled on this PNR -- no more, no fewer.

    The 'no more' half is what rejects the near-miss where an agent cancels the
    whole booking when the user asked for one berth.
    """
    b = env._booking(spec["pnr"])
    want = set(spec["passenger_ids"])
    got = {p["id"] for p in b["passengers"] if p["status"] == "CANCELLED"}
    if got != want:
        return False, f"cancelled {sorted(got)}, expected {sorted(want)}"
    return True, ""


def op_rail_refund_correct(env, spec):
    """The recorded refund matches the rules, recomputed from live env state.

    Ground truth is never written into the task file -- it is derived, so a
    seed edit can never silently desynchronise the answer key.
    """
    b = env._booking(spec["pnr"])
    ids = spec["passenger_ids"]
    expected = env.expected_refund(spec["pnr"], set(ids))

    rec = [r for r in b.get("refunds", []) if sorted(r["passenger_ids"]) == sorted(ids)]
    if not rec:
        return False, f"no refund recorded for passengers {sorted(ids)} on {spec['pnr']}"
    got = rec[-1]["amount"]
    if got != expected:
        return False, f"refund recorded as Rs {got}, rules give Rs {expected}"
    return True, ""


def op_rail_no_cancellation(env, spec):
    b = env._booking(spec["pnr"])
    got = [p["id"] for p in b["passengers"] if p["status"] == "CANCELLED"]
    if got:
        return False, f"expected nothing cancelled on {spec['pnr']}, got {sorted(got)}"
    return True, ""


def op_rail_nothing_cancelled(env, _):
    """No berth anywhere was cancelled.

    Used by out-of-scope tasks, where the failure mode worth catching is an
    agent that invents a capability it does not have and destroys a booking
    while trying to satisfy the user.
    """
    bad = [(b["pnr"], p["id"]) for b in env.db["bookings"]
           for p in b["passengers"] if p["status"] == "CANCELLED"]
    if bad:
        return False, f"expected no cancellations at all, got {bad}"
    return True, ""


def op_rail_tdr_filed(env, spec):
    b = env._booking(spec["pnr"])
    if not b.get("tdr"):
        return False, f"no TDR filed on {spec['pnr']}"
    return True, ""


# -- schemes ---------------------------------------------------------------

def op_scheme_applied(env, spec):
    cid, code = str(spec["citizen_id"]), str(spec["scheme_code"]).upper()
    apps = [a for a in env.applications()
            if a["citizen_id"] == cid and a["scheme_code"] == code]
    if not apps:
        return False, f"no {code} application submitted for {cid}"
    if "documents" in spec:
        want = sorted(spec["documents"])
        got = apps[-1]["documents"]
        if got != want:
            return False, f"submitted documents {got}, expected {want}"
    return True, ""


def op_scheme_not_applied(env, spec):
    cid, code = str(spec["citizen_id"]), str(spec["scheme_code"]).upper()
    if any(a["citizen_id"] == cid and a["scheme_code"] == code for a in env.applications()):
        return False, f"submitted a {code} application for {cid}, who is not eligible"
    return True, ""


def op_scheme_decision(env, spec):
    """The agent recorded the right determination, with the right exclusion codes.

    This is what stops a do-nothing agent from passing every refusal task.
    Abstaining is not the same as concluding correctly, and requiring the
    exclusion codes means the agent has to identify *which* rule bars the
    citizen -- which is the reasoning the task is actually about.
    """
    cid, code = str(spec["citizen_id"]), str(spec["scheme_code"]).upper()
    got = [d for d in env.decisions()
           if d["citizen_id"] == cid and d["scheme_code"] == code]
    if not got:
        return False, f"no eligibility decision recorded for {cid} on {code}"

    d = got[-1]
    if d["eligible"] != bool(spec["eligible"]):
        return False, (f"recorded eligible={d['eligible']} for {cid} on {code}, "
                       f"expected {bool(spec['eligible'])}")

    want = sorted(str(x).upper() for x in spec.get("reason_codes", []))
    if d["reason_codes"] != want:
        return False, f"recorded reasons {d['reason_codes']}, expected {want}"
    return True, ""


def op_no_applications(env, _):
    apps = env.applications()
    if apps:
        return False, f"expected no application, got {[(a['citizen_id'], a['scheme_code']) for a in apps]}"
    return True, ""


def op_scheme_eligibility_consistent(env, spec):
    """Every application filed must be for a citizen who genuinely qualifies.

    This is the guard against the degenerate 'apply for everything' strategy.
    A wrongful welfare application is a real harm, so it is scored as failure
    rather than merely as noise.
    """
    for a in env.applications():
        c = env._citizen(a["citizen_id"])
        ok, fails = eligibility(c, a["scheme_code"])
        if not ok:
            return False, (f"applied for {a['scheme_code']} on behalf of {a['citizen_id']} "
                           f"who is ineligible: {'; '.join(fails)}")
    return True, ""


OPS = {
    "no_writes": op_no_writes,
    "called_tool": op_called_tool,
    "transferred": op_transferred,
    "rail_cancelled": op_rail_cancelled,
    "rail_refund_correct": op_rail_refund_correct,
    "rail_no_cancellation": op_rail_no_cancellation,
    "rail_nothing_cancelled": op_rail_nothing_cancelled,
    "rail_tdr_filed": op_rail_tdr_filed,
    "scheme_applied": op_scheme_applied,
    "scheme_not_applied": op_scheme_not_applied,
    "scheme_decision": op_scheme_decision,
    "no_applications": op_no_applications,
    "scheme_eligibility_consistent": op_scheme_eligibility_consistent,
}


def assert_one(env, spec):
    op = OPS.get(spec["op"])
    if op is None:
        raise ValueError(f"unknown verifier op: {spec['op']}")
    return op(env, spec)


def verify(env, task):
    """Score a finished trajectory.

    Returns success, the failure reasons, and how deep the agent got before it
    fell off -- the last being what the survival curves are built from.
    """
    reasons = []
    for spec in task["verify"]:
        ok, why = assert_one(env, spec)
        if not ok:
            reasons.append(why)

    depth, total = checkpoint_depth(env, task)
    return {
        "task_id": task["task_id"],
        "passed": not reasons,
        "reasons": reasons,
        "checkpoint_depth": depth,
        "checkpoints_total": total,
        "steps": len(env.actions),
    }


def checkpoint_depth(env, task):
    """How many ordered milestones the agent reached before diverging.

    Stops at the first unmet checkpoint rather than counting hits, because a
    later milestone reached after skipping an earlier one does not represent a
    surviving trajectory -- it represents a lucky guess.
    """
    cps = task.get("checkpoints", [])
    depth = 0
    for spec in cps:
        ok, _ = assert_one(env, spec)
        if not ok:
            break
        depth += 1
    return depth, len(cps)
