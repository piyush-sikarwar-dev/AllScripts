"""Medications tab (MEDICATIONS + HX_MEDICATION, later + pre-2010)."""

from app.crosswalk import PatientRef
from app.formatting import EMPTY, date_us, or_dash, partial_date, to_clinic_time
from app.models.chart import MedicationRow, PharmacyFillRow
from app.models.common import Pager, paginate
from app.repositories import source_repository
from app.services import call

MED_FILTERS = ("active", "all", "fills")


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


def _clean(value: object) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def fill_row(r: dict) -> PharmacyFillRow:
    """One pharmacy fill (Surescripts), as dispensed; drug text kept as the pharmacy sent it."""
    name = _clean(r.get("drug_name"))
    strength = _clean(r.get("strength"))
    if strength and strength.upper() not in name.upper():
        name = f"{name} {strength}"
    qty = r.get("quantity")
    days = r.get("days_supply")
    quantity = " · ".join(
        x
        for x in (f"Qty {qty}" if qty is not None else "", f"{days}-day supply" if days else "")
        if x
    )
    return PharmacyFillRow(
        filled=date_us(r.get("last_fill_date")),
        medication=name or EMPTY,
        quantity=quantity or EMPTY,
        instructions=or_dash(_clean(r.get("sig"))),
        prescribed=date_us(r.get("written_date")),
        prescriber=or_dash(_clean(r.get("prescriber"))),
        pharmacy=or_dash(_clean(r.get("pharmacy"))),
        refills=or_dash(_clean(r.get("refills"))),
    )


async def pharmacy_fills(ref: PatientRef) -> list[dict]:
    return await call(source_repository().pharmacy_fills, ref.emr_id)


def checked_on(rows: list[dict]) -> str:
    """When the clinic last pulled the fill history from Surescripts (clinic-local date)."""
    dates = [r["checked_at"] for r in rows if r.get("checked_at")]
    if not dates:
        return EMPTY
    latest = max(dates)
    return date_us(to_clinic_time(latest) if latest.tzinfo else latest)


async def fills_tab(ref: PatientRef, page: int | None) -> tuple[list[PharmacyFillRow], Pager, str]:
    rows = await pharmacy_fills(ref)
    page_rows, pager = paginate(rows, page or 1)
    return [fill_row(r) for r in page_rows], pager, checked_on(rows)
