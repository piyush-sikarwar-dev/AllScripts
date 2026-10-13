"""Contact-level visits (one row per CONTACT): used by the PDF export. The Visits tab uses
app.services.visits (one visit = one encounter)."""

import asyncio

from app.crosswalk import PatientRef
from app.formatting import date_us, or_dash, time_local
from app.models.chart import (
    DocumentLink,
    LabeledValue,
    RenderedDocument,
    VisitDetail,
    VisitSummary,
    VitalReading,
)
from app.repositories import source_repository
from app.services import NotFoundError, call
from app.services.vitals import vital_values


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
