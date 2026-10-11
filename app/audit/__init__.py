"""Audit trail: who viewed / searched / exported what (CLAUDE.md §5, §8).

Rows are written in a background task after the response is sent, so the user never waits on
them; failures are logged as errors (never silently dropped). `detail` holds no PHI values —
only things like the tab name, page number or which search fields were used.
"""

import logging
from typing import Any

from fastapi import BackgroundTasks, Request

from app.auth import client_ip
from app.db.app import new_session
from app.repositories.appdb import audit as audit_repo

log = logging.getLogger("app.audit")


def write_audit(**row: Any) -> None:
    try:
        with new_session() as db:
            audit_repo.insert(db, **row)
    except Exception:
        log.exception(
            "audit write failed action=%s request_id=%s", row.get("action"), row.get("request_id")
        )


def audit(
    request: Request,
    background: BackgroundTasks,
    action: str,
    *,
    patient_key: str | None = None,
    detail: dict[str, Any] | None = None,
    user_id: int | None = None,
) -> None:
    if user_id is None:
        user = getattr(request.state, "user", None)
        user_id = user.id if user else None
    background.add_task(
        write_audit,
        action=action,
        user_id=user_id,
        patient_key=patient_key,
        detail=detail or {},
        ip=client_ip(request),
        request_id=getattr(request.state, "request_id", None),
    )
