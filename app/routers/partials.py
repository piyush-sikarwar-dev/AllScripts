"""HTMX fragments: patient search rows, chart tabs, visit detail, export dialog.

Every fragment URL also has a full-page equivalent; `HX-Push-Url` points the browser history at
that full-page URL so reloads and shared links work without HTMX.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.auth import CurrentUser, current_user
from app.crosswalk import PatientRef, resolve
from app.services import NotFoundError
from app.services.patients import build_search, search_patients
from app.services.tabs import TAB_NAMES, TABS, tab_context
from app.services.visits import visit_detail
from app.templating import render, url_with

router = APIRouter(dependencies=[Depends(current_user)])

User = Annotated[CurrentUser, Depends(current_user)]


async def _resolve(key: str) -> PatientRef:
    try:
        return await resolve(key)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc


@router.get("/patients/rows", response_class=HTMLResponse)
async def patient_rows(
    request: Request,
    q: str = "",
    dob: str = "",
    chart: str = "",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
) -> HTMLResponse:
    search = build_search(q, dob, chart)
    results = await search_patients(search, page)
    push = url_with("/patients", search.params(), page=results.pager.page)
    return render(
        request,
        "partials/patient_rows.html",
        {"results": results, "partial": True},
        headers={"HX-Push-Url": push},
    )


@router.get("/patients/{key}/tab/{name}", response_class=HTMLResponse)
async def chart_tab(request: Request, key: str, name: str) -> HTMLResponse:
    if name not in TAB_NAMES:
        raise HTTPException(status_code=404)
    ref = await _resolve(key)
    try:
        ctx = await tab_context(ref, name, request.query_params)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    pager = ctx.get("pager") or getattr(ctx.get("visit_list"), "pager", None)
    push_params = {"tab": name, **ctx["state"], "page": pager.page if pager else None}
    if name == "visits" and ctx["visit_list"].selected:
        push_params["visit"] = ctx["visit_list"].selected.visit.id
    return render(
        request,
        "partials/tab_frame.html",
        {"key": ref.patient_key, "tabs": TABS, "tab": name, "partial": True, **ctx},
        headers={"HX-Push-Url": url_with(f"/patients/{ref.patient_key}", push_params)},
    )


@router.get("/patients/{key}/visits/{source}/{visit_id}", response_class=HTMLResponse)
async def visit_panel(
    request: Request,
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


@router.get("/patients/{key}/export", response_class=HTMLResponse)
async def export_dialog(request: Request, key: str) -> HTMLResponse:
    ref = await _resolve(key)
    # TODO(Phase 9): sections, date range, recipient, purpose; CSRF-protected POST.
    return render(request, "partials/export_dialog.html", {"key": ref.patient_key})
