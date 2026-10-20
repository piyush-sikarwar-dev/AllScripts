"""EMR (HPSITE) read-only queries — one function per .sql file."""

from datetime import date, datetime
from typing import Any

from app.db.source import Source
from app.repositories.base import run_query, run_scalar

PATIENT_SEARCH = "emr/patient_search.sql"
LAST_VISITS = "emr/last_visit_for_patients.sql"
MRNS = "emr/mrn_for_patients.sql"
PATIENT_HEADER_FULL = "emr/patient_header_full.sql"
PATIENT_INSURANCES = "emr/patient_insurances.sql"
PATIENT_PROFILE = "emr/patient_profile.sql"
PATIENT_RACE = "emr/patient_race.sql"
PATIENT_ETHNICITY = "emr/patient_ethnicity.sql"
PATIENT_CONTACTS = "emr/patient_contacts.sql"
PATIENT_CARE_TEAM = "emr/patient_care_team.sql"
PATIENT_CONSENTS = "emr/patient_consents.sql"
PATIENT_PHOTO = "emr/patient_photo.sql"
HISTORY_ITEMS = "emr/history_items.sql"
HISTORY_ATTRIBUTES = "emr/history_attributes.sql"
MEDICATIONS = "emr/medications.sql"
HX_MEDICATIONS = "emr/hx_medications.sql"
LAST_VISIT_DETAIL = "emr/last_visit_detail.sql"
LAB_RESULTS = "emr/lab_results.sql"
VITALS = "emr/vitals.sql"
VISIT_VITALS = "emr/visit_vitals.sql"
VISITS = "emr/visits.sql"
VISITS_OF_TYPES = "emr/visits_of_types.sql"
VISIT_ONE = "emr/visit_one.sql"
VISIT_ASSESSMENT = "emr/visit_assessment.sql"
VISIT_PLAN = "emr/visit_plan.sql"
VISIT_ADDENDA = "emr/visit_addenda.sql"
VISIT_TEXT_NOTES = "emr/visit_text_notes.sql"
VISIT_DOCUMENTS = "emr/visit_documents.sql"
PATIENT_DOCUMENTS = "emr/patient_documents.sql"
DOCUMENT_CONTENT = "emr/document_content.sql"
TRANSCRIPTIONS = "emr/transcriptions.sql"
TRANSCRIPTION_TEXT = "emr/transcription_text.sql"
SCAN_DOCUMENTS = "emr/scan_documents.sql"
SCAN_DOCUMENT_PAGES = "emr/scan_document_pages.sql"
PATIENT_NAMES = "emr/patient_names.sql"
TABLE_ROW_COUNT = "meta/table_row_count.sql"


def like_prefix(value: str | None) -> str | None:
    """'Smi' → 'Smi%' with LIKE wildcards in user input escaped (ESCAPE '\\')."""
    if not value:
        return None
    escaped = (
        value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace("[", "\\[")
    )
    return f"{escaped}%"


def patient_search(
    *,
    last_name: str | None,
    first_name: str | None,
    dob: date | None,
    chart_id: str | None,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    return run_query(
        Source.EMR,
        PATIENT_SEARCH,
        {
            "last_name_like": like_prefix(last_name),
            "first_name_like": like_prefix(first_name),
            "dob": dob,
            "chart_id": chart_id,
            "offset": offset,
            "limit": limit,
        },
    )


def last_visits(emr_ids: list[int]) -> dict[int, datetime]:
    if not emr_ids:
        return {}
    rows = run_query(Source.EMR, LAST_VISITS, {"emr_ids": emr_ids}, expanding=("emr_ids",))
    return {int(r["emr_id"]): r["last_visit"] for r in rows if r["last_visit"] is not None}


def mrns(emr_ids: list[int]) -> dict[int, str]:
    if not emr_ids:
        return {}
    rows = run_query(Source.EMR, MRNS, {"emr_ids": emr_ids}, expanding=("emr_ids",))
    return {int(r["emr_id"]): r["mrn"] for r in rows if r["mrn"]}


def table_row_count(schema: str, table: str) -> int:
    count = run_scalar(Source.EMR, TABLE_ROW_COUNT, {"schema_name": schema, "table_name": table})
    return int(count or 0)


def patient_header_full(emr_id: int) -> dict[str, Any] | None:
    """Demographics + address + primary insurance + MRN in one query."""
    rows = run_query(Source.EMR, PATIENT_HEADER_FULL, {"emr_id": emr_id})
    return rows[0] if rows else None


def history_items(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, HISTORY_ITEMS, {"emr_id": emr_id})


def history_attributes(emr_id: int, category_codes: list[int]) -> list[dict[str, Any]]:
    if not category_codes:
        return []
    return run_query(
        Source.EMR,
        HISTORY_ATTRIBUTES,
        {"emr_id": emr_id, "category_codes": category_codes},
        expanding=("category_codes",),
    )


def medications(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, MEDICATIONS, {"emr_id": emr_id})


def hx_medications(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, HX_MEDICATIONS, {"emr_id": emr_id})


def last_visit_detail(emr_id: int, visit_types: list[int]) -> dict[str, Any] | None:
    if not visit_types:
        return None
    rows = run_query(
        Source.EMR,
        LAST_VISIT_DETAIL,
        {"emr_id": emr_id, "visit_types": visit_types},
        expanding=("visit_types",),
    )
    return rows[0] if rows else None


def lab_results(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, LAB_RESULTS, {"emr_id": emr_id})


def vitals(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, VITALS, {"emr_id": emr_id})


def visits(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, VISITS, {"emr_id": emr_id})


def visits_of_types(emr_id: int, visit_types: list[int]) -> list[dict[str, Any]]:
    if not visit_types:
        return []
    params = {"emr_id": emr_id, "visit_types": visit_types}
    return run_query(Source.EMR, VISITS_OF_TYPES, params, expanding=("visit_types",))


def visit_one(emr_id: int, contact_id: int) -> dict[str, Any] | None:
    rows = run_query(Source.EMR, VISIT_ONE, {"emr_id": emr_id, "contact_id": contact_id})
    return rows[0] if rows else None


def visit_assessment(encounter_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, VISIT_ASSESSMENT, {"encounter_id": encounter_id})


def visit_plan(encounter_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, VISIT_PLAN, {"encounter_id": encounter_id})


def visit_addenda(encounter_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, VISIT_ADDENDA, {"encounter_id": encounter_id})


def visit_text_notes(contact_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, VISIT_TEXT_NOTES, {"contact_id": contact_id})


def visit_documents(emr_id: int, encounter_id: int) -> list[dict[str, Any]]:
    params = {"emr_id": emr_id, "encounter_code": str(encounter_id)}
    return run_query(Source.EMR, VISIT_DOCUMENTS, params)


def patient_documents(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, PATIENT_DOCUMENTS, {"emr_id": emr_id})


def document_content(emr_id: int, document_id: int) -> dict[str, Any] | None:
    params = {"emr_id": emr_id, "document_id": document_id}
    rows = run_query(Source.EMR, DOCUMENT_CONTENT, params)
    return rows[0] if rows else None


def transcriptions(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, TRANSCRIPTIONS, {"emr_id": emr_id})


def transcription_text(emr_id: int, transcription_id: int) -> dict[str, Any] | None:
    params = {"emr_id": emr_id, "transcription_id": transcription_id}
    rows = run_query(Source.EMR, TRANSCRIPTION_TEXT, params)
    return rows[0] if rows else None


def scan_documents(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, SCAN_DOCUMENTS, {"emr_id": emr_id})


def scan_document_pages(emr_id: int, document_id: int) -> list[dict[str, Any]]:
    params = {"emr_id": emr_id, "document_id": document_id}
    return run_query(Source.EMR, SCAN_DOCUMENT_PAGES, params)


def patient_names(emr_ids: list[int]) -> list[dict[str, Any]]:
    if not emr_ids:
        return []
    return run_query(Source.EMR, PATIENT_NAMES, {"emr_ids": emr_ids}, expanding=("emr_ids",))


def visit_vitals(emr_id: int, contact_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, VISIT_VITALS, {"emr_id": emr_id, "contact_id": contact_id})


# --- Visits tab (Option C): one visit = one encounter ---------------------------------------------
VISITS_LIST = "emr/visits_list.sql"
VISITS_DIAGNOSES = "emr/visits_diagnoses.sql"
VISITS_YEAR_COUNTS = "emr/visits_year_counts.sql"
VISITS_SUMMARY = "emr/visits_summary.sql"
ENCOUNTER_HEADER = "emr/encounter_header.sql"
ENCOUNTER_TEXT_NOTES = "emr/encounter_text_notes.sql"
ENCOUNTER_VITALS = "emr/encounter_vitals.sql"


def like_contains(value: str | None) -> str | None:
    """'diab' → '%diab%' with LIKE wildcards escaped using '!' (ESCAPE '!')."""
    if not value:
        return None
    escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_").replace("[", "![")
    return f"%{escaped}%"


def _type_params(visit_type_codes: list[int] | None) -> dict[str, Any]:
    """None = all entries. An empty category still needs a non-empty IN list (matches nothing)."""
    if visit_type_codes is None:
        return {"all_types": 1, "visit_type_codes": [0]}
    return {"all_types": 0, "visit_type_codes": visit_type_codes or [-999999]}


def visits_list(
    emr_id: int,
    visit_type_codes: list[int] | None,
    year: int | None,
    q: str | None,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    params = {
        "emr_id": emr_id,
        "year": year,
        "offset": offset,
        "limit": limit,
        "q_like": like_contains(q),
    } | _type_params(visit_type_codes)
    return run_query(Source.EMR, VISITS_LIST, params, expanding=("visit_type_codes",))


def visits_diagnoses(encounter_ids: list[int]) -> list[dict[str, Any]]:
    if not encounter_ids:
        return []
    params = {"encounter_ids": encounter_ids}
    return run_query(Source.EMR, VISITS_DIAGNOSES, params, expanding=("encounter_ids",))


def visits_year_counts(emr_id: int, visit_type_codes: list[int] | None) -> list[dict[str, Any]]:
    params = {"emr_id": emr_id} | _type_params(visit_type_codes)
    return run_query(Source.EMR, VISITS_YEAR_COUNTS, params, expanding=("visit_type_codes",))


def visits_summary(emr_id: int, visit_type_codes: list[int] | None) -> dict[str, Any]:
    params = {"emr_id": emr_id} | _type_params(visit_type_codes)
    return run_query(Source.EMR, VISITS_SUMMARY, params, expanding=("visit_type_codes",))[0]


def encounter_header(emr_id: int, encounter_id: int) -> dict[str, Any] | None:
    rows = run_query(Source.EMR, ENCOUNTER_HEADER, {"emr_id": emr_id, "encounter_id": encounter_id})
    return rows[0] if rows else None


def encounter_text_notes(encounter_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, ENCOUNTER_TEXT_NOTES, {"encounter_id": encounter_id})


def encounter_vitals(emr_id: int, encounter_id: int) -> list[dict[str, Any]]:
    params = {"emr_id": emr_id, "encounter_id": encounter_id}
    return run_query(Source.EMR, ENCOUNTER_VITALS, params)


# --- Notes tab (Option A): note index (metadata only) ------------------------------------------
NOTES_LIST_DOCS = "emr/notes_list_docs.sql"
NOTES_DOC_SOURCES = "emr/notes_doc_sources.sql"
NOTES_LIST_TRANS = "emr/notes_list_trans.sql"


def notes_list_docs(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, NOTES_LIST_DOCS, {"emr_id": emr_id})


def notes_doc_sources(emr_id: int, sources: list[str]) -> list[dict[str, Any]]:
    if not sources:
        return []
    params = {"emr_id": emr_id, "sources": sources}
    return run_query(Source.EMR, NOTES_DOC_SOURCES, params, expanding=("sources",))


def notes_list_trans(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, NOTES_LIST_TRANS, {"emr_id": emr_id})


# --- Problems & allergies tab (Option B) --------------------------------------------------------
HISTORY_ENTRIES = "emr/history_entries.sql"
HISTORY_ENTRY_ATTRIBUTES = "emr/history_entry_attributes.sql"
HISTORY_CHANGES = "emr/history_changes.sql"


def history_entries(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, HISTORY_ENTRIES, {"emr_id": emr_id})


def history_entry_attributes(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, HISTORY_ENTRY_ATTRIBUTES, {"emr_id": emr_id})


def history_changes(emr_id: int, hx_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, HISTORY_CHANGES, {"emr_id": emr_id, "hx_id": hx_id})


# --- Appointments tab ----------------------------------------------------------------------------
APPOINTMENTS = "emr/appointments.sql"


def appointments(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, APPOINTMENTS, {"emr_id": emr_id})


# --- Notes tab: messages saved to the chart and patient-portal messages -------------------------
NOTES_LIST_MESSAGES = "emr/notes_list_messages.sql"
NOTES_LIST_PORTAL = "emr/notes_list_portal.sql"
NOTE_MESSAGE = "emr/note_message.sql"
NOTE_PORTAL = "emr/note_portal.sql"
NOTE_PORTAL_ATTACHMENT = "emr/note_portal_attachment.sql"


def notes_list_messages(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, NOTES_LIST_MESSAGES, {"emr_id": emr_id})


def notes_list_portal(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, NOTES_LIST_PORTAL, {"emr_id": emr_id})


def note_message(emr_id: int, message_id: int) -> dict[str, Any] | None:
    rows = run_query(Source.EMR, NOTE_MESSAGE, {"emr_id": emr_id, "message_id": message_id})
    return rows[0] if rows else None


def note_portal(emr_id: int, portal_id: int) -> dict[str, Any] | None:
    rows = run_query(Source.EMR, NOTE_PORTAL, {"emr_id": emr_id, "portal_id": portal_id})
    return rows[0] if rows else None


def note_portal_attachment(emr_id: int, portal_id: int) -> dict[str, Any] | None:
    params = {"emr_id": emr_id, "portal_id": portal_id}
    rows = run_query(Source.EMR, NOTE_PORTAL_ATTACHMENT, params)
    return rows[0] if rows else None


# --- Documents tab: chart attachments -------------------------------------------------------------
CHART_ATTACHMENTS = "emr/chart_attachments.sql"
CHART_ATTACHMENT_FILE = "emr/chart_attachment_file.sql"
CHART_ATTACHMENT_TEXT = "emr/chart_attachment_text.sql"


def chart_attachments(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, CHART_ATTACHMENTS, {"emr_id": emr_id})


def chart_attachment_file(emr_id: int, attachment_id: int) -> dict[str, Any] | None:
    params = {"emr_id": emr_id, "attachment_id": attachment_id}
    rows = run_query(Source.EMR, CHART_ATTACHMENT_FILE, params)
    return rows[0] if rows else None


def chart_attachment_text(emr_id: int, attachment_id: int) -> str | None:
    params = {"emr_id": emr_id, "attachment_id": attachment_id}
    rows = run_query(Source.EMR, CHART_ATTACHMENT_TEXT, params)
    return rows[0]["note_text"] if rows else None


def patient_insurances(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, PATIENT_INSURANCES, {"emr_id": emr_id})


def patient_profile(emr_id: int) -> dict[str, Any] | None:
    rows = run_query(Source.EMR, PATIENT_PROFILE, {"emr_id": emr_id})
    return rows[0] if rows else None


def patient_race(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, PATIENT_RACE, {"emr_id": emr_id})


def patient_ethnicity(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, PATIENT_ETHNICITY, {"emr_id": emr_id})


def patient_contacts(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, PATIENT_CONTACTS, {"emr_id": emr_id})


def patient_care_team(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, PATIENT_CARE_TEAM, {"emr_id": emr_id})


def patient_consents(emr_id: int) -> list[dict[str, Any]]:
    return run_query(Source.EMR, PATIENT_CONSENTS, {"emr_id": emr_id})


def patient_photo(emr_id: int) -> bytes | None:
    rows = run_query(Source.EMR, PATIENT_PHOTO, {"emr_id": emr_id})
    return bytes(rows[0]["photo"]) if rows and rows[0]["photo"] else None
