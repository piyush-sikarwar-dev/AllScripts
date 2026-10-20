"""Real-data patient list (USE_FAKE_DATA=false), with SQL calls stubbed — no database touched."""

from datetime import UTC, date, datetime

import pytest

from app import repositories
from app.crosswalk.build import build_crosswalk_rows, replace_crosswalk
from app.db.app import new_session
from app.repositories import emr, live

BUILT = datetime(2026, 10, 12, tzinfo=UTC)


class FakeSql:
    """Records run_query/run_scalar calls and returns canned rows."""

    def __init__(self, rows=None, visits=None, counts=None):
        self.rows = rows or []
        self.visits = visits or []
        self.counts = counts or {}
        self.calls: list[tuple[str, dict]] = []

    def run_query(self, source, sql_name, params=None, *, expanding=()):
        self.calls.append((sql_name, dict(params or {})))
        if sql_name == emr.PATIENT_SEARCH:
            return self.rows
        if sql_name == emr.MRNS:
            return [{"emr_id": i, "mrn": f"M{i}"} for i in params["emr_ids"]]
        if sql_name == emr.LAST_VISITS:
            assert expanding == ("emr_ids",)
            return self.visits
        raise AssertionError(sql_name)

    def run_scalar(self, source, sql_name, params=None, *, expanding=()):
        self.calls.append((sql_name, dict(params or {})))
        return self.counts.get(params["table_name"], 0)


def _row(emr_id, last, first, **extra):
    return {
        "emr_id": emr_id,
        "last_name": last,
        "first_name": first,
        "middle_initial": None,
        "dob": datetime(1960, 5, 4),
        "dob_mask": None,
        "sex_code": "F",
        "deceased": 0,
        "total_count": 2,
        **extra,
    }


@pytest.fixture
def sql(monkeypatch):
    fake = FakeSql(
        rows=[_row(11, "Sample", "Patient A"), _row(12, "Sample", "Patient B")],
        visits=[{"emr_id": 11, "last_visit": datetime(2019, 3, 2, 9, 30, tzinfo=UTC)}],
        counts={"DEMOGRAPHICS": 21_384, "ENCOUNTER": 2_565_968, "LAB_RESULT": 1_603_126,
                "SCAN_DOCUMENT": 626_325},
    )  # fmt: skip
    monkeypatch.setattr(emr, "run_query", fake.run_query)
    monkeypatch.setattr(emr, "run_scalar", fake.run_scalar)
    monkeypatch.setattr(live, "_totals_cache", None)
    return fake


@pytest.fixture
def real_mode(monkeypatch):
    from app.config import get_settings

    settings = get_settings().model_copy(update={"use_fake_data": False})
    monkeypatch.setattr(repositories, "get_settings", lambda: settings)
    import app.services.patients as patients_service

    monkeypatch.setattr(patients_service, "get_settings", lambda: settings)


def test_like_prefix_escapes_wildcards():
    assert emr.like_prefix("O'Neil") == "O'Neil%"
    assert emr.like_prefix("50%_[x]\\") == "50\\%\\_\\[x]\\\\%"
    assert emr.like_prefix("") is None and emr.like_prefix(None) is None


def test_search_params_and_mapping(sql):
    with new_session() as db:
        replace_crosswalk(db, build_crosswalk_rows(
            [{"emr_id": 11, "ntier_id": 500, "ntier_active_id": 500}, {"emr_id": 12}], [], BUILT
        )[0])  # fmt: skip
    rows, total = live.search_patients(
        last_name="Sam_ple", first_name=None, dob=date(1960, 5, 4), chart_id=None, offset=25,
        limit=25,
    )  # fmt: skip
    name, params = sql.calls[0]
    assert name == emr.PATIENT_SEARCH
    assert params == {
        "last_name_like": "Sam\\_ple%",
        "first_name_like": None,
        "dob": date(1960, 5, 4),
        "chart_id": None,
        "offset": 25,
        "limit": 25,
    }
    assert total == 2
    assert rows[0]["chart_id"] == "M11" and rows[0]["ntier_id"] == 500
    assert rows[1]["ntier_id"] is None


def test_last_visits_only_for_page_ids(sql):
    assert live.last_visits([11, 12]) == {11: datetime(2019, 3, 2, 9, 30, tzinfo=UTC)}
    assert sql.calls[-1] == (emr.LAST_VISITS, {"emr_ids": [11, 12]})


def test_mrns_for_page(sql):
    assert live.search_patients(last_name=None, first_name=None, dob=None, chart_id=None,
                                offset=0, limit=25)[0][1]["chart_id"] == "M12"  # fmt: skip
    assert (emr.MRNS, {"emr_ids": [11, 12]}) in sql.calls
    assert live.last_visits([]) == {}


def test_totals_from_catalog_and_cached(sql):
    assert live.totals()["patients"] == 21_384
    calls = len(sql.calls)
    assert live.totals()["scanned_documents"] == 626_325
    assert len(sql.calls) == calls  # second call served from the 24 h cache


def test_dashboard_renders_real_rows(sql, real_mode, client):
    r = client.get("/patients")
    assert r.status_code == 200
    assert "Sample, Patient A" in r.text and "Sample, Patient B" in r.text
    assert "21,384" in r.text
    assert "03/02/2019" in r.text  # last visit
    assert "05/04/1960" in r.text  # DOB


class ChartSql(FakeSql):
    """Canned rows for the chart header + Overview queries (clearly fake values)."""

    def run_query(self, source, sql_name, params=None, *, expanding=()):
        self.calls.append((sql_name, dict(params or {})))
        onset = datetime(2015, 6, 1, tzinfo=UTC)
        canned = {
            emr.PATIENT_HEADER_FULL: [
                {
                    "emr_id": 11,
                    "last_name": "Sample",
                    "first_name": "Patient A",
                    "middle_initial": None,
                    "dob": date(1960, 5, 4),
                    "dob_mask": 3,
                    "sex_code": 1,
                    "deceased": 0,
                    "date_of_death": None,
                    "date_of_death_mask": None,
                    "address": "1 Example Street",
                    "city": "Anytown",
                    "state": "ST",
                    "zip": "00000",
                    "phone": "(555) 010-0000",
                    "primary_insurance": "Sample Health Plan",
                    "mrn": "M11",
                }
            ],
            emr.HISTORY_ITEMS: [
                {
                    "hx_id": 1,
                    "category_code": 24,
                    "title": "Sample problem",
                    "code_system": "ICD10",
                    "code": "Z00.0",
                    "onset": onset,
                    "onset_mask": 3,
                    "resolved": None,
                    "activity_code": 1,
                },
                {
                    "hx_id": 2,
                    "category_code": 24,
                    "title": "Old problem",
                    "code_system": None,
                    "code": None,
                    "onset": onset,
                    "onset_mask": 3,
                    "resolved": date(2016, 1, 1),
                    "activity_code": 1,
                },
                {
                    "hx_id": 3,
                    "category_code": 21,
                    "title": "Sample allergen",
                    "code_system": None,
                    "code": None,
                    "onset": None,
                    "onset_mask": None,
                    "resolved": None,
                    "activity_code": 1,
                },
            ],
            emr.HISTORY_ATTRIBUTES: [
                {"hx_id": 3, "title": "Rash", "sort_order": 2},
                {"hx_id": 3, "title": "Hives", "sort_order": 1},
            ],
            emr.HISTORY_ENTRY_ATTRIBUTES: [
                {
                    "hx_id": 3,
                    "attribute_id": 2,
                    "title": "Rash",
                    "value": None,
                    "severity_code": 0,
                    "sort_order": 2,
                },
                {
                    "hx_id": 3,
                    "attribute_id": 1,
                    "title": "Hives",
                    "value": None,
                    "severity_code": 0,
                    "sort_order": 1,
                },
            ],
            emr.MEDICATIONS: [
                {
                    "med_id": 7,
                    "title": "Sample med 10 mg",
                    "dose": "1",
                    "dose_unit": "tablet",
                    "route": "by mouth",
                    "frequency": "daily",
                    "intake": None,
                    "start_date": date(2020, 1, 1),
                    "start_mask": 3,
                    "end_date": None,
                    "end_mask": None,
                    "status_code": 1,
                },
                {
                    "med_id": 8,
                    "title": "Stopped med",
                    "dose": None,
                    "dose_unit": None,
                    "route": None,
                    "frequency": None,
                    "intake": "as directed",
                    "start_date": date(2019, 1, 1),
                    "start_mask": 3,
                    "end_date": date(2019, 2, 1),
                    "end_mask": 3,
                    "status_code": 3,
                },
            ],
            emr.HX_MEDICATIONS: [],
            emr.REMINDERS: [
                {
                    "reminder_id": 1,
                    "due_at": datetime(2023, 9, 1, 12, tzinfo=UTC),
                    "subject": "Sample reminder",
                    "priority": 2,
                    "completed": 0,
                    "completed_at": None,
                    "entered_at": None,
                    "erroneous": 0,
                    "entered_last": None,
                    "entered_first": None,
                    "completed_last": None,
                    "completed_first": None,
                }
            ],
            emr.PATIENT_INSURANCES: [
                {
                    "policy_id": 1,
                    "rank": 0,
                    "carrier": "Sample Health Plan",
                    "carrier_phone": None,
                    "plan_type": 5,
                    "group_number": "G-1",
                    "plan_number": None,
                    "member_id": "MEM-1",
                    "effective_date": date(2019, 1, 1),
                    "termination_date": None,
                    "subscriber_last": "Sample",
                    "subscriber_first": "Patient A",
                    "subscriber_middle": None,
                    "subscriber_dob": date(1960, 5, 4),
                    "relation_code": 1,
                    "workers_comp": 0,
                    "archived": 0,
                },
                {
                    "policy_id": 2,
                    "rank": 0,
                    "carrier": "Old Sample Plan",
                    "carrier_phone": None,
                    "plan_type": 3,
                    "group_number": None,
                    "plan_number": None,
                    "member_id": None,
                    "effective_date": None,
                    "termination_date": date(2017, 1, 1),
                    "subscriber_last": None,
                    "subscriber_first": None,
                    "subscriber_middle": None,
                    "subscriber_dob": None,
                    "relation_code": 0,
                    "workers_comp": 0,
                    "archived": 1,
                },
            ],
            emr.PATIENT_PROFILE: [
                {
                    "marital_status": 2,
                    "guarantor_relation": 1,
                    "guarantor_last": "Sample",
                    "guarantor_first": "Patient A",
                    "guarantor_middle": None,
                    "guarantor_suffix": None,
                    "guarantor_dob": date(1960, 5, 4),
                    "guarantor_address": "1 Example Street",
                    "guarantor_city": "Anytown",
                    "guarantor_state": "ST",
                    "guarantor_zip": "00000",
                    "guarantor_phone": None,
                    "has_photo": 0,
                }
            ],
            emr.PATIENT_RACE: [{"code": 5}],
            emr.PATIENT_ETHNICITY: [{"code": 2}],
            emr.PATIENT_CONTACTS: [
                {
                    "contact_id": 1,
                    "rank": 1,
                    "last_name": "Contact",
                    "first_name": "Sample",
                    "middle_name": None,
                    "relationship": "Spouse",
                    "emergency": 1,
                    "proxy": 1,
                    "address": None,
                    "city": None,
                    "state": None,
                    "zip": None,
                    "phone": "555-0300",
                    "mobile": None,
                    "email": None,
                }
            ],
            emr.PATIENT_CARE_TEAM: [
                {
                    "role_code": 1,
                    "added_at": datetime(2016, 1, 4, tzinfo=UTC),
                    "provider_last": "Doctor",
                    "provider_first": "Example",
                    "provider_title": "MD",
                }
            ],
            emr.PATIENT_CONSENTS: [
                {
                    "consent_id": 1,
                    "consent_code": 1,
                    "answer_code": 3,
                    "expires": None,
                    "recorded_at": datetime(2016, 1, 4, tzinfo=UTC),
                }
            ],
            emr.LAST_VISIT_DETAIL: [
                {
                    "contact_id": 5,
                    "start": datetime(2021, 3, 4, 10, tzinfo=UTC),
                    "visit_type_code": 98,
                    "provider_last": "Example",
                    "provider_first": "Doctor",
                    "provider_title": "MD",
                    "location": "Main Clinic",
                }
            ],
        }
        if sql_name == emr.HISTORY_ENTRIES:
            return [_hx_entry(r) for r in canned[emr.HISTORY_ITEMS]]
        if sql_name in canned:
            return canned[sql_name]
        return super().run_query(source, sql_name, params, expanding=expanding)


def _hx_entry(row: dict) -> dict:
    """history_entries.sql row shape from a history_items.sql row (extra columns empty)."""
    extra = dict.fromkeys(("description", "comments", "basis", "reason", "imo_code"))
    return (
        row
        | extra
        | {
            "significance_code": 0,
            "acuity_code": 0,
            "recorded": datetime(2017, 5, 1, tzinfo=UTC),
            "provider_last": "Example",
            "provider_first": "Doctor",
            "provider_title": "DO",
        }
    )


@pytest.fixture
def chart_mode(monkeypatch, real_mode):
    from app import crosswalk as crosswalk_module
    from app.config import get_settings
    from app.repositories import ntier

    fake = ChartSql()
    monkeypatch.setattr(emr, "run_query", fake.run_query)
    pm_policy = {"policy_id": 9, "coverage": "P", "relationship": " ",
                 "carrier": "Sample PM Carrier", "carrier_phone": None, "plan_name": None,
                 "group_name": None, "group_number": None,
                 "certificate_number": "CERT-9", "effective_date": date(2018, 1, 1),
                 "expiration_date": None, "copay": None, "holder_last": None, "holder_first": None,
                 "holder_middle": None, "holder_dob": None}  # fmt: skip

    referral = {"referral_id": 1, "referral_date": date(2019, 4, 2), "expires": None,
                "status": "A", "is_external": True, "authorization_number": "AUTH-9",
                "precert_number": None, "visits_authorized": None, "notes": None,
                "from_last": "Referrer", "from_first": "Sample", "from_suffix": None,
                "to_last": None, "to_first": None, "to_suffix": None, "carrier": None}  # fmt: skip

    def ntier_rows(source, sql_name, params=None, **_k):
        if sql_name == ntier.PATIENT_POLICIES:
            return [pm_policy]
        if sql_name == ntier.INCOMING_REFERRALS:
            return [referral]
        if sql_name == ntier.INCOMING_REFERRAL_DIAGNOSES:
            return []
        return [{"patient_number": "P1", "account_number": "A-900"}]

    monkeypatch.setattr(ntier, "run_query", ntier_rows)
    settings = get_settings().model_copy(update={"use_fake_data": False})
    monkeypatch.setattr(crosswalk_module, "get_settings", lambda: settings)
    crosswalk_module.clear_cache()
    with new_session() as db:
        replace_crosswalk(
            db,
            build_crosswalk_rows(
                [{"emr_id": 11, "ntier_id": 500, "ntier_active_id": 500}], [], BUILT
            )[0],
        )
    yield fake
    crosswalk_module.clear_cache()


def test_real_chart_header_and_overview(chart_mode, client):
    r = client.get("/patients/EMR:11")
    assert r.status_code == 200
    html = r.text
    for text in (
        "Sample, Patient A",
        "05/04/1960",
        "Female",
        "M11",
        "A-900",
        "(555) 010-0000",
        "1 Example Street, Anytown, ST 00000",
        "Sample Health Plan",
        "badge--pm",
    ):
        assert text in html, text
    assert "Sample problem" in html and "Onset 06/01/2015" in html
    assert "Old problem" not in html  # resolved
    assert "Sample allergen" in html and "Hives, Rash" in html
    assert "Sample med 10 mg" in html and "1 tablet by mouth daily" in html
    assert "Stopped med" not in html  # ended
    assert "03/04/2021" in html and "Example, Doctor MD" in html and "Main Clinic" in html
    # Patient details (Overview): every live query feeds the cards.
    assert "Sample Health Plan" in html and "BCBS" in html and "MEM-1" in html
    assert "Old Sample Plan" not in html and "Show archived (1)" in html
    assert "White" in html and "Not Hispanic or Latino" in html and "Married" in html
    assert "Health-care proxy" in html and "Primary care physician" in html and "HIPAA" in html
    assert "Sample PM Carrier" in html  # PM policies via the Ntier link
    assert "Sample reminder" in html and "High priority" in html
    assert "AUTH-9" in html and "Referrer, Sample" in html and "Active" in html


def test_not_connected_error_renders_friendly_page(chart_mode, client, monkeypatch):
    """Any chart area that is not wired raises NotConnectedError -> friendly 501, not a crash."""

    def boom(*_a):
        raise live.NotConnectedError

    monkeypatch.setattr(live, "documents", boom)
    r = client.get("/patients/EMR:11?tab=docs")
    assert r.status_code == 501 and "Not connected yet" in r.text
    r = client.get("/patients/EMR:11/tab/docs", headers={"HX-Request": "true"})
    assert r.status_code == 501 and "not connected to the archive yet" in r.text


def _hx(hx_id, category, title, activity, mask=3, resolved=None):
    return {"hx_id": hx_id, "category_code": category, "title": title, "code_system": None,
            "code": None, "onset": datetime(2015, 6, 1, tzinfo=UTC), "onset_mask": mask,
            "resolved": resolved, "activity_code": activity}  # fmt: skip


def _med(med_id, title, status, end=None):
    return {"med_id": med_id, "title": title, "dose": None, "dose_unit": None, "route": None,
            "frequency": None, "intake": None, "start_date": date(2020, 1, 1), "start_mask": 3,
            "end_date": end, "end_mask": 3, "status_code": status}  # fmt: skip


def test_decoded_statuses_and_erroneous_rows(monkeypatch):
    monkeypatch.setattr(emr, "history_items", lambda _id: [
        _hx(1, 24, "Active problem", 1, mask=1),
        _hx(2, 24, "Resolved problem", 3),
        _hx(3, 24, "Mistake", 8),
    ])  # fmt: skip
    monkeypatch.setattr(emr, "history_attributes", lambda *_a: [])
    items = {h["title"]: h for h in live.history(11)}
    assert "Mistake" not in items  # Erroneous Entry hidden
    assert items["Active problem"]["is_active"] and items["Active problem"]["status"] == "Active"
    assert items["Active problem"]["onset_precision"] == "year"  # DATEMASK 1 = YYYY
    assert not items["Resolved problem"]["is_active"]
    assert items["Resolved problem"]["status"] == "Resolved"

    monkeypatch.setattr(emr, "medications", lambda _id: [
        _med(1, "Active med", 1), _med(2, "Discontinued med", 3), _med(3, "Wrong med", 6),
        _med(4, "Continued med", 5), _med(5, "Active but ended", 1, end=date(2019, 1, 1)),
    ])  # fmt: skip
    monkeypatch.setattr(emr, "hx_medications", lambda _id: [])
    meds = {m["name"]: m for m in live.medications(11)}
    assert "Wrong med" not in meds
    assert meds["Discontinued med"]["status"] == "Discontinued"
    current = sorted(n for n, m in meds.items() if m["is_active"])
    assert current == ["Active med", "Continued med"]


def _lab(result_id, test, value, status=3, flags=None, abnormal=0, observed=None, recorded=None):
    return {"result_id": result_id, "test": test, "value": value, "units": "mg/dL",
            "normal_range": "70-99", "abnormal": abnormal, "flags": flags, "observed": observed,
            "completed": None, "recorded": recorded, "status_code": status,
            "corrected": 0}  # fmt: skip


def test_live_labs_flags_dates_and_hidden_statuses(monkeypatch):
    monkeypatch.setattr(emr, "lab_results", lambda _id: [
        _lab(1, "Glucose", "150", flags="H ", abnormal=1,
             observed=datetime(2019, 3, 2, 14, tzinfo=UTC)),
        _lab(2, "Glucose", "88", recorded=datetime(2018, 1, 5, 9, tzinfo=UTC)),  # no obs date
        _lab(3, "Glucose", "999", status=6),  # canceled
        _lab(4, "Glucose", "0", status=7),  # erroneous
        _lab(5, "TSH", "abnormal text", abnormal=1, flags=""),
    ])  # fmt: skip
    rows = {r["id"]: r for r in live.labs(11)}
    assert set(rows) == {1, 2, 5}
    assert rows[1]["flag"] == "H" and rows[1]["date"] == date(2019, 3, 2)
    assert rows[2]["flag"] is None and rows[2]["date"] == date(2018, 1, 5)
    assert rows[5]["flag"] == "A"


def test_live_vitals_units_and_numbers(monkeypatch):
    from decimal import Decimal

    monkeypatch.setattr(emr, "vitals", lambda _id: [{
        "vital_id": 1, "contact_id": 9, "taken": datetime(2019, 3, 2, 14, tzinfo=UTC),
        "systolic": 128, "diastolic": 82, "pulse": 70, "temperature": Decimal("98.60"),
        "temperature_unit": 4, "weight": Decimal("180.500"), "weight_unit": 6,
        "height": Decimal("68.0"), "height_unit": 2, "spo2": 97, "pain": None,
    }])  # fmt: skip
    v = live.vitals(11)[0]
    assert (v["temp"], v["temp_unit"]) == ("98.6", "°F")
    assert (v["weight"], v["weight_unit"]) == ("180.5", "lb")
    assert (v["height"], v["height_unit"]) == ("68", "in")
    assert v["pain"] is None


def test_real_labs_and_vitals_tabs_render(chart_mode, client, monkeypatch):
    monkeypatch.setattr(emr, "lab_results", lambda _id: [
        _lab(1, "Glucose", "150", flags="H", abnormal=1, observed=datetime(2019, 3, 2, tzinfo=UTC))
    ])  # fmt: skip
    r = client.get("/patients/EMR:11?tab=labs")
    assert r.status_code == 200 and "150 mg/dL" in r.text and "badge--abn" in r.text
    r = client.get("/patients/EMR:11?tab=labs&view=trend")
    assert r.status_code == 200 and "Lab trend" in r.text
    monkeypatch.setattr(emr, "vitals", lambda _id: [])
    r = client.get("/patients/EMR:11?tab=vitals")
    assert r.status_code == 200 and "No vitals recorded." in r.text
    for tab in ("problems", "meds"):
        assert client.get(f"/patients/EMR:11?tab={tab}").status_code == 200


def test_real_problems_tab(chart_mode, client):
    r = client.get("/patients/EMR:11?tab=problems")
    assert r.status_code == 200
    # An active allergy exists → the tab opens on Allergies, with reactions in the detail.
    assert "1 active" in r.text and "Sample allergen" in r.text and "Hives, Rash" in r.text
    r = client.get("/patients/EMR:11?tab=problems&sec=problems&status=all")
    assert "ICD-10 Z00.0" in r.text and "Resolved" in r.text and "Old problem" in r.text
