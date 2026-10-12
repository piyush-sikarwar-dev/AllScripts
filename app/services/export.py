"""Records release: gather the chosen sections and render one PDF (CLAUDE.md §6, Phase 9).

The PDF reuses the same services / view models as the screens, so a release shows exactly what
staff see. Scanned pages are embedded page by page (one image per PDF page) when the scan store
is available; otherwise they are listed as "image not available". WeasyPrint runs in a worker
thread; nothing here logs patient data.
"""

import asyncio
import os
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

from app.config import get_settings
from app.crosswalk import PatientRef
from app.documents.images import to_png
from app.documents.render import DocumentFormatError
from app.documents.store import DocumentUnavailableError, get_store
from app.formatting import EMPTY, date_us, datetime_local, sort_key, to_clinic_time
from app.models.chart import ChartHeader
from app.repositories import source_repository
from app.services import NotFoundError, call
from app.services.chart_header import get_header
from app.services.labs import lab_row
from app.services.meds import med_row, medication_items
from app.services.patients import parse_dob as parse_us_date
from app.services.problems import problem_groups
from app.services.visits import visit_detail
from app.services.vitals import vital_row

SECTIONS: list[tuple[str, str]] = [
    ("demographics", "Demographics & insurance"),
    ("visits", "Visits with notes"),
    ("problems", "Problems & allergies"),
    ("meds", "Medications"),
    ("labs", "Lab results"),
    ("vitals", "Vitals"),
    ("documents", "Documents"),
]
SECTION_LABELS = dict(SECTIONS)
PURPOSES = ["Patient request", "Provider request", "Legal", "Insurance", "Other"]
VISIT_CONCURRENCY = 4
MAX_SCANNED_PAGES = 2000  # safety cap for one release

PDF_DIR = Path(__file__).resolve().parent.parent / "templates" / "pdf"
FONT_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"


@dataclass
class ExportRequest:
    sections: list[str] = field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    recipient: str = ""
    purpose: str = PURPOSES[0]
    # Raw form values (echoed back into the dialog on validation errors).
    raw_from: str = ""
    raw_to: str = ""
    errors: dict[str, str] = field(default_factory=dict)


def parse_export_form(form: Mapping[str, Any]) -> ExportRequest:
    sections = form.getlist("sections") if hasattr(form, "getlist") else form.get("sections", [])
    req = ExportRequest(
        sections=[s for s in SECTION_LABELS if s in set(sections)],
        recipient=str(form.get("recipient", "")).strip()[:300],
        purpose=str(form.get("purpose", "")),
        raw_from=str(form.get("date_from", "")).strip()[:10],
        raw_to=str(form.get("date_to", "")).strip()[:10],
    )
    if not req.sections:
        req.errors["sections"] = "Choose at least one section."
    if not req.recipient:
        req.errors["recipient"] = "Enter who the records are being released to."
    if req.purpose not in PURPOSES:
        req.errors["purpose"] = "Choose a purpose."
    for attr, raw in (("date_from", req.raw_from), ("date_to", req.raw_to)):
        try:
            setattr(req, attr, parse_us_date(raw))
        except ValueError:
            req.errors[attr] = "Enter the date as MM/DD/YYYY."
    if req.date_from and req.date_to and req.date_from > req.date_to:
        req.errors["date_to"] = "The end date is before the start date."
    return req


def _day(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return to_clinic_time(value).date() if value.tzinfo else value.date()
    return value


def _in_range(value: Any, req: ExportRequest) -> bool:
    if req.date_from is None and req.date_to is None:
        return True
    day = _day(value)
    if day is None:
        return False
    return (req.date_from is None or day >= req.date_from) and (
        req.date_to is None or day <= req.date_to
    )


def new_release_code(now: datetime) -> str:
    return f"R{now:%Y%m%d}-{secrets.token_hex(3).upper()}"


def pdf_filename(header: ChartHeader, now: datetime) -> str:
    """release_<chartid>_<yyyymmdd>.pdf — never the patient's name."""
    chart = re.sub(r"[^A-Za-z0-9-]", "", header.chart_id) or header.key.split(":")[-1]
    return f"release_{chart}_{now:%Y%m%d}.pdf"


async def _visits(ref: PatientRef, req: ExportRequest) -> list:
    rows = await call(source_repository().visits, ref.emr_id)
    rows = [v for v in rows if v["is_office_visit"] and _in_range(v["start"], req)]
    rows.sort(key=lambda v: sort_key(v["start"]), reverse=True)
    sem = asyncio.Semaphore(VISIT_CONCURRENCY)

    async def one(contact_id: int):
        async with sem:
            try:
                return await visit_detail(ref, contact_id)
            except NotFoundError:
                return None

    details = await asyncio.gather(*(one(v["contact_id"]) for v in rows))
    return [d for d in details if d is not None]


async def _documents(ref: PatientRef, req: ExportRequest) -> tuple[list[dict], dict[int, str]]:
    """Document listing (+ scanned pages when the store is available) and page_id → location."""
    repo = source_repository()
    rows = [d for d in await call(repo.documents, ref.emr_id) if _in_range(d["date"], req)]
    rows.sort(key=lambda d: sort_key(d["date"]), reverse=True)
    store_ready = get_store() is not None
    locations: dict[int, str] = {}
    out = []
    for d in rows:
        item = {"date": date_us(d["date"]), "type": d["type"], "title": d["title"] or EMPTY,
                "source": d["source"], "kind": d["kind"], "pages": [], "note": None}  # fmt: skip
        if d["kind"] == "scan" and store_ready and len(locations) < MAX_SCANNED_PAGES:
            doc = await call(repo.document_pages, ref.emr_id, d["id"])
            for p in (doc or {}).get("pages", []):
                if len(locations) >= MAX_SCANNED_PAGES:
                    break
                locations[p["page_id"]] = p["location"]
                item["pages"].append(p["page_id"])
        out.append(item)
    return out, locations


async def gather(ref: PatientRef, req: ExportRequest) -> dict[str, Any]:
    """Everything the PDF template needs, using the same services as the screens."""
    repo = source_repository()
    ctx: dict[str, Any] = {"header": await get_header(ref), "sections": req.sections}
    if "visits" in req.sections:
        ctx["visits"] = await _visits(ref, req)
    if "problems" in req.sections:
        ctx["problem_groups"] = await problem_groups(ref)
    if "meds" in req.sections:
        ctx["meds"] = [med_row(m) for m in await medication_items(ref, active_only=False)]
    if "labs" in req.sections:
        labs = [r for r in await call(repo.labs, ref.emr_id) if _in_range(r["date"], req)]
        labs.sort(key=lambda r: (sort_key(r["date"]), r["test"]), reverse=True)
        ctx["labs"] = [lab_row(r) for r in labs]
    if "vitals" in req.sections:
        vit = [v for v in await call(repo.vitals, ref.emr_id) if _in_range(v["date"], req)]
        vit.sort(key=lambda v: sort_key(v["date"]), reverse=True)
        ctx["vitals"] = [vital_row(v) for v in vit]
    ctx["page_locations"] = {}
    if "documents" in req.sections:
        ctx["documents"], ctx["page_locations"] = await _documents(ref, req)
    return ctx


def render_pdf(html: str, page_locations: dict[int, str]) -> tuple[bytes, int]:
    """HTML → PDF with WeasyPrint (sync; call in a worker thread). Returns (pdf, page_count)."""
    dll_dirs = get_settings().weasyprint_dll_directories
    if dll_dirs and not os.environ.get("WEASYPRINT_DLL_DIRECTORIES"):
        os.environ["WEASYPRINT_DLL_DIRECTORIES"] = dll_dirs  # read by WeasyPrint at import
    from weasyprint import CSS, HTML
    from weasyprint.urls import URLFetcher, URLFetcherResponse

    store = get_store()

    class ReleaseFetcher(URLFetcher):
        """Only scanned pages (scanpage:<id>) and the app's own font files may be loaded."""

        def fetch(self, url: str, headers: dict | None = None) -> URLFetcherResponse:
            if url.startswith("scanpage:"):
                location = page_locations.get(int(url.split(":", 1)[1]))
                if store is None or location is None:
                    raise ValueError("page not available")
                try:
                    png = to_png(store.read(location))
                except (DocumentUnavailableError, DocumentFormatError) as exc:
                    raise ValueError("page not available") from exc
                return URLFetcherResponse(url, body=png, headers={"Content-Type": "image/png"})
            if url.startswith("file:"):
                path = Path(url2pathname(urlparse(url).path)).resolve()
                if path.is_relative_to(FONT_DIR):
                    return super().fetch(url, headers)
            raise ValueError("external resources are not allowed in releases")

    fetcher = ReleaseFetcher(allowed_protocols={"file", "scanpage"})
    base = FONT_DIR.as_uri() + "/"
    css = CSS(filename=str(PDF_DIR / "pdf.css"), base_url=base, url_fetcher=fetcher)
    document = HTML(string=html, url_fetcher=fetcher, base_url=base).render(stylesheets=[css])
    return document.write_pdf(), len(document.pages)


def cover_context(req: ExportRequest, released_by: str, code: str, now: datetime) -> dict:
    if req.date_from or req.date_to:
        period = f"{date_us(req.date_from) if req.date_from else 'Start of record'} – " + (
            date_us(req.date_to) if req.date_to else "end of record"
        )
    else:
        period = "Entire record"
    return {
        "clinic_name": get_settings().clinic_name,
        "release_code": code,
        "released_by": released_by,
        "released_at": datetime_local(now),
        "recipient": req.recipient,
        "purpose": req.purpose,
        "period": period,
        "section_labels": [SECTION_LABELS[s] for s in req.sections],
    }
