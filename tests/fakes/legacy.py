"""In-memory stand-in for `app/repositories/legacy.py` (pre-2010 DMZ chart). Clearly fake data."""

import random
from datetime import date, datetime, timedelta
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
