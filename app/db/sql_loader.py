"""Load and cache `.sql` files from app/sql/ as SQLAlchemy text() clauses.

One query per file, bound parameters only (`:name`). Files are checked with the read-only guard
when loaded, so a non-SELECT file fails at startup rather than at request time.
"""

import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy import TextClause, bindparam, text

from app.db.readonly import assert_read_only

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"

_NAME_RE = re.compile(r"^(emr|ntier|dmz|meta)/[a-z0-9_]+\.sql$")
_COMMENT_PARAM_RE = re.compile(r"(?<![:\w]):[A-Za-z_]\w*")


class SqlFileError(RuntimeError):
    """A referenced .sql file is missing, misnamed or not read-only."""


@lru_cache(maxsize=256)
def load_sql(name: str, expanding: tuple[str, ...] = ()) -> TextClause:
    """`load_sql("emr/patient_search.sql")`; `expanding=("ids",)` for `IN :ids` lists."""
    if not _NAME_RE.match(name):
        raise SqlFileError(f"invalid SQL file name: {name}")
    path = SQL_DIR / name
    if not path.is_file():
        raise SqlFileError(f"missing SQL file: {name}")
    sql = path.read_text(encoding="utf-8")
    for line in sql.splitlines():
        comment = line.split("--", 1)[1] if "--" in line else ""
        if _COMMENT_PARAM_RE.search(comment):
            # SQLAlchemy text() would turn ":name" inside a comment into a real bind parameter.
            raise SqlFileError(f"{name}: parameter-like ':name' inside a comment")
    try:
        assert_read_only(sql)
    except Exception as exc:
        raise SqlFileError(f"{name}: {exc}") from exc
    clause = text(sql)
    if expanding:
        clause = clause.bindparams(*(bindparam(p, expanding=True) for p in expanding))
    return clause


def check_sql_files(names: list[str]) -> None:
    """Fail fast at startup if any referenced SQL file is missing or invalid."""
    for name in names:
        load_sql(name)
