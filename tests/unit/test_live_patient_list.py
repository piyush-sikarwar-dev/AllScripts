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


def test_chart_not_connected_page(sql, real_mode, client, monkeypatch):
    from app import crosswalk as crosswalk_module
    from app.config import get_settings

    settings = get_settings().model_copy(update={"use_fake_data": False})
    monkeypatch.setattr(crosswalk_module, "get_settings", lambda: settings)
    crosswalk_module.clear_cache()
    with new_session() as db:
        replace_crosswalk(db, build_crosswalk_rows([{"emr_id": 11}], [], BUILT)[0])
    r = client.get("/patients/EMR:11")
    assert r.status_code == 501
    assert "Not connected yet" in r.text
    crosswalk_module.clear_cache()
