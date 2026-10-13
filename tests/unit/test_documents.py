"""Phase 6: document packages, sanitising, RTF, and real-data Visits / Notes (SQL stubbed)."""

import io
import zipfile
from datetime import UTC, datetime

import pytest

from app.documents.render import DocumentFormatError, render_document, rtf_to_text
from app.repositories import emr, live
from tests.unit.test_live_patient_list import chart_mode, real_mode  # noqa: F401


def make_package(content: str, header: str = "", footer: str = "") -> bytes:
    buf = io.BytesIO()
    parts = (
        ("INFO", "VERSION=1"),
        ("HEADER", header),
        ("CONTENT", content),
        ("FOOTER", footer),
        ("LAYOUT", "COLUMNS=1"),
        ("CSS", "td { x: y }"),
    )
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in parts:
            z.writestr(name, text.encode("utf-8"))
    return buf.getvalue()


def test_package_renders_header_content_footer_in_order():
    html = render_document(
        make_package("<p>Body</p>", "<table><tr><td>Head</td></tr></table>", "<p>Foot</p>")
    )
    assert html.index("Head") < html.index("Body") < html.index("Foot")
    assert "td { x" not in html and "VERSION" not in html  # CSS / INFO parts not shown


@pytest.mark.parametrize(
    ("dirty", "forbidden"),
    [
        ('<p onclick="alert(1)">x</p><script>alert(2)</script>', ["onclick", "<script", "alert"]),
        ('<p style="color:red">x</p><style>p{}</style>', ["style"]),
        ('<a href="https://evil.example/x">link</a>', ["evil.example", "href"]),
        ('<img src="https://tracker.example/p.png">', ["<img", "tracker"]),
        ('<a href="javascript:alert(1)">x</a>', ["javascript"]),
    ],
)
def test_sanitising_removes_scripts_styles_urls_images(dirty, forbidden):
    html = render_document(make_package(dirty))
    for bad in forbidden:
        assert bad not in html


def test_raw_html_and_cp1252_documents():
    assert "Café" in render_document("<p>Café</p>".encode("cp1252"))


def test_unusable_documents_raise():
    for data in (b"", b"plain words, no markup", b"PK\x03\x04broken"):
        with pytest.raises(DocumentFormatError):
            render_document(data)


def test_rtf_to_text():
    rtf = (
        "{\\rtf1\\ansi{\\fonttbl{\\f0 Arial;}}{\\colortbl;\\red0\\green0\\blue0;}"
        "\\pard Line one\\par Caf\\'e9 \\tab tabbed\\par{\\*\\generator X;}Done\\u8212?}"
    )
    assert rtf_to_text(rtf) == "Line one\nCafé \ttabbed\nDone—?"


# --- live visits / notes with SQL stubbed --------------------------------------------------------


def _visit_row(contact_id, visit_type, start):
    return {
        "contact_id": contact_id,
        "encounter_id": contact_id + 1000,
        "start": start,
        "visit_type_code": visit_type,
        "signed": 1,
        "diagnoses": "Sample diagnosis",
        "provider_last": "Example",
        "provider_first": "Doctor",
        "provider_title": "MD",
        "location": "Main Clinic",
    }


def _doc(doc_id, title):
    return {
        "document_id": doc_id,
        "title": title,
        "author": "Dr X",
        "created": datetime(2019, 5, 1, tzinfo=UTC),
    }


@pytest.fixture
def visit_sql(monkeypatch):
    rows = [
        _visit_row(1, 6, datetime(2019, 5, 1, tzinfo=UTC)),
        _visit_row(2, 98, datetime(2026, 1, 1, tzinfo=UTC)),
    ]
    monkeypatch.setattr(emr, "visits", lambda _id: rows)
    monkeypatch.setattr(
        emr,
        "visits_of_types",
        lambda _id, codes: [r for r in rows if r["visit_type_code"] in codes],
    )
    monkeypatch.setattr(
        emr, "visit_one", lambda _e, c: next((r for r in rows if r["contact_id"] == c), None)
    )
    monkeypatch.setattr(
        emr,
        "visit_assessment",
        lambda _enc: [
            {"sort_order": 2, "title": "Second dx", "code": "B2", "code_system": "ICD10"},
            {"sort_order": 1, "title": "First dx", "code": "A1", "code_system": "ICD10"},
        ],
    )
    plan_item = {"lab_title": None, "procedure_title": None, "medication_title": None}
    monkeypatch.setattr(
        emr,
        "visit_plan",
        lambda _enc: [
            plan_item | {"sort_order": 1, "source": "LABORATORY", "lab_title": "Lipid panel"},
            plan_item | {"sort_order": 2, "source": "FL_TEMPLATES"},
        ],
    )
    monkeypatch.setattr(emr, "visit_addenda", lambda _enc: [])
    monkeypatch.setattr(
        emr,
        "visit_text_notes",
        lambda _c: [{"note_id": 5, "note_type": 1, "note_text": "Short text note"}],
    )
    monkeypatch.setattr(
        emr,
        "visit_documents",
        lambda _e, _enc: [
            _doc(70, "* History & Physical Note (v8.3)"),
            _doc(71, "Lab Results by Date Range"),
        ],
    )
    monkeypatch.setattr(
        emr,
        "document_content",
        lambda _e, doc_id: (
            _doc(doc_id, "t")
            | {"content": make_package("<p>Assessment and plan text</p><script>x()</script>")}
        ),
    )
    monkeypatch.setattr(emr, "vitals", lambda _id: [])
    monkeypatch.setattr(emr, "visit_vitals", lambda _id, _contact: [])
    return rows


def test_live_visit_detail(visit_sql):
    v = live.visit(11, 1)
    assert v["visit_type"] == "Office Visit" and v["is_office_visit"]
    assert v["assessment"] == [("First dx", "A1"), ("Second dx", "B2")]
    assert v["plan"] == ["Lab order: Lipid panel"]
    assert [d["id"] for d in v["note_documents"]] == [70]
    assert "Assessment and plan text" in v["note_documents"][0]["html"]
    assert "script" not in v["note_documents"][0]["html"]
    assert [d["id"] for d in v["other_documents"]] == [71]
    assert v["note_text"] == "Short text note"
    assert live.visit(11, 999) is None  # not this patient's contact


def test_visits_tab_real_mode(visit_sql, chart_mode, client):
    r = client.get("/patients/EMR:11?tab=visits")
    assert r.status_code == 200
    assert "Office Visit" in r.text and "Review" not in r.text  # default: real visits only
    assert "Assessment and plan text" in r.text and "Lab Results by Date Range" in r.text
    r = client.get("/patients/EMR:11?tab=visits&filter=all")
    assert "Review" in r.text


def test_notes_tab_and_note_panel_real_mode(chart_mode, client, monkeypatch):
    monkeypatch.setattr(
        emr, "patient_documents", lambda _id: [_doc(70, "H&P Note") | {"status_code": 1}]
    )
    monkeypatch.setattr(
        emr,
        "transcriptions",
        lambda _id: [
            {
                "transcription_id": 9,
                "dictated": datetime(2015, 2, 3),
                "transcribed": None,
                "encounter_date": None,
                "provider_last": "Example",
                "provider_first": "Doctor",
                "provider_title": None,
            }
        ],
    )
    monkeypatch.setattr(
        emr,
        "document_content",
        lambda _e, doc_id: _doc(doc_id, "H&P Note") | {"content": make_package("<p>Note body</p>")},
    )
    monkeypatch.setattr(
        emr,
        "transcription_text",
        lambda _e, tid: {
            "transcription_id": tid,
            "dictated": datetime(2015, 2, 3),
            "encounter_date": None,
            "provider_last": "Example",
            "provider_first": "Doctor",
            "rtf": "{\\rtf1 Dictated words\\par}",
        },
    )
    r = client.get("/patients/EMR:11?tab=notes")
    assert r.status_code == 200 and "H&amp;P Note" in r.text and "Dictation" in r.text
    assert "Note body" in r.text  # newest note opened by default
    r = client.get("/patients/EMR:11/notes/transcription/9", headers={"HX-Request": "true"})
    assert r.status_code == 200 and "Dictated words" in r.text
    assert "note=transcription-9" in r.headers["HX-Push-Url"]
    assert client.get("/patients/EMR:11/notes/bogus/9").status_code == 404


def test_office_visits_query_matches_filtering_all_entries(visit_sql):
    """Perf #3: asking the database for real visits gives exactly the filtered full list."""
    every = live.visits(11)
    office = live.visits(11, office_only=True)
    assert office == [v for v in every if v["is_office_visit"]]
    assert [v["visit_type"] for v in office] == ["Office Visit"]


def test_office_visits_fall_back_when_unknown_types_count_as_visits(visit_sql, monkeypatch):
    """If config makes unknown types count as visits, the DB filter can't be used: load all."""
    from app.lookups import get_lookups

    monkeypatch.setattr(get_lookups(), "visit_default_office", True)
    called = []
    monkeypatch.setattr(emr, "visits_of_types", lambda *_a: called.append(1) or [])
    live.visits(11, office_only=True)
    assert called == []


def _reading(vital_id, hour, systolic):
    return {
        "vital_id": vital_id,
        "contact_id": 1,
        "taken": datetime(2019, 5, 1, hour, tzinfo=UTC),
        "systolic": systolic,
        "diastolic": 80,
        "pulse": 70,
        "temperature": None,
        "temperature_unit": None,
        "weight": None,
        "weight_unit": None,
        "height": None,
        "height_unit": None,
        "spo2": None,
        "pain": None,
    }


def test_visit_with_several_vitals_readings_shows_all(visit_sql, chart_mode, client, monkeypatch):
    """Perf #4: one visit's readings only — and every reading of that visit, in time order."""
    monkeypatch.setattr(
        emr, "visit_vitals", lambda _id, _c: [_reading(9, 15, 150), _reading(8, 14, 140)]
    )
    calls = []
    monkeypatch.setattr(emr, "vitals", lambda _id: calls.append(1) or [])
    r = client.get("/patients/EMR:11/visits/EMR/1", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert calls == []  # the patient's full vitals list is no longer loaded for one visit
    assert r.text.index("140/80") < r.text.index("150/80")  # earliest first
    assert "Also recorded at" in r.text
