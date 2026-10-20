"""Clinical documents that embed a picture as base64 text (e.g. scanned reports)."""

import base64
import io
import zipfile

import pytest
from PIL import Image

from app.documents.render import embed_images, embedded_images, render_document
from tests.fakes.data import PATIENTS

HTMX = {"HX-Request": "true"}
P = PATIENTS[0]
KEY = f"EMR:{P.emr_id}"
REPORT_ID = 990000 + P.emr_id


def _jpeg_b64() -> str:
    out = io.BytesIO()
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(out, format="JPEG")
    return base64.b64encode(out.getvalue()).decode()


def _package(content: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CONTENT", content)
    return buf.getvalue()


def test_base64_picture_becomes_a_placeholder_not_text():
    data = _package(f'<table><tr><td><img src="SCANDOC_9">{_jpeg_b64()}</td></tr></table>')
    html = render_document(data, 77)
    assert '<img class="doc-embedded-img" src="embedded:77/0"' in html
    assert "SCANDOC" not in html and _jpeg_b64()[:40] not in html
    assert "[embedded image]" in render_document(data)  # without a document id: no picture
    mime, raw = embedded_images(data)[0]
    assert mime == "image/jpeg" and raw.startswith(b"\xff\xd8\xff")


def test_long_non_image_base64_is_left_alone():
    junk = base64.b64encode(b"not an image " * 80).decode()  # decodes, but no image signature
    html = render_document(_package(f"<p>{junk}</p>"), 5)
    assert "doc-embedded-img" not in html and junk[:40] in html


def test_embed_images_rewrites_only_our_placeholders():
    html = '<img class="doc-embedded-img" src="embedded:12/3" alt="x">'
    assert 'src="/patients/EMR:7/documents/document/12/images/3"' in embed_images(html, "EMR:7")
    assert 'src="docimage:12/3"' in embed_images(html, "__pdf__")
    assert embed_images(html, 'EMR:7"><script>').count("<script>") == 0
    assert embed_images(None, "EMR:7") == ""


def test_note_shows_the_picture(client):
    r = client.get(f"/patients/{KEY}/notes/document-{REPORT_ID}", headers=HTMX)
    assert r.status_code == 200
    assert f'src="/patients/{KEY}/documents/document/{REPORT_ID}/images/0"' in r.text
    assert "/9j/" not in r.text  # no base64 on screen
    img = client.get(f"/patients/{KEY}/documents/document/{REPORT_ID}/images/0")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize("path", ["images/1", "images/0"])
def test_image_route_guards(client, path):
    other = f"EMR:{PATIENTS[1].emr_id}"
    if path == "images/1":  # index out of range
        url = f"/patients/{KEY}/documents/document/{REPORT_ID}/{path}"
    else:  # another patient's chart
        url = f"/patients/{other}/documents/document/{REPORT_ID}/{path}"
    assert client.get(url).status_code == 404


def test_pdf_renderer_loads_embedded_pictures():
    pytest.importorskip("weasyprint", exc_type=ImportError)
    from app.services.export import render_pdf

    calls = []

    def loader(doc_id, index):
        calls.append((doc_id, index))
        return "image/jpeg", base64.b64decode(_jpeg_b64())

    html = '<html><body><img src="docimage:12/0" alt="x"></body></html>'
    try:
        pdf, pages = render_pdf(html, {}, loader)
    except (OSError, ImportError):
        pytest.skip("WeasyPrint/Pango not installed")
    assert pdf.startswith(b"%PDF") and pages == 1 and calls == [(12, 0)]
