"""Documents tab: chart attachments (CHARTATTACHMENT + NOTES_RAWDATA files)."""

import io
from datetime import UTC, datetime

import pytest
from PIL import Image
from sqlalchemy import select

from app.db.app import new_session
from app.documents.images import frame_count, to_png
from app.documents.render import DocumentFormatError
from app.repositories import emr, live
from app.repositories.appdb.models import AuditLog
from tests.fakes.data import PATIENTS

HTMX = {"HX-Request": "true"}


def _with(fmt: str):
    for p in PATIENTS:
        for d in p.documents:
            if d["kind"] == "attachment" and d["format"] == fmt:
                return f"EMR:{p.emr_id}", d
    raise AssertionError(f"fake data has no {fmt} attachment")


def _audit() -> list[AuditLog]:
    with new_session() as db:
        return list(db.scalars(select(AuditLog).where(AuditLog.action == "view_document")))


def test_attachments_are_listed_with_their_type(client):
    key, d = _with("tif")
    r = client.get(f"/patients/{key}", params={"tab": "docs", "type": d["type"]})
    assert r.status_code == 200 and d["title"] in r.text


def test_tiff_attachment_pages(client):
    key, d = _with("tif")
    r = client.get(f"/patients/{key}/documents/attachment/{d['id']}", headers=HTMX)
    assert r.status_code == 200 and "2 pages" in r.text and "Page 1 of 2" in r.text
    url = f"/patients/{key}/documents/attachment/{d['id']}/pages"
    for page in (1, 2):
        img = client.get(f"{url}/{page}")
        assert img.status_code == 200 and img.headers["content-type"] == "image/png"
        assert img.content.startswith(b"\x89PNG")
    assert client.get(f"{url}/3").status_code == 404
    assert _audit()[-1].detail == {"kind": "attachment", "id": d["id"], "page": 2, "image": True}
    r = client.get(
        f"/patients/{key}/documents/attachment/{d['id']}", params={"docpage": 2}, headers=HTMX
    )
    assert "Page 2 of 2" in r.text


def test_pdf_attachment_is_a_download(client):
    key, d = _with("pdf")
    r = client.get(f"/patients/{key}/documents/attachment/{d['id']}", headers=HTMX)
    assert "Download PDF" in r.text and "<iframe" not in r.text
    f = client.get(f"/patients/{key}/documents/attachment/{d['id']}/file")
    assert f.status_code == 200 and f.content.startswith(b"%PDF")
    cd = f.headers["content-disposition"]
    assert cd == f'attachment; filename="chart-attachment-{d["id"]}.pdf"'
    assert _audit()[-1].detail == {"kind": "attachment", "id": d["id"], "file": True}
    # an image attachment never comes out of the PDF route
    key2, img = _with("tif")
    assert client.get(f"/patients/{key2}/documents/attachment/{img['id']}/file").status_code == 404


def test_rtf_attachment_shows_text(client):
    key, d = _with("rtf")
    r = client.get(f"/patients/{key}/documents/attachment/{d['id']}", headers=HTMX)
    assert "placeholder letter text" in r.text and "note-text" in r.text


def test_other_patients_attachment_is_404(client):
    key, d = _with("pdf")
    other = next(f"EMR:{p.emr_id}" for p in PATIENTS if f"EMR:{p.emr_id}" != key)
    for path in ("", "/file", "/pages/1"):
        url = f"/patients/{other}/documents/attachment/{d['id']}{path}"
        assert client.get(url, headers=HTMX).status_code == 404


def test_unsupported_format_explains(client, monkeypatch):
    key, d = _with("tif")
    from tests.fakes import repository as fake

    original = fake.documents
    monkeypatch.setattr(
        fake,
        "documents",
        lambda emr_id: [
            x | ({"format": "xls"} if x["id"] == d["id"] else {}) for x in original(emr_id)
        ],
    )
    r = client.get(f"/patients/{key}/documents/attachment/{d['id']}", headers=HTMX)
    assert "This attachment is a XLS file, which can&#39;t be shown here." in r.text


def test_live_documents_maps_attachments(monkeypatch):
    monkeypatch.setattr(emr, "scan_documents", lambda _id: [])
    monkeypatch.setattr(emr, "patient_documents", lambda _id: [])
    when = datetime(2018, 4, 5, tzinfo=UTC)
    monkeypatch.setattr(
        emr,
        "chart_attachments",
        lambda _id: [
            {
                "attachment_id": 1,
                "attached": when,
                "date_mask": 3,
                "content_type": 23,
                "subject": " Records ",
                "provider_last": None,
                "provider_first": None,
                "provider_title": None,
                "file_format": "TIF",
                "has_text": None,
            },
            {
                "attachment_id": 2,
                "attached": when,
                "date_mask": 3,
                "content_type": -184,
                "subject": None,
                "provider_last": "Example",
                "provider_first": "Doctor",
                "provider_title": "DO",
                "file_format": None,
                "has_text": 1,
            },
        ],
    )
    rows = {r["id"]: r for r in live.documents(11) if r["kind"] == "attachment"}
    assert rows[1]["type"] == "Historical summary" and rows[1]["format"] == "tif"
    assert rows[1]["title"] == "Records"
    assert rows[2]["type"] == "Patient demographic information" and rows[2]["format"] == "rtf"
    assert rows[2]["author"] == "Example, Doctor DO"


def test_image_frames():
    pages = [Image.new("L", (10, 10), color=c) for c in (0, 128, 255)]
    buf = io.BytesIO()
    pages[0].save(buf, format="TIFF", save_all=True, append_images=pages[1:])
    data = buf.getvalue()
    assert frame_count(data) == 3
    last = Image.open(io.BytesIO(to_png(data, 2)))
    assert last.getpixel((0, 0)) == 255
    with pytest.raises(DocumentFormatError):
        to_png(data, 5)
    with pytest.raises(DocumentFormatError):
        frame_count(b"not an image")
