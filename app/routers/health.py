"""Liveness and readiness probes."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict[str, object]:
    # TODO(Phase 1): SELECT 1 against EMR / Ntier / DMZ engines; Phase 2: the app database.
    return {"status": "ok", "checks": {}}
