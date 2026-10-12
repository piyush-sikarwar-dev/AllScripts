"""EMR (HPSITE) read-only queries — one function per .sql file."""

from datetime import date, datetime
from typing import Any

from app.db.source import Source
from app.repositories.base import run_query, run_scalar

PATIENT_SEARCH = "emr/patient_search.sql"
LAST_VISITS = "emr/last_visit_for_patients.sql"
MRNS = "emr/mrn_for_patients.sql"
PATIENT_HEADER = "emr/patient_header.sql"
PRIMARY_INSURANCE = "emr/primary_insurance.sql"
HISTORY_ITEMS = "emr/history_items.sql"
HISTORY_ATTRIBUTES = "emr/history_attributes.sql"
MEDICATIONS = "emr/medications.sql"
HX_MEDICATIONS = "emr/hx_medications.sql"
LAST_VISIT_DETAIL = "emr/last_visit_detail.sql"
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


def patient_header(emr_id: int) -> dict[str, Any] | None:
    rows = run_query(Source.EMR, PATIENT_HEADER, {"emr_id": emr_id})
    return rows[0] if rows else None


def primary_insurance(emr_id: int) -> str | None:
    rows = run_query(Source.EMR, PRIMARY_INSURANCE, {"emr_id": emr_id})
    return rows[0]["carrier_name"] if rows else None


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


def last_visit_detail(emr_id: int) -> dict[str, Any] | None:
    rows = run_query(Source.EMR, LAST_VISIT_DETAIL, {"emr_id": emr_id})
    return rows[0] if rows else None
