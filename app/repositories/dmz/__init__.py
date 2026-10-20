"""DMZ (pre-2010 legacy chart) read-only queries — one function per .sql file.

Used only by the separate "Pre-2010 records" section; never by the current (EMR / PM) chart.
"""

from datetime import date
from typing import Any

from app.db.source import Source
from app.repositories.base import run_query

LEGACY_PATIENT_SEARCH = "dmz/legacy_patient_search.sql"
LEGACY_PATIENT = "dmz/legacy_patient.sql"
LEGACY_NOTES = "dmz/legacy_notes.sql"
LEGACY_NOTE_TEXT = "dmz/legacy_note_text.sql"
LEGACY_PROBLEMS = "dmz/legacy_problems.sql"
LEGACY_ALLERGIES = "dmz/legacy_allergies.sql"
LEGACY_ALLERGY_REACTIONS = "dmz/legacy_allergy_reactions.sql"
LEGACY_MEDICATIONS = "dmz/legacy_medications.sql"


def like_prefix(value: str | None) -> str | None:
    """'smi' → 'smi%' with LIKE wildcards escaped using '!' (ESCAPE '!')."""
    if not value:
        return None
    escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_").replace("[", "![")
    return f"{escaped}%"


def legacy_patient_search(
    last_name: str | None,
    first_name: str | None,
    dob: date | None,
    legacy_id: str | None,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    params = {
        "last_name_like": like_prefix(last_name),
        "first_name_like": like_prefix(first_name),
        "dob": dob,
        "legacy_id": legacy_id,
        "offset": offset,
        "limit": limit,
    }
    return run_query(Source.DMZ, LEGACY_PATIENT_SEARCH, params)


def legacy_patient(person_key: int) -> dict[str, Any] | None:
    rows = run_query(Source.DMZ, LEGACY_PATIENT, {"person_key": person_key})
    return rows[0] if rows else None


def legacy_notes(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_NOTES, {"person_key": person_key})


def legacy_note_text(person_key: int, note_id: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_NOTE_TEXT, {"person_key": person_key, "note_id": note_id})


def legacy_problems(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_PROBLEMS, {"person_key": person_key})


def legacy_allergies(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_ALLERGIES, {"person_key": person_key})


def legacy_allergy_reactions(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_ALLERGY_REACTIONS, {"person_key": person_key})


def legacy_medications(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_MEDICATIONS, {"person_key": person_key})
