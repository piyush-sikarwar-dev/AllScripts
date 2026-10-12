"""Real data source (USE_FAKE_DATA=false): same function names and shapes as tests/fakes/repository.

Implemented: dashboard totals, patient list, chart header, history (problems / allergies /
other history), medications and last visit. Other chart areas raise NotConnectedError until their
phase wires them, which renders a friendly page.
"""

import time
from datetime import date
from typing import Any

from app.formatting import person_name
from app.lookups import get_lookups
from app.repositories import emr, ntier
from app.repositories.appdb.crosswalk import links_for_emr_ids

TOTALS_TTL_SECONDS = 24 * 3600
_totals_cache: tuple[float, dict[str, int]] | None = None


class NotConnectedError(Exception):
    """This chart area is not yet wired to the source databases."""


def totals() -> dict[str, int]:
    """Catalog row counts (sys.partitions): no table data is read. Cached 24 h."""
    global _totals_cache
    now = time.monotonic()
    if _totals_cache and _totals_cache[0] > now:
        return _totals_cache[1]
    value = {
        "patients": emr.table_row_count("HPSITE", "DEMOGRAPHICS"),
        "encounters": emr.table_row_count("HPSITE", "ENCOUNTER"),
        "lab_results": emr.table_row_count("HPSITE", "LAB_RESULT"),
        "scanned_documents": emr.table_row_count("HPSITE", "SCAN_DOCUMENT"),
    }
    _totals_cache = (now + TOTALS_TTL_SECONDS, value)
    return value


def search_patients(
    *,
    last_name: str | None,
    first_name: str | None,
    dob: date | None,
    chart_id: str | None,
    offset: int,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    rows = emr.patient_search(
        last_name=last_name,
        first_name=first_name,
        dob=dob,
        chart_id=chart_id,
        offset=offset,
        limit=limit,
    )
    total = int(rows[0]["total_count"]) if rows else 0
    ids = [int(r["emr_id"]) for r in rows]
    links = links_for_emr_ids(ids)
    mrns = emr.mrns(ids)
    result = []
    for r in rows:
        emr_id = int(r["emr_id"])
        ntier_id, dmz_id = links.get(emr_id, (None, None))
        result.append(
            {
                "emr_id": emr_id,
                "last_name": r["last_name"],
                "first_name": r["first_name"],
                "middle_initial": r["middle_initial"],
                "dob": r["dob"],
                "dob_mask": r["dob_mask"],
                "sex": r["sex_code"],
                "chart_id": mrns.get(emr_id),
                "deceased": bool(r["deceased"]),
                "ntier_id": ntier_id,
                "dmz_id": dmz_id,
            }
        )
    return result, total


def last_visits(emr_ids: list[int]) -> dict[int, Any]:
    return emr.last_visits(emr_ids)


def get_patient(emr_id: int) -> dict[str, Any] | None:
    """Chart header data (shape matches tests/fakes/repository.get_patient)."""
    header = emr.patient_header(emr_id)
    if header is None:
        return None
    ntier_id, dmz_id = links_for_emr_ids([emr_id]).get(emr_id, (None, None))
    pm = ntier.pm_account(ntier_id) if ntier_id is not None else None
    return {
        "emr_id": emr_id,
        "last_name": header["last_name"],
        "first_name": header["first_name"],
        "middle_initial": header["middle_initial"],
        "dob": header["dob"],
        "dob_mask": header["dob_mask"],
        "sex": header["sex_code"],
        "chart_id": emr.mrns([emr_id]).get(emr_id),
        "deceased": bool(header["deceased"]),
        "phone": header["phone"],
        "address": header["address"],
        "city": header["city"],
        "state": header["state"],
        "zip": header["zip"],
        "primary_insurance": emr.primary_insurance(emr_id),
        "pm_account": ((pm or {}).get("account_number") or "").strip() or None,
        "ntier_id": ntier_id,
        "dmz_id": dmz_id,
    }


def history(emr_id: int) -> list[dict[str, Any]]:
    """HX_DIAGNOSIS latest revisions, grouped via config/history_categories.yaml."""
    lk = get_lookups()
    rows = emr.history_items(emr_id)
    allergy_codes = sorted(
        {
            r["category_code"]
            for r in rows
            if lk.history_category(r["category_code"]).group == "allergy"
        }
    )
    reactions: dict[int, list[tuple[int, str]]] = {}
    for a in emr.history_attributes(emr_id, allergy_codes):
        if a["title"]:
            reactions.setdefault(a["hx_id"], []).append((a["sort_order"] or 0, a["title"].strip()))
    items = []
    for r in rows:
        if lk.is_erroneous("hx_diagnosis", r["activity_code"]):
            continue
        category = lk.history_category(r["category_code"])
        reaction = ", ".join(t for _order, t in sorted(reactions.get(r["hx_id"], []))) or None
        items.append(
            {
                "id": r["hx_id"],
                "group": category.group,
                "category": category.label,
                "title": (r["title"] or "").strip() or "Untitled",
                "code_system": (r["code_system"] or "").strip() or None,
                "code": (r["code"] or "").strip() or None,
                "onset": r["onset"],
                "onset_precision": lk.date_precision(r["onset_mask"]),
                "resolved": r["resolved"],
                "status": lk.label("hx_activity", r["activity_code"]),
                "is_active": r["resolved"] is None
                and lk.is_active("hx_diagnosis", r["activity_code"]),
                "reaction": reaction if category.group == "allergy" else None,
                "source": "EMR",
            }
        )
    return items


def _sig(r: dict[str, Any]) -> str | None:
    dose = " ".join(str(v).strip() for v in (r["dose"], r["dose_unit"]) if v and str(v).strip())
    parts = [str(v).strip() for v in (dose, r["route"], r["frequency"]) if v and str(v).strip()]
    return " ".join(parts) or ((r["intake"] or "").strip() or None)


def _is_current(end_date: Any) -> bool:
    return end_date is None or end_date >= date.today()


def medications(emr_id: int) -> list[dict[str, Any]]:
    """Prescriptions (MEDICATIONS) + medication history (HX_MEDICATION), latest revisions."""
    lk = get_lookups()
    items = []
    for r in emr.medications(emr_id):
        if lk.is_erroneous("medications", r["status_code"]):
            continue
        items.append(
            {
                "id": r["med_id"],
                "name": (r["title"] or "").strip() or "Untitled",
                "sig": _sig(r),
                "start": r["start_date"],
                "start_precision": lk.date_precision(r["start_mask"]),
                "end": r["end_date"],
                "end_precision": lk.date_precision(r["end_mask"]),
                "status": lk.label("med_status", r["status_code"]),
                "is_active": _is_current(r["end_date"])
                and lk.is_active("medications", r["status_code"]),
                "source": "EMR",
            }
        )
    for r in emr.hx_medications(emr_id):
        if lk.is_erroneous("hx_medication", r["activity_code"]):
            continue
        items.append(
            {
                "id": r["hxmed_id"],
                "name": (r["title"] or "").strip() or "Untitled",
                "sig": _sig(r),
                "start": r["start_date"],
                "start_precision": lk.date_precision(r["start_mask"]),
                "end": r["end_date"],
                "end_precision": lk.date_precision(r["end_mask"]),
                "status": lk.label("hx_med_activity", r["activity_code"]),
                "is_active": _is_current(r["end_date"])
                and lk.is_active("hx_medication", r["activity_code"]),
                "source": "EMR history",
            }
        )
    return items


def last_visit(emr_id: int) -> dict[str, Any] | None:
    r = emr.last_visit_detail(emr_id)
    if r is None:
        return None
    provider = person_name(r["provider_last"], r["provider_first"])
    title = (r["provider_title"] or "").strip()
    if title and provider != "—":
        provider = f"{provider} {title}"
    return {
        "start": r["start"],
        "visit_type": get_lookups().visit_type(r["visit_type_code"]).label,
        "provider": provider,
        "location": r["location"],
    }


def _not_connected(*_args: object, **_kwargs: object) -> Any:
    raise NotConnectedError


# Chart areas wired in later phases (6–8).
visits = visit = visit_vitals = notes = labs = vitals = documents = _not_connected
