"""Phase 1: source DB plumbing, tested without any SQL Server connection."""

import struct
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from app.config import Settings
from app.db.readonly import ReadOnlyViolationError, assert_read_only, install_read_only_guard
from app.db.source import (
    Source,
    SourceNotConfiguredError,
    build_engine,
    handle_datetimeoffset,
    is_configured,
    odbc_connection_string,
)
from app.db.sql_loader import SqlFileError, load_sql


def _settings(**overrides) -> Settings:
    base = {
        "sql_host": "db.example.invalid",
        "sql_user": "reader",
        "sql_password": SecretStr("p;w}d"),
        "feature_legacy_dmz": False,
    }
    return Settings(_env_file=None, **(base | overrides))


# --- datetimeoffset converter ---------------------------------------------------------------


def _pack(y, mo, d, h, mi, s, ns, tzh, tzm) -> bytes:
    return struct.pack("<6hI2h", y, mo, d, h, mi, s, ns, tzh, tzm)


def test_datetimeoffset_negative_offset():
    value = handle_datetimeoffset(_pack(2014, 3, 9, 14, 30, 5, 123_456_700, -5, 0))
    assert value == datetime(2014, 3, 9, 14, 30, 5, 123_456, tzinfo=value.tzinfo)
    assert value.utcoffset() == timedelta(hours=-5)


def test_datetimeoffset_half_hour_offset_and_utc():
    assert handle_datetimeoffset(_pack(2020, 1, 1, 0, 0, 0, 0, 5, 30)).utcoffset() == timedelta(
        hours=5, minutes=30
    )
    assert handle_datetimeoffset(_pack(2020, 1, 1, 0, 0, 0, 0, 0, 0)).tzinfo is UTC


def test_datetimeoffset_null():
    assert handle_datetimeoffset(None) is None


# --- connection settings --------------------------------------------------------------------


def test_connection_string_is_encrypted_readonly_and_escaped():
    cs = odbc_connection_string(_settings(), "EMR")
    assert "Encrypt=yes" in cs
    assert "ApplicationIntent=ReadOnly" in cs
    assert "TrustServerCertificate=no" in cs
    assert "SERVER=tcp:db.example.invalid,1433" in cs
    assert "PWD={p;w}}d}" in cs  # ; and } in a password cannot break out of the value
    assert "Connection Timeout=15" in cs


def test_dmz_only_when_feature_on():
    assert not is_configured(Source.DMZ, _settings())
    assert is_configured(Source.DMZ, _settings(feature_legacy_dmz=True))
    with pytest.raises(SourceNotConfiguredError):
        build_engine(Source.DMZ, _settings())


def test_not_configured_without_host():
    assert not is_configured(Source.EMR, _settings(sql_host=""))


def test_build_engine_does_not_connect():
    engine = build_engine(Source.EMR, _settings())  # no driver / network needed
    assert engine.pool.size() == 10
    assert engine.dialect.name == "mssql"


# --- read-only guard ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "  -- comment\nSELECT d.IMREDEM_CODE FROM HPSITE.DEMOGRAPHICS d WHERE d.X = :x;",
        "WITH x AS (SELECT 1 AS a) SELECT a FROM x",
        "SELECT UPDATE_DATE, DELETED_FLAG, CREATED_BY FROM t",  # names containing keywords
        "SELECT 'please drop table x' AS note",  # keywords inside literals
    ],
)
def test_guard_allows_reads(sql):
    assert_read_only(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE HPSITE.DEMOGRAPHICS SET DEM_LASTNAME = 'x'",
        "DELETE FROM t",
        "DROP TABLE t",
        "INSERT INTO t VALUES (1)",
        "SELECT 1; DROP TABLE t",
        "SELECT * INTO new_table FROM t",
        "EXEC sp_who",
        "TRUNCATE TABLE t",
        "WITH x AS (SELECT 1 AS a) DELETE FROM t",
        "/* SELECT */ ALTER TABLE t ADD c int",
        "SELECT 1 /* ; */ ; MERGE t USING s ON 1=1 WHEN MATCHED THEN DELETE;",
    ],
)
def test_guard_blocks_writes(sql):
    with pytest.raises(ReadOnlyViolationError):
        assert_read_only(sql)


def test_guard_is_enforced_on_engine():
    engine = create_engine("sqlite://")
    install_read_only_guard(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
        with pytest.raises(ReadOnlyViolationError):
            conn.execute(text("CREATE TABLE t (a int)"))


# --- SQL file loader ------------------------------------------------------------------------


def test_load_sql_and_cache():
    clause = load_sql("meta/table_row_count.sql")
    assert ":schema_name" in clause.text
    assert load_sql("meta/table_row_count.sql") is clause


@pytest.mark.parametrize("name", ["meta/missing.sql", "../app/config.py", "emr/Bad-Name.sql"])
def test_load_sql_rejects_missing_or_bad_names(name):
    with pytest.raises(SqlFileError):
        load_sql(name)


def test_expanding_bind_params():
    engine = create_engine("sqlite://")
    clause = text("SELECT COUNT(*) FROM (SELECT 1 AS a UNION ALL SELECT 2) WHERE a IN :ids")
    from sqlalchemy import bindparam

    clause = clause.bindparams(bindparam("ids", expanding=True))
    with engine.connect() as conn:
        assert conn.execute(clause, {"ids": [1, 2, 3]}).scalar() == 2


def test_every_shipped_sql_file_is_read_only():
    from app.db.sql_loader import SQL_DIR

    names = [p.relative_to(SQL_DIR).as_posix() for p in SQL_DIR.rglob("*.sql")]
    assert names, "expected at least the meta/*.sql files"
    for name in names:
        load_sql(name)


def test_readyz_without_sources(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "checks": {"appdb": "ok"}}


def test_dbcheck_without_config(capsys):
    import cli

    assert cli.main(["dbcheck"]) == 1
    assert "No source databases configured" in capsys.readouterr().out


def test_datetime_sanity():
    # Converter output compares correctly with UTC instants.
    a = handle_datetimeoffset(_pack(2020, 1, 1, 7, 0, 0, 0, -5, 0))
    assert a == datetime(2020, 1, 1, 12, 0, tzinfo=UTC)


def test_idle_ping_replaces_a_dead_pooled_connection():
    """Perf #1: no ping per query, but a stale connection is still detected and replaced."""
    import time as _time

    from sqlalchemy import event
    from sqlalchemy.pool import QueuePool

    from app.db.source import install_idle_ping

    engine = create_engine("sqlite://", poolclass=QueuePool, pool_size=1, max_overflow=0)
    install_idle_ping(engine, idle_seconds=0)
    connects = []
    event.listen(engine, "connect", lambda dbapi_conn, _rec: connects.append(dbapi_conn))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
    connects[0].close()  # the network dropped the pooled connection
    _time.sleep(0.01)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
    assert len(connects) == 2  # replaced transparently


def test_source_engine_settings_avoid_extra_round_trips():
    engine = build_engine(Source.EMR, _settings())
    assert engine.pool._pre_ping is False
    assert engine.pool._reset_on_return is not None  # value object exists...
    assert str(engine.pool._reset_on_return).lower().endswith("none")  # ...and means "no reset"


def test_sql_comment_with_parameter_name_is_rejected(tmp_path, monkeypatch):
    from app.db import sql_loader

    (tmp_path / "emr").mkdir()
    (tmp_path / "emr" / "bad.sql").write_text("-- filters by :year\nSELECT 1", encoding="utf-8")
    monkeypatch.setattr(sql_loader, "SQL_DIR", tmp_path)
    sql_loader.load_sql.cache_clear()
    with pytest.raises(SqlFileError, match="comment"):
        sql_loader.load_sql("emr/bad.sql")
    sql_loader.load_sql.cache_clear()
