"""Medications tab (MEDICATIONS + HX_MEDICATION, later + pre-2010)."""

from app.crosswalk import PatientRef
from app.formatting import or_dash, partial_date
from app.models.chart import MedicationRow
from app.models.common import Pager, paginate
from app.repositories import source_repository
from app.services import call

MED_FILTERS = ("active", "all")


def med_row(m: dict) -> MedicationRow:
    return MedicationRow(
        name=m["name"],
        instructions=or_dash(m["sig"]),
        start=partial_date(m["start"], m["start_precision"]),
        end=partial_date(m["end"], m["end_precision"]),
        status=or_dash(m["status"]),
        source=m["source"],
    )


async def medication_items(ref: PatientRef, active_only: bool) -> list[dict]:
    rows = await call(source_repository().medications, ref.emr_id)
    if active_only:
        rows = [m for m in rows if m.get("is_active", m["status"] == "Active")]
    # De-duplicate same title + start date (first source wins: EMR before history).
    seen: set[tuple[str, object]] = set()
    unique = []
    for m in rows:
        dedupe_key = (m["name"].strip().lower(), m["start"])
        if dedupe_key not in seen:
            seen.add(dedupe_key)
            unique.append(m)
    unique.sort(key=lambda m: (m["start"] is not None, m["start"]), reverse=True)
    return unique


async def meds_tab(
    ref: PatientRef, page: int | None, med_filter: str
) -> tuple[list[MedicationRow], Pager, str]:
    med_filter = med_filter if med_filter in MED_FILTERS else "active"
    rows = await medication_items(ref, active_only=med_filter == "active")
    page_rows, pager = paginate(rows, page or 1)
    return [med_row(m) for m in page_rows], pager, med_filter
