"""HTMX fragments: patient search rows, chart tabs, visits tab pieces, notes, documents.

Every fragment URL also has a full-page equivalent; `HX-Push-Url` points the browser history at
that full-page URL so reloads and shared links work without HTMX.
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.audit import audit
from app.auth import CurrentUser, current_user, require_csrf
from app.crosswalk import PatientRef, resolve
from app.formatting import date_us, time_local, to_clinic_time
from app.models.history import EntryDetail
from app.models.notes import NoteDetail
from app.models.visits import EncounterDetail
from app.repositories.appdb import utcnow
from app.services import NotFoundError
from app.services.chart_header import get_header
from app.services.documents import (
    DOC_KINDS,
    attachment_pdf,
    attachment_png,
    document_image,
    document_viewer,
    page_png,
)
from app.services.history_service import CHANGES_SHOWN as HISTORY_CHANGES_SHOWN
from app.services.history_service import SECTION_LABELS as HISTORY_SECTION_LABELS
from app.services.history_service import change_history as history_change_lines
from app.services.history_service import entry_detail as history_entry_detail
from app.services.history_service import history_view, toggle_entry_export
from app.services.history_service import load_entries as load_history_entries
from app.services.history_service import parse_state as parse_history_state
from app.services.history_service import print_rows as history_print_rows
from app.services.notes_service import (
    note_detail,
    notes_view,
    portal_attachment,
    selected_note_refs,
    toggle_note_export,
)
from app.services.notes_service import parse_state as parse_notes_state
from app.services.patient_details import patient_photo
from app.services.patients import build_search, search_patients
from app.services.tabs import TAB_NAMES, TABS, tab_context
from app.services.visits import (
    VISIT_TYPES,
    encounter_detail,
    parse_state,
    selected_visit_ids,
    toggle_export,
    visit_list,
)
from app.services.visits import activity as visit_activity
from app.templating import is_htmx, render, url_with

router = APIRouter(dependencies=[Depends(current_user)])


async def _resolve(key: str) -> PatientRef:
    try:
        return await resolve(key)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc


@router.get("/patients/rows", response_class=HTMLResponse)
async def patient_rows(
    request: Request,
    background: BackgroundTasks,
    q: str = "",
    dob: str = "",
    chart: str = "",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
) -> HTMLResponse:
    search = build_search(q, dob, chart)
    results = await search_patients(search, page)
    audit(request, background, "search",
          detail={"fields": search.fields_used(), "page": results.pager.page})  # fmt: skip
    push = url_with("/patients", search.params(), page=results.pager.page)
    return render(
        request,
        "partials/patient_rows.html",
        {"results": results, "partial": True},
        headers={"HX-Push-Url": push},
    )


@router.post("/patients/{key}/tab/{name}/seen", dependencies=[Depends(require_csrf)])
async def chart_tab_seen(
    request: Request, background: BackgroundTasks, key: str, name: str
) -> Response:
    """A tab the browser re-showed from its page memory (perf #7): record the view in the audit
    log exactly like a loaded tab. No data is returned."""
    if name not in TAB_NAMES:
        raise HTTPException(status_code=404)
    ref = await _resolve(key)
    audit(request, background, "view_tab", patient_key=ref.patient_key,
          detail={"tab": name, "from_page_memory": True})  # fmt: skip
    return Response(status_code=204)


@router.get("/patients/{key}/tab/{name}", response_class=HTMLResponse)
async def chart_tab(
    request: Request, background: BackgroundTasks, key: str, name: str
) -> HTMLResponse:
    if name not in TAB_NAMES:
        raise HTTPException(status_code=404)
    ref = await _resolve(key)
    try:
        ctx = await tab_context(ref, name, request.query_params, request.state.session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_tab", patient_key=ref.patient_key, detail={"tab": name})
    pager = ctx.get("pager")
    push_params = {"tab": name, **ctx["state"], "page": pager.page if pager else None}
    if name == "visits":
        push_params = ctx["visits_state"].params()
        _audit_visit(request, background, ref, ctx.get("detail"))
    if name == "docs" and ctx.get("viewer"):
        push_params["doc"] = f"{ctx['viewer'].kind}-{ctx['viewer'].id}"
    if name == "problems":
        push_params = ctx["history_state"].params()
        _audit_entry(request, background, ref, ctx.get("history_detail"))
    if name == "notes":
        push_params = ctx["notes_state"].params()
        _audit_note(request, background, ref, ctx.get("note"))
    return render(
        request,
        "partials/tab_frame.html",
        {"key": ref.patient_key, "tabs": TABS, "tab": name, "partial": True, **ctx},
        headers={"HX-Push-Url": url_with(f"/patients/{ref.patient_key}", push_params)},
    )


# --- Visits tab (Option C) -----------------------------------------------------------------------

EncounterId = Annotated[int, Path(ge=1, le=2_000_000_000)]


def _audit_visit(
    request: Request, background: BackgroundTasks, ref: PatientRef, detail: EncounterDetail | None
) -> None:
    if detail is not None:
        audit(request, background, "view_visit", patient_key=ref.patient_key,
              detail={"encounter_id": detail.id, "view": detail.view})  # fmt: skip


@router.get("/patients/{key}/visits/list", response_class=HTMLResponse)
async def visits_list_partial(
    request: Request, background: BackgroundTasks, key: str
) -> HTMLResponse:
    """Visit list for new filters (search / type / year / page) plus the activity card (OOB).
    The open visit (if any) stays open and stays in the URL."""
    ref = await _resolve(key)
    state = parse_state(request.query_params)
    act, page = await asyncio.gather(visit_activity(ref, state), visit_list(ref, state))
    audit(request, background, "view_tab", patient_key=ref.patient_key,
          detail={"tab": "visits", "page": page.pager.page})  # fmt: skip
    return render(
        request,
        "partials/visits_list.html",
        {"key": ref.patient_key, "visits_state": state, "visit_page": page, "activity": act,
         "visit_types": VISIT_TYPES, "oob_activity": True, "partial": True},
        headers={"HX-Push-Url": url_with(f"/patients/{ref.patient_key}", state.params())},
    )  # fmt: skip


@router.get("/patients/{key}/visits/activity", response_class=HTMLResponse)
async def visits_activity_partial(request: Request, key: str) -> HTMLResponse:
    ref = await _resolve(key)
    state = parse_state(request.query_params)
    act = await visit_activity(ref, state)
    return render(
        request,
        "partials/visits_activity.html",
        {"key": ref.patient_key, "visits_state": state, "activity": act, "partial": True},
    )


async def _encounter(
    ref: PatientRef, encounter_id: int, view: str, session_id: str | None
) -> EncounterDetail:
    selection = await selected_visit_ids(session_id, ref.patient_key)
    try:
        return await encounter_detail(ref, encounter_id, view, encounter_id in selection)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc


@router.get("/patients/{key}/visits/{encounter_id}", response_class=HTMLResponse)
async def visit_panel(
    request: Request, background: BackgroundTasks, key: str, encounter_id: EncounterId
) -> HTMLResponse:
    ref = await _resolve(key)
    state = parse_state(request.query_params)
    detail = await _encounter(ref, encounter_id, state.view, request.state.session_id)
    _audit_visit(request, background, ref, detail)
    state = state.model_copy(update={"visit": encounter_id, "view": detail.view})
    return render(
        request,
        "partials/visit_detail.html",
        {"key": ref.patient_key, "detail": detail, "visits_state": state, "partial": True},
        headers={"HX-Push-Url": url_with(f"/patients/{ref.patient_key}", state.params())},
    )


@router.get("/patients/{key}/visits/{encounter_id}/print", response_class=HTMLResponse)
async def visit_print(
    request: Request,
    background: BackgroundTasks,
    key: str,
    encounter_id: EncounterId,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> HTMLResponse:
    """Standalone printable page (no sidebar) for one visit, structured view."""
    ref = await _resolve(key)
    header, detail = await asyncio.gather(
        get_header(ref), _encounter(ref, encounter_id, "structured", request.state.session_id)
    )
    audit(request, background, "print_visit", patient_key=ref.patient_key,
          detail={"encounter_id": encounter_id})  # fmt: skip
    printed = to_clinic_time(utcnow())
    return render(
        request,
        "pages/visit_print.html",
        {"key": ref.patient_key, "header": header, "detail": detail, "user": user,
         "printed_at": f"{date_us(printed)} {time_local(printed)}"},
    )  # fmt: skip


@router.post(
    "/patients/{key}/export-selection/visits/{encounter_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def toggle_visit_export(request: Request, key: str, encounter_id: EncounterId) -> Response:
    """Add / remove a visit from the next PDF release. Returns the detail's button plus the
    chart header's export button (out of band) with the new count."""
    ref = await _resolve(key)
    try:
        added, count = await toggle_export(ref, request.state.session_id, encounter_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    if not is_htmx(request):  # plain form post (no JS): back to the visit
        back = url_with(f"/patients/{ref.patient_key}", {"tab": "visits", "visit": encounter_id})
        return RedirectResponse(back, status_code=303)
    return render(
        request,
        "partials/visit_export_toggle.html",
        {"key": ref.patient_key, "encounter_id": encounter_id, "in_export": added,
         "export_count": count, "oob": True, "partial": True},
    )  # fmt: skip


# --- Notes tab (Option A) ------------------------------------------------------------------------


def _audit_note(
    request: Request, background: BackgroundTasks, ref: PatientRef, note: NoteDetail | None
) -> None:
    if note is not None:
        audit(request, background, "view_note", patient_key=ref.patient_key,
              detail={"note": note.ref, "category": note.category, "view": note.view})  # fmt: skip


@router.get("/patients/{key}/notes/list", response_class=HTMLResponse)
async def notes_list_partial(
    request: Request, background: BackgroundTasks, key: str
) -> HTMLResponse:
    """Note list for new filters, plus the filter card (OOB: tile counts follow the search and the
    dates) and, when the open note is no longer in the result, the first note (OOB)."""
    ref = await _resolve(key)
    view = await notes_view(ref, parse_notes_state(request.query_params))
    audit(request, background, "view_tab", patient_key=ref.patient_key,
          detail={"tab": "notes", "page": view.page.pager.page, "cat": view.state.cat})  # fmt: skip
    note = None
    if view.selection_changed and view.selected:
        selection = await selected_note_refs(request.state.session_id, ref.patient_key)
        note = await note_detail(ref, view.selected, view.state.view, view.selected in selection)
        _audit_note(request, background, ref, note)
    return render(
        request,
        "partials/notes_list.html",
        {"key": ref.patient_key, "notes_state": view.state, "note_filters": view.filters,
         "note_page": view.page, "oob": True, "oob_note": view.selection_changed, "note": note,
         "partial": True},
        headers={"HX-Push-Url": url_with(f"/patients/{ref.patient_key}", view.state.params())},
    )  # fmt: skip


@router.get("/patients/{key}/notes/filters", response_class=HTMLResponse)
async def notes_filters_partial(request: Request, key: str) -> HTMLResponse:
    ref = await _resolve(key)
    view = await notes_view(ref, parse_notes_state(request.query_params))
    return render(
        request,
        "partials/notes_filters.html",
        {"key": ref.patient_key, "notes_state": view.state, "note_filters": view.filters,
         "partial": True},
    )  # fmt: skip


async def _note(ref: PatientRef, note_ref: str, view: str, session_id: str | None) -> NoteDetail:
    selection = await selected_note_refs(session_id, ref.patient_key)
    try:
        return await note_detail(ref, note_ref, view, note_ref in selection)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc


@router.get("/patients/{key}/notes/{note_ref}", response_class=HTMLResponse)
async def note_panel(
    request: Request, background: BackgroundTasks, key: str, note_ref: str
) -> HTMLResponse:
    ref = await _resolve(key)
    state = parse_notes_state(request.query_params)
    note = await _note(ref, note_ref, state.view, request.state.session_id)
    _audit_note(request, background, ref, note)
    state = state.model_copy(update={"note": note.ref, "view": note.view})
    return render(
        request,
        "partials/note_detail.html",
        {"key": ref.patient_key, "note": note, "notes_state": state, "partial": True},
        headers={"HX-Push-Url": url_with(f"/patients/{ref.patient_key}", state.params())},
    )


@router.get("/patients/{key}/notes/{note_ref}/attachment")
async def note_attachment(
    request: Request, background: BackgroundTasks, key: str, note_ref: str
) -> Response:
    """PDF attached to a patient-portal message: always a download, generic file name."""
    ref = await _resolve(key)
    try:
        pdf = await portal_attachment(ref, note_ref)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_document", patient_key=ref.patient_key,
          detail={"kind": "portal_attachment", "note": note_ref})  # fmt: skip
    filename = f"portal-message-{note_ref.rpartition('-')[2]}.pdf"
    disposition = f'attachment; filename="{filename}"'
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": disposition})


@router.get("/patients/{key}/notes/{note_ref}/print", response_class=HTMLResponse)
async def note_print(
    request: Request,
    background: BackgroundTasks,
    key: str,
    note_ref: str,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> HTMLResponse:
    """Standalone printable page (no sidebar) for one note, formatted view."""
    ref = await _resolve(key)
    header, note = await asyncio.gather(
        get_header(ref), _note(ref, note_ref, "formatted", request.state.session_id)
    )
    audit(request, background, "print_note", patient_key=ref.patient_key,
          detail={"note": note.ref, "category": note.category})  # fmt: skip
    printed = to_clinic_time(utcnow())
    return render(
        request,
        "pages/note_print.html",
        {"key": ref.patient_key, "header": header, "note": note, "user": user,
         "printed_at": f"{date_us(printed)} {time_local(printed)}"},
    )  # fmt: skip


@router.post(
    "/patients/{key}/export-selection/notes/{note_ref}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def toggle_note_export_route(request: Request, key: str, note_ref: str) -> Response:
    """Add / remove a note from the next PDF release; returns the button plus the chart header's
    export button (out of band) with the new item count."""
    ref = await _resolve(key)
    try:
        added, count = await toggle_note_export(ref, request.state.session_id, note_ref)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    if not is_htmx(request):  # plain form post (no JS): back to the note
        back = url_with(f"/patients/{ref.patient_key}", {"tab": "notes", "note": note_ref})
        return RedirectResponse(back, status_code=303)
    return render(
        request,
        "partials/note_export_toggle.html",
        {"key": ref.patient_key, "note_ref": note_ref, "in_export": added,
         "export_count": count, "oob": True, "partial": True},
    )  # fmt: skip


# --- Problems & allergies tab (Option B) ---------------------------------------------------------

EntryId = Annotated[int, Path(ge=1, le=2_147_483_647)]


def _audit_entry(
    request: Request, background: BackgroundTasks, ref: PatientRef, entry: EntryDetail | None
) -> None:
    if entry is not None:
        audit(request, background, "view_history_entry", patient_key=ref.patient_key,
              detail={"entry_id": entry.id, "section": entry.section})  # fmt: skip


@router.get("/patients/{key}/history/rail", response_class=HTMLResponse)
async def history_rail_partial(request: Request, key: str) -> HTMLResponse:
    ref = await _resolve(key)
    view = await history_view(ref, request.query_params, request.state.session_id)
    return render(
        request,
        "partials/history_rail.html",
        {"key": ref.patient_key, "history_state": view.state, "history_rail": view.rail,
         "partial": True},
    )  # fmt: skip


@router.get("/patients/{key}/history/list", response_class=HTMLResponse)
async def history_list_partial(
    request: Request, background: BackgroundTasks, key: str
) -> HTMLResponse:
    """Entry list of a section, plus the rail (OOB: counts and selection stay in sync) and, when
    the selection changed, the detail of the first entry (OOB)."""
    ref = await _resolve(key)
    view = await history_view(ref, request.query_params, request.state.session_id)
    detail = {"tab": "problems", "section": view.state.sec, "status": view.state.status}
    audit(request, background, "view_tab", patient_key=ref.patient_key, detail=detail)
    if view.selection_changed:
        _audit_entry(request, background, ref, view.detail)
    return render(
        request,
        "partials/history_list.html",
        {"key": ref.patient_key, "history_state": view.state, "history_rail": view.rail,
         "history_rows": view.rows, "history_detail": view.detail, "oob": True,
         "oob_detail": view.selection_changed, "partial": True},
        headers={"HX-Push-Url": url_with(f"/patients/{ref.patient_key}", view.state.params())},
    )  # fmt: skip


@router.get("/patients/{key}/history/print", response_class=HTMLResponse)
async def history_print(
    request: Request,
    background: BackgroundTasks,
    key: str,
    user: Annotated[CurrentUser, Depends(current_user)],
    sec: str = "problems",
) -> HTMLResponse:
    """Printable table of one section (all statuses)."""
    if sec not in HISTORY_SECTION_LABELS:
        raise HTTPException(status_code=404)
    ref = await _resolve(key)
    header, entries = await asyncio.gather(get_header(ref), load_history_entries(ref))
    audit(request, background, "print_history", patient_key=ref.patient_key,
          detail={"section": sec})  # fmt: skip
    printed = to_clinic_time(utcnow())
    return render(
        request,
        "pages/history_print.html",
        {"key": ref.patient_key, "header": header, "user": user,
         "section_label": HISTORY_SECTION_LABELS[sec], "rows": history_print_rows(entries, sec),
         "printed_at": f"{date_us(printed)} {time_local(printed)}"},
    )  # fmt: skip


@router.get("/patients/{key}/history/entries/{entry_id}", response_class=HTMLResponse)
async def history_entry_panel(
    request: Request, background: BackgroundTasks, key: str, entry_id: EntryId
) -> HTMLResponse:
    ref = await _resolve(key)
    state, _ = parse_history_state(request.query_params, request.state.session_id)
    try:
        entry = await history_entry_detail(ref, entry_id, request.state.session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    _audit_entry(request, background, ref, entry)
    state = state.model_copy(update={"sec": entry.section, "entry": entry.id})
    return render(
        request,
        "partials/history_detail.html",
        {"key": ref.patient_key, "entry": entry, "history_state": state, "partial": True},
        headers={"HX-Push-Url": url_with(f"/patients/{ref.patient_key}", state.params())},
    )


@router.get("/patients/{key}/history/entries/{entry_id}/changes", response_class=HTMLResponse)
async def history_entry_changes(
    request: Request, key: str, entry_id: EntryId, all: bool = False
) -> HTMLResponse:
    """Change history of one entry (lazy-loaded below the detail)."""
    ref = await _resolve(key)
    try:
        lines = await history_change_lines(ref, entry_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    return render(
        request,
        "partials/history_changes.html",
        {"key": ref.patient_key, "entry_id": entry_id, "lines": lines, "show_all": all,
         "limit": HISTORY_CHANGES_SHOWN, "partial": True},
    )  # fmt: skip


@router.post(
    "/patients/{key}/export-selection/history/{entry_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def toggle_history_export(request: Request, key: str, entry_id: EntryId) -> Response:
    ref = await _resolve(key)
    try:
        added, count = await toggle_entry_export(ref, request.state.session_id, entry_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    if not is_htmx(request):  # plain form post (no JS): back to the entry
        back = url_with(f"/patients/{ref.patient_key}", {"tab": "problems", "entry": entry_id})
        return RedirectResponse(back, status_code=303)
    return render(
        request,
        "partials/history_export_toggle.html",
        {"key": ref.patient_key, "entry_id": entry_id, "in_export": added,
         "export_count": count, "oob": True, "partial": True},
    )  # fmt: skip


@router.get("/patients/{key}/documents/{kind}/{doc_id}", response_class=HTMLResponse)
async def document_panel(
    request: Request,
    background: BackgroundTasks,
    key: str,
    kind: str,
    doc_id: int,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    docpage: Annotated[int, Query(ge=1, le=100_000)] = 1,
    type: str = "",
    src: str = "",
) -> HTMLResponse:
    if kind not in DOC_KINDS:
        raise HTTPException(status_code=404)
    ref = await _resolve(key)
    try:
        viewer = await document_viewer(ref, kind, doc_id, docpage)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_document", patient_key=ref.patient_key,
          detail={"kind": kind, "id": doc_id, "page": viewer.page})  # fmt: skip
    push = url_with(
        f"/patients/{ref.patient_key}",
        {"tab": "docs", "src": src, "type": type, "page": page, "doc": f"{kind}-{doc_id}",
         "docpage": viewer.page if viewer.page > 1 else None},
    )  # fmt: skip
    return render(
        request,
        "partials/document_viewer.html",
        {"viewer": viewer, "key": ref.patient_key, "list_page": page, "doc_type": type,
         "partial": True},
        headers={"HX-Push-Url": push},
    )  # fmt: skip


@router.get("/patients/{key}/documents/scan/{doc_id}/pages/{page_no}")
async def document_page_image(
    request: Request, background: BackgroundTasks, key: str, doc_id: int, page_no: int
) -> Response:
    ref = await _resolve(key)
    try:
        png = await page_png(ref, doc_id, page_no)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_document", patient_key=ref.patient_key,
          detail={"kind": "scan", "id": doc_id, "page": page_no, "image": True})  # fmt: skip
    return Response(content=png, media_type="image/png")


@router.get("/patients/{key}/documents/attachment/{attachment_id}/pages/{page_no}")
async def attachment_page_image(
    request: Request, background: BackgroundTasks, key: str, attachment_id: int, page_no: int
) -> Response:
    """One page of an image chart attachment (TIFF / JPEG / PNG …) as PNG."""
    ref = await _resolve(key)
    try:
        png = await attachment_png(ref, attachment_id, page_no)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    detail = {"kind": "attachment", "id": attachment_id, "page": page_no, "image": True}
    audit(request, background, "view_document", patient_key=ref.patient_key, detail=detail)
    return Response(content=png, media_type="image/png")


@router.get("/patients/{key}/documents/attachment/{attachment_id}/file")
async def attachment_file(
    request: Request, background: BackgroundTasks, key: str, attachment_id: int
) -> Response:
    """A PDF chart attachment: always a download with a generic file name."""
    ref = await _resolve(key)
    try:
        pdf = await attachment_pdf(ref, attachment_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_document", patient_key=ref.patient_key,
          detail={"kind": "attachment", "id": attachment_id, "file": True})  # fmt: skip
    disposition = f'attachment; filename="chart-attachment-{attachment_id}.pdf"'
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": disposition})


@router.get("/patients/{key}/documents/document/{doc_id}/images/{index}")
async def document_embedded_image(
    request: Request, background: BackgroundTasks, key: str, doc_id: int, index: int
) -> Response:
    """A picture embedded in a clinical document (decoded from the stored package)."""
    ref = await _resolve(key)
    try:
        mime, data = await document_image(ref, doc_id, index)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    detail = {"kind": "document", "id": doc_id, "image": index}
    audit(request, background, "view_document", patient_key=ref.patient_key, detail=detail)
    return Response(content=data, media_type=mime)


@router.get("/patients/{key}/photo")
async def patient_photo_image(request: Request, background: BackgroundTasks, key: str) -> Response:
    """The patient's photo (DEMOGRAPHICPICTURE), shown in the chart header."""
    ref = await _resolve(key)
    try:
        data = await patient_photo(ref)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_document", patient_key=ref.patient_key,
          detail={"kind": "photo"})  # fmt: skip
    media = "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"
    return Response(content=data, media_type=media)
