"""Phase 8: DocumentStore path safety, image conversion, Documents tab + viewer (SQL stubbed)."""

import io
from datetime import date

import pytest
from PIL import Image

from app.config import get_settings
from app.documents import images
from app.documents.render import DocumentFormatError
from app.documents.store import DocumentUnavailableError, FileShareStore, get_store
from app.repositories import emr
from tests.unit.test_live_patient_list import chart_mode, real_mode  # noqa: F401

UNC = r"\\amhs-db1\hmscan"


def tiff_bytes(color: int = 0) -> bytes:
    buf = io.BytesIO()
    Image.new("L", (40, 60), color=color).save(buf, format="TIFF")
    return buf.getvalue()


@pytest.fixture
def scan_root(tmp_path):
    (tmp_path / "201922").mkdir()
    (tmp_path / "201922" / "a0567031").write_bytes(tiff_bytes())  # extension-less, like the share
    return tmp_path


# --- DocumentStore ---------------------------------------------------------------------------


def test_store_maps_unc_prefix_case_insensitively(scan_root):
    store = FileShareStore(scan_root, UNC)
    assert store.read(r"\\AMHS-DB1\HMSCAN\201922\a0567031") == tiff_bytes()


@pytest.mark.parametrize(
    "location",
    [
        r"\\amhs-db1\hmscan\..\..\windows\win.ini",
        r"\\amhs-db1\hmscan\201922\..\..\secret",
        r"\\other-server\share\201922\a0567031",
        r"C:\windows\win.ini",
        r"\\amhs-db1\hmscan",
        "",
        "\\\\amhs-db1\\hmscan\\201922\\a\x00b",
    ],
)
def test_store_refuses_paths_outside_root(scan_root, location):
    with pytest.raises(DocumentUnavailableError):
        FileShareStore(scan_root, UNC).read(location)


def test_store_missing_file(scan_root):
    with pytest.raises(DocumentUnavailableError):
        FileShareStore(scan_root, UNC).read(r"\\amhs-db1\hmscan\201922\nope")


def test_no_store_without_scan_root():
    assert get_store(get_settings().model_copy(update={"scan_root": ""})) is None


# --- images ------------------------------------------------------------------------------------


def test_tiff_to_png_and_cache():
    images.clear_cache()
    png = images.to_png(tiff_bytes(255))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    calls = []
    images.cached_png(1, lambda: calls.append(1) or tiff_bytes())
    images.cached_png(1, lambda: calls.append(1) or tiff_bytes())
    assert calls == [1]


def test_unreadable_image():
    with pytest.raises(DocumentFormatError):
        images.to_png(b"not an image")


# --- Documents tab + viewer (real mode, SQL stubbed) ----------------------------------------


def _scan(doc_id, status=4, pages=2, type_="OUTSIDE LABS"):
    return {"document_id": doc_id, "document_date": date(2018, 4, 5), "title": "Sample scan",
            "type": type_, "status_code": status, "pages": pages}  # fmt: skip


@pytest.fixture
def docs_sql(monkeypatch):
    monkeypatch.setattr(emr, "scan_documents", lambda _id: [_scan(500), _scan(501, status=10)])
    monkeypatch.setattr(emr, "patient_documents", lambda _id: [])
    monkeypatch.setattr(emr, "chart_attachments", lambda _id: [])
    monkeypatch.setattr(
        emr,
        "scan_document_pages",
        lambda _e, doc_id: (
            [
                _scan(doc_id)
                | {
                    "page_id": 9000 + n,
                    "page_number": n,
                    "file_location": UNC + r"\201922\a0567031",
                }
                for n in (1, 2)
            ]
            if doc_id == 500
            else []
        ),
    )


def test_documents_tab_without_scan_root(chart_mode, docs_sql, client, monkeypatch):
    monkeypatch.setenv("SCAN_ROOT", "")
    r = client.get("/patients/EMR:11?tab=docs")
    assert r.status_code == 200
    assert "OUTSIDE LABS" in r.text and "Scanned page images are not connected yet" in r.text
    assert "Page 1 of 2" in r.text  # viewer metadata still shown
    assert r.text.count("visit-row__title") == 1  # erroneous scan (status 10) hidden
    assert client.get("/patients/EMR:11/documents/scan/500/pages/1").status_code == 404


def test_viewer_and_page_image_with_scan_root(chart_mode, docs_sql, client, scan_root, monkeypatch):
    from app import config

    settings = config.get_settings().model_copy(update={"scan_root": str(scan_root)})
    monkeypatch.setattr("app.documents.store.get_settings", lambda: settings)
    images.clear_cache()
    r = client.get("/patients/EMR:11/documents/scan/500?docpage=2", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "/patients/EMR:11/documents/scan/500/pages/2" in r.text
    assert "doc=scan-500" in r.headers["HX-Push-Url"] and "docpage=2" in r.headers["HX-Push-Url"]
    img = client.get("/patients/EMR:11/documents/scan/500/pages/2")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert img.headers["Cache-Control"] == "no-store"
    assert client.get("/patients/EMR:11/documents/scan/500/pages/3").status_code == 404
    assert client.get("/patients/EMR:11/documents/scan/777").status_code == 404  # not this patient
