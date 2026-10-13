"""Visits tab against the real EMR (read-only; asserts on counts and shapes, never on PHI).

Run explicitly:  RUN_INTEGRATION=1 uv run pytest -m integration
"""

import pytest
from sqlalchemy import text

from app.db.source import Source, configured_sources, get_engine
from app.repositories import live

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not configured_sources(), reason="SQL_HOST not configured"),
]


@pytest.fixture(scope="module")
def emr_id() -> int:
    """A patient with at least one encounter (the newest encounter's patient)."""
    with get_engine(Source.EMR).connect() as conn:
        return int(
            conn.execute(
                text("SELECT TOP 1 IMREDEMEC_CODE FROM HPSITE.ENCOUNTER ORDER BY IMREENC_CODE DESC")
            ).scalar()
        )


def test_list_total_matches_activity_and_rows_are_unique(emr_id):
    page = live.visits_page(emr_id, None, None, None, 1)
    activity = live.visits_activity(emr_id, None)
    assert page["total"] == activity["total"] == sum(activity["years"].values())
    ids = [r["encounter_id"] for r in page["rows"]]
    assert len(ids) == len(set(ids)) and len(ids) <= live.VISITS_PAGE_SIZE
    dates = [r["date"] for r in page["rows"]]
    assert dates == sorted(dates, reverse=True)  # newest first


def test_year_filter_matches_year_count(emr_id):
    activity = live.visits_activity(emr_id, None)
    year, count = max(activity["years"].items())
    assert live.visits_page(emr_id, None, year, None, 1)["total"] == count


def test_encounter_detail_is_ownership_checked(emr_id):
    first = live.visits_page(emr_id, None, None, None, 1)["rows"][0]
    enc = live.encounter(emr_id, first["encounter_id"])
    assert enc is not None and enc["encounter_id"] == first["encounter_id"]
    assert {"assessment", "plan", "text_notes", "vitals", "note_documents"} <= enc.keys()
    assert live.encounter(emr_id + 1, first["encounter_id"]) is None
