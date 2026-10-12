"""Release log page: who released which records, to whom, when."""

from datetime import date

from pydantic import BaseModel

from app.crosswalk.keys import parse_patient_key
from app.db.app import new_session
from app.formatting import datetime_local
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
