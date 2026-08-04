"""Deterministic seed databases for both domains.

Run `python -m iab.seed` to regenerate data/rail.json and data/schemes.json.

The seeds are hand-designed rather than random: every refund slab and every
eligibility exclusion has at least one record that lands on it, including the
awkward ones (Group D government employee who *is* eligible for PM-KISAN,
mixed CNF/WL booking, train cancelled by the railways). Random seeds would
cover the easy middle and miss exactly the cases where agents break.

Passenger and citizen names are deliberately drawn from several Indian
naming traditions, because romanized-name handling is the mechanism H2
predicts will fail, and a seed full of "John Smith" would test nothing.
"""
from .common import DATA, write_json

NOW = "2026-08-10 09:00"

TRAINS = {
    "12951": {"train_no": "12951", "name": "Mumbai Rajdhani", "departure": "16:30", "cancelled": False},
    "12627": {"train_no": "12627", "name": "Karnataka Express", "departure": "20:15", "cancelled": False},
    "16345": {"train_no": "16345", "name": "Netravati Express", "departure": "11:40", "cancelled": False},
    "12002": {"train_no": "12002", "name": "Bhopal Shatabdi", "departure": "06:00", "cancelled": True},
    "17221": {"train_no": "17221", "name": "Kakinada Express", "departure": "23:50", "cancelled": False},
    "11007": {"train_no": "11007", "name": "Deccan Express", "departure": "18:00", "cancelled": False},
}


def pax(pid, name, age, status="CNF"):
    return {"id": pid, "name": name, "age": age, "status": status}


BOOKINGS = [
    # >48h before departure -> flat charge only. 3A is AC, so GST applies.
    {"pnr": "4501234567", "phone": "9876543210", "train_no": "12951", "date": "2026-08-14",
     "class": "3A", "status": "CONFIRMED", "fare_per_passenger": 2100,
     "boarding": "Mumbai Central", "destination": "New Delhi",
     "passengers": [pax(1, "Ramesh Kumar", 54), pax(2, "Lakshmi Kumar", 49),
                    pax(3, "Aditya Kumar", 21)]},

    # 35.25h -> 25% slab, and 25% of 720 (180) beats the SL floor of 120.
    {"pnr": "4501234568", "phone": "9812345678", "train_no": "12627", "date": "2026-08-11",
     "class": "SL", "status": "CONFIRMED", "fare_per_passenger": 720,
     "boarding": "Pune Junction", "destination": "Bengaluru",
     "passengers": [pax(1, "Shabnam Sheikh", 33), pax(2, "Imran Sheikh", 36)]},

    # 2.67h -> inside the 4h cutoff, confirmed berths get nothing.
    {"pnr": "4501234569", "phone": "9900112233", "train_no": "16345", "date": "2026-08-10",
     "class": "2A", "status": "CONFIRMED", "fare_per_passenger": 3200,
     "boarding": "Mangaluru", "destination": "Mumbai",
     "passengers": [pax(1, "Joseph D'Souza", 61)]},

    # Railways cancelled the train -> full refund regardless of timing, via TDR.
    {"pnr": "4501234570", "phone": "9765432109", "train_no": "12002", "date": "2026-08-12",
     "class": "CC", "status": "CONFIRMED", "fare_per_passenger": 1450,
     "boarding": "New Delhi", "destination": "Bhopal",
     "passengers": [pax(1, "Neha Agarwal", 29), pax(2, "Vikram Agarwal", 31)]},

    # 14.83h -> 25% slab on a 1A fare, where the percentage dwarfs the floor.
    {"pnr": "4501234571", "phone": "9123456780", "train_no": "17221", "date": "2026-08-10",
     "class": "1A", "status": "CONFIRMED", "fare_per_passenger": 4800,
     "boarding": "Secunderabad", "destination": "Kakinada",
     "passengers": [pax(1, "Padmavathi Rao", 58)]},

    # Mixed CNF + WL on one PNR: the two berths refund under different rules.
    {"pnr": "4501234572", "phone": "9812345678", "train_no": "12627", "date": "2026-08-13",
     "class": "SL", "status": "CONFIRMED", "fare_per_passenger": 720,
     "boarding": "Pune Junction", "destination": "Bengaluru",
     "passengers": [pax(1, "Gurpreet Singh", 44), pax(2, "Harleen Kaur", 40, status="WL")]},

    # 9h -> 50% slab, 3A so GST rides on top of the percentage charge.
    {"pnr": "4501234573", "phone": "9900112233", "train_no": "11007", "date": "2026-08-10",
     "class": "3A", "status": "CONFIRMED", "fare_per_passenger": 1800,
     "boarding": "Mumbai CSMT", "destination": "Pune Junction",
     "passengers": [pax(1, "Joseph D'Souza", 61), pax(2, "Maria D'Souza", 57)]},
]


def citizen(cid, name, district, state, age, **kw):
    base = {
        "citizen_id": cid, "name": name, "district": district, "state": state, "age": age,
        "category": "GEN", "profession": None, "land_hectares": 0.0,
        "institutional_landholder": False, "is_taxpayer": False, "govt_employee": False,
        "group_d": False, "pension_monthly": 0, "secc_deprived": False,
        "esic_or_cghs": False, "family_income": 0, "enrolled": False,
        "renewal": False, "previous_marks": 0, "aliases": [], "documents": [],
    }
    base.update(kw)
    return base


CITIZENS = [
    # PM-KISAN: clean pass.
    citizen("C001", "Ramesh Patil", "Nashik", "Maharashtra", 52,
            land_hectares=1.2, aliases=["Ramesh Bhau Patil"],
            documents=["aadhaar", "land_record", "bank_account"]),

    # PM-KISAN: excluded as an income tax payer, despite holding land.
    citizen("C002", "Sunita Devi", "Patna", "Bihar", 47,
            land_hectares=0.8, is_taxpayer=True,
            documents=["aadhaar", "land_record", "bank_account"]),

    # PM-KISAN: excluded as a practising professional.
    citizen("C003", "Anil Verma", "Kanpur", "Uttar Pradesh", 45,
            land_hectares=2.0, profession="Doctor", aliases=["Dr Anil Verma"],
            documents=["aadhaar", "land_record", "bank_account"]),

    # PM-JAY: clean pass.
    citizen("C004", "Meena Kumari", "Gaya", "Bihar", 38,
            secc_deprived=True, documents=["aadhaar", "ration_card"]),

    # NSP: clean pass.
    citizen("C005", "Karthik Raman", "Madurai", "Tamil Nadu", 19,
            category="SC", family_income=180000, enrolled=True, aliases=["Karthik R"],
            documents=["income_certificate", "caste_certificate", "enrollment_proof",
                       "bank_account"]),

    # NSP: excluded on category.
    citizen("C006", "Priya Nair", "Ernakulam", "Kerala", 20,
            category="GEN", family_income=150000, enrolled=True,
            documents=["income_certificate", "enrollment_proof", "bank_account"]),

    # NSP: excluded on the income ceiling. Shares a district with C005 so that
    # district alone cannot disambiguate -- the agent has to use the name.
    citizen("C007", "Lakshmi Narayanan", "Madurai", "Tamil Nadu", 21,
            category="ST", family_income=300000, enrolled=True,
            documents=["income_certificate", "caste_certificate", "enrollment_proof"]),

    # PM-KISAN: Group D government employee, which is the *exception* to the
    # government-employee exclusion. Eligible. Agents routinely get this wrong.
    citizen("C008", "Ravi Shankar", "Nashik", "Maharashtra", 50,
            land_hectares=0.5, govt_employee=True, group_d=True,
            documents=["aadhaar", "land_record", "bank_account"]),

    # PM-KISAN: excluded on the Rs 10000 pension threshold.
    citizen("C009", "Sushila Bai", "Nashik", "Maharashtra", 66,
            land_hectares=1.0, pension_monthly=12000,
            documents=["aadhaar", "land_record", "bank_account"]),

    # PM-JAY: SECC-listed but already covered by ESIC, so excluded.
    citizen("C010", "Arjun Yadav", "Patna", "Bihar", 41,
            secc_deprived=True, esic_or_cghs=True,
            documents=["aadhaar", "ration_card"]),

    # NSP: eligible on the rules but missing the bank account on file. The
    # agent should surface the gap rather than submit an incomplete application.
    citizen("C011", "Fatima Begum", "Hyderabad", "Telangana", 18,
            category="OBC", family_income=90000, enrolled=True,
            documents=["income_certificate", "caste_certificate", "enrollment_proof"]),

    # NSP renewal: marks below the 50 percent bar.
    citizen("C012", "Deepak Bhosale", "Kolhapur", "Maharashtra", 22,
            category="OBC", family_income=140000, enrolled=True,
            renewal=True, previous_marks=42,
            documents=["income_certificate", "caste_certificate", "enrollment_proof",
                       "bank_account"]),
]


def rail_db():
    return {"now": NOW, "trains": TRAINS, "bookings": BOOKINGS}


def schemes_db():
    return {"now": NOW, "citizens": CITIZENS, "applications": []}


def main():
    write_json(DATA / "rail.json", rail_db())
    write_json(DATA / "schemes.json", schemes_db())
    print(f"rail:    {len(BOOKINGS)} bookings across {len(TRAINS)} trains -> {DATA / 'rail.json'}")
    print(f"schemes: {len(CITIZENS)} citizens -> {DATA / 'schemes.json'}")


if __name__ == "__main__":
    main()
