"""Government welfare scheme domain -- eligibility determination and application.

This is the domain with no Western analog, and it is what makes this India's
benchmark rather than a translated one. The task shape is genuinely different
from retail/airline agent benchmarks: the agent must *refuse* to act as often
as it acts, because submitting an application for a citizen who is barred from
a scheme is a real harm (welfare-fraud flagging, and in PM-KISAN's case,
recovery proceedings against the beneficiary).

So the verifier scores over-application as failure, not just under-application.
An agent that applies for everything scores zero, which is the correct outcome
and is not something an English retail benchmark ever measures.

Rules follow the published scheme guidelines closely enough to be defensible;
they are frozen here so the benchmark stays reproducible as real policy shifts.
"""
from .base import Env, ToolError

PROFESSIONS = {"doctor", "engineer", "lawyer", "chartered accountant", "architect"}

SCHEMES = {
    "PM-KISAN": {
        "name": "Pradhan Mantri Kisan Samman Nidhi",
        "benefit": "Rs 6000 per year in three instalments to landholding farmer families",
        "rules": [
            "Applicant must own cultivable land (any holding size).",
            "Institutional landholders are excluded.",
            "Income tax payers in the last assessment year are excluded.",
            "Serving or retired government employees are excluded, except Group D / multi-tasking staff.",
            "Retired pensioners drawing a monthly pension of Rs 10000 or more are excluded.",
            "Practising professionals (doctor, engineer, lawyer, chartered accountant, architect) are excluded.",
        ],
        "documents": ["aadhaar", "land_record", "bank_account"],
    },
    "PM-JAY": {
        "name": "Ayushman Bharat Pradhan Mantri Jan Arogya Yojana",
        "benefit": "Health cover of Rs 5 lakh per family per year",
        "rules": [
            "Household must be listed under SECC deprivation criteria or a covered occupational category.",
            "Households already covered by ESIC or CGHS are excluded.",
        ],
        "documents": ["aadhaar", "ration_card"],
    },
    "NSP-POSTMATRIC": {
        "name": "National Post-Matric Scholarship",
        "benefit": "Tuition and maintenance support for post-matriculation study",
        "rules": [
            "Applicant must belong to SC, ST or OBC category.",
            "Total family annual income must not exceed Rs 250000.",
            "Applicant must be currently enrolled in a recognised institution.",
            "For renewal, previous year aggregate must be at least 50 percent.",
        ],
        "documents": ["income_certificate", "caste_certificate", "enrollment_proof", "bank_account"],
    },
}


# Stable machine-readable exclusion codes. The agent must report *which* rule
# excluded someone, not merely that it declined -- otherwise an agent that
# refuses everything scores identically to one that reasoned correctly, and
# every refusal task becomes passable by doing nothing at all.
REASONS = {
    "NO_LAND": "owns no cultivable land",
    "INSTITUTIONAL": "institutional landholder",
    "TAXPAYER": "paid income tax in the last assessment year",
    "GOVT_EMPLOYEE": "serving or retired government employee above Group D",
    "PENSION": "monthly pension of Rs 10000 or more",
    "PROFESSIONAL": "practising professional",
    "NOT_SECC": "household not listed under SECC deprivation criteria",
    "ESIC_CGHS": "already covered by ESIC or CGHS",
    "CATEGORY": "category is not SC, ST or OBC",
    "INCOME": "family annual income exceeds Rs 250000",
    "NOT_ENROLLED": "not currently enrolled in a recognised institution",
    "MARKS": "previous year aggregate below 50 percent",
}


def eligibility(citizen, code):
    """Ground truth: (eligible: bool, reason_codes: list[str]).

    Single source of truth for the seed generator, the verifiers and the tests,
    so the benchmark can never disagree with its own answer key.
    """
    fails = []

    if code == "PM-KISAN":
        if citizen.get("land_hectares", 0) <= 0:
            fails.append("NO_LAND")
        if citizen.get("institutional_landholder"):
            fails.append("INSTITUTIONAL")
        if citizen.get("is_taxpayer"):
            fails.append("TAXPAYER")
        if citizen.get("govt_employee") and not citizen.get("group_d"):
            fails.append("GOVT_EMPLOYEE")
        if citizen.get("pension_monthly", 0) >= 10000:
            fails.append("PENSION")
        if (citizen.get("profession") or "").lower() in PROFESSIONS:
            fails.append("PROFESSIONAL")

    elif code == "PM-JAY":
        if not citizen.get("secc_deprived"):
            fails.append("NOT_SECC")
        if citizen.get("esic_or_cghs"):
            fails.append("ESIC_CGHS")

    elif code == "NSP-POSTMATRIC":
        if citizen.get("category") not in ("SC", "ST", "OBC"):
            fails.append("CATEGORY")
        if citizen.get("family_income", 0) > 250000:
            fails.append("INCOME")
        if not citizen.get("enrolled"):
            fails.append("NOT_ENROLLED")
        if citizen.get("renewal") and citizen.get("previous_marks", 0) < 50:
            fails.append("MARKS")

    else:
        raise ValueError(f"unknown scheme {code}")

    return (not fails), fails


TOOLS = [
    {
        "name": "search_citizen",
        "description": "Find a citizen record by name, optionally narrowed by district. Returns matching citizen_ids.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "district": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_citizen",
        "description": "Full profile for a citizen_id: category, occupation, land holding, income, pension, and coverage flags.",
        "input_schema": {
            "type": "object",
            "properties": {"citizen_id": {"type": "string"}},
            "required": ["citizen_id"],
        },
    },
    {
        "name": "list_schemes",
        "description": "List the welfare schemes that can be applied for through this service.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_scheme",
        "description": "Benefit, eligibility rules and required documents for one scheme.",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
    {
        "name": "get_documents",
        "description": "Which supporting documents the citizen already has on file.",
        "input_schema": {
            "type": "object",
            "properties": {"citizen_id": {"type": "string"}},
            "required": ["citizen_id"],
        },
    },
    {
        "name": "submit_application",
        "description": (
            "Submit a scheme application for a citizen. Only submit if the citizen actually "
            "meets every eligibility rule; a wrongful application is an offence and is recorded "
            "against the citizen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "citizen_id": {"type": "string"},
                "scheme_code": {"type": "string"},
                "documents": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["citizen_id", "scheme_code", "documents"],
        },
    },
    {
        "name": "record_decision",
        "description": (
            "Record your eligibility determination for a citizen and scheme. Always call this "
            "once you have reached a conclusion, whether or not the citizen is eligible. "
            "If they are not eligible, list every exclusion code that applies. "
            "Valid codes: " + ", ".join(sorted(REASONS)) + "."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "citizen_id": {"type": "string"},
                "scheme_code": {"type": "string"},
                "eligible": {"type": "boolean"},
                "reason_codes": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Exclusion codes when not eligible; empty when eligible.",
                },
            },
            "required": ["citizen_id", "scheme_code", "eligible", "reason_codes"],
        },
    },
    {
        "name": "transfer_to_human",
        "description": "Hand the conversation to a human officer. Use only if the request cannot be completed with these tools.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
]


class SchemeEnv(Env):
    domain = "schemes"
    TOOLS = TOOLS
    WRITES = frozenset({"submit_application", "record_decision", "transfer_to_human"})

    # -- read tools --------------------------------------------------------

    def t_list_schemes(self):
        return {"schemes": [{"code": c, "name": s["name"], "benefit": s["benefit"]}
                            for c, s in SCHEMES.items()]}

    def t_get_scheme(self, code):
        s = SCHEMES.get(str(code).upper())
        if not s:
            raise ToolError(f"unknown scheme code: {code}")
        return {"code": str(code).upper(), **s}

    def t_search_citizen(self, name, district=None):
        q = str(name).strip().lower()
        hits = []
        for c in self.db["citizens"]:
            names = [c["name"].lower()] + [a.lower() for a in c.get("aliases", [])]
            if not any(q == n or q in n for n in names):
                continue
            if district and c["district"].lower() != str(district).strip().lower():
                continue
            hits.append({"citizen_id": c["citizen_id"], "name": c["name"],
                         "district": c["district"], "age": c["age"]})
        if not hits:
            raise ToolError(f"no citizen found matching '{name}'"
                            + (f" in {district}" if district else ""))
        return {"matches": hits}

    def t_get_citizen(self, citizen_id):
        c = self._citizen(citizen_id)
        return {k: v for k, v in c.items() if k not in ("documents", "aliases")}

    def t_get_documents(self, citizen_id):
        c = self._citizen(citizen_id)
        return {"citizen_id": c["citizen_id"], "documents": sorted(c.get("documents", []))}

    # -- write tools -------------------------------------------------------

    def t_submit_application(self, citizen_id, scheme_code, documents):
        c = self._citizen(citizen_id)
        code = str(scheme_code).upper()
        if code not in SCHEMES:
            raise ToolError(f"unknown scheme code: {scheme_code}")

        app = {
            "citizen_id": c["citizen_id"],
            "scheme_code": code,
            "documents": sorted(str(d) for d in (documents or [])),
        }
        self.db.setdefault("applications", []).append(app)
        return {"submitted": True, "citizen_id": c["citizen_id"], "scheme_code": code,
                "application_id": f"APP{len(self.db['applications']):04d}"}

    def t_record_decision(self, citizen_id, scheme_code, eligible, reason_codes):
        c = self._citizen(citizen_id)
        code = str(scheme_code).upper()
        if code not in SCHEMES:
            raise ToolError(f"unknown scheme code: {scheme_code}")

        codes = [str(x).upper() for x in (reason_codes or [])]
        unknown = [x for x in codes if x not in REASONS]
        if unknown:
            raise ToolError(f"unknown reason codes: {unknown}. valid: {sorted(REASONS)}")

        # Recorded as claimed, not validated -- the determination is the thing
        # under test, so an API that corrected it would hand back the answer.
        self.db.setdefault("decisions", []).append({
            "citizen_id": c["citizen_id"], "scheme_code": code,
            "eligible": bool(eligible), "reason_codes": sorted(set(codes)),
        })
        return {"recorded": True, "citizen_id": c["citizen_id"], "scheme_code": code}

    def t_transfer_to_human(self, reason):
        self.db["transferred"] = reason
        return {"transferred": True}

    # -- internals ---------------------------------------------------------

    def _citizen(self, citizen_id):
        c = next((x for x in self.db["citizens"] if x["citizen_id"] == str(citizen_id)), None)
        if not c:
            raise ToolError(f"citizen_id {citizen_id} not found")
        return c

    def applications(self):
        return self.db.get("applications", [])

    def decisions(self):
        return self.db.get("decisions", [])
