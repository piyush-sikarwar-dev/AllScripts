"""Appointments against the real EMR + PM (read-only; counts only).

Run explicitly:  RUN_INTEGRATION=1 uv run pytest -m integration
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.db.source import Source, configured_sources, get_engine
from app.repositories import emr, live, ntier

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not configured_sources(), reason="SQL_HOST not configured"),
]


@pytest.fixture(scope="module")
def ref():
    """A PM-linked patient with a few dozen appointments (PM id via the EMR ↔ PM index)."""
    sql = (
        "SELECT TOP 1 s.IMREDEM_CODE AS emr_id, MIN(p.Patient_ID) AS ntier_id "
        "FROM HPSITE.ARCH_SCHEDULE AS s "
        "JOIN HPSITE.EXTSYS_PATIENTINDEX AS x ON x.IMREDEM_CODE = s.IMREDEM_CODE "
        "JOIN Ntier_0010060.PM.Patients AS p "
        "ON LTRIM(RTRIM(p.Patient_Number)) COLLATE DATABASE_DEFAULT "
        "= LTRIM(RTRIM(x.PATIENTID)) COLLATE DATABASE_DEFAULT "
        "GROUP BY s.IMREDEM_CODE HAVING COUNT(*) BETWEEN 20 AND 40 ORDER BY s.IMREDEM_CODE DESC"
    )
    with get_engine(Source.EMR).connect() as conn:
        row = conn.execute(text(sql)).mappings().one()
    return SimpleNamespace(emr_id=int(row["emr_id"]), ntier_id=int(row["ntier_id"]))


def test_every_emr_and_pm_appointment_appears_once(ref):
    merged = live.appointments(ref.emr_id, ref.ntier_id)
    emr_rows = emr.appointments(ref.emr_id)
    pm_rows = ntier.appointments(ref.ntier_id) if ref.ntier_id else []
    matched = sum(1 for a in merged if a["sources"] == ["EMR", "PM"])
    assert sum(1 for a in merged if "EMR" in a["sources"]) == len(emr_rows)
    assert len(merged) == len(emr_rows) + len(pm_rows) - matched
    assert len({a["id"] for a in merged}) == len(merged)
