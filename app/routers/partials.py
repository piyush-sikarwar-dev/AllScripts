"""HTMX fragments: patient search rows, chart tabs, visit detail, export dialog.

Every fragment URL also has a full-page equivalent; `HX-Push-Url` points the browser history at
that full-page URL so reloads and shared links work without HTMX.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from app.audit import audit
from app.auth import current_user
from app.crosswalk import PatientRef, resolve
from app.services import NotFoundError
from app.services.documents import DOC_KINDS, document_viewer, page_png
from app.services.notes import NOTE_KINDS, note_detail
from app.services.patients import build_search, search_patients
from app.services.tabs import TAB_NAMES, TABS, tab_context
from app.services.visits import visit_detail
from app.templating import render, url_with

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


@router.get("/patients/{key}/tab/{name}", response_class=HTMLResponse)
async def chart_tab(
    request: Request, background: BackgroundTasks, key: str, name: str
) -> HTMLResponse:
    if name not in TAB_NAMES:
        raise HTTPException(status_code=404)
    ref = await _resolve(key)
    try:
        ctx = await tab_context(ref, name, request.query_params)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_tab", patient_key=ref.patient_key, detail={"tab": name})
    pager = ctx.get("pager") or getattr(ctx.get("visit_list"), "pager", None)
    push_params = {"tab": name, **ctx["state"], "page": pager.page if pager else None}
    if name == "visits" and ctx["visit_list"].selected:
        push_params["visit"] = ctx["visit_list"].selected.visit.id
    if name == "docs" and ctx.get("viewer"):
        push_params["doc"] = f"{ctx['viewer'].kind}-{ctx['viewer'].id}"
    if name == "notes" and ctx.get("selected_note"):
        note = ctx["selected_note"]
        push_params["note"] = f"{note.kind}-{note.id}"
    return render(
        request,
        "partials/tab_frame.html",
        {"key": ref.patient_key, "tabs": TABS, "tab": name, "partial": True, **ctx},
        headers={"HX-Push-Url": url_with(f"/patients/{ref.patient_key}", push_params)},
    )


@router.get("/patients/{key}/visits/{source}/{visit_id}", response_class=HTMLResponse)
async def visit_panel(
    request: Request,
    background: BackgroundTasks,
    key: str,
    source: str,
    visit_id: int,
    filter: str = "",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
) -> HTMLResponse:
    if source != "EMR":  # TODO(Phase 10): Pre-2010 chart notes as visits.
        raise HTTPException(status_code=404)
    ref = await _resolve(key)
    try:
        detail = await visit_detail(ref, visit_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_tab", patient_key=ref.patient_key,
          detail={"tab": "visits", "visit_id": visit_id})  # fmt: skip
    push = url_with(
        f"/patients/{ref.patient_key}",
        {"tab": "visits", "filter": filter, "page": page, "visit": visit_id},
    )
    return render(
        request,
        "partials/visit_detail.html",
        {"detail": detail, "partial": True},
        headers={"HX-Push-Url": push},
    )


@router.get("/patients/{key}/notes/{kind}/{note_id}", response_class=HTMLResponse)
async def note_panel(
    request: Request,
    background: BackgroundTasks,
    key: str,
    kind: str,
    note_id: int,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
) -> HTMLResponse:
    if kind not in NOTE_KINDS:
        raise HTTPException(status_code=404)
    ref = await _resolve(key)
    try:
        detail = await note_detail(ref, kind, note_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_document", patient_key=ref.patient_key,
          detail={"kind": kind, "id": note_id})  # fmt: skip
    push = url_with(
        f"/patients/{ref.patient_key}", {"tab": "notes", "page": page, "note": f"{kind}-{note_id}"}
    )
    return render(
        request,
        "partials/note_detail.html",
        {"note": detail, "partial": True},
        headers={"HX-Push-Url": push},
    )


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
