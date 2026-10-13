"""Chart and portal messages against the real EMR (read-only; counts only).

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
        "SELECT TOP 1 IMREDEM_CODE FROM HPSITE.MESSAGE_SAVED "
        "GROUP BY IMREDEM_CODE HAVING COUNT(*) BETWEEN 10 AND 30 ORDER BY IMREDEM_CODE DESC"
    )
    with get_engine(Source.EMR).connect() as conn:
        return int(conn.execute(text(sql)).scalar())


def test_every_saved_message_is_in_the_note_index(emr_id):
    with get_engine(Source.EMR).connect() as conn:
        saved = conn.execute(
            text("SELECT COUNT(*) FROM HPSITE.MESSAGE_SAVED WHERE IMREDEM_CODE = :p"), {"p": emr_id}
        ).scalar()
    index = live.note_index(emr_id)
    assert sum(1 for n in index if n["kind"] == "message") == saved


def test_message_detail_is_patient_guarded(emr_id):
    message = next(n for n in live.note_index(emr_id) if n["kind"] == "message")
    assert emr.note_message(emr_id, message["id"]) is not None
    assert emr.note_message(emr_id + 1, message["id"]) is None
