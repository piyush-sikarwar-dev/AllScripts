"""Documents tab: scanned documents (+ page viewer) and clinical documents."""

from app.crosswalk import PatientRef
from app.documents.images import cached_png, frame_count
from app.documents.render import DocumentFormatError
from app.documents.store import DocumentUnavailableError, get_store
from app.formatting import date_us, or_dash, sort_key
from app.models.chart import DocumentRow, DocumentViewer
from app.models.common import Pager, paginate
from app.repositories import source_repository
from app.services import NotFoundError, call
from app.services.notes import note_detail

DOC_KINDS = ("scan", "document", "attachment")
# Chart attachments (NOTES_RAWDATA.NOTE_SUBFORMAT): images are shown page by page as PNG, PDFs
# are offered as a download, RTF-only attachments are shown as text.
IMAGE_FORMATS = frozenset({"tif", "tiff", "jpg", "jpeg", "png", "gif", "bmp"})
VIEWABLE_FORMATS = IMAGE_FORMATS | {"pdf", "rtf"}
_frame_counts: dict[int, int] = {}  # attachment id → pages (small, memory only)


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


# Source chips: (key, label). "attachment" files are stored in the database and always viewable;
# "scan" images need the scan share (SCAN_ROOT).
SOURCES: list[tuple[str, str]] = [
    ("", "All"),
    ("attachment", "Chart attachments"),
    ("scan", "Scanned"),
    ("document", "Clinical documents"),
]
FORMAT_LABELS = {"tif": "TIFF", "tiff": "TIFF", "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG",
                 "gif": "GIF", "bmp": "BMP", "pdf": "PDF", "rtf": "Text"}  # fmt: skip


def source_chips(rows: list[dict], selected: str) -> list[dict]:
    counts = {k: sum(1 for d in rows if not k or d["kind"] == k) for k, _ in SOURCES}
    return [{"key": k, "label": label, "count": counts[k], "selected": k == selected}
            for k, label in SOURCES if not k or counts[k]]  # fmt: skip


async def documents_tab(
    ref: PatientRef, page: int | None, doc_type: str, source: str = ""
) -> tuple[list[DocumentRow], Pager, list[str], str, str, list[dict]]:
    rows = await call(source_repository().documents, ref.emr_id)
    source = source if source in {k for k, _ in SOURCES} else ""
    chips = source_chips(rows, source)
    if source:
        rows = [d for d in rows if d["kind"] == source]
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
                viewable=d["kind"] == "document"
                or (d["kind"] == "attachment" and d.get("format") in VIEWABLE_FORMATS)
                or bool(store and d["pages"]),
                file_format=FORMAT_LABELS.get(
                    d.get("format") or "", (d.get("format") or "").upper()
                )
                if d["kind"] == "attachment"
                else "",
            )
            for d in page_rows
        ],
        pager,
        types,
        doc_type,
        source,
        chips,
    )


async def _attachment(ref: PatientRef, attachment_id: int) -> dict:
    """List entry of one chart attachment of this patient (404 otherwise)."""
    rows = await call(source_repository().documents, ref.emr_id)
    found = next((d for d in rows if d["kind"] == "attachment" and d["id"] == attachment_id), None)
    if found is None:
        raise NotFoundError(f"attachment {attachment_id}")
    return found


async def _attachment_bytes(ref: PatientRef, attachment_id: int) -> bytes:
    row = await call(source_repository().attachment_file, ref.emr_id, attachment_id)
    if not row or not row["content"]:
        raise NotFoundError(f"attachment {attachment_id}")
    return bytes(row["content"])


async def attachment_viewer(ref: PatientRef, attachment_id: int, page: int) -> DocumentViewer:
    item = await _attachment(ref, attachment_id)
    fmt = item.get("format") or ""
    meta = " · ".join(p for p in (date_us(item["date"]), item["type"], item.get("author"))
                      if p and p != "—")  # fmt: skip
    viewer = DocumentViewer(kind="attachment", id=attachment_id,
                            title=or_dash(item["title"] or item["type"]), meta=meta,
                            source=item["source"])  # fmt: skip
    base = f"/patients/{ref.patient_key}/documents/attachment/{attachment_id}"
    if fmt in IMAGE_FORMATS:
        pages = _frame_counts.get(attachment_id)
        if pages is None:
            try:
                pages = frame_count(await _attachment_bytes(ref, attachment_id))
            except (NotFoundError, DocumentFormatError):
                viewer.unavailable = "This attachment's image could not be read."
                return viewer
            if len(_frame_counts) > 500:
                _frame_counts.clear()
            _frame_counts[attachment_id] = pages
        viewer.pages = pages
        viewer.page = min(max(page, 1), pages)
        viewer.image_url = f"{base}/pages/{viewer.page}"
    elif fmt == "pdf":
        viewer.download_url = f"{base}/file"
    elif fmt == "rtf":
        viewer.text = await call(source_repository().attachment_text, ref.emr_id, attachment_id)
        if not viewer.text:
            viewer.unavailable = "This attachment's text is not available in the archive."
    else:
        label = fmt.upper() if fmt else "unknown"
        viewer.unavailable = f"This attachment is a {label} file, which can't be shown here."
    return viewer


async def attachment_png(ref: PatientRef, attachment_id: int, page: int) -> bytes:
    """PNG of one page of an image attachment of this patient."""
    item = await _attachment(ref, attachment_id)
    if item.get("format") not in IMAGE_FORMATS or page < 1:
        raise NotFoundError(f"attachment {attachment_id} page {page}")
    data = await _attachment_bytes(ref, attachment_id)
    try:
        return await call(cached_png, ("attachment", attachment_id, page), lambda: data, page - 1)
    except DocumentFormatError as exc:
        raise NotFoundError(f"attachment {attachment_id} page {page}") from exc


async def attachment_pdf(ref: PatientRef, attachment_id: int) -> bytes:
    """The PDF of a chart attachment of this patient (PDF bytes only)."""
    item = await _attachment(ref, attachment_id)
    data = await _attachment_bytes(ref, attachment_id) if item.get("format") == "pdf" else b""
    if not data.startswith(b"%PDF"):
        raise NotFoundError(f"attachment {attachment_id}")
    return data


async def document_viewer(ref: PatientRef, kind: str, doc_id: int, page: int) -> DocumentViewer:
    if kind == "attachment":
        return await attachment_viewer(ref, doc_id, page)
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
        noun = "page" if pages == 1 else "pages"
        viewer.unavailable = (
            f"The {pages} {noun} of this scanned document are on the scan archive, which is not "
            "connected yet. They will display here once it is mounted."
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


async def document_image(ref: PatientRef, doc_id: int, index: int) -> tuple[str, bytes]:
    """A picture embedded in a clinical document of this patient: (mime, bytes)."""
    found = await call(source_repository().document_image, ref.emr_id, doc_id, index)
    if found is None:
        raise NotFoundError(f"document {doc_id} image {index}")
    return found
