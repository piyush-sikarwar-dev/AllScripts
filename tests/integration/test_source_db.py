"""Integration tests against the real SQL Server (read-only, metadata + one timestamp).

Run explicitly:  RUN_INTEGRATION=1 uv run pytest -m integration
"""

from datetime import datetime

import pytest
from sqlalchemy import text

from app.db.source import Source, configured_sources, get_engine
from app.repositories.base import run_query, run_scalar

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not configured_sources(), reason="SQL_HOST not configured"),
]


def test_ping_each_source():
    for source in configured_sources():
        assert run_scalar(source, "meta/ping.sql") == 1


def test_demographics_row_count():
    count = run_scalar(
        Source.EMR,
        "meta/table_row_count.sql",
        {"schema_name": "HPSITE", "table_name": "DEMOGRAPHICS"},
    )
    assert count == 21_384


def test_server_info():
    info = run_query(Source.EMR, "meta/server_info.sql")[0]
    assert info["database_name"] == "EMR"


def test_datetimeoffset_converter_on_real_row():
    with get_engine(Source.EMR).connect() as conn:
        value = conn.execute(text("SELECT TOP 1 TAG_SYSTEMDATE FROM HPSITE.DEMOGRAPHICS")).scalar()
    assert value is None or (isinstance(value, datetime) and value.tzinfo is not None)
