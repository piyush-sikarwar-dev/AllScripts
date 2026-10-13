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
from app.models.notes import NoteDetail
from app.models.visits import EncounterDetail
from app.repositories.appdb import utcnow
from app.services import NotFoundError
from app.services.chart_header import get_header
from app.services.documents import DOC_KINDS, document_viewer, page_png
from app.services.notes_service import (
    note_detail,
    notes_view,
    selected_note_refs,
    toggle_note_export,
)
from app.services.notes_service import parse_state as parse_notes_state
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
        {"tab": "docs", "type": type, "page": page, "doc": f"{kind}-{doc_id}",
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
