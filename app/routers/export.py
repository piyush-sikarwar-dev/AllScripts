"""Records release: export dialog / form and the PDF download (CLAUDE.md §6, Phase 9)."""

import hashlib
import logging
import re
from typing import Annotated

import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from app.audit import audit
from app.auth import CurrentUser, current_user, require_csrf
from app.config import get_settings
from app.crosswalk import PatientRef, resolve
from app.db.app import new_session
from app.formatting import to_clinic_time
from app.repositories.appdb import releases, utcnow
from app.services import NotFoundError, call
from app.services.chart_header import get_header
from app.services.export import (
    PURPOSES,
    SECTIONS,
    ExportRequest,
    cover_context,
    gather,
    new_release_code,
    parse_export_form,
    pdf_filename,
    render_pdf,
)
from app.services.history_service import entry_choices, selected_entry_ids
from app.services.notes_service import note_choices, selected_note_refs
from app.services.visits import selected_visit_ids, visit_choices
from app.templating import is_htmx, render, templates

log = logging.getLogger("app.export")
DOWNLOAD_COOKIE = "export_download"
DOWNLOAD_TOKEN = re.compile(r"[A-Za-z0-9]{8,40}")

router = APIRouter(dependencies=[Depends(current_user)])

User = Annotated[CurrentUser, Depends(current_user)]


async def _resolve(key: str) -> PatientRef:
    try:
        return await resolve(key)
    except NotFoundError as exc:
        raise HTTPException(status_code=404) from exc


async def _form(
    request: Request, ref: PatientRef, header, req: ExportRequest, status: int = 200
) -> HTMLResponse:
    selected = await selected_visit_ids(request.state.session_id, ref.patient_key)
    notes = await selected_note_refs(request.state.session_id, ref.patient_key)
    history = await selected_entry_ids(request.state.session_id, ref.patient_key)
    ctx = {"key": ref.patient_key, "header": header, "req": req, "sections": SECTIONS,
           "purposes": PURPOSES, "nav": "patients",
           "visit_choices": await visit_choices(ref, selected),
           "note_choices": await note_choices(ref, notes),
           "history_choices": await entry_choices(ref, history)}  # fmt: skip
    if is_htmx(request):
        return render(request, "partials/export_dialog.html", ctx, status_code=status)
    return render(request, "pages/export.html", ctx, status_code=status)


@router.get("/patients/{key}/export", response_class=HTMLResponse)
async def export_form(request: Request, key: str) -> HTMLResponse:
    ref = await _resolve(key)
    header = await get_header(ref)
    selected = await selected_visit_ids(request.state.session_id, ref.patient_key)
    notes = await selected_note_refs(request.state.session_id, ref.patient_key)
    history = await selected_entry_ids(request.state.session_id, ref.patient_key)
    # Items added with "Add to export" → release only those by default; else the whole record.
    sections = [] if selected or notes or history else [s for s, _ in SECTIONS]
    req = ExportRequest(sections=sections, visit_ids=sorted(selected), note_ids=sorted(notes),
                        history_ids=sorted(history))  # fmt: skip
    return await _form(request, ref, header, req)


@router.post("/patients/{key}/export", dependencies=[Depends(require_csrf)])
async def export_pdf(
    request: Request, background: BackgroundTasks, key: str, user: User
) -> Response:
    ref = await _resolve(key)
    header = await get_header(ref)
    form = await request.form()
    req = parse_export_form(form)
    if req.errors:
        return await _form(request, ref, header, req, status=400)

    now = utcnow()
    code = new_release_code(to_clinic_time(now))
    ctx = await gather(ref, req)
    cover = cover_context(req, user.full_name, code, now)
    html = templates.get_template("pdf/export.html").render(**ctx, cover=cover)
    try:
        pdf, pages = await anyio.to_thread.run_sync(render_pdf, html, ctx["page_locations"])
    except (OSError, ImportError) as exc:  # PDF engine (Pango) not available on this machine
        log.error("pdf engine unavailable: %s", type(exc).__name__)
        return render(request, "pages/errors/export_unavailable.html", {"nav": "patients"},
                      status_code=503)  # fmt: skip

    def save() -> None:
        with new_session() as db:
            releases.insert(
                db,
                user_id=user.id,
                patient_key=ref.patient_key,
                sections=req.sections
                + (["selected_visits"] if req.visit_ids and "visits" not in req.sections else [])
                + (["selected_notes"] if req.note_ids else [])
                + (["selected_history"] if req.history_ids else []),
                date_from=req.date_from,
                date_to=req.date_to,
                recipient=req.recipient,
                page_count=pages,
                file_sha256=hashlib.sha256(pdf).hexdigest(),
                release_code=code,
                purpose=req.purpose,
            )

    await call(save)
    audit(request, background, "export", patient_key=ref.patient_key,
          detail={"release_code": code, "sections": req.sections, "pages": pages,
                  "selected_visits": len(req.visit_ids),
                  "selected_notes": len(req.note_ids),
                  "selected_history": len(req.history_ids)})  # fmt: skip
    filename = pdf_filename(header, to_clinic_time(now))
    response = Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
    token = str(form.get("download_token", ""))
    if DOWNLOAD_TOKEN.fullmatch(token):
        # Lets the page see that the download has started (app.js); holds no data.
        response.set_cookie(DOWNLOAD_COOKIE, token, max_age=120, path="/", samesite="lax",
                            secure=get_settings().cookie_secure, httponly=False)  # fmt: skip
    return response
