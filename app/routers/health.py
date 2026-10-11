"""Liveness and readiness probes."""

import anyio
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.source import Source, configured_sources
from app.repositories.base import run_scalar

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _ping(source: Source) -> str:
    try:
        return "ok" if run_scalar(source, "meta/ping.sql") == 1 else "error"
    except Exception:
        return "error"  # no exception text: it can contain host names / login names


@router.get("/readyz")
async def readyz() -> JSONResponse:
    checks: dict[str, str] = {}
    for source in configured_sources():
        checks[source.value] = await anyio.to_thread.run_sync(_ping, source)
    checks["appdb"] = "skipped"  # TODO(Phase 2): app database check.
    ok = all(v in ("ok", "skipped") for v in checks.values())
    return JSONResponse({"status": "ok" if ok else "error", "checks": checks},
                        status_code=200 if ok else 503)  # fmt: skip
