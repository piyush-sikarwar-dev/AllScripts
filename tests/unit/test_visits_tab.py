"""Visits tab (Option C): routes, URL state, add-to-export selection, print page (fake data)."""

import re

import pytest
from sqlalchemy import func, select

from app.db.app import new_session
from app.models.visits import VisitsState
from app.repositories.appdb.models import AuditLog, ExportSelection
from app.services.export import SECTIONS, ExportRequest, _visits
from app.services.visits import build_detail, parse_state, year_bars
from app.templating import templates
from tests.conftest import page_csrf
from tests.fakes.data import PATIENTS

FIRST = f"EMR:{PATIENTS[0].emr_id}"
HTMX = {"HX-Request": "true"}


def _office(patient=PATIENTS[0]) -> list[dict]:
    return sorted(
        (v for v in patient.visits if v["is_office_visit"]),
        key=lambda v: (v["start"], v["encounter_id"]),
        reverse=True,
    )


def _csrf(client) -> dict[str, str]:
    return {**HTMX, "X-CSRF-Token": page_csrf(client, f"/patients/{FIRST}")}


def _audit(action: str) -> list[AuditLog]:
    with new_session() as db:
        return list(db.scalars(select(AuditLog).where(AuditLog.action == action)))


# --- state / helpers -----------------------------------------------------------------------------


def test_parse_state_defaults_and_rejects_bad_values():
    assert parse_state({}) == VisitsState()
    s = parse_state({"type": "lab", "year": "2019", "q": "  flu   shot ", "page": "3",
                     "visit": "77", "view": "original"})  # fmt: skip
    assert (s.type, s.year, s.q, s.page, s.visit, s.view) == (
        "lab", 2019, "flu shot", 3, 77, "original"
    )  # fmt: skip
    bad = parse_state({"type": "x", "year": "19", "page": "-1", "visit": "1;drop", "view": "raw"})
    assert bad == VisitsState()


def test_state_params_keep_urls_short():
    assert VisitsState().params() == {"tab": "visits", "type": None, "year": None, "q": "",
                                      "page": 1, "visit": None, "view": None}  # fmt: skip
    assert VisitsState(type="all", view="original").params()["type"] == "all"


def test_year_bars_fill_gaps_and_scale():
    bars = year_bars({2015: 10, 2018: 5}, selected=None)
    assert [b.year for b in bars] == [2015, 2016, 2017, 2018]
    assert [b.count for b in bars] == [10, 0, 0, 5]
    assert bars[0].height == 70 and bars[0].y == 0
    assert bars[1].height == 0  # empty year: no bar
    assert bars[3].height == 35
    assert {b.bar_class for b in bars} == {"bar"}
    assert year_bars({}, None) == []


def test_year_bars_minimum_height_and_selection():
    bars = year_bars({2010: 1000, 2011: 1}, selected=2011)
    assert bars[1].height == 3  # small years stay visible
    assert [b.bar_class for b in bars] == ["bar bar--dim", "bar bar--on"]
    assert [b.selected for b in bars] == [False, True]


def test_activity_summary_tie_goes_to_most_recent(client):
    """Most seen provider / diagnosis: ties are broken by the most recent visit."""
    from tests.fakes import repository as fake

    office = _office()
    result = fake.visits_activity(PATIENTS[0].emr_id, "office")
    counts: dict[str, int] = {}
    for v in office:
        counts[v["provider"]] = counts.get(v["provider"], 0) + 1
    best = max(counts.values())
    tied = [p for p, n in counts.items() if n == best]
    newest = next(v["provider"] for v in office if v["provider"] in tied)
    assert result["top_provider"] == newest and result["top_provider_count"] == best


# --- full page and partials ----------------------------------------------------------------------


def test_full_page_renders_every_part(client):
    newest = _office()[0]
    r = client.get(f"/patients/{FIRST}", params={"tab": "visits"})
    assert r.status_code == 200
    for part in ('id="visits-activity"', 'id="visit-filters"', 'id="visit-results"',
                 'id="visit-detail"', "Total visits", "Most seen provider",
                 "Most frequent diagnosis", "<svg width=\"44\" height=\"70\""):  # fmt: skip
        assert part in r.text
    # The newest office visit is selected and open.
    assert f'name="visit" value="{newest["encounter_id"]}"' in r.text
    assert 'aria-current="true"' in r.text
    assert 'style="' not in r.text  # CSP: no inline styles


def test_full_page_url_with_all_params(client):
    visit = PATIENTS[0].visits[0]
    params = {"tab": "visits", "type": "all", "year": str(visit["start"].year), "q": "",
              "page": "1", "visit": str(visit["encounter_id"]), "view": "original"}  # fmt: skip
    r = client.get(f"/patients/{FIRST}", params=params)
    assert r.status_code == 200
    assert '<option value="all" selected>' in r.text
    assert "bar bar--on" in r.text  # the year is selected
    assert re.search(r'value="original"\s+aria-pressed="true"', r.text)
    assert re.search(r'value="structured"\s+aria-pressed="false"', r.text)
    assert "original-block" in r.text or "No original note text" in r.text
    assert f'name="visit" value="{visit["encounter_id"]}"' in r.text


def test_full_page_audits_the_open_visit(client):
    client.get(f"/patients/{FIRST}", params={"tab": "visits"})
    rows = _audit("view_visit")
    assert len(rows) == 1 and rows[0].detail["encounter_id"] == _office()[0]["encounter_id"]


def test_tab_partial_pushes_visit_state(client):
    r = client.get(f"/patients/{FIRST}/tab/visits", params={"type": "all"}, headers=HTMX)
    assert r.status_code == 200
    push = r.headers["HX-Push-Url"]
    assert "tab=visits" in push and "type=all" in push and "visit=" in push
    assert [a.detail["tab"] for a in _audit("view_tab")] == ["visits"]


def test_list_partial_has_oob_activity_and_resets_nothing_else(client):
    year = _office()[0]["start"].year
    r = client.get(
        f"/patients/{FIRST}/visits/list", params={"year": year, "visit": "123"}, headers=HTMX
    )
    assert r.status_code == 200
    assert r.text.lstrip().startswith('<div class="visit-list__results" id="visit-results"')
    assert 'id="visits-activity"' in r.text and 'hx-swap-oob="true"' in r.text
    assert f"Year {year}" in r.text
    push = r.headers["HX-Push-Url"]
    assert f"year={year}" in push and "visit=123" in push and "tab=visits" in push


def test_list_partial_search_and_empty_state(client):
    r = client.get(f"/patients/{FIRST}/visits/list", params={"q": "zzzz-no-match"}, headers=HTMX)
    assert "No visits match these filters." in r.text and "Clear filters" in r.text
    assert "q=zzzz-no-match" in r.headers["HX-Push-Url"]


def test_list_partial_pages(client):
    patient = max(PATIENTS[:30], key=lambda p: len(p.visits))
    key = f"EMR:{patient.emr_id}"
    r = client.get(f"/patients/{key}/visits/list", params={"type": "all"}, headers=HTMX)
    if len(patient.visits) > 25:
        assert "Page 1 of 2" in r.text
        r2 = client.get(f"/patients/{key}/visits/list", params={"type": "all", "page": 2},
                        headers=HTMX)  # fmt: skip
        assert "Page 2 of 2" in r2.text
    else:
        assert 'class="pager"' not in r.text


def test_activity_partial(client):
    r = client.get(f"/patients/{FIRST}/visits/activity", params={"type": "all"}, headers=HTMX)
    assert r.status_code == 200
    assert "Total visits" in r.text and "hx-swap-oob" not in r.text
    assert f"{len(PATIENTS[0].visits):,}" in r.text


def test_detail_partial_views_and_audit(client):
    visit = _office()[0]
    url = f"/patients/{FIRST}/visits/{visit['encounter_id']}"
    r = client.get(url, params={"view": "original", "type": "all"}, headers=HTMX)
    assert r.status_code == 200
    assert "view=original" in r.headers["HX-Push-Url"] and "type=all" in r.headers["HX-Push-Url"]
    assert "note-grid" not in r.text
    r = client.get(url, headers=HTMX)
    assert "note-grid" in r.text and "view=" not in r.headers["HX-Push-Url"]
    assert [a.detail["view"] for a in _audit("view_visit")] == ["original", "structured"]


@pytest.mark.parametrize("encounter_id", ["999999999", "0", "abc"])
def test_unknown_encounter(client, encounter_id):
    r = client.get(f"/patients/{FIRST}/visits/{encounter_id}", headers=HTMX)
    assert r.status_code in (404, 422)


def test_other_patients_encounter_is_404_everywhere(client):
    other = PATIENTS[1].visits[0]["encounter_id"]
    assert client.get(f"/patients/{FIRST}/visits/{other}", headers=HTMX).status_code == 404
    assert client.get(f"/patients/{FIRST}/visits/{other}/print").status_code == 404
    r = client.post(f"/patients/{FIRST}/export-selection/visits/{other}", headers=_csrf(client))
    assert r.status_code == 404


def test_original_view_escapes_note_text():
    enc = {"encounter_id": 1, "date": None, "visit_type": "Office Visit", "signed": True,
           "provider": "Example, Doctor", "location": None, "source": "EMR",
           "text_notes": ["<script>alert(1)</script> plain"], "note_documents": [], "vitals": [],
           "assessment": [], "plan": [], "addenda": [], "other_documents": []}  # fmt: skip
    detail = build_detail(enc, "original", False)
    html = templates.get_template("partials/visit_detail.html").render(
        detail=detail, key=FIRST, visits_state=VisitsState(), partial=True, csrf_token="t"
    )
    assert "<script>alert" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# --- add to export -------------------------------------------------------------------------------


def _selection_count() -> int:
    with new_session() as db:
        return db.scalar(select(func.count()).select_from(ExportSelection))


def test_add_to_export_toggles_and_updates_header(client):
    visit = _office()[0]
    url = f"/patients/{FIRST}/export-selection/visits/{visit['encounter_id']}"
    headers = _csrf(client)
    r = client.post(url, headers=headers)
    assert r.status_code == 200
    assert "Added to export ✓" in r.text and 'aria-pressed="true"' in r.text
    assert 'id="export-button"' in r.text and 'hx-swap-oob="true"' in r.text
    assert "· 1 item<" in r.text
    assert _selection_count() == 1
    page = client.get(f"/patients/{FIRST}", params={"tab": "visits"}).text
    assert "Added to export ✓" in page and "· 1 item<" in page
    r = client.post(url, headers=headers)
    assert "Add to export<" in r.text and "item<" not in r.text.split('id="export-button"')[1]
    assert _selection_count() == 0


def test_add_to_export_requires_csrf(client):
    visit = _office()[0]
    url = f"/patients/{FIRST}/export-selection/visits/{visit['encounter_id']}"
    assert client.post(url, headers=HTMX).status_code == 403
    assert client.post(url, headers={**HTMX, "X-CSRF-Token": "forged"}).status_code == 403
    assert _selection_count() == 0


def test_add_to_export_without_js_redirects_back(client):
    visit = _office()[0]
    token = page_csrf(client, f"/patients/{FIRST}")
    r = client.post(f"/patients/{FIRST}/export-selection/visits/{visit['encounter_id']}",
                    data={"csrf_token": token}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    assert r.headers["location"] == f"/patients/{FIRST}?tab=visits&visit={visit['encounter_id']}"


def test_export_dialog_preselects_added_visits(client):
    visit = _office()[0]
    client.post(f"/patients/{FIRST}/export-selection/visits/{visit['encounter_id']}",
                headers=_csrf(client))  # fmt: skip
    r = client.get(f"/patients/{FIRST}/export", headers=HTMX)
    assert "Visits added to export" in r.text
    assert f'name="visit_ids" value="{visit["encounter_id"]}" checked' in r.text


def test_selection_cleared_on_logout(client):
    visit = _office()[0]
    client.post(f"/patients/{FIRST}/export-selection/visits/{visit['encounter_id']}",
                headers=_csrf(client))  # fmt: skip
    assert _selection_count() == 1
    client.post("/logout", data={"csrf_token": page_csrf(client)}, follow_redirects=False)
    assert _selection_count() == 0


@pytest.mark.anyio
async def test_pdf_visits_are_only_the_selected_encounters(client):
    from app.crosswalk import resolve

    ref = await resolve(FIRST)
    other_type = next((v for v in PATIENTS[0].visits if not v["is_office_visit"]), None)
    picked = [_office()[-1]] + ([other_type] if other_type else [])
    ids = [v["encounter_id"] for v in picked]
    details = await _visits(ref, ExportRequest(sections=[], visit_ids=ids))
    assert sorted(d.visit.id for d in details) == sorted(v["contact_id"] for v in picked)
    # Without a selection: office visits in range, as before.
    everything = await _visits(ref, ExportRequest(sections=["visits"]))
    assert len(everything) == len(_office())
    # Section ticked as well: the whole section plus the added visits.
    both = await _visits(ref, ExportRequest(sections=["visits"], visit_ids=ids))
    expected = {v["contact_id"] for v in _office()} | {v["contact_id"] for v in picked}
    assert {d.visit.id for d in both} == expected


def test_export_dialog_defaults_to_added_items_only(client):
    r = client.get(f"/patients/{FIRST}/export", headers=HTMX)
    assert r.text.count('name="sections"') == r.text.count('name="sections" value=') > 0
    # nothing added → every section ticked
    assert len(re.findall(r'name="sections" value="\w+" checked', r.text)) == len(SECTIONS)
    visit = _office()[0]
    client.post(f"/patients/{FIRST}/export-selection/visits/{visit['encounter_id']}",
                headers=_csrf(client))  # fmt: skip
    r = client.get(f"/patients/{FIRST}/export", headers=HTMX)
    assert re.findall(r'name="sections" value="\w+" checked', r.text) == []
    assert "Only the items you added are included." in r.text
    assert "Also include whole sections" in r.text


def test_export_with_only_added_visits_is_valid():
    from app.services.export import parse_export_form

    class Form(dict):
        def getlist(self, key):
            value = self.get(key, [])
            return value if isinstance(value, list) else [value]

    req = parse_export_form(Form(recipient="Example", purpose="Legal", visit_ids=["123"]))
    assert req.errors == {} and req.visit_ids == [123] and req.sections == []
    req = parse_export_form(Form(recipient="Example", purpose="Legal"))
    assert "sections" in req.errors


# --- print ---------------------------------------------------------------------------------------


def test_print_page(client):
    visit = _office()[0]
    r = client.get(f"/patients/{FIRST}/visits/{visit['encounter_id']}/print")
    assert r.status_code == 200
    assert "/static/js/print-auto.js" in r.text and "Printed by" in r.text
    assert 'class="sidebar' not in r.text and "note-grid" in r.text
    assert PATIENTS[0].last_name in r.text  # patient name on the printout
    rows = _audit("print_visit")
    assert len(rows) == 1 and rows[0].detail == {"encounter_id": visit["encounter_id"]}
