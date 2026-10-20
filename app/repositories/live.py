"""Real data source (USE_FAKE_DATA=false): same function names and shapes as tests/fakes/repository.

Implemented: dashboard totals, patient list, chart header, history (problems / allergies /
other history), medications and last visit. Other chart areas raise NotConnectedError until their
phase wires them, which renders a friendly page.
"""

import logging
import re
import time
from datetime import date, datetime
from typing import Any

from app.documents.render import (
    DocumentFormatError,
    embedded_images,
    render_document,
    rtf_to_text,
)
from app.formatting import date_us, person_name, sort_key, to_clinic_time
from app.lookups import get_lookups
from app.lookups.note_categories import note_categories
from app.repositories import emr, ntier
from app.repositories.appdb.crosswalk import links_for_emr_ids
from app.repositories.base import parallel
from app.repositories.cache import cached

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
    tables = {
        "patients": "DEMOGRAPHICS",
        "encounters": "ENCOUNTER",
        "lab_results": "LAB_RESULT",
        "scanned_documents": "SCAN_DOCUMENT",
    }
    counts = parallel(*(lambda t=t: emr.table_row_count("HPSITE", t) for t in tables.values()))
    value = dict(zip(tables, counts, strict=True))
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
    links, mrns, last = parallel(
        lambda: links_for_emr_ids(ids), lambda: emr.mrns(ids), lambda: emr.last_visits(ids)
    )
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
                "last_visit": last.get(emr_id),
            }
        )
    return result, total


def last_visits(emr_ids: list[int]) -> dict[int, Any]:
    return emr.last_visits(emr_ids)


@cached
def get_patient(emr_id: int) -> dict[str, Any] | None:
    """Chart header data (shape matches tests/fakes/repository.get_patient)."""
    header, links = parallel(
        lambda: emr.patient_header_full(emr_id), lambda: links_for_emr_ids([emr_id])
    )
    if header is None:
        return None
    ntier_id, dmz_id = links.get(emr_id, (None, None))
    pm = ntier.pm_account(ntier_id) if ntier_id is not None else None
    return {
        "emr_id": emr_id,
        "last_name": header["last_name"],
        "first_name": header["first_name"],
        "middle_initial": header["middle_initial"],
        "dob": header["dob"],
        "dob_mask": header["dob_mask"],
        "sex": header["sex_code"],
        "chart_id": header["mrn"],
        "deceased": bool(header["deceased"]),
        "phone": header["phone"],
        "address": header["address"],
        "city": header["city"],
        "state": header["state"],
        "zip": header["zip"],
        "primary_insurance": header["primary_insurance"],
        "has_photo": bool(header.get("has_photo")),
        "pm_account": ((pm or {}).get("account_number") or "").strip() or None,
        "ntier_id": ntier_id,
        "dmz_id": dmz_id,
    }


@cached
def history(emr_id: int) -> list[dict[str, Any]]:
    """HX_DIAGNOSIS latest revisions, grouped via config/history_categories.yaml."""
    lk = get_lookups()
    allergy_codes = lk.history_codes("allergy")
    rows, attributes = parallel(
        lambda: emr.history_items(emr_id),
        lambda: emr.history_attributes(emr_id, allergy_codes),
    )
    reactions: dict[int, list[tuple[int, str]]] = {}
    for a in attributes:
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


@cached
def medications(emr_id: int) -> list[dict[str, Any]]:
    """Prescriptions (MEDICATIONS) + medication history (HX_MEDICATION), latest revisions."""
    lk = get_lookups()
    prescriptions, med_history = parallel(
        lambda: emr.medications(emr_id), lambda: emr.hx_medications(emr_id)
    )
    items = []
    for r in prescriptions:
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
    for r in med_history:
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


@cached
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


@cached
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


def _vital(r: dict[str, Any]) -> dict[str, Any]:
    lk = get_lookups()

    def unit(code: Any) -> str:
        return "" if code is None else lk.label("unit", code).replace("Unknown (code 0)", "")

    return {
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


@cached
def vitals(emr_id: int) -> list[dict[str, Any]]:
    """VITALS_DATA rows (erroneous readings excluded in SQL)."""
    return [_vital(r) for r in emr.vitals(emr_id)]


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


@cached
def visits(emr_id: int, office_only: bool = False) -> list[dict[str, Any]]:
    """Non-cancelled contacts. office_only=True asks the database for real visits only (same rows
    the service would keep after filtering); all entries otherwise."""
    lk = get_lookups()
    if office_only and not lk.visit_default_office:
        rows = emr.visits_of_types(emr_id, lk.office_visit_codes())
    else:
        rows = emr.visits(emr_id)
    summaries = [_visit_summary(r) for r in rows]
    return [v for v in summaries if v["is_office_visit"]] if office_only else summaries


def _note_body(raw: Any) -> str:
    """Visit note text (NOTES_TEXTDATA): about 5% are stored as RTF (smoke test 2026-10-20);
    those are converted to plain text so RTF codes never reach the screen or the PDF."""
    text = (raw or "").strip()
    if text.startswith("{\\rtf"):
        return rtf_to_text(text)
    return text


def _document_html(emr_id: int, document_id: int) -> str | None:
    row = emr.document_content(emr_id, document_id)
    if row is None:
        return None
    try:
        return render_document(row["content"], document_id)
    except DocumentFormatError:
        log.warning("document %s could not be rendered", document_id)
        return None


def document_image(emr_id: int, document_id: int, index: int) -> tuple[str, bytes] | None:
    """(mime, bytes) of the n-th picture embedded in a clinical document of this patient."""
    row = emr.document_content(emr_id, document_id)  # ownership checked in SQL
    if row is None:
        return None
    try:
        images = embedded_images(row["content"])
    except DocumentFormatError:
        return None
    return images[index] if 0 <= index < len(images) else None


@cached
def visit(emr_id: int, contact_id: int) -> dict[str, Any] | None:
    """Visit detail: assessment, plan, addenda and the visit note (documents first, then text)."""
    r = emr.visit_one(emr_id, contact_id)
    if r is None:
        return None
    lk = get_lookups()
    detail = _visit_summary(r)
    enc = r["encounter_id"]
    assessment, plan, addenda, docs, text_notes = parallel(
        lambda: emr.visit_assessment(enc),
        lambda: emr.visit_plan(enc),
        lambda: emr.visit_addenda(enc),
        lambda: emr.visit_documents(emr_id, enc),
        lambda: emr.visit_text_notes(contact_id),
    )
    assessment = sorted(assessment, key=lambda a: a["sort_order"] or 0)
    detail["assessment"] = [((a["title"] or "").strip() or "Untitled", (a["code"] or "").strip())
                            for a in assessment]  # fmt: skip
    plan = sorted(plan, key=lambda p: p["sort_order"] or 0)
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
        for a in sorted(addenda, key=lambda a: sort_key(a["added"]))
    ]
    docs = sorted(docs, key=lambda d: sort_key(d["created"]))
    note_ids = [d["document_id"] for d in docs if lk.is_visit_note_title(d["title"])]
    bodies = dict(zip(note_ids, parallel(*(lambda i=i: _document_html(emr_id, i)
                                           for i in note_ids)), strict=True))  # fmt: skip
    detail["note_documents"] = []
    detail["other_documents"] = []
    for d in docs:
        meta = {"id": d["document_id"], "title": (d["title"] or "").strip() or "Untitled document",
                "author": (d["author"] or "").strip(), "created": d["created"]}  # fmt: skip
        html = bodies.get(d["document_id"])
        if html:
            detail["note_documents"].append(meta | {"html": html})
        else:
            detail["other_documents"].append(meta)
    texts = [_note_body(n["note_text"]) for n in text_notes]
    detail["note_text"] = "\n\n".join(t for t in texts if t) or None
    return detail


@cached
def visit_vitals(emr_id: int, contact_id: int) -> list[dict[str, Any]]:
    """Readings of one visit only (indexed query), in time order."""
    rows = [_vital(r) for r in emr.visit_vitals(emr_id, contact_id)]
    return sorted(rows, key=lambda v: (sort_key(v["date"]), v["id"]))


@cached
def notes(emr_id: int) -> list[dict[str, Any]]:
    """Notes tab: clinical documents + dictations (metadata only)."""
    documents_rows, transcription_rows = parallel(
        lambda: emr.patient_documents(emr_id), lambda: emr.transcriptions(emr_id)
    )
    items = [
        {
            "kind": "document",
            "id": d["document_id"],
            "date": d["created"],
            "title": (d["title"] or "").strip() or "Untitled document",
            "author": (d["author"] or "").strip() or None,
            "source": "EMR",
        }
        for d in documents_rows
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
        for t in transcription_rows
    ]
    return items


def _message_text(body: Any) -> str | None:
    return (body or "").replace("\r\n", "\n").strip() or None


@cached
def note(emr_id: int, kind: str, note_id: int) -> dict[str, Any] | None:
    """One note's content: sanitised HTML for documents, plain text for dictations."""
    if kind == "document":
        row = emr.document_content(emr_id, note_id)
        if row is None:
            return None
        try:
            html = render_document(row["content"], note_id)
        except DocumentFormatError:
            html = None
        return {"kind": kind, "id": note_id, "date": row["created"],
                "title": (row["title"] or "").strip() or "Untitled document",
                "author": (row["author"] or "").strip() or None,
                "html": html, "text": None, "source": "EMR"}  # fmt: skip
    if kind == "message":
        row = emr.note_message(emr_id, note_id)
        if row is None:
            return None
        lk = get_lookups()
        sender = _provider(row["from_last"], row["from_first"], row["from_title"])
        recipient = _provider(row["to_last"], row["to_first"], row["to_title"])
        to = recipient if recipient != "—" else (row["to_addressees"] or "").strip() or None
        fields = [("Type", lk.label("msg_type", row["msg_type"])),
                  ("From", None if sender == "—" else sender), ("To", to),
                  ("Call-back phone", (row["phone"] or "").strip() or None),
                  ("Subject", (row["subject"] or "").strip() or None)]  # fmt: skip
        return {"kind": kind, "id": note_id, "date": row["sent"],
                "title": (row["subject"] or "").strip() or "(no subject)",
                "author": None if sender == "—" else sender, "html": None,
                "text": _message_text(row["body"]),
                "message_fields": [(k, v) for k, v in fields if v], "source": "EMR"}  # fmt: skip
    if kind == "portal":
        row = emr.note_portal(emr_id, note_id)
        if row is None:
            return None
        who = _provider(row["prov_last"], row["prov_first"], row["prov_title"])
        fields = [("Type", get_lookups().label("portal_direction", row["msg_type"])),
                  ("Provider", None if who == "—" else who),
                  ("Subject", (row["subject"] or "").strip() or None),
                  ("Attachment", (row["attachment_name"] or "").strip() or None)]  # fmt: skip
        return {"kind": kind, "id": note_id, "date": row["sent"],
                "title": (row["subject"] or "").strip() or "(no subject)",
                "author": None if who == "—" else who, "html": None,
                "text": _message_text(row["body"]),
                "message_fields": [(k, v) for k, v in fields if v],
                "attachment_name": ((row["attachment_name"] or "").strip() or "Attachment")
                if row["has_attachment"] else None,
                "source": "EMR"}  # fmt: skip
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


def patient_names(emr_ids: list[int]) -> dict[int, str]:
    """Display names for a page of patients (one query)."""
    return {
        int(r["emr_id"]): person_name(r["last_name"], r["first_name"], r["middle_initial"])
        for r in emr.patient_names(emr_ids)
    }


@cached
def documents(emr_id: int) -> list[dict[str, Any]]:
    """Documents tab: scanned documents (+ page counts) and clinical documents."""
    lk = get_lookups()
    scans, clinical, attachments = parallel(
        lambda: emr.scan_documents(emr_id),
        lambda: emr.patient_documents(emr_id),
        lambda: emr.chart_attachments(emr_id),
    )
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
        for d in scans
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
        for d in clinical
    ]
    for a in attachments:
        who = _provider(a["provider_last"], a["provider_first"], a["provider_title"])
        file_format = (a["file_format"] or "").strip().lower() or ("rtf" if a["has_text"] else None)
        items.append({
            "kind": "attachment",
            "id": a["attachment_id"],
            "date": a["attached"],
            "type": lk.label("chart_attachment_type", a["content_type"])
            if a["content_type"] is not None else "Chart attachment",
            "title": (a["subject"] or "").strip() or None,
            "pages": None,
            "format": file_format,
            "author": None if who == "—" else who,
            "source": "EMR",
        })  # fmt: skip
    return items


@cached
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


# --- Visits tab (Option C): one visit = one encounter ---------------------------------------------
VISITS_PAGE_SIZE = 25


def _visit_codes(category: str | None) -> list[int] | None:
    return None if category is None else get_lookups().visit_codes(category)


def _encounter_summary(r: dict[str, Any]) -> dict[str, Any]:
    vt = get_lookups().visit_type(r["visit_type_code"])
    first = (r["provider_first"] or "").strip()
    last = (r["provider_last"] or "").strip()
    short = f"{first[:1]}. {last}" if first and last else (last or first or "—")
    return {
        "encounter_id": r["encounter_id"],
        "date": r["visit_date"],
        "visit_type": vt.label,
        "category": vt.category,
        "signed": bool(r["signed"]),
        "provider": _provider(r["provider_last"], r["provider_first"], r["provider_title"]),
        "provider_short": short,
        "location": (r["location"] or "").strip() or None,
        "source": "EMR",
    }


def _diagnoses_by_encounter(encounter_ids: list[int]) -> dict[int, list[tuple[str, str]]]:
    grouped: dict[int, list[tuple[int, str, str]]] = {}
    for d in emr.visits_diagnoses(encounter_ids):
        title = (d["title"] or "").strip()
        if title:
            grouped.setdefault(d["encounter_id"], []).append(
                (d["sort_order"] or 0, (d["code"] or "").strip(), title)
            )
    return {
        enc: [(code, title) for _o, code, title in sorted(items, key=lambda x: x[0])]
        for enc, items in grouped.items()
    }


@cached
def visits_page(
    emr_id: int, category: str | None, year: int | None, q: str | None, page: int
) -> dict[str, Any]:
    """One page (25) of visits, newest first, with each visit's diagnoses."""
    rows = emr.visits_list(
        emr_id, _visit_codes(category), year, q, (page - 1) * VISITS_PAGE_SIZE, VISITS_PAGE_SIZE
    )
    dx = _diagnoses_by_encounter([r["encounter_id"] for r in rows])
    return {
        "total": int(rows[0]["total_count"]) if rows else 0,
        "rows": [
            _encounter_summary(r) | {"diagnoses": dx.get(r["encounter_id"], [])} for r in rows
        ],
    }


@cached
def visits_activity(emr_id: int, category: str | None) -> dict[str, Any]:
    """Per-year counts + summary (total, last visit, top provider, top diagnosis)."""
    codes = _visit_codes(category)
    years, summary = parallel(
        lambda: emr.visits_year_counts(emr_id, codes), lambda: emr.visits_summary(emr_id, codes)
    )
    provider = None
    if summary["provider_count"]:
        provider = _provider(summary["provider_last"], summary["provider_first"],
                             summary["provider_title"])  # fmt: skip
    diagnosis = (summary["dx_title"] or "").strip() or None
    return {
        "years": {int(y["visit_year"]): int(y["visits"]) for y in years if y["visit_year"]},
        "total": int(summary["total"] or 0),
        "last_visit": summary["last_visit"],
        "top_provider": provider,
        "top_provider_count": int(summary["provider_count"] or 0),
        "top_diagnosis": diagnosis,
        "top_diagnosis_code": (summary["dx_code"] or "").strip() or None,
        "top_diagnosis_count": int(summary["dx_count"] or 0),
    }


def _plan_title(p: dict[str, Any]) -> str:
    title = p["lab_title"] or p["procedure_title"] or p["medication_title"] or ""
    return title.strip() or "—"


@cached
def encounter(emr_id: int, encounter_id: int) -> dict[str, Any] | None:
    """Full visit detail for the Visits tab (ownership-checked)."""
    header = emr.encounter_header(emr_id, encounter_id)
    if header is None:
        return None
    lk = get_lookups()
    dx, plan, addenda, docs, text_notes, vitals_rows = parallel(
        lambda: _diagnoses_by_encounter([encounter_id]).get(encounter_id, []),
        lambda: emr.visit_plan(encounter_id),
        lambda: emr.visit_addenda(encounter_id),
        lambda: emr.visit_documents(emr_id, encounter_id),
        lambda: emr.encounter_text_notes(encounter_id),
        lambda: emr.encounter_vitals(emr_id, encounter_id),
    )
    labels = {"LABORATORY": "Lab order", "PROCEDURE": "Procedure", "MEDICATION": "Medication"}
    docs = sorted(docs, key=lambda d: sort_key(d["created"]))
    note_ids = [d["document_id"] for d in docs if lk.is_visit_note_title(d["title"])]
    bodies = dict(zip(note_ids, parallel(*(lambda i=i: _document_html(emr_id, i)
                                           for i in note_ids)), strict=True))  # fmt: skip
    note_documents, other_documents = [], []
    for d in docs:
        meta = {"id": d["document_id"], "title": (d["title"] or "").strip() or "Untitled document",
                "author": (d["author"] or "").strip(), "created": d["created"]}  # fmt: skip
        html = bodies.get(d["document_id"])
        if html:
            note_documents.append(meta | {"html": html})
        else:
            other_documents.append(meta)
    return _encounter_summary(header) | {
        "assessment": dx,
        "plan": [
            f"{labels[p['source']]}: {_plan_title(p)}"
            for p in sorted(plan, key=lambda p: p["sort_order"] or 0)
            if p["source"] in labels
        ],
        "addenda": [
            f"{date_us(a['added'])} · {person_name(a['provider_last'], a['provider_first'])}: "
            f"{(a['note_text'] or '').strip() or '(no text)'}"
            for a in sorted(addenda, key=lambda a: sort_key(a["added"]))
        ],
        "note_documents": note_documents,
        "other_documents": other_documents,
        "text_notes": [
            _note_body(n["note_text"])
            for n in sorted(text_notes, key=lambda n: (sort_key(n["contact_start"]), n["note_id"]))
            if _note_body(n["note_text"])
        ],
        "vitals": sorted(
            (_vital(v) for v in vitals_rows), key=lambda v: (sort_key(v["date"]), v["id"])
        ),
    }


# --- Notes tab (Option A): note index ------------------------------------------------------------


def _app_source(author: Any) -> str | None:
    """'Clinical Module (17.3.1.6)' → 'Clinical Module' (AUTHOR holds the program, not a person)."""
    text = re.sub(r"\s*\([^)]*\)\s*$", "", (author or "").strip())
    return text or None


@cached
def note_index(emr_id: int) -> list[dict[str, Any]]:
    """Every note of the patient (documents + dictations), metadata only, with its map sources
    (for classification), clinician and encounter. Classification happens in the service."""
    sources = note_categories().map_sources()
    docs, doc_sources, dictations, messages, portal = parallel(
        lambda: emr.notes_list_docs(emr_id),
        lambda: emr.notes_doc_sources(emr_id, sources),
        lambda: emr.notes_list_trans(emr_id),
        lambda: emr.notes_list_messages(emr_id),
        lambda: emr.notes_list_portal(emr_id),
    )
    by_doc: dict[int, set[str]] = {}
    for s in doc_sources:
        by_doc.setdefault(s["document_id"], set()).add(s["source"])
    items = []
    for d in docs:
        who = _provider(d["provider_last"], d["provider_first"], d["provider_title"])
        items.append({
            "kind": "document",
            "id": d["document_id"],
            "date": d["created"],
            "title": (d["title"] or "").strip() or "Untitled document",
            "app_source": _app_source(d["app_source"]),
            "who": None if who == "—" else who,
            "encounter_id": d["encounter_id"],
            "map_sources": sorted(by_doc.get(d["document_id"], ())),
            "source": "EMR",
        })  # fmt: skip
    for t in dictations:
        who = _provider(t["provider_last"], t["provider_first"], t["provider_title"])
        items.append({
            "kind": "transcription",
            "id": t["transcription_id"],
            "date": t["dictated"] or t["encounter_date"] or t["transcribed"],
            "title": "Dictation",
            "app_source": "Transcription",
            "who": None if who == "—" else who,
            "encounter_id": t["encounter_id"],
            "map_sources": [],
            "source": "EMR",
        })  # fmt: skip
    lk = get_lookups()
    for m in messages:
        who = _provider(m["from_last"], m["from_first"], m["from_title"])
        items.append({
            "kind": "message",
            "id": m["message_id"],
            "date": m["sent"],
            "title": (m["subject"] or "").strip() or "(no subject)",
            "app_source": lk.label("msg_type", m["msg_type"]),
            "who": None if who == "—" else who,
            "encounter_id": m["encounter_id"],
            "map_sources": [],
            "source": "EMR",
        })  # fmt: skip
    for w in portal:
        who = _provider(w["prov_last"], w["prov_first"], w["prov_title"])
        items.append({
            "kind": "portal",
            "id": w["portal_id"],
            "date": w["sent"],
            "title": (w["subject"] or "").strip() or "(no subject)",
            "app_source": lk.label("portal_direction", w["msg_type"]),
            "who": None if who == "—" else who,
            "encounter_id": w["encounter_id"],
            "map_sources": [],
            "attachment": (w["attachment_name"] or "").strip() or None,
            "source": "EMR",
        })  # fmt: skip
    return items


# --- Problems & allergies tab (Option B) --------------------------------------------------------


def _text(value: Any) -> str | None:
    return (value or "").strip() or None


@cached
def history_entries(emr_id: int) -> list[dict[str, Any]]:
    """Current state of every history entry (latest revision) with its attributes and the
    provider of the visit it was recorded in. Interpretation happens in the service."""
    rows, attributes = parallel(
        lambda: emr.history_entries(emr_id), lambda: emr.history_entry_attributes(emr_id)
    )
    attrs: dict[int, list[dict[str, Any]]] = {}
    for a in attributes:
        if _text(a["title"]) or _text(a["value"]):
            attrs.setdefault(a["hx_id"], []).append({
                "sort_order": a["sort_order"] or 0,
                "title": _text(a["title"]),
                "value": _text(a["value"]),
                "severity_code": a["severity_code"],
            })  # fmt: skip
    entries = []
    for r in rows:
        who = _provider(r["provider_last"], r["provider_first"], r["provider_title"])
        entries.append({
            "id": r["hx_id"],
            "category_code": r["category_code"],
            "code_system": _text(r["code_system"]),
            "code": _text(r["code"]),
            "imo_code": r["imo_code"] or None,
            "title": _text(r["title"]),
            "description": _text(r["description"]),
            "activity_code": r["activity_code"],
            "significance_code": r["significance_code"],
            "acuity_code": r["acuity_code"],
            "onset": r["onset"],
            "onset_mask": r["onset_mask"],
            "resolved": r["resolved"],
            "comments": _text(r["comments"]),
            "basis": _text(r["basis"]),
            "reason": _text(r["reason"]),
            "recorded": r["recorded"],
            "provider": None if who == "—" else who,
            "attributes": sorted(attrs.get(r["hx_id"], []), key=lambda a: a["sort_order"]),
            "source": "EMR",
        })  # fmt: skip
    return entries


@cached
def history_changes(emr_id: int, hx_id: int) -> list[dict[str, Any]]:
    """Every revision of one entry of this patient, oldest first (ownership-checked in SQL)."""
    revisions = []
    for r in emr.history_changes(emr_id, hx_id):
        who = _provider(r["provider_last"], r["provider_first"], r["provider_title"])
        revisions.append({
            "revision": r["revision"],
            "changed": r["changed"],
            "title": _text(r["title"]),
            "activity_code": r["activity_code"],
            "significance_code": r["significance_code"],
            "onset": r["onset"],
            "onset_mask": r["onset_mask"],
            "resolved": r["resolved"],
            "comments": _text(r["comments"]),
            "reason": _text(r["reason"]),
            "provider": None if who == "—" else who,
        })  # fmt: skip
    return revisions


# --- Appointments tab -----------------------------------------------------------------------------


def _hhmm(value: Any) -> str | None:
    """PM times are stored as HHMM integers (924 = 9:24 AM)."""
    if not value or not isinstance(value, int) or not 0 < value < 2400 or value % 100 > 59:
        return None
    hour, minute = divmod(value, 100)
    return f"{hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}"


def _clock(value: Any) -> str | None:
    if value is None:
        return None
    local = to_clinic_time(value) if value.tzinfo else value
    return f"{local.hour % 12 or 12}:{local:%M} {'AM' if local.hour < 12 else 'PM'}"


def _local_day(value: Any) -> date | None:
    if value is None:
        return None
    return (to_clinic_time(value) if value.tzinfo else value).date()


@cached
def appointments(emr_id: int, ntier_id: int | None) -> list[dict[str, Any]]:
    """EMR schedule (2010 onwards), enriched with the practice-management appointment when it is
    the same patient's on the same day (type, duration, PM status, cancellation reason). PM
    appointments with no EMR row are added. Status interpretation happens in the service."""
    if ntier_id is not None:
        emr_rows, pm_rows = parallel(
            lambda: emr.appointments(emr_id), lambda: ntier.appointments(ntier_id)
        )
    else:
        emr_rows, pm_rows = emr.appointments(emr_id), []
    pm_by_id = {int(r["pm_id"]): r for r in pm_rows}
    used: set[int] = set()
    items = []
    for r in emr_rows:
        pm_key = str(r["pm_id"] or "").strip()
        pm = pm_by_id.get(int(pm_key)) if pm_key.isdigit() and len(pm_key) <= 9 else None
        if pm is not None and _local_day(pm["starts"]) != _local_day(r["starts"]):
            pm = None  # same id, different day: an id from the older PM system
        if pm is not None:
            used.add(int(pm["pm_id"]))
        who = _provider(r["provider_last"], r["provider_first"], r["provider_title"])
        items.append({
            "id": f"emr-{r['sched_id']}",
            "starts": r["starts"],
            "emr_status": r["status_code"],
            "pm_status": (pm["status"] or "").strip() if pm else None,
            "type": _text(pm["appt_type"]) if pm else None,
            "duration": pm["duration"] if pm else None,
            "provider": None if who == "—" else who,
            "location": _text(r["location"]) or (_text(pm["location"]) if pm else None),
            "cancel_reason": _text(pm["cancel_reason"]) if pm else None,
            "arrived": _clock(r["time_in"]) or (_hhmm(pm["time_in"]) if pm else None),
            "left": _clock(r["time_out"]) or (_hhmm(pm["check_out"]) if pm else None),
            "comment": _text(r["comment"]) or (_text(pm["comment"]) if pm else None),
            "sources": ["EMR", "PM"] if pm else ["EMR"],
        })  # fmt: skip
    for pm_id, pm in pm_by_id.items():
        if pm_id in used:
            continue
        items.append({
            "id": f"pm-{pm_id}",
            "starts": pm["starts"],
            "emr_status": None,
            "pm_status": (pm["status"] or "").strip(),
            "type": _text(pm["appt_type"]),
            "duration": pm["duration"],
            "provider": _text(pm["resource"]),
            "location": _text(pm["location"]),
            "cancel_reason": _text(pm["cancel_reason"]),
            "arrived": _hhmm(pm["time_in"]),
            "left": _hhmm(pm["check_out"]),
            "comment": _text(pm["comment"]),
            "sources": ["PM"],
        })  # fmt: skip
    return items


def portal_attachment(emr_id: int, portal_id: int) -> dict[str, Any] | None:
    """Attachment bytes of one portal message of this patient (not cached: can be large)."""
    return emr.note_portal_attachment(emr_id, portal_id)


def attachment_file(emr_id: int, attachment_id: int) -> dict[str, Any] | None:
    """File bytes of one chart attachment of this patient (not cached: can be large)."""
    return emr.chart_attachment_file(emr_id, attachment_id)


@cached
def attachment_text(emr_id: int, attachment_id: int) -> str | None:
    """Plain text of an RTF-only chart attachment of this patient."""
    rtf = emr.chart_attachment_text(emr_id, attachment_id)
    return rtf_to_text(rtf) if rtf else None


@cached
def patient_details(emr_id: int, ntier_id: int | None) -> dict[str, Any]:
    """Insurance (EMR + PM), race, ethnicity, marital status, contacts, guarantor, care team,
    consents and photo flag of one patient (shape matches tests/fakes/repository)."""
    calls = [
        lambda: emr.patient_insurances(emr_id),
        lambda: emr.patient_profile(emr_id),
        lambda: emr.patient_race(emr_id),
        lambda: emr.patient_ethnicity(emr_id),
        lambda: emr.patient_contacts(emr_id),
        lambda: emr.patient_care_team(emr_id),
        lambda: emr.patient_consents(emr_id),
        lambda: ntier.patient_policies(ntier_id) if ntier_id is not None else [],
    ]
    insurances, profile, race, ethnicity, contacts, care_team, consents, pm_policies = parallel(
        *calls
    )
    return {
        "insurances": insurances,
        "pm_policies": pm_policies,
        "profile": profile or {},
        "race": [r["code"] for r in race],
        "ethnicity": [r["code"] for r in ethnicity],
        "contacts": contacts,
        "care_team": care_team,
        "consents": consents,
    }


def patient_photo(emr_id: int) -> bytes | None:
    return emr.patient_photo(emr_id)


def _fill_key(r: dict[str, Any]) -> tuple:
    return tuple(
        str(r.get(k) or "").strip().upper()
        for k in ("drug_name", "strength", "quantity", "written_date", "last_fill_date", "pharmacy")
    )


@cached
def pharmacy_fills(emr_id: int) -> list[dict[str, Any]]:
    """Surescripts fill history, newest fill first, exact repeats (from later requests) merged."""
    rows = sorted(emr.pharmacy_fills(emr_id), key=lambda r: r["fill_id"])
    unique: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        unique.setdefault(_fill_key(r), r)
    out = list(unique.values())
    out.sort(
        key=lambda r: (sort_key(r["last_fill_date"]), sort_key(r["written_date"])), reverse=True
    )
    return out


@cached
def lab_orders(emr_id: int) -> list[dict[str, Any]]:
    """Lab orders with their own status, newest order first."""
    rows = emr.lab_orders(emr_id)
    rows.sort(key=lambda r: (sort_key(r["ordered_at"]), r["order_id"]), reverse=True)
    return rows


@cached
def reminders(emr_id: int) -> list[dict[str, Any]]:
    """Clinical reminders, newest due date first."""
    rows = emr.reminders(emr_id)
    rows.sort(key=lambda r: (sort_key(r["due_at"]), r["reminder_id"]), reverse=True)
    return rows


@cached
def referrals(ntier_id: int | None) -> list[dict[str, Any]]:
    """Referrals received (PM), newest first, each with its diagnoses."""
    if ntier_id is None:
        return []
    rows, diagnoses = parallel(
        lambda: ntier.incoming_referrals(ntier_id),
        lambda: ntier.incoming_referral_diagnoses(ntier_id),
    )
    by_referral: dict[int, list[dict[str, Any]]] = {}
    for d in diagnoses:
        by_referral.setdefault(d["referral_id"], []).append(d)
    for r in rows:
        r["diagnoses"] = by_referral.get(r["referral_id"], [])
    rows.sort(key=lambda r: (sort_key(r["referral_date"]), r["referral_id"]), reverse=True)
    return rows


_phi_cache: tuple[float, list[dict[str, Any]]] | None = None


def phi_requests() -> list[dict[str, Any]]:
    """Release requests recorded in Allscripts (whole table, 659 rows; cached 24 h), newest first,
    each with the information it asked for."""
    global _phi_cache
    now = time.monotonic()
    if _phi_cache and _phi_cache[0] > now:
        return [dict(r) for r in _phi_cache[1]]
    rows, info = parallel(emr.phi_requests, emr.phi_request_info)
    asked: dict[int, list[int]] = {}
    for i in info:
        asked.setdefault(i["request_id"], []).append(i["code"])
    for r in rows:
        r["requested"] = sorted(asked.get(r["request_id"], []))
    rows.sort(key=lambda r: (sort_key(r["entered_at"]), r["request_id"]), reverse=True)
    _phi_cache = (now + TOTALS_TTL_SECONDS, rows)
    return [dict(r) for r in rows]
