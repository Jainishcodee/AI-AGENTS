"""Rail domain -- booking, cancellation and refund against IRCTC-style rules.

This domain exists as the *control*. It parallels the airline domain in
tau2-bench, so English-condition results here can be sanity-checked against
published English agent numbers. If our C1 scores land nowhere near that band,
the harness is broken and no cross-language claim from it is trustworthy.

The refund rules are the real IRCTC slabs. They are worth reproducing exactly
because they force a genuine multi-step chain -- find booking, read departure,
compute the time delta, pick the slab, apply the per-class floor, add GST on AC
classes, subtract -- which is precisely the kind of reasoning we expect to
degrade under romanized input.
"""
from datetime import datetime

from .base import Env, ToolError

# Flat per-passenger cancellation charge by class, in rupees. Also the floor
# that the 25%/50% slabs are clamped up to.
FLAT = {
    "1A": 240, "EC": 240,
    "2A": 200, "FC": 200,
    "3A": 180, "3E": 180, "CC": 180,
    "SL": 120,
    "2S": 60,
}

# GST is levied on the cancellation charge for air-conditioned classes only.
AC_CLASSES = {"1A", "EC", "2A", "3A", "3E", "CC"}
GST_RATE = 0.05

# Clerkage deducted per passenger when cancelling a non-confirmed (RAC/WL) berth.
CLERKAGE = 60

TS = "%Y-%m-%d %H:%M"


def parse(ts):
    return datetime.strptime(ts, TS)


def refund_for(passenger, klass, fare, hours_left, train_cancelled=False):
    """Ground-truth refund for one passenger. Pure function, no state.

    Verifiers and the seed generator both call this, so the rules live in
    exactly one place and the benchmark can never disagree with itself.
    """
    # The berth status *as booked*, never the live one. Reading `status` here
    # would be a silent correctness bug: cancelling flips it to CANCELLED, so a
    # waitlisted berth would stop looking waitlisted and the answer key would
    # change the moment the agent acted on it.
    status = passenger.get("booked_status", passenger["status"])

    # Railways cancelled the train: full refund, no deduction, any time.
    if train_cancelled:
        return fare

    # RAC / waitlisted berths are refunded minus clerkage, not the slab.
    if status in ("RAC", "WL"):
        if hours_left < 0.5:
            return 0
        return max(0, fare - CLERKAGE)

    # Confirmed berths follow the time slabs.
    if hours_left <= 4:
        return 0
    flat = FLAT[klass]
    if hours_left > 48:
        charge = flat
    elif hours_left > 12:
        charge = max(flat, 0.25 * fare)
    else:
        charge = max(flat, 0.50 * fare)

    if klass in AC_CLASSES:
        charge += charge * GST_RATE

    return max(0, int(round(fare - charge)))


TOOLS = [
    {
        "name": "list_bookings",
        "description": "Find all bookings belonging to a passenger's registered mobile number.",
        "input_schema": {
            "type": "object",
            "properties": {"phone": {"type": "string", "description": "10-digit mobile number"}},
            "required": ["phone"],
        },
    },
    {
        "name": "get_booking",
        "description": "Full details of one booking: train, class, fare per passenger, and the passenger list with berth status.",
        "input_schema": {
            "type": "object",
            "properties": {"pnr": {"type": "string"}},
            "required": ["pnr"],
        },
    },
    {
        "name": "get_train",
        "description": "Train details including scheduled departure and whether the railways have cancelled it.",
        "input_schema": {
            "type": "object",
            "properties": {"train_no": {"type": "string"}},
            "required": ["train_no"],
        },
    },
    {
        "name": "current_time",
        "description": "The current date and time, for computing how long remains before departure.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancel_passengers",
        "description": (
            "Cancel specific passengers on a booking and record the refund you have calculated. "
            "Pass the passenger_ids to cancel and the total refund in rupees across those passengers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pnr": {"type": "string"},
                "passenger_ids": {"type": "array", "items": {"type": "integer"}},
                "refund_amount": {"type": "integer", "description": "Total refund in whole rupees"},
            },
            "required": ["pnr", "passenger_ids", "refund_amount"],
        },
    },
    {
        "name": "file_tdr",
        "description": "File a Ticket Deposit Receipt claim, used when the railways cancelled the train.",
        "input_schema": {
            "type": "object",
            "properties": {"pnr": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["pnr", "reason"],
        },
    },
    {
        "name": "transfer_to_human",
        "description": "Hand the conversation to a human agent. Use only if the request cannot be completed with these tools.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
]


class RailEnv(Env):
    domain = "rail"
    TOOLS = TOOLS
    WRITES = frozenset({"cancel_passengers", "file_tdr", "transfer_to_human"})

    def __init__(self, db):
        super().__init__(db)
        # Freeze the as-booked berth status so the refund rules stay stable
        # once the agent starts mutating the booking. Done here rather than in
        # the seed file so a hand-added booking can never forget it.
        for b in self.db["bookings"]:
            for p in b["passengers"]:
                p.setdefault("booked_status", p["status"])

    # -- read tools --------------------------------------------------------

    def t_current_time(self):
        return {"now": self.db["now"]}

    def t_list_bookings(self, phone):
        hits = [
            {"pnr": b["pnr"], "train_no": b["train_no"], "date": b["date"],
             "class": b["class"], "status": b["status"]}
            for b in self.db["bookings"] if b["phone"] == str(phone)
        ]
        if not hits:
            raise ToolError(f"no bookings found for mobile {phone}")
        return {"bookings": hits}

    def t_get_booking(self, pnr):
        b = self._booking(pnr)
        return {
            "pnr": b["pnr"], "train_no": b["train_no"], "date": b["date"],
            "class": b["class"], "status": b["status"],
            "fare_per_passenger": b["fare_per_passenger"],
            "boarding": b["boarding"], "destination": b["destination"],
            "passengers": b["passengers"],
        }

    def t_get_train(self, train_no):
        t = self.db["trains"].get(str(train_no))
        if not t:
            raise ToolError(f"train {train_no} not found")
        return t

    # -- write tools -------------------------------------------------------

    def t_cancel_passengers(self, pnr, passenger_ids, refund_amount):
        b = self._booking(pnr)
        if b["status"] == "CANCELLED":
            raise ToolError(f"booking {pnr} is already fully cancelled")

        ids = list(passenger_ids or [])
        if not ids:
            raise ToolError("passenger_ids must not be empty")

        known = {p["id"] for p in b["passengers"]}
        unknown = [i for i in ids if i not in known]
        if unknown:
            raise ToolError(f"passenger_ids {unknown} are not on booking {pnr}")

        already = [i for i in ids
                   if next(p for p in b["passengers"] if p["id"] == i)["status"] == "CANCELLED"]
        if already:
            raise ToolError(f"passengers {already} are already cancelled")

        for p in b["passengers"]:
            if p["id"] in ids:
                p["status"] = "CANCELLED"
        if all(p["status"] == "CANCELLED" for p in b["passengers"]):
            b["status"] = "CANCELLED"

        # The claimed refund is recorded, not validated. The agent's arithmetic
        # is the thing under test; a validating API would hand back the answer.
        b.setdefault("refunds", []).append(
            {"passenger_ids": sorted(ids), "amount": int(refund_amount)}
        )
        return {"pnr": pnr, "cancelled": sorted(ids),
                "refund_recorded": int(refund_amount), "booking_status": b["status"]}

    def t_file_tdr(self, pnr, reason):
        b = self._booking(pnr)
        b.setdefault("tdr", []).append({"reason": reason})
        return {"pnr": pnr, "tdr_filed": True}

    def t_transfer_to_human(self, reason):
        self.db["transferred"] = reason
        return {"transferred": True}

    # -- internals ---------------------------------------------------------

    def _booking(self, pnr):
        b = next((x for x in self.db["bookings"] if x["pnr"] == str(pnr)), None)
        if not b:
            raise ToolError(f"PNR {pnr} not found")
        return b

    def hours_left(self, pnr):
        b = self._booking(pnr)
        train = self.db["trains"][b["train_no"]]
        dep = parse(f"{b['date']} {train['departure']}")
        return (dep - parse(self.db["now"])).total_seconds() / 3600.0

    def expected_refund(self, pnr, passenger_ids):
        """Ground truth for a cancellation, used by verifiers and tests."""
        b = self._booking(pnr)
        train = self.db["trains"][b["train_no"]]
        hrs = self.hours_left(pnr)
        total = 0
        for p in b["passengers"]:
            if p["id"] in passenger_ids:
                total += refund_for(p, b["class"], b["fare_per_passenger"], hrs,
                                    train_cancelled=train.get("cancelled", False))
        return total
