"""Notes tab: chart messages (MESSAGE_SAVED) and patient-portal messages."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.db.app import new_session
from app.lookups.note_categories import note_categories
from app.repositories import emr, live
from app.repositories.appdb.models import AuditLog
from tests.conftest import page_csrf
from tests.fakes.data import PATIENTS

FIRST = f"EMR:{PATIENTS[0].emr_id}"
HTMX = {"HX-Request": "true"}


def _patient_with(kind: str, attachment: bool = False):
    for p in PATIENTS:
        for n in p.clinical_notes:
            if n["kind"] == kind and (not attachment or n.get("attachment")):
                return p, n
    raise AssertionError(f"fake data has no {kind}")


def _ref(n: dict) -> str:
    return f"{n['kind']}-{n['id']}"


def test_messages_are_their_own_category():
    cats = note_categories()
    assert cats.classify("Lab results question", set(), kind="message") == "message"
    assert cats.classify("Anything", set(), kind="portal") == "message"
    assert cats.label("message") == "Messages" and cats.badge("message") == "Message"


def test_messages_tile_and_list(client):
    p, _ = _patient_with("message")
    r = client.get(f"/patients/EMR:{p.emr_id}", params={"tab": "notes", "cat": "message"})
    assert r.status_code == 200 and "Messages" in r.text
    assert "badge-type--message" in r.text
    assert 'value="message"' in r.text  # the tile


def test_message_detail_fields_and_visit_link(client):
    p, m = _patient_with("message")
    r = client.get(f"/patients/EMR:{p.emr_id}/notes/{_ref(m)}", headers=HTMX)
    assert r.status_code == 200
    for label in ("Type", "From", "To", "Call-back phone", "Subject", "Message"):
        assert f">{label}<" in r.text
    assert "Placeholder message text" in r.text
    if m["encounter_id"]:
        assert "Open in Visits" in r.text
    r = client.get(
        f"/patients/EMR:{p.emr_id}/notes/{_ref(m)}", params={"view": "original"}, headers=HTMX
    )
    assert "note-original" in r.text


def test_portal_attachment_download(client):
    p, w = _patient_with("portal", attachment=True)
    key = f"EMR:{p.emr_id}"
    r = client.get(f"/patients/{key}/notes/{_ref(w)}", headers=HTMX)
    assert "Attachment (PDF)" in r.text
    r = client.get(f"/patients/{key}/notes/{_ref(w)}/attachment")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert (
        r.headers["content-disposition"] == f'attachment; filename="portal-message-{w["id"]}.pdf"'
    )
    with new_session() as db:
        row = db.scalars(select(AuditLog).where(AuditLog.action == "view_document")).all()[-1]
    assert row.detail == {"kind": "portal_attachment", "note": _ref(w)}


def test_attachment_only_for_this_patients_portal_pdfs(client, monkeypatch):
    p, w = _patient_with("portal", attachment=True)
    other = next(q for q in PATIENTS if q.emr_id != p.emr_id and q.clinical_notes)
    assert client.get(f"/patients/EMR:{other.emr_id}/notes/{_ref(w)}/attachment").status_code == 404
    doc = next(n for n in p.clinical_notes if n["kind"] == "document")
    assert client.get(f"/patients/EMR:{p.emr_id}/notes/{_ref(doc)}/attachment").status_code == 404
    from tests.fakes import repository as fake

    monkeypatch.setattr(
        fake, "portal_attachment", lambda _e, _i: {"content": b"<html>not a pdf</html>"}
    )
    assert client.get(f"/patients/EMR:{p.emr_id}/notes/{_ref(w)}/attachment").status_code == 404


def test_message_add_to_export(client):
    p, m = _patient_with("message")
    key = f"EMR:{p.emr_id}"
    token = page_csrf(client, f"/patients/{key}")
    r = client.post(
        f"/patients/{key}/export-selection/notes/{_ref(m)}", headers={**HTMX, "X-CSRF-Token": token}
    )
    assert r.status_code == 200 and "Added ✓ · Remove" in r.text
    r = client.get(f"/patients/{key}/export", headers=HTMX)
    assert f'name="note_ids" value="{_ref(m)}" checked' in r.text


# --- real-mode repository (SQL stubbed) ----------------------------------------------------------


def test_live_note_index_and_message_detail(monkeypatch):
    sent = datetime(2019, 5, 1, 10, tzinfo=UTC)
    monkeypatch.setattr(emr, "notes_list_docs", lambda _id: [])
    monkeypatch.setattr(emr, "notes_doc_sources", lambda _id, _s: [])
    monkeypatch.setattr(emr, "notes_list_trans", lambda _id: [])
    monkeypatch.setattr(
        emr,
        "notes_list_messages",
        lambda _id: [
            {
                "message_id": 7,
                "sent": sent,
                "msg_type": 5,
                "subject": "Refill: sample drug",
                "encounter_id": 70,
                "from_last": "Example",
                "from_first": "Doctor",
                "from_title": "DO",
            }
        ],
    )
    monkeypatch.setattr(
        emr,
        "notes_list_portal",
        lambda _id: [
            {
                "portal_id": 8,
                "sent": sent,
                "msg_type": 1,
                "subject": None,
                "encounter_id": None,
                "prov_last": None,
                "prov_first": None,
                "prov_title": None,
                "attachment_name": "x.pdf",
            }
        ],
    )
    index = {f"{n['kind']}-{n['id']}": n for n in live.note_index(11)}
    assert index["message-7"]["app_source"] == "Refill request"
    assert index["message-7"]["encounter_id"] == 70
    assert index["portal-8"]["title"] == "(no subject)"
    assert index["portal-8"]["app_source"] == "Portal message from patient"
    monkeypatch.setattr(
        emr,
        "note_message",
        lambda _e, _m: {
            "message_id": 7,
            "sent": sent,
            "msg_type": 3,
            "subject": "Call back",
            "phone": "555-0100",
            "to_addressees": None,
            "from_last": "Example",
            "from_first": "Doctor",
            "from_title": None,
            "to_last": None,
            "to_first": None,
            "to_title": None,
            "body": "Line one\r\nLine two  ",
        },
    )
    note = live.note(11, "message", 7)
    assert note["text"] == "Line one\nLine two"
    assert dict(note["message_fields"]) == {
        "Type": "Patient message",
        "From": "Example, Doctor",
        "Call-back phone": "555-0100",
        "Subject": "Call back",
    }
