"""Visits tab: visit list and visit detail."""

from app.crosswalk import PatientRef
from app.formatting import date_us, or_dash
from app.models.chart import LabeledValue, VisitDetail, VisitList, VisitSummary
from app.models.common import paginate
from app.repositories import source_repository
from app.services import NotFoundError, call
from app.services.vitals import vital_values

VISIT_FILTERS = ("office", "all")


def _summary(v: dict) -> VisitSummary:
    return VisitSummary(
        id=v["contact_id"],
        source=v["source"],
        date=date_us(v["start"]),
        type=or_dash(v["visit_type"]),
        provider=or_dash(v["provider"]),
        location=or_dash(v["location"]),
        diagnoses=", ".join(title for title, _code in v["diagnoses"]),
        signed=bool(v["signed"]),
    )


async def visit_detail(ref: PatientRef, visit_id: int) -> VisitDetail:
    repo = source_repository()
    v = await call(repo.visit, ref.emr_id, visit_id)
    if v is None:
        raise NotFoundError(f"visit {visit_id}")
    vitals = await call(repo.visit_vitals, ref.emr_id, visit_id)
    return VisitDetail(
        visit=_summary(v),
        assessment=[LabeledValue(label=code, value=title) for title, code in v["diagnoses"]],
        plan=list(v["plan"]),
        vitals=vital_values(vitals[0]) if vitals else [],
        addenda=list(v["addenda"]),
        note_text=v["note_text"],
    )


async def visit_list(
    ref: PatientRef, page: int | None, visit_filter: str, selected_id: int | None
) -> VisitList:
    visit_filter = visit_filter if visit_filter in VISIT_FILTERS else "office"
    rows = await call(source_repository().visits, ref.emr_id)
    if visit_filter == "office":
        rows = [v for v in rows if v["is_office_visit"]]
    rows.sort(key=lambda v: v["start"], reverse=True)
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
