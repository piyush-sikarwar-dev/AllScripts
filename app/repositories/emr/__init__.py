"""EMR (HPSITE) read-only queries — one function per .sql file."""

from datetime import date, datetime
from typing import Any

from app.db.source import Source
from app.repositories.base import run_query, run_scalar

PATIENT_SEARCH = "emr/patient_search.sql"
LAST_VISITS = "emr/last_visit_for_patients.sql"
MRNS = "emr/mrn_for_patients.sql"
PATIENT_HEADER_FULL = "emr/patient_header_full.sql"
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
