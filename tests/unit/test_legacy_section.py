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
    r = client.get(f"/legacy/{_key(p)}")
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
    assert r.headers["HX-Push-Url"] == f"/legacy/{_key(p)}?note={note['note_id']}"


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
    assert client.get(f"/legacy/{_key(a)}", params={"note": other}).status_code == 404


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
    assert r.headers["HX-Push-Url"] == f"/legacy/{_key(p)}?year={year}"
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
    client.get(f"/legacy/{_key(p)}")
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
