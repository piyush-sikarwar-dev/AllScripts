"""Notes tab (Option A): classification, date range rules, counts, routes, export, print."""

import re
from datetime import date, datetime

import pytest
from sqlalchemy import func, select

from app.db.app import new_session
from app.lookups import LookupConfigError
from app.lookups.note_categories import NoteCategories, note_categories
from app.models.notes import NotesState
from app.repositories.appdb.models import AuditLog, ExportSelection
from app.services.export import ExportRequest, gather
from app.services.notes_service import (
    NoteMeta,
    counts_by_category,
    date_range,
    filtered,
    parse_state,
)
from tests.conftest import page_csrf
from tests.fakes.data import PATIENTS

P = PATIENTS[0]
FIRST = f"EMR:{P.emr_id}"
EMPTY = f"EMR:{PATIENTS[29].emr_id}"
HTMX = {"HX-Request": "true"}


def _refs(kind_filter=lambda n: True) -> list[dict]:
    return [n for n in P.clinical_notes if kind_filter(n)]


def _rx_ok() -> dict:
    """A prescription printout of the first patient that parses."""
    for n in P.clinical_notes:
        if "IMREMED_CODE" in n["map_sources"] and "Medication:" in (n["html"] or ""):
            return n
    raise AssertionError("fake data has no readable prescription")


def _ref(n: dict) -> str:
    return f"{n['kind']}-{n['id']}"


def _audit(action: str) -> list[AuditLog]:
    with new_session() as db:
        return list(db.scalars(select(AuditLog).where(AuditLog.action == action)))


def _csrf(client) -> dict[str, str]:
    return {**HTMX, "X-CSRF-Token": page_csrf(client, f"/patients/{FIRST}")}


# --- classification ------------------------------------------------------------------------------


def test_map_source_wins_over_title():
    cats = note_categories()
    assert cats.classify("* Lab Results by Date Range", {"IMREMED_CODE"}) == "rx"
    assert cats.classify("Sample letter", {"IMREQUISITION_CODE"}) == "lab"
    assert cats.classify("Glimepiride 4MG, 1 Tablet daily, #90, Ref. x1.", set()) == "rx"
    assert cats.classify("* History & Physical Note with Caregiver", set()) == "visit"
    assert cats.classify("Cover page for * History & Physical Note", set()) == "letter"
    assert cats.classify("Entire Chart Receipt", set()) == "letter"
    assert cats.classify("Anything", set(), transcription=True) == "visit"


def test_category_config_is_validated():
    good = note_categories().model_dump()
    bad = {"categories": dict(good["categories"])}
    bad["categories"]["lab"] = dict(bad["categories"]["lab"], title_regex=["(unclosed"])
    with pytest.raises(ValueError):
        NoteCategories.model_validate(bad)
    no_default = {"categories": {k: dict(v, default=False) for k, v in good["categories"].items()}}
    with pytest.raises(ValueError):
        NoteCategories.model_validate(no_default)
    assert issubclass(LookupConfigError, RuntimeError)


# --- state and date rules ------------------------------------------------------------------------


def test_parse_state_defaults_and_bad_values():
    assert parse_state({}) == NotesState()
    s = parse_state({"cat": "x", "range": "5y", "sort": "z", "page": "-2", "note": "doc-1",
                     "view": "raw"})  # fmt: skip
    assert s == NotesState()


def test_dates_swap_and_invalid_are_ignored():
    s = parse_state({"from": "2021-05-01", "to": "2020-01-31"})
    assert (s.range, s.date_from, s.date_to) == ("custom", date(2020, 1, 31), date(2021, 5, 1))
    s = parse_state({"range": "custom", "from": "13/45/2020", "to": "02/03/2021"})
    assert (s.date_from, s.date_to) == (None, date(2021, 2, 3))
    s = parse_state({"range": "12m", "from": "2020-01-01"})  # dates only count for custom
    assert s.date_from is None


def test_date_range_chips():
    today, earliest = date(2026, 10, 13), date(2011, 4, 2)
    assert date_range(NotesState(range="12m"), earliest, today) == (date(2025, 10, 14), today)
    assert date_range(NotesState(range="3y"), earliest, today) == (date(2023, 10, 14), today)
    assert date_range(NotesState(), earliest, today) == (earliest, today)
    custom = NotesState(range="custom", date_from=date(2015, 1, 1))
    assert date_range(custom, earliest, today) == (date(2015, 1, 1), today)
    assert date_range(NotesState(), None, today) == (today, today)
    leap = date(2024, 2, 29)
    assert date_range(NotesState(range="12m"), earliest, leap)[0] == date(2023, 3, 1)


def _m(category: str, day: date, title: str) -> NoteMeta:
    return NoteMeta(ref=f"document-{day.toordinal()}", kind="document", id=day.toordinal(),
                    day=day, sort_key=datetime(day.year, day.month, day.day), category=category,
                    title=title, subtitle="", who="Example", app_source="", source="EMR",
                    encounter_id=None, search_text=title.lower())  # fmt: skip


def test_counts_ignore_type_but_respect_dates_and_search():
    notes = [
        _m("rx", date(2020, 1, 1), "metformin"),
        _m("rx", date(2021, 1, 1), "glimepiride"),
        _m("lab", date(2021, 6, 1), "lab results"),
        _m("visit", date(2019, 1, 1), "metformin"),
    ]
    lo, hi = date(2020, 1, 1), date(2021, 12, 31)
    assert counts_by_category(notes, lo, hi, "") == {
        "all": 3,
        "rx": 2,
        "visit": 0,
        "lab": 1,
        "message": 0,
        "letter": 0,
    }
    assert counts_by_category(notes, lo, hi, "METFORMIN")["all"] == 1
    state = NotesState(cat="rx", sort="old")
    assert [m.title for m in filtered(notes, state, lo, hi)] == ["metformin", "glimepiride"]


def test_search_is_accent_insensitive():
    notes = [_m("letter", date(2020, 1, 1), "cafe")]
    notes[0].search_text = "café".casefold()
    from app.services.notes_service import _fold

    notes[0].search_text = _fold("Café")
    assert counts_by_category(notes, date(2000, 1, 1), date(2030, 1, 1), "CAFE")["all"] == 1


# --- routes --------------------------------------------------------------------------------------


def test_full_page_renders_every_part(client):
    r = client.get(f"/patients/{FIRST}", params={"tab": "notes"})
    assert r.status_code == 200
    for part in ('id="note-filters"', 'id="note-results"', 'id="note-detail"', "All notes",
                 "Prescriptions", "Visit notes", "Lab reports", "Letters &amp; other",
                 "Last 12 months", "All time", 'aria-pressed="true"'):  # fmt: skip
        assert part in r.text
    assert 'style="' not in r.text
    assert re.search(r"showing \d+ of [\d,]+", r.text)
    assert 'aria-current="true"' in r.text  # newest note selected


def test_full_page_with_every_param(client):
    n = _rx_ok()
    day = n["date"].date()
    params = {"tab": "notes", "cat": "rx", "range": "custom", "from": day.isoformat(),
              "to": day.isoformat(), "q": "", "sort": "old", "page": "1", "note": _ref(n),
              "view": "original"}  # fmt: skip
    r = client.get(f"/patients/{FIRST}", params=params)
    assert r.status_code == 200
    assert f'name="note" value="{_ref(n)}"' in r.text
    assert re.search(r'value="original"\s+aria-pressed="true"', r.text)
    assert "note-original" in r.text and "note-kv" not in r.text
    assert f'value="{day.isoformat()}"' in r.text
    assert '<option value="old" selected>' in r.text
    assert re.search(r'type-tile type-tile--on"[^>]*value="rx"', r.text)


def test_list_partial_oob_filters_follow_search(client):
    r = client.get(f"/patients/{FIRST}/notes/list", params={"q": "zzzz-nothing"}, headers=HTMX)
    assert r.status_code == 200
    assert r.text.lstrip().startswith('<div class="note-list__results" id="note-results"')
    assert 'id="note-filters"' in r.text and 'hx-swap-oob="true"' in r.text
    assert "No notes match these filters." in r.text and "Clear filters" in r.text
    counts = re.findall(r'type-tile__count">([\d,]+)<', r.text)
    assert counts == ["0"] * 6  # tile counts follow the search (All + 5 types)
    assert "q=zzzz-nothing" in r.headers["HX-Push-Url"]


def test_list_partial_keeps_or_replaces_the_open_note(client):
    rx, other = _rx_ok(), next(n for n in P.clinical_notes if n["kind"] == "document"
                               and not n["map_sources"] and "Letter" in n["title"])  # fmt: skip
    r = client.get(f"/patients/{FIRST}/notes/list", params={"cat": "rx", "note": _ref(rx)},
                   headers=HTMX)  # fmt: skip
    assert f"note={_ref(rx)}" in r.headers["HX-Push-Url"] and 'id="note-detail"' not in r.text
    r = client.get(f"/patients/{FIRST}/notes/list", params={"cat": "rx", "note": _ref(other)},
                   headers=HTMX)  # fmt: skip
    assert f"note={_ref(other)}" not in r.headers["HX-Push-Url"]
    assert 'id="note-detail"' in r.text  # first note of the new result, out of band


def test_filters_partial(client):
    r = client.get(f"/patients/{FIRST}/notes/filters", params={"range": "3y"}, headers=HTMX)
    assert r.status_code == 200 and "hx-swap-oob" not in r.text
    assert re.search(r'chip chip--on"[^>]*value="3y"', r.text)


def test_detail_formatted_and_original(client):
    n = _rx_ok()
    url = f"/patients/{FIRST}/notes/{_ref(n)}"
    r = client.get(url, headers=HTMX)
    assert r.status_code == 200 and "note-kv" in r.text and "Directions (SIG)" in r.text
    assert "Sample Community Pharmacy #12" in r.text and "DEA" not in r.text.split("note-kv")[1]
    assert P.phone not in r.text  # the patient block of the printout is not in the formatted view
    r = client.get(url, params={"view": "original"}, headers=HTMX)
    assert "note-original" in r.text and "view=original" in r.headers["HX-Push-Url"]
    assert [a.detail["view"] for a in _audit("view_note")] == ["formatted", "original"]
    assert _audit("view_note")[0].detail["category"] == "rx"


def test_unparseable_rx_falls_back_to_original(client):
    bad = next(n for n in P.clinical_notes if n["html"] == "<p>Unreadable printout</p>")
    r = client.get(f"/patients/{FIRST}/notes/{_ref(bad)}", headers=HTMX)
    assert "Couldn&#39;t format this note — showing the original." in r.text
    assert "Unreadable printout" in r.text and 'name="view" value="original"' in r.text


def test_html_is_sanitised_and_ssn_masked(client):
    visit = next(n for n in P.clinical_notes if "<script>" in (n["html"] or ""))
    r = client.get(f"/patients/{FIRST}/notes/{_ref(visit)}", params={"view": "original"},
                   headers=HTMX)  # fmt: skip
    assert "<script>" not in r.text and "onclick" not in r.text
    lab = next(n for n in P.clinical_notes if "SSN:" in (n["html"] or ""))
    r = client.get(f"/patients/{FIRST}/notes/{_ref(lab)}", params={"view": "original"},
                   headers=HTMX)  # fmt: skip
    assert "000-12-3456" not in r.text and "•••-••-••••" in r.text


def test_open_in_visits_only_for_linked_notes(client):
    linked = next(n for n in P.clinical_notes if n["encounter_id"])
    r = client.get(f"/patients/{FIRST}/notes/{_ref(linked)}", headers=HTMX)
    assert "Open in Visits" in r.text and f"visit={linked['encounter_id']}" in r.text
    unlinked = next(n for n in P.clinical_notes if not n["encounter_id"])
    r = client.get(f"/patients/{FIRST}/notes/{_ref(unlinked)}", headers=HTMX)
    assert "Open in Visits" not in r.text


@pytest.mark.parametrize(
    "note_ref", ["document-987654321", "bogus-9", "document-abc", "transcription-0"]
)
def test_unknown_note_is_404(client, note_ref):
    assert client.get(f"/patients/{FIRST}/notes/{note_ref}", headers=HTMX).status_code == 404


def test_other_patients_note_is_404_everywhere(client):
    other = _ref(PATIENTS[1].clinical_notes[0])
    assert client.get(f"/patients/{FIRST}/notes/{other}", headers=HTMX).status_code == 404
    assert client.get(f"/patients/{FIRST}/notes/{other}/print").status_code == 404
    r = client.post(f"/patients/{FIRST}/export-selection/notes/{other}", headers=_csrf(client))
    assert r.status_code == 404


def test_empty_patient(client):
    r = client.get(f"/patients/{EMPTY}", params={"tab": "notes"})
    assert r.status_code == 200 and "No notes recorded." in r.text


# --- add to export / print / PDF -----------------------------------------------------------------


def _selection_count() -> int:
    with new_session() as db:
        return db.scalar(select(func.count()).select_from(ExportSelection))


def test_add_note_to_export_and_header_counts_all_items(client):
    n = _rx_ok()
    headers = _csrf(client)
    r = client.post(f"/patients/{FIRST}/export-selection/notes/{_ref(n)}", headers=headers)
    assert r.status_code == 200 and "Added ✓ · Remove" in r.text
    assert 'id="export-button"' in r.text and "· 1 item<" in r.text
    visit = P.visits[0]["encounter_id"]
    r = client.post(f"/patients/{FIRST}/export-selection/visits/{visit}", headers=headers)
    assert "· 2 items<" in r.text  # visits + notes together
    r = client.post(f"/patients/{FIRST}/export-selection/notes/{_ref(n)}", headers=headers)
    assert "Add to export<" in r.text and "· 1 item<" in r.text
    assert _selection_count() == 1


def test_add_note_to_export_requires_csrf(client):
    url = f"/patients/{FIRST}/export-selection/notes/{_ref(_rx_ok())}"
    assert client.post(url, headers=HTMX).status_code == 403
    assert client.post(url, headers={**HTMX, "X-CSRF-Token": "forged"}).status_code == 403
    assert _selection_count() == 0


def test_export_dialog_and_pdf_context_include_selected_notes(client):
    n = _rx_ok()
    client.post(f"/patients/{FIRST}/export-selection/notes/{_ref(n)}", headers=_csrf(client))
    r = client.get(f"/patients/{FIRST}/export", headers=HTMX)
    assert "Notes added to export" in r.text
    assert f'name="note_ids" value="{_ref(n)}" checked' in r.text


@pytest.mark.anyio
async def test_pdf_gather_selected_notes(client):
    from app.crosswalk import resolve

    ref = await resolve(FIRST)
    n = _rx_ok()
    other = _ref(PATIENTS[1].clinical_notes[0])
    ctx = await gather(ref, ExportRequest(sections=[], note_ids=[_ref(n), other]))
    assert [d.ref for d in ctx["selected_notes"]] == [_ref(n)]  # other patient's note skipped
    assert ctx["selected_notes"][0].fields and ctx["selected_notes"][0].original_html


def test_print_note(client):
    n = _rx_ok()
    r = client.get(f"/patients/{FIRST}/notes/{_ref(n)}/print")
    assert r.status_code == 200
    assert "/static/js/print-auto.js" in r.text and "Printed by" in r.text
    assert 'class="sidebar' not in r.text and "note-kv" in r.text
    rows = _audit("print_note")
    assert len(rows) == 1 and rows[0].detail == {"note": _ref(n), "category": "rx"}
