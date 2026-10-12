"""Real data source (USE_FAKE_DATA=false): same function names and shapes as tests/fakes/repository.

Implemented: dashboard totals, patient list, chart header, history (problems / allergies /
other history), medications and last visit. Other chart areas raise NotConnectedError until their
phase wires them, which renders a friendly page.
"""

import logging
import time
from datetime import date, datetime
from typing import Any

from app.documents.render import DocumentFormatError, render_document, rtf_to_text
from app.formatting import date_us, person_name, sort_key, to_clinic_time
from app.lookups import get_lookups
from app.repositories import emr, ntier
from app.repositories.appdb.crosswalk import links_for_emr_ids

log = logging.getLogger("app.repositories")

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


def _provider(last: Any, first: Any, title: Any = None) -> str:
    provider = person_name(last, first)
    title = (title or "").strip()
    if title and provider != "—":
        provider = f"{provider} {title}"
    return provider


def last_visit(emr_id: int) -> dict[str, Any] | None:
    """Newest real visit (visit types configured as office visits)."""
    r = emr.last_visit_detail(emr_id, get_lookups().office_visit_codes())
    if r is None:
        return None
    provider = _provider(r["provider_last"], r["provider_first"], r["provider_title"])
    return {
        "start": r["start"],
        "visit_type": get_lookups().visit_type(r["visit_type_code"]).label,
        "provider": provider,
        "location": r["location"],
    }


def _day(value: Any) -> date | None:
    """Calendar day in the clinic time zone (labs/vitals list by day)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return to_clinic_time(value).date() if value.tzinfo else value.date()
    return value


def labs(emr_id: int) -> list[dict[str, Any]]:
    """LAB_RESULT rows; canceled / erroneous results hidden (config/statuses.yaml)."""
    lk = get_lookups()
    items = []
    for r in emr.lab_results(emr_id):
        if lk.is_erroneous("lab_result", r["status_code"]):
            continue
        flag = (r["flags"] or "").strip().upper() or None
        if flag not in lk.lab_flags:
            flag = "A" if r["abnormal"] == 1 else None
        items.append(
            {
                "id": r["result_id"],
                "date": _day(r["observed"] or r["completed"] or r["recorded"]),
                "test": (r["test"] or "").strip() or "Unnamed test",
                "result_text": (r["value"] or "").strip(),
                "units": (r["units"] or "").strip(),
                "range_text": (r["normal_range"] or "").strip() or None,
                "flag": flag,
                "corrected": bool(r["corrected"]),
                "source": "EMR",
            }
        )
    return items


def _number(value: Any) -> str | None:
    """Readable number: Decimal('180.500') -> '180.5'; None/0-length -> None."""
    if value is None or value == "":
        return None
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value).strip() or None


def vitals(emr_id: int) -> list[dict[str, Any]]:
    """VITALS_DATA rows (erroneous readings excluded in SQL)."""
    lk = get_lookups()

    def unit(code: Any) -> str:
        return "" if code is None else lk.label("unit", code).replace("Unknown (code 0)", "")

    return [
        {
            "id": r["vital_id"],
            "contact_id": r["contact_id"],
            "date": r["taken"],
            "systolic": _number(r["systolic"]),
            "diastolic": _number(r["diastolic"]),
            "pulse": _number(r["pulse"]),
            "temp": _number(r["temperature"]),
            "temp_unit": unit(r["temperature_unit"]),
            "weight": _number(r["weight"]),
            "weight_unit": unit(r["weight_unit"]),
            "height": _number(r["height"]),
            "height_unit": unit(r["height_unit"]),
            "spo2": _number(r["spo2"]),
            "pain": _number(r["pain"]),
            "source": "EMR",
        }
        for r in emr.vitals(emr_id)
    ]


def _visit_summary(r: dict[str, Any]) -> dict[str, Any]:
    vt = get_lookups().visit_type(r["visit_type_code"])
    return {
        "contact_id": r["contact_id"],
        "encounter_id": r["encounter_id"],
        "start": r["start"],
        "visit_type": vt.label,
        "is_office_visit": vt.is_office_visit,
        "provider": _provider(r["provider_last"], r["provider_first"], r["provider_title"]),
        "location": r["location"],
        "signed": bool(r["signed"]),
        "diagnoses": (r["diagnoses"] or "").strip(),
        "source": "EMR",
    }


def visits(emr_id: int) -> list[dict[str, Any]]:
    """Every non-cancelled contact; the service filters to real visits by default."""
    return [_visit_summary(r) for r in emr.visits(emr_id)]


def _document_html(emr_id: int, document_id: int) -> str | None:
    row = emr.document_content(emr_id, document_id)
    if row is None:
        return None
    try:
        return render_document(row["content"])
    except DocumentFormatError:
        log.warning("document %s could not be rendered", document_id)
        return None


def visit(emr_id: int, contact_id: int) -> dict[str, Any] | None:
    """Visit detail: assessment, plan, addenda and the visit note (documents first, then text)."""
    r = emr.visit_one(emr_id, contact_id)
    if r is None:
        return None
    lk = get_lookups()
    detail = _visit_summary(r)
    enc = r["encounter_id"]
    assessment = sorted(emr.visit_assessment(enc), key=lambda a: a["sort_order"] or 0)
    detail["assessment"] = [((a["title"] or "").strip() or "Untitled", (a["code"] or "").strip())
                            for a in assessment]  # fmt: skip
    plan = sorted(emr.visit_plan(enc), key=lambda p: p["sort_order"] or 0)
    labels = {"LABORATORY": "Lab order", "PROCEDURE": "Procedure", "MEDICATION": "Medication"}
    detail["plan"] = [
        f"{labels.get(p['source'], 'Plan item')}: "
        f"{(p['lab_title'] or p['procedure_title'] or p['medication_title'] or '').strip() or '—'}"
        for p in plan
        if p["source"] in labels
    ]
    detail["addenda"] = [
        f"{date_us(a['added'])} · {person_name(a['provider_last'], a['provider_first'])}: "
        f"{(a['note_text'] or '').strip() or '(no text)'}"
        for a in sorted(emr.visit_addenda(enc), key=lambda a: sort_key(a["added"]))
    ]
    docs = sorted(emr.visit_documents(emr_id, enc), key=lambda d: sort_key(d["created"]))
    detail["note_documents"] = []
    detail["other_documents"] = []
    for d in docs:
        meta = {"id": d["document_id"], "title": (d["title"] or "").strip() or "Untitled document",
                "author": (d["author"] or "").strip(), "created": d["created"]}  # fmt: skip
        if lk.is_visit_note_title(d["title"]):
            html = _document_html(emr_id, d["document_id"])
            if html:
                detail["note_documents"].append(meta | {"html": html})
                continue
        detail["other_documents"].append(meta)
    texts = [(n["note_text"] or "").strip() for n in emr.visit_text_notes(contact_id)]
    detail["note_text"] = "\n\n".join(t for t in texts if t) or None
    return detail


def visit_vitals(emr_id: int, contact_id: int) -> list[dict[str, Any]]:
    return [v for v in vitals(emr_id) if v["contact_id"] == contact_id]


def notes(emr_id: int) -> list[dict[str, Any]]:
    """Notes tab: clinical documents + dictations (metadata only)."""
    items = [
        {
            "kind": "document",
            "id": d["document_id"],
            "date": d["created"],
            "title": (d["title"] or "").strip() or "Untitled document",
            "author": (d["author"] or "").strip() or None,
            "source": "EMR",
        }
        for d in emr.patient_documents(emr_id)
    ]
    items += [
        {
            "kind": "transcription",
            "id": t["transcription_id"],
            "date": t["dictated"] or t["transcribed"] or t["encounter_date"],
            "title": "Dictation",
            "author": _provider(t["provider_last"], t["provider_first"], t["provider_title"]),
            "source": "EMR",
        }
        for t in emr.transcriptions(emr_id)
    ]
    return items


def note(emr_id: int, kind: str, note_id: int) -> dict[str, Any] | None:
    """One note's content: sanitised HTML for documents, plain text for dictations."""
    if kind == "document":
        row = emr.document_content(emr_id, note_id)
        if row is None:
            return None
        try:
            html = render_document(row["content"])
        except DocumentFormatError:
            html = None
        return {"kind": kind, "id": note_id, "date": row["created"],
                "title": (row["title"] or "").strip() or "Untitled document",
                "author": (row["author"] or "").strip() or None,
                "html": html, "text": None, "source": "EMR"}  # fmt: skip
    if kind == "transcription":
        row = emr.transcription_text(emr_id, note_id)
        if row is None:
            return None
        return {"kind": kind, "id": note_id, "date": row["dictated"] or row["encounter_date"],
                "title": "Dictation",
                "author": person_name(row["provider_last"], row["provider_first"]),
                "html": None, "text": rtf_to_text(row["rtf"] or "") or None,
                "source": "EMR"}  # fmt: skip
    return None


def documents(emr_id: int) -> list[dict[str, Any]]:
    """Documents tab: scanned documents (+ page counts) and clinical documents."""
    lk = get_lookups()
    items = [
        {
            "kind": "scan",
            "id": d["document_id"],
            "date": d["document_date"],
            "type": (d["type"] or "").strip() or "Scanned document",
            "title": (d["title"] or "").strip() or None,
            "pages": int(d["pages"] or 0),
            "source": "EMR",
        }
        for d in emr.scan_documents(emr_id)
        if not lk.is_erroneous("scan_document", d["status_code"])
    ]
    items += [
        {
            "kind": "document",
            "id": d["document_id"],
            "date": d["created"],
            "type": "Clinical document",
            "title": (d["title"] or "").strip() or None,
            "pages": None,
            "source": "EMR",
        }
        for d in emr.patient_documents(emr_id)
    ]
    return items


def document_pages(emr_id: int, document_id: int) -> dict[str, Any] | None:
    """One scanned document (ownership-checked) with its pages in order."""
    rows = emr.scan_document_pages(emr_id, document_id)
    if not rows or get_lookups().is_erroneous("scan_document", rows[0]["status_code"]):
        return None
    first = rows[0]
    return {
        "id": document_id,
        "date": first["document_date"],
        "type": (first["type"] or "").strip() or "Scanned document",
        "title": (first["title"] or "").strip() or None,
        "pages": [
            {"page_id": r["page_id"], "location": r["file_location"]}
            for r in rows
            if r["page_id"] is not None
        ],
        "source": "EMR",
    }
