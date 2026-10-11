"""Deterministic, obviously fake archive data for UI work and unit tests.

Every name, address and phone number here is invented ("Sample, Patient A", 555-01xx numbers).
Rows are shaped like what the real repositories will return: raw values (dates, codes), not
display strings. Services do all formatting.
"""

import random
import string
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

LAST_NAMES = ["Sample", "Example", "Demo", "Testcase", "Placeholder", "Fictional"]
PROVIDERS = ["Sample, Provider MD", "Example, Doctor DO", "Demo, Clinician NP"]
LOCATIONS = ["Main Clinic", "North Office"]
INSURERS = ["Sample Health Plan", "Example Mutual Insurance", "Demo Medicare Advantage"]

# (label, is_office_visit)
VISIT_TYPES = [
    ("Office visit", True),
    ("Follow-up visit", True),
    ("Annual physical", True),
    ("Telephone encounter", False),
    ("Refill request", False),
]

DIAGNOSES = [
    ("Essential hypertension", "I10"),
    ("Type 2 diabetes mellitus without complications", "E11.9"),
    ("Hyperlipidemia, unspecified", "E78.5"),
    ("Acute upper respiratory infection", "J06.9"),
    ("Low back pain", "M54.50"),
    ("Vitamin D deficiency", "E55.9"),
]

PLAN_LINES = [
    "Continue current medications.",
    "Return to clinic in 3 months.",
    "Labs ordered: basic metabolic panel.",
    "Diet and exercise counselling provided.",
    "Follow up sooner if symptoms worsen.",
]

ALLERGIES = [("Penicillin", "Hives"), ("Sulfa drugs", "Rash"), ("Latex", "Itching")]
SURGERIES = ["Appendectomy", "Tonsillectomy", "Knee arthroscopy"]
FAMILY = ["Family history of hypertension", "Family history of diabetes"]
SOCIAL = ["Never smoker", "Former smoker", "Occasional alcohol use"]

MEDS = [
    ("Lisinopril 10 mg tablet", "Take 1 tablet by mouth once daily"),
    ("Metformin 500 mg tablet", "Take 1 tablet by mouth twice daily with meals"),
    ("Atorvastatin 20 mg tablet", "Take 1 tablet by mouth at bedtime"),
    ("Vitamin D3 1000 unit capsule", "Take 1 capsule by mouth daily"),
    ("Amoxicillin 500 mg capsule", "Take 1 capsule by mouth three times daily for 10 days"),
]

# (test, units, low, high, decimals)
LAB_TESTS = [
    ("Glucose", "mg/dL", 70.0, 99.0, 0),
    ("Hemoglobin A1c", "%", 4.0, 5.6, 1),
    ("LDL cholesterol", "mg/dL", 0.0, 99.0, 0),
    ("Creatinine", "mg/dL", 0.6, 1.2, 2),
    ("Potassium", "mmol/L", 3.5, 5.1, 1),
    ("TSH", "mIU/L", 0.4, 4.0, 2),
]

DOC_TYPES = ["Referral letter", "Outside records", "Insurance card", "Consent form", "Lab report"]

EMR_START = date(2010, 9, 1)
EMR_END = date(2023, 6, 30)
LEGACY_START = date(2002, 1, 1)
LEGACY_END = date(2010, 8, 27)


@dataclass
class FakePatient:
    emr_id: int
    last_name: str
    first_name: str
    middle_initial: str
    dob: date
    sex: str
    chart_id: str
    deceased: bool
    phone: str
    address: str
    city: str
    state: str
    zip: str
    ntier_id: int | None
    pm_account: str | None
    dmz_id: int | None
    primary_insurance: str | None
    visits: list[dict] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    medications: list[dict] = field(default_factory=list)
    labs: list[dict] = field(default_factory=list)
    vitals: list[dict] = field(default_factory=list)
    documents: list[dict] = field(default_factory=list)


def _letter(i: int) -> str:
    letters = string.ascii_uppercase
    return letters[i] if i < 26 else letters[i // 26 - 1] + letters[i % 26]


def _rand_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _rand_dt(rng: random.Random, start: date, end: date) -> datetime:
    d = _rand_date(rng, start, end)
    return datetime(d.year, d.month, d.day, rng.randint(8, 16), rng.choice([0, 15, 30, 45]))


def _lab_value(rng: random.Random, low: float, high: float, decimals: int) -> float:
    span = high - low if high > low else high
    # ~25% abnormal, both directions.
    roll = rng.random()
    if roll < 0.15:
        value = high + span * rng.uniform(0.05, 0.6)
    elif roll < 0.25 and low > 0:
        value = low - span * rng.uniform(0.05, 0.3)
    else:
        value = rng.uniform(low if low > 0 else high * 0.4, high)
    return round(max(value, 0.01), decimals)


def _build_patient(i: int, rng: random.Random, ids: dict[str, int]) -> FakePatient:
    emr_id = 1001 + i
    has_pm = i % 3 != 2
    has_legacy = i % 4 == 0
    p = FakePatient(
        emr_id=emr_id,
        last_name=LAST_NAMES[i % len(LAST_NAMES)],
        first_name=f"Patient {_letter(i)}",
        middle_initial="Q" if i % 5 == 0 else "",
        dob=_rand_date(rng, date(1935, 1, 1), date(2015, 12, 31)),
        sex="F" if i % 2 == 0 else "M",
        chart_id=f"{100200 + i * 37}",
        deceased=i == 7,
        phone=f"(555) 010-{i:04d}",
        address=f"{100 + i} Sample Street",
        city="Anytown",
        state="ST",
        zip="00000",
        ntier_id=50000 + i if has_pm else None,
        pm_account=f"{700000 + i * 11}" if has_pm else None,
        dmz_id=9000 + i if has_legacy else None,
        primary_insurance=INSURERS[i % len(INSURERS)] if i % 6 != 5 else None,
    )
    if i == 29:  # One patient with no clinical data at all, to exercise every empty state.
        return p

    def next_id(kind: str) -> int:
        ids[kind] += 1
        return ids[kind]

    # Visits (+ vitals, labs and notes hanging off them).
    for _ in range(rng.randint(4, 34)):
        vtype, office = rng.choice(VISIT_TYPES)
        start = _rand_dt(rng, EMR_START, EMR_END)
        dx = rng.sample(DIAGNOSES, k=rng.randint(1, 3)) if office else []
        contact_id = next_id("contact")
        has_note = rng.random() < 0.75
        visit = {
            "contact_id": contact_id,
            "encounter_id": contact_id + 500000,
            "start": start,
            "visit_type": vtype,
            "is_office_visit": office,
            "provider": rng.choice(PROVIDERS),
            "location": rng.choice(LOCATIONS),
            "signed": rng.random() < 0.9,
            "diagnoses": dx,
            "plan": rng.sample(PLAN_LINES, k=rng.randint(1, 3)) if office else [],
            "addenda": ["Addendum: results reviewed with patient by phone."]
            if rng.random() < 0.1
            else [],
            "note_text": (
                f"{vtype}. This is placeholder note text generated for interface review only.\n\n"
                "Subjective: Sample subjective findings.\nObjective: Sample objective findings.\n"
                "Assessment and plan: See structured sections above."
            )
            if has_note
            else None,
            "source": "EMR",
        }
        p.visits.append(visit)
        if has_note:
            p.notes.append(
                {
                    "id": next_id("note"),
                    "date": start,
                    "title": f"{vtype} note",
                    "author": visit["provider"],
                    "source": "EMR",
                }
            )
        if office:
            p.vitals.append(
                {
                    "id": next_id("vital"),
                    "contact_id": contact_id,
                    "date": start,
                    "systolic": rng.randint(104, 168),
                    "diastolic": rng.randint(62, 98),
                    "pulse": rng.randint(56, 104),
                    "temp": round(rng.uniform(97.0, 100.4), 1),
                    "temp_unit": "°F",
                    "weight": round(rng.uniform(110, 260), 1),
                    "weight_unit": "lb",
                    "height": rng.randint(58, 76) if rng.random() < 0.6 else None,
                    "height_unit": "in",
                    "spo2": rng.randint(93, 100) if rng.random() < 0.8 else None,
                    "pain": rng.randint(0, 6) if rng.random() < 0.7 else None,
                    "source": "EMR",
                }
            )
            if rng.random() < 0.5:
                for test, units, low, high, dec in rng.sample(LAB_TESTS, k=rng.randint(2, 5)):
                    value = _lab_value(rng, low, high, dec)
                    flag = "H" if value > high else "L" if value < low else None
                    p.labs.append(
                        {
                            "id": next_id("lab"),
                            "date": start + timedelta(days=rng.randint(0, 3)),
                            "test": test,
                            "value": value,
                            "decimals": dec,
                            "units": units,
                            "low": low,
                            "high": high,
                            "flag": flag,
                            "source": "EMR",
                        }
                    )

    # Transcriptions.
    for _ in range(rng.randint(0, 3)):
        p.notes.append(
            {
                "id": next_id("note"),
                "date": _rand_dt(rng, EMR_START, EMR_END),
                "title": rng.choice(["Consultation letter", "Dictated progress note"]),
                "author": rng.choice(PROVIDERS),
                "source": "EMR",
            }
        )

    # History: problems, allergies, surgical, family, social.
    for title, code in rng.sample(DIAGNOSES, k=rng.randint(1, 4)):
        resolved = rng.random() < 0.25
        onset = _rand_date(rng, date(2005, 1, 1), EMR_END)
        p.history.append(
            {
                "id": next_id("hx"),
                "group": "problem",
                "title": title,
                "code_system": "ICD-10",
                "code": code,
                "onset": onset,
                "onset_precision": rng.choice(["full", "full", "month_year", "year"]),
                "resolved": onset + timedelta(days=rng.randint(30, 900)) if resolved else None,
                "status": "Resolved" if resolved else "Active",
                "reaction": None,
                "source": "EMR",
            }
        )
    for name, reaction in rng.sample(ALLERGIES, k=rng.randint(0, 2)):
        p.history.append(
            {
                "id": next_id("hx"),
                "group": "allergy",
                "title": name,
                "code_system": None,
                "code": None,
                "onset": _rand_date(rng, date(1990, 1, 1), EMR_END),
                "onset_precision": "year",
                "resolved": None,
                "status": "Active",
                "reaction": reaction,
                "source": "EMR",
            }
        )
    for group, choices in (("surgical", SURGERIES), ("family", FAMILY), ("social", SOCIAL)):
        for title in rng.sample(choices, k=rng.randint(0, 1)):
            p.history.append(
                {
                    "id": next_id("hx"),
                    "group": group,
                    "title": title,
                    "code_system": None,
                    "code": None,
                    "onset": _rand_date(rng, date(1980, 1, 1), EMR_END)
                    if group == "surgical"
                    else None,
                    "onset_precision": "year",
                    "resolved": None,
                    "status": "Active" if group != "surgical" else "Completed",
                    "reaction": None,
                    "source": "EMR",
                }
            )

    # Medications.
    for name, sig in rng.sample(MEDS, k=rng.randint(1, 4)):
        start = _rand_date(rng, EMR_START, EMR_END)
        stopped = rng.random() < 0.35
        p.medications.append(
            {
                "id": next_id("med"),
                "name": name,
                "sig": sig,
                "start": start,
                "start_precision": "full",
                "end": start + timedelta(days=rng.randint(10, 700)) if stopped else None,
                "end_precision": "full",
                "status": "Discontinued" if stopped else "Active",
                "source": "EMR",
            }
        )
    if rng.random() < 0.5:
        name, sig = rng.choice(MEDS)
        p.medications.append(
            {
                "id": next_id("med"),
                "name": name,
                "sig": "Reported by patient",
                "start": _rand_date(rng, date(2008, 1, 1), EMR_END),
                "start_precision": "month_year",
                "end": None,
                "end_precision": "full",
                "status": "Active",
                "source": "EMR history",
            }
        )

    # Scanned documents and HTML clinical documents.
    for _ in range(rng.randint(0, 8)):
        doc_type = rng.choice(DOC_TYPES)
        p.documents.append(
            {
                "id": next_id("doc"),
                "date": _rand_date(rng, EMR_START, EMR_END),
                "type": doc_type,
                "title": f"{doc_type} (sample)",
                "pages": rng.randint(1, 6),
                "kind": "scan",
                "source": "EMR",
            }
        )
    for _ in range(rng.randint(0, 2)):
        p.documents.append(
            {
                "id": next_id("doc"),
                "date": _rand_date(rng, EMR_START, EMR_END),
                "type": "Clinical document",
                "title": "Clinical summary (sample)",
                "pages": None,
                "kind": "html",
                "source": "EMR",
            }
        )

    # Pre-2010 legacy chart rows.
    if has_legacy:
        legacy_dt = _rand_dt(rng, LEGACY_START, LEGACY_END)
        p.medications.append(
            {
                "id": next_id("med"),
                "name": "Hydrochlorothiazide 25 mg tablet",
                "sig": "Take 1 tablet by mouth once daily",
                "start": legacy_dt.date(),
                "start_precision": "full",
                "end": None,
                "end_precision": "full",
                "status": "Unknown",
                "source": "Pre-2010",
            }
        )
        p.notes.append(
            {
                "id": next_id("note"),
                "date": legacy_dt,
                "title": "Legacy chart note",
                "author": rng.choice(PROVIDERS),
                "source": "Pre-2010",
            }
        )
        test, units, low, high, dec = rng.choice(LAB_TESTS)
        value = _lab_value(rng, low, high, dec)
        p.labs.append(
            {
                "id": next_id("lab"),
                "date": legacy_dt,
                "test": test,
                "value": value,
                "decimals": dec,
                "units": units,
                "low": low,
                "high": high,
                "flag": "H" if value > high else "L" if value < low else None,
                "source": "Pre-2010",
            }
        )
    return p


def build_patients(count: int = 30, seed: int = 20100827) -> list[FakePatient]:
    rng = random.Random(seed)
    ids = dict.fromkeys(("contact", "note", "hx", "med", "lab", "vital", "doc"), 0)
    return [_build_patient(i, rng, ids) for i in range(count)]


PATIENTS: list[FakePatient] = build_patients()
PATIENTS_BY_ID: dict[int, FakePatient] = {p.emr_id: p for p in PATIENTS}
