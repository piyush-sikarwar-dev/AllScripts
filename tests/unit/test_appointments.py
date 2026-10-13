"""Appointments tab: EMR + PM merge, statuses, filters, routes, PDF section."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.models.appointments import AppointmentsState
from app.repositories import emr, live, ntier
from app.services.appointments import build_page, parse_state, status_of
from tests.fakes.data import PATIENTS

P = PATIENTS[0]
FIRST = f"EMR:{P.emr_id}"
EMPTY = f"EMR:{PATIENTS[29].emr_id}"
HTMX = {"HX-Request": "true"}
EASTERN = timezone(timedelta(hours=-5))


# --- statuses ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("emr_status", "pm_status", "expected"),
    [
        (2, None, ("Completed", "kept")),
        (4, None, ("Cancelled", "cancelled")),
        (8, None, ("No-show", "no_show")),
        (1, None, ("Scheduled", "scheduled")),
        (77, None, ("Unknown", "other")),
        (2, "X", ("Cancelled", "cancelled")),  # the PM status wins when matched
        (4, "A", ("Completed", "kept")),
        (2, "B", ("Bumped", "cancelled")),
        (None, "N", ("No-show", "no_show")),
        (None, "?", ("Unknown", "other")),
    ],
)
def test_status_of(emr_status, pm_status, expected):
    assert status_of({"emr_status": emr_status, "pm_status": pm_status}) == expected


def test_parse_state():
    assert parse_state({}) == AppointmentsState()
    assert parse_state({"status": "kept", "year": "2019", "page": "2"}) == AppointmentsState(
        status="kept", year=2019, page=2
    )
    assert parse_state({"status": "x", "year": "19", "page": "-1"}) == AppointmentsState()


# --- EMR + PM merge (SQL stubbed) ----------------------------------------------------------------


def _emr_row(sched_id, starts, status, pm_id=None, time_in=None, comment=None):
    return {
        "sched_id": sched_id,
        "starts": starts,
        "status_code": status,
        "pm_id": pm_id,
        "time_in": time_in,
        "time_out": None,
        "comment": comment,
        "provider_last": "Example",
        "provider_first": "Doctor",
        "provider_title": "DO",
        "location": "Main Clinic",
    }


def _pm_row(pm_id, starts, status, **extra):
    return {
        "pm_id": pm_id,
        "starts": starts,
        "duration": 20,
        "status": status,
        "comment": None,
        "time_in": 924,
        "check_out": 1042,
        "cancelled_at": None,
        "no_show_at": None,
        "appt_type": "Office Visit 20 Min",
        "resource": "Example, Doctor",
        "location": "Main Office",
        "cancel_reason": None,
    } | extra


def test_merge_matches_same_patient_same_day_only(monkeypatch):
    emr_rows = [
        _emr_row(1, datetime(2019, 3, 4, 9, 0, tzinfo=EASTERN), 2, pm_id="501"),
        _emr_row(2, datetime(2012, 5, 6, 10, 0, tzinfo=EASTERN), 2, pm_id="502"),  # old-system id
        _emr_row(3, datetime(2018, 1, 2, 8, 0, tzinfo=EASTERN), 4, pm_id=None, comment=" note "),
    ]
    pm_rows = [
        _pm_row(501, datetime(2019, 3, 4, 9, 0), "X", cancel_reason="Reschedule"),
        _pm_row(502, datetime(2016, 7, 8, 11, 0), "A"),  # same id, different day → separate
        _pm_row(503, datetime(2020, 2, 3, 14, 30), "N"),  # PM only
    ]
    monkeypatch.setattr(emr, "appointments", lambda _id: emr_rows)
    monkeypatch.setattr(ntier, "appointments", lambda _id: pm_rows)
    rows = {r["id"]: r for r in live.appointments(11, 50011)}
    assert set(rows) == {"emr-1", "emr-2", "emr-3", "pm-502", "pm-503"}
    matched = rows["emr-1"]
    assert matched["sources"] == ["EMR", "PM"] and matched["pm_status"] == "X"
    assert matched["type"] == "Office Visit 20 Min" and matched["cancel_reason"] == "Reschedule"
    assert matched["arrived"] == "9:24 AM" and matched["left"] == "10:42 AM"  # HHMM integers
    assert rows["emr-2"]["sources"] == ["EMR"] and rows["emr-2"]["pm_status"] is None
    assert rows["emr-3"]["comment"] == "note"
    assert rows["pm-503"]["sources"] == ["PM"] and status_of(rows["pm-503"])[1] == "no_show"


def test_unlinked_patient_reads_emr_only(monkeypatch):
    monkeypatch.setattr(emr, "appointments", lambda _id: [_emr_row(1, datetime(2019, 1, 1), 2)])
    monkeypatch.setattr(ntier, "appointments", lambda _id: pytest.fail("PM must not be queried"))
    assert [r["id"] for r in live.appointments(11, None)] == ["emr-1"]


def test_sql_never_reads_free_text_sched_text():
    from app.db.sql_loader import SQL_DIR

    assert "SCHED_TEXT" not in (SQL_DIR / "emr" / "appointments.sql").read_text().split("--")[-1]
    sql = (SQL_DIR / "emr" / "appointments.sql").read_text()
    body = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    assert (
        "SCHED_TEXT" not in body
        and "Operator"
        not in (SQL_DIR / "ntier" / "appointments.sql").read_text().split("SELECT", 1)[1]
    )


# --- page building -------------------------------------------------------------------------------


def _appt(i, starts, emr_status, pm_status=None):
    return {
        "id": f"emr-{i}",
        "starts": starts,
        "emr_status": emr_status,
        "pm_status": pm_status,
        "type": None,
        "duration": None,
        "provider": None,
        "location": None,
        "cancel_reason": None,
        "arrived": None,
        "left": None,
        "comment": None,
        "sources": ["EMR"],
    }


def test_build_page_counts_filters_and_stats():
    appts = [
        _appt(i, datetime(2019 + i % 2, 1, 1 + i, 12, tzinfo=UTC), [2, 4, 8, 2][i % 4])
        for i in range(28)
    ]
    appts.sort(key=lambda a: a["starts"], reverse=True)
    page = build_page(appts, AppointmentsState())
    chips = {c.key: c.count for c in page.chips}
    assert chips == {"all": 28, "kept": 14, "cancelled": 7, "no_show": 7}
    assert len(page.rows) == 25 and page.pager.pages == 2
    assert [s.value for s in page.stats] == ["28", "14", "7", "7"]
    kept_2019 = build_page(appts, AppointmentsState(status="kept", year=2019))
    assert {c.key: c.count for c in kept_2019.chips}["all"] == 14  # chips follow the year
    assert all(r.status == "kept" for r in kept_2019.rows) and kept_2019.context.startswith(
        "Year 2019"
    )
    assert build_page(appts, AppointmentsState(page=99)).pager.page == 2  # clamped
    assert page.years == [2020, 2019]


# --- routes and PDF ------------------------------------------------------------------------------


def test_tab_renders_with_filters(client):
    r = client.get(f"/patients/{FIRST}", params={"tab": "appointments"})
    assert r.status_code == 200
    for part in ("Appointments", "Kept", "No-shows", 'class="chip', "appts-table"):
        assert part in r.text
    assert 'style="' not in r.text
    r = client.get(
        f"/patients/{FIRST}/tab/appointments", params={"status": "cancelled"}, headers=HTMX
    )
    assert r.status_code == 200 and "status=cancelled" in r.headers["HX-Push-Url"]
    assert "chip chip--on" in r.text and "Completed" not in r.text.split("<tbody>")[-1]


def test_tab_tab_bar_has_appointments_after_visits(client):
    r = client.get(f"/patients/{FIRST}", params={"tab": "appointments"})
    tabs = (
        r.text.index('id="tab-visits"'),
        r.text.index('id="tab-appointments"'),
        r.text.index('id="tab-notes"'),
    )
    assert tabs[0] < tabs[1] < tabs[2]


def test_empty_patient_and_no_match(client):
    r = client.get(f"/patients/{EMPTY}", params={"tab": "appointments"})
    assert r.status_code == 200 and "No appointments recorded." in r.text
    r = client.get(f"/patients/{FIRST}", params={"tab": "appointments", "year": "1999"})
    assert "No appointments match these filters." in r.text and "Clear filters" in r.text


@pytest.mark.anyio
async def test_pdf_appointments_respect_date_range(client):
    from datetime import date

    from app.crosswalk import resolve
    from app.services.export import ExportRequest, gather

    ref = await resolve(FIRST)
    every = await gather(ref, ExportRequest(sections=["appointments"]))
    assert len(every["appointments"]) == len(P.appointments)
    none = await gather(
        ref,
        ExportRequest(
            sections=["appointments"], date_from=date(1990, 1, 1), date_to=date(1990, 12, 31)
        ),
    )
    assert none["appointments"] == []
