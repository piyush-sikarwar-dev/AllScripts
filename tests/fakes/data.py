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
    clinical_notes: list[dict] = field(default_factory=list)  # Notes tab
    hx_entries: list[dict] = field(default_factory=list)  # Problems & allergies tab
    hx_revisions: dict[int, list[dict]] = field(default_factory=dict)
    appointments: list[dict] = field(default_factory=list)  # Appointments tab


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


# --- Notes tab: ~40 synthetic clinical notes per patient (own seed and id range, so the data above
# stays exactly as it was). Bodies are shaped like the real documents, all values invented.

RX_DRUGS = [
    ("MetFORMIN HCl ER 500MG", "Tablet ER 24HR", "2 (two) Tablet ER 24HR daily", 270, 90, 3),
    ("Glimepiride 4MG", "Tablet", "2 (two) Tablet daily", 180, 90, 3),
    ("Insulin Detemir 100UNIT/ML", "Solution Pen-injector", "10 units twice daily", 1, 30, 11),
    ("Telmisartan 80MG", "Tablet", "1 (one) Tablet daily", 30, 30, 11),
    ("Synthroid 50MCG", "Tablet", "1 (one) Tablet daily", 90, 90, 1),
    ("Victoza 18MG/3ML", "Solution Pen-injector", "1.8 mg daily", 9, 30, 5),
    ("Atorvastatin Calcium 20MG", "Tablet", "1 (one) Tablet at bedtime", 90, 90, 0),
]
RX_DX = [
    ("Type 2 diabetes mellitus with hyperglycemia", "250.02", "E11.65"),
    ("Hypothyroidism, unspecified", "244.9", "E03.9"),
    ("Essential hypertension", "401.9", "I10"),
]
LAB_TITLES = ["* Lab Results by Date Range", "Laboratory Requisitions", "Lab Report", "A1C"]
VISIT_TITLES = [
    "* History & Physical Note with Caregiver",
    "Encounter History & Physical Note",
    "Follow-up visit note",
]
LETTER_TITLES = [
    "DEC Letter to Referring Provider",
    "Incoming Fax",
    "Entire Chart Receipt",
    "MEDICAL NECESSITY LETTER",
    "Patient Education",
]
APP_SOURCES = ["Clinical Module", "Input Manager"]
SAMPLE_PHARMACY = "Sample Community Pharmacy #12"


def _rx_body(p: FakePatient, drug: tuple, dx: tuple, written: datetime, prescriber: str) -> str:
    name, form, sig, qty, days, refills = drug
    return (
        f"<p>Main Clinic<br>100 Sample Street, Anytown, ST 00000<br>Phone: (555) 010-0100</p>"
        f"<p>Date: {written:%m/%d/%Y}<br>Patient: {p.first_name} {p.last_name}<br>"
        f"Phone: {p.phone} Gender: {p.sex} DOB: {p.dob:%m/%d/%Y}<br>Address: {p.address}</p>"
        f"<p>Pharmacy: {SAMPLE_PHARMACY}<br>Address: 1 Example Road, Anytown, ST 00000<br>"
        f"Phone: (555) 010-0200 Fax: (555) 010-0201</p><p>RX</p>"
        f"<p>Medication: {name} {form}<br>Date Written: {written:%m/%d/%Y}<br>"
        f"Dispense: {qty} (sample) {form.split()[0]}, Days Supply: {days} (sample)<br>"
        f"Substitution Permissible<br>SIG: {sig}<br>Notes for Pharmacist: Sample instructions.<br>"
        f"Refill(s) x{refills} (sample) x {qty} {form.split()[0]}<br>Associated Diagnosis<br>"
        f"{dx[0]} ({dx[1]} | {dx[2]})</p><p>---------------------------------------</p>"
        f"<p>{prescriber}<br>NPI: 0000000000<br>DEA: XX0000000</p>"
    )


def _note_body(kind: str, title: str, when: datetime, who: str) -> str:
    if kind == "lab":
        return (
            f"<h3>{title}</h3><p>Collected: {when:%m/%d/%Y}</p><table><tr><th>Test</th>"
            "<th>Result</th><th>Range</th></tr><tr><td>Hemoglobin A1c</td><td>7.2 %</td>"
            "<td>4.0-5.6</td></tr><tr><td>Glucose</td><td>132 mg/dL</td><td>70-99</td></tr>"
            "</table><p>SSN: 000-12-3456</p>"
        )
    if kind == "visit":
        return (
            f"<h3>History of Present Illness ({who}; {when:%m/%d/%Y})</h3><p>Sample patient seen "
            "for follow-up. Placeholder narrative generated for interface review only.</p>"
            "<h3>Assessment &amp; Plan</h3><p>Continue current medications.</p>"
            '<script>alert(1)</script><p onclick="x()">Return in 3 months.</p>'
        )
    return (
        f"<p>Dear Dr. Example,</p><p>{title}: placeholder letter text generated for interface "
        f"review only.</p><p>Sincerely,<br>{who}</p>"
    )


def add_clinical_notes(p: FakePatient, seed: int) -> None:
    rng = random.Random(seed + p.emr_id)
    next_doc = 700000 + (p.emr_id - 1000) * 100
    encounters = [v["encounter_id"] for v in p.visits]
    for n in range(rng.randint(36, 44)):
        roll = rng.random()
        kind = (
            "rx" if roll < 0.45 else "visit" if roll < 0.65 else "lab" if roll < 0.85 else "letter"
        )
        when = _rand_dt(rng, EMR_START, EMR_END)
        who = rng.choice(PROVIDERS)
        note = {
            "kind": "document",
            "id": next_doc + n,
            "date": when,
            "who": who,
            "app_source": rng.choice(APP_SOURCES),
            "map_sources": [],
            "source": "EMR",
            "encounter_id": rng.choice(encounters) if encounters and rng.random() < 0.5 else None,
        }
        if kind == "rx":
            drug, dx = rng.choice(RX_DRUGS), rng.choice(RX_DX)
            name, _form, sig, qty, days, refills = drug
            note |= {
                "title": f"{name}, {sig}, #{qty}, {days} days starting {when:%m/%d/%Y}, "
                f"Ref. x{refills}.",
                "map_sources": ["IMREMED_CODE"],
                # every 12th printout is unreadable, to exercise the formatting fallback
                "html": "<p>Unreadable printout</p>"
                if n % 12 == 5
                else _rx_body(p, drug, dx, when, who),
            }
        elif kind == "lab":
            title = rng.choice(LAB_TITLES)
            note |= {
                "title": title,
                "html": _note_body("lab", title, when, who),
                "map_sources": ["IMREQUISITION_CODE"] if "Requisition" in title else [],
            }
        elif kind == "visit":
            title = rng.choice(VISIT_TITLES)
            note |= {"title": title, "html": _note_body("visit", title, when, who)}
        else:
            title = rng.choice(LETTER_TITLES)
            note |= {"title": title, "html": _note_body("letter", title, when, who)}
        p.clinical_notes.append(note)
    if encounters:  # one dictation (RTF text) per patient with visits
        when = _rand_dt(rng, EMR_START, EMR_END)
        p.clinical_notes.append(
            {
                "kind": "transcription",
                "id": 900000 + p.emr_id,
                "date": when,
                "title": "Dictation",
                "who": rng.choice(PROVIDERS),
                "app_source": "Transcription",
                "map_sources": [],
                "source": "EMR",
                "encounter_id": encounters[0],
                "html": None,
                "text": "Chief Complaint: Sample follow-up.\nAssessment: Stable.\nPlan: Continue.",
            }
        )


# --- Problems & allergies tab: history entries with revisions (own seed and id range, so the
# data above stays exactly as it was). Shaped like repositories.live.history_entries output.

HX_PROBLEMS = [
    ("Type 2 diabetes mellitus", "ICD9", "250.00"),
    ("Essential hypertension", "ICD9", "401.9"),
    ("Hyperlipidemia", "HISTORY", "17354"),
    ("Hypothyroidism", "ICD9", "244.9"),
    ("Obesity", "HISTORY", "18022"),
    ("Vitamin D deficiency", "ICD9", "268.9"),
    ("Osteoarthritis of knee", "HISTORY", "16410"),
    ("GERD", "ICD9", "530.81"),
]
HX_ALLERGIES = [("Exenatide (Bydureon)", "MEDISPAN_NAME", "184586", ["Nausea"]),
                ("Penicillin", "MEDISPAN_NAME", "100370", ["Hives"]),
                ("Peanuts", "HISTORY", "20111", ["Rash", "Swelling"])]  # fmt: skip
HX_SURGICAL = [("Appendectomy", "CPT", "44950"), ("Cholecystectomy", "HISTORY", "15521")]
HX_FAMILY = [("Diabetes mellitus", ["Mother"]), ("Hypertension", ["Father", "Brother"])]
HX_SOCIAL = [
    ("Tobacco use", ["Never Smoker"]),
    ("Marital status", ["Married"]),
    ("Alcohol use", ["Occasional alcohol use"]),
    ("Education", ["College graduate"]),
]


def _hx(hx_id: int, category: int, title: str, system: str | None, code: str | None,
        onset: datetime | None, mask: int, activity: int, recorded: datetime, who: str,
        attributes: list[str] | None = None, comments: str | None = None) -> dict:  # fmt: skip
    return {
        "id": hx_id, "category_code": category, "code_system": system, "code": code,
        "imo_code": None, "title": title, "description": None, "activity_code": activity,
        "significance_code": 0, "acuity_code": 0, "onset": onset, "onset_mask": mask,
        "resolved": None, "comments": comments, "basis": None, "reason": None,
        "recorded": recorded, "provider": who, "source": "EMR",
        "attributes": [{"sort_order": i, "title": t, "value": None, "severity_code": 0}
                       for i, t in enumerate(attributes or [])],
    }  # fmt: skip


def _revisions(rng: random.Random, entry: dict) -> list[dict]:
    """1–4 revisions ending in the entry's current state."""
    keys = ("title", "activity_code", "significance_code", "onset", "onset_mask", "resolved",
            "comments")  # fmt: skip
    final = {k: entry[k] for k in keys} | {"reason": None}
    revs = [dict(final)]
    for _ in range(rng.randint(0, 3)):
        prev = dict(revs[0])
        change = rng.choice(["activity", "onset", "comment"])
        if change == "activity":
            prev["activity_code"] = 1 if prev["activity_code"] != 1 else 2
        elif change == "onset" and prev["onset"]:
            prev["onset"] = prev["onset"] - timedelta(days=rng.randint(30, 400))
        else:
            prev["comments"] = None if prev["comments"] else "Earlier comment (placeholder)."
        revs.insert(0, prev)
    start = entry["recorded"] - timedelta(days=200 * len(revs))
    return [r | {"revision": i + 1, "changed": start + timedelta(days=200 * i),
                 "provider": entry["provider"]}
            for i, r in enumerate(revs)]  # fmt: skip


def add_history_entries(p: FakePatient, seed: int) -> None:
    rng = random.Random(seed * 7 + p.emr_id)
    next_id = 800000 + (p.emr_id - 1000) * 100
    entries: list[dict] = []

    def add(category: int, title: str, system: str | None, code: str | None, *,
            attributes: list[str] | None = None, active: bool = True, dated: bool = True,
            comments: str | None = None) -> dict:  # fmt: skip
        nonlocal next_id
        next_id += 1
        onset = _rand_dt(rng, date(2008, 1, 1), EMR_END) if dated else None
        mask = rng.choice([3, 3, 2, 1]) if onset else 0
        recorded = _rand_dt(rng, date(2012, 1, 1), EMR_END)
        e = _hx(next_id, category, title, system, code, onset, mask, 1 if active else 2, recorded,
                rng.choice(PROVIDERS), attributes, comments)  # fmt: skip
        entries.append(e)
        return e

    for title, system, code in rng.sample(HX_PROBLEMS, k=rng.randint(3, 8)):
        add(24, title, system, code, active=rng.random() < 0.7, dated=rng.random() < 0.6)
    allergies = rng.sample(HX_ALLERGIES, k=rng.randint(0, 2))
    for title, system, code, reactions in allergies:
        add(21, title, system, code, attributes=reactions, dated=rng.random() < 0.4)
    if allergies:  # superseded "no known allergies" entry
        add(21, "No known allergies", "HISTORY", "16950", active=False,
            comments="Superseded when an allergy was added.")  # fmt: skip
    for title, system, code in rng.sample(HX_SURGICAL, k=rng.randint(0, 2)):
        add(20, title, system, code)
    for title, relations in rng.sample(HX_FAMILY, k=rng.randint(1, 2)):
        add(23, title, "HISTORY", str(rng.randint(10000, 19999)), attributes=relations, dated=False)
    for title, values in rng.sample(HX_SOCIAL, k=rng.randint(2, 4)):
        add(25, title, "HISTORY", str(rng.randint(10000, 19999)), attributes=values, dated=False)
    for e in entries:
        p.hx_revisions[e["id"]] = _revisions(rng, e)
    p.hx_entries = entries


# --- Appointments tab: one kept appointment per visit plus cancelled / no-show / scheduled ones
# (own seed, so the data above stays exactly as it was). Shaped like live.appointments output.

APPT_TYPES = [
    ("Office Visit 20 Min", 20),
    ("Office Visit 15 Minute", 15),
    ("Lab", 20),
    ("Consult 40", 40),
    ("Bone Density", 30),
]
CANCEL_REASONS = ["Reschedule", "Patient Cancelled", "Office Cancelled", "Weather"]


def add_appointments(p: FakePatient, seed: int) -> None:
    rng = random.Random(seed * 13 + p.emr_id)
    linked = p.ntier_id is not None
    appts = []
    for i, v in enumerate(sorted(p.visits, key=lambda v: v["start"])):
        appt_type, minutes = rng.choice(APPT_TYPES)
        appts.append(
            {
                "id": f"emr-{p.emr_id * 1000 + i}",
                "starts": v["start"],
                "emr_status": 2,
                "pm_status": "A" if linked else None,
                "type": appt_type if linked else None,
                "duration": minutes if linked else None,
                "provider": v["provider"],
                "location": v["location"],
                "cancel_reason": None,
                "arrived": f"{v['start'].hour % 12 or 12}:{v['start'].minute:02d} "
                f"{'AM' if v['start'].hour < 12 else 'PM'}",
                "left": None,
                "comment": None,
                "sources": ["EMR", "PM"] if linked else ["EMR"],
            }
        )
    for j in range(rng.randint(1, 6)):
        kind = rng.choice(["cancelled", "cancelled", "no_show", "scheduled"])
        start = _rand_dt(rng, EMR_START, EMR_END)
        appts.append(
            {
                "id": f"emr-{p.emr_id * 1000 + 900 + j}",
                "starts": start,
                "emr_status": {"cancelled": 4, "no_show": 8, "scheduled": 1}[kind],
                "pm_status": {"cancelled": "X", "no_show": "N", "scheduled": "S"}[kind]
                if linked
                else None,
                "type": "Office Visit 20 Min" if linked else None,
                "duration": 20 if linked else None,
                "provider": rng.choice(PROVIDERS),
                "location": rng.choice(LOCATIONS),
                "cancel_reason": rng.choice(CANCEL_REASONS)
                if kind == "cancelled" and linked
                else None,
                "arrived": None,
                "left": None,
                "comment": "Placeholder appointment note." if rng.random() < 0.3 else None,
                "sources": ["EMR", "PM"] if linked else ["EMR"],
            }
        )
    p.appointments = appts


# --- Notes tab: chart messages and portal messages (own seed / id range) ------------------------

MESSAGE_SUBJECTS = [
    ("Patient message", "Question about lab results"),
    ("Patient message", "Requests call back about dosage"),
    ("Refill request", "Refill request: Metformin ER 500 mg"),
]
PORTAL_SUBJECTS = [
    ("Portal message from patient", "Blood sugar log attached"),
    ("Portal message to patient", "Your recent lab results"),
]
FAKE_PDF = b"%PDF-1.4 placeholder attachment generated for interface review only %%EOF"


def add_messages(p: FakePatient, seed: int) -> None:
    rng = random.Random(seed * 17 + p.emr_id)
    encounters = [v["encounter_id"] for v in p.visits]
    base = 950000 + (p.emr_id - 1000) * 20
    for n in range(rng.randint(2, 5)):
        kind_label, subject = rng.choice(MESSAGE_SUBJECTS)
        who = rng.choice(PROVIDERS)
        p.clinical_notes.append(
            {
                "kind": "message",
                "id": base + n,
                "date": _rand_dt(rng, EMR_START, EMR_END),
                "title": subject,
                "who": who,
                "app_source": kind_label,
                "map_sources": [],
                "source": "EMR",
                "encounter_id": rng.choice(encounters) if encounters else None,
                "html": None,
                "text": "Patient called. Placeholder message text (interface review only).",
                "message_fields": [
                    ("Type", kind_label),
                    ("From", who),
                    ("To", rng.choice(PROVIDERS)),
                    ("Call-back phone", p.phone),
                    ("Subject", subject),
                ],
            }
        )
    for n in range(rng.randint(0, 2)):
        direction, subject = PORTAL_SUBJECTS[n % 2]
        attachment = "sugar-log.pdf" if n == 0 else None
        p.clinical_notes.append(
            {
                "kind": "portal",
                "id": base + 10 + n,
                "date": _rand_dt(rng, EMR_START, EMR_END),
                "title": subject,
                "who": rng.choice(PROVIDERS),
                "app_source": direction,
                "map_sources": [],
                "source": "EMR",
                "encounter_id": None,
                "html": None,
                "attachment": attachment,
                "attachment_name": attachment,
                "text": "Placeholder portal message generated for interface review only.",
                "message_fields": [("Type", direction), ("Subject", subject)]
                + ([("Attachment", attachment)] if attachment else []),
            }
        )


def build_patients(count: int = 30, seed: int = 20100827) -> list[FakePatient]:
    rng = random.Random(seed)
    ids = dict.fromkeys(("contact", "note", "hx", "med", "lab", "vital", "doc"), 0)
    patients = [_build_patient(i, rng, ids) for i in range(count)]
    for i, p in enumerate(patients):
        if i != 29:  # the patient with no clinical data stays empty
            add_clinical_notes(p, seed)
            add_history_entries(p, seed)
            add_appointments(p, seed)
            add_messages(p, seed)
    return patients


PATIENTS: list[FakePatient] = build_patients()
PATIENTS_BY_ID: dict[int, FakePatient] = {p.emr_id: p for p in PATIENTS}
