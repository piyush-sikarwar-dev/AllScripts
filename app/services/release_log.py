"""Release log page: who released which records, to whom, when."""

from datetime import date

from pydantic import BaseModel

from app.crosswalk.keys import parse_patient_key
from app.db.app import new_session
from app.formatting import EMPTY, date_us, datetime_local, person_name, to_clinic_time
from app.lookups import label
from app.models.common import PAGE_SIZE, Pager, clamp_page
from app.repositories import source_repository
from app.repositories.appdb import releases
from app.services import call
from app.services.export import SECTION_LABELS


class ReleaseRow(BaseModel):
    date: str
    release_code: str
    patient_key: str
    patient_name: str
    sections: str
    recipient: str
    purpose: str
    pages: int
    released_by: str


def _page(page: int, date_from: date | None, date_to: date | None):
    with new_session() as db:
        return releases.page(db, offset=(page - 1) * PAGE_SIZE, limit=PAGE_SIZE,
                             date_from=date_from, date_to=date_to)  # fmt: skip


async def release_page(
    page: int | None, date_from: date | None, date_to: date | None
) -> tuple[list[ReleaseRow], Pager]:
    page = clamp_page(page)
    rows, total = await call(_page, page, date_from, date_to)
    emr_ids = sorted(
        {k.id for r, _ in rows if (k := parse_patient_key(r.patient_key)) and k.source == "EMR"}
    )
    names = await call(source_repository().patient_names, emr_ids) if emr_ids else {}
    out = []
    for r, released_by in rows:
        key = parse_patient_key(r.patient_key)
        out.append(
            ReleaseRow(
                date=datetime_local(r.at),
                release_code=r.release_code or "—",
                patient_key=r.patient_key,
                patient_name=names.get(key.id, r.patient_key) if key else r.patient_key,
                sections=", ".join(SECTION_LABELS.get(s, s) for s in r.sections or []),
                recipient=r.recipient,
                purpose=r.purpose or "—",
                pages=r.page_count,
                released_by=released_by,
            )
        )
    return out, Pager(page=page, total=total)


class AllscriptsReleaseRow(BaseModel):
    date: str
    patient_key: str
    patient_name: str
    requested: str
    status: str
    approval: str
    completed: str
    requester: str
    entered_by: str


def _local_day(value) -> date | None:
    return to_clinic_time(value).date() if value is not None else None


def _allscripts_row(r: dict, names: dict[int, str]) -> AllscriptsReleaseRow:
    asked = [label("phi_requested_info", c) for c in r.get("requested") or []]
    if r.get("entire_chart"):
        asked.insert(0, "Entire chart")
    approval = (r.get("approval_text") or "").strip()
    emr_id = r.get("emr_id")
    return AllscriptsReleaseRow(
        date=datetime_local(r.get("entered_at")),
        patient_key=f"EMR:{emr_id}",
        patient_name=names.get(emr_id, f"EMR:{emr_id}"),
        requested=", ".join(asked) or EMPTY,
        status=(r.get("status_text") or "").strip() or EMPTY,
        approval="" if approval in ("", "Not Required") else approval,
        completed=date_us(_local_day(r.get("completed_at"))),
        requester=(r.get("requester") or "").strip() or EMPTY,
        entered_by=person_name(r.get("entered_last"), r.get("entered_first")),
    )


async def allscripts_release_page(
    page: int | None, date_from: date | None, date_to: date | None
) -> tuple[list[AllscriptsReleaseRow], Pager]:
    """Release-of-information requests recorded in Allscripts before it was retired (PHIREQUEST),
    newest first; the date filter applies to the request date."""
    page = clamp_page(page)
    rows = await call(source_repository().phi_requests)
    chosen = [
        r
        for r in rows
        if (date_from is None or (_local_day(r.get("entered_at")) or date.min) >= date_from)
        and (date_to is None or (_local_day(r.get("entered_at")) or date.max) <= date_to)
    ]
    pager = Pager(page=page, total=len(chosen))
    shown = chosen[pager.offset : pager.offset + PAGE_SIZE]
    emr_ids = sorted({r["emr_id"] for r in shown if r.get("emr_id") is not None})
    names = await call(source_repository().patient_names, emr_ids) if emr_ids else {}
    return [_allscripts_row(r, names) for r in shown], pager
