"""Problems & allergies tab (Option B): rules, change history, routes, export, print."""

import re
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.db.app import new_session
from app.lookups import get_lookups
from app.lookups.history_codes import history_codes
from app.models.history import HistoryState
from app.repositories.appdb.models import AuditLog
from app.services.history_service import (
    _entry,
    build_detail,
    change_lines,
    code_view,
    default_section,
    describe_change,
    entry_row,
    parse_state,
    sections,
    visible,
)
from tests.conftest import page_csrf
from tests.fakes.data import PATIENTS

P = PATIENTS[0]
FIRST = f"EMR:{P.emr_id}"
EMPTY = f"EMR:{PATIENTS[29].emr_id}"
HTMX = {"HX-Request": "true"}


def _raw(
    hx_id=1,
    category=24,
    title="Sample problem",
    system="HISTORY",
    code="17354",
    activity=1,
    onset=None,
    mask=3,
    resolved=None,
    attributes=(),
    **extra,
) -> dict:
    return {
        "id": hx_id,
        "category_code": category,
        "code_system": system,
        "code": code,
        "imo_code": None,
        "title": title,
        "description": None,
        "activity_code": activity,
        "significance_code": 0,
        "acuity_code": 0,
        "onset": onset,
        "onset_mask": mask,
        "resolved": resolved,
        "comments": None,
        "basis": None,
        "reason": None,
        "recorded": datetime(2020, 1, 2, tzinfo=UTC),
        "provider": "Chen, L MD",
        "attributes": [
            {"sort_order": i, "title": t, "value": None, "severity_code": 0}
            for i, t in enumerate(attributes)
        ],
        "source": "EMR",
    } | extra


def _audit(action: str) -> list[AuditLog]:
    with new_session() as db:
        return list(db.scalars(select(AuditLog).where(AuditLog.action == action)))


# --- rules ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("category", "section"),
    [
        (24, "problems"),
        (21, "allergies"),
        (20, "surgical"),
        (23, "family"),
        (25, "social"),
        (29, "other"),
        (28, "other"),
        (99, "other"),
    ],
)
def test_category_to_section(category, section):
    assert _entry(_raw(category=category)).section == section


def test_unmapped_category_logged_once(caplog):
    _entry(_raw(category=77))
    _entry(_raw(category=77))
    logged = [r for r in caplog.records if "history_category_unmapped" in r.getMessage()]
    assert len(logged) <= 1 and all("code=77" in r.getMessage() for r in logged)


def test_code_display():
    assert code_view("ICD9", "250.00", None).model_dump() == {
        "standard": "ICD-9 250.00",
        "tags": [],
    }
    assert code_view("MEDISPAN_NAME", "184586", None).standard == "Medi-Span 184586"
    internal = code_view("HISTORY", "17354", 5678)
    assert internal.standard is None and internal.tags == ["History 17354", "IMO 5678"]
    assert code_view(None, None, None).model_dump() == {"standard": None, "tags": []}
    assert history_codes().system("weird").label == "Other"


@pytest.mark.parametrize(
    ("mask", "expected"),
    [
        (0, "Since 03/04/2019"),
        (1, "Since 2019"),
        (2, "Since 03/2019"),
        (3, "Since 03/04/2019"),
        (4, "Since 03/04/2019"),
        (None, "Since 03/04/2019"),
    ],
)
def test_partial_onset_dates(mask, expected):
    row = entry_row(_entry(_raw(onset=datetime(2019, 3, 4, 12, tzinfo=UTC), mask=mask)))
    assert row.meta == expected


def test_date_lines():
    assert entry_row(_entry(_raw())).meta == "Date not recorded"
    resolved = _entry(_raw(onset=date(2019, 3, 1), mask=2, resolved=date(2019, 4, 2), activity=3))
    assert entry_row(resolved).meta == "Since 03/2019 · Resolved 04/02/2019"
    assert entry_row(resolved).status == "resolved"


def test_statuses_and_active_filter():
    entries = [
        _entry(_raw(1, activity=1)),
        _entry(_raw(2, activity=2)),
        _entry(_raw(3, activity=8)),
        _entry(_raw(4, activity=1, resolved=date(2020, 1, 1))),
    ]
    assert [e.status for e in entries] == ["active", "inactive", "error", "resolved"]
    assert [e.id for e in visible(entries, "problems", "active")] == [1]
    assert {e.id for e in visible(entries, "problems", "all")} == {1, 2, 3, 4}


def test_allergy_kinds_and_nka_conflict():
    drug = _entry(
        _raw(
            1,
            category=21,
            title="Penicillin",
            system="MEDISPAN_NAME",
            code="1",
            attributes=["Hives"],
        )
    )
    nka = _entry(_raw(2, category=21, title="No Known Allergies", activity=1))
    assert drug.kind == "Drug" and nka.kind == "Status" and nka.is_nka
    detail = build_detail(nka, [drug, nka])
    assert detail.conflict
    assert not build_detail(nka, [nka]).conflict
    fields = {f.label: f.value for f in build_detail(drug, [drug, nka]).fields}
    assert (
        fields["Reaction"] == "Hives"
        and fields["Type"] == "Drug"
        and fields["Onset"] == "Not recorded"
    )


def test_rail_pills_and_default_section():
    state = HistoryState(sec="allergies")
    drug = _entry(_raw(1, category=21, title="Penicillin", system="MEDISPAN_NAME"))
    nka_on = _entry(_raw(2, category=21, title="NKDA"))
    nka_off = _entry(_raw(3, category=21, title="No known allergies", activity=2))
    pill = lambda es: next(s for s in sections(es, state) if s.key == "allergies")  # noqa: E731
    assert (pill([drug, nka_off]).pill, pill([drug, nka_off]).pill_kind) == ("1 active", "alert")
    assert pill([nka_on]).pill == "NKA"
    assert pill([nka_off]).pill == "None active"  # never "no allergies"
    assert pill([]).pill == "None active"
    assert default_section([drug]) == "allergies" and default_section([nka_on]) == "problems"
    assert "other" not in {s.key for s in sections([drug], state)}


def _rev(n, **changes):
    base = {
        "revision": n,
        "changed": datetime(2019, 1, n, tzinfo=UTC),
        "title": "Asthma",
        "activity_code": 1,
        "significance_code": 0,
        "onset": None,
        "onset_mask": 3,
        "resolved": None,
        "comments": None,
        "reason": None,
        "provider": "Chen, L MD",
    }
    return base | changes


def test_describe_change():
    assert describe_change(None, _rev(1)) == ["Added"]
    assert describe_change(None, _rev(1, activity_code=2)) == ["Added (inactive)"]
    assert describe_change(_rev(1), _rev(2, activity_code=2)) == ["Marked inactive"]
    assert describe_change(_rev(1), _rev(2, resolved=date(2019, 4, 1))) == ["Marked resolved"]
    assert describe_change(_rev(1), _rev(2, onset=date(2019, 3, 1), onset_mask=2)) == [
        "Onset changed to 03/2019"
    ]
    assert describe_change(_rev(1, comments="a"), _rev(2, comments="b")) == ["Comment edited"]
    assert describe_change(_rev(1), _rev(2, comments="a")) == ["Comment added"]
    assert describe_change(_rev(1), _rev(2, activity_code=8)) == ["Marked as entered in error"]
    assert describe_change(_rev(1), _rev(2)) == []  # nothing visible changed


def test_change_lines_newest_first_and_skip_empty():
    revs = [_rev(3, activity_code=2, reason="Patient report"), _rev(1), _rev(2)]
    lines = change_lines(revs)
    assert [line.text for line in lines] == [
        "Marked inactive — Patient report · Chen, L MD",
        "Added · Chen, L MD",
    ]
    assert lines[0].date == "01/03/2019"


def test_status_default_and_memory():
    state, given = parse_state({}, "s1")
    assert (state.sec, given) == ("problems", False)
    assert parse_state({"sec": "problems"}, "s-new")[0].status == "active"
    assert parse_state({"sec": "allergies"}, "s-new2")[0].status == "all"
    parse_state({"sec": "allergies", "status": "active"}, "s2")  # user picks Active
    assert parse_state({"sec": "family"}, "s2")[0].status == "active"  # remembered
    assert parse_state({"sec": "bogus", "status": "x", "entry": "1;2"}, None)[0] == HistoryState(
        sec="problems", status="active", entry=None
    )


def test_lookup_labels_for_acuity_and_significance():
    lk = get_lookups()
    assert lk.label("hx_acuity", 2) == "Chronic" and lk.label("hx_significance", 1) == "Major"


# --- routes --------------------------------------------------------------------------------------


def _entries(section: str | None = None) -> list[dict]:
    return [e for e in P.hx_entries if section is None or _entry(e).section == section]


def test_full_page_defaults_to_allergies_when_active(client):
    r = client.get(f"/patients/{FIRST}", params={"tab": "problems"})
    assert r.status_code == 200
    active_allergy = any(
        _entry(e).section == "allergies" and _entry(e).is_active and not _entry(e).is_nka
        for e in P.hx_entries
    )
    expected = "Allergies" if active_allergy else "Problems"
    assert re.search(
        r'section-rail__btn--on"[^>]*>\s*'
        rf'<span class="section-rail__name">{expected}',
        r.text,
    )
    for part in (
        'id="history-rail"',
        'id="history-list"',
        'id="history-detail"',
        "Change history",
        'hx-trigger="load"',
        "Status",
    ):
        assert part in r.text
    assert 'style="' not in r.text


def test_full_page_with_every_param(client):
    fam = _entries("family")[0]
    r = client.get(
        f"/patients/{FIRST}",
        params={"tab": "problems", "sec": "family", "status": "all", "entry": fam["id"]},
    )
    assert r.status_code == 200
    assert f'name="entry" value="{fam["id"]}"' in r.text and "Relationship" in r.text
    assert re.search(r'value="all"\s+aria-pressed="true"', r.text)


def test_list_partial_has_oob_rail_and_detail(client):
    r = client.get(
        f"/patients/{FIRST}/history/list", params={"sec": "social", "status": "all"}, headers=HTMX
    )
    assert r.status_code == 200
    assert r.text.lstrip().startswith('<section class="card entry-list" id="history-list"')
    assert 'id="history-rail"' in r.text and r.text.count('hx-swap-oob="true"') == 2
    assert "sec=social" in r.headers["HX-Push-Url"] and "entry=" in r.headers["HX-Push-Url"]
    assert f"{len(_entries('social'))} shown" in r.text


def test_rail_partial(client):
    r = client.get(f"/patients/{FIRST}/history/rail", params={"sec": "family"}, headers=HTMX)
    assert r.status_code == 200 and "hx-swap-oob" not in r.text and "Family history" in r.text


def test_status_toggle_filters(client):
    problems = _entries("problems")
    active = [e for e in problems if _entry(e).is_active]
    r = client.get(
        f"/patients/{FIRST}/history/list",
        params={"sec": "problems", "status": "active"},
        headers=HTMX,
    )
    assert f"{len(active)} shown" in r.text
    r = client.get(
        f"/patients/{FIRST}/history/list", params={"sec": "problems", "status": "all"}, headers=HTMX
    )
    assert f"{len(problems)} shown" in r.text


def test_entry_detail_changes_and_audit(client):
    e = _entries("problems")[0]
    r = client.get(f"/patients/{FIRST}/history/entries/{e['id']}", headers=HTMX)
    assert r.status_code == 200 and "data-focus-on-load" in r.text
    assert f"entry={e['id']}" in r.headers["HX-Push-Url"]
    r = client.get(f"/patients/{FIRST}/history/entries/{e['id']}/changes", headers=HTMX)
    assert r.status_code == 200 and ("change-line" in r.text or "No earlier changes" in r.text)
    assert "Added" in r.text
    rows = _audit("view_history_entry")
    assert rows[-1].detail == {"entry_id": e["id"], "section": "problems"}


def test_internal_code_is_a_tag_not_the_headline(client):
    internal = next(e for e in P.hx_entries if e["code_system"] == "HISTORY")
    r = client.get(f"/patients/{FIRST}/history/entries/{internal['id']}", headers=HTMX)
    assert (
        "No standard code" in r.text
        and f'<span class="tag">History {internal["code"]}</span>' in r.text
    )


@pytest.mark.parametrize("path", ["entries/{id}", "entries/{id}/changes"])
def test_other_patients_entry_is_404(client, path):
    other = PATIENTS[1].hx_entries[0]["id"]
    url = f"/patients/{FIRST}/history/" + path.format(id=other)
    assert client.get(url, headers=HTMX).status_code == 404
    assert (
        client.get(f"/patients/{FIRST}/history/entries/999999999", headers=HTMX).status_code == 404
    )


def test_empty_patient_and_section(client):
    r = client.get(f"/patients/{EMPTY}", params={"tab": "problems"})
    assert r.status_code == 200 and "Nothing recorded in this section." in r.text
    assert "Select an entry to see its details." in r.text
    r = client.get(f"/patients/{FIRST}/history/list", params={"sec": "other"}, headers=HTMX)
    assert r.status_code == 200


def test_add_entry_to_export_and_dialog(client):
    e = _entries("problems")[0]
    token = page_csrf(client, f"/patients/{FIRST}")
    url = f"/patients/{FIRST}/export-selection/history/{e['id']}"
    assert client.post(url, headers=HTMX).status_code == 403
    r = client.post(url, headers={**HTMX, "X-CSRF-Token": token})
    assert "Added ✓ · Remove" in r.text and "· 1 item<" in r.text
    r = client.get(f"/patients/{FIRST}/export", headers=HTMX)
    assert "Problems &amp; allergies added to export" in r.text
    assert f'name="history_ids" value="{e["id"]}" checked' in r.text
    other = PATIENTS[1].hx_entries[0]["id"]
    assert (
        client.post(
            f"/patients/{FIRST}/export-selection/history/{other}",
            headers={**HTMX, "X-CSRF-Token": token},
        ).status_code
        == 404
    )


def test_print_section(client):
    r = client.get(f"/patients/{FIRST}/history/print", params={"sec": "problems"})
    assert r.status_code == 200 and "Printed by" in r.text and "<table" in r.text
    assert "History 1" not in r.text  # internal ids are never printed
    assert _audit("print_history")[-1].detail == {"section": "problems"}
    assert client.get(f"/patients/{FIRST}/history/print", params={"sec": "x"}).status_code == 404


@pytest.mark.anyio
async def test_pdf_problems_section_allergies_first_without_internal_ids(client):
    from app.crosswalk import resolve
    from app.services.problems import problem_groups

    groups = await problem_groups(await resolve(FIRST))
    assert groups[0].key == "allergy" and groups[1].key == "problem"
    codes = [r.code for g in groups for r in g.rows]
    assert not any(c.startswith("HISTORY") or c.startswith("History") for c in codes)
