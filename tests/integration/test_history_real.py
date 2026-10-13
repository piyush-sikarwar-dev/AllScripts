"""Problems & allergies against the real EMR (read-only; counts only, never titles).

Run explicitly:  RUN_INTEGRATION=1 uv run pytest -m integration
"""

import pytest
from sqlalchemy import text

from app.db.source import Source, configured_sources, get_engine
from app.lookups import get_lookups
from app.repositories import live
from app.services.history_service import GROUP_TO_SECTION, _entry

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not configured_sources(), reason="SQL_HOST not configured"),
]


@pytest.fixture(scope="module")
def emr_id() -> int:
    """The patient with the most history entries."""
    with get_engine(Source.EMR).connect() as conn:
        sql = (
            "SELECT TOP 1 PATIENT_ID FROM HPSITE.HX_DIAGNOSIS "
            "GROUP BY PATIENT_ID ORDER BY COUNT(*) DESC"
        )
        return int(conn.execute(text(sql)).scalar())


def test_entries_per_section_match_latest_revisions(emr_id):
    with get_engine(Source.EMR).connect() as conn:
        rows = conn.execute(text(
            "SELECT x.CATEGORY_CODE, COUNT(*) FROM (SELECT h.CATEGORY_CODE, ROW_NUMBER() OVER "
            "(PARTITION BY h.HXDIAGNOSIS_ID ORDER BY h.TAG_REVISION DESC) AS rn "
            "FROM HPSITE.HX_DIAGNOSIS AS h WHERE h.PATIENT_ID = :p) AS x WHERE x.rn = 1 "
            "GROUP BY x.CATEGORY_CODE"
        ), {"p": emr_id}).all()  # fmt: skip
    expected: dict[str, int] = {}
    lk = get_lookups()
    for category, n in rows:
        section = GROUP_TO_SECTION.get(lk.history_category(category).group, "other")
        expected[section] = expected.get(section, 0) + n
    got: dict[str, int] = {}
    for e in live.history_entries(emr_id):
        section = _entry(e).section
        got[section] = got.get(section, 0) + 1
    assert got == expected


def test_change_history_is_patient_guarded(emr_id):
    entry = live.history_entries(emr_id)[0]
    assert live.history_changes(emr_id, entry["id"])  # at least the current revision
    assert live.history_changes(emr_id + 1, entry["id"]) == []
