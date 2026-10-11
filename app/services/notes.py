"""Notes tab (HTML documents, transcriptions, visit notes; later pre-2010 chart notes)."""

from app.crosswalk import PatientRef
from app.formatting import date_us, or_dash
from app.models.chart import NoteRow
from app.models.common import Pager, paginate
from app.repositories import source_repository
from app.services import call


async def notes_tab(ref: PatientRef, page: int | None) -> tuple[list[NoteRow], Pager]:
    rows = await call(source_repository().notes, ref.emr_id)
    rows.sort(key=lambda n: n["date"], reverse=True)
    page_rows, pager = paginate(rows, page or 1)
    return [
        NoteRow(
            date=date_us(n["date"]),
            title=or_dash(n["title"]),
            author=or_dash(n["author"]),
            source=n["source"],
        )
        for n in page_rows
    ], pager
