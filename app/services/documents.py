"""Documents tab (scanned documents + HTML clinical documents). Viewer arrives in Phase 8."""

from app.config import get_settings
from app.crosswalk import PatientRef
from app.formatting import date_us, or_dash
from app.models.chart import DocumentRow
from app.models.common import Pager, paginate
from app.repositories import source_repository
from app.services import call


def scan_store_configured() -> bool:
    return bool(get_settings().scan_root)


async def documents_tab(
    ref: PatientRef, page: int | None, doc_type: str
) -> tuple[list[DocumentRow], Pager, list[str], str]:
    rows = await call(source_repository().documents, ref.emr_id)
    types = sorted({d["type"] for d in rows})
    doc_type = doc_type if doc_type in types else ""
    if doc_type:
        rows = [d for d in rows if d["type"] == doc_type]
    rows.sort(key=lambda d: d["date"], reverse=True)
    page_rows, pager = paginate(rows, page or 1)
    return (
        [
            DocumentRow(
                id=d["id"],
                date=date_us(d["date"]),
                type=d["type"],
                title=or_dash(d["title"]),
                pages=or_dash(d["pages"]),
                source=d["source"],
                # TODO(Phase 8): True once the DocumentStore can open this document.
                viewable=False,
            )
            for d in page_rows
        ],
        pager,
        types,
        doc_type,
    )
