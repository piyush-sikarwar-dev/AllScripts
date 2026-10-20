"""Liveness and readiness probes."""

import anyio
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.app import new_session
from app.db.source import Source, configured_sources
from app.repositories.base import run_scalar
from app.security import is_production, sql_login_problems

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _ping(source: Source) -> str:
    try:
        return "ok" if run_scalar(source, "meta/ping.sql") == 1 else "error"
    except Exception:
        return "error"  # no exception text: it can contain host names / login names


def _ping_appdb() -> str:
    try:
        with new_session() as db:
            return "ok" if db.execute(text("SELECT 1")).scalar() == 1 else "error"
    except Exception:
        return "error"


@router.get("/readyz")
async def readyz() -> JSONResponse:
    checks: dict[str, str] = {}
    for source in configured_sources():
        checks[source.value] = await anyio.to_thread.run_sync(_ping, source)
    checks["appdb"] = await anyio.to_thread.run_sync(_ping_appdb)
    if is_production():
        writable = await anyio.to_thread.run_sync(sql_login_problems)
        checks["sql_login"] = "writable" if writable else "read-only"
    ok = all(v in ("ok", "skipped", "read-only") for v in checks.values())
    return JSONResponse({"status": "ok" if ok else "error", "checks": checks},
                        status_code=200 if ok else 503)  # fmt: skip
