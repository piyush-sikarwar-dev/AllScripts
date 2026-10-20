"""The separate "Pre-2010 records" section (DMZ legacy chart). Hidden (404) unless enabled.

Full pages and their HTMX fragments live together here; every fragment pushes the matching
full-page URL so reloads and shared links work without HTMX.
"""

from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from app.audit import audit
from app.auth import CurrentUser, current_user
from app.formatting import date_us, time_local, to_clinic_time
from app.repositories.appdb import utcnow
from app.services import NotFoundError
from app.services.legacy import (
    TAB_LABELS,
    TAB_NAMES,
    TABS,
    build_search,
    document_page_png,
    document_viewer,
    get_header,
    get_note,
    lab_order,
    legacy_enabled,
    note_page,
    patient_photo,
    search_patients,
    tab_context,
)
from app.templating import render, url_with


def _require_enabled() -> None:
    if not legacy_enabled():
        raise HTTPException(status_code=404)


router = APIRouter(dependencies=[Depends(current_user), Depends(_require_enabled)])

User = Annotated[CurrentUser, Depends(current_user)]
Page = Annotated[int, Query(ge=1, le=100_000)]
NoteId = Annotated[int, Query(ge=1, le=2_000_000_000)]


@router.get("/legacy", response_class=HTMLResponse)
async def legacy_list(
    request: Request,
    background: BackgroundTasks,
    user: User,
    q: str = "",
    dob: str = "",
    legacy_id: str = "",
    page: Page = 1,
) -> HTMLResponse:
    search = build_search(q, dob, legacy_id)
    results = await search_patients(search, page)
    audit(request, background, "search",
          detail={"section": "legacy", "fields": search.fields_used(),
                  "page": results.pager.page})  # fmt: skip
    return render(
        request, "pages/legacy_list.html", {"user": user, "nav": "legacy", "results": results}
    )


@router.get("/legacy/rows", response_class=HTMLResponse)
async def legacy_rows(
    request: Request,
    background: BackgroundTasks,
    q: str = "",
    dob: str = "",
    legacy_id: str = "",
    page: Page = 1,
) -> HTMLResponse:
    search = build_search(q, dob, legacy_id)
    results = await search_patients(search, page)
    audit(request, background, "search",
          detail={"section": "legacy", "fields": search.fields_used(),
                  "page": results.pager.page})  # fmt: skip
    push = url_with("/legacy", search.params(), page=results.pager.page)
    return render(
        request,
        "partials/legacy_rows.html",
        {"results": results, "partial": True},
        headers={"HX-Push-Url": push},
    )


def _validated(params: Mapping[str, str]) -> dict[str, str]:
    """Only the known state parameters, length-capped (they are echoed into URLs)."""
    keep = ("year", "page", "note", "voided", "test", "type", "doc", "docpage", "view", "order")
    return {k: params[k][:60] for k in keep if params.get(k)}


async def _tab(request: Request, background: BackgroundTasks, key: str, tab: str) -> dict:
    if tab not in TAB_NAMES:
        raise HTTPException(status_code=404)
    try:
        ctx = await tab_context(key, tab, _validated(request.query_params))
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_tab", patient_key=key,
          detail={"section": "legacy", "tab": tab})  # fmt: skip
    if ctx.get("note"):
        audit(request, background, "view_note", patient_key=key,
              detail={"section": "legacy", "note": ctx["note"].id})  # fmt: skip
    return ctx


@router.get("/legacy/{key}", response_class=HTMLResponse)
async def legacy_chart(
    request: Request, background: BackgroundTasks, key: str, user: User, tab: str = "overview"
) -> HTMLResponse:
    try:
        header = await get_header(key)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    ctx = await _tab(request, background, key, tab)
    audit(request, background, "view_patient", patient_key=key,
          detail={"section": "legacy", "tab": tab})  # fmt: skip
    return render(
        request,
        "pages/legacy_chart.html",
        {"user": user, "nav": "legacy", "header": header, "key": key, "tab": tab,
         "tabs": TABS, "tab_labels": TAB_LABELS, **ctx},
    )  # fmt: skip


@router.get("/legacy/{key}/tab/{name}", response_class=HTMLResponse)
async def legacy_tab(
    request: Request, background: BackgroundTasks, key: str, name: str
) -> HTMLResponse:
    ctx = await _tab(request, background, key, name)
    params = {k: v for k, v in _validated(request.query_params).items()}
    push = url_with(f"/legacy/{key}", {"tab": None if name == "overview" else name, **params})
    return render(
        request,
        "partials/legacy_tab_frame.html",
        {"key": key, "tab": name, "tabs": TABS, "partial": True, **ctx},
        headers={"HX-Push-Url": push},
    )


@router.get("/legacy/{key}/notes", response_class=HTMLResponse)
async def legacy_notes(
    request: Request, background: BackgroundTasks, key: str, year: str = "", page: Page = 1,
    note: NoteId | None = None, type: str = "",
) -> HTMLResponse:  # fmt: skip
    try:
        notes = await note_page(key, year, page, type[:60])
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_tab", patient_key=key,
          detail={"section": "legacy", "tab": "notes", "page": notes.pager.page})  # fmt: skip
    push = url_with(f"/legacy/{key}", notes.params(note=note))
    return render(
        request,
        "partials/legacy_notes.html",
        {"key": key, "notes": notes, "selected": note},
        headers={"HX-Push-Url": push},
    )


@router.get("/legacy/{key}/notes/{note_id}", response_class=HTMLResponse)
async def legacy_note(
    request: Request,
    background: BackgroundTasks,
    key: str,
    note_id: int,
    year: str = "",
    page: Page = 1,
    type: str = "",
) -> HTMLResponse:
    try:
        opened = await get_note(key, note_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_note", patient_key=key,
          detail={"section": "legacy", "note": opened.id})  # fmt: skip
    state = (("type", type[:60]), ("year", year), ("page", page))
    params = {k: v for k, v in state if v not in ("", 1)}
    push = url_with(f"/legacy/{key}", {"tab": "notes", **params}, note=note_id)
    return render(
        request,
        "partials/legacy_note.html",
        {"key": key, "note": opened, "partial": True},
        headers={"HX-Push-Url": push},
    )


@router.get("/legacy/{key}/notes/{note_id}/print", response_class=HTMLResponse)
async def legacy_note_print(
    request: Request, background: BackgroundTasks, key: str, note_id: int, user: User
) -> HTMLResponse:
    """Standalone printable page (no sidebar) for one pre-2010 chart note."""
    try:
        header = await get_header(key)
        opened = await get_note(key, note_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "print_note", patient_key=key,
          detail={"section": "legacy", "note": opened.id})  # fmt: skip
    printed = to_clinic_time(utcnow())
    return render(
        request,
        "pages/legacy_note_print.html",
        {"key": key, "header": header, "note": opened, "user": user,
         "printed_at": f"{date_us(printed)} {time_local(printed)}"},
    )  # fmt: skip


@router.get("/legacy/{key}/documents/{doc_id}", response_class=HTMLResponse)
async def legacy_document(
    request: Request,
    background: BackgroundTasks,
    key: str,
    doc_id: int,
    docpage: Page = 1,
    type: str = "",
    page: Page = 1,
) -> HTMLResponse:
    """Viewer panel for one scanned document (HTMX); pushes the full-page URL."""
    try:
        viewer = await document_viewer(key, doc_id, docpage)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    detail = {"section": "legacy", "kind": "scan", "id": doc_id, "page": viewer.page}
    audit(request, background, "view_document", patient_key=key, detail=detail)
    state = {"tab": "docs", "type": type[:60], "page": page}
    push = url_with(
        f"/legacy/{key}", state, doc=doc_id, docpage=viewer.page if viewer.page > 1 else None
    )
    return render(
        request,
        "partials/legacy_doc_viewer.html",
        {"key": key, "viewer": viewer, "state": state, "partial": True},
        headers={"HX-Push-Url": push},
    )


@router.get("/legacy/{key}/documents/{doc_id}/pages/{page_no}")
async def legacy_document_page(
    request: Request, background: BackgroundTasks, key: str, doc_id: int, page_no: int
) -> Response:
    """One page of a pre-2010 scan as PNG (only when LEGACY_SCAN_ROOT is configured)."""
    try:
        png = await document_page_png(key, doc_id, page_no)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_document", patient_key=key,
          detail={"section": "legacy", "kind": "scan", "id": doc_id, "page": page_no,
                  "image": True})  # fmt: skip
    return Response(content=png, media_type="image/png")


@router.get("/legacy/{key}/labs/{order_id}", response_class=HTMLResponse)
async def legacy_lab_order(
    request: Request,
    background: BackgroundTasks,
    key: str,
    order_id: int,
    year: str = "",
    page: Page = 1,
) -> HTMLResponse:
    """One lab order with its results (HTMX); pushes the full-page URL."""
    try:
        order = await lab_order(key, order_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_lab_order", patient_key=key,
          detail={"section": "legacy", "order": order.id})  # fmt: skip
    state = {"tab": "labs", "view": "reports", "year": year[:4], "page": page}
    return render(
        request,
        "partials/legacy_lab_order.html",
        {"key": key, "order": order, "partial": True},
        headers={"HX-Push-Url": url_with(f"/legacy/{key}", state, order=order_id)},
    )


@router.get("/legacy/{key}/photo")
async def legacy_photo(request: Request, background: BackgroundTasks, key: str) -> Response:
    """The legacy patient's photo (JPEG), shown in the chart header."""
    try:
        data = await patient_photo(key)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    audit(request, background, "view_document", patient_key=key,
          detail={"section": "legacy", "kind": "photo"})  # fmt: skip
    return Response(content=data, media_type="image/jpeg")
