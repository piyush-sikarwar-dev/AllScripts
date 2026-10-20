"""In-memory stand-in for `app/repositories/legacy.py` (pre-2010 DMZ chart). Clearly fake data."""

import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import PureWindowsPath
from typing import Any

from app.documents.render import rtf_to_text

_LAST = ["Sample", "Specimen", "Example", "Placeholder", "Testcase", "Mockridge"]
_FIRST = ["Legacy A", "Legacy B", "Legacy C", "Legacy D"]
_PROVIDERS = [("Doctor", "Sample", "MD"), ("Clinician", "Example", "DO"), (None, None, None)]
_FACILITIES = ["Main Street Clinic", "North Office", None]
_SECTIONS = [
    ("Chief complaint", "Follow-up visit."),
    ("Assessment", "Condition stable."),
    ("Plan", "Continue current care. Return in 3 months."),
]

LEGACY_START = datetime(2002, 1, 1, 9, 0)
_NOTE_TYPES = ["DEC FOLLOW-UP VISIT", "NURSE PHONE CALL"]


def _rtf(i: int) -> str:
    """A small RTF document in the shape of the legacy chart notes (fonts, header, fields)."""
    lines = "".join(f"\\b {title}:\\b0  {text}\\par " for title, text in _SECTIONS)
    return (
        "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Arial;}}{\\colortbl;\\red0\\green0\\blue0;}"
        "{\\header Sample header}"
        f"\\pard Fake chart note {i}\\par {lines}"
        "{\\field{\\*\\fldinst DATE}{\\fldrslt 01/01/2005}}\\par }"
    )


def _build() -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]], dict[int, str]]:
    rng = random.Random(20020101)
    people: list[dict[str, Any]] = []
    notes: dict[int, list[dict[str, Any]]] = {}
    texts: dict[int, str] = {}
    note_id = 900_000
    for i in range(24):
        key = 5_000 + i
        people.append(
            {
                "person_key": key,
                "last_name": _LAST[i % len(_LAST)],
                "first_name": _FIRST[i % len(_FIRST)],
                "middle_initial": None,
                "suffix": None,
                "dob": datetime(1940 + i * 2, 1 + i % 12, 1 + i % 27),
                "sex": "FMU"[i % 3],
                "deceased": "Y" if i == 5 else "N",
                "street1": f"{100 + i} Example Ave",
                "street2": None,
                "city": "Sampletown",
                "state": "NY",
                "zip": "00000",
                "home_area": "555",
                "home_phone": f"01{i:05d}",
                "legacy_id": f"L{key}",
            }
        )
        rows = []
        for n in range(0 if i == 7 else 3 + i % 30):
            note_id += 1
            when = LEGACY_START + timedelta(days=rng.randint(0, 3100), hours=rng.randint(0, 8))
            doctor = _PROVIDERS[n % len(_PROVIDERS)]
            has_text = n % 9 != 4
            rows.append(
                {
                    "note_id": note_id,
                    "service_date": when,
                    "provider_last": doctor[1],
                    "provider_first": doctor[0],
                    "provider_title": doctor[2],
                    "facility": _FACILITIES[n % len(_FACILITIES)],
                    "has_text": 1 if has_text else 0,
                    "note_type": _NOTE_TYPES[n % 2] if has_text else "ORDER MANAGEMENT RESULT",
                }
            )
            if has_text:
                texts[note_id] = _rtf(note_id)
        rows.sort(key=lambda r: (r["service_date"], r["note_id"]), reverse=True)
        notes[key] = rows
    return people, notes, texts


PEOPLE, NOTES, TEXTS = _build()
PEOPLE_BY_KEY = {p["person_key"]: p for p in PEOPLE}


def search(
    *,
    last_name: str | None,
    first_name: str | None,
    dob: date | None,
    legacy_id: str | None,
    offset: int,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    def matches(p: dict[str, Any]) -> bool:
        return (
            (last_name is None or p["last_name"].lower().startswith(last_name.lower()))
            and (first_name is None or p["first_name"].lower().startswith(first_name.lower()))
            and (dob is None or p["dob"].date() == dob)
            and (legacy_id is None or p["legacy_id"] == legacy_id)
        )

    found = sorted(
        (p for p in PEOPLE if matches(p)),
        key=lambda p: (p["last_name"], p["first_name"], p["person_key"]),
    )
    return [dict(p) for p in found[offset : offset + limit]], len(found)


def patient(person_key: int) -> dict[str, Any] | None:
    p = PEOPLE_BY_KEY.get(person_key)
    return dict(p) if p else None


def notes(person_key: int) -> list[dict[str, Any]]:
    return [dict(n) for n in NOTES.get(person_key, [])]


def note_text(person_key: int, note_id: int) -> dict[str, Any] | None:
    row = next((n for n in NOTES.get(person_key, []) if n["note_id"] == note_id), None)
    if row is None or note_id not in TEXTS:
        return None
    return {"note_id": note_id, "service_date": row["service_date"],
            "text": rtf_to_text(TEXTS[note_id])}  # fmt: skip


_PROBLEMS = [
    ("250.00", "DIABETES MELLITUS TYPE II", 12),
    ("401.9", "HYPERTENSION NOS", 12),
    ("272.4", "HYPERLIPIDEMIA NEC/NOS", 11),
    ("477.9", "ALLERGIC RHINITIS NOS", 30),
]
_ALLERGIES = [
    ("PENICILLIN", "DRUG", 1, "ACTIVE", "Severe", ["Hives", "Rash"]),
    ("SULFA", "DRUG", 1, "ACTIVE", "Not Available", []),
    ("PEANUTS", "FOOD", 11, "INACTIVE", None, ["Swelling"]),
    ("LATEX", None, 30, "ENTERED IN ERROR", "Mild", []),
]


def _history(person_key: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    i = person_key - 5_000
    if i % 4 == 3:  # some legacy patients have no problems or allergies
        return [], []
    probs = [
        {
            "problem_id": person_key * 10 + n,
            "dx_code": code,
            "dx_desc1": desc,
            "dx_desc2": None,
            "provisional": None,
            "comment": "Sample comment" if n == 0 else None,
            "onset_date": datetime(2003 + n, 3, 1),
            "stop_date": datetime(2008, 1, 1) if status == 11 else None,
            "status_key": status,
            "recorded_at": datetime(2003 + n, 3, 1, 10, 0),
            "provider_last": "Sample",
            "provider_first": "Doctor",
            "provider_title": "MD",
        }
        for n, (code, desc, status) in enumerate(_PROBLEMS)
    ]
    alrgs = [
        {
            "allergy_id": person_key * 10 + n,
            "allergen": name,
            "allergen_desc": name,
            "category": cat,
            "status_key": status_key,
            "status": status,
            "active_flag": "E" if status_key == 30 else "Y",
            "severity": severity,
            "comment": None,
            "noted_date": datetime(2004, 1 + n, 1),
            "provider_last": None,
            "provider_first": None,
            "provider_title": None,
            "reactions": list(reactions),
        }
        for n, (name, cat, status_key, status, severity, reactions) in enumerate(_ALLERGIES)
    ]
    probs.sort(key=lambda r: r["onset_date"], reverse=True)
    alrgs.sort(key=lambda r: r["noted_date"], reverse=True)
    return probs, alrgs


def problems(person_key: int) -> list[dict[str, Any]]:
    return _history(person_key)[0] if person_key in PEOPLE_BY_KEY else []


def allergies(person_key: int) -> list[dict[str, Any]]:
    return _history(person_key)[1] if person_key in PEOPLE_BY_KEY else []


# (drug, sig frequency, [(status_key, status, group, months after start, stopped?)])
_MEDS = [
    (
        "METFORMIN HCL  TABLET 500 MG",
        "Twice Daily",
        [(1, "New Prescription", 1, 0, False), (2, "Continued", 1, 6, False)],
    ),
    (
        "LISINOPRIL  TABLET 10 MG",
        "Every A.M.",
        [(1, "New Prescription", 1, 0, False), (11, "Discontinued", 3, 12, True)],
    ),
    ("ASPIRIN  TABLET 81 MG", None, [(10, "New History", 1, 0, False)]),
    ("AMOXICILLIN  CAPSULE 500 MG", "Three Times Daily", [(30, "Entered in Error", 6, 0, False)]),
]


def medications(person_key: int) -> list[dict[str, Any]]:
    if person_key not in PEOPLE_BY_KEY or (person_key - 5_000) % 4 == 3:
        return []
    rows = []
    for n, (drug, freq, entries) in enumerate(_MEDS):
        med_id = person_key * 100 + n * 10
        start = datetime(2004 + n, 2, 1)
        for e, (status_key, status, group, months, stopped) in enumerate(entries):
            when = start + timedelta(days=30 * months)
            rows.append(
                {
                    "entry_id": med_id + e,
                    "med_id": med_id,
                    "mdrug_name": drug,
                    "udrug_name": None,
                    "udrug_strength": None,
                    "sig_quantity": "1" if freq else None,
                    "sig_dose_form": None,
                    "sig_frequency": freq,
                    "amt_dispensed": Decimal("60.000") if freq else None,
                    "amt_uom": "TAB" if freq else None,
                    "num_refills": 2 if freq else None,
                    "days_supply": 30,
                    "dispense_as_written": "N",
                    "date_written": when,
                    "date_of_service": when,
                    "stop_date": when if stopped else None,
                    "last_dose_date": None,
                    "status_key": status_key,
                    "status": status,
                    "status_group": group,
                    "comments": "Sample comment" if n == 0 and e == 0 else None,
                    "dx_code": "250.00" if n == 0 else None,
                    "dx_desc": "DIABETES MELLITUS TYPE II" if n == 0 else None,
                    "provider_last": "Sample",
                    "provider_first": "Doctor",
                    "provider_title": "MD",
                }
            )
    return rows


# (name, value, low, high) per lab draw; vitals per visit.
_LABS = [
    ("TSH", "2.10", "0.40", "4.00"),
    ("A1C", "7.8", "4.0", "5.6"),
    ("POTASSIUM", "3.1", "3.5", "5.1"),
]
_VITALS = [
    ("VS-BLOOD PRESSURE", "128/82"),
    ("VS-PULSE", "72"),
    ("VS-WEIGHT", "180lb"),
    ("VS-HEIGHT", "5ft10in"),
    ("BMI", "25.8"),
]


def clinical_items(person_key: int) -> list[dict[str, Any]]:
    if person_key not in PEOPLE_BY_KEY or (person_key - 5_000) % 4 == 3:
        return []
    note_ids = [n["note_id"] for n in NOTES.get(person_key, [])]
    rows: list[dict[str, Any]] = []
    item_id = person_key * 1000
    for visit in range(3):
        when = datetime(2005 + visit, 4, 12, 10, 30)
        items = [(name, value, None, None) for name, value in _VITALS]
        items += _LABS if visit != 1 else []
        items.append(("GENERIC-PHONE ENTRY", "(555)000-0000 home.", None, None))
        for name, value, low, high in items:
            item_id += 1
            rows.append(
                {
                    "item_id": item_id,
                    "service_datetime": when,
                    "item_name": name,
                    "value": value,
                    "ref_low": low,
                    "ref_high": high,
                    "comments": "Fasting" if name == "A1C" else None,
                    "note_id": note_ids[0] if note_ids and visit == 0 else None,
                }
            )
    rows.sort(key=lambda r: (r["service_datetime"], r["item_id"]), reverse=True)
    return rows


LEGACY_SHARE = PureWindowsPath("//w10060-1/images")
_DOC_TYPES = ["OUTSIDE LABS", "INSURANCE CARD", "HIPAA", "X-RAY REPORT"]


def documents(person_key: int) -> list[dict[str, Any]]:
    if person_key not in PEOPLE_BY_KEY or (person_key - 5_000) % 4 == 3:
        return []
    note_ids = [n["note_id"] for n in NOTES.get(person_key, [])]
    rows = [
        {
            "document_id": person_key * 10 + n,
            "doc_date": datetime(2006, 1 + n, 15),
            "scanned_date": datetime(2006, 1 + n, 16, 9, 0),
            "doc_type": doc_type,
            "pages": 1 + n % 3,
            "file_ext": "JPG" if n == 3 else "TIF",
            "note_id": note_ids[0] if note_ids and n == 0 else None,
            "provider_last": "Sample" if n % 2 == 0 else None,
            "provider_first": "Doctor" if n % 2 == 0 else None,
            "provider_title": "MD" if n % 2 == 0 else None,
        }
        for n, doc_type in enumerate(_DOC_TYPES)
    ]
    rows.sort(key=lambda r: r["doc_date"], reverse=True)
    return rows


def document_file(person_key: int, document_id: int) -> dict[str, Any] | None:
    row = next((d for d in documents(person_key) if d["document_id"] == document_id), None)
    if row is None:
        return None
    ext = row["file_ext"]
    location = str(LEGACY_SHARE / "archive" / f"{document_id}.{ext}")
    return {"document_id": document_id, "location": location, "pages": row["pages"],
            "file_ext": ext}  # fmt: skip
