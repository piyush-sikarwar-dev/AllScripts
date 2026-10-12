"""Ntier_0010060 (PM) read-only queries — one function per .sql file."""

from typing import Any

from app.db.source import Source
from app.repositories.base import run_query

PM_ACCOUNT = "ntier/pm_account.sql"


def pm_account(ntier_id: int) -> dict[str, Any] | None:
    rows = run_query(Source.NTIER, PM_ACCOUNT, {"ntier_id": ntier_id})
    return rows[0] if rows else None
