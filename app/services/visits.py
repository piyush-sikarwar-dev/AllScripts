"""Visits tab: visit list and visit detail."""

import asyncio

from app.crosswalk import PatientRef
from app.formatting import date_us, or_dash, sort_key, time_local
from app.models.chart import (
    DocumentLink,
    LabeledValue,
    RenderedDocument,
    VisitDetail,
    VisitList,
    VisitSummary,
    VitalReading,
)
from app.models.common import paginate
from app.repositories import source_repository
from app.services import NotFoundError, call
from app.services.vitals import vital_values

VISIT_FILTERS = ("office", "all")


def _diagnoses_text(v: dict) -> str:
    dx = v["diagnoses"]
    if isinstance(dx, str):  # real data: ENCOUNTER.ENC_DIAGNOSES summary
        return dx
    return ", ".join(title for title, _code in dx)  # fake data: (title, code) pairs


def _summary(v: dict) -> VisitSummary:
    return VisitSummary(
        id=v["contact_id"],
        source=v["source"],
        date=date_us(v["start"]),
        type=or_dash(v["visit_type"]),
        provider=or_dash(v["provider"]),
        location=or_dash(v["location"]),
        diagnoses=_diagnoses_text(v),
        signed=bool(v["signed"]),
    )


def _doc_meta(d: dict) -> str:
    parts = [date_us(d.get("created")), (d.get("author") or "").strip()]
    return " · ".join(p for p in parts if p and p != "—")


async def visit_detail(ref: PatientRef, visit_id: int) -> VisitDetail:
    repo = source_repository()
    v, vitals = await asyncio.gather(
        call(repo.visit, ref.emr_id, visit_id), call(repo.visit_vitals, ref.emr_id, visit_id)
    )
    if v is None:
        raise NotFoundError(f"visit {visit_id}")
    pairs = v.get("assessment")
    if pairs is None:  # fake data keeps the pairs in "diagnoses"
        pairs = v["diagnoses"]
    return VisitDetail(
        visit=_summary(v),
        assessment=[LabeledValue(label=code or "—", value=title) for title, code in pairs],
        plan=list(v["plan"]),
        vitals=vital_values(vitals[0]) if vitals else [],
        more_vitals=[
            VitalReading(time=time_local(r["date"]), values=vital_values(r)) for r in vitals[1:]
        ],
        addenda=list(v["addenda"]),
        note_text=v["note_text"],
        documents=[
            RenderedDocument(title=d["title"], meta=_doc_meta(d), html=d["html"])
            for d in v.get("note_documents", [])
        ],
        other_documents=[
            DocumentLink(kind="document", id=d["id"], title=d["title"], meta=_doc_meta(d))
            for d in v.get("other_documents", [])
        ],
    )


async def visit_list(
    ref: PatientRef, page: int | None, visit_filter: str, selected_id: int | None
) -> VisitList:
    visit_filter = visit_filter if visit_filter in VISIT_FILTERS else "office"
    office_only = visit_filter == "office"
    rows = await call(source_repository().visits, ref.emr_id, office_only)
    if office_only:  # the repository already filtered; kept as a guarantee
        rows = [v for v in rows if v["is_office_visit"]]
    # Newest first; visits at the same date/time keep a stable order (by visit number).
    rows.sort(key=lambda v: (sort_key(v["start"]), v["contact_id"]), reverse=True)
    page_rows, pager = paginate(rows, page or 1)
    visits = [_summary(v) for v in page_rows]
    if selected_id is None and visits:
        selected_id = visits[0].id
    selected = None
    if selected_id is not None:
        try:
            selected = await visit_detail(ref, selected_id)
        except NotFoundError:
            selected = None
    return VisitList(visits=visits, pager=pager, filter=visit_filter, selected=selected)
