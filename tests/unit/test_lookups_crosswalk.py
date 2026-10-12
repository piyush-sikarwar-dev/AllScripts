"""Phase 3: lookups from config, formatting, crosswalk build rules and resolution."""

from datetime import UTC, date, datetime

import pytest
import yaml

from app import crosswalk as crosswalk_module
from app.config import get_settings
from app.crosswalk import clear_cache, resolve
from app.crosswalk.build import build_crosswalk_rows, replace_crosswalk, resolve_merges
from app.db.app import new_session
from app.formatting import datetime_local, mask_ssn, partial_date_masked, time_local
from app.lookups import CONFIG_DIR, LookupConfigError, Lookups, get_lookups, label
from app.services import NotFoundError

BUILT = datetime(2026, 10, 11, tzinfo=UTC)


# --- lookups --------------------------------------------------------------------------------


def test_shipped_config_loads():
    lk = Lookups().load_config()
    assert lk.history_category(21).group == "allergy"
    assert lk.history_category(24).group == "problem"
    assert lk.history_category(99).label == "History (code 99)"
    assert lk.history_category(99).group == "other"
    assert lk.date_precision(3) == "full"
    assert lk.is_active("hx_diagnosis", 1) and not lk.is_active("hx_diagnosis", 2)
    assert lk.visit_type(6) == lk.visit_type("6")
    assert lk.visit_type(6).label == "Office Visit" and lk.visit_type(6).is_office_visit
    assert not lk.visit_type(98).is_office_visit  # Review
    assert lk.visit_type(99999).label == "Visit type 99999"
    assert lk.date_precision(None) == "full"


def test_unknown_codes_never_raise():
    assert label("sex", 9) == "Unknown (code 9)"
    assert label("no_such_kind", "x") == "Unknown (code x)"
    assert label("sex", None) == "—"
    assert get_lookups().history_category(999).label == "History (code 999)"


def test_codes_are_normalised():
    lk = Lookups()
    lk.merge_dictionary("sex", {1: "Female"})
    assert lk.label("sex", 1) == lk.label("sex", "1") == lk.label("sex", 1.0) == "Female"


def _write_config(tmp_path, monkeypatch, **overrides):
    for name in (
        "lookups_fallback",
        "history_categories",
        "visit_types",
        "date_masks",
        "statuses",
        "lab_flags",
        "documents",
    ):
        src = CONFIG_DIR / f"{name}.yaml"
        data = overrides.get(name, yaml.safe_load(src.read_text(encoding="utf-8")))
        (tmp_path / f"{name}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setattr("app.lookups.CONFIG_DIR", tmp_path)


def test_configured_mappings(tmp_path, monkeypatch):
    _write_config(
        tmp_path,
        monkeypatch,
        history_categories={
            "default_group": "other",
            "categories": {21: {"label": "Allergies", "group": "allergy"}},
        },
        visit_types={"visit_types": {7: {"label": "Telephone", "is_office_visit": False}}},
        date_masks={"default": "full", "masks": {1: "year", 2: "month_year"}},
    )
    lk = Lookups().load_config()
    assert lk.history_category(21).group == "allergy"
    assert not lk.visit_type(7).is_office_visit
    assert lk.date_precision(1) == "year" and lk.date_precision(3) == "full"


def test_bad_config_fails_fast(tmp_path, monkeypatch):
    _write_config(
        tmp_path, monkeypatch, history_categories={"categories": {21: {"group": "nonsense"}}}
    )
    with pytest.raises(LookupConfigError):
        Lookups().load_config()


# --- formatting -----------------------------------------------------------------------------


def test_partial_date_masked_unknown_mask_shows_full_date():
    assert partial_date_masked(date(2009, 3, 7), 42) == "03/07/2009"
    assert partial_date_masked(None, 1) == "—"


def test_datetime_local_converts_to_clinic_tz():
    assert get_settings().clinic_tz == "America/New_York"
    value = datetime(2020, 7, 1, 16, 5, tzinfo=UTC)  # EDT = UTC-4
    assert datetime_local(value) == "07/01/2020 12:05 PM"
    assert time_local(datetime(2020, 1, 1, 0, 30)) == "12:30 AM"
    assert datetime_local(None) == "—"


def test_mask_ssn():
    assert mask_ssn("123-45-6789") == "***-**-6789"
    assert mask_ssn(None) == "—"


# --- crosswalk build rules ------------------------------------------------------------------


def test_build_rules():
    links = [
        {"emr_id": 1, "ntier_id": 10, "ntier_active_id": 10},  # ExactId
        {"emr_id": 2, "ntier_id": None, "ntier_active_id": None},  # None
        {"emr_id": 3, "ntier_id": 31, "ntier_active_id": 30},  # ambiguous: 30 is active
        {"emr_id": 3, "ntier_id": 30, "ntier_active_id": 30},
        {"emr_id": 4, "ntier_id": 42, "ntier_active_id": 99},  # ambiguous, none active
        {"emr_id": 4, "ntier_id": 41, "ntier_active_id": 99},  #   → lowest
        {"emr_id": 5, "ntier_id": 10, "ntier_active_id": 10},  # duplicate index rows
        {"emr_id": 5, "ntier_id": 10, "ntier_active_id": 10},
        {"emr_id": 6, "ntier_id": None, "ntier_active_id": None},  # merged into 1
    ]
    rows, summary = build_crosswalk_rows(links, [{"original_id": 6, "current_id": 1}], BUILT)
    by_key = {r["patient_key"]: r for r in rows}
    assert (by_key["EMR:1"]["ntier_id"], by_key["EMR:1"]["match_method"]) == (10, "ExactId")
    assert (by_key["EMR:2"]["ntier_id"], by_key["EMR:2"]["match_method"]) == (None, "None")
    assert (by_key["EMR:3"]["ntier_id"], by_key["EMR:3"]["match_method"]) == (
        30,
        "ExactId-ambiguous",
    )
    assert by_key["EMR:4"]["ntier_id"] == 41
    assert by_key["EMR:5"]["match_method"] == "ExactId"
    assert (by_key["EMR:6"]["emr_id"], by_key["EMR:6"]["ntier_id"]) == (1, 10)
    assert by_key["EMR:6"]["match_method"] == "Merged"
    assert summary == {"ExactId": 2, "None": 1, "ExactId-ambiguous": 2, "Merged": 1}


def test_merge_chains_and_cycles():
    assert resolve_merges([(1, 2), (2, 3)]) == {1: 3, 2: 3}
    cyclic = resolve_merges([(1, 2), (2, 1)])  # must terminate
    assert set(cyclic) == {1, 2}
    assert resolve_merges([(5, 5)]) == {}


# --- crosswalk resolution (real mode, app DB) -----------------------------------------------


@pytest.fixture
def real_mode(monkeypatch):
    settings = get_settings().model_copy(update={"use_fake_data": False})
    monkeypatch.setattr(crosswalk_module, "get_settings", lambda: settings)
    clear_cache()
    yield
    clear_cache()


@pytest.mark.anyio
async def test_resolve_from_table_and_merge_redirect(real_mode):
    links = [{"emr_id": 1, "ntier_id": 10, "ntier_active_id": 10},
             {"emr_id": 6, "ntier_id": None, "ntier_active_id": None}]  # fmt: skip
    rows, _ = build_crosswalk_rows(links, [{"original_id": 6, "current_id": 1}], BUILT)
    with new_session() as db:
        replace_crosswalk(db, rows)

    ref = await resolve("EMR:1")
    assert (ref.patient_key, ref.emr_id, ref.ntier_id) == ("EMR:1", 1, 10)
    merged = await resolve("EMR:6")
    assert merged.patient_key == "EMR:1" and merged.ntier_id == 10
    with pytest.raises(NotFoundError):
        await resolve("EMR:777")
    with pytest.raises(NotFoundError):
        await resolve("bogus")


@pytest.mark.anyio
async def test_replace_crosswalk_is_a_full_swap(real_mode):
    with new_session() as db:
        replace_crosswalk(db, build_crosswalk_rows([{"emr_id": 1}], [], BUILT)[0])
    with new_session() as db:
        replace_crosswalk(db, build_crosswalk_rows([{"emr_id": 2}], [], BUILT)[0])
    with pytest.raises(NotFoundError):
        await resolve("EMR:1")
    assert (await resolve("EMR:2")).match_method == "None"


def test_build_crosswalk_cli_without_config(capsys):
    import cli

    assert cli.main(["build-crosswalk"]) == 1
    assert "EMR source not configured" in capsys.readouterr().out
