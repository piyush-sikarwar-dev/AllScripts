"""Full pages: dashboard, patient chart, release log."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.audit import audit
from app.auth import CurrentUser, current_user
from app.crosswalk import resolve
from app.services import NotFoundError
from app.services.chart_header import get_header
from app.services.patients import build_search, dashboard_totals, search_patients
from app.services.tabs import TAB_LABELS, TAB_NAMES, TABS, tab_context
from app.templating import render, url_with

router = APIRouter()

User = Annotated[CurrentUser, Depends(current_user)]


@router.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse("/patients", status_code=303)


@router.get("/patients", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    background: BackgroundTasks,
    user: User,
    q: str = "",
    dob: str = "",
    chart: str = "",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
) -> HTMLResponse:
    search = build_search(q, dob, chart)
    totals, results = await asyncio.gather(dashboard_totals(), search_patients(search, page))
    audit(request, background, "search",
          detail={"fields": search.fields_used(), "page": results.pager.page})  # fmt: skip
    return render(
        request,
        "pages/dashboard.html",
        {"user": user, "nav": "dashboard", "totals": totals, "results": results},
    )


@router.get("/patients/{key}", response_class=HTMLResponse)
async def chart(
    request: Request, background: BackgroundTasks, key: str, user: User, tab: str = "overview"
) -> Response:
    if tab not in TAB_NAMES:
        raise HTTPException(status_code=404)
    try:
        ref = await resolve(key)
        header, ctx = await asyncio.gather(
            get_header(ref), tab_context(ref, tab, request.query_params)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    if ref.patient_key != key:  # merged-away record → the surviving chart
        return RedirectResponse(url_with(f"/patients/{ref.patient_key}", request.query_params),
                                status_code=303)  # fmt: skip
    audit(request, background, "view_patient", patient_key=ref.patient_key, detail={"tab": tab})
    return render(
        request,
        "pages/chart.html",
        {
            "user": user,
            "nav": "patients",
            "header": header,
            "key": ref.patient_key,
            "tabs": TABS,
            "tab_labels": TAB_LABELS,
            "tab": tab,
            **ctx,
        },
    )


@router.get("/release-log", response_class=HTMLResponse)
async def release_log(request: Request, user: User) -> HTMLResponse:
    # TODO(Phase 9): read release_log from the app database.
    return render(request, "pages/release_log.html", {"user": user, "nav": "release", "rows": []})
