"""Documents tab: scanned documents (+ page viewer) and clinical documents."""

from app.crosswalk import PatientRef
from app.documents.images import cached_png
from app.documents.render import DocumentFormatError
from app.documents.store import DocumentUnavailableError, get_store
from app.formatting import date_us, or_dash, sort_key
from app.models.chart import DocumentRow, DocumentViewer
from app.models.common import Pager, paginate
from app.repositories import source_repository
from app.services import NotFoundError, call
from app.services.notes import note_detail

DOC_KINDS = ("scan", "document")


def scan_store_configured() -> bool:
    return get_store() is not None


def parse_doc_ref(raw: str | None) -> tuple[str, int] | None:
    """'scan-123' → ('scan', 123)."""
    if not raw or "-" not in raw:
        return None
    kind, _, ident = raw.rpartition("-")
    if kind not in DOC_KINDS or not ident.isdigit() or len(ident) > 10:
        return None
    return kind, int(ident)


async def documents_tab(
    ref: PatientRef, page: int | None, doc_type: str
) -> tuple[list[DocumentRow], Pager, list[str], str]:
    rows = await call(source_repository().documents, ref.emr_id)
    types = sorted({d["type"] for d in rows})
    doc_type = doc_type if doc_type in types else ""
    if doc_type:
        rows = [d for d in rows if d["type"] == doc_type]
    rows.sort(key=lambda d: sort_key(d["date"]), reverse=True)
    page_rows, pager = paginate(rows, page or 1)
    store = scan_store_configured()
    return (
        [
            DocumentRow(
                kind=d["kind"],
                id=d["id"],
                date=date_us(d["date"]),
                type=d["type"],
                title=or_dash(d["title"]),
                pages=or_dash(d["pages"]),
                source=d["source"],
                viewable=d["kind"] == "document" or (store and bool(d["pages"])),
            )
            for d in page_rows
        ],
        pager,
        types,
        doc_type,
    )


async def document_viewer(ref: PatientRef, kind: str, doc_id: int, page: int) -> DocumentViewer:
    if kind == "document":
        note = await note_detail(ref, "document", doc_id)
        return DocumentViewer(
            kind=kind, id=doc_id, title=note.title, meta=note.meta, source=note.source, note=note
        )
    if kind != "scan":
        raise NotFoundError(kind)
    doc = await call(source_repository().document_pages, ref.emr_id, doc_id)
    if doc is None:
        raise NotFoundError(f"scan {doc_id}")
    pages = len(doc["pages"])
    page = min(max(page, 1), max(pages, 1))
    viewer = DocumentViewer(
        kind=kind,
        id=doc_id,
        title=or_dash(doc["title"] or doc["type"]),
        meta=" · ".join(p for p in (date_us(doc["date"]), doc["type"]) if p and p != "—"),
        source=doc["source"],
        page=page,
        pages=pages,
    )
    if pages == 0:
        viewer.unavailable = "This document has no pages in the archive."
    elif not scan_store_configured():
        viewer.unavailable = (
            "Scanned page images are not connected yet. "
            "The page will display once the scan archive is mounted."
        )
    else:
        viewer.image_url = f"/patients/{ref.patient_key}/documents/scan/{doc_id}/pages/{page}"
    return viewer


async def page_png(ref: PatientRef, doc_id: int, page: int) -> bytes:
    """PNG bytes of one scanned page (ownership checked through the document query)."""
    store = get_store()
    if store is None:
        raise NotFoundError("scan store not configured")
    doc = await call(source_repository().document_pages, ref.emr_id, doc_id)
    if doc is None or not 1 <= page <= len(doc["pages"]):
        raise NotFoundError(f"scan {doc_id} page {page}")
    target = doc["pages"][page - 1]

    def load() -> bytes:
        return store.read(target["location"])

    try:
        return await call(cached_png, target["page_id"], load)
    except (DocumentUnavailableError, DocumentFormatError) as exc:
        raise NotFoundError(f"scan {doc_id} page {page}") from exc
