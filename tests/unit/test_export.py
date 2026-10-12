"""Phase 9: export form validation, PDF release (fake data), release log + audit rows."""

import io
import re
from datetime import date

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.db.app import new_session
from app.repositories.appdb.models import AuditLog, ReleaseLog
from app.services.export import SECTIONS, parse_export_form
from tests.conftest import page_csrf
from tests.fakes.data import PATIENTS

FIRST = f"EMR:{PATIENTS[0].emr_id}"
HTMX = {"HX-Request": "true"}
ALL_SECTIONS = [s for s, _ in SECTIONS]


def _pdf_engine_available() -> bool:
    try:
        from app.services.export import render_pdf

        render_pdf("<p>x</p>", {})
        return True
    except (OSError, ImportError):
        return False


needs_pdf = pytest.mark.skipif(not _pdf_engine_available(), reason="WeasyPrint/Pango not installed")


class Form(dict):
    def getlist(self, key):
        value = self.get(key, [])
        return value if isinstance(value, list) else [value]


# --- form validation ---------------------------------------------------------------------------


def test_parse_export_form_valid():
    form = Form(
        sections=["labs", "visits", "bogus"],
        recipient=" Dr. Example ",
        purpose="Legal",
        date_from="01/01/2015",
        date_to="12/31/2016",
    )
    req = parse_export_form(form)
    assert req.errors == {}
    assert req.sections == ["visits", "labs"]  # canonical order, unknown dropped
    assert (req.date_from, req.date_to) == (date(2015, 1, 1), date(2016, 12, 31))
    assert req.recipient == "Dr. Example"


def test_parse_export_form_errors():
    req = parse_export_form(Form(sections=[], recipient="", purpose="Gossip",
                                 date_from="13/45/2015", date_to=""))  # fmt: skip
    assert set(req.errors) == {"sections", "recipient", "purpose", "date_from"}
    req = parse_export_form(Form(sections=["labs"], recipient="x", purpose="Legal",
                                 date_from="02/01/2020", date_to="01/01/2020"))  # fmt: skip
    assert "date_to" in req.errors


# --- routes ------------------------------------------------------------------------------------


def test_export_dialog_and_page(client):
    r = client.get(f"/patients/{FIRST}/export", headers=HTMX)
    assert r.status_code == 200 and 'name="sections"' in r.text and "<html" not in r.text
    assert 'name="csrf_token"' in r.text
    r = client.get(f"/patients/{FIRST}/export")
    assert r.status_code == 200 and "<html" in r.text and "Back to chart" in r.text


def test_export_requires_csrf(client):
    r = client.post(f"/patients/{FIRST}/export",
                    data={"sections": ["labs"], "recipient": "x", "purpose": "Legal"})  # fmt: skip
    assert r.status_code == 403


def test_export_validation_errors_rerender_form(client):
    data = {"csrf_token": page_csrf(client), "recipient": "", "purpose": "Legal"}
    r = client.post(f"/patients/{FIRST}/export", data=data)
    assert r.status_code == 400
    assert "Choose at least one section." in r.text and "Enter who the records" in r.text
    with new_session() as db:
        assert db.scalar(select(ReleaseLog)) is None


def _export(client, key=FIRST, **extra):
    data = {"csrf_token": page_csrf(client), "sections": ALL_SECTIONS,
            "recipient": "Example Law Office", "purpose": "Legal"} | extra  # fmt: skip
    return client.post(f"/patients/{key}/export", data=data)


@needs_pdf
def test_export_creates_pdf_release_log_and_audit(client):
    r = _export(client)
    assert r.status_code == 200, r.text[:500]
    assert r.headers["content-type"] == "application/pdf"
    disposition = r.headers["content-disposition"]
    assert re.search(rf'filename="release_{PATIENTS[0].chart_id}_\d{{8}}\.pdf"', disposition)
    assert "Sample" not in disposition  # never the patient's name in the filename

    reader = PdfReader(io.BytesIO(r.content))
    first = reader.pages[0].extract_text()
    assert "Medical records release" in first and "Example Law Office" in first
    assert f"Page 1 of {len(reader.pages)}" in first
    text = "\n".join(p.extract_text() for p in reader.pages)
    for heading in ("Visits with notes", "Problems & allergies", "Lab results", "Vitals"):
        assert heading in text

    with new_session() as db:
        rel = db.scalar(select(ReleaseLog))
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "export"))
    assert rel.page_count == len(reader.pages) and len(rel.file_sha256) == 64
    assert rel.purpose == "Legal" and rel.recipient == "Example Law Office"
    assert rel.release_code in first
    assert audit.patient_key == FIRST and audit.detail["release_code"] == rel.release_code
    assert "Example Law Office" not in str(audit.detail)

    page = client.get("/release-log")
    assert rel.release_code in page.text and "Example Law Office" in page.text
    assert "Sample, Patient A" in page.text


@needs_pdf
def test_export_date_range_limits_sections(client):
    r = _export(client, sections=["labs"], date_from="01/01/1990", date_to="01/02/1990")
    assert r.status_code == 200
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "No lab results in the selected period." in text
    assert "Visits with notes" not in text  # section not chosen


@needs_pdf
def test_export_embeds_scanned_pages_when_store_available(client, tmp_path, monkeypatch):
    from PIL import Image

    from app import config

    patient = next(p for p in PATIENTS if any(d["kind"] == "scan" for d in p.documents))
    docs = [d for d in patient.documents if d["kind"] == "scan"]
    (tmp_path / "fake").mkdir()
    for d in docs:
        for n in range(1, d["pages"] + 1):
            buf = io.BytesIO()
            Image.new("L", (85, 110), color=200).save(buf, format="TIFF")
            (tmp_path / "fake" / f"{d['id']}-{n}").write_bytes(buf.getvalue())
    settings = config.get_settings().model_copy(update={"scan_root": str(tmp_path)})
    monkeypatch.setattr("app.documents.store.get_settings", lambda: settings)

    r = _export(client, key=f"EMR:{patient.emr_id}", sections=["documents"])
    assert r.status_code == 200, r.text[:300]
    reader = PdfReader(io.BytesIO(r.content))
    expected_scans = sum(d["pages"] for d in docs)
    assert len(reader.pages) >= 2 + expected_scans  # cover + listing + one page per scan
    assert re.search(r"page \d+ of \d+", reader.pages[-1].extract_text())


def test_release_log_date_filter_validation(client):
    r = client.get("/release-log", params={"from": "99/99/9999"})
    assert r.status_code == 200 and "Enter the date as MM/DD/YYYY." in r.text
