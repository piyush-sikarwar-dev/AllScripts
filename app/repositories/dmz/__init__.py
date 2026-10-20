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
LEGACY_CLINICAL_ITEMS = "dmz/legacy_clinical_items.sql"
LEGACY_DOCUMENTS = "dmz/legacy_documents.sql"
LEGACY_DOCUMENT_FILE = "dmz/legacy_document_file.sql"
LEGACY_LAB_ORDERS = "dmz/legacy_lab_orders.sql"
LEGACY_LAB_TESTS = "dmz/legacy_lab_tests.sql"
LEGACY_LAB_RESULTS = "dmz/legacy_lab_results.sql"
LEGACY_LAB_RESULT_COMMENTS = "dmz/legacy_lab_result_comments.sql"
LEGACY_LAB_TASK_COMMENTS = "dmz/legacy_lab_task_comments.sql"
LEGACY_LAB_DIAGNOSES = "dmz/legacy_lab_diagnoses.sql"
LEGACY_NOTE_RESULT_LINKS = "dmz/legacy_note_result_links.sql"
LEGACY_PHOTO = "dmz/legacy_photo.sql"
LEGACY_EXTERNAL_IDS = "dmz/legacy_external_ids.sql"
LEGACY_PHARMACIES = "dmz/legacy_pharmacies.sql"
LEGACY_CONSENT = "dmz/legacy_consent.sql"
LEGACY_PAST_HISTORY = "dmz/legacy_past_history.sql"
LEGACY_PROCEDURES = "dmz/legacy_procedures.sql"
LEGACY_ACCOUNT_NOTES = "dmz/legacy_account_notes.sql"


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


def legacy_clinical_items(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_CLINICAL_ITEMS, {"person_key": person_key})


def legacy_documents(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_DOCUMENTS, {"person_key": person_key})


def legacy_document_file(person_key: int, document_id: int) -> dict[str, Any] | None:
    params = {"person_key": person_key, "document_id": document_id}
    rows = run_query(Source.DMZ, LEGACY_DOCUMENT_FILE, params)
    return rows[0] if rows else None


def legacy_lab_orders(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_LAB_ORDERS, {"person_key": person_key})


def legacy_lab_tests(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_LAB_TESTS, {"person_key": person_key})


def legacy_lab_results(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_LAB_RESULTS, {"person_key": person_key})


def legacy_lab_result_comments(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_LAB_RESULT_COMMENTS, {"person_key": person_key})


def legacy_lab_task_comments(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_LAB_TASK_COMMENTS, {"person_key": person_key})


def legacy_lab_diagnoses(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_LAB_DIAGNOSES, {"person_key": person_key})


def legacy_note_result_links(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_NOTE_RESULT_LINKS, {"person_key": person_key})


def legacy_photo(person_key: int) -> bytes | None:
    rows = run_query(Source.DMZ, LEGACY_PHOTO, {"person_key": person_key})
    return bytes(rows[0]["photo"]) if rows and rows[0]["photo"] else None


def legacy_external_ids(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_EXTERNAL_IDS, {"person_key": person_key})


def legacy_pharmacies(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_PHARMACIES, {"person_key": person_key})


def legacy_consent(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_CONSENT, {"person_key": person_key})


def legacy_past_history(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_PAST_HISTORY, {"person_key": person_key})


def legacy_procedures(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_PROCEDURES, {"person_key": person_key})


def legacy_account_notes(person_key: int) -> list[dict[str, Any]]:
    return run_query(Source.DMZ, LEGACY_ACCOUNT_NOTES, {"person_key": person_key})
