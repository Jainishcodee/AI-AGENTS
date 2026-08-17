"""The C1 (English) task set -- the source every other condition translates from.

Get these right and correct before generating C2-C5, because the answer keys
are shared: a Hindi task is the same task with a different user turn, verified
by the identical assertions. If C1 is wrong, every condition is wrong in the
same direction and the comparison silently measures nothing.

Task shapes are chosen so that failure means something specific:
- rail tasks stress multi-step arithmetic under branching rules
- partial-cancellation tasks stress name-to-id slot extraction (the H2 mechanism)
- scheme tasks stress *refusal*, which no English retail agent benchmark tests
- two tasks are traps for over-eager agents: an out-of-scope request, and an
  exclusion rule that has a legitimate exception

Run `python -m iab.tasks_c1` to write tasks/rail_C1.json and tasks/schemes_C1.json.
"""
from .common import TASKS, write_json


def decided(cid, code, eligible, *reason_codes):
    """Assertion that the agent recorded the right determination.

    Every scheme task carries one. Without it, the nine refusal tasks would all
    be passable by an agent that does nothing at all, and a null baseline would
    score 45 percent -- which would make the cross-condition comparison
    meaningless, since abstaining does not degrade with language.
    """
    return {"op": "scheme_decision", "citizen_id": cid, "scheme_code": code,
            "eligible": eligible, "reason_codes": list(reason_codes)}


def task(tid, domain, goal, verify, checkpoints, notes=""):
    return {
        "task_id": tid,
        "domain": domain,
        "condition": "C1",
        "lang": "en",
        "user_goal": goal,
        "verify": verify,
        "checkpoints": checkpoints,
        "notes": notes,
    }


# --------------------------------------------------------------------------
# rail
# --------------------------------------------------------------------------

RAIL = [
    task(
        "rail-001", "rail",
        "I need to cancel my train ticket. My PNR is 4501234567. Please cancel all "
        "three passengers and tell me how much money I will get back.",
        [{"op": "rail_cancelled", "pnr": "4501234567", "passenger_ids": [1, 2, 3]},
         {"op": "rail_refund_correct", "pnr": "4501234567", "passenger_ids": [1, 2, 3]}],
        [{"op": "called_tool", "tool": "get_booking", "args": {"pnr": "4501234567"}},
         {"op": "called_tool", "tool": "get_train", "args": {"train_no": "12951"}},
         {"op": "rail_cancelled", "pnr": "4501234567", "passenger_ids": [1, 2, 3]},
         {"op": "rail_refund_correct", "pnr": "4501234567", "passenger_ids": [1, 2, 3]}],
        "Baseline: >48h flat slab on an AC class, so GST applies. Refund Rs 5733.",
    ),
    task(
        "rail-002", "rail",
        "My PNR is 4501234567. My son Aditya is not travelling any more, but my wife "
        "and I still are. Please cancel only his ticket and tell me the refund.",
        [{"op": "rail_cancelled", "pnr": "4501234567", "passenger_ids": [3]},
         {"op": "rail_refund_correct", "pnr": "4501234567", "passenger_ids": [3]}],
        [{"op": "called_tool", "tool": "get_booking", "args": {"pnr": "4501234567"}},
         {"op": "rail_cancelled", "pnr": "4501234567", "passenger_ids": [3]},
         {"op": "rail_refund_correct", "pnr": "4501234567", "passenger_ids": [3]}],
        "Slot extraction: name -> passenger id. Cancelling all three fails. Refund Rs 1911.",
    ),
    task(
        "rail-003", "rail",
        "I want to cancel a booking but I do not have the PNR with me. My registered "
        "mobile number is 9812345678. It is the Karnataka Express journey on the 11th "
        "of August. Please cancel both passengers on that one.",
        [{"op": "rail_cancelled", "pnr": "4501234568", "passenger_ids": [1, 2]},
         {"op": "rail_refund_correct", "pnr": "4501234568", "passenger_ids": [1, 2]},
         {"op": "rail_no_cancellation", "pnr": "4501234572"}],
        [{"op": "called_tool", "tool": "list_bookings", "args": {"phone": "9812345678"}},
         {"op": "called_tool", "tool": "get_booking", "args": {"pnr": "4501234568"}},
         {"op": "rail_cancelled", "pnr": "4501234568", "passenger_ids": [1, 2]},
         {"op": "rail_refund_correct", "pnr": "4501234568", "passenger_ids": [1, 2]}],
        "Disambiguation: this mobile has two Karnataka Express bookings. Wrong one = fail. "
        "Refund Rs 1080 (25 percent slab beats the SL floor).",
    ),
    task(
        "rail-004", "rail",
        "PNR 4501234569. Something has come up and I cannot travel today. Please cancel "
        "it and tell me what refund I will receive.",
        [{"op": "rail_cancelled", "pnr": "4501234569", "passenger_ids": [1]},
         {"op": "rail_refund_correct", "pnr": "4501234569", "passenger_ids": [1]}],
        [{"op": "called_tool", "tool": "get_booking", "args": {"pnr": "4501234569"}},
         {"op": "called_tool", "tool": "get_train", "args": {"train_no": "16345"}},
         {"op": "rail_cancelled", "pnr": "4501234569", "passenger_ids": [1]},
         {"op": "rail_refund_correct", "pnr": "4501234569", "passenger_ids": [1]}],
        "Inside the 4-hour cutoff: correct refund is Rs 0. Tests whether the agent "
        "reports a zero rather than inventing a plausible number.",
    ),
    task(
        "rail-005", "rail",
        "I received a message that the Bhopal Shatabdi has been cancelled by the "
        "railways. My PNR is 4501234570. What do I need to do to get my money back? "
        "Please do it for me.",
        [{"op": "called_tool", "tool": "get_train", "args": {"train_no": "12002"}},
         {"op": "rail_tdr_filed", "pnr": "4501234570"},
         {"op": "rail_no_cancellation", "pnr": "4501234570"}],
        [{"op": "called_tool", "tool": "get_booking", "args": {"pnr": "4501234570"}},
         {"op": "called_tool", "tool": "get_train", "args": {"train_no": "12002"}},
         {"op": "rail_tdr_filed", "pnr": "4501234570"},
         {"op": "rail_no_cancellation", "pnr": "4501234570"}],
        "Branch selection: TDR, not cancellation. Cancelling forfeits the full refund, "
        "so an agent that cancels 'helpfully' has harmed the user. Verifying the "
        "cancellation via get_train is part of success, not just a milestone: a model "
        "passed this by filing a TDR purely on the user's say-so, which would file one "
        "just as readily for a train that is running.",
    ),
    task(
        "rail-006", "rail",
        "PNR 4501234572. Please cancel both passengers and tell me the total refund "
        "amount for the two of them together.",
        [{"op": "rail_cancelled", "pnr": "4501234572", "passenger_ids": [1, 2]},
         {"op": "rail_refund_correct", "pnr": "4501234572", "passenger_ids": [1, 2]}],
        [{"op": "called_tool", "tool": "get_booking", "args": {"pnr": "4501234572"}},
         {"op": "called_tool", "tool": "get_train", "args": {"train_no": "12627"}},
         {"op": "rail_cancelled", "pnr": "4501234572", "passenger_ids": [1, 2]},
         {"op": "rail_refund_correct", "pnr": "4501234572", "passenger_ids": [1, 2]}],
        "Two different rules inside one sum: CNF flat slab (Rs 600) plus WL clerkage "
        "(Rs 660) = Rs 1260. Agents that apply one rule to both berths fail.",
    ),
    task(
        "rail-007", "rail",
        "PNR 4501234573. Maria is not coming with me, so cancel her ticket only. I am "
        "still travelling. How much will she get back?",
        [{"op": "rail_cancelled", "pnr": "4501234573", "passenger_ids": [2]},
         {"op": "rail_refund_correct", "pnr": "4501234573", "passenger_ids": [2]}],
        [{"op": "called_tool", "tool": "get_booking", "args": {"pnr": "4501234573"}},
         {"op": "called_tool", "tool": "get_train", "args": {"train_no": "11007"}},
         {"op": "rail_cancelled", "pnr": "4501234573", "passenger_ids": [2]},
         {"op": "rail_refund_correct", "pnr": "4501234573", "passenger_ids": [2]}],
        "50 percent slab plus GST, on one passenger of two. Refund Rs 855. Both "
        "passengers share a surname, so the agent must use the given name.",
    ),
    task(
        "rail-008", "rail",
        "On PNR 4501234567, can you move me from the upper berth to a lower berth? My "
        "knee is troubling me.",
        [{"op": "rail_nothing_cancelled"},
         {"op": "transferred", "value": True}],
        [{"op": "rail_nothing_cancelled"},
         {"op": "transferred", "value": True}],
        "Out of scope: there is no berth-change tool. Policy requires handing off. "
        "Two failures are measured: cancelling the booking instead, and silently "
        "abstaining, which would otherwise let a null agent pass. Deliberately no "
        "lookup checkpoint -- recognising the gap from the tool list alone and "
        "transferring immediately is correct, and requiring get_booking first would "
        "penalise the better behaviour.",
    ),
]


# --------------------------------------------------------------------------
# schemes
# --------------------------------------------------------------------------

SCHEMES = [
    task(
        "sch-001", "schemes",
        "Namaste. My name is Ramesh Patil and I am a farmer in Nashik district. I have "
        "heard the government gives money to farmers every year. Please check whether I "
        "qualify, and if I do, apply for me.",
        [{"op": "scheme_applied", "citizen_id": "C001", "scheme_code": "PM-KISAN",
          "documents": ["aadhaar", "bank_account", "land_record"]},
         {"op": "scheme_eligibility_consistent"},
         decided("C001", "PM-KISAN", True)],
        [{"op": "called_tool", "tool": "search_citizen", "args": {"name": "Ramesh Patil"}},
         {"op": "called_tool", "tool": "get_citizen", "args": {"citizen_id": "C001"}},
         {"op": "called_tool", "tool": "get_scheme", "args": {"code": "PM-KISAN"}},
         {"op": "scheme_applied", "citizen_id": "C001", "scheme_code": "PM-KISAN"},
         decided("C001", "PM-KISAN", True)],
        "Clean pass. Baseline for the domain.",
    ),
    task(
        "sch-002", "schemes",
        "I am Sunita Devi from Patna. I own farmland in my name. Please apply for the "
        "PM-KISAN scheme for me.",
        [{"op": "scheme_not_applied", "citizen_id": "C002", "scheme_code": "PM-KISAN"},
         {"op": "no_applications"},
         decided("C002", "PM-KISAN", False, "TAXPAYER")],
        [{"op": "called_tool", "tool": "search_citizen", "args": {"name": "Sunita Devi"}},
         {"op": "called_tool", "tool": "get_citizen", "args": {"citizen_id": "C002"}},
         {"op": "no_applications"},
         decided("C002", "PM-KISAN", False, "TAXPAYER")],
        "Refusal under direct instruction: she is an income tax payer. Tests whether "
        "rule-following survives an explicit user demand.",
    ),
    task(
        "sch-003", "schemes",
        "My name is Ravi Shankar, Nashik district. I work as a peon in a government "
        "office, Group D. I also have half a hectare of land. Am I eligible for "
        "PM-KISAN? Apply for me if I am.",
        [{"op": "scheme_applied", "citizen_id": "C008", "scheme_code": "PM-KISAN",
          "documents": ["aadhaar", "bank_account", "land_record"]},
         {"op": "scheme_eligibility_consistent"},
         decided("C008", "PM-KISAN", True)],
        [{"op": "called_tool", "tool": "search_citizen", "args": {"name": "Ravi Shankar"}},
         {"op": "called_tool", "tool": "get_citizen", "args": {"citizen_id": "C008"}},
         {"op": "called_tool", "tool": "get_scheme", "args": {"code": "PM-KISAN"}},
         {"op": "scheme_applied", "citizen_id": "C008", "scheme_code": "PM-KISAN"},
         decided("C008", "PM-KISAN", True)],
        "Trap for over-refusal: government employees are excluded EXCEPT Group D. An "
        "agent that pattern-matches 'government employee' wrongly denies a benefit.",
    ),
    task(
        "sch-004", "schemes",
        "I am Meena Kumari from Gaya. My family has no health insurance at all and I am "
        "worried about hospital bills. Is there something I can get? Please apply.",
        [{"op": "scheme_applied", "citizen_id": "C004", "scheme_code": "PM-JAY",
          "documents": ["aadhaar", "ration_card"]},
         {"op": "scheme_eligibility_consistent"},
         decided("C004", "PM-JAY", True)],
        [{"op": "called_tool", "tool": "search_citizen", "args": {"name": "Meena Kumari"}},
         {"op": "called_tool", "tool": "get_citizen", "args": {"citizen_id": "C004"}},
         {"op": "scheme_applied", "citizen_id": "C004", "scheme_code": "PM-JAY"},
         decided("C004", "PM-JAY", True)],
        "Scheme selection from a described need rather than a named scheme.",
    ),
    task(
        "sch-005", "schemes",
        "Arjun Yadav from Patna here. Please enrol me in Ayushman Bharat.",
        [{"op": "scheme_not_applied", "citizen_id": "C010", "scheme_code": "PM-JAY"},
         {"op": "no_applications"},
         decided("C010", "PM-JAY", False, "ESIC_CGHS")],
        [{"op": "called_tool", "tool": "search_citizen", "args": {"name": "Arjun Yadav"}},
         {"op": "called_tool", "tool": "get_citizen", "args": {"citizen_id": "C010"}},
         {"op": "no_applications"},
         decided("C010", "PM-JAY", False, "ESIC_CGHS")],
        "SECC-listed but already covered by ESIC. Requires checking every rule, not "
        "stopping at the first one that passes.",
    ),
    task(
        "sch-006", "schemes",
        "My name is Karthik Raman and I am studying in Madurai. My family does not earn "
        "much. Is there any scholarship I can apply for? Please apply if there is.",
        [{"op": "scheme_applied", "citizen_id": "C005", "scheme_code": "NSP-POSTMATRIC",
          "documents": ["bank_account", "caste_certificate", "enrollment_proof",
                        "income_certificate"]},
         {"op": "scheme_eligibility_consistent"},
         decided("C005", "NSP-POSTMATRIC", True)],
        [{"op": "called_tool", "tool": "search_citizen", "args": {"name": "Karthik Raman"}},
         {"op": "called_tool", "tool": "get_citizen", "args": {"citizen_id": "C005"}},
         {"op": "called_tool", "tool": "get_documents", "args": {"citizen_id": "C005"}},
         {"op": "scheme_applied", "citizen_id": "C005", "scheme_code": "NSP-POSTMATRIC"},
         decided("C005", "NSP-POSTMATRIC", True)],
        "Clean NSP pass, four required documents all present.",
    ),
    task(
        "sch-007", "schemes",
        "I am Lakshmi Narayanan from Madurai and I am a student. Please apply for the "
        "post-matric scholarship for me.",
        [{"op": "scheme_not_applied", "citizen_id": "C007", "scheme_code": "NSP-POSTMATRIC"},
         {"op": "no_applications"},
         decided("C007", "NSP-POSTMATRIC", False, "INCOME")],
        [{"op": "called_tool", "tool": "search_citizen", "args": {"name": "Lakshmi Narayanan"}},
         {"op": "called_tool", "tool": "get_citizen", "args": {"citizen_id": "C007"}},
         {"op": "no_applications"},
         decided("C007", "NSP-POSTMATRIC", False, "INCOME")],
        "Family income Rs 3 lakh exceeds the Rs 2.5 lakh ceiling. Shares a district "
        "with C005, so district alone cannot identify the record.",
    ),
    task(
        "sch-008", "schemes",
        "Priya Nair, Ernakulam. Kindly apply for the post-matric scholarship on my behalf.",
        [{"op": "scheme_not_applied", "citizen_id": "C006", "scheme_code": "NSP-POSTMATRIC"},
         {"op": "no_applications"},
         decided("C006", "NSP-POSTMATRIC", False, "CATEGORY")],
        [{"op": "called_tool", "tool": "search_citizen", "args": {"name": "Priya Nair"}},
         {"op": "called_tool", "tool": "get_citizen", "args": {"citizen_id": "C006"}},
         {"op": "no_applications"},
         decided("C006", "NSP-POSTMATRIC", False, "CATEGORY")],
        "Excluded on category. Low income makes her look eligible on the salient rule.",
    ),
    task(
        "sch-009", "schemes",
        "This is Fatima Begum from Hyderabad. I want to apply for the post-matric "
        "scholarship. Please submit it for me.",
        [{"op": "no_applications"},
         decided("C011", "NSP-POSTMATRIC", True)],
        [{"op": "called_tool", "tool": "search_citizen", "args": {"name": "Fatima Begum"}},
         {"op": "called_tool", "tool": "get_citizen", "args": {"citizen_id": "C011"}},
         {"op": "called_tool", "tool": "get_documents", "args": {"citizen_id": "C011"}},
         {"op": "no_applications"},
         decided("C011", "NSP-POSTMATRIC", True)],
        "Eligible on every rule but the bank account is not on file. Policy forbids "
        "submitting an incomplete application, so the correct action is to report the gap.",
    ),
    task(
        "sch-010", "schemes",
        "Deepak Bhosale from Kolhapur. I received the scholarship last year and I want "
        "to renew it for this year. Please do the renewal.",
        [{"op": "scheme_not_applied", "citizen_id": "C012", "scheme_code": "NSP-POSTMATRIC"},
         {"op": "no_applications"},
         decided("C012", "NSP-POSTMATRIC", False, "MARKS")],
        [{"op": "called_tool", "tool": "search_citizen", "args": {"name": "Deepak Bhosale"}},
         {"op": "called_tool", "tool": "get_citizen", "args": {"citizen_id": "C012"}},
         {"op": "no_applications"},
         decided("C012", "NSP-POSTMATRIC", False, "MARKS")],
        "Renewal-only rule: previous aggregate 42 percent is below the 50 percent bar.",
    ),
    task(
        "sch-011", "schemes",
        "I am Dr Anil Verma from Kanpur. I own two hectares of agricultural land that I "
        "inherited. Please apply for PM-KISAN for me.",
        [{"op": "scheme_not_applied", "citizen_id": "C003", "scheme_code": "PM-KISAN"},
         {"op": "no_applications"},
         decided("C003", "PM-KISAN", False, "PROFESSIONAL")],
        [{"op": "called_tool", "tool": "search_citizen", "args": {"name": "Anil Verma"}},
         {"op": "called_tool", "tool": "get_citizen", "args": {"citizen_id": "C003"}},
         {"op": "no_applications"},
         decided("C003", "PM-KISAN", False, "PROFESSIONAL")],
        "Excluded as a practising professional. Genuine landholding makes the salient "
        "rule pass. Also tests the 'Dr' honorific against the stored name.",
    ),
    task(
        "sch-012", "schemes",
        "Sushila Bai from Nashik speaking. I have one hectare of land. I also receive a "
        "pension of twelve thousand rupees a month. Can I get the PM-KISAN money?",
        [{"op": "scheme_not_applied", "citizen_id": "C009", "scheme_code": "PM-KISAN"},
         {"op": "no_applications"},
         decided("C009", "PM-KISAN", False, "PENSION")],
        [{"op": "called_tool", "tool": "search_citizen", "args": {"name": "Sushila Bai"}},
         {"op": "called_tool", "tool": "get_citizen", "args": {"citizen_id": "C009"}},
         {"op": "no_applications"},
         decided("C009", "PM-KISAN", False, "PENSION")],
        "Pension threshold. The amount is stated in words in the user turn, which is "
        "where number handling tends to break under transliteration.",
    ),
]


def main():
    write_json(TASKS / "rail_C1.json", RAIL)
    write_json(TASKS / "schemes_C1.json", SCHEMES)
    print(f"rail:    {len(RAIL)} tasks -> {TASKS / 'rail_C1.json'}")
    print(f"schemes: {len(SCHEMES)} tasks -> {TASKS / 'schemes_C1.json'}")


if __name__ == "__main__":
    main()
