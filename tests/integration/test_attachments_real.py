"""Chart attachments against the real EMR (read-only; counts and file signatures only).

Run explicitly:  RUN_INTEGRATION=1 uv run pytest -m integration
"""

import pytest
from sqlalchemy import text

from app.db.source import Source, configured_sources, get_engine
from app.repositories import emr, live

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not configured_sources(), reason="SQL_HOST not configured"),
]


@pytest.fixture(scope="module")
def emr_id() -> int:
    sql = (
        "SELECT TOP 1 IMREDEMEC_CODE FROM HPSITE.CHARTATTACHMENT "
        "GROUP BY IMREDEMEC_CODE HAVING COUNT(*) BETWEEN 10 AND 30 ORDER BY IMREDEMEC_CODE DESC"
    )
    with get_engine(Source.EMR).connect() as conn:
        return int(conn.execute(text(sql)).scalar())


def test_every_attachment_is_listed(emr_id):
    sql = (
        "SELECT COUNT(*) FROM HPSITE.CHARTATTACHMENT "
        "WHERE IMREDEMEC_CODE = :p AND ISNULL(TAG_ARCHIVED, 0) = 0"
    )
    with get_engine(Source.EMR).connect() as conn:
        expected = conn.execute(text(sql), {"p": emr_id}).scalar()
    listed = [d for d in live.documents(emr_id) if d["kind"] == "attachment"]
    assert len(listed) == expected


def test_attachment_file_is_patient_guarded(emr_id):
    item = next(d for d in live.documents(emr_id) if d["kind"] == "attachment" and d["format"])
    if item["format"] == "rtf":
        pytest.skip("first attachment is text only")
    assert emr.chart_attachment_file(emr_id, item["id"]) is not None
    assert emr.chart_attachment_file(emr_id + 1, item["id"]) is None
