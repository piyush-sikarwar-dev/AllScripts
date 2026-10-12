"""Notes tab: clinical documents and dictations (later: pre-2010 chart notes)."""

from app.crosswalk import PatientRef
from app.formatting import date_us, or_dash, sort_key
from app.models.chart import NoteDetail, NoteRow
from app.models.common import Pager, paginate
from app.repositories import source_repository
from app.services import NotFoundError, call

NOTE_KINDS = ("document", "transcription")


def parse_note_ref(raw: str | None) -> tuple[str, int] | None:
    """'document-123' → ('document', 123); anything else → None."""
    if not raw or "-" not in raw:
        return None
    kind, _, ident = raw.rpartition("-")
    if kind not in NOTE_KINDS or not ident.isdigit() or len(ident) > 10:
        return None
    return kind, int(ident)


def _meta(n: dict) -> str:
    parts = [date_us(n["date"]), (n.get("author") or "").strip()]
    return " · ".join(p for p in parts if p and p != "—")


async def notes_tab(ref: PatientRef, page: int | None) -> tuple[list[NoteRow], Pager]:
    rows = await call(source_repository().notes, ref.emr_id)
    rows.sort(key=lambda n: sort_key(n["date"]), reverse=True)
    page_rows, pager = paginate(rows, page or 1)
    return [
        NoteRow(
            kind=n["kind"],
            id=n["id"],
            date=date_us(n["date"]),
            title=or_dash(n["title"]),
            author=or_dash(n["author"]),
            source=n["source"],
        )
        for n in page_rows
    ], pager


async def note_detail(ref: PatientRef, kind: str, note_id: int) -> NoteDetail:
    if kind not in NOTE_KINDS:
        raise NotFoundError(kind)
    n = await call(source_repository().note, ref.emr_id, kind, note_id)
    if n is None:
        raise NotFoundError(f"{kind} {note_id}")
    return NoteDetail(
        kind=kind,
        id=note_id,
        title=or_dash(n["title"]),
        meta=_meta(n),
        source=n["source"],
        html=n.get("html"),
        text=n.get("text"),
    )
