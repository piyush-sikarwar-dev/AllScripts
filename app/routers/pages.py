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
from app.services.patients import build_search, dashboard_totals, parse_dob, search_patients
from app.services.release_log import allscripts_release_page, release_page
from app.services.selection import export_item_count
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
            get_header(ref),
            tab_context(ref, tab, request.query_params, request.state.session_id),
        )
        export_count = await export_item_count(request.state.session_id, ref.patient_key)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc
    if ref.patient_key != key:  # merged-away record → the surviving chart
        return RedirectResponse(url_with(f"/patients/{ref.patient_key}", request.query_params),
                                status_code=303)  # fmt: skip
    audit(request, background, "view_patient", patient_key=ref.patient_key, detail={"tab": tab})
    if tab == "problems" and ctx.get("history_detail"):
        entry = ctx["history_detail"]
        audit(request, background, "view_history_entry", patient_key=ref.patient_key,
              detail={"entry_id": entry.id, "section": entry.section})  # fmt: skip
    if tab == "notes" and ctx.get("note"):
        audit(request, background, "view_note", patient_key=ref.patient_key,
              detail={"note": ctx["note"].ref, "category": ctx["note"].category,
                      "view": ctx["note"].view})  # fmt: skip
    if tab == "visits" and ctx.get("detail"):
        audit(request, background, "view_visit", patient_key=ref.patient_key,
              detail={"encounter_id": ctx["detail"].id, "view": ctx["detail"].view})  # fmt: skip
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
            "export_count": export_count,
            **ctx,
        },
    )


class _ReleaseFilters:
    def __init__(self, raw_from: str, raw_to: str) -> None:
        self.raw_from, self.raw_to = raw_from.strip()[:10], raw_to.strip()[:10]
        self.errors: dict[str, str] = {}
        self.date_from = self._parse("from", self.raw_from)
        self.date_to = self._parse("to", self.raw_to)

    def _parse(self, name: str, raw: str):
        try:
            return parse_dob(raw)
        except ValueError:
            self.errors[name] = "Enter the date as MM/DD/YYYY."
            return None


@router.get("/release-log", response_class=HTMLResponse)
async def release_log(
    request: Request,
    user: User,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    apage: Annotated[int, Query(ge=1, le=100_000)] = 1,
    date_from: Annotated[str, Query(alias="from")] = "",
    date_to: Annotated[str, Query(alias="to")] = "",
) -> HTMLResponse:
    filters = _ReleaseFilters(date_from, date_to)
    (rows, pager), (old_rows, old_pager) = await asyncio.gather(
        release_page(page, filters.date_from, filters.date_to),
        allscripts_release_page(apage, filters.date_from, filters.date_to),
    )
    return render(
        request,
        "pages/release_log.html",
        {"user": user, "nav": "release", "rows": rows, "pager": pager, "filters": filters,
         "old_rows": old_rows, "old_pager": old_pager, "page": pager.page},
    )  # fmt: skip
