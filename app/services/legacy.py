"""The separate "Pre-2010 records" section: legacy patient search, chart header, chart notes.

Reads only the DMZ legacy chart (via `legacy_repository()`); it never touches the current EMR /
PM chart, and the current chart never reads from here (CLAUDE.md §4.3, FEATURE_LEGACY_DMZ).
"""

import asyncio
import re
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.config import get_settings
from app.documents.images import cached_png
from app.documents.render import DocumentFormatError
from app.documents.store import DocumentUnavailableError, get_legacy_store
from app.formatting import EMPTY, age, date_us, initials, or_dash, person_name, sort_key
from app.lookups import label
from app.lookups.legacy_codes import LegacyCodes, legacy_codes
from app.models.common import PAGE_SIZE, Pager, clamp_page, paginate
from app.models.legacy import (
    LegacyAllergy,
    LegacyDocPage,
    LegacyDocRow,
    LegacyDocViewer,
    LegacyHeader,
    LegacyHistory,
    LegacyLabComment,
    LegacyLabOrder,
    LegacyLabOrderRow,
    LegacyLabPage,
    LegacyLabReports,
    LegacyLabResult,
    LegacyLabRow,
    LegacyLabTest,
    LegacyMedEntry,
    LegacyMedication,
    LegacyMedications,
    LegacyNote,
    LegacyNotePage,
    LegacyNoteRow,
    LegacyOverview,
    LegacyOverviewItem,
    LegacyPage,
    LegacyProblem,
    LegacyRow,
    LegacySearch,
    LegacyVitalsPage,
    LegacyVitalsRow,
)
from app.repositories import legacy_repository
from app.services import NotFoundError, call
from app.services.patients import parse_dob, parse_name_query

KEY_RE = re.compile(r"DMZ:(\d{1,10})")


def legacy_enabled() -> bool:
    settings = get_settings()
    return settings.feature_legacy_dmz or settings.use_fake_data


def person_key(key: str) -> int:
    """'DMZ:<personkey>' → personkey; NotFoundError for anything else."""
    match = KEY_RE.fullmatch(key)
    if not match:
        raise NotFoundError(key)
    return int(match.group(1))


def _day(value: date | datetime | None) -> date | None:
    return value.date() if isinstance(value, datetime) else value


def _time(value: date | datetime | None) -> str:
    """Legacy times are stored as clinic-local wall-clock times; midnight means 'no time'."""
    if not isinstance(value, datetime) or (value.hour, value.minute) == (0, 0):
        return ""
    return f"{value.hour % 12 or 12}:{value:%M} {value:%p}"


def _phone(area: str | None, number: str | None) -> str:
    digits = re.sub(r"\D", "", f"{area or ''}{number or ''}")
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 7:
        return f"{digits[:3]}-{digits[3:]}"
    return or_dash(" ".join(part for part in (area, number) if part))


def _address(p: dict) -> str:
    street = ", ".join(s.strip() for s in (p.get("street1"), p.get("street2")) if s and s.strip())
    state_zip = " ".join(part for part in (p.get("state"), p.get("zip")) if part)
    city_line = ", ".join(part for part in (p.get("city"), state_zip) if part)
    return ", ".join(part for part in (street, city_line) if part) or EMPTY


def _deceased(value: object) -> bool:
    return str(value or "").strip().upper() in {"Y", "1", "TRUE", "T"}


def _provider(r: dict) -> str:
    name = person_name(r.get("provider_last"), r.get("provider_first"))
    if name == EMPTY:
        return EMPTY
    title = (r.get("provider_title") or "").strip()
    return f"{name}, {title}" if title else name


def build_search(q: str = "", dob: str = "", legacy_id: str = "") -> LegacySearch:
    search = LegacySearch(q=q.strip()[:100], dob=dob.strip()[:10], legacy_id=legacy_id.strip()[:20])
    if search.dob:
        try:
            parse_dob(search.dob)
        except ValueError:
            search.errors["dob"] = "Enter the date of birth as MM/DD/YYYY."
    if search.legacy_id and not re.fullmatch(r"[A-Za-z0-9-]+", search.legacy_id):
        search.errors["legacy_id"] = "Legacy ID can contain only letters, numbers and dashes."
    return search


async def search_patients(search: LegacySearch, page: int | None) -> LegacyPage:
    page = clamp_page(page)
    if search.errors:
        return LegacyPage(search=search, rows=[], pager=Pager(page=1, total=0))
    last, first = parse_name_query(search.q)
    rows, total = await call(
        legacy_repository().search,
        last_name=last,
        first_name=first,
        dob=parse_dob(search.dob),
        legacy_id=search.legacy_id or None,
        offset=(page - 1) * PAGE_SIZE,
        limit=PAGE_SIZE,
    )
    return LegacyPage(
        search=search,
        rows=[
            LegacyRow(
                key=f"DMZ:{r['person_key']}",
                name=person_name(r["last_name"], r["first_name"], r["middle_initial"]),
                dob=date_us(_day(r["dob"])),
                sex=label("sex", r["sex"]),
                legacy_id=or_dash(r["legacy_id"]),
            )
            for r in rows
        ],
        pager=Pager(page=page, total=total),
    )


async def get_header(key: str) -> LegacyHeader:
    p = await call(legacy_repository().patient, person_key(key))
    if p is None:
        raise NotFoundError(key)
    name = person_name(p["last_name"], p["first_name"], p["middle_initial"])
    suffix = (p.get("suffix") or "").strip()
    return LegacyHeader(
        key=key,
        name=f"{name} {suffix}" if suffix and name != EMPTY else name,
        initials=initials(p["last_name"], p["first_name"]),
        dob=date_us(_day(p["dob"])),
        age=age(_day(p["dob"])),
        sex=label("sex", p["sex"]),
        legacy_id=or_dash(p["legacy_id"]),
        phone=_phone(p.get("home_area"), p.get("home_phone")),
        address=_address(p),
        deceased=_deceased(p.get("deceased")),
    )


def _note_row(r: dict) -> LegacyNoteRow:
    return LegacyNoteRow(
        id=int(r["note_id"]),
        date=date_us(_day(r["service_date"])),
        time=_time(r["service_date"]),
        type=_squash(r.get("note_type")) or "Chart note",  # as stored (DEC CONSULT, HIPAA …)
        provider=_provider(r),
        facility=or_dash(r.get("facility")),
        has_text=bool(r["has_text"]),
    )


def _year(r: dict) -> str:
    value = r["service_date"]
    return str(value.year) if value else ""


def _note_type(r: dict) -> str:
    return _squash(r.get("note_type")) or "Chart note"


async def note_page(
    key: str, year: str = "", page: int | None = None, note_type: str = ""
) -> LegacyNotePage:
    pkey = person_key(key)
    repo = legacy_repository()
    rows, links = await asyncio.gather(call(repo.notes, pkey), call(repo.note_result_links, pkey))
    years = sorted({_year(r) for r in rows if _year(r)}, reverse=True)
    types = sorted({_note_type(r) for r in rows})
    year = year if year in years else ""
    note_type = note_type if note_type in types else ""
    chosen = [
        r
        for r in rows
        if (not year or _year(r) == year) and (not note_type or _note_type(r) == note_type)
    ]
    shown, pager = paginate(chosen, clamp_page(page))
    dated = [r["service_date"] for r in rows if r["service_date"]]
    return LegacyNotePage(
        rows=[
            _note_row(r).model_copy(update={"has_results": int(r["note_id"]) in links})
            for r in shown
        ],
        pager=pager,
        years=years,
        year=year,
        types=types,
        type=note_type,
        total_all=len(rows),
        first_date=date_us(_day(min(dated))) if dated else EMPTY,
        last_date=date_us(_day(max(dated))) if dated else EMPTY,
    )


async def get_note(key: str, note_id: int) -> LegacyNote:
    pkey = person_key(key)
    repo = legacy_repository()
    rows = await call(repo.notes, pkey)
    row = next((r for r in rows if int(r["note_id"]) == note_id), None)
    if row is None:
        raise NotFoundError(f"{key}/{note_id}")
    body = await call(repo.note_text, pkey, note_id) if row["has_text"] else None
    item = _note_row(row)
    tests, order_ids = await _note_lab_tests(pkey, note_id)
    return LegacyNote(
        id=item.id,
        date=item.date,
        time=item.time,
        type=item.type,
        provider=item.provider,
        facility=item.facility,
        text=(body or {}).get("text") or None,
        lab_tests=tests,
        lab_order_ids=order_ids,
    )


async def _note_lab_tests(pkey: int, note_id: int) -> tuple[list[LegacyLabTest], list[int]]:
    """The lab tests (with results) a chart note reports, and the lab orders they belong to."""
    repo = legacy_repository()
    links = await call(repo.note_result_links, pkey)
    test_ids = links.get(note_id) or []
    if not test_ids:
        return [], []
    orders = await call(repo.lab_reports, pkey)
    codes = legacy_codes()
    by_id = {
        int(t["test_id"]): (t, int(o["order_id"])) for o in orders for t in o.get("tests") or []
    }
    found = [by_id[t] for t in dict.fromkeys(test_ids) if t in by_id]
    return [_lab_test(t, codes) for t, _ in found], list(dict.fromkeys(o for _, o in found))


# Tabs of the pre-2010 chart, in display order.
TABS: list[tuple[str, str]] = [
    ("overview", "Overview"),
    ("notes", "Chart notes"),
    ("problems", "Problems & allergies"),
    ("meds", "Medications"),
    ("labs", "Lab results"),
    ("vitals", "Vitals"),
    ("docs", "Documents"),
]
TAB_NAMES = {name for name, _ in TABS}
TAB_LABELS = dict(TABS)


def _label_case(value: str | None) -> str:
    """'ENTERED IN ERROR' → 'Entered in error' (legacy lookup labels are stored in capitals)."""
    value = (value or "").strip()
    return value[:1].upper() + value[1:].lower() if value.isupper() else value or EMPTY


def _problem(r: dict, codes: LegacyCodes) -> LegacyProblem:
    desc = " ".join(p for p in (r.get("dx_desc1"), r.get("dx_desc2")) if p and p.strip())
    status_key = r.get("status_key")
    return LegacyProblem(
        id=int(r["problem_id"]),
        name=desc or (r.get("provisional") or "").strip() or or_dash(r.get("dx_code")),
        code=or_dash(r.get("dx_code")),
        onset=date_us(_day(r.get("onset_date"))),
        resolved=date_us(_day(r.get("stop_date"))),
        status=codes.problem_status_label(status_key),
        provider=_provider(r),
        comment=(r.get("comment") or "").strip(),
        active=codes.problem_status.get(status_key or -1) == "Active",
        voided=status_key in codes.problem_voided,
    )


def _allergy(r: dict, codes: LegacyCodes) -> LegacyAllergy:
    allergen = (r.get("allergen") or "").strip()
    detail = (r.get("allergen_desc") or "").strip()
    severity = (r.get("severity") or "").strip()
    status_key = r.get("status_key")
    voided = status_key in codes.allergy_voided or (r.get("active_flag") or "") == "E"
    return LegacyAllergy(
        id=int(r["allergy_id"]),
        allergen=allergen or detail or EMPTY,
        detail=detail if detail and detail.upper() != allergen.upper() else "",
        category=_label_case(r.get("category")),
        reactions=", ".join(r.get("reactions") or []) or EMPTY,
        severity=EMPTY if not severity or severity in codes.severity_blank else severity,
        status=_label_case(r.get("status")) if r.get("status") else f"Unknown (code {status_key})",
        noted=date_us(_day(r.get("noted_date"))),
        provider=_provider(r),
        comment=(r.get("comment") or "").strip(),
        active=status_key == 1 and not voided,
        voided=voided,
    )


async def history(key: str, show_voided: bool = False) -> LegacyHistory:
    pkey = person_key(key)
    repo = legacy_repository()
    prob_rows, alrg_rows = await asyncio.gather(
        call(repo.problems, pkey), call(repo.allergies, pkey)
    )
    codes = legacy_codes()
    probs = [_problem(r, codes) for r in prob_rows]
    alrgs = [_allergy(r, codes) for r in alrg_rows]
    voided = sum(1 for x in [*probs, *alrgs] if x.voided)
    if not show_voided:
        probs = [p for p in probs if not p.voided]
        alrgs = [a for a in alrgs if not a.voided]
    return LegacyHistory(
        problems=probs, allergies=alrgs, show_voided=show_voided, voided_count=voided
    )


_MED_ACTIVE, _MED_VOIDED = 1, {6, 2}  # Medications.MedicationStatus.PROEHR_Med_Status groups


def _squash(*parts: object) -> str:
    """Join non-empty parts with single spaces (legacy names are padded / double-spaced)."""
    return " ".join(" ".join(str(p).split()) for p in parts if p is not None and str(p).strip())


def _amount(value: object) -> str:
    if value is None:
        return ""
    text = f"{value:f}" if isinstance(value, Decimal) else str(value)
    return text.rstrip("0").rstrip(".") if "." in text else text


def _med_entry(r: dict) -> LegacyMedEntry:
    refills = r.get("num_refills")
    return LegacyMedEntry(
        date=date_us(_day(r.get("date_of_service") or r.get("date_written"))),
        status=r.get("status") or f"Unknown (code {r.get('status_key')})",
        sig=_squash(r.get("sig_quantity"), r.get("sig_dose_form"), r.get("sig_frequency")) or EMPTY,
        quantity=_squash(_amount(r.get("amt_dispensed")), r.get("amt_uom")) or EMPTY,
        refills=EMPTY if refills is None else str(refills),
        stopped=date_us(_day(r.get("stop_date"))),
        provider=_provider(r),
    )


def _medication(rows: list[dict]) -> tuple[LegacyMedication, str]:
    """One medication from its entries (oldest first) -> (view model, active | past | voided)."""
    first, last = rows[0], rows[-1]
    entry = _med_entry(last)
    name = _squash(last.get("mdrug_name")) or _squash(
        last.get("udrug_name"), last.get("udrug_strength")
    )
    reason = _squash(last.get("dx_desc")) or _squash(last.get("dx_code"))
    comments = [_squash(r.get("comments")) for r in rows]
    group = last.get("status_group")
    stopped = next((r["stop_date"] for r in reversed(rows) if r.get("stop_date")), None)
    if group in _MED_VOIDED:
        kind = "voided"
    elif group == _MED_ACTIVE and stopped is None:
        kind = "active"
    else:
        kind = "past"
    med = LegacyMedication(
        id=int(last["med_id"]),
        name=name or EMPTY,
        sig=entry.sig,
        reason=reason,
        comment="; ".join(dict.fromkeys(c for c in comments if c)),
        started=date_us(_day(first.get("date_of_service") or first.get("date_written"))),
        last_update=entry.date,
        stopped=date_us(_day(stopped)),
        status=entry.status,
        provider=entry.provider,
        quantity=entry.quantity,
        refills=entry.refills,
        voided=kind == "voided",
        entries=[_med_entry(r) for r in reversed(rows)],
    )
    return med, kind


async def medications(key: str, show_voided: bool = False) -> LegacyMedications:
    """Medications grouped from their entries: active, discontinued, entered in error."""
    rows = await call(legacy_repository().medications, person_key(key))
    chains: dict[int, list[dict]] = {}
    for r in rows:  # already oldest first
        chains.setdefault(int(r["med_id"]), []).append(r)
    groups: dict[str, list[tuple[datetime, LegacyMedication]]] = {
        "active": [],
        "past": [],
        "voided": [],
    }
    for entries in chains.values():
        med, kind = _medication(entries)
        latest = entries[-1].get("date_of_service") or entries[-1].get("date_written")
        groups[kind].append((sort_key(latest), med))
    ordered = {
        k: [m for _, m in sorted(v, key=lambda x: (x[0], x[1].id), reverse=True)]
        for k, v in groups.items()
    }
    return LegacyMedications(
        active=ordered["active"],
        past=ordered["past"],
        voided=ordered["voided"],
        show_voided=show_voided,
    )


def _number(value: str | None) -> float | None:
    try:
        return float((value or "").strip())
    except ValueError:
        return None


def _lab_flag(value: str | None, low: str | None, high: str | None) -> str | None:
    """'H' / 'L' when a plain numeric result is outside a numeric reference range."""
    result, lo, hi = _number(value), _number(low), _number(high)
    if result is None:
        return None
    if hi is not None and result > hi:
        return "H"
    if lo is not None and result < lo:
        return "L"
    return None


def _range(low: str | None, high: str | None) -> str:
    low, high = (low or "").strip(), (high or "").strip()
    if low and high:
        return f"{low} – {high}"
    if high:
        return f"≤ {high}"
    if low:
        return f"≥ {low}"
    return EMPTY


async def _items(key: str) -> tuple[list[dict], list[dict], set[int]]:
    """Clinical values split into (labs, vitals), plus the patient's note ids (for links)."""
    pkey = person_key(key)
    repo = legacy_repository()
    rows, notes = await asyncio.gather(call(repo.clinical_items, pkey), call(repo.notes, pkey))
    codes = legacy_codes()
    labs_rows, vital_rows = [], []
    for r in rows:
        kind = codes.item_kind(r.get("item_name"))
        if kind == "lab":
            labs_rows.append(r)
        elif kind == "vital":
            vital_rows.append(r)
    return labs_rows, vital_rows, {int(n["note_id"]) for n in notes}


def _note_link(note_id: object, note_ids: set[int]) -> int | None:
    return int(note_id) if note_id is not None and int(note_id) in note_ids else None


async def labs(key: str, test: str = "", year: str = "", page: int | None = None) -> LegacyLabPage:
    rows, _, note_ids = await _items(key)
    tests = sorted({_squash(r["item_name"]) for r in rows})
    years = sorted(
        {str(r["service_datetime"].year) for r in rows if r["service_datetime"]}, reverse=True
    )
    test = test if test in tests else ""
    year = year if year in years else ""
    chosen = [
        r
        for r in rows
        if (not test or _squash(r["item_name"]) == test)
        and (not year or (r["service_datetime"] and str(r["service_datetime"].year) == year))
    ]
    shown, pager = paginate(chosen, clamp_page(page))
    return LegacyLabPage(
        rows=[
            LegacyLabRow(
                date=date_us(_day(r["service_datetime"])),
                test=_squash(r["item_name"]),
                result=(r.get("value") or "").strip() or EMPTY,
                range=_range(r.get("ref_low"), r.get("ref_high")),
                flag=_lab_flag(r.get("value"), r.get("ref_low"), r.get("ref_high")),
                comment=_squash(r.get("comments")),
                note_id=_note_link(r.get("note_id"), note_ids),
            )
            for r in shown
        ],
        pager=pager,
        tests=tests,
        test=test,
        years=years,
        year=year,
    )


_VITAL_COLUMNS = ("bp", "pulse", "temp", "resp", "weight", "height", "bmi", "waist")


async def vitals(key: str, page: int | None = None) -> LegacyVitalsPage:
    """One row per recorded time (newest first), one column per vital sign."""
    _, rows, note_ids = await _items(key)
    columns = legacy_codes().vital_columns()
    by_time: dict[object, dict[str, object]] = {}
    for r in rows:  # newest first
        row = by_time.setdefault(r["service_datetime"], {"note_id": None})
        column = columns[(r["item_name"] or "").strip().upper()]
        row.setdefault(column, (r.get("value") or "").strip())
        row["note_id"] = row["note_id"] or _note_link(r.get("note_id"), note_ids)
    shown, pager = paginate(list(by_time.items()), clamp_page(page))
    return LegacyVitalsPage(
        rows=[
            LegacyVitalsRow(
                date=date_us(_day(when)),  # type: ignore[arg-type]
                time=_time(when),  # type: ignore[arg-type]
                note_id=values["note_id"],  # type: ignore[arg-type]
                **{c: str(values.get(c) or EMPTY) for c in _VITAL_COLUMNS},
            )
            for when, values in shown
        ],
        pager=pager,
    )


_FILE_TYPES = {"TIF": "TIFF image", "TIFF": "TIFF image", "JPG": "JPEG image", "JPEG": "JPEG image"}


def _doc_row(r: dict, note_ids: set[int]) -> LegacyDocRow:
    ext = (r.get("file_ext") or "").strip().upper()
    return LegacyDocRow(
        id=int(r["document_id"]),
        date=date_us(_day(r.get("doc_date") or r.get("scanned_date"))),
        type=_squash(r.get("doc_type")) or "Scanned document",  # as stored (HIPAA, BCBS …)
        pages=max(int(r.get("pages") or 1), 1),
        file_type=_FILE_TYPES.get(ext, ext or EMPTY),
        provider=_provider(r),
        note_id=_note_link(r.get("note_id"), note_ids),
    )


def _viewer(key: str, row: LegacyDocRow, page: int, store_ready: bool) -> LegacyDocViewer:
    page = min(max(page, 1), row.pages)
    meta = " · ".join(x for x in (row.date, row.provider, row.file_type) if x and x != EMPTY)
    return LegacyDocViewer(
        id=row.id,
        title=row.type,
        meta=meta,
        page=page,
        pages=row.pages,
        image_url=f"/legacy/{key}/documents/{row.id}/pages/{page}" if store_ready else None,
        note_id=row.note_id,
    )


async def documents(
    key: str,
    doc_type: str = "",
    page: int | None = None,
    doc_id: int | None = None,
    doc_page: int = 1,
) -> LegacyDocPage:
    """Scanned documents with a type filter and paging; the selected (or first) one opened."""
    pkey = person_key(key)
    repo = legacy_repository()
    rows, notes = await asyncio.gather(call(repo.documents, pkey), call(repo.notes, pkey))
    note_ids = {int(n["note_id"]) for n in notes}
    all_rows = [_doc_row(r, note_ids) for r in rows]
    types = sorted({r.type for r in all_rows})
    doc_type = doc_type if doc_type in types else ""
    chosen = [r for r in all_rows if not doc_type or r.type == doc_type]
    shown, pager = paginate(chosen, clamp_page(page))
    store_ready = get_legacy_store() is not None
    if doc_id is not None:
        selected = next((r for r in all_rows if r.id == doc_id), None)
        if selected is None:
            raise NotFoundError(f"{key}/document/{doc_id}")
    else:
        selected = shown[0] if shown else None
    return LegacyDocPage(
        rows=shown,
        pager=pager,
        types=types,
        type=doc_type,
        store_ready=store_ready,
        viewer=_viewer(key, selected, doc_page, store_ready) if selected else None,
    )


async def document_viewer(key: str, doc_id: int, doc_page: int = 1) -> LegacyDocViewer:
    pkey = person_key(key)
    repo = legacy_repository()
    rows, notes = await asyncio.gather(call(repo.documents, pkey), call(repo.notes, pkey))
    row = next((r for r in rows if int(r["document_id"]) == doc_id), None)
    if row is None:
        raise NotFoundError(f"{key}/document/{doc_id}")
    doc = _doc_row(row, {int(n["note_id"]) for n in notes})
    return _viewer(key, doc, doc_page, get_legacy_store() is not None)


async def document_page_png(key: str, doc_id: int, page: int) -> bytes:
    """PNG of one page (TIFF frame) of a legacy scan; ownership checked by the file query."""
    store = get_legacy_store()
    if store is None:
        raise NotFoundError("legacy scan store not configured")
    found = await call(legacy_repository().document_file, person_key(key), doc_id)
    if found is None or not 1 <= page <= max(int(found.get("pages") or 1), 1):
        raise NotFoundError(f"{key}/document/{doc_id}/{page}")

    def load() -> bytes:
        return store.read(found["location"])

    try:
        return await call(cached_png, ("legacy", doc_id, page), load, page - 1)
    except (DocumentUnavailableError, DocumentFormatError) as exc:
        raise NotFoundError(f"{key}/document/{doc_id}/{page}") from exc


async def overview(key: str) -> LegacyOverview:
    """Summary cards: active problems, allergies, medications active at the last update, the
    last chart note, and how many records each tab holds."""
    pkey = person_key(key)
    repo = legacy_repository()
    hist, meds, notes, items, docs, reports = await asyncio.gather(
        history(key),
        medications(key),
        call(repo.notes, pkey),
        _items(key),
        call(repo.documents, pkey),
        call(repo.lab_reports, pkey),
    )
    labs_rows, vital_rows, _ = items
    last = _note_row(notes[0]) if notes else None
    return LegacyOverview(
        problems=[
            LegacyOverviewItem(name=p.name, detail=f"Onset {p.onset}" if p.onset != EMPTY else "")
            for p in hist.problems
            if p.active
        ],
        allergies=[
            LegacyOverviewItem(name=a.allergen, detail="" if a.reactions == EMPTY else a.reactions)
            for a in hist.allergies
            if a.active
        ],
        medications=[
            LegacyOverviewItem(name=m.name, detail="" if m.sig == EMPTY else m.sig)
            for m in meds.active
        ],
        last_note=last,
        counts={
            "notes": len(notes),
            "problems": len(hist.problems) + len(hist.allergies),
            "meds": len(meds.active) + len(meds.past),
            "labs": len(reports) or len(labs_rows),  # lab reports, else recorded values
            "vitals": len({r["service_datetime"] for r in vital_rows}),
            "docs": len(docs),
        },
    )


def _text_lines(value: object) -> str:
    """Free text with line endings normalised and surrounding blank lines removed."""
    lines = str(value or "").replace("\r", "").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def _result_flag(r: dict) -> str | None:
    """The lab's own abnormal flag (H, L, A, …); else computed for plain numeric results."""
    flag = (r.get("flags") or "").strip().upper()
    return flag or _lab_flag(r.get("value"), r.get("ref_low"), r.get("ref_high"))


def _lab_result(r: dict, codes: LegacyCodes) -> LegacyLabResult:
    status = (r.get("status") or "").strip()
    lines = [_text_lines(r.get("comments"))] + [_text_lines(c) for c in r.get("lab_comments") or []]
    return LegacyLabResult(
        name=_squash(r.get("name")) or EMPTY,
        value=_squash(r.get("value")) or EMPTY,
        units=_squash(r.get("units")),
        range=_range(r.get("ref_low"), r.get("ref_high")),
        flag=_result_flag(r),
        status=codes.result_status_label(status),
        voided=status in codes.result_voided,
        comments=[c for c in lines if c],
        staff_comments=[
            LegacyLabComment(date=date_us(_day(c.get("created_at"))), text=text)
            for c in r.get("staff_comments") or []
            if (text := _text_lines(c.get("comment")))
        ],
    )


def _lab_test(t: dict, codes: LegacyCodes) -> LegacyLabTest:
    dxs = [_squash(d.get("dx_desc")) or _squash(d.get("dx_code")) for d in t.get("diagnoses") or []]
    return LegacyLabTest(
        name=_squash(t.get("test_name")) or "Lab test",
        collected=date_us(_day(t.get("collected_date"))),
        diagnoses=", ".join(dict.fromkeys(d for d in dxs if d)),
        comment=_text_lines(t.get("test_comments")),
        results=[_lab_result(r, codes) for r in t.get("results") or []],
    )


def _order_day(o: dict) -> date | None:
    return _day(o.get("service_date") or o.get("order_date") or o.get("result_date"))


def _order_title(o: dict) -> str:
    names = [_squash(t.get("test_name")) for t in o.get("tests") or []]
    names = [n for n in dict.fromkeys(names) if n]
    if not names:
        return "Lab order"
    return ", ".join(names[:3]) + (f" + {len(names) - 3} more" if len(names) > 3 else "")


def _order_row(o: dict, codes: LegacyCodes) -> LegacyLabOrderRow:
    results = [r for t in o.get("tests") or [] for r in t.get("results") or []]
    return LegacyLabOrderRow(
        id=int(o["order_id"]),
        date=date_us(_order_day(o)),
        title=_order_title(o),
        provider=_provider(o),
        results=len(results),
        abnormal=sum(1 for r in results if _result_flag(r)),
    )


def _lab_order(o: dict, codes: LegacyCodes) -> LegacyLabOrder:
    return LegacyLabOrder(
        id=int(o["order_id"]),
        title=_order_title(o),
        date=date_us(_order_day(o)),
        ordered=date_us(_day(o.get("order_date"))),
        resulted=date_us(_day(o.get("result_date"))),
        provider=_provider(o),
        facility=or_dash(o.get("facility")),
        order_no=or_dash(o.get("order_no")),
        comment=_text_lines(o.get("comments")),
        tests=[_lab_test(t, codes) for t in o.get("tests") or []],
    )


async def lab_reports(
    key: str, year: str = "", page: int | None = None, order_id: int | None = None
) -> LegacyLabReports:
    """Lab orders with their results, newest first; the selected (or first) order opened."""
    orders = await call(legacy_repository().lab_reports, person_key(key))
    codes = legacy_codes()
    years = sorted({str(d.year) for o in orders if (d := _order_day(o))}, reverse=True)
    year = year if year in years else ""
    chosen = [o for o in orders if not year or ((d := _order_day(o)) and str(d.year) == year)]
    shown, pager = paginate(chosen, clamp_page(page))
    if order_id is not None:
        selected = next((o for o in orders if int(o["order_id"]) == order_id), None)
        if selected is None:
            raise NotFoundError(f"{key}/lab-order/{order_id}")
    else:
        selected = shown[0] if shown else None
    return LegacyLabReports(
        rows=[_order_row(o, codes) for o in shown],
        pager=pager,
        years=years,
        year=year,
        order=_lab_order(selected, codes) if selected else None,
    )


async def lab_order(key: str, order_id: int) -> LegacyLabOrder:
    orders = await call(legacy_repository().lab_reports, person_key(key))
    found = next((o for o in orders if int(o["order_id"]) == order_id), None)
    if found is None:
        raise NotFoundError(f"{key}/lab-order/{order_id}")
    return _lab_order(found, legacy_codes())


LAB_VIEWS = ("reports", "values")


async def labs_context(key: str, params: Mapping[str, str], page_no: int) -> dict[str, Any]:
    """Labs tab: "reports" (orders and results from the lab system, the default when the patient
    has any) or "values" (lab values recorded on the clinical flowsheet)."""
    view = params.get("view", "")
    if view not in LAB_VIEWS:
        orders = await call(legacy_repository().lab_reports, person_key(key))
        view = "reports" if orders else "values"
    if view == "reports":
        raw = params.get("order") or ""
        reports = await lab_reports(
            key, params.get("year", ""), page_no, int(raw) if raw.isdigit() else None
        )
        return {"lab_view": view, "reports": reports}
    values = await labs(key, params.get("test", ""), params.get("year", ""), page_no)
    return {"lab_view": view, "labs": values}


async def tab_context(key: str, tab: str, params: Mapping[str, str]) -> dict[str, Any]:
    """Everything one tab of the pre-2010 chart needs (full page or HTMX fragment)."""
    if tab == "overview":
        return {"overview": await overview(key)}
    if tab == "problems":
        return {"history": await history(key, params.get("voided") == "1")}
    if tab == "meds":
        return {"meds": await medications(key, params.get("voided") == "1")}
    page_no = int(params["page"]) if (params.get("page") or "").isdigit() else 1
    if tab == "labs":
        return await labs_context(key, params, page_no)
    if tab == "vitals":
        return {"vitals": await vitals(key, page_no)}
    if tab == "docs":
        raw_doc, raw_docpage = params.get("doc") or "", params.get("docpage") or ""
        return {
            "docs": await documents(
                key,
                params.get("type", ""),
                page_no,
                int(raw_doc) if raw_doc.isdigit() else None,
                int(raw_docpage) if raw_docpage.isdigit() else 1,
            )
        }
    page = int(params["page"]) if (params.get("page") or "").isdigit() else 1
    notes = await note_page(key, params.get("year", ""), page, params.get("type", ""))
    raw_note = params.get("note") or ""
    note_id = int(raw_note) if raw_note.isdigit() else (notes.rows[0].id if notes.rows else None)
    note = await get_note(key, note_id) if note_id is not None else None
    return {"notes": notes, "note": note}
