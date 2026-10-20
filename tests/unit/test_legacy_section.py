"""Separate "Pre-2010 records" section: legacy patient list, chart header, chart notes."""

import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.db.app import new_session
from app.repositories import legacy as live_legacy
from app.repositories.appdb.models import AuditLog
from tests.fakes.data import PATIENTS
from tests.fakes.legacy import NOTES, PEOPLE, TEXTS

HTMX = {"HX-Request": "true"}
SQL_DIR = Path(__file__).resolve().parents[2] / "app" / "sql" / "dmz"


def _with_notes(min_count: int = 1) -> dict:
    return next(p for p in PEOPLE if len(NOTES[p["person_key"]]) >= min_count)


def _key(p: dict) -> str:
    return f"DMZ:{p['person_key']}"


def test_sidebar_link_and_list_page(client):
    r = client.get("/legacy")
    assert r.status_code == 200
    assert 'href="/legacy"' in r.text and "Pre-2010 records" in r.text
    assert "All pre-2010 patients" in r.text
    assert f"of {len(PEOPLE)}" in r.text
    assert 'href="/legacy/DMZ:' in r.text


def test_list_search_by_name_dob_and_id(client):
    p = PEOPLE[3]
    r = client.get("/legacy/rows", params={"q": p["last_name"]}, headers=HTMX)
    expected = sum(1 for x in PEOPLE if x["last_name"] == p["last_name"])
    assert r.status_code == 200 and f"Showing {expected} of {expected}" in r.text
    assert r.headers["HX-Push-Url"].startswith("/legacy?q=")
    r = client.get("/legacy/rows", params={"dob": p["dob"].strftime("%m/%d/%Y")}, headers=HTMX)
    assert _key(p) in r.text
    r = client.get("/legacy/rows", params={"legacy_id": p["legacy_id"]}, headers=HTMX)
    assert _key(p) in r.text and "Showing 1 of 1" in r.text


def test_list_search_validation(client):
    r = client.get("/legacy/rows", params={"dob": "13/45/20"}, headers=HTMX)
    assert "Enter the date of birth as MM/DD/YYYY." in r.text
    r = client.get("/legacy/rows", params={"legacy_id": "a b"}, headers=HTMX)
    assert "Legacy ID can contain only letters" in r.text


def test_legacy_patients_never_appear_in_current_patient_list(client):
    legacy_only = "Mockridge"
    assert all(p.last_name != legacy_only for p in PATIENTS)
    r = client.get("/patients/rows", params={"q": legacy_only}, headers=HTMX)
    assert "No matches" in r.text and "DMZ:" not in r.text
    assert "DMZ:" not in client.get("/patients").text


def test_chart_header_and_first_note_open(client):
    p = _with_notes(3)
    r = client.get(f"/legacy/{_key(p)}", params={"tab": "notes"})
    assert r.status_code == 200
    assert p["last_name"] in r.text and p["legacy_id"] in r.text
    assert "Chart notes" in r.text and "badge--legacy" in r.text
    newest = NOTES[p["person_key"]][0]
    assert "note-row--selected" in r.text
    assert f"/legacy/{_key(p)}/notes/{newest['note_id']}" in r.text
    # Separate section: no export / current-chart tabs on the legacy chart.
    assert "Export records" not in r.text and "/patients/DMZ" not in r.text


def test_note_text_is_converted_from_rtf(client):
    p = _with_notes(3)
    note = next(n for n in NOTES[p["person_key"]] if n["note_id"] in TEXTS)
    r = client.get(f"/legacy/{_key(p)}/notes/{note['note_id']}", headers=HTMX)
    assert r.status_code == 200
    body = re.search(r'<div class="legacy-note-text">(.*?)</div>', r.text, re.S).group(1)
    assert "Assessment:" in body and "Condition stable." in body
    assert "\\" not in body and "Sample header" not in body and "DATE" not in body
    assert "01/01/2005" in body  # field result kept, field instruction dropped
    assert r.headers["HX-Push-Url"] == f"/legacy/{_key(p)}?tab=notes&note={note['note_id']}"


def test_note_without_text_shows_empty_state(client):
    p, note = next(
        (p, n) for p in PEOPLE for n in NOTES[p["person_key"]] if n["note_id"] not in TEXTS
    )
    r = client.get(f"/legacy/{_key(p)}/notes/{note['note_id']}", headers=HTMX)
    assert r.status_code == 200 and "not available in the pre-2010 archive" in r.text
    assert "Print note" not in r.text


def test_note_of_another_patient_is_404(client):
    a, b = [p for p in PEOPLE if NOTES[p["person_key"]]][:2]
    other = NOTES[b["person_key"]][0]["note_id"]
    assert client.get(f"/legacy/{_key(a)}/notes/{other}", headers=HTMX).status_code == 404
    params = {"tab": "notes", "note": other}
    assert client.get(f"/legacy/{_key(a)}", params=params).status_code == 404


def test_bad_and_unknown_keys_are_404(client):
    assert client.get("/legacy/EMR:1").status_code == 404
    assert client.get("/legacy/DMZ:abc").status_code == 404
    assert client.get("/legacy/DMZ:1").status_code == 404


def test_patient_without_notes(client):
    p = next(p for p in PEOPLE if not NOTES[p["person_key"]])
    r = client.get(f"/legacy/{_key(p)}")
    assert r.status_code == 200 and "No chart notes recorded" in r.text


def test_year_filter_and_paging(client):
    p = max(PEOPLE, key=lambda x: len(NOTES[x["person_key"]]))
    rows = NOTES[p["person_key"]]
    year = str(rows[0]["service_date"].year)
    r = client.get(f"/legacy/{_key(p)}/notes", params={"year": year}, headers=HTMX)
    in_year = sum(1 for n in rows if str(n["service_date"].year) == year)
    assert r.status_code == 200 and f"in {year}" in r.text
    assert r.text.count("data-list-row") == min(in_year, 25)
    assert r.headers["HX-Push-Url"] == f"/legacy/{_key(p)}?tab=notes&year={year}"
    r = client.get(f"/legacy/{_key(p)}/notes", params={"year": "1890"}, headers=HTMX)
    assert r.text.count("data-list-row") == min(len(rows), 25)  # unknown year → all


def test_print_page(client):
    p = _with_notes(3)
    note = next(n for n in NOTES[p["person_key"]] if n["note_id"] in TEXTS)
    r = client.get(f"/legacy/{_key(p)}/notes/{note['note_id']}/print")
    assert r.status_code == 200 and "print-auto.js" in r.text
    assert "From the pre-2010 legacy chart" in r.text and 'class="sidebar"' not in r.text


def test_views_are_audited_without_phi(client):
    p = _with_notes(3)
    client.get(f"/legacy/{_key(p)}", params={"tab": "notes"})
    client.get("/legacy/rows", params={"q": p["last_name"]}, headers=HTMX)
    with new_session() as db:
        rows = db.scalars(select(AuditLog)).all()
    legacy = [a for a in rows if (a.detail or {}).get("section") == "legacy"]
    actions = {a.action for a in legacy}
    assert {"view_patient", "view_note", "search"} <= actions
    assert all(a.patient_key in (None, _key(p)) for a in legacy)
    assert all(p["last_name"] not in str(a.detail) for a in legacy)


def test_section_hidden_when_disabled(client, monkeypatch):
    import app.routers.legacy as router
    import app.templating as templating

    monkeypatch.setattr(router, "legacy_enabled", lambda: False)
    monkeypatch.setitem(templating.templates.env.globals, "legacy_enabled", lambda: False)
    assert client.get("/legacy").status_code == 404
    assert client.get(f"/legacy/{_key(PEOPLE[0])}").status_code == 404
    assert 'href="/legacy"' not in client.get("/patients").text


def test_live_note_text_joins_rows_and_notes_sort_newest_first(monkeypatch):
    rtf = "{\\rtf1{\\fonttbl{\\f0 Arial;}}\\pard Part %d\\par }"
    rows = [{"service_date": datetime(2005, 1, 1), "note_text": rtf % n} for n in (1, 2)]
    monkeypatch.setattr(live_legacy.dmz, "legacy_note_text", lambda k, n: rows)
    assert live_legacy.note_text(1, 2)["text"] == "Part 1\n\nPart 2"
    headers = [
        {"note_id": 1, "service_date": datetime(2003, 5, 1)},
        {"note_id": 2, "service_date": None},
        {"note_id": 3, "service_date": datetime(2009, 5, 1)},
    ]
    monkeypatch.setattr(live_legacy.dmz, "legacy_notes", lambda k: [dict(h) for h in headers])
    assert [n["note_id"] for n in live_legacy.notes(1)] == [3, 1, 2]
    monkeypatch.setattr(live_legacy.dmz, "legacy_note_text", lambda k, n: [])
    assert live_legacy.note_text(1, 99) is None


def test_legacy_sql_never_selects_ssn():
    for path in SQL_DIR.glob("legacy_*.sql"):
        sql = path.read_text().lower()
        assert "ssno" not in sql.replace("ssno is never selected", "") and "select *" not in sql


def _with_history() -> dict:
    return next(p for p in PEOPLE if (p["person_key"] - 5_000) % 4 != 3)


def test_tab_bar_and_unknown_tab(client):
    p = _with_history()
    r = client.get(f"/legacy/{_key(p)}")
    assert 'id="tab-notes"' in r.text and 'id="tab-problems"' in r.text
    assert f'href="/legacy/{_key(p)}?tab=problems"' in r.text
    assert client.get(f"/legacy/{_key(p)}", params={"tab": "visits"}).status_code == 404
    assert client.get(f"/legacy/{_key(p)}/tab/nope", headers=HTMX).status_code == 404


def test_problems_tab(client):
    p = _with_history()
    r = client.get(f"/legacy/{_key(p)}", params={"tab": "problems"})
    assert r.status_code == 200 and "Pre-2010 problems &amp; allergies" in r.text
    assert "DIABETES MELLITUS TYPE II" in r.text and "250.00" in r.text
    assert "Active" in r.text and "Inactive" in r.text
    assert "ALLERGIC RHINITIS NOS" not in r.text  # entered in error: hidden by default
    assert "Show entered-in-error (2)" in r.text
    assert "Hives, Rash" in r.text and "Drug" in r.text and "Severe" in r.text
    assert "LATEX" not in r.text and "Not Available" not in r.text


def test_problems_tab_show_voided_and_htmx(client):
    p = _with_history()
    r = client.get(f"/legacy/{_key(p)}/tab/problems", params={"voided": "1"}, headers=HTMX)
    assert r.status_code == 200 and 'id="chart-tabs"' in r.text
    assert "ALLERGIC RHINITIS NOS" in r.text and "LATEX" in r.text
    assert "badge--voided" in r.text and "Hide entered-in-error" in r.text
    assert r.headers["HX-Push-Url"] == f"/legacy/{_key(p)}?tab=problems&voided=1"


def test_problems_tab_empty(client):
    p = next(p for p in PEOPLE if (p["person_key"] - 5_000) % 4 == 3)
    r = client.get(f"/legacy/{_key(p)}", params={"tab": "problems"})
    assert "No problems recorded in the pre-2010 chart." in r.text
    assert "No allergies recorded in the pre-2010 chart." in r.text
    assert "entered-in-error" not in r.text


def test_problem_status_unknown_code():
    from app.lookups.legacy_codes import legacy_codes

    assert legacy_codes().problem_status_label(12) == "Active"
    assert legacy_codes().problem_status_label(77) == "Unknown (code 77)"


def test_live_allergies_attach_reactions(monkeypatch):
    rows = [
        {"allergy_id": 1, "noted_date": datetime(2004, 1, 1)},
        {"allergy_id": 2, "noted_date": datetime(2006, 1, 1)},
    ]
    reactions = [{"allergy_id": 1, "reaction": "Hives"}, {"allergy_id": 1, "reaction": "Rash"}]
    monkeypatch.setattr(live_legacy.dmz, "legacy_allergies", lambda k: [dict(r) for r in rows])
    monkeypatch.setattr(live_legacy.dmz, "legacy_allergy_reactions", lambda k: reactions)
    out = live_legacy.allergies(1)
    assert [r["allergy_id"] for r in out] == [2, 1]
    assert out[1]["reactions"] == ["Hives", "Rash"] and out[0]["reactions"] == []


def test_meds_tab_groups_entries(client):
    p = _with_history()
    r = client.get(f"/legacy/{_key(p)}", params={"tab": "meds"})
    assert r.status_code == 200 and 'id="tab-meds"' in r.text
    assert "Active at last pre-2010 update" in r.text and "Discontinued" in r.text
    assert r.text.count("METFORMIN HCL TABLET 500 MG") == 1  # two entries, one medication
    assert "History (2 entries)" in r.text and "New Prescription" in r.text
    assert "Continued" in r.text and "Twice Daily" in r.text and "60 TAB" in r.text
    assert "For: DIABETES MELLITUS TYPE II" in r.text
    assert "AMOXICILLIN" not in r.text and "Show entered-in-error (1)" in r.text


def test_meds_tab_voided_and_empty(client):
    p = _with_history()
    r = client.get(f"/legacy/{_key(p)}/tab/meds", params={"voided": "1"}, headers=HTMX)
    assert "AMOXICILLIN" in r.text and "Entered in error" in r.text and "badge--voided" in r.text
    assert r.headers["HX-Push-Url"] == f"/legacy/{_key(p)}?tab=meds&voided=1"
    empty = next(p for p in PEOPLE if (p["person_key"] - 5_000) % 4 == 3)
    r = client.get(f"/legacy/{_key(empty)}", params={"tab": "meds"})
    assert "No medications recorded in the pre-2010 chart." in r.text


def test_med_status_groups():
    from app.services.legacy import _medication

    base = {"med_id": 1, "mdrug_name": "X  TAB", "date_of_service": datetime(2005, 1, 1)}
    active, kind = _medication([{**base, "entry_id": 1, "status_group": 1, "status": "Continued"}])
    assert kind == "active" and active.name == "X TAB"
    _, kind = _medication([{**base, "entry_id": 1, "status_group": 1,
                            "stop_date": datetime(2006, 1, 1)}])  # fmt: skip
    assert kind == "past"
    _, kind = _medication([{**base, "entry_id": 1, "status_group": 6}])
    assert kind == "voided"
    med, kind = _medication([{**base, "entry_id": 1, "status_group": None, "status_key": 55}])
    assert kind == "past" and med.status == "Unknown (code 55)"


def test_labs_tab_flags_filters_and_note_link(client):
    p = _with_history()
    r = client.get(f"/legacy/{_key(p)}", params={"tab": "labs"})
    assert r.status_code == 200 and 'id="tab-labs"' in r.text
    assert "TSH" in r.text and "0.40 – 4.00" in r.text
    assert "High" in r.text and "Low" in r.text  # A1C 7.8 > 5.6, potassium 3.1 < 3.5
    assert "GENERIC-PHONE" not in r.text and "(555)000-0000" not in r.text  # skipped fields
    assert "VS-PULSE" not in r.text  # vitals are not labs
    assert "Showing 6 of 6" in r.text and "Fasting" in r.text
    first_note = NOTES[p["person_key"]][0]["note_id"]
    assert f"?note={first_note}" in r.text
    r = client.get(f"/legacy/{_key(p)}/tab/labs", params={"test": "TSH"}, headers=HTMX)
    assert "Showing 2 of 2" in r.text and "A1C</td>" not in r.text
    assert r.headers["HX-Push-Url"] == f"/legacy/{_key(p)}?tab=labs&test=TSH"
    r = client.get(f"/legacy/{_key(p)}/tab/labs", params={"test": "NOPE"}, headers=HTMX)
    assert "Showing 6 of 6" in r.text  # unknown test → all


def test_vitals_tab(client):
    p = _with_history()
    r = client.get(f"/legacy/{_key(p)}", params={"tab": "vitals"})
    assert r.status_code == 200 and "Showing 3 of 3" in r.text
    assert "128/82" in r.text and "180lb" in r.text and "5ft10in" in r.text and "25.8" in r.text
    assert "10:30 AM" in r.text and "TSH" not in r.text
    empty = next(p for p in PEOPLE if (p["person_key"] - 5_000) % 4 == 3)
    r = client.get(f"/legacy/{_key(empty)}", params={"tab": "vitals"})
    assert "No vitals recorded in the pre-2010 chart." in r.text
    r = client.get(f"/legacy/{_key(empty)}", params={"tab": "labs"})
    assert "No lab results recorded in the pre-2010 chart." in r.text


def test_note_link_opens_notes_tab(client):
    p = _with_history()
    note = NOTES[p["person_key"]][-1]["note_id"]  # oldest: not on the default selection
    r = client.get(f"/legacy/{_key(p)}/tab/notes", params={"note": note}, headers=HTMX)
    assert r.status_code == 200 and f"/legacy/{_key(p)}/notes/{note}/print" in r.text


def test_lab_flag_and_range():
    from app.services.legacy import _lab_flag, _range

    assert _lab_flag("7.8", "4.0", "5.6") == "H" and _lab_flag("3.1", "3.5", "5.1") == "L"
    assert _lab_flag("<0.01", "0.4", "4") is None and _lab_flag("5", None, None) is None
    assert _range("1", "2") == "1 – 2" and _range(None, "200") == "≤ 200"
    assert _range("", "") == "—"


def _multipage_tiff(pages: int) -> bytes:
    import io

    from PIL import Image

    frames = [Image.new("L", (40, 60), color=40 * n) for n in range(pages)]
    buf = io.BytesIO()
    frames[0].save(buf, format="TIFF", save_all=True, append_images=frames[1:])
    return buf.getvalue()


def _legacy_store(monkeypatch, tmp_path):
    from app import config
    from tests.fakes.legacy import documents

    (tmp_path / "archive").mkdir()
    for p in PEOPLE:
        for d in documents(p["person_key"]):
            name = f"{d['document_id']}.{d['file_ext']}"
            (tmp_path / "archive" / name).write_bytes(_multipage_tiff(d["pages"]))
    settings = config.get_settings().model_copy(update={"legacy_scan_root": str(tmp_path)})
    monkeypatch.setattr("app.documents.store.get_settings", lambda: settings)


def test_docs_tab_lists_metadata_with_banner(client):
    p = _with_history()
    r = client.get(f"/legacy/{_key(p)}", params={"tab": "docs"})
    assert r.status_code == 200 and 'id="tab-docs"' in r.text
    assert "4 documents" in r.text and "Outside labs" in r.text and "Insurance card" in r.text
    assert "old image server" in r.text and "TIFF image" in r.text and "JPEG image" in r.text
    assert "scan-page__img" not in r.text
    r = client.get(f"/legacy/{_key(p)}/tab/docs", params={"type": "Hipaa"}, headers=HTMX)
    assert "1 document" in r.text and r.headers["HX-Push-Url"].endswith("tab=docs&type=Hipaa")


def test_docs_tab_empty(client):
    p = next(p for p in PEOPLE if (p["person_key"] - 5_000) % 4 == 3)
    r = client.get(f"/legacy/{_key(p)}", params={"tab": "docs"})
    assert "No scanned documents in the pre-2010 chart." in r.text
    assert "old image server" not in r.text


def test_doc_pages_render_when_share_copy_configured(client, monkeypatch, tmp_path):
    _legacy_store(monkeypatch, tmp_path)
    p = _with_history()
    doc = p["person_key"] * 10 + 2  # HIPAA, 3 pages
    r = client.get(f"/legacy/{_key(p)}/documents/{doc}", params={"docpage": "2"}, headers=HTMX)
    assert r.status_code == 200 and "Page 2 of 3" in r.text
    assert f"/legacy/{_key(p)}/documents/{doc}/pages/2" in r.text
    assert r.headers["HX-Push-Url"] == f"/legacy/{_key(p)}?tab=docs&doc={doc}&docpage=2"
    img = client.get(f"/legacy/{_key(p)}/documents/{doc}/pages/2")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert img.content.startswith(b"\x89PNG")
    assert client.get(f"/legacy/{_key(p)}/documents/{doc}/pages/4").status_code == 404
    r = client.get(f"/legacy/{_key(p)}", params={"tab": "docs"})
    assert "scan-page__img" in r.text and "old image server" not in r.text


def test_doc_of_another_patient_is_404(client, monkeypatch, tmp_path):
    _legacy_store(monkeypatch, tmp_path)
    a, b = [p for p in PEOPLE if (p["person_key"] - 5_000) % 4 != 3][:2]
    other = b["person_key"] * 10
    assert client.get(f"/legacy/{_key(a)}/documents/{other}", headers=HTMX).status_code == 404
    assert client.get(f"/legacy/{_key(a)}/documents/{other}/pages/1").status_code == 404
    assert client.get(f"/legacy/{_key(a)}", params={"tab": "docs", "doc": other}).status_code == 404


def test_doc_page_404_without_store(client):
    p = _with_history()
    doc = p["person_key"] * 10
    assert client.get(f"/legacy/{_key(p)}/documents/{doc}/pages/1").status_code == 404


def test_overview_is_default_tab(client):
    p = _with_history()
    r = client.get(f"/legacy/{_key(p)}")
    assert r.status_code == 200 and 'id="tab-overview"' in r.text
    assert 'id="tab-overview" class="tab tab--active"' in r.text
    assert "Active problems" in r.text and "DIABETES MELLITUS TYPE II" in r.text
    assert "ALLERGIC RHINITIS NOS" not in r.text  # entered in error
    assert "HYPERLIPIDEMIA" not in r.text  # inactive
    assert "PENICILLIN" in r.text and "Hives, Rash" in r.text and "PEANUTS" not in r.text
    assert "METFORMIN HCL TABLET 500 MG" in r.text and "LISINOPRIL" not in r.text
    assert "Last chart note" in r.text and "All chart notes" in r.text
    assert "In this pre-2010 chart" in r.text and f'href="/legacy/{_key(p)}?tab=labs"' in r.text
    assert "Pre-2010 overview" in r.text  # page title


def test_overview_empty_patient(client):
    p = next(p for p in PEOPLE if not NOTES[p["person_key"]])
    r = client.get(f"/legacy/{_key(p)}")
    assert r.status_code == 200 and "No chart notes recorded." in r.text
