"""Read-only engines for the source SQL Server databases (EMR, Ntier_0010060, DMZ).

One instance, one read-only login, one engine per database. Every engine:
  - connects with Encrypt=yes and ApplicationIntent=ReadOnly,
  - converts `datetimeoffset` (ODBC type -155) to timezone-aware datetimes,
  - sets a per-statement query timeout,
  - refuses any non-SELECT statement (app.db.readonly).
"""

import struct
import time
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.exc import DisconnectionError

from app.config import Settings, get_settings
from app.db.readonly import install_read_only_guard

SQL_DATETIMEOFFSET = -155


class Source(StrEnum):
    EMR = "emr"
    NTIER = "ntier"
    DMZ = "dmz"


class SourceNotConfiguredError(RuntimeError):
    """The source database is disabled (DMZ feature flag) or has no connection settings."""


def handle_datetimeoffset(value: bytes | None) -> datetime | None:
    """Decode SQL Server's datetimeoffset wire format into an aware datetime."""
    if value is None:
        return None
    year, month, day, hour, minute, second, nanos, tz_hour, tz_minute = struct.unpack(
        "<6hI2h", value
    )
    tz = timezone(timedelta(hours=tz_hour, minutes=tz_minute))
    if tz.utcoffset(None) == timedelta(0):
        tz = UTC
    return datetime(year, month, day, hour, minute, second, nanos // 1000, tzinfo=tz)


def _odbc_value(value: str) -> str:
    """Brace-quote a connection-string value so ; { } in passwords are safe."""
    return "{" + value.replace("}", "}}") + "}"


def odbc_connection_string(settings: Settings, database: str) -> str:
    parts = {
        "DRIVER": _odbc_value(settings.sql_driver),
        "SERVER": f"tcp:{settings.sql_host},{settings.sql_port}",
        "DATABASE": _odbc_value(database),
        "UID": _odbc_value(settings.sql_user),
        "PWD": _odbc_value(settings.sql_password.get_secret_value()),
        "Encrypt": "yes",
        "TrustServerCertificate": "yes" if settings.sql_trust_server_certificate else "no",
        "ApplicationIntent": "ReadOnly",
        "Connection Timeout": str(settings.sql_login_timeout),
        "APP": "legacy-viewer",
    }
    return ";".join(f"{k}={v}" for k, v in parts.items())


def database_name(source: Source, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return {
        Source.EMR: settings.emr_database,
        Source.NTIER: settings.ntier_database,
        Source.DMZ: settings.dmz_database,
    }[source]


def is_configured(source: Source, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if source is Source.DMZ and not settings.feature_legacy_dmz:
        return False
    return bool(settings.sql_host and settings.sql_user)


def build_engine(source: Source, settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    if not is_configured(source, settings):
        raise SourceNotConfiguredError(source.value)
    url = URL.create(
        "mssql+pyodbc",
        query={"odbc_connect": odbc_connection_string(settings, database_name(source, settings))},
    )
    # Performance (docs/PERFORMANCE_PLAN.md #1): every network round trip to SQL Server costs
    # ~50 ms from a workstation. Reads run in autocommit mode, so no transaction is ever open and
    # the pool does not need a ROLLBACK when a connection is returned; connections are pinged only
    # after they sat idle (instead of before every query). Results are unchanged.
    engine = create_engine(
        url,
        pool_size=10,  # parallel queries per screen (perf #2) x a few concurrent users
        max_overflow=10,
        pool_pre_ping=False,
        pool_reset_on_return=None,
        pool_recycle=1800,
        isolation_level="AUTOCOMMIT",
        connect_args={"timeout": settings.sql_login_timeout},
    )
    query_timeout = settings.sql_query_timeout

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        dbapi_conn.add_output_converter(SQL_DATETIMEOFFSET, handle_datetimeoffset)
        dbapi_conn.timeout = query_timeout

    install_idle_ping(engine)
    install_read_only_guard(engine)
    return engine


IDLE_PING_SECONDS = 60


def install_idle_ping(engine: Engine, idle_seconds: float = IDLE_PING_SECONDS) -> None:
    """Check a pooled connection only if it has been idle a while (networks drop idle links).

    A failed check raises DisconnectionError, which makes the pool discard that connection and
    hand out a fresh one — the same recovery pool_pre_ping gives, without a round trip per query.
    """

    @event.listens_for(engine, "checkin")
    def _checkin(_dbapi_conn, record):
        record.info["last_used"] = time.monotonic()

    @event.listens_for(engine, "checkout")
    def _checkout(dbapi_conn, record, _proxy):
        last_used = record.info.get("last_used")
        if last_used is None or time.monotonic() - last_used < idle_seconds:
            return
        try:
            cursor = dbapi_conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchall()
            cursor.close()
        except Exception as exc:
            raise DisconnectionError("stale pooled connection") from exc


_engines: dict[Source, Engine] = {}


def get_engine(source: Source) -> Engine:
    """Lazily created, process-wide engine for one source database."""
    if source not in _engines:
        _engines[source] = build_engine(source)
    return _engines[source]


def configured_sources() -> list[Source]:
    return [s for s in Source if is_configured(s)]


def dispose_engines() -> None:
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()
