"""Read-only guard for the source databases.

Defence in depth: the SQL Server login should itself be read-only (db_datareader), but every
statement sent through a source engine is also checked here and anything that is not a plain
SELECT / WITH … SELECT is refused before it reaches the server.
"""

import re

from sqlalchemy import Engine, event


class ReadOnlyViolationError(RuntimeError):
    """A non-SELECT statement was about to be sent to a source database."""


_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_LITERALS = re.compile(r"'(?:[^']|'')*'")
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|GRANT|REVOKE|DENY"
    r"|BACKUP|RESTORE|DBCC|BULK|OPENROWSET|OPENQUERY|OPENDATASOURCE|SHUTDOWN|KILL|INTO|USE"
    r"|RECONFIGURE|WAITFOR|DECLARE|SET)\b",
    re.I,
)


def assert_read_only(statement: str) -> None:
    """Raise ReadOnlyViolationError unless `statement` is a single read-only query."""
    sql = _LITERALS.sub("''", _COMMENTS.sub(" ", statement)).strip().rstrip(";").strip()
    if not re.match(r"(?is)^(SELECT|WITH)\b", sql):
        raise ReadOnlyViolationError("only SELECT statements may run against source databases")
    if ";" in sql:
        raise ReadOnlyViolationError("multiple statements are not allowed")
    match = _FORBIDDEN.search(sql)
    if match:
        raise ReadOnlyViolationError(f"forbidden keyword in source query: {match.group(1).upper()}")


def install_read_only_guard(engine: Engine) -> None:
    @event.listens_for(engine, "before_cursor_execute")
    def _guard(_conn, _cursor, statement, _params, _context, _executemany):
        assert_read_only(statement)
